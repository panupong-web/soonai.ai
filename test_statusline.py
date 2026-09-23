# -*- coding: utf-8 -*-
"""Regression: TUI (M6) — บรรทัดสถานะ · log tool ของ session · สรุป ±บรรทัด
- status_line: โมเดล/โหมด/shell/git/undo/token เฉพาะที่มีจริง
- _status_extras: cache (ไม่เรียก git ซ้ำทุกเฟรม)
- _record_tools: จำกัดจำนวน + /tools อ่านได้
- _diff_stat_line: นับ +และ- ให้ถูก + ไม่พังกับ tool อื่น
- build_input_bar: รับ status ยาวมากได้โดยไม่พัง (ตัดในกรอบเอง)
ไม่แตะเน็ต (เขียน temp ไฟล์ในโฟลเดอร์งานชั่วคราว)
"""
import io
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

from rich.console import Console  # noqa: E402

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


tmp = Path(tempfile.mkdtemp(prefix="soonai-tui-"))
_orig = (S.workspace_root, S.load_config, S.console)
S.workspace_root = lambda: tmp.resolve()
S.load_config = lambda: {"agent": {"shell": "safe", "checkpoints": True}}
S.console = Console(file=io.StringIO(), width=200, force_terminal=False)

try:
    # ---------- status_line
    S.usage_reset()
    S.SESSION_TOOLS[:] = []
    S._CP["bucket"] = None
    S.CHECKPOINT_DIR = tmp / ".cp"
    S._STATUS_CACHE["extra"] = None
    base = S.status_line("openrouter", "cohere/x", agent=True, auto_yes=False, effort="low")
    check("status: มีโมเดล", "cohere/x" in base, base)
    check("status: มีโหมด agent + effort", "agent" in base and "eff:low" in base, base)
    check("status: มี shell ที่เปิดอยู่", "shell:safe" in base, base)
    check("status: ไม่มี AUTO เมื่อปิด", "AUTO" not in base, base)
    check("status: ไม่มี token ตอนยังไม่ใช้", "tok" not in base, base)
    S.usage_note("openrouter", "free-model", 1200, 300)
    check("status: โชว์ token หลังใช้งาน", "tok" in S.status_line("openrouter", "m"), base)
    S._STATUS_CACHE["extra"] = None
    S.load_config = lambda: {"agent": {"shell": "off", "checkpoints": True}}
    off = S.status_line("ollama", "llama3", auto_yes=True)
    check("status: shell off ไม่แสดง", "shell:" not in off, off)
    check("status: AUTO แสดงเมื่อเปิด", "AUTO" in off, off)
    S.load_config = lambda: {"agent": {"shell": "safe", "checkpoints": True}}

    # checkpoint → undo:N
    f = tmp / "x.txt"
    S.checkpoint_file(f)
    S._STATUS_CACHE["extra"] = None
    check("status: โชว์จำนวน checkpoint", "undo:1" in S.status_line("openrouter", "m"),
          S.status_line("openrouter", "m"))

    # ---------- _status_extras cache
    calls = {"n": 0}
    _orig_changes = S.git_changes
    _orig_in_repo = S.git_in_repo
    S.git_in_repo = lambda: True
    S.git_changes = lambda: (calls.__setitem__("n", calls["n"] + 1) or [("M", "a.py")])
    S.git_branch = lambda: "main"
    S._STATUS_CACHE["extra"] = None
    S._STATUS_CACHE["t"] = 0.0
    e1 = S._status_extras(ttl=30)
    e2 = S._status_extras(ttl=30)
    check("extras: มีสาขา + สกปรก", "git:main*1" in e1, e1)
    check("extras: cache ทำงาน (เรียก git ครั้งเดียว)", calls["n"] == 1, calls)
    check("extras: คืนค่าเดิมจาก cache", e1 == e2, (e1, e2))
    S._STATUS_CACHE["t"] = 0.0
    S._status_extras(ttl=0)
    check("extras: หมดอายุแล้วอ่านใหม่", calls["n"] == 2, calls)
    S.git_changes = _orig_changes
    S.git_in_repo = _orig_in_repo

    # ---------- tool log
    S.SESSION_TOOLS[:] = []
    S._record_tools([("write_file", "ok", "OK: เขียนไฟล์ x (+3/-1 บรรทัด)")])
    S._record_tools([("run_tests", "error", "exit=1")])
    check("tool log: เก็บครบ", len(S.SESSION_TOOLS) == 2, S.SESSION_TOOLS)
    check("tool log: เก็บเป็น tuple 3 ช่อง",
          S.SESSION_TOOLS[0] == ("write_file", "ok", "OK: เขียนไฟล์ x (+3/-1 บรรทัด)"),
          S.SESSION_TOOLS[0])
    S._record_tools([("t", "ok", "x")] * (S.SESSION_TOOLS_MAX + 20))
    check("tool log: จำกัดจำนวน", len(S.SESSION_TOOLS) == S.SESSION_TOOLS_MAX, len(S.SESSION_TOOLS))
    S._record_tools(["ชื่อล้วน"])
    check("tool log: รับสตริงเดี่ยวได้", S.SESSION_TOOLS[-1] == ("ชื่อล้วน", "", ""), S.SESSION_TOOLS[-1])

    # ---------- _diff_stat_line
    target = tmp / "code.py"
    S.CHECKPOINT_DIR = tmp / ".cp2"
    S._CP["bucket"] = None
    line = S._diff_stat_line("write_file", {"path": str(target), "content": "a\nb\nc\n"})
    check("diff stat: ไฟล์ใหม่ = +3/-0", line == "+3/-0 บรรทัด", line)
    target.write_text("a\nb\nc\n", encoding="utf-8")
    line2 = S._diff_stat_line("edit_file", {"path": str(target), "old_string": "b",
                                           "new_string": "B\nBB"})
    check("diff stat: แก้ไข = นับ +/- (2 บรรทัดใหม่ 1 บรรทัดหาย)",
          line2 == "+2/-1 บรรทัด", line2)
    check("diff stat: tool อื่น = ว่าง", S._diff_stat_line("read_file", {"path": str(target)}) == "")
    check("diff stat: path พัง = ว่าง", S._diff_stat_line("write_file", {}) == "")

    # ---------- build_input_bar รับ status ยาว
    long_status = "openrouter / cohere/north-mini-code:free · agent · shell:safe · " \
                  "git:main*12 · test:มี · undo:9 · ~128.4k tok เข้า/12.3k ออก · 42 calls"
    layout, buf, kb = S.build_input_bar(None, long_status)
    check("input bar: สร้างได้พร้อมสถานะยาว", layout is not None and buf is not None)
    check("input bar: ยังคุมความกว้างของกรอบได้", S._dwidth(long_status) > 60)
    check("input bar: สถานะว่างก็ยังประกอบได้", S.build_input_bar(None, "")[0] is not None)

    # ---------- ⚠ statusline: ค่าย timeout ล่าสุด ----------
    _orig_hf = S._health_file
    S._health_file = lambda: tmp / "health.json"
    try:
        S._STATUS_CACHE["slow"] = None
        check("slow: ไม่มีอะไร = ไม่โชว์", S.slow_statusline("openrouter") == "",
              S.slow_statusline("openrouter"))
        S._health_note_slow("openrouter")
        S._STATUS_CACHE["slow"] = None
        mark = S.slow_statusline("openrouter")
        check("slow: ค่ายที่เพิ่ง timeout = ⚠timeout + อายุ", "⚠timeout:" in mark, mark)
        check("slow: มีแค่ค่ายนี้ = ไม่โชว์ค่ายอื่น", "⚠slow:" not in mark, mark)
        other = S.slow_statusline("groq")
        check("slow: ค่ายอื่นมองเห็นเป็น ⚠slow:ชื่อ", "⚠slow:openrouter" in other, other)
        S._STATUS_CACHE["slow"] = None
        line = S.status_line("openrouter", "cohere/x")
        check("status: เซกเมนต์ ⚠timeout อยู่ในแถบสถานะจริง", "⚠timeout:" in line, line)
        # cache 5s: แก้ไฟล์กลางทางในช่วง cache = ยังค่าเดิม (ทุกเฟรมไม่ยิงไฟล์ซ้ำ)
        a1 = S.slow_statusline("openrouter")
        (tmp / "health.json").write_text(
            json.dumps({"slow": {"groq": time.time()}}), encoding="utf-8")
        a2 = S.slow_statusline("openrouter")
        check("slow: cache 5s (ไม่อ่านไฟล์ซ้ำทุกเฟรม)",
              "⚠timeout:" in a1 and "⚠slow:groq" not in a2 and a1 == a2, (a1, a2))
        # หมดอายุ (เกิน SLOW_TTL) = เงียบ
        (tmp / "health.json").write_text(
            json.dumps({"slow": {"openrouter": time.time() - S.SLOW_TTL - 60}}),
            encoding="utf-8")
        S._STATUS_CACHE["slow"] = None
        check("slow: เกิน SLOW_TTL = ไม่โชว์", S.slow_statusline("openrouter") == "",
              S.slow_statusline("openrouter"))
    finally:
        S._health_file = _orig_hf
        S._STATUS_CACHE["slow"] = None
finally:
    S.workspace_root, S.load_config, S.console = _orig

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL STATUS LINE TESTS PASSED")
