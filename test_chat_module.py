# -*- coding: utf-8 -*-
"""Regression: Step 5 แยก cmd_chat ออกจาก soonai.py ไป shared/chat.py

ตรวจ 5 อย่าง:
1) โหลดถูกไฟล์จริง + identity (soonai.cmd_chat คือ object เดียวกับ chat.cmd_chat)
2) ขอบเขต: ไม่มีชื่อว่างเลย — chat อ่าน seam ผ่าน `runtime` + รับ state ผ่าน st
   (รวมเช็คว่าทุกฟังก์ชันที่ใช้ st มี st ให้ใช้จริง ไม่ใช่แค่ scope ระดับโมดูล)
3) ไม่ import soonai กลับ และถูกนำเข้าแบบไม่ bind (bind_refs = 0)
4) ทุก R.<ชื่อ> ที่ใช้มีอยู่จริงบน runtime + patch จากภายนอกถึงโค้ดภายใน
5) พฤติกรรมคีย์: ChatState เป็นที่เก็บ state, handle_command คืน True/EXIT/False
   ตามสัญญาใหม่ (เดิมคือ continue/break/ไหลต่อในลูปของ cmd_chat)

ไม่แตะไฟล์/เน็ต · ไม่เรียก stdin
"""
import ast
import builtins
import io
import re
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

import chat as C  # noqa: E402

from rich.console import Console  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


MOVED = ["ChatState", "handle_command", "read_input", "_framed_input", "_agi_turn",
         "EXIT", "cmd_chat"]

# ---------- 1) โหลดถูกไฟล์จริง + identity ----------
check("chat เป็นโมดูลไฟล์ shared/chat.py",
      Path(C.__file__).name == "chat.py" and Path(C.__file__).parent.name == "shared",
      C.__file__)
check("soonai อ้างโมดูล chat", getattr(S, "_chat_mod", None) is C)
check("soonai.cmd_chat = chat.cmd_chat (object เดียวกัน)",
      S.cmd_chat is C.cmd_chat and S.cmd_chat.__module__ == "chat",
      f"{S.cmd_chat.__module__}.{S.cmd_chat.__name__}")
_missing = [n for n in MOVED if not hasattr(C, n)]
check("โมดูลมีชื่อที่ย้ายมาครบ", not _missing, _missing)
# ตัวช่วยเดิมเป็น local ของ cmd_chat → ไม่ต้อง re-export และไม่ควรหลุดไป soonai
_not_exported = [n for n in MOVED if n != "cmd_chat" and hasattr(S, n)]
check("ตัวช่วยภายในไม่หลุดไป soonai (ขอบเขตสะอาด)", not _not_exported, _not_exported)

# ---------- 2) ขอบเขต: ไม่มีชื่อว่าง ----------
_src = Path(C.__file__).read_text(encoding="utf-8")
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
check("ไม่มีชื่อว่างเลย (อ่าน seam ผ่าน runtime เท่านั้น)", not _free, _free)


def _st_deps(fn):
    """(จำนวนที่ใช้ st, มี st ให้ใช้จริง) — เดินเฉพาะ body ของฟังก์ชันนี้เอง"""
    _args = {a.arg for a in list(fn.args.args) + list(fn.args.posonlyargs)
             + list(fn.args.kwonlyargs)}
    _loads, _stores = 0, False

    def rec(n):
        nonlocal _loads, _stores
        if n is not fn and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                          ast.Lambda, ast.ClassDef)):
            return
        if isinstance(n, ast.Name) and n.id == "st":
            if isinstance(n.ctx, ast.Store):
                _stores = True
            else:
                _loads += 1
        for ch in ast.iter_child_nodes(n):
            rec(ch)

    rec(fn)
    return _loads, ("st" in _args or _stores)


_bad_st = [n.name for n in ast.walk(_tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and _st_deps(n)[0] and not _st_deps(n)[1]]
check("ทุกฟังก์ชันที่ใช้ st มี st ให้ใช้จริง", not _bad_st, _bad_st)
for _sig in ("def _framed_input(st):", "def read_input(st):", "def _agi_turn(st, goal):"):
    check(f"ตัวช่วยรับ st เป็นพารามิเตอร์แรก: {_sig.split('(')[0][4:]}", _sig in _src)

check("โมดูลไม่ import soonai กลับ", "soonai" not in _bound, sorted(_bound))
check("ถูกนำเข้าแบบไม่ bind (bind_refs = 0)",
      C not in set(R.bound_modules()), [m.__name__ for m in R.bound_modules()])
_R_used = sorted(set(re.findall(r"\bR\.([A-Za-z_][A-Za-z0-9_]*)", _src)))
check(f"ทุก R.<ชื่อ> ที่ใช้มีจริงบน runtime ({len(_R_used)} ชื่อ)",
      not [x for x in _R_used if not hasattr(R, x)],
      [x for x in _R_used if not hasattr(R, x)])

# ---------- 3) patch จากภายนอกถึงโค้ดภายใน ----------
_orig_console = S.console
_probe = object()
S.console = _probe
check("patch S.console → chat เห็นผ่าน runtime", C.R.console is _probe)
S.console = _orig_console
check("คืนค่า console เรียบร้อย", S.console is _orig_console and C.R.console is _orig_console)
# chat ไม่อยู่ในทะเบียนเจ้าของชื่อ (ไม่ได้ re-export อะไรเลยนอกจาก cmd_chat) → ไม่ต้อง
# propagate; แต่การ patch ยัง mirror ลง runtime ตาม facade ของ soonai
_orig_cmd = S.cmd_chat
_other = object()
S.cmd_chat = _other
check("patch S.cmd_chat → mirror ลง runtime", R.cmd_chat is _other)
check("แต่สำเนาในโมดูล chat ไม่ถูกเขียนทับ (อ่าน seam ผ่าน runtime เท่านั้น)",
      C.cmd_chat is _orig_cmd and C not in R.owners("cmd_chat"),
      [m.__name__ for m in R.owners("cmd_chat")])
S.cmd_chat = _orig_cmd

# ---------- 4) พฤติกรรมคีย์ของ handle_command (สัญญาใหม่) ----------
_orig_print = R.console.print
_buf = io.StringIO()
R.console = Console(file=_buf, width=100)
_maybe_reflect = []
_orig_reflect = S.maybe_reflect
S.maybe_reflect = lambda *a: _maybe_reflect.append(a)
_orig_detect, _orig_runtests = S.detect_test_command, S.run_tests_command
S.detect_test_command = lambda *a, **k: "pytest -q"
S.run_tests_command = lambda *a, **k: ("1 failed", False)    # ให้ /test ไม่ผ่าน → ไหลต่อ
try:
    st = C.ChatState(type("A", (), {"temperature": 0.7})(), {}, {})
    check("ChatState เริ่มต้นว่างตามเดิม",
          (st.provider, st.model, st.history, st.sid, st.agent, st.auto_yes) ==
          ("", "", [], None, False, False) and st.temperature == 0.7,
          (st.provider, st.model, st.agent, st.temperature))
    check("handle_command('/exit') คืน EXIT + สะท้อนบทเรียนก่อนออก",
          C.handle_command(st, "/exit") == C.EXIT and len(_maybe_reflect) == 1,
          _maybe_reflect)
    check("handle_command('/quit') คืน EXIT (เทียบตัวพิมพ์เล็ก)",
          C.handle_command(st, "/QUIT") == C.EXIT)
    check("handle_command('/clear') คืน True + ล้างประวัติ",
          C.handle_command(st, "/clear") is True and st.history == [], st.history)
    check("handle_command('/shell') คืน True (คำสั่งที่จัดการเอง)",
          C.handle_command(st, "/shell") is True)
    check("handle_command ไม่รู้จัก = False (ไหลต่อไปส่งงานโมเดล)",
          C.handle_command(st, "สวัสดีครับ") is False)
    check("handle_command('/test') ที่ไม่ผ่าน = False + แก้ st.q ให้ไหลต่อ",
          C.handle_command(st, "/test") is False and isinstance(st.q, str),
          repr(st.q))
    check("EXIT เป็นค่าคงที่ระดับโมดูล (ไม่ใช่ bool)",
          C.EXIT == "exit" and not isinstance(C.EXIT, bool), repr(C.EXIT))
    check("ลูปใช้ EXIT ตามสัญญา (เช็คจากซอร์ส)",
          "if _cmd == EXIT:" in _src and "_cmd = handle_command(st, q)" in _src)
finally:
    S.maybe_reflect = _orig_reflect
    S.detect_test_command, S.run_tests_command = _orig_detect, _orig_runtests
    R.console = _orig_print

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL CHAT MODULE TESTS PASSED")
