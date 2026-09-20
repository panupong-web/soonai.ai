# -*- coding: utf-8 -*-
"""Regression: Step 2 แยกโมดูล skills ออกจาก soonai.py
- โหลด shared/skills.py จริง (ไม่ใช่โฟลเดอร์ข้อมูล shared/skills/)
- ทุกชื่อที่ย้ายไป ยัง re-export จาก soonai แบบ "object เดียวกัน" (identity)
- ชื่อภายนอกที่โค้ดเดิมอ้าง (console/load_config/DATA_DIR/SKILL_STATE_FILE/...)
  ถูก bind เข้าโมดูลจริง + การ patch จากภายนอก propagate ถึงโมดูล
- runtime.bind_module ลงทะเบียนโมดูลไว้ (ให้ depgraph/propagate เห็น)
ไม่แตะไฟล์/เน็ต (ใช้ _SKILLS_TEST_ROOTS เป็นโฟลเดอร์จำลอง แล้วคืนค่า)
"""
import ast
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

import skills as SK  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------- 1) โหลดถูกไฟล์จริง ----------
check("skills เป็นโมดูลไฟล์ shared/skills.py",
      Path(SK.__file__).name == "skills.py"
      and Path(SK.__file__).parent.name == "shared",
      SK.__file__)
check("soonai อ้างโมดูล skills", getattr(S, "_skills_mod", None) is SK)
check("skills ปลด bind แล้ว (อ่าน seam ผ่าน runtime เอง)",
      SK not in R.bound_modules() and not R.bound_modules(),
      [m.__name__ for m in R.bound_modules()])
check("runtime จด skills เป็นเจ้าของชื่อ (propagate ถึง)",
      SK in R.owners("scan_skills") and SK in R.owners("skills_dirs"),
      [R.owners("scan_skills"), R.owners("skills_dirs")])


# ---------- 2) helper: ชื่อระดับบนของโมดูล skills ----------
def module_names(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.append(t.id)
    return out


moved = module_names(SK.__file__)
check("ได้รายชื่อที่ย้ายมาเยอะพอ", len(moved) >= 60, len(moved))
check("SKILL_STATE_FILE ไม่ย้ายไปโมดูล (คงอยู่ใน soonai)",
      "SKILL_STATE_FILE" not in moved)

# ---------- 3) re-export ครบ + identity (object เดียวกัน) ----------
missing = [n for n in moved if not hasattr(S, n)]
check("re-export ทุกชื่อจาก soonai", not missing, missing)
not_same = [n for n in moved if getattr(S, n, None) is not getattr(SK, n, None)]
check("identity ทุกชื่อ (ไม่ใช่สำเนา)", not not_same, not_same)

for name in ("SKILL_CATALOG", "SKILL_DIRNAME", "_SKILL_STATE", "_SKILL_CARRYOVER",
             "_SKILL_AUTOSUGGEST", "SKILL_DECLINE_LIMIT", "SKILL_FREQUENT_USE",
             "_SKILLS_TEST_ROOTS"):
    check(f"identity: {name}", getattr(S, name) is getattr(SK, name, object()))

for fn in ("skills_dirs", "scan_skills", "install_skill", "search_catalog",
           "ai_suggest_skills", "autosuggest_skill", "carryover_skills",
           "cmd_skills", "skills_find_flow"):
    check(f"identity fn: {fn}", getattr(S, fn) is getattr(SK, fn, object()))

# ---------- 4) seam: อ่านผ่าน runtime (attribute access) แทนการ bind ----------
check("โมดูล skills import runtime เดียวกัน", SK.R is R)
check("โมดูล skills import โมดูลพี่น้องตรง ๆ",
      SK._symbols.__name__ == "symbols" and SK._project.__name__ == "project"
      and SK._shell.__name__ == "shell",
      [SK._symbols.__name__, SK._project.__name__, SK._shell.__name__])
for name in ("console", "load_config", "load_json", "save_json", "neo_table",
             "send_messages", "workspace_root", "fix_mojibake", "_http_session",
             "BASE_DIR", "SHARED_DIR", "DATA_DIR", "SKILL_STATE_FILE", "agent_tools"):
    check(f"seam {name} อ่านผ่าน runtime",
          getattr(R, name, object()) is getattr(S, name, object()))
check("seam ไม่ถูก freeze ลง namespace ของโมดูล (ไม่มีสำเนาเก่า)",
      not ({"load_config", "console", "send_messages"} & set(SK.__dict__)),
      sorted({"load_config", "console", "send_messages"} & set(SK.__dict__)))
check("ใช้ไลบรารีภายนอกที่ import เอง (Panel/Prompt/requests)",
      all(n in SK.__dict__ for n in ("Panel", "Prompt", "requests")))
check("SKILL_STATE_FILE ชี้ที่เดียวกับ soonai",
      SK.R.SKILL_STATE_FILE == S.SKILL_STATE_FILE)

# ---------- 5) propagate: patch จากภายนอก (แบบที่เทสต์เดิมทำ) ----------
_orig_roots = S._SKILLS_TEST_ROOTS
try:
    probe_roots = [str(Path.cwd() / "shared" / "skills")]
    S._SKILLS_TEST_ROOTS = probe_roots
    check("propagate _SKILLS_TEST_ROOTS → โมดูล", SK._SKILLS_TEST_ROOTS == probe_roots)
    check("skills_dirs() ใช้ hook ที่ patch (อ่านจากโมดูล)",
          [str(p) for p in SK.skills_dirs()] == probe_roots,
          [str(p) for p in SK.skills_dirs()])
finally:
    S._SKILLS_TEST_ROOTS = _orig_roots

_orig_console = S.console
try:
    probe = object()
    S.console = probe
    check("patch console → runtime เห็น (โมดูลอ่านต่อจาก runtime)",
          R.console is probe and SK.R.console is probe)
finally:
    S.console = _orig_console
check("คืนค่า console แล้ว", R.console is _orig_console)

# ---------- 6) mutate in-place เห็นทั้งสองฝั่ง ----------
_cat_backup = dict(S.SKILL_CATALOG)
try:
    S.SKILL_CATALOG["_probe_"] = ("คำอธิบาย", "เนื้อหา")
    check("mutate SKILL_CATALOG เห็นทั้งคู่",
          SK.SKILL_CATALOG.get("_probe_") == ("คำอธิบาย", "เนื้อหา"))
finally:
    S.SKILL_CATALOG.clear()
    S.SKILL_CATALOG.update(_cat_backup)
check("SKILL_CATALOG กลับสภาพเดิม", "_probe_" not in SK.SKILL_CATALOG)

S._SKILL_STATE["data"] = None
check("mutate _SKILL_STATE เห็นทั้งคู่", SK._SKILL_STATE["data"] is None)

# ---------- 7) บล็อกสกิลเดิมใน soonai ถูกลบจริง ----------
_src = Path("soonai.py").read_text(encoding="utf-8", errors="replace")
check("soonai.py ไม่มีเนื้อใน skills ค้าง (def skills_dirs)",
      "def skills_dirs(" not in _src)
check("soonai.py ไม่มี SKILL_CATALOG ตัวจริงค้าง (literal 116 บรรทัด)",
      "SKILL_CATALOG = {" not in _src)
check("soonai.py ยังมี SKILL_STATE_FILE (พึ่ง DATA_DIR)",
      "SKILL_STATE_FILE = (" in _src)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL SKILLS MODULE TESTS PASSED")
