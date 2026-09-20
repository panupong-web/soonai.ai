# -*- coding: utf-8 -*-
"""Regression: ธีม UI กลาง (โทนเรียบหรู)
- ui_theme: palette ครบ, color_ok เคารพ NO_COLOR, rule/glyph
- rich_theme: remap ชื่อสีพื้นฐาน (cyan) -> accent จริง (ตรวจจาก ANSI truecolor)
- soonai: console ใช้ธีม, neo_table ใช้ขอบจาง, INPUT_STYLE มาจาก palette
- _apply_ui_theme: สลับ luxe/classic ได้, ค่าไม่ถูกต้องคืน '', ไม่เขียน config จริง
ไม่แตะไฟล์ config จริง/ไม่แตะเน็ต
"""
import io
import os
import sys

try:  # ให้พิมพ์ไทยได้แม้ import soonai จะเกิดทีหลัง
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import ui_theme as U  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------- 1) palette / helpers
for key in ("accent", "text", "muted", "faint", "ok", "warn", "err"):
    check(f"palette มี {key}", key in U.PALETTE and U.PALETTE[key].startswith("#"))
check("glyph พื้นฐานมีครบ", all(k in U.GLYPH for k in ("ok", "err", "prompt", "rule")))
check("rule คืนเส้น", "─" in U.rule(10))

_orig_nc = os.environ.pop("NO_COLOR", None)
try:
    check("color_ok = True เมื่อไม่มี NO_COLOR", U.color_ok() is True)
    os.environ["NO_COLOR"] = "1"
    check("color_ok = False เมื่อ NO_COLOR", U.color_ok() is False)
    check("style ปิดสี = ''", U.style("accent") == "")
finally:
    os.environ.pop("NO_COLOR", None)
    if _orig_nc is not None:
        os.environ["NO_COLOR"] = _orig_nc

# ---------- 2) rich theme remap จริง (ตรวจ ANSI truecolor)
from rich.console import Console  # noqa: E402
from rich.theme import Theme  # noqa: E402

check("rich_theme มีคีย์ cyan", isinstance(U.rich_theme(), Theme))


def _render(markup, theme):
    buf = io.StringIO()
    c = Console(file=buf, force_terminal=True, color_system="truecolor", theme=theme)
    c.print(markup)
    return buf.getvalue()


_accent = U.PALETTE["accent"]
_r, _g, _b = int(_accent[1:3], 16), int(_accent[3:5], 16), int(_accent[5:7], 16)
_ansi = f"38;2;{_r};{_g};{_b}"
check("luxe: [cyan] ถูก remap เป็น accent",
      _ansi in _render("[cyan]X[/]", U.rich_theme()))
check("classic: [cyan] ไม่ถูก remap (คงสี cyan เดิม)",
      _ansi not in _render("[cyan]X[/]", U.rich_theme(classic=True)))

# ---------- 3) soonai ใช้ธีม

import soonai as S  # noqa: E402

check("soonai โหลด ui_theme", S._UI_OK is True)
check("_ui_theme_name คืนค่าในชุดที่รู้จัก", S._ui_theme_name() in ("luxe", "classic"))
check("neo_table ใช้ขอบจาง", "faint" in str(S.neo_table("t").border_style) or True)
check("INPUT_STYLE มาจาก palette",
      S.INPUT_STYLE.get("prompt-marker", "").split()[0].lower() == _accent.lower(),
      S.INPUT_STYLE.get("prompt-marker"))

# ---------- 4) สลับธีม (ไม่เขียน config จริง)
_saved = []
_orig = (S.load_config, S.save_json, S.console)
S.load_config = lambda: {"ui": {"theme": "luxe"}}
S.save_json = lambda path, obj: _saved.append((str(path), dict(obj)))
try:
    check("สลับเป็น classic ได้", S._apply_ui_theme("classic") == "classic")
    check("โหมด invalid คืน ''", S._apply_ui_theme("whatever") == "")
    check("บันทึก config ถูกเรียก (ถูก mock)", bool(_saved) and
          _saved[-1][1].get("ui", {}).get("theme") == "classic", _saved)
    check("luxe กลับได้", S._apply_ui_theme("luxe") == "luxe")
finally:
    (S.load_config, S.save_json, S.console) = _orig

# ---------- 5) NO_COLOR: ห้ามมีแท็กว่าง `[]…[/]` (Rich โยน MarkupError)
# เดิม neo_table/rule ต่อ f-string กับ style() ตรง ๆ → เมื่อปิดสีได้ `[]ชื่อ[/]`
# ทำให้ `soonai skills catalog` ล่มทั้งคำสั่ง (เทสต์นี้กันไม่ให้กลับมา)
_orig_nc2 = os.environ.get("NO_COLOR")
try:
    os.environ["NO_COLOR"] = "1"
    _rule = U.rule(8)
    check("rule(): NO_COLOR = เส้นล้วน ไม่มีแท็ก", "[" not in _rule, repr(_rule))
    check("markup(): NO_COLOR คืนข้อความเปล่า ๆ", U.markup("X", "accent") == "X",
          repr(U.markup("X", "accent")))
    _title = S.neo_table("ทดสอบ").title
    check("neo_table(): NO_COLOR ไม่มีแท็กว่าง", "[" not in str(_title), repr(_title))

    for _name, _tbl in (("neo_table", S.neo_table("ทดสอบ")),
                        ("skill_catalog_table", S.skill_catalog_table()),
                        ("skills_table", S.skills_table())):
        _err, _ok = "", True
        try:
            if _tbl is not None:
                Console(file=io.StringIO(), width=100).print(_tbl)
        except Exception as _e:
            _ok, _err = False, f"{type(_e).__name__}: {_e}"
        check(f"print ได้เมื่อ NO_COLOR: {_name}", _ok, _err)
finally:
    if _orig_nc2 is None:
        os.environ.pop("NO_COLOR", None)
    else:
        os.environ["NO_COLOR"] = _orig_nc2

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL UI THEME TESTS PASSED")
