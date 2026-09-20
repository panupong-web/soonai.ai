# -*- coding: utf-8 -*-
"""Regression: Step 0 การแยกโมดูล (runtime seam + facade)
- soonai ผูก state เข้า runtime เป็น object เดียวกัน (identity)
- `soonai.X = ...` จากภายนอก mirror ลง runtime (เทสต์เดิมจึงยังใช้ได้)
- อ่าน attribute ที่มีแค่ใน runtime ได้ (fallback) · ที่ไม่มีจริง = AttributeError
ไม่แตะไฟล์/เน็ต
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import runtime as R  # noqa: E402

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------- 1) ผูกกันแล้ว
check("soonai อ้าง runtime", getattr(S, "_RT", None) is R)
check("โมดูล soonai ใช้ facade class", type(S).__name__ == "_SoonaiModule", type(S).__name__)

# ---------- 1b) โมดูลที่แยกออกมา โหลด + identity ครบ
MODULES = {"symbols": "_symbols_mod", "project": "_project_mod", "usage": "_usage_mod",
           "shell": "_shell_mod", "skills": "_skills_mod",
           "ui_render": "_ui_render_mod"}
for _mod, _var in MODULES.items():
    _m = getattr(S, _var, None)
    check(f"โหลดโมดูล {_mod}", _m is not None and _m.__name__ == _mod)

# หลังลด bind ครบทุกโมดูล: ไม่มีอะไรถูก bind อีก ทุกโมดูลอ่าน seam ผ่าน `import runtime`
# (depgraph bind_refs = 0) → ไม่มีการฉีดชื่อใด ๆ เข้า namespace ของโมดูลเลย
_bound = set(R.bound_modules())
check("ไม่มีโมดูลที่ต้อง bind แล้ว (bind_refs = 0 ทุกตัว)",
      _bound == set(), sorted(m.__name__ for m in _bound))
check("แต่ยังจดเจ้าของชื่อให้ propagate ถึง (รวม skills)",
      all(R.owners(n) for n in ("scan_skills", "skills_dirs", "outline_text",
                                "run_command_safe", "usage_line")),
      {n: [m.__name__ for m in R.owners(n)]
       for n in ("scan_skills", "outline_text", "run_command_safe", "usage_line")})

# แต่องค์ประกอบที่ re-export มายังต้อง patch ได้ถึงโค้ดภายในโมดูล (provenance)
check("provenance: symbols โหลดมาแล้วจดเจ้าของชื่อ",
      S._symbols_mod in R.owners("outline_text") and
      S._project_mod in R.owners("iter_project_files"),
      [R.owners("outline_text"), R.owners("iter_project_files")])
for _name, _owner in (("_pricing_cached", S._usage_mod),
                      ("run_command_safe", S._shell_mod)):
    check(f"provenance: {_name} เป็นของ {_owner.__name__}",
          _owner in R.owners(_name), R.owners(_name))
check("identity outline_text", S.outline_text is S._symbols_mod.outline_text)
check("identity iter_project_files", S.iter_project_files is S._project_mod.iter_project_files)
check("identity detect_test_command", S.detect_test_command is S._shell_mod.detect_test_command)
check("identity usage_line", S.usage_line is S._usage_mod.usage_line)
check("identity skills_dirs", S.skills_dirs is S._skills_mod.skills_dirs)
check("identity neo_table", S.neo_table is S._ui_render_mod.neo_table)
check("identity status_line", S.status_line is S._ui_render_mod.status_line)
check("identity build_input_bar", S.build_input_bar is S._ui_render_mod.build_input_bar)

# ---------- 2) state เป็น object เดียวกัน (identity)
for name in ("_TEST_CMD_CACHE", "_SHELL_OVERRIDE", "_SKILL_STATE", "USAGE",
             "SESSION_TOOLS", "_COSMOS_MODE", "_MODEL_DEAD", "_QUOTA_DEAD"):
    check(f"identity: {name}", getattr(S, name) is getattr(R, name, object()))

# ---------- 3) การ mutate แบบ in-place เห็นทั้งสองฝั่ง
S.USAGE["calls"] = 7
check("mutate in-place เห็นทั้งคู่", R.USAGE["calls"] == 7 and S.USAGE["calls"] == 7)
S.USAGE["calls"] = 0

# ---------- 4) facade mirror เมื่อเซ็ตจากภายนอก (แบบที่เทสต์เดิมทำ)
_orig = S.__dict__.get("console")
_probe = object()
S.console = _probe
check("set ภายนอก: โมดูลเห็น", S.__dict__.get("console") is _probe)
check("set ภายนอก: runtime เห็น (mirror)", getattr(R, "console", None) is _probe)
S.console = _orig

S._step0_probe_scalar = 123
check("mirror scalar", R._step0_probe_scalar == 123 and S._step0_probe_scalar == 123)

# ---------- 5) fallback อ่านจาก runtime + missing = AttributeError
R._step0_only_in_runtime = "hello"
check("fallback อ่านค่าที่มีแค่ใน runtime", S._step0_only_in_runtime == "hello")
check("attribute ที่ไม่มีจริง → AttributeError", not hasattr(S, "_definitely_not_here_xyz"))

# ---------- 6) โมดูลที่ลด bind แล้ว: ทุก R.<name> ต้องมีจริงบน runtime
# (attribute access พังตอนเรียกเท่านั้น — static scan คือด่านจับล่วงหน้า)
import re as _re  # noqa: E402 - ต้อง sys.path.insert ก่อน
import os as _os  # noqa: E402 - ต้อง sys.path.insert ก่อน
_MIGRATED_SRC = ["shell.py", "usage.py", "symbols.py", "skills.py", "ui_render.py"]
# ทุกโมดูลที่ย้ายต้องอ่าน seam ผ่าน runtime (ไม่มี bind ช่วยอีกแล้ว)
_here = _os.path.dirname(_os.path.abspath(__file__))
_missing = {}
_refs = {}
for _f in _MIGRATED_SRC:
    _p = _os.path.join(_here, "shared", _f)
    if not _os.path.exists(_p):
        continue
    _s = open(_p, encoding="utf-8").read()
    _names = sorted(set(_re.findall(r"\bR\.([A-Za-z_][A-Za-z0-9_]*)", _s)))
    _refs[_f] = _names
    _miss = [x for x in _names if not hasattr(R, x)]
    if _miss:
        _missing[_f] = _miss
check("ทุก R.<name> ในโมดูลที่ลด bind มีจริงบน runtime", not _missing, _missing)

# ชื่อที่ทั้ง runtime และ soonai มี ต้องเป็น object เดียวกัน (seam เดียวจริง)
_shared_names = sorted({x for v in _refs.values() for x in v if hasattr(S, x)})
_mismatch = [x for x in _shared_names if getattr(R, x) is not getattr(S, x)]
check("R.<name> ที่เป็น seam ตรงกับ soonai (identity)", not _mismatch, _mismatch)

# ---------- 6b) regression: patch "ตัวช่วยภายในโมดูล" ต้องเห็นผล (เคยพังตอนปลด bind)
# เดิม test_usage patch S._pricing_cached แล้วได้ผล เพราะ propagate เขียนทับให้โมดูล
_orig_pricing = S._pricing_cached
S._pricing_cached = lambda provider: {"m": {"prompt": 1e-6, "completion": 1e-6}}
_c = S.estimate_cost("openrouter", "m", 1000, 500)
check("patch _pricing_cached → โค้ดภายใน usage เห็น (provenance)",
      abs(_c - 0.0015) < 1e-12, _c)
check("patch ลงถึง namespace ของโมดูลจริง", S._usage_mod._pricing_cached is S._pricing_cached)
S._pricing_cached = _orig_pricing
check("คืนค่าเดิมแล้วเรียกใช้ได้", S._usage_mod._pricing_cached is _orig_pricing)

_orig_safe = S.run_command_safe
S.run_command_safe = lambda *a, **k: (0, "stub", "")
check("patch ตัวช่วยของ shell → ถึง namespace โมดูล",
      S._shell_mod.run_command_safe is S.run_command_safe)
S.run_command_safe = _orig_safe

# ---------- 7) เก็บกวาด
for _n in ("_step0_probe_scalar", "_step0_only_in_runtime"):
    S.__dict__.pop(_n, None)
    R.__dict__.pop(_n, None)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL RUNTIME SEAM TESTS PASSED")
