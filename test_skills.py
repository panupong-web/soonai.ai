# -*- coding: utf-8 -*-
"""Regression: ติดตั้ง skill แบบจบในคําสั่งเดียว
- แคตตาล็อกในตัว: SKILL.md ถูกต้องครบทุกตัว + ติดตั้งได้โดยไม่ต้องมีเน็ต/ไฟล์
- ติดตั้งทั้งชุด / ทับของเดิม (force) / ปฏิเสธเมื่อไม่ force
- ติดตั้งจาก SKILL.md ไฟล์เดียว (ใหม่) และจากโฟลเดอร์ (ของเดิมยังใช้ได้)
- _git_source_parts: owner/repo · owner/repo@สาขา · gh:owner/repo · URL เต็ม
- scaffold_skill: สร้างแม่แบบที่ parse ผ่าน + ชื่อผิดถูกปฏิเสธ
- cmd_skills: menu/list/catalog/all/new ทำงานและคืน exit code ถูก
ใช้ _SKILLS_TEST_ROOTS ชี้ไป temp เท่านั้น (ไม่แตะ shared/skills ของจริง)
"""
import argparse
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

# ความจำ preference ของผู้ใช้ = ใช้ไฟล์ temp ในเทสต์ ไม่แตะของจริง
_STATE_TMP = tempfile.mkdtemp(prefix="soonai-skillstate-")
os.environ["SOONAI_SKILL_STATE"] = str(Path(_STATE_TMP) / "skills_state.json")

from rich.console import Console  # noqa: E402

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


tmp = Path(tempfile.mkdtemp(prefix="soonai-skills-"))
root = tmp / "skills"
_orig = (S._SKILLS_TEST_ROOTS, S.console)
S._SKILLS_TEST_ROOTS = [str(root)]
S.console = Console(file=io.StringIO(), width=200, force_terminal=False)


def run_cli(**kw):
    args = argparse.Namespace(action=kw.get("action", "list"), target=kw.get("target", ""),
                              rest=kw.get("rest", []), force=kw.get("force", False))
    return S.cmd_skills(args)


try:
    # ---------------- แคตตาล็อกในตัว
    names = S.skill_catalog_names()
    check("catalog: มีอย่างน้อย 5 skill", len(names) >= 5, names)
    check("catalog: ชื่อเป็นมาตรฐาน a-z0-9-", all(S.skill_name_ok(n) for n in names), names)
    check("catalog: ชื่อเรียงเป็น", names == sorted(names), names)
    bad = []
    for nm in names:
        md = S.skill_catalog_md(nm)
        meta, body = S.parse_skill_md(md)
        if (meta.get("name") != nm or not meta.get("description")
                or "## ใช้เมื่อ" not in body or "## เกณฑ์เสร็จ" not in body):
            bad.append(nm)
    check("catalog: SKILL.md ครบ frontmatter+หัวข้อ", bad == [], bad)
    check("catalog: ชื่อไม่มี = ข้อความว่าง", S.skill_catalog_md("ไม่มีจริง") == "")

    # ---------------- ติดตั้งตัวเดียว (ไม่ต้องมีเน็ต)
    ok, msg = S.install_skill("thai-docs")
    check("ติดตั้งจากชื่อในแคตตาล็อก", ok is True, msg)
    check("เขียน SKILL.md จริง", (root / "thai-docs" / "SKILL.md").is_file())
    loaded = S.scan_skills()
    check("scan เห็น skill ที่ติดตั้ง", "thai-docs" in loaded, sorted(loaded))
    check("read_skill อ่านเนื้อหาได้", "## ขั้นตอน" in S.read_skill_text("thai-docs"))
    check("ข้อความบอกวิธีใช้ต่อ", "soonai skills show thai-docs" in msg, msg)

    # ติดตั้งซ้ำ = ปฏิเสธ ไม่ทับของเดิม
    (root / "thai-docs" / "SKILL.md").write_text(
        "---\nname: thai-docs\ndescription: ของเดิม\n---\n\nของเดิม\n", encoding="utf-8")
    ok2, msg2 = S.install_skill("thai-docs")
    check("ติดตั้งซ้ำไม่ทับ (ไม่ force)", ok2 is False and "--force" in msg2, msg2)
    check("ของเดิมยังอยู่", "ของเดิม" in S.read_skill_text("thai-docs"))
    ok3, _msg3 = S.install_skill("thai-docs", force=True)
    check("force เขียนทับได้", ok3 is True and "ของเดิม" not in S.read_skill_text("thai-docs"))

    # ชื่อที่ไม่มีในแคตตาล็อกและไม่ใช่แหล่งที่รู้จัก
    ok4, msg4 = S.install_skill("../ไม่มีอยู่จริง")
    check("แหล่งที่ไม่มี = ข้อความบอกทางเลือก", ok4 is False and "โฟลเดอร์" in msg4, msg4)

    # ---------------- ติดตั้งทั้งชุด
    _n, msg_all = S.install_catalog_all()
    check("all: รายงานผลการติดตั้ง", "ติดตั้งแล้ว" in msg_all, msg_all)
    check("all: scan เห็นทุกตัว", set(S.scan_skills()) >= set(names), sorted(S.scan_skills()))
    # all ซ้ำ = ไม่มีอะไรเปลี่ยนและไม่ error
    n2, msg2b = S.install_catalog_all()
    check("all ซ้ำ: ข้ามทั้งหมด", n2 == 0 and "ข้าม" in msg2b, msg2b)

    # ---------------- ไฟล์ .md เดียว + โฟลเดอร์
    single = tmp / "my-skill.md"
    single.write_text("---\nname: my-skill\ndescription: สกิลจากไฟล์เดียว\n---\n\nเนื้อหา\n",
                      encoding="utf-8")
    ok5, msg5 = S.install_skill(str(single))
    check("ติดตั้งจากไฟล์ .md เดียว", ok5 is True and "my-skill" in msg5, msg5)
    _ms = S.read_skill_text("my-skill")
    check("ไฟล์เดียว → SKILL.md ถูกต้อง",
          _ms.startswith("---") and "เนื้อหา" in _ms and "my-skill" in _ms, _ms)
    folder = tmp / "folder-skill"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: folder-skill\ndescription: จากโฟลเดอร์\n---\n\nก\n", encoding="utf-8")
    ok6, _msg6 = S.install_skill(str(folder))
    check("ติดตั้งจากโฟลเดอร์ (ของเดิมยังใช้ได้)", ok6 is True and "folder-skill" in S.scan_skills())
    ok7, msg7 = S.install_skill(str(folder), name="renamed-skill")
    check("ตั้งชื่อใหม่ตอนติดตั้งได้", ok7 is True and "renamed-skill" in msg7, msg7)

    # ---------------- แหล่งแบบ git (ไม่ยิงเน็ต: ตรวจการแปลงที่อยู่)
    check("git: owner/repo", S._git_source_parts("owner/repo") ==
          ("https://github.com/owner/repo", ""))
    check("git: owner/repo@dev", S._git_source_parts("owner/repo@dev") ==
          ("https://github.com/owner/repo", "dev"))
    check("git: gh:owner/repo#v2", S._git_source_parts("gh:owner/repo#v2") ==
          ("https://github.com/owner/repo", "v2"))
    check("git: URL เต็มคงเดิม", S._git_source_parts("https://gitlab.com/a/b.git") ==
          ("https://gitlab.com/a/b.git", ""))
    check("git: git@ คงเดิม (ไม่ตัด @)",
          S._git_source_parts("git@github.com:a/b.git")[0] == "git@github.com:a/b.git")
    check("git: owner/repo ถูกมองเป็น git", S._looks_like_git("owner/repo") is True)
    check("catalog ชื่อถูกมองเป็นแคตตาล็อก ไม่ใช่ owner/repo",
          S.is_catalog_skill("thai-docs") and not S.is_catalog_skill("owner/repo"))

    # ---------------- scaffold
    ok8, msg8 = S.scaffold_skill("my-new-skill")
    check("new: สร้างแม่แบบ", ok8 is True and (root / "my-new-skill" / "SKILL.md").is_file(), msg8)
    check("new: แม่แบบ parse ผ่าน", "my-new-skill" in S.scan_skills())
    ok9, msg9 = S.scaffold_skill("ชื่อไทย")
    check("new: ชื่อผิดถูกปฏิเสธ", ok9 is False and "a-z" in msg9, msg9)
    ok10, _m = S.scaffold_skill("my-new-skill")
    check("new: ซ้ำถูกปฏิเสธถ้าไม่ force", ok10 is False)

    # ---------------- CLI actions
    check("cmd list = 0", run_cli(action="list") == 0)
    check("cmd catalog = 0", run_cli(action="catalog") == 0)
    check("cmd menu (ไม่ interactive) = 0", run_cli(action="menu") == 0)
    check("cmd show = 0", run_cli(action="show", target="thai-docs") == 0)
    check("cmd show ตัวที่ไม่มี = 1", run_cli(action="show", target="ไม่มีจริง") == 1)
    check("cmd rm = 0", run_cli(action="rm", target="renamed-skill") == 0)
    check("cmd rm อีกครั้ง = 1", run_cli(action="rm", target="renamed-skill") == 1)
    check("cmd new = 0", run_cli(action="new", target="cli-made") == 0)
    check("cmd new ชื่อผิด = 1", run_cli(action="new", target="BAD NAME") == 1)
    check("cmd all = 0", run_cli(action="all") == 0)
    out = S.console.file.getvalue()
    check("cmd list แสดงตาราง", "skills ที่ติดตั้ง" in out, out[-200:])

    # ---------------- parser + slash menu
    ap = S.build_parser()
    a1 = ap.parse_args(["skills"])
    check("parser: ไม่ใส่อะไร = menu", a1.action == "menu", a1)
    a2 = ap.parse_args(["skills", "add", "thai-docs", "--force"])
    check("parser: add + --force", a2.action == "add" and a2.target == "thai-docs" and a2.force)
    a3 = ap.parse_args(["skills", "new", "abc"])
    check("parser: new", a3.action == "new" and a3.target == "abc")
    cmds = dict(S.SLASH_COMMANDS)
    check("slash: มี /skills", "/skills" in cmds)
finally:
    S._SKILLS_TEST_ROOTS, S.console = _orig

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL SKILL TESTS PASSED")
