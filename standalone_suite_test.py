# -*- coding: utf-8 -*-
"""ทางเข้า `python -m pytest` ของโปรเจกต์นี้

เทสต์จริงอยู่ในไฟล์ test_*.py แบบ standalone (รันโค้ดระดับโมดูล + sys.exit เอง)
ไฟล์นี้รันแต่ละไฟล์เป็น subprocess **แยกโปรเซส** (คงการแยก env/global ที่แต่ละ
เทสต์ต้องพึ่ง) แล้วรัน **ขนานกัน** เพื่อลดเวลา (ดูเหตุผลการแยกที่ conftest.py)
"""
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


def _run_one(script):
    """รันสคริปต์หนึ่งไฟล์ในโปรเซสของตัวเอง คืน (ชื่อ, exit code, output, วินาที)"""
    import time
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, script],
            cwd=str(_ROOT),
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
