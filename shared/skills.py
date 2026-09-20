# -*- coding: utf-8 -*-
"""skills: ระบบสกิลของ agent (catalog · ติดตั้ง · ค้นหา · AI เสนอ · เรียนรู้จากผู้ใช้)

Step 2 ของการแยกโมดูล — ย้ายมาจาก soonai.py แบบ verbatim แล้วลดการพึ่งภายนอก
ตามกฎเดียวกับ shell/usage: ``depgraph.py`` รายงาน bind_refs = 0 (ไม่ต้อง bind เลย)
- seam ของ CLI (console, neo_table, agent_tools, load_config, load_json, save_json,
  send_messages, fix_mojibake, _http_session, workspace_root, SKILL_STATE_FILE,
  BASE_DIR, SHARED_DIR) อ่านผ่าน ``R.<ชื่อ>`` — attribute access เท่านั้น
  (ห้าม ``from runtime import X`` เพราะค่าเหล่านี้อาจถูก rebind ทีหลัง)
- ชื่อที่เป็นของโมดูลพี่น้องจริง (CODE_SUFFIXES, iter_project_files, detect_test_command)
  import โมดูลนั้นตรง ๆ
- ไลบรารีภายนอก (requests, rich Panel/Prompt) import ตรงในไฟล์นี้

หมายเหตุ: ไฟล์นี้ชื่อ skills.py อยู่ข้างโฟลเดอร์ข้อมูล shared/skills/ (คนละอย่างกัน —
อันนั้นเป็นโฟลเดอร์เก็บ SKILL.md จริง) Python จะเลือก skills.py เมื่อ import ชื่อ 'skills'
"""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import requests
from rich.panel import Panel
from rich.prompt import Prompt

import project as _project
import runtime as R
import shell as _shell
import symbols as _symbols


SKILL_DIRNAME = "skills"
_SKILLS_TEST_ROOTS = None  # hook สำหรับเทส: ลิสต์ Path โฟลเดอร์ skills จำลอง


def skills_dirs():
    """โฟลเดอร์ skills ทั้งหมด: ส่วนกลาง (shared/skills) + CLI (cli/skills) + ประจำโปรเจกต์ (./.soonai/skills)"""
    if _SKILLS_TEST_ROOTS is not None:
        return [Path(p) for p in _SKILLS_TEST_ROOTS]
    roots = [R.SHARED_DIR / SKILL_DIRNAME, R.BASE_DIR / SKILL_DIRNAME]
    try:
        proj = Path.cwd() / ".soonai" / SKILL_DIRNAME
        if proj.resolve() not in [r.resolve() for r in roots]:
            roots.append(proj)
    except Exception:
        pass
    return roots


def parse_skill_md(text):
    """แยก frontmatter (--- ... ---) + body ของ SKILL.md คืน (meta, body)"""
    meta, body = {}, str(text or "").replace("\r\n", "\n")
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            fm = body[3:end]
            body = body[end + 4:]
            if body.startswith("\n"):
                body = body[1:]
            for line in fm.splitlines():
                s = line.strip()
                if not s or s.startswith("#") or s.startswith("-") or ":" not in s:
                    continue
                k, _, v = s.partition(":")
                meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta, body.strip()


def skill_name_ok(name):
    """ชื่อ skill มาตรฐาน: a-z 0-9 - ขึ้นต้นด้วยตัวอักษร/เลข"""
    import re
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(name or "")))


def load_skill_meta(skill_dir):
    """อ่าน+ตรวจ SKILL.md ในโฟลเดอร์ คืน (name, meta, body, error)"""
    try:
        p = Path(skill_dir) / "SKILL.md"
        if not p.is_file():
            return None, {}, "", "ไม่มี SKILL.md"
        meta, body = parse_skill_md(p.read_text(encoding="utf-8", errors="replace"))
        name = str(meta.get("name", "")).strip()
        desc = str(meta.get("description", "")).strip()
        if not skill_name_ok(name):
            return None, meta, body, f"ชื่อ skill ไม่ถูกต้อง: {name!r} (ต้อง a-z 0-9 -)"
        if not desc:
            return None, meta, body, "ขาด description ใน frontmatter"
        return name, meta, body, ""
    except Exception as e:
        return None, {}, "", str(e)


def scan_skills():
    """สแกน skills ทุกโฟลเดอร์ คืน {name: {name, description, path, scope}} (โปรเจกต์ชนะชื่อซ้ำ)"""
    out = {}
    try:
        roots = skills_dirs()
    except Exception:
        return out
    for root in roots:
        try:
            is_global = Path(root).expanduser().resolve() == (R.SHARED_DIR / SKILL_DIRNAME).resolve()
        except Exception:
            is_global = False
        scope = "ส่วนกลาง" if is_global else "โปรเจกต์"
        try:
            subs = sorted(x for x in Path(root).iterdir() if x.is_dir())
        except Exception:
            continue
        for sub in subs:
            name, meta, body, err = load_skill_meta(sub)
            if err:
                continue
            out[name] = {"name": name, "description": str(meta.get("description", "")),
                         "path": str(sub), "scope": scope}
    return out


def read_skill_text(name, max_chars=6000):
    """อ่านเนื้อหา SKILL.md ฉบับเต็มของ skill (ว่าง = '')"""
    try:
        sk = scan_skills().get(str(name or "").strip())
        if not sk:
            return ""
        t = Path(sk["path"], "SKILL.md").read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""
    if len(t) > max_chars:
        t = t[:max_chars] + "\n... (ตัดให้สั้น)"
    return t


def _ensure_skills_hint(messages, skills=None):
    """ถ้าติดตั้ง skills ไว้ เติมรายชื่อใน system prompt (ครั้งเดียว)"""
    try:
        sk = scan_skills() if skills is None else skills
        if not sk or not messages or messages[0].get("role") != "system":
            return
        if "read_skill" in (messages[0].get("content") or ""):
            return
        names = [f"{n} — {v.get('description', '')[:80]}" for n, v in list(sk.items())[:20]]
        messages[0] = {"role": "system",
                       "content": messages[0]["content"] +
                       "\nทักษะเสริม (skills) ที่ติดตั้งไว้ "
                       "เรียกอ่านฉบับเต็มด้วย read_skill เมื่อตรงกับงาน (ชื่อ: คำอธิบาย): " +
                       "; ".join(names)}
    except Exception:
        pass


def _collect_skill_candidates(base):
    """หาโฟลเดอร์ที่มี SKILL.md: ตัวเอง หรือลูกชั้นเดียว (repo รวมหลาย skills)"""
    base = Path(base)
    try:
        if (base / "SKILL.md").is_file():
            return [base]
        cands = []
        for sub in sorted(base.iterdir()):
            try:
                if sub.is_dir() and (sub / "SKILL.md").is_file():
                    cands.append(sub)
            except Exception:
                pass
        return cands[:50]
    except Exception:
        return []


def _safe_extract_zip(zf, dest):
    """แตก zip แบบกัน zip-slip (../ หรือ absolute)"""
    dest = Path(dest).resolve()
    for m in zf.infolist():
        try:
            target = (dest / m.filename).resolve()
        except Exception:
            raise ValueError(f"ชื่อไฟล์ไม่ปลอดภัย: {m.filename}")
        if target != dest and dest not in target.parents:
            raise ValueError(f"ชื่อไฟล์ไม่ปลอดภัย: {m.filename}")
    zf.extractall(str(dest))


# ── แคตตาล็อก skill ในตัว: ติดตั้งได้ทันทีโดยไม่ต้องมี URL/ไฟล์อะไรเลย ─────────
# เก็บเป็นข้อความ SKILL.md ในโค้ด → คัดลอกลงโฟลเดอร์ skills (ใช้ได้ทุกเครื่อง)
SKILL_CATALOG = {
    "thai-docs": (
        "เขียน/เกลาข้อความ เอกสาร และคอมเมนต์ให้เป็นไทยที่อ่านง่าย คงศัพท์เทคนิคอังกฤษ",
        """## ใช้เมื่อ
- ผู้ใช้ขอเอกสาร คอมเมนต์ หรือข้อความ UI เป็นไทย หรือขอให้เกลาภาษาให้อ่านง่าย

## ขั้นตอน
1. อ่านโค้ดหรือข้อความต้นทางจริงก่อนแก้ (ห้ามแต่งเนื้อหาใหม่ที่ไม่มีในโค้ด)
2. ประโยคสั้น ตรงประเด็น ไม่ใช้ศัพท์ราชการ
3. ศัพท์เทคนิค ชื่อฟังก์ชัน ชื่อไฟล์ คำสั่ง คงเป็นอังกฤษและห่อด้วย `backtick`
4. โครงเอกสาร: ทำอะไร · ใช้ยังไง (คำสั่งจริง) · ตัวอย่างผลลัพธ์ · ข้อควรระวัง
5. ตัวอย่างโค้ดต้องสอดคล้องกับค่าตั้งต้น/พารามิเตอร์จริงในไฟล์

## เสี่ยงที่ต้องเลี่ยง
- เดาค่า config หรือชื่อพารามิเตอร์เอง → ต้องเปิดไฟล์ตรวจก่อน
- ใช้คำว่า "ง่าย" "แค่" แล้วข้ามขั้นตอนที่จำเป็น

## เกณฑ์เสร็จ
- ไม่มีการเดา API/ค่าตั้งต้น · ภาษาไทยอ่านจบครั้งเดียวเข้าใจ
"""),
    "pytest-first": (
        "เขียนเทสต์ pytest จากโค้ดจริงก่อนแก้ แล้วรันด้วย run_tests จนผ่าน",
        """## ใช้เมื่อ
- ต้องแก้โค้ดที่ยังไม่มีเทสต์ หรือต้องกัน regression

## ขั้นตอน
1. เปิดอ่านฟังก์ชันที่จะแก้ + หาว่าโปรเจกต์ใช้ pytest อยู่แล้วไหม (ดู AGENTS.md/ไฟล์เทสต์เดิม)
2. เขียนเทสต์ใหม่ในไฟล์เดียวกับที่โปรเจกต์ใช้ (เช่น `tests/test_<โมดูล>.py`)
3. ครอบทั้งเคสปกติ + ขอบ (ค่าว่าง/ค่าผิดรูป/กรณีที่เคยพัง)
4. รันด้วย tool `run_tests` ให้เห็นผลจริงก่อนแก้โค้ดหลัก
5. แก้โค้ดให้เทสต์ผ่าน แล้วรัน `run_tests` ซ้ำเพื่อยืนยัน

## เสี่ยงที่ต้องเลี่ยง
- เทสต์ที่ผ่านตลอดโดยไม่ทดสอบอะไรจริง (assert หลวม)
- แก้เทสต์ให้ตามโค้ดที่พัง แทนที่จะแก้โค้ด

## เกณฑ์เสร็จ
- `run_tests` เขียว · เทสต์ใหม่ล้มเหลวจริงถ้าโค้ดกลับไปเป็นเวอร์ชันเดิม
"""),
    "security-check": (
        "ตรวจ secrets ช่องโหว่ input และคำสั่งอันตรายก่อนส่งงาน",
        """## ใช้เมื่อ
- ก่อน commit/push · หลังรับโค้ดจากที่อื่น · เมื่อแก้เรื่อง auth/ไฟล์/คำสั่ง shell

## ขั้นตอน
1. `grep` หาความเสี่ยง: `api_key|secret|token|password|BEGIN .*PRIVATE KEY`
2. ตรวจ sink ที่รับ input ผู้ใช้: `eval|exec|subprocess|os.system|open(|requests.`
3. ตรวจเส้นทางไฟล์: `../`, พาธ absolute, ชื่อไฟล์จากผู้ใช้ที่ไม่ได้ตรวจ
4. ตรวจคำสั่ง shell: pipe หลายชั้น, ตัวแปรจากภายนอก, wildcard ที่อาจกว้างเกิน
5. ตรวจว่า log/error ไม่ปริ้นค่าลับออกมา

## เสี่ยงที่ต้องเลี่ยง
- รายงานว่า "ปลอดภัย" โดยไม่มีหลักฐานเป็นไฟล์:บรรทัด
- แนะนำ dependency ใหม่โดยไม่จำเป็น

## เกณฑ์เสร็จ
- ทุกข้อสงสัยมี `ไฟล์:บรรทัด` ประกอบ · จุดที่ต้องลับมีคำสั่งแก้ชัดเจน
"""),
    "excel-report": (
        "สร้างรายงาน Excel/CSV จากข้อมูลจริงด้วย openpyxl พร้อมตรวจไฟล์ผลลัพธ์",
        """## ใช้เมื่อ
- ผู้ใช้ขอไฟล์ .xlsx/.csv สรุปข้อมูล ตาราง หรือรายงาน

## ขั้นตอน
1. หาข้อมูลต้นทางจริงก่อน (ไฟล์/คำสั่ง/ฐานข้อมูล) ถ้าไม่มีให้ถาม ไม่สร้างข้อมูลปลอม
2. ตรวจว่ามี `openpyxl` (หรือ `pandas`) ในเครื่อง ถ้าไม่มีให้บอกวิธิติดตั้งก่อน
3. เขียนสคริปต์สั้น ๆ ที่รันซ้ำได้ (อ่านข้อมูล → คำนวณ → เขียนไฟล์)
4. ตั้งหัวตาราง ความกว้างคอลัมน์ และรูปแบบตัวเลข/วันที่ให้อ่านง่าย
5. รันจริงด้วย `run_cmd` แล้วเปิดไฟล์กลับมาอ่านตรวจว่ามีข้อมูลตามที่ควร

## เสี่ยงที่ต้องเลี่ยง
- ใส่ตัวเลข/แถวที่แต่งขึ้นเอง
- ทับไฟล์ต้นฉบับของผู้ใช้ → เขียนเป็นชื่อใหม่เสมอ

## เกณฑ์เสร็จ
- มีไฟล์ผลลัพธ์จริง · รายงาน path + จำนวนแถว/คอลัมน์ · บอกคำสั่งที่ใช้สร้างใหม่ได้
"""),
    "windows-files": (
        "งานจัดการไฟล์/โฟลเดอร์บน Windows ด้วยคำสั่งที่ตรวจผลได้ทุกครั้ง",
        """## ใช้เมื่อ
- ต้องคัดลอก/ย้าย/เปลี่ยนชื่อ/จัดเรียงไฟล์จำนวนมาก บน Windows

## ขั้นตอน
1. ลิสต์ของจริงก่อนแตะ: `dir` / `Get-ChildItem` แล้วนับจำนวน
2. ทดลองกับสำเนาหรือโฟลเดอร์ย่อยก่อนเสมอ
3. ใช้พาธในเครื่องหมายคำพูดทุกครั้ง (ชื่อไฟล์ไทย/มีวรรคต้องรอด)
4. หลีกเลี่ยง `/s`, `/q`, `-Recurse -Force` ที่กว้างเกิน — ระบุโฟลเดอร์เป้าหมายชัด ๆ
5. รันทีละขั้น แล้วตรวจผล (นับไฟล์เทียบก่อน/หลัง) ก่อนไปขั้นต่อไป

## เสี่ยงที่ต้องเลี่ยง
- ลบ/ย้ายโดยไม่มีทางกลับ (soonai มี `/undo` เฉพาะไฟล์ที่ agent เขียนเอง)
- ใช้ wildcard ที่ครอบโฟลเดอร์ระบบ

## เกณฑ์เสร็จ
- รายงานจำนวนไฟล์ก่อน/หลัง · ระบุพาธจริงที่แตะ · คำสั่งที่ใช้รันซ้ำได้
"""),
    "refactor-safe": (
        "รีแฟกเตอร์โค้ดเดิมทีละขั้นโดยไม่เปลี่ยนพฤติกรรม มีเทสต์คุมและย้อนได้",
        """## ใช้เมื่อ
- ผู้ใช้ขอจัดโค้ดใหม่ ลดความซ้ำ หรือย้ายฟังก์ชัน โดยไม่ให้พฤติกรรมเปลี่ยน

## ขั้นตอน
1. ล็อกพฤติกรรมเดิมด้วยเทสต์ก่อน (ดู skill `pytest-first`) แล้วรัน `run_tests`
2. แบ่งเป็นขั้นเล็ก ๆ ที่รันเทสต์ผ่านได้ทุกขั้น อย่ารวมหลายอย่างในรอบเดียว
3. แก้ด้วย `edit_file` เป็นจุด ไม่เขียนทั้งไฟล์
4. รัน `run_tests` ทุกขั้น — แดงให้ย้อน `/undo` แล้วทำใหม่ให้เล็กลง
5. สรุปให้ผู้ใช้ว่าแต่ละขั้นย้ายอะไรไปไหน และมีอะไรที่จงใจไม่แตะ

## เสี่ยงที่ต้องเลี่ยง
- เปลี่ยนชื่อ public API หรือเปลี่ยนข้อความ error ที่ผู้ใช้เห็น
- รีแฟกเตอร์พร้อมเพิ่มฟีเจอร์ในคราวเดียว

## เกณฑ์เสร็จ
- เทสต์เขียวทั้งก่อน/หลัง · diff อ่านง่าย · ไม่มีโค้ดซ้ำที่ตั้งใจเหลือ
"""),
}


def skill_catalog_md(name):
    """สร้างข้อความ SKILL.md ของ skill ในแคตตาล็อก ('' = ไม่มีชื่อนั้น)"""
    item = SKILL_CATALOG.get(str(name or "").strip().lower())
    if not item:
        return ""
    desc, body = item
    return f"---\nname: {name}\ndescription: {desc}\n---\n\n{body.strip()}\n"


def skill_catalog_names():
    return sorted(SKILL_CATALOG)


def is_catalog_skill(name):
    """ชื่อนี้เป็น skill ในแคตตาล็อกหรือไม่ (owner/repo, URL, พาธของจริง = ไม่ใช่)"""
    nm = str(name or "").strip().lower()
    if not nm or nm not in SKILL_CATALOG:
        return False
    if nm.startswith(("http://", "https://", "gh:")):
        return False
    try:
        if Path(str(name)).exists():
            return False
    except Exception:
        pass
    return True


def skill_catalog_table():
    """ตาราง skill ที่ติดตั้งได้ทันที (ชื่อ · คำอธิบาย · สถานะ)"""
    installed = scan_skills()
    table = R.neo_table(title=f"skill พร้อมติดตั้งทันที ({len(SKILL_CATALOG)})")
    table.add_column("ชื่อ", style="cyan", no_wrap=True)
    table.add_column("ทำอะไร", style="white", no_wrap=True, max_width=46)
    table.add_column("สถานะ", style="dim", no_wrap=True)
    for nm in skill_catalog_names():
        desc = SKILL_CATALOG[nm][0]
        if len(desc) > 44:
            desc = desc[:43] + "…"
        table.add_row(nm, desc, "ติดตั้งแล้ว" if nm in installed else
                      ("หยุดเสนอ — คุณเคยปฏิเสธ" if skill_is_declined(nm) else "-"))
    return table


def install_catalog_skill(name, dest_root=None, force=False):
    """ติดตั้ง skill จากแคตตาล็อกในตัว (ไม่ต้องโหลดอะไร) คืน (สำเร็จ, ข้อความ)"""
    key = str(name or "").strip().lower()
    md = skill_catalog_md(key)
    if not md:
        return False, (f"ไม่มี skill ชื่อ '{name}' ในแคตตาล็อก "
                       f"(มี: {', '.join(skill_catalog_names())})")
    root = Path(dest_root) if dest_root else Path(skills_dirs()[0])
    dest = root / key
    try:
        if dest.exists() and not force:
            return False, f"{key} ติดตั้งอยู่แล้ว (ใช้ --force ถ้าจะเขียนทับ)"
        if dest.exists():
            shutil.rmtree(str(dest))
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text(md, encoding="utf-8")
    except Exception as e:
        return False, f"ติดตั้งไม่ได้: {e}"
    return True, f"ติดตั้ง {key} แล้ว — agent ใช้ได้ทันที (ลอง: soonai skills show {key})"


def install_catalog_all(dest_root=None, force=False):
    """ติดตั้งทุก skill ในแคตตาล็อก คืน (จำนวนที่สำเร็จ, ข้อความ)"""
    done, skipped = [], []
    for nm in skill_catalog_names():
        ok, msg = install_catalog_skill(nm, dest_root=dest_root, force=force)
        (done if ok else skipped).append(nm)
    parts = []
    if done:
        parts.append(f"ติดตั้งแล้ว {len(done)}: " + ", ".join(done))
    if skipped:
        parts.append("ข้าม: " + ", ".join(skipped))
    return len(done), " · ".join(parts) or "ไม่มีอะไรติดตั้ง"


def _git_source_parts(src):
    """แยกแหล่งแบบ git เป็น (url, branch) — รองรับ owner/repo, owner/repo@สาขา, gh:owner/repo"""
    s = str(src or "").strip()
    branch = ""
    if "@" in s and not s.startswith("git@") and "://" not in s:
        s, _, branch = s.rpartition("@")
    elif "#" in s and "://" not in s:
        s, _, branch = s.rpartition("#")
    if s.startswith("gh:"):
        s = "https://github.com/" + s[3:].lstrip("/")
    if re.fullmatch(r"[\w.\-]+/[\w.\-]+", s):
        s = f"https://github.com/{s}"
    return s, branch.strip()


def _looks_like_git(src):
    import re
    s = src.strip()
    if s.endswith(".git") or s.startswith("git@"):
        return True
    if re.fullmatch(r"[\w.\-]+/[\w.\-]+", s):
        return True
    return bool(re.match(r"https?://(github\.com|gitlab\.com)/[^/]+/[^/]+?(\.git)?/?$", s))


def _stage_skill_git(src):
    import shutil
    import subprocess
    url, branch = _git_source_parts(src)
    if shutil.which("git") is None:
        return "", None, "เครื่องนี้ไม่มี git"
    td = tempfile.mkdtemp(prefix="skill_")
    repo = td + "_repo"
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["-b", branch]
    cmd += [url, repo]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        shutil.rmtree(td, ignore_errors=True)
        return "", None, f"clone ไม่ได้: {e}"
    shutil.rmtree(td, ignore_errors=True)
    if r.returncode != 0:
        shutil.rmtree(repo, ignore_errors=True)
        return "", None, f"clone ไม่ได้: {(r.stderr or '')[-300:]}"
    return repo, repo, ""


def _stage_skill_url(url):
    import shutil
    try:
        r = requests.get(url, timeout=30)
    except Exception as e:
        return "", None, f"โหลดไม่ได้: {e}"
    if r.status_code != 200:
        return "", None, f"โหลดไม่ได้ (HTTP {r.status_code})"
    td = tempfile.mkdtemp(prefix="skill_")
    low = url.lower().split("?")[0]
    ctype = (r.headers.get("content-type", "") or "").lower()
    try:
        if low.endswith(".zip") or "zip" in ctype:
            zp = Path(td) / "skill.zip"
            zp.write_bytes(r.content)
            import zipfile
            with zipfile.ZipFile(str(zp)) as z:
                _safe_extract_zip(z, td)
            zp.unlink()
        else:
            (Path(td) / "SKILL.md").write_text(r.text, encoding="utf-8")
    except Exception as e:
        shutil.rmtree(td, ignore_errors=True)
        return "", None, f"แตกไฟล์ไม่ได้: {e}"
    return td, td, ""


def _stage_skill_source(src):
    import shutil
    p = Path(src)
    try:
        if p.is_dir():
            return str(p), None, ""
        if p.is_file() and p.suffix.lower() in (".md", ".markdown"):
            # SKILL.md ไฟล์เดียว → ห่อเป็นโฟลเดอร์ skill ให้เลย
            td = tempfile.mkdtemp(prefix="skill_")
            try:
                (Path(td) / "SKILL.md").write_text(
                    p.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            except Exception as e:
                shutil.rmtree(td, ignore_errors=True)
                return "", None, f"อ่านไฟล์ .md ไม่ได้: {e}"
            return td, td, ""
        if p.is_file() and p.suffix.lower() == ".zip":
            td = tempfile.mkdtemp(prefix="skill_")
            try:
                import zipfile
                with zipfile.ZipFile(str(p)) as z:
                    _safe_extract_zip(z, td)
            except Exception as e:
                shutil.rmtree(td, ignore_errors=True)
                return "", None, f"แตก zip ไม่ได้: {e}"
            return td, td, ""
    except Exception as e:
        return "", None, f"อ่านไฟล์ไม่ได้: {e}"
    low = src.lower()
    if low.startswith(("http://", "https://")):
        return _stage_skill_url(src)
    if _looks_like_git(src):
        return _stage_skill_git(src)
    return "", None, "ไม่รู้จักแหล่ง skill (ใช้โฟลเดอร์/.zip/URL/git)"


def install_skill(source, name=None, dest_root=None, force=False):
    """ติดตั้ง skill ได้ทุกทางในคําสั่งเดียว:
    - ชื่อในแคตตาล็อก (เช่น `thai-docs`) → ใช้ทันทีโดยไม่ต้องโหลด
    - `owner/repo`, `owner/repo@สาขา`, `gh:owner/repo` → GitHub
    - SKILL.md ไฟล์เดียว (URL หรือ .md ในเครื่อง) · .zip · โฟลเดอร์ · git URL
    โฟลเดอร์ปลายทางเริ่มต้น = โฟลเดอร์ skills ส่วนกลาง (ที่ CLI สแกนอยู่แล้ว)
    คืน (สำเร็จ, ข้อความ)"""
    import shutil
    if is_catalog_skill(source):
        return install_catalog_skill(source, dest_root=dest_root, force=force)
    try:
        dest_root = Path(dest_root) if dest_root else Path(skills_dirs()[0])
        dest_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"สร้างโฟลเดอร์ skills ไม่ได้: {e}"
    base, cleanup, err = _stage_skill_source(str(source or "").strip())
    if err:
        return False, err
    try:
        cands = _collect_skill_candidates(base)
        if not cands:
            return False, "ไม่พบ SKILL.md ในแหล่งนี้"
        done, skipped = [], []
        for cand in cands:
            sname, meta, body, verr = load_skill_meta(cand)
            if verr:
                skipped.append(f"{cand.name} ({verr})")
                continue
            final = str(name or "").strip() if len(cands) == 1 else ""
            final = final or sname
            if not skill_name_ok(final):
                skipped.append(f"{cand.name} (ชื่อไม่ถูกต้อง)")
                continue
            dest = dest_root / final
            if dest.exists() and not force:
                skipped.append(f"{final} (มีอยู่แล้ว — ใช้ --force เพื่อเขียนทับ)")
                continue
            try:
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(cand), str(dest))
            except Exception as e:
                skipped.append(f"{final} (ก๊อปไม่ได้: {e})")
                continue
            done.append(final)
        if not done:
            return False, "ติดตั้งไม่ได้: " + "; ".join(skipped[:5])
        msg = f"ติดตั้งแล้ว {len(done)} skill: " + ", ".join(done)
        msg += " — ใช้ได้ทันที (ลอง: soonai skills show " + done[0] + ")"
        if skipped:
            msg += " (ข้าม: " + "; ".join(skipped[:5]) + ")"
        return True, msg
    finally:
        if cleanup:
            shutil.rmtree(cleanup, ignore_errors=True)


# ── ค้นหา/แนะนํา skill: ให้ AI ดูโปรเจกต์ หรือให้ผู้ใช้พิมพ์คำค้นก็ได้ ────────
# 1) ค้นในแคตตาล็อกในตัว + skill ที่ติดตั้งแล้ว (ไม่ต้องมีเน็ต)
# 2) จะค้นบน GitHub ด้วยก็ได้ (--web) โดยตรวจว่ามี SKILL.md จริงก่อนเสนอ
# 3) ให้ AI อ่านบริบทโปรเจกต์แล้วเสนอ skill ที่เหมาะสม (บอกว่าตัวไหนติดตั้งได้เลย)
SKILL_SEARCH_SYNONYMS = {
    "ทดสอบ": ["test", "pytest", "เทสต์"],
    "เทสต์": ["test", "pytest"],
    "บัก": ["test", "bug", "debug"],
    "เอกสาร": ["docs", "document", "readme"],
    "อ่านง่าย": ["readable"],   # อย่าให้กินคำกว้างอย่าง docs — กันเสนอ thai-docs ผิดเรื่อง
    "ภาษาไทย": ["thai", "ไทย"],
    "ความปลอดภัย": ["security", "secret", "ช่องโหว่"],
    "ลับ": ["secret", "security", "key"],
    "ตาราง": ["excel", "csv", "รายงาน"],
    "รายงาน": ["excel", "report", "csv"],
    "ไฟล์": ["file", "files", "โฟลเดอร์"],
    "ย้ายไฟล์": ["files", "windows", "move"],
    "ปรับโค้ด": ["refactor", "clean"],
    "จัดโค้ด": ["refactor", "clean"],
    "รีแฟกเตอร์": ["refactor"],
}


def _skill_search_terms(query):
    """แยกคำค้นเป็นคำย่อย + เติมคำพ้อง (รองรับการพิมพ์ไทยที่ไม่มีวรรค)"""
    q = str(query or "").strip().lower()
    if not q:
        return []
    terms = [t for t in re.split(r"[\s,;/|]+", q) if t]
    out = list(terms)
    for th, ens in SKILL_SEARCH_SYNONYMS.items():
        if th in q or any(e in q for e in ens):
            out.extend(ens)
            out.append(th)
    return list(dict.fromkeys(out))

# คำที่พบบ่อยเกินไปในเนื้อหา — นับเฉพาะชื่อ/คำอธิบาย ไม่เอาไปนับในเนื้อหา (กันผลล้น)
SKILL_SEARCH_STOP = {"ไฟล์", "file", "files", "โฟลเดอร์", "folder", "งาน", "และ", "ของ",
                     "ที่", "ใช้", "การ", "ด้วย", "ให้", "การ", "the", "and", "with"}


def _skill_score(name, desc, body, terms):
    """ให้คะแนนความตรง: ชื่อสำคัญสุด → คำอธิบาย → เนื้อหา (คำพบบ่อยไม่นับในเนื้อหา)"""
    hay_name, hay_desc, hay_body = name.lower(), (desc or "").lower(), (body or "").lower()
    score = 0
    for t in terms:
        if not t:
            continue
        if t in hay_name:
            score += 6
        if t in hay_desc:
            score += 3
        if t not in SKILL_SEARCH_STOP:
            score += min(3, hay_body.count(t))
    return score


def search_catalog(query, include_installed=True, limit=8, boost=None):
    """ค้น skill จากแคตตาล็อกในตัว + ที่ติดตั้งแล้ว คืน list ของ dict (คะแนนมากก่อน)
    boost = ฟังก์ชันชื่อ → คะแนนพิเศษ (ใช้ดัน skill ที่ผู้ใช้ใช้บ่อย โดยไม่ลดความแม่นของการกรอง)
    คืน [] เมื่อคำค้นว่าง"""
    terms = _skill_search_terms(query)
    if not terms:
        return []
    installed = {}
    if include_installed:
        try:
            installed = scan_skills()
        except Exception:
            installed = {}
    rows = []
    for nm in skill_catalog_names():
        desc = SKILL_CATALOG[nm][0]
        score = _skill_score(nm, desc, SKILL_CATALOG[nm][1], terms)
        if score > 0:
            rows.append({"name": nm, "description": desc, "score": score,
                         "in_catalog": True, "installed": nm in installed,
                         "used": skill_use_count(nm), "declined": skill_is_declined(nm)})
    for nm, info in installed.items():
        if nm in SKILL_CATALOG:
            continue
        desc = info.get("description", "")
        body = read_skill_text(nm, max_chars=4000)
        score = _skill_score(nm, desc, body, terms)
        if score > 0:
            rows.append({"name": nm, "description": desc, "score": score,
                         "in_catalog": False, "installed": True,
                         "used": skill_use_count(nm), "declined": skill_is_declined(nm)})
    rows.sort(key=lambda r: (-r["score"], r["name"]))
    if rows:
        # เก็บเฉพาะที่คะแนนไม่ห่างจากตัวท็อปเกินครึ่ง — กันการคืนทั้งแคตตาล็อก
        # (กรองด้วยคะแนนพื้นฐานก่อน แล้วค่อยดันอันดับด้วย boost = ความแม่นคงเดิม)
        top = rows[0]["score"]
        rows = [r for r in rows if r["score"] >= max(2, int(top * 0.5))]
    if boost and rows:
        for r in rows:
            try:
                r["boost"] = int(boost(r["name"]) or 0)
            except Exception:
                r["boost"] = 0
            r["score"] += r["boost"]
        rows.sort(key=lambda r: (-r["score"], r["name"]))
    return rows[:max(1, int(limit))]


def search_github_skills(query, limit=6):
    """หา skill บน GitHub จากคำค้น (best-effort ต้องมีเน็ต)
    ตรวจก่อนว่า repo นั้นมี SKILL.md จริง แล้วคืน [{name, repo, url, description}]
    คืน (rows, เหตุผลที่ว่าง)"""
    q = str(query or "").strip()
    if not q:
        return [], "ต้องมีคำค้นก่อน"
    try:
        r = R._http_session().get(
            "https://api.github.com/search/repositories",
            params={"q": f"{q} skill in:name,description,readme", "per_page": max(1, min(20, limit * 2))},
            headers={"Accept": "application/vnd.github+json"}, timeout=15)
        if r.status_code != 200:
            return [], f"GitHub ตอบ HTTP {r.status_code} (อาจติดเรต — ลองใหม่ทีหลัง)"
        items = (r.json() or {}).get("items") or []
    except Exception as e:
        return [], f"ค้น GitHub ไม่ได้: {e}"
    rows = []
    for it in items[:limit * 2]:
        full = str(it.get("full_name") or "")
        if not full:
            continue
        for path in ("SKILL.md", "skills", ".soonai/skills"):
            try:
                chk = R._http_session().get(
                    f"https://api.github.com/repos/{full}/contents/{path}",
                    headers={"Accept": "application/vnd.github+json"}, timeout=10)
                if chk.status_code == 200:
                    rows.append({"name": full.split("/")[-1][:40], "repo": full,
                                 "url": f"https://github.com/{full}",
                                 "description": str(it.get("description") or "")[:110],
                                 "path": path})
                    break
            except Exception:
                continue
        if len(rows) >= limit:
            break
    if not rows:
        return [], "ไม่พบ repo ที่มี SKILL.md จากคำค้นนี้"
    return rows, ""


def project_facts():
    """สรุปข้อเท็จจริงของโปรเจกต์ที่กำลังอยู่ (ให้ AI ใช้เลือก skill)
    คืน dict: languages, test_command, files, has_docs, has_ci, deps, entry"""
    root = R.workspace_root()
    facts = {"root": str(root), "languages": [], "test_command": "", "files": 0,
             "has_docs": False, "has_ci": False, "deps": [], "entry": []}
    try:
        files = list(_project.iter_project_files(root))[:400]
    except Exception:
        files = []
    facts["files"] = len(files)
    by_suffix = {}
    for f in files:
        by_suffix[f.suffix.lower()] = by_suffix.get(f.suffix.lower(), 0) + 1
    facts["languages"] = [s.lstrip(".") for s, n in sorted(by_suffix.items(), key=lambda kv: -kv[1])
                          if s in _symbols.CODE_SUFFIXES][:6]
    try:
        facts["test_command"] = _shell.detect_test_command()
    except Exception:
        pass
    try:
        facts["has_docs"] = any(f.name.lower() in ("readme.md", "docs.md", "agents.md")
                                for f in files)
        facts["has_ci"] = any(".github" in str(f) or f.name.lower().startswith("ci")
                              for f in files)
        facts["entry"] = [f.name for f in files
                          if f.name.lower() in ("main.py", "app.py", "index.js", "main.go",
                                                "cli.py", "__main__.py")][:5]
    except Exception:
        pass
    facts["deps"] = _project_deps(root)
    return facts


def _project_deps(root):
    """รายชื่อ dependency ของโปรเจกต์ — รองรับ requirements.txt / package.json / pyproject.toml"""
    skip = {"name", "version", "description", "dependencies", "devdependencies", "scripts",
            "project", "tool", "requires-python", "python", "build-system", "optional"}

    def _clean(names):
        out = []
        for n in names:
            n = str(n).strip().strip("\"'").split(">=")[0].split("==")[0].split("[")[0]
            n = n.strip()
            if not n or n.lower() in skip or len(n) < 2:
                continue
            out.append(n)
        return list(dict.fromkeys(out))[:12]

    try:
        req = Path(root) / "requirements.txt"
        if req.is_file():
            names = []
            for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or line.startswith("-"):
                    continue
                m = re.match(r"([A-Za-z][\w.\-]{1,40})", line)
                if m:
                    names.append(m.group(1))
            if names:
                return _clean(names)
    except Exception:
        pass
    try:
        pj = Path(root) / "package.json"
        if pj.is_file():
            data = json.loads(pj.read_text(encoding="utf-8")) or {}
            names = (list((data.get("dependencies") or {}).keys())
                     + list((data.get("devDependencies") or {}).keys()))
            if names:
                return _clean(names)
    except Exception:
        pass
    try:
        pt = Path(root) / "pyproject.toml"
        if pt.is_file():
            txt = pt.read_text(encoding="utf-8", errors="replace")
            names = []
            m = re.search(r"dependencies\s*=\s*\[(.*?)\]", txt, re.S)
            if m:
                names += re.findall(r"[\"']([^\"']+)[\"']", m.group(1))
            m2 = re.search(r"\[tool\.poetry\.dependencies\](.*?)(\n\[|\Z)", txt, re.S)
            if m2:
                names += re.findall(r"^\s*([A-Za-z][\w.\-]*)", m2.group(1), re.M)
            return _clean(names)
    except Exception:
        pass
    return []


SKILL_ADVISOR_SYSTEM = (
    "You recommend reusable agent skills for a software project. "
    "Reply in Thai (keep English tech terms). Reply with JSON only, shape: "
    '{"skills":[{"name":"a-z0-9-and-dashes","description":"<=60 chars Thai",'
    '"why":"<=60 chars Thai why it fits this project"}],"note":"<=80 chars Thai"}'
    "Rules: 2-4 skills, name must be lowercase a-z 0-9 and '-' only, "
    "prefer generic reusable workflows (not project-specific hacks), no markdown fences.")


def parse_skill_suggestions(text):
    """แยก JSON ข้อเสนอ skill จากคำตอบโมเดล (ทนข้อความห่อ/โค้ดเฟนซ์) คืน list ของ dict"""
    s = str(text or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s.split("\n", 1)[1] if "\n" in s else s
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j <= i:
        return []
    try:
        data = json.loads(s[i:j + 1])
    except Exception:
        return []
    out = []
    for item in (data.get("skills") or []):
        if not isinstance(item, dict):
            continue
        nm = str(item.get("name", "")).strip().lower()
        if not skill_name_ok(nm):
            continue
        out.append({"name": nm,
                    "description": str(item.get("description", "")).strip()[:80],
                    "why": str(item.get("why", "")).strip()[:80]})
    return out


def ai_suggest_skills(provider, model, question="", facts=None, limit=4):
    """ให้ AI ดูบริบทโปรเจกต์ (+โจทย์ที่ผู้ใช้พิมพ์) แล้วเสนอ skill ที่ควรมี
    คืน list ของ dict {name, description, why, in_catalog, installed}"""
    facts = facts if isinstance(facts, dict) else project_facts()
    catalog_txt = "\n".join(f"- {n}: {SKILL_CATALOG[n][0]}" for n in skill_catalog_names())
    installed = []
    try:
        installed = sorted(scan_skills())
    except Exception:
        pass
    ctx = (f"[โปรเจกต์] {facts.get('root')}\n"
           f"ภาษา: {', '.join(facts.get('languages') or []) or '-'}\n"
           f"คำสั่งเทสต์: {facts.get('test_command') or '-'}\n"
           f"ไฟล์ที่สแกน: {facts.get('files')} · มีเอกสาร: {facts.get('has_docs')} · "
           f"มี CI: {facts.get('has_ci')}\n"
           f"ไฟล์หลัก: {', '.join(facts.get('entry') or []) or '-'}\n"
           f"dependency เด่น: {', '.join(facts.get('deps') or []) or '-'}\n"
           f"[skill ที่มีในแคตตาล็อกในเครื่อง]\n{catalog_txt}\n"
           f"[ติดตั้งแล้ว] {', '.join(installed) or '-'}\n"
           f"[สิ่งที่ผู้ใช้ขอเพิ่ม] {str(question or '').strip() or '(ไม่ได้ระบุ — ดูจากโปรเจกต์)'}")
    msgs = [{"role": "system", "content": SKILL_ADVISOR_SYSTEM},
            {"role": "user", "content": ctx}]
    try:
        out = R.send_messages(provider, model, msgs, 0.2, stream=False, effort="", max_tokens=700)
    except Exception as e:
        R.console.print(f"[yellow]ให้ AI เสนอไม่สำเร็จ: {e}[/yellow]")
        return []
    sugs = parse_skill_suggestions(R.fix_mojibake(out or ""))[:max(1, int(limit))]
    for s in sugs:
        s["in_catalog"] = is_catalog_skill(s["name"])
        s["installed"] = s["name"] in installed
    return sugs


# ── เรียนรู้จากผู้ใช้: ปฏิเสธซ้ำ = หยุดเสนอ · ใช้บ่อย = เสนอก่อน/พกข้ามโฟลเดอร์ ──
# เก็บใน DATA_DIR (แยกเครื่อง ไม่ปนกับโปรเจกต์) เพื่อให้ความเคยชินติดตามผู้ใช้ทุกโฟลเดอร์
SKILL_DECLINE_LIMIT = 2   # ปฏิเสธครบเท่านี้ = หยุดเสนอ (ทับได้ด้วย config agent.skill_decline_limit)
SKILL_FREQUENT_USE = 2    # ใช้จริงครบเท่านี้ = "ใช้บ่อย" (ได้คะแนนพิเศษ + เสนอข้ามโฟลเดอร์)
_SKILL_STATE = {"data": None}
_SKILL_CARRYOVER = {"done": False}   # เสนอพกสกิลข้ามโฟลเดอร์แค่ครั้งเดียวต่อเซสชัน


def _skill_state():
    """อ่าน/แคชความเคยชินของผู้ใช้: {'declined': {ชื่อ: ครั้ง}, 'used': {ชื่อ: ครั้ง}}"""
    if _SKILL_STATE["data"] is None:
        raw = R.load_json(R.SKILL_STATE_FILE, {})
        data = {"declined": {}, "used": {}}
        if isinstance(raw, dict):
            for key in ("declined", "used"):
                src = raw.get(key)
                if not isinstance(src, dict):
                    continue
                for k, v in src.items():
                    try:
                        n = int(v)
                    except Exception:
                        continue
                    k = str(k).strip().lower()
                    if k and n > 0:
                        data[key][k] = n
        _SKILL_STATE["data"] = data
    return _SKILL_STATE["data"]


def _skill_state_save():
    try:
        R.save_json(R.SKILL_STATE_FILE, _skill_state())
    except Exception:
        pass


def _skill_decline_limit():
    try:
        v = int((R.load_config().get("agent") or {}).get("skill_decline_limit", SKILL_DECLINE_LIMIT))
        return max(1, v)
    except Exception:
        return SKILL_DECLINE_LIMIT


def skill_decline_count(name):
    try:
        return int(_skill_state()["declined"].get(str(name or "").strip().lower(), 0))
    except Exception:
        return 0


def skill_is_declined(name):
    """ผู้ใช้ปฏิเสธ skill นี้ครบโควตาแล้ว → หยุดเสนอ (เปิดคืนได้ด้วย /skills reset <ชื่อ>)"""
    return skill_decline_count(name) >= _skill_decline_limit()


def skill_use_count(name):
    try:
        return int(_skill_state()["used"].get(str(name or "").strip().lower(), 0))
    except Exception:
        return 0


def skill_used_often(name):
    return skill_use_count(name) >= SKILL_FREQUENT_USE


def skill_usage_boost(name):
    """คะแนนพิเศษให้ skill ที่ผู้ใช้ใช้บ่อย (สูงสุด +12) — ดันอันดับโดยไม่ลดความแม่นของการค้น"""
    return min(skill_use_count(name), 6) * 2


def record_skill_decline(names):
    """จดว่าผู้ใช้ปฏิเสธ skill อะไร (นับสะสม) คืนรายชื่อที่ถึงโควตา 'หยุดเสนอ' แล้ว"""
    names = [str(n).strip().lower() for n in (names or []) if n]
    if not names:
        return []
    st = _skill_state()
    stopped = []
    for nm in names:
        st["declined"][nm] = int(st["declined"].get(nm, 0)) + 1
        if st["declined"][nm] >= _skill_decline_limit():
            stopped.append(nm)
    _skill_state_save()
    return stopped


def record_skill_use(name, weight=1):
    """จดว่า skill ถูกใช้จริง/ติดตั้งตามที่ผู้ใช้สั่ง — ใช้ตัดสิน 'ใช้บ่อย' และล้างการปฏิเสธเดิม"""
    nm = str(name or "").strip().lower()
    if not nm or not skill_name_ok(nm):
        return False
    try:
        st = _skill_state()
        st["used"][nm] = int(st["used"].get(nm, 0)) + max(1, int(weight or 1))
        st["declined"].pop(nm, None)
        _skill_state_save()
    except Exception:
        return False
    return True


def block_skill(name):
    """สั่ง 'หยุดเสนอทันที' โดยไม่ต้องรอปฏิเสธครบโควตา คืน (สำเร็จ, ข้อความ)"""
    nm = str(name or "").strip().lower()
    if not nm:
        return False, "ระบุชื่อ skill"
    if not is_catalog_skill(nm) and nm not in scan_skills():
        return False, f"ไม่รู้จัก skill: {nm} (ดูรายชื่อด้วย soonai skills catalog)"
    st = _skill_state()
    st["declined"][nm] = max(int(st["declined"].get(nm, 0)), _skill_decline_limit())
    _skill_state_save()
    return True, f"จะไม่เสนอติดตั้ง {nm} อีก — เปิดคืนด้วย: /skills reset {nm}"


def reset_skill_learning(name=None):
    """ล้างความจำ preference ทั้งหมด หรือเฉพาะชื่อเดียว คืนจำนวนรายการที่ล้าง"""
    st = _skill_state()
    if not name:
        n = len(st["declined"]) + len(st["used"])
        st["declined"].clear()
        st["used"].clear()
        _skill_state_save()
        return n
    nm = str(name).strip().lower()
    n = (1 if nm in st["declined"] else 0) + (1 if nm in st["used"] else 0)
    st["declined"].pop(nm, None)
    st["used"].pop(nm, None)
    _skill_state_save()
    return n


def skill_learning_table():
    """ตารางความเคยชินที่ระบบจำไว้ (ว่าง = None): อะไรใช้บ่อย · อะไรถูกปฏิเสธจนหยุดเสนอ"""
    st = _skill_state()
    if not st["declined"] and not st["used"]:
        return None
    lim = _skill_decline_limit()
    table = R.neo_table(title="skill ที่ระบบจำจากพฤติกรรมของคุณ")
    table.add_column("skill", style="cyan", no_wrap=True)
    table.add_column("ใช้ไป", style="white", no_wrap=True)
    table.add_column("ปฏิเสธ", style="white", no_wrap=True)
    table.add_column("ผลในตอนนี้", style="dim", no_wrap=True, max_width=44)
    for nm in sorted(set(st["declined"]) | set(st["used"])):
        dec, use = int(st["declined"].get(nm, 0)), int(st["used"].get(nm, 0))
        eff = []
        if use >= SKILL_FREQUENT_USE:
            eff.append("ใช้บ่อย — ดันอันดับก่อน + เสนอข้ามโฟลเดอร์")
        if dec >= lim:
            eff.append("หยุดเสนอ (reset เพื่อเปิดคืน)")
        table.add_row(nm, str(use) or "-", f"{dec}/{lim}", " · ".join(eff) or "-")
    return table


def frequent_skills_missing(limit=3):
    """skill ในแคตตาล็อกที่ผู้ใช้ใช้บ่อย แต่โฟลเดอร์นี้ยังไม่มี และยังไม่ถูกปฏิเสธ"""
    try:
        installed = set(scan_skills())
    except Exception:
        installed = set()
    out = []
    for nm in skill_catalog_names():
        if nm in installed or skill_is_declined(nm) or not skill_used_often(nm):
            continue
        out.append({"name": nm, "description": SKILL_CATALOG[nm][0], "used": skill_use_count(nm)})
    out.sort(key=lambda r: (-r["used"], r["name"]))
    return out[:max(1, int(limit))]


def carryover_skills(auto_yes=False):
    """เริ่มงานในโฟลเดอร์ที่ยังไม่มี skill ที่คุณใช้บ่อยที่อื่น → เสนอพกมาให้ (ขออนุญาตก่อนเสมอ)
    - interactive: y = ติดตั้งทั้งหมด · n = ไม่ (จดเป็นการปฏิเสธด้วย)
    - ไม่ interactive: ติดตั้งเองเฉพาะ auto_yes ไม่งั้นบอกคำสั่งให้ผู้ใช้
    คืน list ชื่อ skill ที่พร้อมใช้ในงานนี้"""
    if _SKILL_CARRYOVER["done"]:
        return []
    _SKILL_CARRYOVER["done"] = True
    try:
        if not _skill_suggest_enabled():
            return []
        cands = frequent_skills_missing()
    except Exception:
        return []
    if not cands:
        return []
    names = ", ".join(f"{c['name']} ({c['used']} ครั้ง)" for c in cands)
    R.console.print(f"[cyan]สกิลที่คุณใช้บ่อยยังไม่มีในโฟลเดอร์นี้:[/cyan] [bold]{names}[/bold]")
    if sys.stdin.isatty():
        try:
            ans = Prompt.ask("ติดตั้งมาใช้ในโฟลเดอร์นี้ด้วยไหม? (y=ติดตั้งทั้งหมด · n=ไม่)",
                             choices=["y", "n"], default="n")
        except (EOFError, KeyboardInterrupt):
            R.console.print()
            return []
        if ans != "y":
            stopped = record_skill_decline([c["name"] for c in cands])
            if stopped:
                R.console.print(f"[dim]จะไม่เสนอ {', '.join(stopped)} อีก (เปิดคืน: /skills reset)")
            return []
        picks = [c["name"] for c in cands]
    elif auto_yes:
        picks = [c["name"] for c in cands]
    else:
        R.console.print(f"[dim](บอกได้เลยว่าติดตั้งเลย: /skills add {cands[0]['name']})")
        return []
    ready = []
    for nm in picks:
        ok, msg = install_catalog_skill(nm)
        R.console.print(f"[green]{msg}[/green]" if ok else f"[dim]{msg}[/dim]")
        if ok or "อยู่แล้ว" in msg:
            ready.append(nm)
            record_skill_use(nm)
    if ready:
        try:
            R.agent_tools(refresh=True)
        except Exception:
            pass
        R.console.print(f"[green]พร้อมใช้ในโฟลเดอร์นี้: {', '.join(ready)}[/green]")
    return ready


# ── auto-suggest: งานที่กําลังทําตรงกับ skill ที่ยังไม่ติดตั้ง → เสนอพร้อมขออนุญาต ──
_SKILL_AUTOSUGGEST = {"asked": set()}  # ไม่เสนอซ้ำในเซสชันเดียวกัน


def _skill_suggest_enabled():
    if os.environ.get("SOONAI_NO_SKILL_SUGGEST"):
        return False
    try:
        return bool((R.load_config().get("agent") or {}).get("auto_skill", True))
    except Exception:
        return True


def skill_suggestions_for_task(task_text, limit=3):
    """skill ในแคตตาล็อกที่ตรงกับงานนี้และยังไม่ได้ติดตั้ง (ตรวจในเครื่องล้วน ไม่ยิงเน็ต)
    เคารพความเคยชินของผู้ใช้: ตัวที่เคยถูกปฏิเสธครบโควตาจะไม่ถูกเสนอ · ตัวที่ใช้บ่อยถูกดันขึ้นก่อน"""
    q = str(task_text or "").strip()
    if len(q) < 6:
        return []   # ข้อความสั้นเกินไป เสี่ยงเสนอผิดเรื่อง
    try:
        installed = set(scan_skills())
    except Exception:
        installed = set()
    out = []
    for r in search_catalog(q, limit=limit + 4, boost=skill_usage_boost):
        if not r.get("in_catalog"):
            continue
        if r["name"] in installed or r["name"] in _SKILL_AUTOSUGGEST["asked"]:
            continue
        if skill_is_declined(r["name"]):
            continue   # ผู้ใช้เคยปฏิเสธตัวนี้ซ้ำ ๆ → หยุดเสนอจนกว่าจะ /skills reset
        out.append(r)
        if len(out) >= limit:
            break
    return out


def _hint_use_skill(messages, names):
    """บอก agent ตรง ๆ ว่างานนี้เพิ่งติดตั้ง skill อะไรมาให้ — ให้อ่าน read_skill ก่อนลงมือ"""
    try:
        names = [n for n in (names or []) if n]
        if not names or not messages or messages[0].get("role") != "system":
            return messages
        tag = "[สกิลที่เพิ่งติดตั้งให้งานนี้]"
        if tag in (messages[0].get("content") or ""):
            return messages
        messages[0] = {"role": "system", "content": messages[0]["content"] +
                       f"\n{tag} {', '.join(names)} — เรียก read_skill('<ชื่อ>') อ่านวิธีทำก่อนลงมือ "
                       "เพราะผู้ใช้ติดตั้งไว้ให้ใช้กับงานนี้โดยเฉพาะ"}
    except Exception:
        pass
    return messages


def autosuggest_skill(task_text, auto_yes=False):
    """ตรวจงานที่กําลังเริ่มว่าตรงกับ skill ที่ยังไม่ติดตั้งไหม
    - interactive: ถามก่อนเสมอ (y = ตัวนั้น · a = ทุกตัวที่ตรง · n = ข้าม)
    - ไม่ interactive: ติดตั้งเองเฉพาะเมื่อ auto_yes (โหมด --yes/auto_approve)
    คืน list ชื่อ skill ที่พร้อมใช้ในงานนี้"""
    try:
        if not _skill_suggest_enabled():
            return []
        cands = skill_suggestions_for_task(task_text)
    except Exception:
        return []
    if not cands:
        return []
    top = cands[0]
    _often = f" · คุณใช้บ่อย ({skill_use_count(top['name'])} ครั้ง)" if skill_used_often(top["name"]) else ""
    R.console.print(f"[cyan]งานนี้ตรงกับสกิล[/cyan] [bold]{top['name']}[/bold] "
                  f"[dim]— {top['description'][:70]}{_often}[/dim]")
    if sys.stdin.isatty():
        try:
            ans = Prompt.ask("ติดตั้งสกิลนี้แล้วใช้เลยไหม? (y=ติดตั้ง · a=ทุกตัวที่ตรง · "
                             "n=ข้าม)", choices=["y", "a", "n"], default="n")
        except (EOFError, KeyboardInterrupt):
            R.console.print()
            return []
        if ans == "n":
            for c in cands:
                _SKILL_AUTOSUGGEST["asked"].add(c["name"])
            stopped = record_skill_decline([c["name"] for c in cands])
            if stopped:
                R.console.print(f"[dim]จดไว้ว่าปฏิเสธ {', '.join(stopped)} — จะไม่เสนออีก "
                              "(เปิดคืน: /skills reset <ชื่อ>)[/dim]")
            return []
        picks = [c["name"] for c in cands] if ans == "a" else [top["name"]]
    elif auto_yes:
        picks = [top["name"]]
    else:
        R.console.print(f"[dim](ไม่ได้ติดตั้งอัตโนมัติ — สั่งได้ด้วย /skills add {top['name']} "
                      "หรือ soonai skills add " + f"{top['name']})[/dim]")
        _SKILL_AUTOSUGGEST["asked"].add(top["name"])
        return []
    ready = []
    for nm in picks:
        _SKILL_AUTOSUGGEST["asked"].add(nm)
        ok, msg = install_catalog_skill(nm)
        R.console.print(f"[green]{msg}[/green]" if ok else f"[dim]{msg}[/dim]")
        if ok or "อยู่แล้ว" in msg:
            ready.append(nm)
            record_skill_use(nm)   # ติดตั้งเพราะจะใช้กับงานนี้ = สัญญาณว่าใช้จริง
    if ready:
        try:
            R.agent_tools(refresh=True)
        except Exception:
            pass
        R.console.print(f"[green]พร้อมใช้ในงานนี้: {', '.join(ready)}[/green]")
    return ready


def skills_find_flow(provider="", model="", question="", web=False, install_now=False,
                     force=False, use_ai=False):
    """ผู้ใช้พิมพ์คำค้น/ หรือเว้นว่างให้ AI ดูโปรเจกต์ — แล้วเสนอ + ติดตั้งให้เลือก
    คืนจำนวนที่ติดตั้ง"""
    q = str(question or "").strip()
    local = search_catalog(q, boost=skill_usage_boost) if q else []
    if local:
        table = R.neo_table(title=f"skill ที่ตรงกับ '{q}'")
        table.add_column("ชื่อ", style="cyan", no_wrap=True)
        table.add_column("ทำอะไร", style="white", no_wrap=True, max_width=46)
        table.add_column("ที่มา", style="dim", no_wrap=True)
        for r in local:
            src = "แคตตาล็อก" + (" · ติดตั้งแล้ว" if r["installed"] else "") if r["in_catalog"] \
                else "ติดตั้งอยู่แล้ว"
            if r.get("used"):
                src += f" · คุณใช้ {r['used']} ครั้ง"
            if r.get("declined"):
                src += " · หยุดเสนอ (reset เปิดคืน)"
            table.add_row(r["name"], (r["description"] or "")[:44], src)
        R.console.print(table)
    sugs = []
    want_ai = use_ai or q == "" or not local
    if want_ai and provider and model:
        with R.console.status("[cyan]กำลังให้ AI ดูโปรเจกต์…[/]", spinner="dots"):
            sugs = ai_suggest_skills(provider, model, q)
        if not sugs:
            R.console.print("[dim](AI ไม่ได้เสนออะไร — ลองพิมพ์คำค้นเอง หรือดูทั้งหมดด้วย "
                          "/skills catalog)[/dim]")
    if sugs:
        st = R.neo_table(title="AI เสนอ skill ที่เข้ากับโปรเจกต์นี้")
        st.add_column("ชื่อ", style="cyan", no_wrap=True)
        st.add_column("ทำอะไร", style="white", no_wrap=True, max_width=42)
        st.add_column("ทำไม", style="dim", no_wrap=True, max_width=38)
        st.add_column("สถานะ", style="dim", no_wrap=True)
        for s in sugs:
            status = ("ติดตั้งแล้ว" if s["installed"] else
                      ("ติดตั้งได้เลย" if s["in_catalog"] else "ต้องหาเพิ่ม"))
            st.add_row(s["name"], s["description"][:42], s["why"][:38], status)
        R.console.print(st)
        _missing = [s["name"] for s in sugs
                    if not s.get("in_catalog") and not s.get("installed")]
        if _missing and not web:
            R.console.print(f"[dim]ตัวที่ต้องหาเพิ่มเอง: {', '.join(_missing[:4])} — "
                          f"ลองค้นบน GitHub: soonai skills search \"{_missing[0]}\" --web[/dim]")
    if web:
        wq = q or (sugs[0]["name"] if sugs else "")
        if wq:
            with R.console.status("[cyan]กำลังค้น GitHub…[/]", spinner="dots"):
                rows, why = search_github_skills(wq)
            if why:
                R.console.print(f"[dim]{why}[/dim]")
            for r in rows:
                R.console.print(f"[cyan]{r['repo']}[/cyan] [dim]({r['path']})[/dim] "
                              f"{r['description'][:70]}\n  ติดตั้ง: soonai skills add {r['repo']}")
    installable = [r["name"] for r in local if r["in_catalog"] and not r["installed"]]
    installable += [s["name"] for s in sugs
                    if s.get("in_catalog") and not s.get("installed")]
    installable = list(dict.fromkeys(installable))
    _blocked = [nm for nm in installable if skill_is_declined(nm)]
    if _blocked:
        installable = [nm for nm in installable if nm not in _blocked]
        R.console.print(f"[dim]ข้ามตัวที่คุณเคยปฏิเสธ: {', '.join(_blocked)} "
                      "(เปิดคืน: /skills reset <ชื่อ>)[/dim]")
    if not installable:
        if _blocked:
            R.console.print("[dim]ไม่มีอะไรให้ติดตั้งเพิ่ม — ตัวที่ตรงคุณเคยปฏิเสธไว้ "
                          "(เปิดคืน: /skills reset <ชื่อ>)[/dim]")
        elif local or sugs:
            R.console.print("[dim]ทุกตัวที่ตรงติดตั้งอยู่แล้ว — ไม่มีอะไรต้องติดตั้ง[/dim]")
        else:
            R.console.print("[yellow]ไม่พบ skill ที่ตรง — ลองคำอื่น หรือใช้ /skills catalog "
                          "ดูทั้งหมด (สร้างเองได้ด้วย /skills new <ชื่อ>)[/yellow]")
        return 0
    if install_now:
        picks = installable
    elif sys.stdin.isatty():
        R.console.print("[dim]ติดตั้งตัวไหน? พิมพ์หมายเลข/ชื่อ คั่นด้วยวรรค · a = ทั้งหมด · Enter = ยังไม่ติดตั้ง[/dim]")
        for i, nm in enumerate(installable, 1):
            R.console.print(f"  [cyan]{i}[/cyan]. {nm}")
        try:
            ans = Prompt.ask("เลือก", default="").strip()
        except (EOFError, KeyboardInterrupt):
            R.console.print()
            return 0
        if not ans:
            return 0
        if ans.lower() in ("a", "all", "*"):
            picks = installable
        else:
            picks = []
            for tok in re.split(r"[\s,]+", ans):
                if not tok:
                    continue
                if tok.isdigit() and 1 <= int(tok) <= len(installable):
                    tok = installable[int(tok) - 1]
                if tok.strip().lower() in installable:
                    picks.append(tok.strip().lower())
    else:
        R.console.print("[dim]ติดตั้งได้ด้วย: soonai skills add <ชื่อ> (" +
                      ", ".join(installable[:6]) + ")[/dim]")
        return 0
    done = 0
    for nm in picks:
        ok, msg = install_catalog_skill(nm, force=force)
        if ok:
            done += 1
        R.console.print(f"[green]{msg}[/green]" if ok else f"[dim]{msg}[/dim]")
    if done:
        try:
            R.agent_tools(refresh=True)
        except Exception:
            pass
        R.console.print(f"[green]พร้อมใช้ {done} skill — บอกงานที่ตรงได้เลย[/green]")
    return done


def remove_skill(name):
    """ลบ skill ตามชื่อ (เจอที่ไหนลบที่นั่น) คืน (สำเร็จ, ข้อความ)"""
    import shutil
    key = str(name or "").strip()
    if not key:
        return False, "ระบุชื่อ skill"
    found = None
    for root in skills_dirs():
        try:
            cand = Path(root) / key
            if cand.is_dir() and (cand / "SKILL.md").is_file():
                found = cand
                break
        except Exception:
            pass
    if found is None:
        for _sk, info in scan_skills().items():
            if _sk == key:
                found = Path(info["path"])
                break
    if found is None:
        return False, f"ไม่พบ skill: {key}"
    try:
        shutil.rmtree(str(found))
    except Exception as e:
        return False, f"ลบไม่ได้: {e}"
    return True, f"ลบ skill {key} แล้ว"


def skills_table():
    """ตาราง skills ที่ติดตั้ง (ว่าง = None)"""
    sk = scan_skills()
    if not sk:
        return None
    table = R.neo_table(title=f"skills ที่ติดตั้ง ({len(sk)})")
    table.add_column("ชื่อ", style="cyan", no_wrap=True)
    table.add_column("คำอธิบาย", style="white", no_wrap=True, max_width=46)
    table.add_column("ที่", style="dim", no_wrap=True)
    for n in sorted(sk):
        desc = sk[n].get("description", "") or ""
        if len(desc) > 44:
            desc = desc[:43] + "…"
        table.add_row(n, desc, sk[n].get("scope", ""))
    return table


SKILL_TEMPLATE = """---
name: {name}
description: อธิบายสั้น ๆ ว่าจะใช้เมื่อไร (บรรทัดเดียว)
---

## ใช้เมื่อ
- งานลักษณะไหนที่ควรเปิด skill นี้

## ขั้นตอน
1. ตรวจของจริงก่อน (อ่านไฟล์/รันคําสั่ง) อย่าเดา
2. ลงมือทีละขั้น ตรวจผลทุกขั้น

## เสี่ยงที่ต้องเลี่ยง
- อะไรที่ห้ามทําในงานแบบนี้

## เกณฑ์เสร็จ
- วัดผลได้ว่าจบจริง
"""


def scaffold_skill(name, dest_root=None, force=False):
    """สร้างแม่แบบ SKILL.md ให้แก้ต่อ คืน (สำเร็จ, ข้อความ)"""
    nm = str(name or "").strip().lower()
    if not skill_name_ok(nm):
        return False, f"ชื่อ skill ต้องเป็น a-z 0-9 และ - เท่านั้น: {name!r}"
    root = Path(dest_root) if dest_root else Path(skills_dirs()[0])
    dest = root / nm
    try:
        if dest.exists() and not force:
            return False, f"มี {nm} อยู่แล้ว (ใช้ --force เพื่อเขียนทับ)"
        dest.mkdir(parents=True, exist_ok=True)
        md = dest / "SKILL.md"
        if md.exists() and not force:
            return False, f"มี {nm}/SKILL.md อยู่แล้ว"
        md.write_text(SKILL_TEMPLATE.format(name=nm), encoding="utf-8")
    except Exception as e:
        return False, f"สร้างไม่สําเร็จ: {e}"
    return True, f"สร้างแม่แบบ {md} แล้ว — แก้เนื้อหาในไฟล์ได้เลย"


def skills_install_menu(dest_root=None, force=False):
    """เมนูติดตั้ง skill จากแคตตาล็อก (กดหมายเลข / a = ทั้งหมด / Enter = ออก)
    ในโหมดไม่ interactive จะพิมพ์รายการ + คําสั่งสั่งเดียวแล้วออก"""
    scan_skills()                        # เตรียม/รีเฟรชข้อมูล skills ก่อนสร้างเมนู
    R.console.print(skill_catalog_table())
    R.console.print("[dim]ติดตั้งพร้อมกันหมด: [bold]soonai skills all[/bold] · "
                  "จากที่อื่น: [bold]soonai skills add owner/repo[/bold] · "
                  "สร้างเอง: [bold]soonai skills new <ชื่อ>[/bold][/dim]")
    if not sys.stdin.isatty():
        return 0
    try:
        ans = Prompt.ask("เลือกหมายเลข/ชื่อ skill (a = ทั้งหมด, Enter = ออก)", default="").strip()
    except (EOFError, KeyboardInterrupt):
        R.console.print()
        return 0
    if not ans:
        return 0
    names = skill_catalog_names()
    picks = []
    if ans.lower() in ("a", "all", "*"):
        picks = names
    else:
        for token in re.split(r"[\s,]+", ans):
            if not token:
                continue
            if token.isdigit() and 1 <= int(token) <= len(names):
                token = names[int(token) - 1]
            token = token.strip().lower()
            if token in names:
                picks.append(token)
            else:
                R.console.print(f"[yellow]ข้าม '{token}' (ไม่รู้จัก)[/yellow]")
    if not picks:
        R.console.print("[dim]ไม่มีอะไรถูกเลือก[/dim]")
        return 0
    done = 0
    for nm in picks:
        ok, msg = install_catalog_skill(nm, dest_root=dest_root, force=force)
        if ok:
            done += 1
        R.console.print(f"[green]{msg}[/green]" if ok else f"[dim]{msg}[/dim]")
    if done:
        try:
            R.agent_tools(refresh=True)
        except Exception:
            pass
        R.console.print(f"[green]พร้อมใช้ทันที {done} skill — ถามงานที่ตรงกับสกิลได้เลย[/green]")
    return 0


def cmd_skills(args, keys=None, cfg=None):
    """จัดการ skills เสริมให้ agent (CLI: soonai skills ...)
    ไม่ใส่คําสั่งเลย = เปิดเมนูติดตั้งจากแคตตาล็อกให้เลย"""
    action = (getattr(args, "action", None) or "list").lower()
    target = (getattr(args, "target", "") or "").strip()
    rest = list(getattr(args, "rest", []) or [])
    force = bool(getattr(args, "force", False))
    if action in ("add", "install"):
        if not target:
            R.console.print("[yellow]ใช้: soonai skills add <ชื่อในแคตตาล็อก/owner/repo/URL/โฟลเดอร์/.zip> "
                          "[ชื่อใหม่][/yellow]")
            R.console.print("[dim]หรือดูรายการที่ติดตั้งได้ทันที: soonai skills catalog[/dim]")
            return 1
        ok, msg = install_skill(target, rest[0] if rest else None, force=force)
        R.console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        if ok:
            try:
                R.agent_tools(refresh=True)
            except Exception:
                pass
        return 0 if ok else 1
    if action in ("find", "search", "suggest"):
        cfg = cfg if isinstance(cfg, dict) else {}
        prov = str(getattr(args, "provider", "") or cfg.get("provider") or "")
        mdl = str(getattr(args, "model", "") or cfg.get("model") or "")
        web = bool(getattr(args, "web", False))
        install_now = bool(getattr(args, "install", False))
        use_ai = bool(getattr(args, "ai", False))
        if not target and not sys.stdin.isatty():
            R.console.print("[dim]ไม่มีคำค้น — ให้ AI ดูโปรเจกต์แล้วเสนอ skill ให้[/dim]")
        skills_find_flow(prov, mdl, question=target, web=web, install_now=install_now,
                         force=force, use_ai=use_ai)
        return 0
    if action == "catalog":
        R.console.print(skill_catalog_table())
        R.console.print("[dim]ติดตั้งตัวเดียว: soonai skills add <ชื่อ> · "
                      "ทั้งหมด: soonai skills all[/dim]")
        return 0
    if action == "all":
        n, msg = install_catalog_all(force=force)
        # ติดตั้งครบอยู่แล้ว = ไม่ใช่ความผิดพลาด (บอกเฉย ๆ)
        R.console.print(f"[green]{msg}[/green]" if n else f"[dim]{msg}[/dim]")
        try:
            R.agent_tools(refresh=True)
        except Exception:
            pass
        return 0
    if action == "new":
        if not target:
            R.console.print("[yellow]ใช้: soonai skills new <ชื่อ> (a-z 0-9 -)[/yellow]")
            return 1
        ok, msg = scaffold_skill(target, force=force)
        R.console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        return 0 if ok else 1
    if action == "rm":
        if not target:
            R.console.print("[yellow]ใช้: soonai skills rm <ชื่อ>[/yellow]")
            return 1
        ok, msg = remove_skill(target)
        R.console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        if ok:
            R.console.print(f"[dim]ถ้าไม่อยากให้เสนอติดตั้งกลับ: soonai skills decline {target} "
                          "· ดูความจำทั้งหมด: soonai skills learning[/dim]")
        return 0 if ok else 1
    if action in ("learning", "prefs", "preference"):
        table = skill_learning_table()
        if table is None:
            R.console.print("[dim]ยังไม่มีความจำอะไร — ระบบจะจดเมื่อคุณใช้สกิลหรือปฏิเสธ "
                          "จนครบโควตา (ถ้าอยากให้เสนอน้อยลงตอนนี้เลย: soonai skills decline <ชื่อ>)[/dim]")
        else:
            R.console.print(table)
            R.console.print("[dim]ล้างความจำ: soonai skills reset [ชื่อ] · "
                          "หยุดเสนอทันที: soonai skills decline <ชื่อ>[/dim]")
        return 0
    if action in ("reset", "forget"):
        n = reset_skill_learning(target or None)
        where = f"ของ {target}" if target else "ทั้งหมด"
        R.console.print(f"[green]ล้างความจำ {where} แล้ว ({n} รายการ) — ระบบจะเสนอสกิลนั้นตามปกติ[/green]")
        return 0
    if action in ("decline", "block"):
        if not target:
            R.console.print("[yellow]ใช้: soonai skills decline <ชื่อ> (หยุดเสนอติดตั้งตัวนี้)[/yellow]")
            return 1
        ok, msg = block_skill(target)
        R.console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
        return 0 if ok else 1
    if action == "show":
        if not target:
            R.console.print("[yellow]ใช้: soonai skills show <ชื่อ>[/yellow]")
            return 1
        t = read_skill_text(target, max_chars=4000)
        if not t:
            R.console.print(f"[yellow]ไม่พบ skill: {target}[/yellow]")
            return 1
        R.console.print(Panel(t[:4000], title=f"skill: {target}", border_style="cyan"))
        return 0
    if action == "menu":
        return skills_install_menu(force=force)
    table = skills_table()
    if table is None:
        R.console.print("[dim]ยังไม่มี skills — ติดตั้งชุดแนะนําทันทีได้เลย:\n"
                      "  [bold]soonai skills all[/bold]        ติดตั้งทุกตัวจากแคตตาล็อกในตัว\n"
                      "  [bold]soonai skills[/bold]            เปิดเมนูเลือกติดตั้ง\n"
                      "  [bold]soonai skills add owner/repo[/bold]  จาก GitHub\n"
                      "  [bold]soonai skills new <ชื่อ>[/bold]     สร้างของเองใหม่[/dim]")
        R.console.print(skill_catalog_table())
        return 0
    R.console.print(table)
    R.console.print("[dim]อ่านฉบับเต็ม: soonai skills show <ชื่อ> · ลบ: soonai skills rm <ชื่อ> · "
                  "เพิ่ม: soonai skills add <ชื่อ/owner/repo/URL> · ทั้งชุด: soonai skills all[/dim]")
    return 0
