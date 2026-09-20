# -*- coding: utf-8 -*-
"""Regression: ระบบเรียนรู้ preference ของผู้ใช้ (skill)
- ปฏิเสธซ้ำ ๆ = หยุดเสนอ (นับสะสม เก็บถาวรในไฟล์ ไม่หายเมื่อเปิดโปรแกรมใหม่)
- ใช้จริง (read_skill / ติดตั้งตามที่ผู้ใช้สั่ง) = ใช้บ่อย → ดันอันดับก่อน + พกข้ามโฟลเดอร์
- /skills learning|reset|decline (+CLI) และ tool install_skill/search_skills เคารพ preference
- เทสต์ใช้ไฟล์ state ใน temp (SOONAI_SKILL_STATE) และ skill roots ใน temp เท่านั้น
ไม่แตะไฟล์ของผู้ใช้จริง/ไม่แตะเน็ต
"""
import argparse
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

# ความจำ preference ต้องไม่ไปแตะไฟล์จริงของผู้ใช้
_STATE_TMP = tempfile.mkdtemp(prefix="soonai-learn-state-")
os.environ["SOONAI_SKILL_STATE"] = str(Path(_STATE_TMP) / "skills_state.json")
_STATE_FILE = Path(os.environ["SOONAI_SKILL_STATE"])

from rich.console import Console  # noqa: E402

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


class FakeTty(io.StringIO):
    def isatty(self):
        return True


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload or {}
        self.text = json.dumps(self._p)

    def json(self):
        return self._p


def fresh_root(tag):
    p = Path(tempfile.mkdtemp(prefix=f"soonai-learn-{tag}-"))
    S._SKILLS_TEST_ROOTS = [str(p)]
    return p


def run_cli(**kw):
    ns = argparse.Namespace(action=kw.get("action", "list"), target=kw.get("target", ""),
                            rest=[], force=False)
    return S.cmd_skills(ns, None, {})


_orig = (S._SKILLS_TEST_ROOTS, S.console, S.load_config, S.Prompt)
S.console = Console(file=io.StringIO(), width=200, force_terminal=False)
S.load_config = lambda: {"agent": {"auto_skill": True}}
fresh_root("base")

try:
    # ---------------- 1) ชั้นความจำ (นับสะสม + เก็บถาวร)
    S.reset_skill_learning()
    check("เริ่มจากว่าง", S.skill_decline_count("thai-docs") == 0 and
          S.skill_use_count("thai-docs") == 0)
    check("ปฏิเสธครั้งเดียว = ยังไม่หยุดเสนอ",
          S.record_skill_decline(["thai-docs"]) == [] and S.skill_is_declined("thai-docs") is False)
    check("ปฏิเสธครบโควตา = หยุดเสนอ",
          S.record_skill_decline(["thai-docs"]) == ["thai-docs"] and
          S.skill_is_declined("thai-docs") is True)
    check("นับสะสมต่อเนื่อง", S.skill_decline_count("thai-docs") == 2)
    S._SKILL_STATE["data"] = None          # จำลองเปิดโปรแกรมใหม่
    check("ความจำคงอยู่หลังเปิดใหม่", S.skill_is_declined("thai-docs") is True)
    check("เขียนไฟล์ state จริง", _STATE_FILE.is_file())
    _STATE_FILE.write_text("{ไฟล์พัง", encoding="utf-8")
    S._SKILL_STATE["data"] = None
    check("ไฟล์พัง = เริ่มใหม่ ไม่ crash",
          S.skill_learning_table() is None and S.skill_decline_count("thai-docs") == 0)

    check("ชื่อซ้ำ/ตัวพิมพ์ใหญ่ถูกทำให้เป็นมาตรฐาน",
          S.record_skill_decline(["Thai-Docs"]) == [] and S.skill_decline_count("thai-docs") == 1)
    S.load_config = lambda: {"agent": {"auto_skill": True, "skill_decline_limit": 1}}
    S.reset_skill_learning()
    check("config: skill_decline_limit=1 → ปฏิเสธครั้งเดียวก็หยุดเสนอ",
          S.record_skill_decline(["thai-docs"]) == ["thai-docs"] and
          S.skill_is_declined("thai-docs") is True)
    S.load_config = lambda: {"agent": {"auto_skill": True, "skill_decline_limit": "มาก"}}
    check("config ค่าเพี้ยน = ใช้ค่าเริ่มต้น", S._skill_decline_limit() == S.SKILL_DECLINE_LIMIT)
    S.load_config = lambda: {"agent": {"auto_skill": True}}
    S.reset_skill_learning()

    # ---------------- 2) การใช้จริง → ใช้บ่อย
    S.reset_skill_learning()
    S.record_skill_use("pytest-first")
    check("ใช้ 1 ครั้ง = ยังไม่ 'บ่อย'", S.skill_used_often("pytest-first") is False)
    S.record_skill_use("pytest-first")
    check("ใช้ครบโควตา = 'ใช้บ่อย'", S.skill_used_often("pytest-first") is True)
    check("ให้คะแนนพิเศษตามจำนวนครั้ง (เพดาน +12)", S.skill_usage_boost("pytest-first") == 4)
    for _ in range(10):
        S.record_skill_use("pytest-first")
    check("เพดาน boost ไม่เกิน 12", S.skill_usage_boost("pytest-first") == 12)
    check("ชื่อผิดรูปแบบไม่ถูกจด", S.record_skill_use("ไม่ ใช่ ชื่อ") is False)
    S.record_skill_decline(["pytest-first"])
    S.record_skill_decline(["pytest-first"])
    check("ถูกปฏิเสธก่อนหน้า", S.skill_is_declined("pytest-first") is True)
    S.record_skill_use("pytest-first")
    check("ใช้สกิลอีกครั้ง = ล้างการปฏิเสธเดิม", S.skill_is_declined("pytest-first") is False)
    check("block: หยุดเสนอทันทีโดยไม่รอครบโควตา",
          S.block_skill("excel-report")[0] is True and S.skill_is_declined("excel-report") is True)
    check("block: ชื่อที่ไม่รู้จักถูกปฏิเสธ", S.block_skill("ไม่มีสกิลนี้")[0] is False)
    check("reset ตัวเดียว = เปิดคืนเฉพาะตัวนั้น",
          S.reset_skill_learning("excel-report") >= 1 and
          S.skill_is_declined("excel-report") is False)
    _c = Console(file=io.StringIO(), width=200, force_terminal=False)
    _c.print(S.skill_learning_table())
    check("ตารางความจำแสดงสถานะที่จดไว้",
          "pytest-first" in _c.file.getvalue() and "ใช้บ่อย" in _c.file.getvalue(),
          _c.file.getvalue()[:200])

    # ---------------- 3) ไม่เสนอตัวที่เคยถูกปฏิเสธ + เสนอคืนหลัง reset
    S.reset_skill_learning()
    S._SKILL_AUTOSUGGEST["asked"].clear()
    names0 = [r["name"] for r in S.skill_suggestions_for_task("ช่วยเขียนเอกสาร README ให้อ่านง่าย")]
    check("ปกติเสนอ thai-docs", names0[:1] == ["thai-docs"], names0)
    check("แถวผลมีข้อมูล used/declined",
          all("used" in r and "declined" in r for r in S.search_catalog("เอกสาร")))
    S.record_skill_decline(["thai-docs"])
    S.record_skill_decline(["thai-docs"])
    check("เคยปฏิเสธครบโควตา = ไม่เสนออีก",
          "thai-docs" not in [r["name"] for r in S.skill_suggestions_for_task("ช่วยเขียนเอกสาร README")])
    S.reset_skill_learning("thai-docs")
    names2 = [r["name"] for r in S.skill_suggestions_for_task("ช่วยเขียนเอกสาร README ให้อ่านง่าย")]
    check("reset แล้วเสนอคืน", names2[:1] == ["thai-docs"], names2)

    # ---------------- 4) boost ดันอันดับ โดยไม่ลดความแม่น
    # เพิ่มสกิลเทียมเพื่อให้มีหลายแถวเทียบ (ค้นจริงตามปกติมักเหลือตัวเดียวหลังกรอง)
    _cat_backup = dict(S.SKILL_CATALOG)
    try:
        S.SKILL_CATALOG["doc-extra"] = ("เอกสาร docs เสริม อีกตัว", "เอกสาร docs เสริม\n")
        S.SKILL_CATALOG["doc-weak"] = ("เอกสาร docs ทั่วไป", "เอกสาร docs\n")
        plain = [r["name"] for r in S.search_catalog("เอกสาร")]
        check("มีหลายตัวให้เทียบ", len(plain) >= 2, plain)
        boosted = [r["name"] for r in S.search_catalog(
            "เอกสาร", boost=lambda n: 99 if n == plain[-1] else 0)]
        check("boost: ตัวท้ายสุดถูกดันขึ้นก่อน", boosted[:1] == [plain[-1]], (plain, boosted))
        check("boost: ชุดผลเท่าเดิม (กรองด้วยคะแนนพื้นฐาน)",
              set(boosted) == set(plain), (plain, boosted))
        check("boost: แถวที่ถูกดันบอกคะแนนพิเศษ",
              S.search_catalog("เอกสาร", boost=lambda n: 99 if n == plain[-1] else 0)[0]["boost"] == 99)
    finally:
        S.SKILL_CATALOG.clear()
        S.SKILL_CATALOG.update(_cat_backup)
    S.reset_skill_learning()
    for _ in range(3):
        S.record_skill_use("thai-docs")
    used_rows = S.search_catalog("เอกสาร", boost=S.skill_usage_boost)
    check("boost จากประวัติ: ตัวที่ใช้บ่อยมาก่อน", used_rows[0]["name"] == "thai-docs", used_rows[:2])

    # ---------------- 5) ปฏิเสธใน auto-suggest → ครั้งที่ 3 ไม่ถามอีกเลย
    S.reset_skill_learning()
    S._SKILL_AUTOSUGGEST["asked"].clear()
    S._SKILL_CARRYOVER["done"] = True          # ไม่ให้ carryover ยิง Statement ซ้อนในเทสต์นี้
    _orig_stdin = sys.stdin
    sys.stdin = FakeTty()
    S.Prompt = argparse.Namespace(ask=lambda *a, **k: "n")
    try:
        r1 = S.autosuggest_skill("ทำรายงาน excel จาก csv")
        check("n ครั้งแรก = ไม่ติดตั้ง + จดปฏิเสธ",
              r1 == [] and S.skill_decline_count("excel-report") == 1)
        check("เซสชันเดียวกัน = ไม่ถามซ้ำ", S.autosuggest_skill("ทำรายงาน excel จาก csv") == [] and
              S.skill_decline_count("excel-report") == 1)
        S._SKILL_AUTOSUGGEST["asked"].clear()      # จำลองเปิดเซสชันใหม่
        r2 = S.autosuggest_skill("ทำรายงาน excel จาก csv")
        check("ปฏิเสธซ้ำในเซสชันถัดไป = ครบโควตา",
              r2 == [] and S.skill_is_declined("excel-report") is True)
        check("บอกผู้ใช้ว่าจะไม่เสนออีก", "จะไม่เสนออีก" in S.console.file.getvalue())
        S.Prompt = argparse.Namespace(
            ask=lambda *a, **k: (_ for _ in ()).throw(AssertionError("ไม่ควรถามอีก")))
        check("ปฏิเสธครบโควตา = ไม่แม้แต่จะถาม", S.autosuggest_skill("ทำรายงาน excel จาก csv") == [])
    finally:
        sys.stdin = _orig_stdin
        S.Prompt = _orig[3]
    S.reset_skill_learning()
    S._SKILL_AUTOSUGGEST["asked"].clear()

    # ---------------- 6) ติดตั้งผ่าน auto-suggest/อ่านสกิล = สัญญาณว่าใช้จริง
    root_a = fresh_root("use")
    ready = S.autosuggest_skill("ย้ายไฟล์รูปไปโฟลเดอร์ใหม่", auto_yes=True)
    check("auto_yes ติดตั้ง + จดว่าใช้",
          ready == ["windows-files"] and S.skill_use_count("windows-files") == 1, ready)
    msg = S.run_tool("read_skill", {"name": "windows-files"})
    check("read_skill คืนเนื้อหา", "## ขั้นตอน" in msg, msg[:80])
    check("อ่านสกิลจริง = นับการใช้เพิ่ม + เป็น 'ใช้บ่อย'",
          S.skill_use_count("windows-files") >= 2 and S.skill_used_often("windows-files"))
    bad = S.run_tool("read_skill", {"name": "ไม่มีจริง"})
    check("read_skill ที่ไม่มี = ERROR และไม่จด",
          bad.startswith("ERROR:") and S.skill_use_count("ไม่มีจริง") == 0)
    check("ไฟล์ถูกติดตั้งจริง", (root_a / "windows-files" / "SKILL.md").is_file())

    # ---------------- 7) tool install_skill เคารพ 'หยุดเสนอ'
    fresh_root("tool")
    S.block_skill("pytest-first")
    g = S.run_tool("install_skill", {"name": "pytest-first"})
    check("tool: สกิลที่หยุดเสนอ = ปฏิเสธ พร้อมทางเปิดคืน",
          g.startswith("ERROR:") and "reset" in g, g)
    check("tool: ไม่ได้ติดตั้งให้", not (Path(S._SKILLS_TEST_ROOTS[0]) / "pytest-first").exists())
    S.reset_skill_learning("pytest-first")
    g2 = S.run_tool("install_skill", {"name": "pytest-first"})
    check("reset แล้วติดตั้งได้ตามปกติ", g2.startswith("ติดตั้ง pytest-first"), g2)

    # ---------------- 8) พกสกิลที่ใช้บ่อยข้ามโฟลเดอร์ (carryover)
    S.reset_skill_learning()
    fresh_root("carry")
    for _ in range(3):
        S.record_skill_use("thai-docs")
    S._SKILL_CARRYOVER["done"] = False
    check("ไม่ interactive + ไม่ auto_yes = ไม่ติดตั้งเอง", S.carryover_skills() == [])
    log = S.console.file.getvalue()
    check("บอกว่าสกิลที่ใช้บ่อยยังไม่มีในโฟลเดอร์นี้ + คำสั่งให้ผู้ใช้",
          "ใช้บ่อยยังไม่มีในโฟลเดอร์นี้" in log and "/skills add thai-docs" in log, log[-300:])
    check("เสนอครั้งเดียวต่อเซสชัน", S.carryover_skills() == [])
    S._SKILL_CARRYOVER["done"] = False
    carried = S.carryover_skills(auto_yes=True)
    check("auto_yes = ติดตั้งให้เลย", carried == ["thai-docs"], carried)
    check("ติดตั้งจริง + จดว่าใช้",
          (Path(S._SKILLS_TEST_ROOTS[0]) / "thai-docs" / "SKILL.md").is_file() and
          S.skill_use_count("thai-docs") >= 4)
    S._SKILL_CARRYOVER["done"] = False
    check("ติดตั้งแล้ว = ไม่เสนอซ้ำ", S.carryover_skills(auto_yes=True) == [])

    S.reset_skill_learning()
    fresh_root("carry2")
    for _ in range(3):
        S.record_skill_use("excel-report")
    S.block_skill("excel-report")
    S._SKILL_CARRYOVER["done"] = False
    check("ตัวที่หยุดเสนอ = ไม่ถูกพกข้ามโฟลเดอร์", S.carryover_skills(auto_yes=True) == [])

    S.reset_skill_learning()
    fresh_root("carry3")
    for _ in range(2):
        S.record_skill_use("pytest-first")
    S._SKILL_CARRYOVER["done"] = False
    sys.stdin = FakeTty()
    S.Prompt = argparse.Namespace(ask=lambda *a, **k: "n")
    try:
        check("interactive n = ไม่ติดตั้ง + จดปฏิเสธ",
              S.carryover_skills() == [] and S.skill_decline_count("pytest-first") == 1)
    finally:
        sys.stdin = _orig_stdin
        S.Prompt = _orig[3]

    # ---------------- 9) CLI + parser + ตาราง/คำสั่ง
    S.reset_skill_learning()
    check("cli learning = 0", run_cli(action="learning") == 0)
    check("cli learning บอกว่ายังว่าง", "ยังไม่มีความจำ" in S.console.file.getvalue())
    check("cli decline ไม่มีชื่อ = 1", run_cli(action="decline") == 1)
    check("cli decline = 0", run_cli(action="decline", target="security-check") == 0 and
          S.skill_is_declined("security-check"))
    check("cli decline บอกทางเปิดคืน", "จะไม่เสนอติดตั้ง security-check อีก" in S.console.file.getvalue())
    check("cli reset ตัวเดียว = 0", run_cli(action="reset", target="security-check") == 0 and
          S.skill_is_declined("security-check") is False)
    check("cli reset ทั้งหมด = 0", run_cli(action="reset") == 0)
    check("cli forget = alias ของ reset", run_cli(action="forget") == 0)
    S.console.print(S.skill_catalog_table())
    S.block_skill("refactor-safe")
    S.console = Console(file=io.StringIO(), width=200, force_terminal=False)
    S.console.print(S.skill_catalog_table())
    check("catalog table: ทำเครื่องหมายตัวที่หยุดเสนอ",
          "หยุดเสนอ" in S.console.file.getvalue())

    par = S.build_parser()
    check("parser: skills learning", par.parse_args(["skills", "learning"]).action == "learning")
    check("parser: skills decline <ชื่อ>",
          par.parse_args(["skills", "decline", "thai-docs"]).target == "thai-docs")
    check("parser: skills reset", par.parse_args(["skills", "reset"]).action == "reset")
    cmds = dict(S.SLASH_COMMANDS)
    check("slash: /skills พูดถึง learning",
          "learning" in cmds.get("/skills", ""), cmds.get("/skills", ""))

    # search_skills ต้องเตือน agent ไม่ให้เสนอตัวที่ผู้ใช้ปฏิเสธ
    S.block_skill("security-check")
    out = S.run_tool("search_skills", {"query": "ความปลอดภัย security ตรวจ secrets"})
    check("tool search_skills: เตือน 'อย่าเสนอซ้ำ' กับตัวที่หยุดเสนอ",
          "security-check" in out and "ปฏิเสธ" in out, out[:200])

    # ---------------- 10) agent_chat: พกสกิล (carryover) + ตรงงาน รวม hint ไม่ซ้ำ
    fresh_root("chat")
    S.reset_skill_learning()
    calls = []
    _mocks = (S.carryover_skills, S.autosuggest_skill, S._attach_symbol_map, S._post_chat)
    S.carryover_skills = lambda auto_yes=False: (calls.append("carry") or ["thai-docs"])
    S.autosuggest_skill = lambda task, auto_yes=False: (calls.append(task) or ["thai-docs", "pytest-first"])
    S._attach_symbol_map = lambda m, **k: m
    payloads = []

    def _post(url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        payloads.append(payload)
        return Resp(200, {"choices": [{"message": {"content": "เสร็จแล้ว"},
                                       "finish_reason": "stop"}]})

    S._post_chat = _post
    _approve_orig = S.approve
    S.approve = lambda *a, **k: True
    try:
        out, err, used, info = S.agent_chat(
            "openrouter", "m-test",
            [{"role": "system", "content": "sys"},
             {"role": "user", "content": "ช่วยเขียนเอกสารให้อ่านง่าย"}],
            0.2, auto_yes=True, max_steps=1)
    finally:
        (S.carryover_skills, S.autosuggest_skill, S._attach_symbol_map, S._post_chat) = _mocks
        S.approve = _approve_orig
    check("agent_chat: พกสกิลก่อน แล้วค่อยดูงานที่ตรง", calls[:1] == ["carry"], calls)
    sys_txt = (payloads[0].get("messages") or [{}])[0].get("content", "") if payloads else ""
    check("agent_chat: hint มีชื่อสกิล",
          "read_skill" in sys_txt and "thai-docs" in sys_txt and "pytest-first" in sys_txt, sys_txt[-200:])
    check("agent_chat: ชื่อซ้ำถูกยุบเหลือครั้งเดียว", sys_txt.count("thai-docs") == 1, sys_txt[-200:])
    check("agent_chat: จบงานปกติ", out == "เสร็จแล้ว" and err == "", (out, err))
finally:
    (S._SKILLS_TEST_ROOTS, S.console, S.load_config, S.Prompt) = _orig
    os.environ.pop("SOONAI_NO_SKILL_SUGGEST", None)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL SKILL LEARNING TESTS PASSED")
