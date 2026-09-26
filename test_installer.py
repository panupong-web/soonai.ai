# -*- coding: utf-8 -*-
"""Regression: installer ต้องไม่แพร่งพรายความลับ/แคชของผู้พัฒนา และไม่อ้างของที่ลบไปแล้ว

ที่พบตอนตรวจ:
- install.ps1/install.sh คัดลอก shared/ ทั้งโฟลเดอร์แบบ recursive → กวาด keys.json,
  mcp.json, .models_cache.json (88KB), .machine_id, __pycache__ ติดไปด้วย
  ทั้งที่ README เขียนว่า "does not copy secrets or session data"
- ทั้งสองสคริปต์ยังคัดลอก soonai_custom.py กับโฟลเดอร์ apps/ packages/ ที่ลบไปแล้ว
- launcher ของ install.sh ไม่ตั้ง PYTHONUTF8/PYTHONIOENCODING (install.ps1 ตั้ง)
  → บนเครื่องที่ locale ไม่ใช่ UTF-8 จะ UnicodeEncodeError ตั้งแต่บรรทัดแรก
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

ROOT = Path(__file__).resolve().parent
FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


def skip(name, why):
    print(f"skip: {name} ({why})")


PS1 = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")
SH = (ROOT / "install.sh").read_text(encoding="utf-8")

# ── 1) ต้องไม่อ้างไฟล์/โฟลเดอร์ที่ลบไปแล้ว ──────────────────────────────────
DEAD = ("soonai_custom.py", "cli_smooth.py", "core_utils", "eval_ambiguous.py")
for name in DEAD:
    check(f"install.ps1 ไม่อ้างของตาย: {name}", name not in PS1)
    check(f"install.sh ไม่อ้างของตาย: {name}", name not in SH)
# apps/packages เป็นชื่อสามัญ — ตรวจเฉพาะทรงที่ installer ใช้ไล่คัดลอกโฟลเดอร์
check("install.ps1 ไม่คัดลอก apps/packages",
      '"shared", "apps", "packages"' not in PS1 and "'apps'" not in PS1)
check("install.sh ไม่คัดลอก apps/packages", "shared apps packages" not in SH)

# ── 2) ต้องมีกฎเว้นความลับ/แคช ครบทุกชื่อ ────────────────────────────────────
MUST_EXCLUDE = ("keys.json", "config.json", "team.json", "mcp.json",
                ".machine_id", ".models_cache.json", "__pycache__")
for name in MUST_EXCLUDE:
    check(f"install.ps1 เว้น {name}", name in PS1, "ไม่เจอชื่อในกฎคัดออก")
    check(f"install.sh เว้น {name}", name in SH, "ไม่เจอชื่อในกฎคัดออก")

# ── 3) ต้องยังคัดลอกของที่ต้องมีตอนรัน ──────────────────────────────────────
# ensure_user_files() ใช้ *.default.json เป็นต้นแบบสร้างไฟล์ที่ DATA_DIR ครั้งแรก
for name in ("config.default.json", "team.default.json", "mcp_catalog.json"):
    check(f"install.sh ไม่เผลอเว้น {name}",
          f"-name '{name}' -prune" not in SH)
    check(f"install.ps1 ไม่เผลอเว้น {name}", f'"{name}"' not in PS1)
for name in ("soonai.py", "requirements.txt", "shared"):
    check(f"install.ps1 ยังคัดลอก {name}", name in PS1)
    check(f"install.sh ยังคัดลอก {name}", name in SH)

# ── 4) launcher ต้องบังคับ UTF-8 (ทุกข้อความ UI เป็นภาษาไทย) ─────────────────
for label, text in (("install.ps1", PS1), ("install.sh", SH)):
    check(f"{label}: launcher ตั้ง PYTHONUTF8", "PYTHONUTF8" in text)
    check(f"{label}: launcher ตั้ง PYTHONIOENCODING=utf-8",
          "PYTHONIOENCODING" in text and "utf-8" in text.lower())

# ── 5) รันจริงกฎคัดออกของ install.sh (ข้ามถ้าเครื่องไม่มี sh) ─────────────────
SH_BIN = shutil.which("sh") or shutil.which("bash")
if not SH_BIN:
    skip("รันกฎคัดออกของ install.sh จริง", "ไม่พบ sh/bash ใน PATH")
else:
    work = Path(tempfile.mkdtemp(prefix="soonai-inst-"))
    src = work / "src" / "shared"
    (src / "skills" / "demo").mkdir(parents=True)
    (src / "__pycache__").mkdir()
    payload = {
        "chat.py": "code", "config.default.json": "{}", "team.default.json": "{}",
        "mcp_catalog.json": "{}", "keys.json": "SECRET", "config.json": "PRIVATE",
        "team.json": "PRIVATE", "mcp.json": "SECRET", ".machine_id": "ID",
        ".models_cache.json": "CACHE",
        "skills/demo/SKILL.md": "# demo", "skills/keys.json": "SECRET",
        "__pycache__/chat.cpython-314.pyc": "BYTECODE",
    }
    for rel, body in payload.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    # ดึงบล็อกคัดลอกจริงจาก install.sh มาใช้ (ไม่เขียนกฎซ้ำในเทสต์)
    start = SH.index("mkdir -p \"$INSTALL_DIR/shared\"")
    end = SH.index("cat > \"$BIN_DIR/soonai\"")
    block = SH[start:end].replace("$SCRIPT_DIR/shared", "$SRC") \
                         .replace("$INSTALL_DIR/shared", "$DST")
    dst = work / "dst"
    env = dict(os.environ, SRC=str(src), DST=str(dst))
    proc = subprocess.run([SH_BIN, "-c", block], env=env, cwd=str(work),
                          capture_output=True, text=True, timeout=60)
    check("install.sh: บล็อกคัดลอกทำงานได้", proc.returncode == 0,
          (proc.returncode, proc.stdout[-300:], proc.stderr[-300:]))
    got = {p.relative_to(dst).as_posix() for p in dst.rglob("*") if p.is_file()}
    for keep in ("chat.py", "config.default.json", "team.default.json",
                 "mcp_catalog.json", "skills/demo/SKILL.md"):
        check(f"install.sh: คัดลอก {keep}", keep in got, sorted(got))
    for drop in ("keys.json", "config.json", "team.json", "mcp.json", ".machine_id",
                 ".models_cache.json", "skills/keys.json",
                 "__pycache__/chat.cpython-314.pyc"):
        check(f"install.sh: ไม่คัดลอก {drop}", drop not in got, sorted(got))
    check("install.sh: ไม่มีเนื้อหาความลับหลุดไปถึงปลายทางเลย",
          not any("SECRET" in p.read_text(encoding="utf-8")
                  for p in dst.rglob("*") if p.is_file() and p.suffix in
                  (".json", ".py", ".md")))
    shutil.rmtree(work, ignore_errors=True)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)
print("ALL INSTALLER TESTS PASSED")
