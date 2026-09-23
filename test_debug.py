# -*- coding: utf-8 -*-
"""Regression: โหมด debug (shared/debug.py) — เก็บ traceback ของ exception ที่ถูกกลืน + หมุนไฟล์

สิ่งที่ล็อกไว้:
- ปิดโหมด (ค่าเริ่มต้น) = ไม่แตะดิสก์เลย ทุกฟังก์ชันคืน False เฉย ๆ
- เปิดด้วย SOONAI_DEBUG=1 · ค่าปิด (0/false/no/off) ต้องปิดจริง (ของเดิมเช็ค truthiness = "0" ก็เปิด!)
- เก็บ traceback ครบ: where · pid · thread · ชื่อ exception
- หมุนไฟล์ตามเพดาน + จำนวนสำรอง · ไฟล์เก่าสุดถูกทิ้ง · เขียนต่อได้ไม่พัง
- เขียนไม่ได้ (พาธเป็นโฟลเดอร์/ไม่มีสิทธิ์) = กลืน error ของตัวเอง ไม่ทำให้โปรแกรมพัง
- ตาข่ายจับ error ที่มองไม่เห็น (threading.excepthook / sys.unraisablehook) ทำงานเฉพาะตอนเปิด
- ต่อสายจริงกับ soonai: load_json() ที่อ่านไฟล์พัง = มีร่องรอยใน log (ไฟล์หาย = ไม่ต้องมี)
ไม่แตะเน็ต · ไม่แตะไฟล์จริงของเครื่อง (ทุกอย่างอยู่ในโฟลเดอร์ temp และ log ชี้ด้วย env)
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

TMP = Path(tempfile.mkdtemp(prefix="soonai-debugtest-"))
LOG = TMP / "debug.log"
CRASH = TMP / "crash.log"
os.environ["SOONAI_DEBUG_LOG"] = str(LOG)
os.environ["SOONAI_CRASH_LOG"] = str(CRASH)
os.environ.pop("SOONAI_DEBUG", None)

import debug as _DBG  # noqa: E402 - ต้อง sys.path.insert ก่อน

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


def read_log():
    try:
        return LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def reset_log():
    for p in [LOG] + [_DBG._part(LOG, i) for i in range(1, 6)]:
        try:
            p.unlink()
        except OSError:
            pass


def boom(kind=ValueError):
    try:
        raise kind("ข้อความทดสอบ")
    except Exception as e:
        return e


# ---------- 1) ปิดอยู่ = ไม่แตะดิสก์ ----------
reset_log()
check("ค่าเริ่มต้น = ปิดโหมด", _DBG.enabled() is False)
check("ปิด: log_swallowed คืน False", _DBG.log_swallowed(ValueError("x"), "t") is False)
check("ปิด: note คืน False", _DBG.note("x") is False)
check("ปิด: install_hooks คืน False", _DBG.install_hooks() is False)
check("ปิด: ไม่มีไฟล์ log ถูกสร้าง", not LOG.exists())
check("ปิด: status_line บอกว่าปิด", "ปิด" in _DBG.status_line())


# ---------- 2) การอ่านค่า env (ของเดิมนับ "0" เป็นเปิด = ต้องไม่เป็นอีก) ----------
ON = ("1", "true", "yes", "on", "debug", "TRUE", "on ")
OFF = ("0", "false", "no", "off", "none", "")
for v in ON:
    os.environ["SOONAI_DEBUG"] = v
    check(f"SOONAI_DEBUG={v!r} = เปิด", _DBG.enabled() is True)
for v in OFF:
    os.environ["SOONAI_DEBUG"] = v
    check(f"SOONAI_DEBUG={v!r} = ปิด", _DBG.enabled() is False)
os.environ["SOONAI_DEBUG"] = "1"
check("ค่าเริ่มต้นของเพดานไฟล์ = 2 MiB", _DBG.max_bytes() == 2 * 1024 * 1024)
check("ค่าเริ่มต้นของจำนวนสำรอง = 3", _DBG.backups() == 3)
os.environ["SOONAI_DEBUG_MAX_BYTES"] = "0"          # ค่าประหลาด = ใช้ค่าเริ่มต้น
os.environ["SOONAI_DEBUG_BACKUPS"] = "-5"
check("เพดาน/จำนวนสำรองที่ผิด = ใช้ค่าเริ่มต้น", _DBG.max_bytes() == 2 * 1024 * 1024
      and _DBG.backups() == 3)
os.environ.pop("SOONAI_DEBUG_MAX_BYTES", None)
os.environ.pop("SOONAI_DEBUG_BACKUPS", None)
check("log_path เคารพ SOONAI_DEBUG_LOG", str(_DBG.log_path()) == str(LOG))


# ---------- 3) เก็บ traceback ครบ ----------
reset_log()
exc = boom(KeyError)
check("log_swallowed เขียนสำเร็จ", _DBG.log_swallowed(exc, "soonai.py:load_json",
                                                     "อ่าน config ไม่ได้ — ใช้ค่าเริ่มต้น") is True)
txt = read_log()
check("มีชื่อ exception ใน log", "KeyError" in txt, txt[:200])
check("มีร่องรอย call stack", "Traceback (most recent call last)" in txt)
check("มี where ให้ตามได้", "soonai.py:load_json" in txt)
check("มี pid ของโปรเซส", f"pid={os.getpid()}" in txt)
check("มีชื่อ thread", f"thread={threading.current_thread().name}" in txt)
check("มีคำอธิบายว่ากลืนแล้วทำอะไรต่อ", "ใช้ค่าเริ่มต้น" in txt)
check("log_swallowed(note=None) ยังใช้ได้", _DBG.log_swallowed(exc, "w/x") is True)


# ---------- 4) เรียกใน/นอกบล็อก except ----------
reset_log()
try:
    {}["ไม่มีคีย์"]
except Exception:
    in_except = _DBG.log_swallowed()
check("ในบล็อก except (ไม่ส่ง exc) = ดึงจาก sys.exc_info() ได้", in_except is True)
check("ได้ชื่อ exception จริง", "KeyError" in read_log())
check("นอกบล็อก except = False ไม่พัง", _DBG.log_swallowed() is False)
check("ส่ง exc=None แบบไม่มี exception = False", _DBG.log_swallowed(None, "w") is False)


# ---------- 5) ตัดรายการยาวผิดปกติ ----------
reset_log()
_DBG.note("ก" * (_DBG._ENTRY_LIMIT * 3), "long")
size = LOG.stat().st_size
check("note ยาวผิดปกติถูกตัดเหลือบรรทัดสรุปสั้น ๆ", 0 < size < 2000, size)

_trimmed = _DBG._finish("x" * (_DBG._ENTRY_LIMIT * 2))
check("รายการยาว (traceback ลึก ๆ) ถูกตัดตามเพดาน",
      len(_trimmed) < _DBG._ENTRY_LIMIT + 200, len(_trimmed))
check("มีบรรทัดบอกว่าถูกตัด", "ตัดทอน" in _trimmed)
check("รายการสั้นไม่ถูกแก้", _DBG._finish("สั้น") == "สั้น" + "-" * 72 + "\n")


# ---------- 6) หมุนไฟล์อัตโนมัติ ----------
reset_log()
os.environ["SOONAI_DEBUG_MAX_BYTES"] = "4096"
os.environ["SOONAI_DEBUG_BACKUPS"] = "2"
for i in range(80):
    _DBG.note("x" * 300, f"fill-{i}")
files = sorted(p.name for p in TMP.glob("debug.log*"))
check("หมุนครบตามจำนวนสำรอง (current + .1 + .2)", files == ["debug.log", "debug.log.1", "debug.log.2"],
      files)
check("ไฟล์ปัจจุบันไม่เกินเพดาน", LOG.stat().st_size <= 4096, LOG.stat().st_size)
check("ไฟล์สำรองไม่เกินเพดาน", (_DBG._part(LOG, 1).stat().st_size <= 4096
                                and _DBG._part(LOG, 2).stat().st_size <= 4096))
check("ไฟล์เก่าสุดถูกทิ้ง (ไม่มี .3)", not _DBG._part(LOG, 3).exists())
tail_lines = _DBG.tail(10)
check("tail ยังอ่านย้อนหลังได้หลังหมุน", len(tail_lines) == 10 and "fill-" in "\n".join(tail_lines),
      len(tail_lines))
check("ข้อมูลล่าสุดอยู่ในไฟล์ปัจจุบัน", "fill-79" in read_log())
check("ข้อมูลเก่าสุดไม่ได้อยู่ในไฟล์ปัจจุบัน", "fill-0\n" not in read_log())

os.environ["SOONAI_DEBUG_BACKUPS"] = "1"
reset_log()
for i in range(80):
    _DBG.note("y" * 300, f"one-{i}")
check("ตั้งสำรอง=1 → มีแค่ .1", sorted(p.name for p in TMP.glob("debug.log*")) ==
      ["debug.log", "debug.log.1"], sorted(p.name for p in TMP.glob("debug.log*")))
check("ยังเขียนต่อเนื่องได้ไม่พัง", "one-79" in read_log())
os.environ["SOONAI_DEBUG_BACKUPS"] = "2"


# ---------- 7) เขียนไม่ได้ = ต้องไม่ทำให้โปรแกรมพัง ----------
reset_log()
os.environ["SOONAI_DEBUG_LOG"] = str(TMP)          # ชี้ไปที่ "โฟลเดอร์" = เปิดเขียนไม่ได้
check("พาธเป็นโฟลเดอร์: note คืน False ไม่ raise", _DBG.note("x") is False)
check("พาธเป็นโฟลเดอร์: log_swallowed คืน False ไม่ raise",
      _DBG.log_swallowed(ValueError("v"), "w") is False)
check("พาธเป็นโฟลเดอร์: tail คืน list ว่าง", _DBG.tail(5) == [])
check("พาธเป็นโฟลเดอร์: status_line ยังอ่านได้", "debug" in _DBG.status_line())
os.environ["SOONAI_DEBUG_LOG"] = str(LOG)
check("พาธซ้อนชั้นที่ยังไม่มี = สร้างโฟลเดอร์ให้เอง",
      _DBG._append(TMP / "deep" / "more" / "x.log", "hi\n", 4096, 1) is True)
check("ไฟล์ลึกถูกสร้างจริง", (TMP / "deep" / "more" / "x.log").read_text(encoding="utf-8") == "hi\n")


# ---------- 8) crash.log หมุนไฟล์ (ของเดิมเขียนทับ = ร่องรอยเก่าหาย) ----------
try:
    CRASH.unlink()
except OSError:
    pass
check("log_crash เขียนครั้งแรกได้", _DBG.log_crash("crash ครั้งที่ 1\n") is True)
check("log_crash เขียนครั้งที่สองต่อท้าย", _DBG.log_crash("crash ครั้งที่ 2\n") is True)
crash_txt = CRASH.read_text(encoding="utf-8")
check("crash.log เก็บทั้งสองครั้ง", "ครั้งที่ 1" in crash_txt and "ครั้งที่ 2" in crash_txt)
before = CRASH.stat().st_size
for i in range(40):
    _DBG.log_crash("z" * 10000 + f" {i}\n")
check("crash.log ถูกหมุนเมื่อเกินเพดาน", _DBG._part(CRASH, 1).exists())
check("crash.log ยังถูกจำกัดขนาด", CRASH.stat().st_size <= _DBG._CRASH_MAX_BYTES, CRASH.stat().st_size)
check("crash ครั้งแรก ๆ ถูกหมุนออกไปตามกติกา", before > 0)


# ---------- 9) ตาข่ายจับ error ที่มองไม่เห็น ----------
os.environ["SOONAI_DEBUG"] = "0"
check("ปิดโหมด = ไม่ติดตั้ง hooks", _DBG.install_hooks() is False)
os.environ["SOONAI_DEBUG"] = "1"
_DBG._hooks_installed["done"] = False
check("เปิดโหมด = ติดตั้ง hooks", _DBG.install_hooks() is True)
check("เรียกซ้ำ = no-op (คืน True)", _DBG.install_hooks() is True)
check("threading.excepthook ถูกเปลี่ยน", threading.excepthook is not threading.__excepthook__
      if hasattr(threading, "__excepthook__") else True)


class _Args:
    exc_value = ValueError("thread boom")
    thread = threading.current_thread()


reset_log()
threading.excepthook(_Args())
check("exception ใน thread ถูกบันทึก", "thread boom" in read_log(), read_log()[:200])


class _Unraisable:
    exc_value = RuntimeError("finalizer boom")
    object = "obj"


sys.unraisablehook(_Unraisable())
check("exception ตอน finalize ถูกบันทึก", "finalizer boom" in read_log())


def _bad_hook(*_a, **_k):
    raise RuntimeError("hook เดิมพัง")


threading.excepthook = _bad_hook
sys.unraisablehook = _bad_hook
_DBG._hooks_installed["done"] = False
_DBG.install_hooks()
try:
    threading.excepthook(_Args())          # hook เดิมโยน error → hook ใหม่ต้องไม่พังตาม
    ok_chain = True
except Exception:
    ok_chain = False
check("hook เดิมพัง = hook ใหม่ยังไม่พัง", ok_chain)


# ---------- 10) ต่อสายกับ soonai จริง ----------
os.environ["SOONAI_DEBUG"] = "1"
import runtime as R  # noqa: E402 - seam/state ที่โมดูลย่อยใช้ร่วมกับ soonai
import soonai as S  # noqa: E402 - import หลังตั้ง env (โหมดอ่าน env ทุกครั้งอยู่แล้ว)

check("soonai ผูก debug แล้ว", S._DBG is _DBG)
reset_log()
bad = TMP / "broken.json"
bad.write_text("{ ไฟล์พังจริง ๆ ", encoding="utf-8")
got = S.load_json(bad, {"fallback": True})
check("load_json ยังคืนค่าเริ่มต้นเหมือนเดิม", got == {"fallback": True})
check("load_json บันทึกร่องรอยไฟล์พังลง log", "load_json" in read_log() and "broken.json" in read_log(),
      read_log()[:200])
reset_log()
missing = TMP / "no-file-yet.json"
check("ไฟล์หาย = ไม่ต้องมีร่องรอย (ยังไม่ตั้งค่าครั้งแรก)",
      S.load_json(missing, {}) == {} and read_log() == "")

reset_log()
os.environ["SOONAI_DEBUG"] = "0"
check("ปิด debug = load_json กลับมาเงียบสนิท",
      S.load_json(bad, {"fallback": True}) == {"fallback": True} and read_log() == "")

# ---------- 11) ต่อสายเส้นทางเครือข่าย/กู้ session (ของจริงจาก soonai) ----------
os.environ["SOONAI_DEBUG"] = "1"
import mcp_client as MC  # noqa: E402
import permissions as PM  # noqa: E402
import skills as SK  # noqa: E402

# 11.1 โมเดล vision: ยิงเครือข่ายพัง = มีร่องรอย (ของเดิมเงียบสนิท)
_orig_data, _orig_get = S.DATA_DIR, S.requests.get
S.DATA_DIR = TMP / "data"


def _net_down(*_a, **_k):
    raise RuntimeError("จำลองเครือข่ายล่ม")


S.requests.get = _net_down
reset_log()
try:
    vis = S.discover_vision_models("openrouter")
finally:
    S.requests.get = _orig_get
    S.DATA_DIR = _orig_data
check("vision: ล่มแล้วยังคืน [] ไม่พัง", vis == [])
check("vision: บันทึกร่องรอยเครือข่ายล่ม", "discover_vision_models" in read_log()
      and "จำลองเครือข่ายล่ม" in read_log(), read_log()[:200])

# 11.2 cache รายการโมเดล: เขียนไม่ได้ = มีร่องรอย
_orig_cache = S.MODELS_CACHE_FILE
S.MODELS_CACHE_FILE = TMP / "cache-dir"
S.MODELS_CACHE_FILE.mkdir(exist_ok=True)          # ตั้งใจให้เป็นโฟลเดอร์ = เขียนทับไม่ได้
reset_log()
try:
    S._write_models_cache({"openrouter": {"models": ["m"]}})
finally:
    S.MODELS_CACHE_FILE = _orig_cache
check("models cache: เขียนไม่ได้ = บันทึกเหตุผล", "_write_models_cache" in read_log(), read_log()[:200])

# 11.3 session: ไฟล์เสียหายตอนกู้ = มีร่องรอยทั้ง list_sessions และ migrate
_orig_sess, _orig_migrated = S.SESSIONS_DIR, S._MIGRATED_SESSIONS["done"]
sess_dir = TMP / "sessions"
sess_dir.mkdir(exist_ok=True)
(sess_dir / "broken.json").write_text("[[[ พัง", encoding="utf-8")
legacy = TMP / "legacy"
legacy.mkdir()
(legacy / "20200101-000000.json").write_text("ไม่ใช่ json", encoding="utf-8")
S.SESSIONS_DIR = sess_dir
reset_log()
try:
    S.list_sessions()
    S._MIGRATED_SESSIONS["done"] = False
    moved = S._migrate_legacy_sessions(dest=sess_dir, sources=[legacy])
finally:
    S.SESSIONS_DIR = _orig_sess
    S._MIGRATED_SESSIONS["done"] = _orig_migrated
check("session: list_sessions ข้ามไฟล์พังพร้อมร่องรอย",
      "list_sessions" in read_log() and "broken.json" in read_log(), read_log()[:200])
check("session: migrate บอกว่าไฟล์เก่าอ่านไม่ได้",
      "_migrate_legacy_sessions" in read_log() and "20200101-000000.json" in read_log())
check("session: migrate ยังทำงานต่อได้ (คืน int)", isinstance(moved, int))

# 11.4 session: เขียน session ไม่ได้ = ต้องรู้ว่าประวัติจะหาย
_orig_write = S._atomic_write_text


def _write_fails(*_a, **_k):
    raise PermissionError("จำลองเขียนไม่ได้")


S._atomic_write_text = _write_fails
S.SESSIONS_DIR = TMP / "sessions2"
reset_log()
try:
    sid = S.save_session("20260101-000000", "openrouter", "m",
                         [{"role": "user", "content": "สวัสดี"}])
finally:
    S._atomic_write_text = _orig_write
    S.SESSIONS_DIR = _orig_sess
check("session: save_session ยังคืน id (ไม่พัง)", sid == "20260101-000000", sid)
check("session: บันทึกร่องรอยว่าเขียน session ไม่ได้",
      "save_session" in read_log() and "จำลองเขียนไม่ได้" in read_log(), read_log()[:200])

# 11.5 MCP: mcp.json พัง = ล้มเหลวเงียบ ๆ ไม่ได้อีกต่อไป
bad_mcp = TMP / "mcp-broken.json"
bad_mcp.write_text("{ พังอยู่", encoding="utf-8")
reset_log()
check("mcp: ไฟล์พังคืน {} ตามเดิม", MC.load_mcp_config(bad_mcp) == {})
check("mcp: บอกว่าอ่านไฟล์พัง (จะไม่มี server เลย)", "load_mcp_config" in read_log(), read_log()[:200])
reset_log()
check("mcp: ไฟล์หาย = ไม่ต้องมีร่องรอย", MC.load_mcp_config(TMP / "none.json") == {}
      and read_log() == "")

# 11.6 สกิล: จำความเคยชินไม่ได้ = มีร่องรอย
_orig_skill = R.SKILL_STATE_FILE
R.SKILL_STATE_FILE = TMP / "skill-state-dir"
R.SKILL_STATE_FILE.mkdir(exist_ok=True)
reset_log()
try:
    SK._skill_state_save()
finally:
    R.SKILL_STATE_FILE = _orig_skill
check("skills: จำ state ไม่ได้ = บันทึกร่องรอย", "_skill_state_save" in read_log(), read_log()[:200])

# 11.7 ความปลอดภัย: เขียน audit ไม่ได้ = ต้องรู้ (เป็นเรื่องสำคัญ)
audit_dir = TMP / "auditdir"
audit_dir.mkdir()
reset_log()
check("permissions: audit_append คืน False ตามเดิม",
      PM.audit_append(audit_dir, "run_cmd", target="dir", tool="run_cmd") is False)
check("permissions: บอกว่าไม่มีร่องรอยการอนุญาต", "audit_append" in read_log(), read_log()[:200])
reset_log()
check("permissions: เขียน audit ปกติ = ไม่มีร่องรอยแต่อย่างใด",
      PM.audit_append(TMP / "audit.log", "run_cmd", target="ok", tool="run_cmd") is True
      and read_log() == "")

# ---------- 12) สรุปว่า exception ถูกกลืนซ้ำตรงไหนบ่อยสุด (อ่านจาก log) ----------
os.environ["SOONAI_DEBUG"] = "1"
os.environ.pop("SOONAI_DEBUG_MAX_BYTES", None)
os.environ.pop("SOONAI_DEBUG_BACKUPS", None)
os.environ.pop("SOONAI_DEBUG_SUMMARY", None)
reset_log()
check("log ว่าง = ไม่มีอะไรให้สรุป", _DBG.summary() == [] and _DBG.summary_lines() == [])
_sl0 = _DBG.startup_lines()
check("เปิดโหมดแต่ยังไม่มีอะไร = ยังบอกที่อยู่ log ให้", len(_sl0) == 1 and "ยังไม่พบ" in _sl0[0]
      and _DBG.display_path() in _sl0[0], _sl0)

reset_log()
for i in range(5):
    _DBG.log_swallowed(ValueError(f"พังครั้งที่ {i}"), "soonai.py:load_json", "ใช้ค่าเริ่มต้น")
for _i in range(2):
    _DBG.log_swallowed(PermissionError("เขียนไม่ได้"), "mcp_client.py:load_mcp_config", "ไม่มี server")
_DBG.note("เหตุการณ์ทั่วไป", "chat.py:cmd_chat")

rows = _DBG.summary(0)
check("จัดกลุ่มตาม where ครบทุกจุด", [r["where"] for r in rows] ==
      ["soonai.py:load_json", "mcp_client.py:load_mcp_config", "chat.py:cmd_chat"],
      [r["where"] for r in rows])
check("เรียงจากบ่อยไปน้อย + นับครั้งถูก", [r["count"] for r in rows] == [5, 2, 1],
      [r["count"] for r in rows])
check("รู้ชนิด exception ของครั้งล่าสุด", rows[0]["exc"] == "ValueError" and "พังครั้งที่ 4" in rows[0]["msg"],
      rows[0])
check("รู้ว่ากลืนแล้วทำอะไรต่อ", rows[0]["note"] == "ใช้ค่าเริ่มต้น", rows[0]["note"])
check("รู้เวลาล่าสุดที่เกิด", rows[0]["last"].startswith("20") and len(rows[0]["last"]) == 19,
      rows[0]["last"])
check("บรรทัด note ล้วน ๆ ก็นับเป็นจุดด้วย", rows[2]["exc"] == "" and rows[2]["note"] == "เหตุการณ์ทั่วไป")
check("limit ตัดจำนวนแกนที่คืน", len(_DBG.summary(2)) == 2)
check("ยอดรวมทุกแกน = จำนวนรายการที่อ่านได้",
      sum(r["count"] for r in rows) == len(_DBG.entries()) == 8)

lines = _DBG.summary_lines()
check("summary_lines มีจำนวน× + where + ชนิด error",
      lines[0].startswith("5×  soonai.py:load_json") and "ValueError" in lines[0], lines[0])
check("summary_lines บอกว่ามีมากกว่า limit", any("และอีก" in ln for ln in _DBG.summary_lines(2)))
_sl_long = _DBG.summary_lines()
check("บรรทัดสรุปถูกตัดความยาว ไม่ล้นจอ", all(len(ln) <= 110 for ln in _sl_long), len(_sl_long[0]))
check("พาธในบรรทัดสรุปย่อโฟลเดอร์บ้านเป็น ~",
      "~" in _DBG.display_path() and str(Path.home()) not in _DBG.display_path(),
      _DBG.display_path())
check("พาธที่ไม่อยู่ใต้โฟลเดอร์บ้าน = แสดงเต็ม",
      _DBG.display_path("C:/other/place/x.log") == "C:/other/place/x.log")
_sl = _DBG.startup_lines()
check("startup_lines สรุปยอดรวม + จำนวนจุด", "8 ครั้ง" in _sl[0] and "3 จุด" in _sl[0], _sl[0])
check("startup_lines ใส่ top ไว้ด้านใน", any("5× soonai.py:load_json" in ln for ln in _sl), _sl)
check("startup_lines ไม่ตัดเมื่อจุดน้อยกว่า limit", not any("และอีก" in ln for ln in _sl))
os.environ["SOONAI_DEBUG_SUMMARY"] = "2"
check("ตั้ง SOONAI_DEBUG_SUMMARY=2 = เหลือ 2 จุด + บอกว่ามีต่อ",
      len(_DBG.startup_lines()) == 4 and any("และอีก 1 จุด" in ln for ln in _DBG.startup_lines()))
os.environ["SOONAI_DEBUG_SUMMARY"] = "0"
check("ตั้ง 0 = ไม่โชว์อะไรเลย", _DBG.startup_lines() == [])
os.environ["SOONAI_DEBUG_SUMMARY"] = "999"          # ค่าประหลาด = ใช้ค่าเริ่มต้น
check("ค่าประหลาด = กลับไปใช้ค่าเริ่มต้น (5)", _DBG.summary_limit() == 5)
os.environ.pop("SOONAI_DEBUG_SUMMARY", None)
os.environ["SOONAI_DEBUG"] = "0"
check("ปิดโหมด debug = ไม่โชว์สรุปเลย", _DBG.startup_lines() == [])
os.environ["SOONAI_DEBUG"] = "1"

# 12.1 นับรายการที่อยู่ในไฟล์ที่หมุนไปแล้วด้วย ไม่ใช่แค่ไฟล์ปัจจุบัน
os.environ["SOONAI_DEBUG_MAX_BYTES"] = "4096"
os.environ["SOONAI_DEBUG_BACKUPS"] = "2"
reset_log()
for _i in range(80):
    _DBG.log_swallowed(RuntimeError("z" * 300), "net:repeated", "ยิงซ้ำ")
check("ช่วงทดสอบนี้เกิดการหมุนไฟล์จริง", _DBG._part(LOG, 1).exists())
check("ยอดรวมใน summary = ทุกรายการที่อ่านได้ (รวมไฟล์ที่หมุน)",
      sum(r["count"] for r in _DBG.summary(0)) == len(_DBG.entries()) > 10,
      len(_DBG.entries()))
check("แกนที่ถูกหมุนออกไปแล้วก็ยังนับครั้งที่เหลืออยู่ถูก",
      _DBG.summary(0)[0]["where"] == "net:repeated")
os.environ.pop("SOONAI_DEBUG_MAX_BYTES", None)
os.environ.pop("SOONAI_DEBUG_BACKUPS", None)

# 12.2 log เสียหาย/ถูกตัดกลาง = ต้องไม่พัง และไม่โกหก
reset_log()
LOG.write_text("ขยะที่ไม่มีหัวรายการ\n" + "-" * 72 + "\n[ยังไม่มีปี]\n", encoding="utf-8")
check("log เสียหาย = สรุปได้ [] ไม่พัง", _DBG.summary() == [] and _DBG.summary_lines() == [])
LOG.write_text("[2026-09-20 03:00:00] pid=1 tid=2 thread=MainThread\n"
               "  where : x.py:f\n"
               "Traceback (most recent call last):\n"
               "json.decoder.JSONDecodeError: bad\n", encoding="utf-8")
check("รายการท้ายไฟล์ที่ยังไม่ถูกคั่น = ยังนับได้",
      len(_DBG.summary(0)) == 1 and _DBG.summary(0)[0]["exc"] == "json.decoder.JSONDecodeError",
      _DBG.summary(0))

# 12.3 crash (หลุดถึง main) ถูกนับเป็นอีกจุดหนึ่ง
reset_log()
_DBG.log_crash("บึ้มแล้ว\n")
check("การ l่มที่หลุดถึง main ถูกนับด้วย",
      [r["where"] for r in _DBG.summary(0)] == ["main (unhandled)"], _DBG.summary(0))

# 12.4 ของจริงจาก soonai เข้าสรุปเอง
reset_log()
S.load_json(bad, {})
S.load_json(bad, {})
check("เส้นทางจริงถูกนับรวมในสรุป (soonai.py:load_json ×2)",
      [(r["where"], r["count"]) for r in _DBG.summary(0)] == [("soonai.py:load_json", 2)],
      _DBG.summary(0))
import inspect  # noqa: E402
import chat  # noqa: E402
check("ห้องแชทต่อสายสรุปไว้จริง (แสดงเฉพาะตอนคุยกับคน)",
      "startup_lines()" in inspect.getsource(chat.cmd_chat))

# เก็บกวาด: คืนค่า hook ที่ถูกแก้ (เทสต์อื่นในซับโพรเซสเดียวกันอาจอ่านค่า)
sys.unraisablehook = getattr(sys, "__unraisablehook__", sys.unraisablehook)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL DEBUG MODE TESTS PASSED")
