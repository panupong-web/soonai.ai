# -*- coding: utf-8 -*-
"""โหมด debug: เก็บ traceback ของ exception ที่ถูกกลืนลงไฟล์ log + หมุนไฟล์อัตโนมัติ

ปัญหาที่แก้: โค้ดนี้กลืน exception หลายร้อยจุดแบบ `except Exception: pass` (เจตนาให้
CLI ไม่ล่ม) ผลคือเวลามีอะไรพังจริง ผู้ใช้เห็นแค่ "โมเดลตอบว่าง" หรือค่าที่หายไป
โดยไม่มีร่องรอยให้ตาม — crash.log เก็บเฉพาะ exception ที่หลุดถึง main เท่านั้น

วิธีใช้ (จาก soonai.py):
    import debug as _DBG
    ...
    except Exception as e:
        _DBG.log_swallowed(e, "load_json", f"อ่าน {path} ไม่ได้ — ใช้ค่าเริ่มต้น")
(ในบล็อก except ที่ไม่มีตัวแปร e เรียก ``_DBG.log_swallowed(None, ...)`` ได้ —
ดึงจาก sys.exc_info() ให้เอง)

เปิดโหมด:
    SOONAI_DEBUG=1            เปิด (รับ 1/true/yes/on/debug — ปิดด้วย 0/false/no/off)
    SOONAI_DEBUG_LOG=<path>   เปลี่ยนที่เก็บ log (ค่าเริ่มต้น <DATA_DIR>/logs/debug.log)
    SOONAI_DEBUG_MAX_BYTES=N  ขนาดสูงสุดต่อไฟล์ก่อนหมุน (ค่าเริ่มต้น 2 MiB)
    SOONAI_DEBUG_BACKUPS=N    จำนวนไฟล์เก่าที่เก็บ (ค่าเริ่มต้น 3 → debug.log.1..3)
    SOONAI_CRASH_LOG=<path>   เปลี่ยนที่เก็บ crash.log (ค่าเริ่มต้นรากโปรเจค · ใช้ในเทสต์)
    SOONAI_DEBUG_SUMMARY=N    จำนวนบรรทัดสรุปที่โชว์ตอนเปิดห้องแชท (ค่าเริ่มต้น 5 · 0 = ไม่โชว์)

การหมุนไฟล์: ก่อนเขียนทุกรายการ ถ้าขนาดไฟล์ + รายการใหม่จะเกินเพดาน จะเลื่อน
``debug.log`` → ``debug.log.1`` → ``debug.log.2`` … ทิ้งตัวที่เก่าสุดเมื่อครบ N
(ขนาดที่ใช้จริงจึงถูกจำกัดที่ MAX_BYTES × (BACKUPS+1) — ไม่มีทางบวมไม่จำกัด)

หลักการสำคัญ: **ห้ามทำให้โปรแกรมพัง** ทุกฟังก์ชันกลืน error ของตัวเองทั้งหมด
(พาธเขียนไม่ได้/ไม่มีสิทธิ์/ไฟล์ถูกล็อก = คืน False เฉย ๆ) และ **ปิดอยู่ = ไม่แตะดิสก์เลย**
"""
import os
import re as _re
import sys
import threading
import time
import traceback
from pathlib import Path

_DEFAULT_MAX_BYTES = 2 * 1024 * 1024     # 2 MiB ต่อไฟล์
_DEFAULT_BACKUPS = 3                     # เก็บ debug.log.1 .. .3
_ENTRY_LIMIT = 20000                     # ตัดรายการที่ยาวผิดปกติ (traceback ลึกๆ)
_DEFAULT_SUMMARY_LIMIT = 5               # บรรทัดสรุปที่โชว์ตอนเปิดห้องแชท
_CRASH_MAX_BYTES = 256 * 1024            # crash.log เล็กกว่าได้ เพราะเก็บเฉพาะตอนล่ม
_CRASH_BACKUPS = 2

_ON_VALUES = ("1", "true", "yes", "on", "debug", "y", "t")
_OFF_VALUES = ("", "0", "false", "no", "off", "n", "f", "none")

_lock = threading.RLock()
_hooks_installed = {"done": False}


# ---------- ตั้งค่า (อ่าน env ทุกครั้ง เพื่อให้เทสต์สลับได้กลางโปรเซส) ----------

def _flag(name):
    """ค่า env แบบตั้ง/ไม่ตั้ง → คืนสตริงตัวพิมพ์เล็กที่ตัดช่องว่างแล้ว ('0'/'' ถ้าไม่มี)"""
    try:
        return str(os.environ.get(name, "") or "").strip().lower()
    except Exception:
        return ""


def enabled():
    """เปิดโหมด debug อยู่ไหม (SOONAI_DEBUG) — ค่าที่ไม่รู้จักถือว่า 'ไม่เปิด'"""
    v = _flag("SOONAI_DEBUG")
    if v in _OFF_VALUES:
        return False
    return v in _ON_VALUES or (v not in _OFF_VALUES and bool(v))


def _env_int(name, default, lo, hi):
    try:
        v = int(_flag(name) or default)
    except Exception:
        return default
    if v < lo or v > hi:      # ค่าประหลาด (0/ติดลบ/ใหญ่เกิน) = ใช้ค่าเริ่มต้น
        return default
    return v


def max_bytes():
    return _env_int("SOONAI_DEBUG_MAX_BYTES", _DEFAULT_MAX_BYTES, 4096, 512 * 1024 * 1024)


def display_path(path=None):
    """พาธแบบสั้น ๆ ให้คนอ่าน (แทนที่โฟลเดอร์บ้านด้วย ``~``) — ใช้เฉพาะตอนแสดงผล"""
    try:
        s = str(path or log_path())
        home = str(Path.home())
        if home and s.lower().startswith(home.lower()):
            return "~" + s[len(home):]
        return s
    except Exception:
        return str(path or "")


def _brief(text, limit=70):
    """ตัดข้อความยาว ๆ ให้อ่านง่ายบนบรรทัดเดียว"""
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit - 1] + "…"


def summary_limit():
    """จำนวนบรรทัดสรุปที่ยอมให้แสดง (0 = ไม่แสดง — ยอมรับ 0 ต่างจากเพดานอื่น)"""
    try:
        v = int(_flag("SOONAI_DEBUG_SUMMARY") or _DEFAULT_SUMMARY_LIMIT)
    except Exception:
        return _DEFAULT_SUMMARY_LIMIT
    if v < 0 or v > 50:
        return _DEFAULT_SUMMARY_LIMIT
    return v


def backups():
    return _env_int("SOONAI_DEBUG_BACKUPS", _DEFAULT_BACKUPS, 1, 20)


def _data_dir():
    """โฟลเดอร์ข้อมูลระดับเครื่อง — ตรงกับ soonai._data_dir()

    ปกติได้ค่าจาก runtime (soonai mirror DATA_DIR ให้ตอนท้าย import) ส่วน fallback
    นี้มีไว้เผื่อถูกเรียกก่อน mirror จะเกิด (เช่น main พังตั้งแต่ต้น)
    """
    try:
        import runtime as R
        d = R.get("DATA_DIR")
        if d:
            return Path(d)
    except Exception:
        pass
    try:
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(base) / "SoonAI"
        return Path.home() / ".soonai"
    except Exception:
        return Path.cwd()


def log_path():
    """พาธไฟล์ debug log (SOONAI_DEBUG_LOG ทับได้ — ใช้ในเทสต์)"""
    try:
        ov = str(os.environ.get("SOONAI_DEBUG_LOG", "") or "").strip()
        if ov:
            return Path(ov)
    except Exception:
        pass
    try:
        return _data_dir() / "logs" / "debug.log"
    except Exception:
        return Path("debug.log")


def _part(path, i):
    """ไฟล์สำรองลำดับที่ i (1 = เก่าสุดที่ยังเก็บ)"""
    return path.with_name(f"{path.name}.{i}")


def crash_path():
    """ที่อยู่เดิมของ crash.log (รากโปรเจค) — เขียนผ่าน log_crash() เท่านั้น
    (SOONAI_CRASH_LOG ทับได้ เพื่อให้เทสต์ไม่ไปแตะ crash.log ตัวจริง)"""
    try:
        ov = str(os.environ.get("SOONAI_CRASH_LOG", "") or "").strip()
        if ov:
            return Path(ov)
    except Exception:
        pass
    try:
        import runtime as R
        return Path(R.BASE_DIR) / "crash.log"
    except Exception:
        return Path(__file__).resolve().parent.parent / "crash.log"


# ---------- เขียนไฟล์ + หมุน ----------

def _size(path):
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _rotate(path, n_backups):
    """เลื่อนไฟล์ตามลำดับ .1..N (ทิ้งเก่าสุด) — สำเร็จเมื่อ path ไม่เหลืออยู่"""
    moved = True
    for i in range(n_backups, 0, -1):
        src = _part(path, i - 1) if i > 1 else path
        dst = _part(path, i)
        if not src.exists():
            continue
        try:
            dst.unlink(missing_ok=True)
            os.replace(src, dst)
        except OSError:
            moved = False
    return moved


def _append(path, text, limits_bytes, n_backups):
    """ต่อท้ายไฟล์ (หมุนก่อนถ้าจำเป็น) — คืน True/False ไม่มีทาง raise"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    try:
        data = text.encode("utf-8", errors="replace")
    except Exception:
        data = b""
    try:
        size = _size(path)
        if size and size + len(data) > limits_bytes:
            if not _rotate(path, n_backups):
                # หมุนไม่ได้ (ไฟล์ถูกล็อก/สิทธิ์ไม่พอ) → กันบวมไม่จำกัดด้วยการทิ้งรายการ
                if size > limits_bytes * (n_backups + 2):
                    return False
        with open(path, "a", encoding="utf-8", errors="replace") as f:
            f.write(text)
            f.flush()
        return True
    except Exception:
        return False


def _stamp():
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "?"


def _header(where, note):
    lines = [f"[{_stamp()}] pid={os.getpid()} tid={threading.get_ident()} "
             f"thread={threading.current_thread().name}"]
    if where:
        lines.append(f"  where : {where}")
    if note:
        lines.append(f"  note  : {str(note)[:400]}")
    return lines


def _finish(text):
    """ตัดรายการยาวผิดปกติ + ใส่เส้นคั่นเพื่อให้อ่านง่าย"""
    if len(text) > _ENTRY_LIMIT:
        text = text[:_ENTRY_LIMIT] + "\n…(ตัดทอน — รายการยาวเกินเพดาน)\n"
    return text + "-" * 72 + "\n"


def _write(text, limits_bytes=None, n_backups=None, path=None):
    if not enabled():
        return False
    with _lock:
        p = path or log_path()
        return _append(p, _finish(text), limits_bytes or max_bytes(),
                       n_backups if n_backups is not None else backups())


def note(msg, where=""):
    """บันทึกข้อความ (ไม่มี traceback) — ใช้ตามร่องรอยการทำงานที่อยากรู้

    ตั้งชื่อพารามิเตอร์ของ log_swallowed เป็น ``why`` (ไม่ใช่ ``note``) เพื่อไม่ชนกับฟังก์ชันนี้
    """
    if not enabled():
        return False
    body = "\n".join(_header(where, msg)) + "\n"
    return _write(body)


def log_swallowed(exc=None, where="", why=""):
    """บันทึก traceback ของ exception ที่ถูกกลืน

    - exc: ตัว exception (ถ้าไม่ส่งมา จะดึงจาก sys.exc_info() ของบล็อก except ปัจจุบัน)
    - where: จุดที่กลืน เช่น "soonai.py:load_json"
    - why: คำอธิบายสั้น ๆ ว่ากลืนแล้วทำอะไรต่อ (จะได้ไม่ต้องเดาว่าปลอดภัยไหม)
    คืน True ถ้าเขียนลงไฟล์ได้จริง
    """
    if not enabled():
        return False
    if exc is None:
        try:
            if sys.exc_info()[0] is None:
                return False      # เรียกนอกบล็อก except = ไม่มีอะไรให้เก็บ
        except Exception:
            return False
    try:
        if exc is None:
            tb = traceback.format_exc()
        else:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception as e:
        tb = f"(ดึง traceback ไม่ได้: {e})\n"
    body = "\n".join(_header(where, why)) + "\n" + tb
    return _write(body)


def log_crash(text, where="main (unhandled)"):
    """เขียน crash.log (ของเดิม) แบบหมุนไฟล์ + สำเนาลง debug log ถ้าเปิดโหมดอยู่

    เดิมเขียนทับทุกครั้ง = ร่องรอยการล่มเก่าหายหมด เปลี่ยนเป็นต่อท้ายจนถึงเพดาน
    แล้วหมุนเป็น crash.log.1/.2 (คนอ่านไฟล์นี้ยังเห็นของล่าสุดเสมอที่ท้ายไฟล์)
    """
    body = f"[{_stamp()}] pid={os.getpid()}\n{text}"
    body = body if body.endswith("\n") else body + "\n"
    ok = _append(crash_path(), _finish(body), _CRASH_MAX_BYTES, _CRASH_BACKUPS)
    if enabled():
        _write("\n".join(_header(where, "exception หลุดถึง main — บันทึก crash.log แล้ว"))
               + "\n" + text)
    return ok


# ---------- ตาข่ายจับ error ที่มองไม่เห็น (thread / finalizer) ----------

def install_hooks():
    """จับ exception ที่ปกติ 'หายเงียบ' ให้ลง log ด้วย (เฉพาะตอนเปิดโหมด)

    - threading.excepthook: exception ใน thread (MCP reader, อนิเมชัน ฯลฯ)
    - sys.unraisablehook: exception ตอน __del__/finalizer ที่ Python กลืนเอง
    เรียกซ้ำได้ (ติดตั้งครั้งเดียว) — คืน True ถ้าติดตั้ง/ติดตั้งไว้แล้ว
    """
    if not enabled():
        return False
    if _hooks_installed["done"]:
        return True
    prev_thread = getattr(threading, "excepthook", None)
    prev_unraisable = getattr(sys, "unraisablehook", None)

    def _thread_hook(args):
        try:
            log_swallowed(getattr(args, "exc_value", None),
                          f"thread:{getattr(args, 'thread', None) and args.thread.name}",
                          "exception ใน thread ถูกกลืน")
        except Exception:
            pass
        try:
            if prev_thread is not None:
                prev_thread(args)
        except Exception:
            pass

    def _unraisable_hook(unraisable):
        try:
            log_swallowed(getattr(unraisable, "exc_value", None),
                          f"unraisable:{getattr(unraisable, 'object', None)!r}",
                          "exception ตอน finalize (__del__/gc)")
        except Exception:
            pass
        try:
            if prev_unraisable is not None:
                prev_unraisable(unraisable)
        except Exception:
            pass

    try:
        threading.excepthook = _thread_hook
        if hasattr(sys, "unraisablehook"):
            sys.unraisablehook = _unraisable_hook
        _hooks_installed["done"] = True
    except Exception:
        return False
    return True


# ---------- สรุปว่า exception ที่ถูกกลืนเกิดซ้ำที่ไหน (อ่านจากไฟล์ log) ----------

_SEP_RE = _re.compile(r"^-{20,}[ \t]*$", _re.M)      # เส้นคั่นระหว่างรายการ
_HEAD_RE = _re.compile(r"^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\]", _re.M)
_WHERE_RE = _re.compile(r"^ {2}where : (.+)$", _re.M)
_NOTE_RE = _re.compile(r"^ {2}note  : (.+)$", _re.M)
# บรรทัดสุดท้ายของ traceback (ไม่ย่อหน้า) เช่น `json.decoder.JSONDecodeError: Expecting value`
_EXC_RE = _re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Exit|Interrupt|Warning|Fault)):? ?(.*)$", _re.M)


def _log_files_oldest_first():
    """ไฟล์ log เรียงจากเก่า → ใหม่ (.N … .1 → ไฟล์ปัจจุบัน)"""
    p = log_path()
    out = [_part(p, i) for i in range(backups(), 0, -1)]
    return out + [p]


def _parse_entries(text):
    """แยก log เป็นรายการ ๆ ละ dict — บรรทัดที่ถูกตัดกลางไฟล์ (rotation) จะถูกข้าม
    หลักการ: ทุกฟิลด์ที่หาไม่ได้ = ค่าว่าง ไม่เคย raise"""
    out = []
    try:
        blocks = _SEP_RE.split(text or "")
    except Exception:
        return out
    for block in blocks:
        if not block or not block.strip():
            continue
        try:
            h = _HEAD_RE.search(block)
            if not h:
                continue                 # เศษบรรทัดที่ไม่มีหัวรายการ = ข้าม
            w = _WHERE_RE.search(block)
            e = _EXC_RE.search(block)
            n = _NOTE_RE.search(block)
            out.append({
                "date": h.group(1), "time": h.group(2),
                "where": (w.group(1).strip() if w else ""),
                "exc": (e.group(1) if e else ""),
                "msg": (e.group(2).strip()[:80] if e else ""),
                "note": (n.group(1).strip()[:200] if n else ""),
            })
        except Exception:
            continue
    return out


def _read_logs():
    """อ่านทุกไฟล์ log (เก่า → ใหม่) — อ่านไม่ได้ = ข้าม"""
    parts = []
    for f in _log_files_oldest_first():
        try:
            if f.exists():
                parts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "".join(parts)


def entries():
    """รายการทั้งหมดในไฟล์ log (เก่า → ใหม่) — ใช้ตรวจ/เทสต์"""
    return _parse_entries(_read_logs())


def summary(limit=10):
    """สรุปว่า "กลืน exception" ซ้ำที่จุดใดมากที่สุด (นับจาก log ที่ค้างอยู่ทุกไฟล์)

    คืน list ของ dict เรียงจากมากไปน้อย:
    ``{where, count, last, exc, msg, note, errors}``
    - ``last``  = เวลาเกิดครั้งล่าสุด (YYYY-MM-DD HH:MM:SS)
    - ``exc``   = ชนิด exception ของรายการล่าสุดที่ระบุได้ · ``msg`` = ข้อความสั้น
    - ``note``  = คำอธิบายว่ากลืนแล้วทำอะไรต่อ (จากรายการล่าสุดที่มี)
    ``limit<=0`` = ไม่จำกัดจำนวนแกน
    """
    groups = {}
    for e in entries():
        key = e["where"] or "(ไม่ระบุที่มา)"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"where": key, "count": 0, "last": "", "exc": "",
                               "msg": "", "note": "", "errors": 0}
        g["count"] += 1
        g["last"] = f"{e['date']} {e['time']}"
        if e["exc"]:
            g["errors"] += 1
            g["exc"], g["msg"] = e["exc"], e["msg"]
        if e["note"]:                      # "กลืนแล้วทำอะไรต่อ" เอาจากรายการล่าสุดที่มี
            g["note"] = e["note"]
    rows = sorted(groups.values(), key=lambda r: (-r["count"], r["where"]))
    return rows if limit is None or limit <= 0 else rows[:limit]


def summary_lines(limit=8):
    """บรรทัดสรุปแบบข้อความล้วน (ให้ UI เอาไปใส่สีเอง) — ไม่มีอะไร = []"""
    rows = summary(limit + 1)
    if not rows:
        return []
    out = []
    for r in rows[:limit]:
        detail = f"{r['exc']}: {r['msg']}".strip(": ") if r["exc"] else (r["note"] or "-")
        out.append(f"{r['count']}×  {r['where']}  —  {_brief(detail)} (ล่าสุด {r['last'][11:]})")
    if len(rows) > limit:
        out.append(f"…และอีก {len(rows) - limit} จุด (ดูทั้งหมด: {display_path()})")
    return out


def startup_lines():
    """บล็อกบรรทัดสั้น ๆ สำหรับ "โชว์ตอนเปิดห้องแชท" เวลาเปิดโหมด debug อยู่

    ปิดโหมด/ตั้ง SOONAI_DEBUG_SUMMARY=0 = คืน [] (ผู้เรียกจะไม่พิมพ์อะไรเลย)
    """
    if not enabled():
        return []
    limit = summary_limit()
    if limit <= 0:
        return []
    rows = summary(0)
    total = sum(r["count"] for r in rows)
    head = (f"โหมด debug: เปิด — ยังไม่พบ exception ที่ถูกกลืน · log: {display_path()}" if not rows
            else (f"โหมด debug: เปิด — พบ exception ที่ถูกกลืน {total} ครั้ง "
                  f"จาก {len(rows)} จุด (log: {display_path()})"))
    out = [head]
    for r in rows[:limit]:
        detail = f"{r['exc']}: {r['msg']}".strip(": ") if r["exc"] else (r["note"] or "-")
        out.append(f"   {r['count']}× {r['where']} — {_brief(detail)}")
    if len(rows) > limit:
        out.append(f"   …และอีก {len(rows) - limit} จุด")
    return out


# ---------- อ่าน log (ให้คำสั่ง/เทสต์ดูย้อนหลังได้) ----------

def tail(limit=40):
    """คืนบรรทัดท้าย ๆ ของ log (ไล่จากไฟล์สำรองล่าสุดถ้าไฟล์ปัจจุบันสั้นไม่พอ)"""
    out = []
    p = log_path()
    for cand in [p] + [_part(p, i) for i in range(1, backups() + 1)]:
        try:
            if not cand.exists():
                continue
            lines = cand.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        out = lines[-limit:] + out
        if len(out) >= limit:
            break
    return out[-limit:]


def status_line():
    """สรุปสั้น ๆ ว่าเปิดอยู่ไหม + เก็บที่ไหน + ไฟล์ใหญ่เท่าไร (ไว้แสดงให้ผู้ใช้เห็น)"""
    if not enabled():
        return "โหมด debug: ปิด (เปิดด้วย SOONAI_DEBUG=1)"
    p = log_path()
    kb = _size(p) / 1024.0
    return (f"โหมด debug: เปิด · {display_path(p)} "
            f"({kb:.0f} KB, หมุนที่ {max_bytes() // 1024} KB เก็บ {backups()} ไฟล์)")
