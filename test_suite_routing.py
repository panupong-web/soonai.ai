# -*- coding: utf-8 -*-
"""Regression: standalone_suite_test ต้อง "รันจริง" ทุกไฟล์ ไม่ปล่อยให้ผ่านฟรี

ที่มา: conftest.py สั่ง collect_ignore ทุก test_*.py (กัน pytest import ไฟล์ที่
sys.exit ตอน collect) ผลข้างเคียงคือไฟล์ที่เขียนแบบ pytest ล้วน — มีแต่
`def test_*(): assert ...` ไม่มีโค้ดระดับโมดูล — พอถูกรันเป็นสคริปต์จะจบ 0
โดยไม่ได้ assert อะไรเลย = เขียวปลอมทั้งไฟล์

ตรวจ:
1) _is_pytest_style แยกถูก: pytest ล้วน → True · standalone script → False
   · ผสม (มี test_ + sys.exit ระดับโมดูล) → False · พาส/ไม่มีไฟล์ → False
2) _command_for ส่งไฟล์ pytest-style เข้า pytest จริง
3) รันจริง: ไฟล์ที่เคยเขียวปลอมต้อง collect ได้ >= 1 เทสต์ (ไม่ใช่ 0)
4) ไฟล์ทุกไฟล์ใน repo ถูกจัดหมวด และหมวดตรงกับความตั้งใจ
"""
import os
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import standalone_suite_test as SS  # noqa: E402

ROOT = Path(__file__).resolve().parent
FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


def _probe(name, source):
    """เขียนไฟล์ชั่วคราวลง repo root แล้วคืนชื่อที่ใช้กับ _is_pytest_style

    ตั้งชื่อไม่ขึ้นต้นด้วย test_ เพราะ _SCRIPTS glob จาก test_*.py — ถ้าใช้ชื่อชน
    จะทำให้ suite ไปรันไฟล์ขยะที่สร้างไว้ในเทสต์นี้
    """
    path = ROOT / name
    path.write_text(source, encoding="utf-8")
    return path


# ---------- 1) แยกหมวดถูก ----------
_PROBES = {
    "_probe_pytest_only.py": 'def test_a():\n    assert 1 + 1 == 2\n',
    "_probe_script_only.py": (
        'import sys\nprint("ok: x")\nif False:\n    sys.exit(1)\n'
        'print("ALL PASSED")\n'
    ),
    "_probe_mixed.py": (
        'import sys\nFAILS = []\ndef test_a():\n    assert True\n'
        'if FAILS:\n    print(FAILS)\n    sys.exit(1)\nprint("ALL PASSED")\n'
    ),
    "_probe_raise_mixed.py": (
        'def test_a():\n    assert True\n'
        'try:\n    pass\nexcept Exception:\n    raise SystemExit(1)\n'
    ),
    "_probe_exit_in_func.py": (
        'import sys\ndef test_a():\n    sys.exit(1)\n'
    ),
    "_probe_broken.py": "def test_a(:\n",
}
_paths = {n: _probe(n, s) for n, s in _PROBES.items()}
try:
    check("pytest ล้วน → รันด้วย pytest", SS._is_pytest_style("_probe_pytest_only.py") is True)
    check("standalone script → รันตรง", SS._is_pytest_style("_probe_script_only.py") is False)
    check("ผสม (มี test_ + sys.exit ระดับโมดูล) → รันตรง",
          SS._is_pytest_style("_probe_mixed.py") is False)
    check("raise SystemExit ใน try ระดับโมดูล → รันตรง",
          SS._is_pytest_style("_probe_raise_mixed.py") is False)
    check("sys.exit ในตัวเทสต์ (ไม่ใช่ระดับโมดูล) → ยังเป็น pytest-style",
          SS._is_pytest_style("_probe_exit_in_func.py") is True)
    check("ไฟล์พาส syntax → รันตรง (fail ดัง ๆ ดีกว่าเงียบ)",
          SS._is_pytest_style("_probe_broken.py") is False)
    check("ไม่มีไฟล์ → รันตรง", SS._is_pytest_style("_probe_missing.py") is False)

    cmd = SS._command_for("_probe_pytest_only.py")
    check("command ของ pytest-style ขึ้นต้นด้วย python -m pytest",
          cmd[:3] == [sys.executable, "-m", "pytest"], cmd)
    check("command ของ pytest-style ไม่ถูก addopts ของโปรเจกต์แทรก",
          "-o" in cmd and "addopts=" in cmd, cmd)
    check("command ของ standalone = รันไฟล์ตรง",
          SS._command_for("_probe_script_only.py") == [sys.executable, "_probe_script_only.py"],
          SS._command_for("_probe_script_only.py"))
finally:
    for p in _paths.values():
        try:
            p.unlink()
        except OSError:
            pass

# ---------- 2) ไฟล์จริงใน repo ----------
check("test_theme_catalog.py (ต้นเหตุเขียวปลอม) ถูกส่งเข้า pytest",
      SS._is_pytest_style("test_theme_catalog.py") is True)
check("test_ui_render.py (standalone) ถูกรันตรง",
      SS._is_pytest_style("test_ui_render.py") is False)
check("ตัวเทสต์นี้เองถูกรันตรง (ไม่ใช่ pytest-style)",
      SS._is_pytest_style(Path(__file__).name) is False)

_pytest_style = [s for s in SS._SCRIPTS if SS._is_pytest_style(s)]
print(f"    (pytest-style ใน repo: {_pytest_style or 'ไม่มี'})")

# ---------- 3) รันจริง — collect ต้องไม่เป็น 0 ----------
_env = SS._subprocess_env() if hasattr(SS, "_subprocess_env") else dict(os.environ)
for _script in _pytest_style:
    _proc = subprocess.run(
        [sys.executable, "-m", "pytest", _script, "-q", "--collect-only",
         "-p", "no:cacheprovider", "--no-header", "-o", "addopts="],
        cwd=str(ROOT), env=_env, capture_output=True, text=True, timeout=180,
    )
    _out = (_proc.stdout or "") + (_proc.stderr or "")
    check(f"{_script}: pytest collect ได้จริง (ไม่ใช่เขียวปลอม)",
          _proc.returncode == 0 and "no tests ran" not in _out
          and ("test" in _out and "::" in _out),
          _out.strip()[-400:])

# ---------- 4) env ของ subprocess ต้องบังคับ UTF-8 ----------
_env = SS._subprocess_env()
check("subprocess env ตั้ง PYTHONUTF8", _env.get("PYTHONUTF8") == "1", _env.get("PYTHONUTF8"))
check("subprocess env ตั้ง PYTHONIOENCODING", _env.get("PYTHONIOENCODING", "").lower() == "utf-8",
      _env.get("PYTHONIOENCODING"))

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL SUITE ROUTING TESTS PASSED")
