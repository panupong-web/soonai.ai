# -*- coding: utf-8 -*-
"""Regression: ค้นหาไฟล์ต้องมีมารยาท (ข้ามของหนัก + ตาม .gitignore/.soonaiignore)

ก่อนหน้านี้ grep/glob ใช้ rglob("*") = กวาด node_modules/.venv/build/dist ทั้งหมด
ทำให้ช้า ผลลัพธ์เต็มไปด้วยของไม่เกี่ยว และเปลือง context ของโมเดล
"""
import os
import sys
import tempfile

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


root = tempfile.mkdtemp(prefix="soonai-scan-")


def w(rel, text="hello world\n"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


# โครงสร้างจำลองโปรเจกต์จริง
w("src/app.py", "MAGIC_TOKEN = 1\n")
w("src/util.js", "// MAGIC_TOKEN js\n")
w("keep/notes.md", "MAGIC_TOKEN ในเอกสาร\n")
w("node_modules/pkg/index.js", "MAGIC_TOKEN in dependency\n")
w(".venv/lib/site.py", "MAGIC_TOKEN in venv\n")
w("build/out.py", "MAGIC_TOKEN in build\n")
w("dist/out.js", "MAGIC_TOKEN in dist\n")
w("logs/debug.log", "MAGIC_TOKEN in logs\n")
w("src/gen.pb.py", "MAGIC_TOKEN generated\n")
w(".gitignore", "logs/\n*.pb.py\n")
w(".soonaiignore", "keep/\n")
with open(os.path.join(root, "binary.bin"), "wb") as fh:
    fh.write(b"\x00\x01MAGIC_TOKEN\xff\xfe")

files = {os.path.relpath(str(p), root).replace("\\", "/") for p in S.iter_project_files(root)}
check("เห็นไฟล์โปรเจกต์จริง", {"src/app.py", "src/util.js"} <= files, sorted(files))
check("ข้าม node_modules", "node_modules/pkg/index.js" not in files)
check("ข้าม .venv", ".venv/lib/site.py" not in files)
check("ข้าม build/dist", "build/out.py" not in files and "dist/out.js" not in files)
check("ตาม .gitignore (logs/)", "logs/debug.log" not in files)
check("ตาม .gitignore (*.pb.py)", "src/gen.pb.py" not in files)
check("ตาม .soonaiignore (keep/)", "keep/notes.md" not in files)

grep_out = S.run_tool("grep", {"pattern": "MAGIC_TOKEN", "path": root})
grep_out_slash = grep_out.replace("\\", "/")
check("grep: เจอในซอร์ส", "src/app.py" in grep_out_slash, grep_out[:300])
check("grep: ไม่เจอใน node_modules", "node_modules" not in grep_out, grep_out[:300])
check("grep: ไม่เจอใน .venv", ".venv" not in grep_out, grep_out[:300])
check("grep: ไม่เจอใน logs (gitignore)", "logs/debug.log" not in grep_out_slash, grep_out[:300])
check("grep: ไม่เจอใน keep (soonaiignore)", "keep/notes.md" not in grep_out_slash, grep_out[:300])
check("grep: ไฟล์ไบนารีถูกข้าม", "binary.bin" not in grep_out, grep_out[:300])

glob_py = S.run_tool("glob", {"pattern": "**/*.py", "path": root})
check("glob **/*.py: เจอไฟล์ชั้นบนสุด", "src/app.py" in glob_py, glob_py)
check("glob **/*.py: ข้าม .venv/build",
      ".venv" not in glob_py and "build/" not in glob_py, glob_py)
glob_all = S.run_tool("glob", {"pattern": "*.md", "path": os.path.join(root, "src")})
check("glob ระดับเดียว", glob_all.strip() == "(ไม่พบ)", glob_all)

# grep บนไฟล์เดี่ยวต้องยังทำงาน (ไม่ผ่านตัวเดินไฟล์)
one = S.run_tool("grep", {"pattern": "MAGIC_TOKEN", "path": os.path.join(root, "src", "app.py")})
check("grep ไฟล์เดียว", "1: MAGIC_TOKEN = 1" in one, one)

# ยังกัน secret อยู่ (ไม่ถูก ignore rules แซง) — เช็คว่าไม่มี "ตำแหน่งที่เจอ" ชี้ไปที่ไฟล์ secret
# (ข้อความที่ "พูดถึงชื่อ" keys.json เช่นใน .gitignore ยังปรากฏได้ตามปกติ)
all_slash = S.run_tool("grep", {"pattern": ".", "path": "."}).replace("\\", "/").lower()
check("secret ยังถูกกัน", "shared/keys.json:" not in all_slash, all_slash[:200])
check("secret ยังถูกกัน (sessions)", "/sessions/" not in all_slash, all_slash[:200])

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)
print("ALL PROJECT SEARCH TESTS PASSED")
