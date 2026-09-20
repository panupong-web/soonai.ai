# -*- coding: utf-8 -*-
"""Regression: git workflow (M4) — ร่าง commit/PR + commit จริงใน temp repo
- _git_run / git_in_repo / git_branch / git_changes / git_base_branch
- git_commit_flow: stage เฉพาะไฟล์ที่เปลี่ยน + commit ด้วยข้อความที่ยืนยัน (ไม่ push)
- ปฏิเสธเมื่อไม่ interactive และไม่ได้ --yes (ต้องไม่ commit)
- draft_pr_body บันทึก .soonai/pr-body.md และไม่ push
ใช้ git จริงในโฟลเดอร์ temp เท่านั้น (ชี้ workspace_root ไปที่ temp)
"""
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

from rich.console import Console  # noqa: E402

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


tmp = tempfile.mkdtemp(prefix="soonai-git-")
_cwd = os.getcwd()
os.chdir(tmp)
_orig = (S.workspace_root, S.send_messages, S.console, S.load_config)
S.workspace_root = lambda: Path(tmp).resolve()
S.load_config = lambda: {"agent": {"shell": "off"}}
S.console = Console(file=io.StringIO(), width=200, force_terminal=False)

try:
    # ไม่ใช่ repo ก่อน
    check("git_in_repo = False ตอนยังไม่ init", S.git_in_repo() is False)
    check("git_changes ว่างเมื่อไม่ใช่ repo", S.git_changes() == [])
    check("git_branch ว่างเมื่อไม่ใช่ repo", S.git_branch() == "")

    # init repo + identity (เฉพาะใน temp)
    subprocess.run(["git", "init", "-q"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp, capture_output=True)
    check("git_in_repo = True หลัง init", S.git_in_repo() is True)
    br = S.git_branch()
    check("git_branch อ่านสาขาได้", br in ("main", "master"), br)

    # ไฟล์ตั้งต้น + commit แรกด้วยมือ
    Path(tmp, "app.py").write_text("a = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=tmp, capture_output=True)
    check("working tree สะอาด", S.git_changes() == [], S.git_changes())

    # แก้ไฟล์ + เพิ่มไฟล์ใหม่
    Path(tmp, "app.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    Path(tmp, "new.txt").write_text("ใหม่\n", encoding="utf-8")
    changes = dict((p, st) for st, p in S.git_changes())
    check("git_changes เห็นไฟล์ที่แก้", changes.get("app.py") == "M", changes)
    check("git_changes เห็นไฟล์ใหม่", changes.get("new.txt") == "??", changes)
    check("git_base_branch หา main/master เจอ", S.git_base_branch() in ("main", "master"),
          S.git_base_branch())

    # ร่างข้อความ commit (mock โมเดล)
    S.send_messages = lambda *a, **k: "แก้บั๊กการบวกเลข\n\n- เพิ่ม b = 2 ให้ครบ"
    diff_text, why = S.git_diff_text()
    check("git_diff_text มี diff จริง", "b = 2" in diff_text and why == "", (diff_text[:80], why))
    msg = S.draft_commit_message("openrouter", "m", diff_text)
    check("draft_commit_message คืนข้อความที่ลอก ``` ออก",
          msg.startswith("แก้บั๊กการบวกเลข") and "```" not in msg, msg)
    S.send_messages = lambda *a, **k: "```\nhmm\nข้อความล้วน\n```"
    msg2 = S.draft_commit_message("openrouter", "m", "diff")
    check("draft: ลอก code fence ออก", msg2.startswith("hmm"), msg2)
    check("draft: diff ว่าง = ไม่เรียกโมเดล",
          S.draft_commit_message("openrouter", "m", "") == "")

    # ปฏิเสธเมื่อไม่ interactive และไม่ได้ --yes (ต้องไม่เกิด commit)
    S.send_messages = lambda *a, **k: "ข้อความทดสอบ"
    ok_no = S.git_commit_flow("openrouter", "m", auto_yes=False)
    check("commit ถูกปฏิเสธเมื่อไม่ interactive", ok_no is False)
    code, log = S._git_run(["log", "--oneline"])
    check("ยังไม่เกิด commit ใหม่", len(log.splitlines()) == 1, log)

    # commit จริงด้วย auto_yes
    ok = S.git_commit_flow("openrouter", "m", auto_yes=True)
    check("commit สำเร็จเมื่อ auto_yes", ok is True)
    code, log2 = S._git_run(["log", "--oneline"])
    check("มี commit ใหม่", len(log2.splitlines()) == 2, log2)
    _c, subject = S._git_run(["log", "-1", "--pretty=%s"])
    check("ข้อความ commit ถูกใช้", subject.strip() == "ข้อความทดสอบ", subject)
    _c, files = S._git_run(["show", "--stat", "--oneline", "HEAD"])
    check("commit รวมทั้งไฟล์ที่แก้และไฟล์ใหม่",
          "app.py" in files and "new.txt" in files, files)
    check("ไม่มี remote/ไม่ push", S._git_run(["remote"])[1].strip() == "")
    check("working tree สะอาดหลัง commit", S.git_changes() == [], S.git_changes())

    # ไม่มีอะไรให้ commit → False
    check("commit เมื่อสะอาด = False", S.git_commit_flow("openrouter", "m", auto_yes=True) is False)

    # draft PR บันทึกลง .soonai/pr-body.md
    subprocess.run(["git", "checkout", "-qb", "feature"], cwd=tmp, capture_output=True)
    Path(tmp, "app.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "feature work"], cwd=tmp, capture_output=True)
    S.send_messages = lambda *a, **k: "TITLE: เพิ่ม c\n\n## ทำอะไร\n- เพิ่ม c"
    body = S.draft_pr_body("openrouter", "m", S.git_base_branch())
    check("draft_pr_body คืนข้อความ", body.startswith("TITLE:"), body[:60])
    saved = Path(tmp, ".soonai", "pr-body.md")
    check("บันทึก .soonai/pr-body.md", saved.is_file() and "เพิ่ม c" in saved.read_text(encoding="utf-8"))
    check("PR ไม่ push (ไม่มี remote)", S._git_run(["remote"])[1].strip() == "")
    S.send_messages = lambda *a, **k: ""
    check("draft PR ว่าง = ไม่บันทึกทับ", S.draft_pr_body("openrouter", "m", "main") == "")
finally:
    os.chdir(_cwd)
    S.workspace_root, S.send_messages, S.console, S.load_config = _orig

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL GIT WORKFLOW TESTS PASSED")
