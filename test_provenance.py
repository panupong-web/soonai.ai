# -*- coding: utf-8 -*-
"""เทสต์ provenance ของการ patch: `soonai.X = ...` ต้องไปถึงโมดูลที่นิยาม X เอง ด้วย

ทำไมต้องมี: หลังลด bind (เหลือแค่ skills) โมดูล symbols/project/usage/shell ไม่อยู่
ใน propagate list แล้ว — แต่เทสต์และโค้ดภายนอกยัง patch ผ่าน `S.X` ถ้าไม่ส่งถึง
namespace ของโมดูล โค้ด *ภายใน* โมดูลจะยังใช้ค่าเดิม (เคยเกิดจริง: patch
`S._pricing_cached` แล้ว `estimate_cost` ยังคืน 0 เพราะอ่านค่าเดิมในโมดูลตัวเอง)

กลไกที่ทดสอบ: `runtime.register_owners()` จด "เจ้าของชื่อ" ตอน import ด้วย identity
(ไม่เดาจากชื่อ) แล้ว `propagate()` เขียนค่าใหม่ลงโมดูลเจ้าของด้วย

ทดสอบกับ **ทุกชื่อในทะเบียน** (ไล่จริงทั้งหมด ไม่ใช่สุ่มตัวอย่าง) + กันเขียนเกินขอบเขต
"""
import sys
import types

sys.path.insert(0, "shared")
sys.modules.setdefault("mcp", types.ModuleType("mcp"))

import soonai as S            # noqa: E402
import runtime as R           # noqa: E402

FAILS = []
MIGRATED = {"symbols", "project", "usage", "shell", "skills", "ui_render"}


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------- 1) ทะเบียนเจ้าของชื่อ ----------
owners = R.owner_map()
check("ทะเบียนเจ้าของชื่อถูกจดหลัง import (ไม่ว่าง)", len(owners) > 0, len(owners))
check("ทะเบียนครอบคลุมอย่างน้อย 100 ชื่อ", len(owners) >= 100, len(owners))

_by_mod = {}
for _n, _mods in owners.items():
    for _m in _mods:
        _by_mod.setdefault(_m.__name__, []).append(_n)
check("เจ้าของชื่อทั้งหมดคือโมดูลที่ย้ายออกมา",
      set(_by_mod) <= MIGRATED, sorted(_by_mod))
for _mod in sorted(MIGRATED):
    check(f"{_mod} มีชื่อที่จดเป็นเจ้าของ ≥ 5 ชื่อ",
          len(_by_mod.get(_mod, [])) >= 5, len(_by_mod.get(_mod, [])))

_bad_owner = [n for n, ms in owners.items()
              if any(m.__dict__.get(n) is not getattr(S, n, object()) for m in ms)]
check("ทุกชื่อในทะเบียน: เจ้าของถือวัตถุเดียวกับ soonai (identity)",
      not _bad_owner, _bad_owner[:8])

_missing = [n for n in owners if n not in S.__dict__]
check("ทุกชื่อในทะเบียน re-export มาถึง soonai จริง", not _missing, _missing[:8])


# ---------- 2) patch ไล่ทุกชื่อ (พร้อมคืนค่าให้ครบ ไม่ให้รั่ว) ----------
_orig = {n: S.__dict__[n] for n in owners}
_patched = _is_module = _not_reached = 0
_details = []
try:
    for _name, _mods in sorted(owners.items()):
        _value = _orig[_name]
        if isinstance(_value, types.ModuleType):
            _is_module += 1          # ข้าม module object (ไม่ใช่ seam ที่ใคร patch)
            continue
        _sentinel = object()
        setattr(S, _name, _sentinel)
        _patched += 1
        _hit = [m.__name__ for m in _mods if m.__dict__.get(_name) is _sentinel]
        if len(_hit) != len(_mods) or getattr(R, _name, None) is not _sentinel:
            _not_reached += 1
            _details.append((_name, [m.__name__ for m in _mods], _hit))
        # คืนค่าทันทีในลูป → ไม่มีช่วงที่ทั้งโปรเซสเห็นค่าปลอม
        setattr(S, _name, _value)
finally:
    for _name, _value in _orig.items():          # ตาข่ายกันค่าเพี้ยนถ้ามีข้อยกเว้น
        setattr(S, _name, _value)

check("patch ไล่ครบทุกชื่อในทะเบียน", _patched >= 100, _patched)
check("ทุกชื่อที่ patch ไปถึงโมดูลเจ้าของ + runtime",
      _not_reached == 0, f"{_not_reached} ตัว เช่น {_details[:5]}")

_leak = [n for n, v in _orig.items() if S.__dict__.get(n) is not v or getattr(R, n, None) is not v]
check("คืนค่าเดิมครบทุกชื่อหลังทดสอบ (ไม่รั่ว)", not _leak, _leak[:8])
print(f"[ข้าม module object {_is_module} ชื่อ · patch จริง {_patched} ชื่อ]")


# ---------- 3) กันเขียนเกินขอบเขต (over-propagation) ----------
# ชื่อที่เป็นของ soonai เอง (ไม่มีเจ้าของ) ต้องไม่ถูกฉีดเข้าโมดูลที่ปลด bind แล้ว
_UNBOUND = (S._symbols_mod, S._project_mod, S._usage_mod, S._shell_mod)
_s_only = [n for n in S.__dict__
           if not n.startswith("__") and not R.owners(n)
           and callable(S.__dict__[n]) and not isinstance(S.__dict__[n], types.ModuleType)
           and not any(n in m.__dict__ for m in _UNBOUND)]
check("มีชื่อที่เป็นของ soonai เองให้ทดสอบ (เช่น send_messages)", len(_s_only) >= 5, _s_only[:8])

_probe = _s_only[0]
_probe_val = S.__dict__[_probe]
_sentinel = object()
setattr(S, _probe, _sentinel)
_leaked_into = [m.__name__ for m in _UNBOUND if m.__dict__.get(_probe) is _sentinel]
setattr(S, _probe, _probe_val)
check(f"ชื่อของ soonai เอง ({_probe}) ไม่ถูกเขียนเข้าโมดูลที่ปลด bind",
      not _leaked_into, _leaked_into)
check(f"คืนค่า {_probe} เรียบร้อย", S.__dict__[_probe] is _probe_val)

# ไม่เหลือโมดูลที่ถูก bind → seam ทุกตัวต้องถึงมือโมดูลทาง runtime (ไม่ใช่การฉีดชื่อ)
check("ไม่มีโมดูลที่ถูก bind แล้ว", R.bound_modules() == [],
      [m.__name__ for m in R.bound_modules()])
_send = S.__dict__["send_messages"]
sentinel2 = object()
S.send_messages = sentinel2
check("patch seam (send_messages) → runtime เห็น และ skills อ่านผ่าน runtime",
      getattr(R, "send_messages", None) is sentinel2
      and S._skills_mod.R.send_messages is sentinel2)
setattr(S, "send_messages", _send)
check("คืนค่า send_messages เรียบร้อย",
      S.__dict__["send_messages"] is _send and R.send_messages is _send)

# skills ต้องยังเป็นเจ้าของชื่อของตัวเอง (patch ถึงโค้ดภายในได้โดยไม่ต้อง bind)
check("skills เป็นเจ้าของชื่อของตัวเอง (patch ถึงภายใน)",
      S._skills_mod in R.owners("scan_skills"), R.owners("scan_skills"))

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL PROVENANCE TESTS PASSED")
