# -*- coding: utf-8 -*-
"""เลเยอร์ UI/เรนเดอร์ของ CLI — ตาราง · แบนเนอร์ · กรอบอินพุตจักรวาล · บรรทัดสถานะ

แยกออกจาก soonai.py (Step 3 ของการแยกโมดูล) เพื่อให้ทุกส่วนของ CLI (chat · skills ·
commands) เรียกตัวจัดรูปแบบชุดเดียวกันได้ โดยไม่ต้องพึ่ง namespace ของ soonai

กฎการอ่าน seam (เหมือนโมดูลอื่น):
- ชื่อที่เป็น state/ฟังก์ชันของ soonai → ``R.<ชื่อ>`` (attribute access) เพื่อให้
  ค่าที่ถูก patch ทีหลัง (จากเทสต์หรือผู้ใช้) เห็นตรงกันเสมอ
- ชื่อของโมดูลพี่น้อง (shell/usage/providers) → import โมดูลนั้นตรง ๆ
"""
import colorsys
import json
import os
import re
import time

import requests
from rich import box
from rich.align import Align
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

import runtime as R
import shell
import usage
from providers import PROVIDERS

try:
    import ui_theme as _UI
    _UI_OK = True
except Exception:  # pragma: no cover - ธีมเป็นของเสริม ไม่ควรทำให้ CLI ล่ม
    _UI = None
    _UI_OK = False


LOGO = [
    " ███████╗ ██████╗  ██████╗ ███╗   ██╗ █████╗ ██╗",
    " ██╔════╝██╔═══██╗██╔═══██╗████╗  ██║██╔══██╗██║",
    " ███████╗██║   ██║██║   ██║██╔██╗ ██║███████║██║",
    " ╚════██║██║   ██║██║   ██║██║╚██╗██║██╔══██║██║",
    " ███████║╚██████╔╝╚██████╔╝██║ ╚████║██║  ██║██║",
    " ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝",
]


def _hex(rgb):
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def neon(text, start=(0, 229, 255), end=(255, 47, 214)):
    """ข้อความไล่สีนีออน (ฟ้า -> ม่วง) ทีละตัวอักษร"""
    t = Text()
    n = len(text)
    for i, ch in enumerate(text):
        f = i / (n - 1) if n > 1 else 0
        t.append(ch, style=_hex(tuple(int(a + (b - a) * f) for a, b in zip(start, end))))
    return t


def _rainbow_line(line, offset, spread=0.85):
    t = Text()
    n = len(line)
    for i, ch in enumerate(line):
        h = (offset + (i / (n - 1) if n > 1 else 0) * spread) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
        t.append(ch, style=f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
    return t


def _rainbow_logo(offset):
    return Group(*[_rainbow_line(line, offset) for line in LOGO])


def _thai_attach(ch):
    o = ord(ch)
    return (0x0E30 <= o <= 0x0E3A) or (0x0E47 <= o <= 0x0E5E)


def _clusters(s):
    """ตัดข้อความเป็นกลุ่มตัวอักษร (สระ/วรรณยุกต์ติดกับพยัญชนะ) สำหรับเอฟเฟกต์พิมพ์ทีละตัว"""
    import unicodedata
    out, cur = [], ""
    for ch in s:
        if cur and (unicodedata.combining(ch) or _thai_attach(ch)):
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ch
    if cur:
        out.append(cur)
    return out


def welcome_popup(keys, cfg, provider, model):
    """ป๊อปอัพต้อนรับสไตล์ JARVIS: กรอบขยาย + พิมพ์ทีละตัว + ขอบเรืองแสง + สถานะระบบ (เฉพาะจอจริง)"""
    if not R.console.is_terminal:
        return
    import time as _t

    try:
        ok = requests.get("http://localhost:11434/api/tags", timeout=2).status_code == 200
    except Exception:
        ok = False
    statuses = [
        ("Ollama", "[green]ONLINE[/]" if ok else "[red]OFFLINE[/]"),
        ("API keys", f"[green]{len(keys)} loaded[/]"),
        ("Model", f"[cyan]{provider} / {model or '(auto)'}[/]"),
    ]
    greet = _clusters("ยินดีต้อนรับสู่")
    brand = _clusters("S O O N A I")
    reactor = ["|", "/", "-", "\\"]
    state = {"w": 28, "g": 0, "b": 0, "s": 0, "frame": 0, "hue": 0.52}

    def render():
        t = Text(justify="center")
        t.append(f"[ {reactor[state['frame'] % 4]} ]\n", style="bold bright_cyan")
        if state["g"]:
            t.append("".join(greet[:state["g"]]) + "\n", style="bold white")
        if state["b"]:
            t.append("".join(brand[:state["b"]]) + "\n", style="bold magenta")
        if state["s"]:
            t.append("─" * 28 + "\n", style="dim")
            for label, val in statuses[:state["s"]]:
                t.append("✓ ", style="green")
                t.append(f"{label}  ", style="dim")
                t.append(Text.from_markup(val))
                t.append("\n")
        r, g, b = colorsys.hsv_to_rgb(state["hue"], 1.0, 1.0)
        border = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
        return Align.center(Panel(t, width=state["w"], title="[bold]SOONAI OS[/]",
                                  border_style=border, box=box.ROUNDED))

    if os.name == "nt":
        os.system("cls")
    R.console.clear()
    try:
        with Live(render(), console=R.console, transient=True,
                  refresh_per_second=20) as live:
            def upd(**kw):
                state.update(kw)
                state["frame"] += 1
                state["hue"] = (state["hue"] + 0.035) % 1.0
                live.update(render())

            for w in range(34, 72, 6):  # กรอบขยาย
                upd(w=w)
                _t.sleep(0.05)
            upd(w=72)
            for i in range(1, len(greet) + 1):  # พิมพ์ทีละตัว
                upd(g=i)
                _t.sleep(0.045)
            for i in range(1, len(brand) + 1):
                upd(b=i)
                _t.sleep(0.05)
            for i in range(1, len(statuses) + 1):  # สถานะทีละบรรทัด
                upd(s=i)
                _t.sleep(0.18)
            for _ in range(6):  # ค้างโชว์ขอบเรืองแสง
                upd()
                _t.sleep(0.1)
    except Exception:
        pass
    _t.sleep(0.15)


def boot_sequence(keys, cfg, provider, model):
    """รุ่นเก่า: คงไว้เผื่อเรียกใช้ เปลี่ยนทางไปป๊อปอัพ"""
    return welcome_popup(keys, cfg, provider, model)


def show_banner(provider="", model=""):
    """แบนเนอร์เปิดห้องแชท: โลโก้สีเดียว + คำโปรย (เรียบหรู ไม่มีอนิเมชัน)
    อยากได้อนิเมชันจักรวาลแบบเดิม → `soonai demo`"""
    if os.environ.get("SOONAI_NO_BANNER"):
        return
    if not R.console.is_terminal:
        return
    if os.environ.get("NO_COLOR"):
        for line in LOGO:
            R.console.print(line)
    else:
        col = _UI.logo_style() if _UI_OK else "cyan"
        for line in LOGO:
            R.console.print(f"[{col}]{line}[/]")
    R.console.print(f"  [dim]U N I V E R S A L   A I   C H A T B O T[/dim]"
                  f"  [dim]·[/dim]  [dim]v{R.VERSION}[/dim]")
    if provider:
        R.console.print(f"  [dim]{provider} / {model}[/dim]")
    R.console.print()


def set_term_title(title):
    """ตั้งชื่อแท็บ terminal เป็นชื่อที่กำหนด (เช่น soonaiTH) เฉพาะตอนจอจริง"""
    try:
        if R.console.is_terminal:
            R.console.file.write(f"\x1b]0;{title}\x07")
            R.console.file.flush()
    except Exception:
        pass
    try:
        if os.name == "nt":
            os.system(f"title {title}")
    except Exception:
        pass


def neo_table(title, **kw):
    """ตารางโทนเรียบหรู: ขอบบางสีจาง · หัวตารางหม่น · ชื่อเรื่อง accent

    ระวัง: เมื่อ NO_COLOR/TERM=dumb สไตล์จะว่าง → ห้ามปล่อยแท็กว่าง `[]…[/]`
    (Rich โยน MarkupError) จึงใช้ _UI.markup() และ `or None` แทน f-string ตรง ๆ
    """
    faint = (_UI.style("faint") if _UI_OK else "grey50") or None
    muted = (_UI.style("muted") if _UI_OK else "cyan") or None
    opt = dict(show_lines=False, box=box.ROUNDED, border_style=faint,
               header_style=muted, padding=(0, 2))
    opt.update(kw)
    title_txt = _UI.markup(title, "muted") if _UI_OK else f"[{muted}]{title}[/]"
    return Table(title=title_txt, **opt)


def short_model(model, limit=40):
    m = model or ""
    return m if len(m) <= limit else m[: limit - 3] + "..."


def _record_tools(tools):
    """เก็บ log tool ไว้ให้ผู้ใช้ย้อนดู (/tools) — เก็บไม่เกิน SESSION_TOOLS_MAX"""
    try:
        for t in tools or []:
            if isinstance(t, (list, tuple)):
                row = (str(t[0]), str(t[1]) if len(t) > 1 else "",
                       str(t[2]) if len(t) > 2 else "")
            else:
                row = (str(t), "", "")
            R.SESSION_TOOLS.append(row)
            _audit_tool_event(row)
        if len(R.SESSION_TOOLS) > R.SESSION_TOOLS_MAX:
            del R.SESSION_TOOLS[:-R.SESSION_TOOLS_MAX]
    except Exception:
        pass


_AUDIT_SECRET_RE = re.compile(
    r"(?i)(token|password|passwd|pwd|api[_-]?key|secret|bearer)\s*[:=]\s*\S+"
)


def _audit_tool_event(tool):
    """Append a small redacted tool event without storing payloads or file contents."""
    try:
        row = tool if isinstance(tool, (list, tuple)) else (str(tool), "", "")
        payload = {
            "ts": time.time(),
            "tool": str(row[0])[:120],
            "status": str(row[1])[:30] if len(row) > 1 else "",
            "result": _AUDIT_SECRET_RE.sub(r"\1=***", str(row[2])[:300])
            if len(row) > 2 else "",
        }
        data_dir = getattr(R, "DATA_DIR", None)
        if not data_dir:
            return
        path = os.path.join(str(data_dir), "audit.log")
        os.makedirs(str(data_dir), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        if os.path.getsize(path) > 1_000_000:
            with open(path, "rb") as handle:
                tail = handle.read()[-500_000:]
            with open(path, "wb") as handle:
                handle.write(tail)
    except Exception:
        pass


def _diff_stat_line(name, fargs, max_lines=400):
    """สรุป '±n บรรทัด' ของ diff ก่อนเขียน/แก้ (ว่าง = คำนวณไม่ได้)"""
    try:
        d = R.preview_diff(name, fargs if isinstance(fargs, dict) else {})
        if not d:
            return ""
        plus = minus = 0
        for ln in d.splitlines()[:max_lines]:
            if ln.startswith("+") and not ln.startswith("+++"):
                plus += 1
            elif ln.startswith("-") and not ln.startswith("---"):
                minus += 1
        return f"+{plus}/-{minus} บรรทัด" if (plus or minus) else ""
    except Exception:
        return ""


def _status_extras(ttl=5.0):
    """ข้อมูลแพง ๆ ของบรรทัดสถานะ (git/คำสั่งเทสต์) — cache 5 วินาที
    สำคัญเพราะบรรทัดนี้ถูกวาดซ้ำทุกเฟรมของกรอบอนิเมชัน"""
    now = time.time()
    if R._STATUS_CACHE["extra"] is not None and now - R._STATUS_CACHE["t"] < ttl:
        return R._STATUS_CACHE["extra"]
    parts = []
    try:
        if R.git_in_repo():
            dirty = len(R.git_changes())
            parts.append(f"git:{R.git_branch() or '?'}" + (f"*{dirty}" if dirty else ""))
    except Exception:
        pass
    try:
        cmd = shell.detect_test_command()
        if cmd:
            parts.append("test:มี")
    except Exception:
        pass
    R._STATUS_CACHE["t"] = now
    R._STATUS_CACHE["extra"] = " · ".join(parts)
    return R._STATUS_CACHE["extra"]


def _age_str(sec):
    """อายุสั้น ๆ: 45s / 12m"""
    sec = max(0, int(sec))
    return f"{sec}s" if sec < 60 else f"{sec // 60}m"


def slow_statusline(provider=""):
    """⚠ ค่ายที่ timeout/ล่มล่าสุด (ภายใน SLOW_TTL) — เห็นทันทีในแถบสถานะ
    - ค่ายที่ใช้อยู่เพิ่ง timeout → ⚠timeout:5m (อายุครั้งล่าสุด)
    - ค่ายอื่นที่เพิ่ง timeout → ⚠slow:ชื่อ (ใหม่สุดก่อน โชว์สูงสุด 2 +N)
    cache 5 วินาที (แถบนี้วาดซ้ำทุกเฟรม) · คืน '' เมื่อไม่มีอะไรน่าเตือน"""
    now = time.time()
    c = R._STATUS_CACHE
    if c.get("slow") is None or now - (c.get("slow_t") or 0) >= 5.0:
        try:
            ttl = float(getattr(R, "SLOW_TTL", 900))
        except Exception:
            ttl = 900.0
        try:
            slow = {str(k): float(v)
                    for k, v in dict(R._health_load().get("slow") or {}).items()
                    if isinstance(v, (int, float)) and 0 <= now - float(v) <= ttl}
        except Exception:
            slow = {}
        c["slow"], c["slow_t"] = slow, now
    slow = c.get("slow") or {}
    if not slow:
        return ""
    out = []
    if provider in slow:
        out.append(f"⚠timeout:{_age_str(now - slow[provider])}")
    others = sorted(((p, now - ts) for p, ts in slow.items() if p != provider),
                    key=lambda x: x[1])
    if others:
        names = [p for p, _ in others[:2]]
        if len(others) > 2:
            names.append(f"+{len(others) - 2}")
        out.append("⚠slow:" + ",".join(names))
    return " · ".join(out)


def status_line(provider="", model="", agent=False, auto_yes=False, effort=""):
    """บรรทัดสถานะสำหรับแถบล่างของ TUI: โมเดล · โหมด · shell · git · token"""
    parts = []
    if model:
        parts.append(short_model(model, 24))
    if agent:
        parts.append("agent")
    if auto_yes:
        parts.append("AUTO")
    if effort:
        parts.append(f"eff:{effort}")
    try:
        sl = slow_statusline(provider)
        if sl:
            parts.append(sl)
    except Exception:
        pass
    try:
        sh = shell._shell_mode()
        if sh != "off":
            parts.append(f"shell:{sh}")
    except Exception:
        pass
    ex = _status_extras()
    if ex:
        parts.append(ex)
    cps = len(R.checkpoint_records())
    if cps:
        parts.append(f"undo:{cps}")
    u = usage.usage_line()
    if u:
        parts.append(u)
    return " · ".join(parts)


def current_summary(provider, model):
    name = PROVIDERS.get(provider, {}).get("name", provider)
    return f"{name} / {model}"


def _term_width(default=80):
    import shutil
    try:
        return max(40, shutil.get_terminal_size((default, 20)).columns)
    except Exception:
        return default


def _dwidth(text):
    try:
        from wcwidth import wcswidth
        return max(0, wcswidth(text))
    except Exception:
        return len(text)


def box_title(provider, model, agent=False, auto_yes=False, effort=""):
    flags = []
    if agent:
        flags.append("agent")
    if auto_yes:
        flags.append("AUTO")
    if effort:
        flags.append("effort:" + effort)
    extra = (" · " + " ".join(flags)) if flags else ""
    return f"{provider} / {short_model(model, 30)}{extra}"


def input_box_top(provider, model, agent=False, auto_yes=False, effort=""):
    title = f"┌─ {box_title(provider, model, agent, auto_yes, effort)} "
    return title + "─" * max(0, _term_width() - _dwidth(title) - 1)


def locked_box_text(title, body, width=None):
    """กรอบนิ่งสำหรับข้อความที่ส่งแล้ว (ล็อคไว้ใน transcript แบบ Codex)"""
    w = max(20, width or _term_width())
    top = f"┌─ {title} "
    top += "─" * max(0, w - _dwidth(top) - 1)
    mid = [f"│ > {ln}" for ln in (str(body or "").splitlines() or [""])]
    bot = "└" + "─" * max(0, w - 2)
    return "\n".join([top] + mid + [bot])


def input_box_bottom():
    return "└" + "─" * max(0, _term_width() - 2)


SLASH_COMMANDS = [
    ("/model", "เปลี่ยนโมเดล (ในค่ายเดิม)"),
    ("/provider", "เปลี่ยนค่าย + เลือกโมเดลใหม่"),
    ("/connect", "เชื่อมต่อค่าย: เลือก/เพิ่มค่าย + key + ทดสอบจริง"),
    ("/pull", "โหลดโมเดลใหม่มาใช้บนเครื่อง"),
    ("/agent", "เปิด/ปิดโหมดสั่งงานเครื่อง"),
    ("/init", "ร่าง AGENTS.md ประจำโปรเจกต์ด้วย AI"),
    ("/review", "ให้ AI รีวิว diff + สรุปความเสี่ยง"),
    ("/hire", "จ้างลูกน้อง AI (สูงสุด 5 คน)"),
    ("/team", "ดูทีมงานทั้งหมด"),
    ("/fire", "ไล่ลูกน้องออก (เลือกจากเมนูได้)"),
    ("/tell", "สั่งงานลูกน้อง (/tell @coder ...)"),
    ("/tellall", "สั่งงานทั้งทีมพร้อมกัน (/tellall @a,@b ...)"),
    ("/auto", "เปิด/ปิดอนุมัติอัตโนมัติ (ไม่ต้องกด y)"),
    ("/mcp", "ดู/จัดการ MCP servers (tools เสริม)"),
    ("/skills", "ดู/ติดตั้ง skills เสริม — มีชุดในตัว (/skills all) · "
                 "ความจำ preference: /skills learning · /skills reset [ชื่อ]"),
    ("/skill", "พิมพ์คำค้นหาสกิล หรือให้ AI หาสกิลที่เข้ากับงานนี้"),
    ("/effort", "ตั้ง reasoning effort (low/medium/high/off)"),
    ("/theme", "สลับธีม UI: luxe (เรียบหรู) / classic (นีออนเดิม)"),
    ("/smart", "เปิด/ปิดโหมดฉลาดอัตโนมัติ"),
    ("/boost", "เปิด/ปิดเกลาพร้อมอัตโนมัติ (/boost th|en|off)"),
    ("/shell", "โหมด shell ของ agent: off/safe/on"),
    ("/commit", "ร่างข้อความ commit → ยืนยัน → commit (ไม่ push)"),
    ("/pr", "ร่าง title+body ของ PR จาก diff (ไม่ push)"),
    ("/tools", "ดู tool ที่ agent เรียกในเซสชันนี้"),
    ("/test", "รันเทสต์ของโปรเจกต์ (ไม่ผ่าน = ส่งให้ agent แก้)"),
    ("/undo", "ย้อนไฟล์กลับจาก checkpoint ล่าสุด"),
    ("/checkpoints", "ดู checkpoint ของงานนี้"),
    ("/diff", "ดูความต่างของไฟล์กับ checkpoint"),
    ("/usage", "ดู token/ค่าใช้จ่ายโดยประมาณของ session"),
    ("/sessions", "ดูบทสนทนาที่บันทึกไว้"),
    ("/sum", "สรุปบทสนทนา + ย่อประวัติ"),
    ("/verify", "ทวนสอบคำตอบล่าสุด"),
    ("/resume", "คุยต่อ session เดิม (/resume 1)"),
    ("/new", "เริ่มบทสนทนาใหม่"),
    ("/choose", "แตกคำถามเป็นช้อย 6 ข้อ (ข้อ 6 พิมพ์เอง)"),
    ("/agi", "ตั้งเป้าให้ AI วางแผน+ทำ+ตรวจเองจนจบ"),
    ("/providers", "ดูรายชื่อค่ายทั้งหมด"),
    ("/clear", "ล้างประวัติการคุย"),
    ("/help", "ช่วยเหลือ"),
    ("/menu", "เปิดเมนูลัด"),
    ("/exit", "ออกจากห้องแชท"),
]


def slash_suggestions(text):
    """คืน [(cmd, คำอธิบาย)] ที่ตรงกับข้อความที่พิมพ์อยู่ (เช่น '/' -> ทั้งหมด, '/p' -> /provider...)"""
    if not text.startswith("/") or " " in text or "\n" in text:
        return []
    return [(c, d) for c, d in SLASH_COMMANDS if c.startswith(text)]


def rgb_hex(hue):
    """hue 0..1 -> '#rrggbb' (อิ่มตัว+สว่างสุด)"""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(float(hue) % 1.0, 1.0, 1.0)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


# ---------- กรอบจักรวาลอนิเมชัน (ดาวกะพริบ + ดาวตกวิ่งตามขอบ) ----------
# ใช้กับ build_input_bar: คำนวณสี/ตัวอักษรทีละช่องจาก (ขอบ, ตำแหน่ง, เฟรม)
# - deterministic ล้วน (ไม่มี random) เฟรมเดิมได้ภาพเดิม เทสต์ได้
# - ทุก glyph กว้าง 1 ช่อง ความกว้างกรอบไม่เพี้ยน
# - ปิดได้ด้วย SOONAI_NO_ANIM=1 หรือ NO_COLOR=1 (กรอบนิ่งสี default)
COSMOS_STARS = ("·", "*", "+", "•", "×")


COSMOS_FAMILIES = (  # (hue, sat) สีดาวแต่ละตระกูล
    (0.52, 0.65),  # ฟ้า
    (0.60, 0.25),  # ขาวน้ำแข็ง
    (0.86, 0.70),  # ชมพูเนบิวลา
    (0.11, 0.85),  # ทอง
    (0.75, 0.70),  # ม่วง
)


COSMOS_TITLE = "#ffd479"  # ชื่อค่ายสีทองแสงดาว อ่านชัด


COSMOS_COMET = ("#7df9ff", "#ff7ad9")  # หัวดาวตก ฟ้า/ชมพู สลับตามขอบ


COSMOS_GLOW_R = 6  # รัศมีแสงหาง (ช่อง)


def _cosmos_on():
    """เล่นอนิเมชันจักรวาลไหม — ค่าเริ่มต้น 'ปิด' (โทนเรียบหรู)
    เปิดได้: config ui.animation=true หรือ SOONAI_ANIM=1 · ปิด: NO_COLOR / SOONAI_NO_ANIM
    ผลถูก cache ต่อโปรเซส (ไม่อ่าน config ทุกเฟรม)"""
    if R._COSMOS_MODE["on"] is None:
        on = False
        if not (os.environ.get("NO_COLOR") or os.environ.get("SOONAI_NO_ANIM")):
            if os.environ.get("SOONAI_ANIM", "").strip().lower() in ("1", "true", "yes", "on"):
                on = True
            else:
                try:
                    on = bool((R.load_config().get("ui") or {}).get("animation", False))
                except Exception:
                    on = False
        R._COSMOS_MODE["on"] = on
    return R._COSMOS_MODE["on"]


def _cosmos_hash(n):
    """สุ่มเทียม deterministic [0,1) จากจำนวนเต็ม"""
    return ((int(n) * 2654435761) & 0xFFFFFFFF) / 4294967296.0


def _unhex(h):
    h = str(h or "").lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (255, 255, 255)


def _cosmos_fade(c1, c2, t):
    """ไล่สี c1 -> c2 ตาม t (0..1) คืน '#rrggbb'"""
    t = max(0.0, min(1.0, float(t)))
    a, b = _unhex(c1), _unhex(c2)
    return _hex(tuple(int(x + (y - x) * t) for x, y in zip(a, b)))


def _cosmos_nebula(pos, frame):
    """สีพื้นอวกาศ ไหลช้า ๆ ตามตำแหน่ง+เวลา (คราม -> ม่วง)"""
    import math
    h = (0.66 + 0.10 * math.sin(pos * 0.12 + frame * 0.045)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.75, 0.45)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _cosmos_cell(edge, pos, edge_len, frame, base):
    """ช่องเดียวของขอบจักรวาล คืน (style, ตัวอักษร 1 ช่อง)"""
    import math
    h = _cosmos_hash(edge * 100003 + pos * 917 + 11)
    L = max(1, int(edge_len))
    cpos = (frame * 2 + edge * 37) % L
    d = min((pos - cpos) % L, (cpos - pos) % L)  # ระยะห่างจากหัวดาวตก
    if d == 0 and L > 1:
        return ("bold #ffffff", "●")
    if h < 0.12:  # ดาวประจำตำแหน่ง กะพริบตามเวลา
        fam_h, fam_s = COSMOS_FAMILIES[int(h * 5.0) % len(COSMOS_FAMILIES)]
        tw = 0.5 + 0.5 * math.sin(frame * 0.55 + (h * 91.7 % 1.0) * 6.2832)
        r, g, b = colorsys.hsv_to_rgb(fam_h, fam_s, 0.45 + 0.55 * tw)
        col = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
        glyph = COSMOS_STARS[int(h * 977.0) % len(COSMOS_STARS)]
    else:
        col, glyph = _cosmos_nebula(pos, frame), base
    if d < COSMOS_GLOW_R and L > 1:  # แสงหางรอบหัวดาวตก
        col = _cosmos_fade(col, COSMOS_COMET[edge % 2], 1.0 - d / COSMOS_GLOW_R)
    return (col, glyph)


def _cosmos_edge(edge, length, frame, base):
    """ขอบยาวทั้งเส้น คืนลิสต์ (style, ตัวอักษร)"""
    n = max(0, int(length))
    return [_cosmos_cell(edge, i, n, frame, base) for i in range(n)]


def _cosmos_word(text, frame):
    """ข้อความ shimmer ไล่เฉดจักรวาลทีละตัวอักษร (เช่นป้าย soonai)"""
    import math
    out = []
    for i, ch in enumerate(text):
        h = (0.58 + 0.16 * math.sin(frame * 0.35 + i * 0.55)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.85, 1.0)
        out.append((f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}", ch))
    return out


def _input_style():
    """สไตล์แถบพิมพ์ — โทนเรียบหรู (accent เดียว, ไฮไลต์นุ่ม ไม่ทึบสีจัด)"""
    if _UI_OK:
        p = _UI.PALETTE
        return {
            "": p["text"],
            "prompt-marker": f"{p['accent']} bold",
            "input-bar": "bg:#1e1e1e",
            "input-hint": f"fg:{p['faint']} bg:#1e1e1e",
            "completion-menu.completion": f"fg:{p['muted']} bg:#1e1e1e",
            "completion-menu.completion.current": f"bold #000000 bg:{p['accent']}",
            "completion-menu.meta.completion": f"fg:{p['faint']} bg:#1e1e1e",
            "completion-menu.meta.completion.current": f"bold #000000 bg:{p['accent']}",
            "completion-menu": "bg:#1e1e1e",
        }
    return {
        "": "#00e5ff bold",
        "prompt-marker": "#00e5ff bold",
        "input-bar": "bg:#333333",
        "input-hint": "fg:#888888 bg:#333333",
        "completion-menu.completion": "#bbbbbb bg:#333333",
        "completion-menu.completion.current": "bold #000000 bg:#00e5ff",
        "completion-menu.meta.completion": "#888888 bg:#333333",
        "completion-menu.meta.completion.current": "bold #000000 bg:#00e5ff",
        "completion-menu": "bg:#333333",
    }


INPUT_STYLE = _input_style()


def _input_rgb_label(frame, width, text="soonai"):
    """RGB rainbow label under the input box, animated independently."""
    pad = max(0, (int(width) - len(text)) // 2)
    out = [("", " " * pad)] if pad else []
    for i, ch in enumerate(text):
        hue = (float(frame) * 0.018 + i / max(1, len(text))) % 1.0
        out.append((rgb_hex(hue), ch))
    return out


def build_input_bar(history=None, status=""):
    """ประกอบแถบพิมพ์กรอบจักรวาลอนิเมชัน (ดาวกะพริบ + ดาวตกวิ่งตามขอบ)
    เมนู / แสดง "เหนือ" แถบพิมพ์ (แทรกในกรอบ) — ไม่ต้องมีจอก็ประกอบได้
    คืน (layout, buffer, key_bindings)"""
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import (
        HSplit, VSplit, Window)
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.menus import CompletionsMenu
    from prompt_toolkit.layout.processors import BeforeInput

    class _Slash(Completer):
        def get_completions(self, document, complete_event):
            word = document.text_before_cursor
            for cmd, desc in slash_suggestions(word):
                yield Completion(cmd, start_position=-len(word),
                                 display_meta=desc)

    buf = Buffer(history=history, completer=_Slash(),
                 complete_while_typing=True, multiline=False)
    kb = KeyBindings()

    @kb.add("enter")
    def _accept(event):
        b = event.current_buffer
        if b.complete_state:
            c = b.complete_state.current_completion
            if c is not None:
                before = b.text
                b.apply_completion(c)
                if b.text == before:
                    event.app.exit(result=b.text)  # เลือกตัวที่ตรงอยู่แล้ว = ยืนยันส่งเลย
                return
            b.complete_state = None  # เมนูเปิดแต่ยังไม่เลือก = ปิดเมนูแล้วส่ง
        event.app.exit(result=b.text)

    @kb.add("escape")
    def _esc(event):
        if event.current_buffer.complete_state:
            event.current_buffer.complete_state = None

    @kb.add("c-c")
    def _abort(event):
        raise KeyboardInterrupt

    @kb.add("c-d")
    def _eof(event):
        if not event.current_buffer.text:
            raise EOFError
        event.current_buffer.delete()

    @kb.add("up")
    def _up(event):
        b = event.current_buffer
        if b.complete_state:
            b.complete_previous()
        else:
            b.history_backward()

    @kb.add("down")
    def _down(event):
        b = event.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.history_forward()

    @kb.add("tab")
    def _tab(event):
        event.current_buffer.start_completion(select_first=False)

    def _cols(default=80):
        try:
            from prompt_toolkit.application.current import get_app
            return max(20, get_app().output.get_size().columns)
        except Exception:
            return default

    state = {"frame": 0, "anim_on": False}

    async def _anim_loop():
        """ขยับเฟรมจักรวาล ~8fps + สั่งวาดใหม่ (หยุดเองเมื่อแอปปิด)"""
        import asyncio
        try:
            while True:
                await asyncio.sleep(0.12)
                state["frame"] += 1
                try:
                    from prompt_toolkit.application.current import get_app
                    get_app().invalidate()
                except Exception:
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def _tick():
        """คืนเฟรมปัจจุบัน + สตาร์ทลูปอนิเมชันครั้งแรก (โหมดนิ่งคืน 0 ไม่สตาร์ท)"""
        if not _cosmos_on():
            return 0
        if not state["anim_on"]:
            state["anim_on"] = True
            try:
                from prompt_toolkit.application.current import get_app
                get_app().create_background_task(_anim_loop())
            except Exception:
                pass
        return state["frame"]

    def _rgb_label_tick():
        """เริ่มลูปสีของป้ายชื่อแม้กรอบจักรวาลจะอยู่โหมดนิ่ง"""
        if not state["anim_on"]:
            state["anim_on"] = True
            try:
                from prompt_toolkit.application.current import get_app
                get_app().create_background_task(_anim_loop())
            except Exception:
                pass
        return state["frame"]

    def _top():
        f = _tick()
        st = status
        if st:  # กันสถานะยาวจนกรอบพุ่ง: ตัดให้พอดีความกว้างจอ
            lim = max(10, _cols() - 8)
            if _dwidth(st) > lim:
                st = st[:max(1, lim - 1)] + "…"
        left_txt = f"┌─ {st} " if st else "┌─ "
        fill = max(0, _cols() - _dwidth(left_txt) - 1)
        if not _cosmos_on():
            return [("", left_txt + "─" * fill + "┐")]
        out = [(_cosmos_nebula(0, f), "┌─ ")]
        if st:
            out.append((COSMOS_TITLE, st + " "))
        out += _cosmos_edge(0, fill, f, "─")
        out.append((_cosmos_nebula(fill + 1, f), "┐"))
        return out

    def _side(edge=2):
        f = _tick()
        if not _cosmos_on():
            return [("", "│")]
        return [_cosmos_cell(edge, f % 512, 512, f, "│")]

    def _bottom():
        f = _tick()
        if not _cosmos_on():
            w = _cols()
            return [("", "└" + "─" * max(0, w - 2) + "┘")]
        w = _cols()
        n = max(0, w - 2)
        return ([(_cosmos_nebula(0, f), "└")] + _cosmos_edge(1, n, f, "─")
                + [(_cosmos_nebula(n + 1, f), "┘")])

    def _label():
        f = _rgb_label_tick()
        w = _cols()
        return _input_rgb_label(f, w)

    bar = "class:input-bar"
    mid = VSplit([
        Window(content=FormattedTextControl(lambda: _side(2)), width=1),
        Window(content=BufferControl(
            buffer=buf,
            input_processors=[BeforeInput("> ", style="class:prompt-marker")],
        ), wrap_lines=False, style=bar, height=1),
        Window(content=FormattedTextControl(lambda: _side(3)), width=1),
    ])
    # เมนู / แสดง "เหนือ" แถบพิมพ์ — แทรกเป็นส่วนหนึ่งของกรอบ
    # (ระหว่างหัวกรอบกับบรรทัดพิมพ์) แทน Float ลอยตามเคอร์เซอร์แบบเดิมที่
    # ห้อยลงล่าง: โหมด inline ของ prompt_toolkit วาดแถวเหนือหัวกรอบไม่ได้
    # (แถวบนสุดของจอ ptk คือหัวกรอบ — เหนือขึ้นไปคือ history ที่พิมพ์ไว้ก่อน วาดทับไม่ได้)
    # มี completion = กรอบขยายลงล่าง บรรทัดพิมพ์ขยับลงตามเมนู
    # ไม่มี completion = ConditionalContainer ซ่อน (สูง 0) → กรอบ 4 แถวเหมือนเดิม
    menu_zone = CompletionsMenu(max_height=6, scroll_offset=1, display_arrows=True)
    body = HSplit([
        Window(content=FormattedTextControl(_top), height=1),
        menu_zone,
        mid,
        Window(content=FormattedTextControl(_bottom), height=1),
        Window(content=FormattedTextControl(_label), height=1),
    ])
    layout = Layout(body, focused_element=mid.children[1])
    return layout, buf, kb


def show_command_menu():
    """เมนูคำสั่งแบบกดหมายเลข คืนคำสั่ง (เช่น /model) หรือ '' ถ้ายกเลิก"""
    items = [
        ("/model", "เปลี่ยนโมเดล (ในค่ายเดิม)"),
        ("/provider", "เปลี่ยนค่าย (เช่น groq / gemini / openrouter)"),
        ("/connect", "เชื่อมต่อค่าย AI (เลือก/เพิ่มค่าย + ใส่ key + ทดสอบยิงจริง)"),
        ("/pull", "โหลดโมเดลใหม่มาใช้บนเครื่อง (เช่น qwen3, llama3.1)"),
        ("/agent", "เปิด/ปิดโหมดสั่งงานเครื่อง (สร้างไฟล์/โฟลเดอร์ได้)"),
        ("/hire", "จ้างลูกน้อง AI (สูงสุด 5 คน)"),
        ("/team", "ดูทีมงานทั้งหมด"),
        ("/fire", "ไล่ลูกน้องออก (เลือกจากเมนูได้)"),
        ("/tell", "สั่งงานลูกน้อง (/tell @coder ...)"),
        ("/tellall", "สั่งงานทั้งทีมพร้อมกัน + สรุปรวม"),
        ("/init", "ร่าง AGENTS.md ประจำโปรเจกต์ด้วย AI"),
        ("/review", "รีวิว diff + สรุปความเสี่ยงก่อน push"),
        ("/auto", "เปิด/ปิดอนุมัติอัตโนมัติ (ไม่ต้องกด y ทุกครั้ง)"),
        ("/mcp", "ดู/จัดการ MCP servers (tools เสริมให้ agent)"),
        ("/skills", "ดู/ติดตั้ง skills เสริมให้ agent"),
        ("/effort", "ตั้ง reasoning effort (low/medium/high/off)"),
        ("/theme", "สลับธีม UI: luxe (เรียบหรู) / classic (นีออนเดิม)"),
        ("/smart", "เปิด/ปิดย่อประวัติ+ตรวจโค้ดอัตโนมัติ"),
        ("/boost", "เลือกโหมดเกลาพร้อม (th/en/off ว่าง=เมนู)"),
        ("/sessions", "ดูบทสนทนาที่บันทึกไว้"),
        ("/sum", "สรุปบทสนทนา + ย่อประวัติ"),
        ("/verify", "ทวนสอบคำตอบล่าสุด"),
        ("/resume [id]", "คุยต่อ session เดิม"),
        ("/new", "เริ่มบทสนทนาใหม่ (ของเดิมบันทึกไว้แล้ว)"),
        ("/choose [เรื่อง]", "แตกเป็นช้อย 6 ข้อ เลือกแล้วส่งงานต่อเลย"),
        ("/agi [เป้าหมาย]", "AGI ตั้งเป้าแล้วทำเองจนจบ (/agi auto on|off)"),
        ("/save [ชื่อ]", "บันทึก session ตอนนี้"),
        ("/providers", "ดูรายชื่อค่ายทั้งหมด"),
        ("/clear", "ล้างประวัติการคุย"),
        ("/help", "ช่วยเหลือ"),
        ("/exit", "ออกจากห้องแชท"),
    ]
    TEAM_CMDS = {"/hire", "/team", "/fire", "/tell", "/tellall"}
    lines = []
    n = 0
    team_header_shown = False
    for cmd, label in items:
        if cmd in TEAM_CMDS and not team_header_shown:
            lines.append("[blue]━━ agent · ทีมงานลูกน้อง ━━[/]")
            team_header_shown = True
        n += 1
        if cmd in TEAM_CMDS:
            lines.append(f"[blue]{n}. {label}  {cmd}[/]")
        else:
            lines.append(f"[cyan]{n}.[/] {label}  [dim]{cmd}[/dim]")
    R.console.print(Panel("\n".join(lines), title="เมนูคำสั่ง", border_style="magenta"))
    try:
        n = int(Prompt.ask("เลือกหมายเลข (0 = ยกเลิก)", default="0"))
    except Exception:
        return ""
    if 1 <= n <= len(items):
        return items[n - 1][0]
    return ""
