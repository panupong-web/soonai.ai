# -*- coding: utf-8 -*-
"""Regression: config/keys/team ต้องอยู่นอก source tree (DATA_DIR) + migrate จากร่างเก่าได้

เหตุผลที่ย้าย: แต่เดิม shared/config.json · shared/keys.json · shared/team.json อยู่ใน
โฟลเดอร์โค้ดที่ git track ผลคือ (1) ค่าส่วนตัวของผู้พัฒนาถูก commit (2) installer
คัดลอก config ของผู้พัฒนาไปให้ผู้ใช้ทุกคน (3) config ในเครื่องกับใน repo เป็นคนละไฟล์กัน
"""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

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


# ---------- 1) ตำแหน่งไฟล์ชี้อยู่ DATA_DIR ไม่ใช่ source tree
check("DATA_DIR ไม่ได้อยู่ในโฟลเดอร์โค้ด",
      not Path(R.DATA_DIR).is_relative_to(R.BASE_DIR), R.DATA_DIR)
for label, path in (("CONFIG_FILE", R.CONFIG_FILE), ("KEYS_FILE", R.KEYS_FILE),
                    ("TEAM_FILE", R.TEAM_FILE)):
    check(f"{label} อยู่ใต้ DATA_DIR", Path(path).parent == Path(R.DATA_DIR), path)
check("SHARED_DIR ยังอยู่ใน repo (เป็นที่อยู่ของ *.default.json)",
      Path(R.SHARED_DIR).is_relative_to(R.BASE_DIR))

if os.name == "nt":
    _base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    check("Windows: DATA_DIR = %LOCALAPPDATA%\\SoonAI",
          Path(R.DATA_DIR) == Path(_base) / "SoonAI", R.DATA_DIR)
else:
    check("POSIX: DATA_DIR = ~/.soonai", Path(R.DATA_DIR) == Path.home() / ".soonai",
          R.DATA_DIR)

# ---------- 2) *.default.json ต้องไม่มีค่าส่วนตัวติดมา
for name in ("config.default.json", "team.default.json"):
    p = Path(R.SHARED_DIR) / name
    check(f"{name} มีอยู่ (ใช้เป็นต้นแบบตอนรันครั้งแรก)", p.is_file(), p)

_default_cfg = json.loads((Path(R.SHARED_DIR) / "config.default.json").read_text("utf-8"))
check("config.default.json ไม่มี custom_providers ของผู้พัฒนา",
      not _default_cfg.get("custom_providers"), _default_cfg.get("custom_providers"))
_SECRETISH = re.compile(r"(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|xai-[A-Za-z0-9]{8,}"
                        r"|AIza[A-Za-z0-9_\-]{20,}|Bearer\s+[A-Za-z0-9._\-]{16,})", re.I)
_blob = json.dumps(_default_cfg, ensure_ascii=False)
check("config.default.json ไม่มีรูปทรง API key", not _SECRETISH.search(_blob),
      (_SECRETISH.search(_blob) or [None])[0])
check("config.default.json ไม่มี key_env ชี้ env ส่วนตัว",
      not any("key_env" in json.dumps(v) for v in _default_cfg.values()
              if isinstance(v, (dict, list))))

# ---------- 3) ensure_user_files(): ย้ายร่างเก่า ไม่ทับของที่มี idempotent
_orig = {n: getattr(R, n) for n in
         ("DATA_DIR", "CONFIG_FILE", "KEYS_FILE", "TEAM_FILE", "LEGACY_CONFIG_FILE",
          "LEGACY_KEYS_FILE", "LEGACY_TEAM_FILE", "CONFIG_DEFAULT_FILE",
          "TEAM_DEFAULT_FILE", "LEGACY_FILES")}
_work = Path(tempfile.mkdtemp(prefix="soonai-mig-"))
try:
    data = _work / "data"
    shared = _work / "shared"
    shared.mkdir()
    R.DATA_DIR = data
    R.CONFIG_FILE = data / "config.json"
    R.KEYS_FILE = data / "keys.json"
    R.TEAM_FILE = data / "team.json"
    R.LEGACY_CONFIG_FILE = shared / "config.json"
    R.LEGACY_KEYS_FILE = shared / "keys.json"
    R.LEGACY_TEAM_FILE = shared / "team.json"
    R.CONFIG_DEFAULT_FILE = shared / "config.default.json"
    R.TEAM_DEFAULT_FILE = shared / "team.default.json"
    R.LEGACY_FILES = ((R.CONFIG_FILE, R.LEGACY_CONFIG_FILE, R.CONFIG_DEFAULT_FILE),
                      (R.KEYS_FILE, R.LEGACY_KEYS_FILE, None),
                      (R.TEAM_FILE, R.LEGACY_TEAM_FILE, R.TEAM_DEFAULT_FILE))
    R._USER_FILES_MIGRATED["done"] = False

    # กรณีที่ไม่มีอะไรเลย: ต้องไม่สร้างไฟล์เปล่า และไม่พัง
    check("ไม่มีร่างเก่า/ไม่มี default = ไม่สร้างอะไร", R.ensure_user_files() == 0)
    check("DATA_DIR ถูกสร้างไว้รองรับ", data.is_dir())

    # ลำดับความสำคัญ: ร่างเก่า (ของเครื่องนี้) ชนะ default (ของ repo)
    R.LEGACY_CONFIG_FILE.write_text('{"provider":"legacy"}', encoding="utf-8")
    R.CONFIG_DEFAULT_FILE.write_text('{"provider":"default"}', encoding="utf-8")
    R.LEGACY_KEYS_FILE.write_text('{"openrouter":"sk-legacy"}', encoding="utf-8")
    R._USER_FILES_MIGRATED["done"] = False
    made = R.ensure_user_files()
    check("ย้าย config + keys จากร่างเก่า", made == 2, made)
    check("config ที่ย้ายมาคือร่างเก่า ไม่ใช่ default",
          json.loads(R.CONFIG_FILE.read_text("utf-8"))["provider"] == "legacy")
    check("keys ถูกย้ายมาครบ", "sk-legacy" in R.KEYS_FILE.read_text("utf-8"))
    check("ไม่มี default ของ keys → ไม่สร้าง team.json มั่ว",
          not R.TEAM_FILE.exists() or R.TEAM_FILE.read_text("utf-8"))

    # default ถูกใช้เมื่อไม่มีร่างเก่า
    R.TEAM_DEFAULT_FILE.write_text('{"staff":[]}', encoding="utf-8")
    R._USER_FILES_MIGRATED["done"] = False
    R.ensure_user_files()
    check("team.json สร้างจาก team.default.json",
          json.loads(R.TEAM_FILE.read_text("utf-8")) == {"staff": []})

    # idempotent + ห้ามทับของที่มีอยู่ (ของผู้ใช้)
    R.CONFIG_FILE.write_text('{"provider":"mine"}', encoding="utf-8")
    R._USER_FILES_MIGRATED["done"] = False
    check("รอบซ้ำ: ไม่มีอะไรต้องทำ", R.ensure_user_files() == 0)
    check("ไม่ทับ config ที่ผู้ใช้แก้เอง",
          json.loads(R.CONFIG_FILE.read_text("utf-8"))["provider"] == "mine")

    # ธงสำเร็จต้องไม่ค้างเมื่อสร้าง DATA_DIR ไม่ได้ (รอบหน้าต้องลองใหม่)
    R._USER_FILES_MIGRATED["done"] = False
    R.DATA_DIR = _work / "blocked" / "data"
    (_work / "blocked").write_text("not a dir", encoding="utf-8")   # mkdir จะชนไฟล์
    check("DATA_DIR สร้างไม่ได้ = คืน 0", R.ensure_user_files() == 0)
    check("ไม่ตั้งธงสำเร็จเมื่อ migrate ไม่รอด",
          R._USER_FILES_MIGRATED["done"] is False)

    if os.name == "nt":
        print("skip: สิทธิ์ 0600 ของ keys.json (Windows มีแค่ read-only bit)")
    else:
        R.DATA_DIR = data
        R._USER_FILES_MIGRATED["done"] = False
        R.KEYS_FILE.unlink(missing_ok=True)
        R.ensure_user_files()
        check("keys.json ได้สิทธิ์ 0600",
              (os.stat(R.KEYS_FILE).st_mode & 0o777) == 0o600,
              oct(os.stat(R.KEYS_FILE).st_mode & 0o777))
finally:
    for n, v in _orig.items():
        setattr(R, n, v)
    R._USER_FILES_MIGRATED["done"] = True      # ของจริง migrate ไปแล้วตอน import
    shutil.rmtree(_work, ignore_errors=True)

# ---------- 4) โมดูลย่อยต้องเห็น path ชุดเดียวกัน (ไม่มีการ hardcode shared/ เหลืออยู่)
for label in ("CONFIG_FILE", "KEYS_FILE", "TEAM_FILE", "DATA_DIR", "SHARED_DIR"):
    check(f"soonai.{label} ตรงกับ runtime.{label}",
          getattr(S, label) == getattr(R, label),
          (getattr(S, label), getattr(R, label)))

# ---------- 5) ไม่มีโค้ดเหลือที่ hardcode path กลับไป shared/ (ตรวจจาก AST
#               จึงข้าม comment กับ docstring ที่แค่ "ยกตัวอย่างชื่อไฟล์" ให้เอง)
_HARDCODED = re.compile(r"shared[/\\](config|keys|team)\.json$")


def _string_literals(path):
    """สตริง literal ทุกก้อนในไฟล์ (ไม่รวม docstring — ไม่ใช่พาธที่ใช้จริง)"""
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None and node.body:
                first = node.body[0]
                if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                        and first.value.value == doc):
                    docstrings.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


_hits = []
for p in sorted(Path(".").rglob("*.py")):
    parts = set(p.parts)
    if "__pycache__" in parts or ".venv" in parts or ".git" in parts:
        continue
    if p.name in ("depgraph.py", "conftest.py") or p.name.startswith("test_"):
        continue
    for lit in _string_literals(p):
        if _HARDCODED.search(lit.replace("\\", "/")):
            _hits.append(f"{p}: {lit!r}")
check("ไม่มีโค้ด hardcode shared/config|keys|team.json เหลืออยู่", not _hits, _hits)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)
print("ALL DATA-DIR TESTS PASSED")
