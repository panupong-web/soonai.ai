# -*- coding: utf-8 -*-
"""ทางเข้า `python -m pytest` ของโปรเจกต์นี้

เทสต์จริงอยู่ในไฟล์ test_*.py แบบ standalone (รันโค้ดระดับโมดูล + sys.exit เอง)
ไฟล์นี้รันแต่ละไฟล์เป็น subprocess **แยกโปรเซส** (คงการแยก env/global ที่แต่ละ
เทสต์ต้องพึ่ง) แล้วรัน **ขนานกัน** เพื่อลดเวลา (ดูเหตุผลการแยกที่ conftest.py)
"""
import ast
import concurrent.futures as _cf
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent
_SCRIPTS = sorted(p.name for p in _ROOT.glob("test_*.py"))


def _jobs():
    """จำนวนโปรเซสขนาน — ENV SOONAI_TEST_JOBS ทับได้ (0/ว่าง = อัตโนมัติตาม cpu)"""
    try:
        n = int(os.environ.get("SOONAI_TEST_JOBS") or 0)
    except Exception:
        n = 0
    if n <= 0:
        n = min(len(_SCRIPTS) or 1, max(2, (os.cpu_count() or 4)))
    return max(1, min(n, len(_SCRIPTS) or 1))


def _timeout():
    try:
        return max(30, int(os.environ.get("SOONAI_TEST_TIMEOUT") or 300))
    except Exception:
        return 300


_EXIT_FUNCS = {"exit", "quit", "_exit"}


def _exits_now(node):
    """โหนดนี้คือ sys.exit()/raise SystemExit/exit() หรือไม่"""
    if isinstance(node, ast.Raise):
        return "SystemExit" in ast.dump(node)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr in _EXIT_FUNCS
        if isinstance(func, ast.Name):
            return func.id in _EXIT_FUNCS
    return False


def _module_level_nodes(tree):
    """ทุกโหนดระดับโมดูล (รวมที่อยู่ใน if/try/with) แต่ไม่ลงไปใน def/class

    exit ที่อยู่ข้างในฟังก์ชันไม่ใช่สัญญาณของ standalone script — pytest-style
    ก็เรียก sys.exit ใน test ได้เหมือนกัน
    """
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _is_pytest_style(script):
    """ไฟล์นี้เขียนแบบ pytest (def test_*) ไม่ใช่ standalone script หรือเปล่า

    conftest.py สั่ง collect_ignore ทุก test_*.py เพื่อไม่ให้ pytest import ไฟล์ที่
    sys.exit() ตอน collect — ผลข้างเคียงคือไฟล์แบบ pytest ล้วนจะ "ผ่าน" โดยไม่ได้
    assert อะไรเลย (รันเป็น script แล้วจบ 0) จึงต้องแยกให้ออกแล้วรันด้วย pytest จริง
    """
    try:
        tree = ast.parse((_ROOT / script).read_text(encoding="utf-8"))
    except Exception:
        return False
    has_test_func = any(isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
                        for n in tree.body)
    # standalone script ของโปรเจกต์จบตัวเองที่ระดับโมดูลด้วย sys.exit / raise SystemExit
    calls_exit = any(_exits_now(n) for n in _module_level_nodes(tree))
    return has_test_func and not calls_exit


def _command_for(script):
    """คำสั่งรันเทสต์หนึ่งไฟล์ — pytest-style ต้องผ่าน pytest ไม่ใช่รันตรง"""
    if _is_pytest_style(script):
        return [sys.executable, "-m", "pytest", script, "-q", "-p", "no:cacheprovider",
                "--no-header", "-o", "addopts="]
    return [sys.executable, script]


def _subprocess_env():
    """env ของโปรเซสเทสต์ — บังคับ UTF-8 เพราะทุกเทสต์ print ภาษาไทย

    ถ้าไม่ตั้ง เครื่องที่ใช้ codepage อื่น (cp1252 บน Windows, LANG=C บน Linux)
    จะล้มด้วย UnicodeEncodeError ทั้งที่โค้ดไม่ผิด — CI ตั้งสองตัวนี้ไว้ใน
    workflow และ launcher ของ install.ps1 ก็ตั้ง จึงต้องตั้งที่นี่ให้ครบทุกทางเข้า
    """
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_one(script):
    """รันสคริปต์หนึ่งไฟล์ในโปรเซสของตัวเอง คืน (ชื่อ, exit code, output, วินาที)"""
    import time
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            _command_for(script),
            cwd=str(_ROOT),
            env=_subprocess_env(),
            input="",  # stdin เป็น pipe ปิด (ไม่ใช่ tty) — ให้เทสต์เดินเส้นทาง non-interactive
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_timeout(),
        )
        code = proc.returncode
        out = (proc.stdout or "")
        if proc.stderr:
            out += "\n[stderr]\n" + proc.stderr[-1500:]
    except subprocess.TimeoutExpired as e:
        code = -9
        out = (e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode(
            "utf-8", "replace")) or ""
        out += f"\n[หมดเวลา {_timeout()}s — ฆ่าโปรเซสแล้ว]"
    return script, code, out, time.perf_counter() - t0


@pytest.fixture(scope="session")
def _suite_results():
    """รันทุกสคริปต์ขนานครั้งเดียวต่อ session (แต่ละไฟล์ยังอยู่คนละโปรเซส)"""
    with _cf.ThreadPoolExecutor(max_workers=_jobs()) as ex:
        results = list(ex.map(_run_one, _SCRIPTS))
    return {r[0]: r for r in results}


@pytest.mark.parametrize("script", _SCRIPTS)
def test_standalone_suite(script, _suite_results):
    """pass เมื่อสคริปต์นั้น exit code = 0 (ขนานแล้ว อ่านผลจากรอบเดียว)"""
    _name, code, out, secs = _suite_results[script]
    assert code == 0, f"{script} ล้มเหลว (exit={code}, {secs:.1f}s)\n{out[-3000:]}"
