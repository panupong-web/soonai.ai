# -*- coding: utf-8 -*-
"""สะพานเชื่อมให้ `python -m pytest` ใช้ได้กับชุดเทสต์ของโปรเจกต์นี้

เทสต์ทุกไฟล์ (test_*.py) เป็น "standalone script" ที่รันโค้ดระดับโมดูลและเรียก
sys.exit() เอง — ไม่ใช่ฟังก์ชัน test_* ที่ pytest เก็บได้ ถ้าปล่อยให้ pytest
import ตอน collect จะล่มด้วย INTERNALERROR (SystemExit ระหว่าง collection)

จึงบอก pytest ว่า "อย่า import ไฟล์พวกนี้ตรง ๆ" แล้วรันแต่ละไฟล์เป็น subprocess
แยกโปรเซสแทน — ตรงกับวิธีใช้จริง (python test_x.py) และคงการแยก env/global
ที่แต่ละเทสต์ต้องพึ่งพาไว้
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# ไฟล์เทสต์แบบ standalone — ห้ามให้ pytest import/collect เอง (จะ SystemExit ทิ้ง collection)
collect_ignore = sorted(p.name for p in _ROOT.glob("test_*.py"))
