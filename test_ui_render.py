# -*- coding: utf-8 -*-
"""Regression: Step 3 แยกเลเยอร์ UI/เรนเดอร์ออกจาก soonai.py ไป shared/ui_render.py

ตรวจ 4 อย่าง:
1) ทุกชื่อที่ย้ายไป ยัง re-export จาก soonai แบบ object เดียวกัน (identity)
2) ขอบเขต: โมดูลนี้ไม่พึ่ง namespace ของ soonai เลย — อ่าน seam ผ่าน `runtime`
   และ import โมดูลพี่น้อง (shell/usage/providers/ui_theme) ตรง ๆ
3) การ patch จากภายนอก (`S.X = ...`) ส่งผลถึงโค้ดภายใน ui_render จริง
4) พฤติกรรมเดิมยังอยู่: neo_table ปลอดภัยเมื่อ NO_COLOR · INPUT_STYLE มาจาก palette

ไม่แตะไฟล์/เน็ต
"""
import ast
import builtins
import io
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import runtime as R  # noqa: E402

import soonai as S  # noqa: E402

import ui_render as UR  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ── ชื่อที่ย้ายไปทั้งหมด (ต้อง re-export จาก soonai) ──────────────────────────
MOVED = [
    "LOGO", "_hex", "neon", "_rainbow_line", "_rainbow_logo", "_thai_attach",
    "_clusters", "welcome_popup", "boot_sequence", "show_banner", "set_term_title",
    "neo_table", "rgb_hex", "COSMOS_STARS", "COSMOS_FAMILIES", "COSMOS_TITLE",
    "COSMOS_COMET", "COSMOS_GLOW_R", "_cosmos_on", "_cosmos_hash", "_unhex",
    "_cosmos_fade", "_cosmos_nebula", "_cosmos_cell", "_cosmos_edge", "_cosmos_word",
    "_input_style", "INPUT_STYLE", "build_input_bar", "SLASH_COMMANDS",
    "slash_suggestions", "show_command_menu", "short_model", "_record_tools",
    "_diff_stat_line", "_status_extras", "status_line", "current_summary",
    "_term_width", "_dwidth", "box_title", "input_box_top", "locked_box_text",
    "input_box_bottom",
]

# ---------- 1) โหลดถูกไฟล์จริง + identity ----------
check("ui_render เป็นโมดูลไฟล์ shared/ui_render.py",
      Path(UR.__file__).name == "ui_render.py"
      and Path(UR.__file__).parent.name == "shared", UR.__file__)
check("soonai อ้างโมดูล ui_render", getattr(S, "_ui_render_mod", None) is UR)

_missing = [n for n in MOVED if not hasattr(UR, n)]
check("โมดูลมีชื่อที่ย้ายมาครบ", not _missing, _missing)
_not_reexported = [n for n in MOVED if n not in S.__dict__]
check("ทุกชื่อ re-export มาถึง soonai จริง", not _not_reexported, _not_reexported[:8])
_not_same = [n for n in MOVED if getattr(S, n) is not getattr(UR, n, object())]
check("identity: soonai ชี้ object เดียวกับ ui_render", not _not_same, _not_same[:8])
check("provenance: soonai patch แล้วถึงโมดูล",
      UR in R.owners("neo_table") and UR in R.owners("status_line"),
      [R.owners("neo_table"), R.owners("status_line")])

# ---------- 2) ขอบเขต: ไม่มีชื่อว่าง (ไม่ได้มาจาก namespace ของ soonai) ----------
_src = Path(UR.__file__).read_text(encoding="utf-8")
_tree = ast.parse(_src)
_bound, _used = set(), set()
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Import):
        for _a in _node.names:
            _bound.add((_a.asname or _a.name).split(".")[0])
    elif isinstance(_node, ast.ImportFrom):
        for _a in _node.names:
            _bound.add(_a.asname or _a.name)
    elif isinstance(_node, ast.Name) and isinstance(_node.ctx, (ast.Store, ast.Del)):
        _bound.add(_node.id)
    elif isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _bound.add(_node.name)
        for _a in (list(_node.args.args) + list(_node.args.posonlyargs)
                   + list(_node.args.kwonlyargs)):
            _bound.add(_a.arg)
        if _node.args.vararg:
            _bound.add(_node.args.vararg.arg)
        if _node.args.kwarg:
            _bound.add(_node.args.kwarg.arg)
    elif isinstance(_node, ast.ClassDef):
        _bound.add(_node.name)
    elif isinstance(_node, ast.Lambda):
        for _a in _node.args.args:
            _bound.add(_a.arg)
    elif isinstance(_node, ast.ExceptHandler) and _node.name:
        _bound.add(_node.name)
    if isinstance(_node, ast.Name) and isinstance(_node.ctx, ast.Load):
        _used.add(_node.id)
_free = sorted(_used - _bound - set(dir(builtins)))
check("ไม่มีชื่อว่างเลย (อ่าน seam ผ่าน runtime/พี่น้องเท่านั้น)", not _free, _free)

check("โมดูลไม่ import soonai กลับ", "soonai" not in _bound, sorted(_bound))
check("ถูกนำเข้าแบบไม่ bind (bind_refs = 0)",
      UR not in set(R.bound_modules()), [m.__name__ for m in R.bound_modules()])
check("ทุก R.<name> ที่ใช้มีจริงบน runtime",
      not [x for x in sorted(set(__import__("re").findall(
          r"\bR\.([A-Za-z_][A-Za-z0-9_]*)", _src))) if not hasattr(R, x)])

# ---------- 3) patch จากภายนอกถึงโค้ดภายใน ----------
_orig_console = S.console
_probe = object()
S.console = _probe
check("patch S.console → ui_render เห็นผ่าน runtime", R.console is _probe)
S.console = _orig_console

_orig_cfg = S.load_config
S.load_config = lambda: {"ui": {"animation": False}}
R._COSMOS_MODE["on"] = None
check("patch S.load_config → _cosmos_on ใช้ค่าใหม่", UR._cosmos_on() is False)
S.load_config = _orig_cfg
R._COSMOS_MODE["on"] = None

_orig_short = S.short_model
S.short_model = lambda m, limit=40: "<patched>"
check("patch S.short_model → status_line ใช้ค่าใหม่",
      "<patched>" in UR.status_line("openrouter", "some/model"),
      UR.status_line("openrouter", "some/model"))
S.short_model = _orig_short

# ---------- 4) พฤติกรรมเดิมยังอยู่ ----------
check("INPUT_STYLE จาก palette (accent)",
      UR.INPUT_STYLE.get("prompt-marker", "").split()[0].lower()
      == __import__("ui_theme").PALETTE["accent"].lower(),
      UR.INPUT_STYLE.get("prompt-marker"))
_slash = dict(UR.SLASH_COMMANDS)
check("SLASH_COMMANDS ยังมีครบ (>=30)", len(_slash) >= 30, len(_slash))
check("slash_suggestions กรองได้", [c for c, _ in UR.slash_suggestions("/mo")] == ["/model"],
      UR.slash_suggestions("/mo"))
check("slash_suggestions: '/' = ทั้งหมด, มีช่องว่าง = ว่าง",
      len(UR.slash_suggestions("/")) == len(UR.SLASH_COMMANDS)
      and UR.slash_suggestions("/model x") == [])
check("_dwidth/_term_width ทำงาน", UR._dwidth("abc") == 3 and UR._term_width() >= 40)
check("locked_box_text วาดกรอบได้", "┌" in UR.locked_box_text("t", "b", width=40))

_orig_nc = os.environ.get("NO_COLOR")
try:
    os.environ["NO_COLOR"] = "1"
    _title = UR.neo_table("ทดสอบ").title
    check("neo_table: NO_COLOR ไม่มีแท็กว่าง", "[" not in str(_title), repr(_title))
    _ok, _err = True, ""
    try:
        from rich.console import Console
        Console(file=io.StringIO(), width=100).print(UR.neo_table("ทดสอบ"))
    except Exception as _e:
        _ok, _err = False, f"{type(_e).__name__}: {_e}"
    check("neo_table: print ได้เมื่อ NO_COLOR", _ok, _err)
finally:
    if _orig_nc is None:
        os.environ.pop("NO_COLOR", None)
    else:
        os.environ["NO_COLOR"] = _orig_nc

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL UI RENDER MODULE TESTS PASSED")
