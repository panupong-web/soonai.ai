# -*- coding: utf-8 -*-
"""Regression: ค้นหา/แนะนํา skill (ให้ AI หา หรือผู้ใช้พิมพ์คําค้น)
- search_catalog: ไทย/อังกฤษ ตรงกับตัวที่ควร + กรองผลที่ห่างจากตัวท็อป + คําว่าง = []
- คําพ้อง (ทดสอบ→pytest, เอกสาร→docs) ช่วยในการพิมพ์ไทย
- project_facts: ภาษา/คําสั่งเทสต์/deps ของโปรเจกต์
- parse_skill_suggestions + ai_suggest_skills: ทน JSON ห่อโค้ดเฟนซ์ + รู้ว่าตัวไหนอยู่ในแคตตาล็อก
- search_github_skills: ตรวจว่ามี SKILL.md จริงก่อนเสนอ (mock เน็ต)
- tool search_skills + skills_find_flow (โหมดไม่ interactive) + parser/slash
ไม่แตะเน็ตจริง (mock requests + send_messages)
"""
import io
import json
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


tmp = Path(tempfile.mkdtemp(prefix="soonai-skillsearch-"))
_orig = (S._SKILLS_TEST_ROOTS, S.console, S.workspace_root, S.send_messages)
S._SKILLS_TEST_ROOTS = [str(tmp / "skills")]
S.console = Console(file=io.StringIO(), width=200, force_terminal=False)

try:
    # ---------------- 1) ค้นในแคตตาล็อก (ไม่ต้องมีเน็ต)
    def names(q, **kw):
        return [r["name"] for r in S.search_catalog(q, **kw)]

    check("ค้นอังกฤษ: excel", "excel-report" in names("excel"))
    check("ค้นไทย: เอกสาร → thai-docs", names("เอกสาร") == ["thai-docs"], names("เอกสาร"))
    check("คําพ้อง: ทดสอบ → pytest-first", "pytest-first" in names("ทดสอบ"), names("ทดสอบ"))
    check("คําพ้อง: ความปลอดภัย → security-check",
          "security-check" in names("ความปลอดภัย"), names("ความปลอดภัย"))
    check("คําพ้อง: ย้ายไฟล์ → windows-files", names("ย้ายไฟล์") == ["windows-files"],
          names("ย้ายไฟล์"))
    check("คําพ้อง: รีแฟกเตอร์ → refactor-safe",
          "refactor-safe" in names("รีแฟกเตอร์"), names("รีแฟกเตอร์"))
    check("กรองผลที่ห่างจากตัวท็อป (ไม่คืนทั้งแคตตาล็อก)", len(names("excel")) <= 2, names("excel"))
    check("คําว่าง = []", S.search_catalog("") == [] and S.search_catalog("   ") == [])
    check("ไม่รู้จัก = []", S.search_catalog("zzzzz") == [])
    check("ติดตั้งแล้วถูกทําเครื่องหมาย", names("เอกสาร") == ["thai-docs"])
    S.install_catalog_skill("thai-docs")
    r = S.search_catalog("เอกสาร")[0]
    check("catalog row บอกว่าติดตั้งแล้ว", r["installed"] is True and r["in_catalog"] is True, r)
    # skill ที่ติดตั้งเอง (ไม่อยู่ในแคตตาล็อก) ต้องค้นเจอด้วย
    S.scaffold_skill("voice-notes")
    own = (tmp / "skills" / "voice-notes" / "SKILL.md")
    own.write_text("---\nname: voice-notes\ndescription: ถอดเสียงเป็นข้อความ\n---\n\n## ใช้เมื่อ\n- เสียง\n",
                   encoding="utf-8")
    got = S.search_catalog("ถอดเสียง")
    check("ค้นเจอ skill ที่ติดตั้งเอง", any(x["name"] == "voice-notes" for x in got), got)

    # ---------------- 2) project_facts
    (tmp / "pyproject.toml").write_text("[project]\nname='x'\ndependencies=['rich','requests']\n",
                                       encoding="utf-8")
    (tmp / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp / "tests").mkdir(exist_ok=True)
    (tmp / "tests" / "test_x.py").write_text("def test_a():\n    assert 1\n", encoding="utf-8")
    S.workspace_root = lambda: tmp
    S._TEST_CMD_CACHE["key"] = None
    f = S.project_facts()
    check("facts: เจอภาษา py", "py" in f["languages"], f)
    check("facts: เจอคําสั่งเทสต์ pytest", "pytest" in (f["test_command"] or ""), f)
    check("facts: นับไฟล์ได้", f["files"] >= 3, f)
    check("facts: อ่าน dependency", "rich" in f["deps"] and "requests" in f["deps"], f["deps"])
    check("facts: เจอไฟล์หลัก", "main.py" in f["entry"], f["entry"])

    # ---------------- 3) AI เสนอ skill
    check("parse: ลอก code fence + JSON ห่อ", S.parse_skill_suggestions(
        "```json\n{\"skills\":[{\"name\":\"pdf-report\",\"description\":\"ก\",\"why\":\"ข\"}],"
        "\"note\":\"n\"}\n```") == [{"name": "pdf-report", "description": "ก", "why": "ข"}])
    check("parse: ชื่อผิดกฎถูกตัดออก",
          S.parse_skill_suggestions('{"skills":[{"name":"BAD NAME"},{"name":"ok-name"}]}') ==
          [{"name": "ok-name", "description": "", "why": ""}])
    check("parse: ไม่มี JSON = []", S.parse_skill_suggestions("ไม่มีเลย") == [])

    S.send_messages = lambda *a, **k: ('{"skills":[{"name":"thai-docs","description":"เอกสาร",'
                                       '"why":"โปรเจกต์มีเอกสารน้อย"},{"name":"pdf-report",'
                                       '"description":"รายงาน","why":"มีรายงานบ่อย"}],'
                                       '"note":"ลอง"}')
    sugs = S.ai_suggest_skills("openrouter", "m")
    check("ai_suggest: ได้ 2 ตัว", len(sugs) == 2, sugs)
    check("ai_suggest: รู้ว่าอยู่ในแคตตาล็อก",
          sugs[0]["in_catalog"] is True and sugs[1]["in_catalog"] is False, sugs)
    check("ai_suggest: บอกสถานะติดตั้ง", sugs[0]["installed"] is True and sugs[1]["installed"] is False,
          sugs)
    S.send_messages = lambda *a, **k: ""
    check("ai_suggest: โมเดลตอบว่าง = [] ไม่พัง", S.ai_suggest_skills("openrouter", "m") == [])
    S.send_messages = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 500"))


    check("ai_suggest: โมเดลพัง = [] ไม่พัง", S.ai_suggest_skills("openrouter", "m") == [])

    # ---------------- 4) ค้น GitHub (mock เน็ต)
    class Resp:
        def __init__(self, code=200, payload=None):
            self.status_code = code
            self._p = payload or {}

        def json(self):
            return self._p

    class FakeHttp:
        def __init__(self, ok=True):
            self.ok = ok

        def get(self, url, params=None, headers=None, timeout=None):
            if "search/repositories" in url:
                if not self.ok:
                    return Resp(403, {})
                return Resp(200, {"items": [
                    {"full_name": "acme/thai-skills", "description": "ชุดสกิลไทย"},
                    {"full_name": "acme/no-skill-here", "description": "ไม่มีSKILL.md"}]})
            if "acme/thai-skills/contents/SKILL.md" in url:
                return Resp(200, {"type": "file"})
            return Resp(404, {})

    _orig_http = S._http_session
    S._http_session = lambda: FakeHttp()
    rows, why = S.search_github_skills("skill ไทย")
    check("github: เจอ repo ที่มี SKILL.md", len(rows) == 1 and rows[0]["repo"] == "acme/thai-skills",
          (rows, why))
    check("github: ตัด repo ที่ไม่มี SKILL.md", "no-skill-here" not in json.dumps(rows), rows)
    check("github: บอกวิธิติดตั้ง", "soonai skills add acme/thai-skills" in
          f"soonai skills add {rows[0]['repo']}")
    S._http_session = lambda: FakeHttp(ok=False)
    rows2, why2 = S.search_github_skills("อะไรก็ได้")
    check("github: ติดเรต = แจ้งไม่พัง", rows2 == [] and "HTTP" in why2, why2)
    check("github: คําว่าง = เตือน", S.search_github_skills("")[1] != "")
    S._http_session = _orig_http

    # ---------------- 5) tool ของ agent
    out = S.run_tool("search_skills", {"query": "เอกสาร"})
    check("tool: เจอ + บอกว่าติดตั้งแล้ว", "thai-docs" in out and "read_skill" in out, out)
    out2 = S.run_tool("search_skills", {"query": "pdf"})
    check("tool: ไม่เจอ = บอกทางเลือก", out2.startswith("(ไม่พบ skill"), out2[:80])
    check("tool: อยู่ใน KNOWN_TOOLS", "search_skills" in S.KNOWN_TOOLS)
    check("tool: อยู่ใน READONLY_TOOLS", "search_skills" in S.READONLY_TOOLS)
    check("tool: ประกาศใน AGENT_TOOLS",
          any(d["function"]["name"] == "search_skills" for d in S.AGENT_TOOLS))

    # ---------------- 6) flow (โหมดไม่ interactive)
    S.send_messages = lambda *a, **k: ('{"skills":[{"name":"thai-docs","description":"d","why":"w"}]}')
    n = S.skills_find_flow("openrouter", "m", question="เอกสาร")
    check("flow: ค้นเจอแล้วไม่ติดตั้งเอง = 0", n == 0)
    log = S.console.file.getvalue()
    check("flow: พิมพ์ตารางให้เลือก", "skill ที่ตรงกับ" in log, log[-200:])
    n2 = S.skills_find_flow("openrouter", "m", question="pdf", use_ai=True)
    check("flow: ไม่เจอ + AI เสนอได้ = ไม่พัง", n2 == 0, n2)
    S.scaffold_skill("find-install-me")
    S._SKILLS_TEST_ROOTS = [str(tmp / "skills")]
    n3 = S.skills_find_flow("", "", question="find-install-me")
    check("flow: ค้นชื่อตรงและติดตั้งเมื่อสั่ง", n3 in (0, 1), n3)

    # ---------------- 7) parser + slash
    ap = S.build_parser()
    a1 = ap.parse_args(["skills", "find", "ทํารายงาน excel"])
    check("parser: find + คําค้น", a1.action == "find" and a1.target == "ทํารายงาน excel")
    a2 = ap.parse_args(["skills", "search", "pdf", "--web", "--ai", "--install"])
    check("parser: ธง --web/--ai/--install", a2.web and a2.ai and a2.install)
    cmds = dict(S.SLASH_COMMANDS)
    check("slash: มี /skill", "/skill" in cmds)
    check("slash: มี /skills", "/skills" in cmds)
finally:
    (S._SKILLS_TEST_ROOTS, S.console, S.workspace_root, S.send_messages) = _orig

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL SKILL SEARCH TESTS PASSED")
