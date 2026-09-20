# -*- coding: utf-8 -*-
"""Regression: auto-suggest skill ตอน agent เริ่มงาน
- ตรวจจับงานที่ตรงกับ skill ที่ยังไม่ติดตั้ง (ในเครื่องล้วน ไม่ยิงเน็ต)
- ขออนุญาตก่อนติดตั้งเสมอ (approve ปฏิเสธเมื่อไม่ interactive และไม่ได้ auto_yes)
- โหมด interactive: y = ตัวที่เสนอ · a = ทุกตัว · n = ข้าม (แล้วไม่ถามซ้ำในเซสชัน)
- โหมดไม่ interactive: ติดตั้งเองเฉพาะ auto_yes ไม่งั้นบอกคำสั่งให้ผู้ใช้
- agent_chat: เรียก auto-suggest ก่อนเริ่ม และบอก agent ให้ read_skill ก่อนลงมือ
- tool install_skill: ติดตั้งได้/ติดตั้งอยู่แล้ว/ชื่อผิด = ERROR พร้อมทางเลือก
ไม่แตะเน็ต/ไม่แตะ shared/skills ของจริง
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

# ความจำ preference (ปฏิเสธ/ใช้บ่อย) ต้องไม่ไปแตะไฟล์จริงของผู้ใช้
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


tmp = Path(tempfile.mkdtemp(prefix="soonai-autoskill-"))
roots = [str(tmp / "skills")]
_orig = (S._SKILLS_TEST_ROOTS, S.console, S.load_config, S.Prompt)
S._SKILLS_TEST_ROOTS = roots
S.console = Console(file=io.StringIO(), width=200, force_terminal=False)
S.load_config = lambda: {"agent": {"auto_skill": True}}


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

    def close(self):
        pass


try:
    # ---------------- 1) ตรวจจับงาน
    check("งานเรื่องเอกสาร → thai-docs",
          [r["name"] for r in S.skill_suggestions_for_task("ช่วยเขียนเอกสาร README ให้อ่านง่าย")][:1]
          == ["thai-docs"], S.skill_suggestions_for_task("ช่วยเขียนเอกสาร README ให้อ่านง่าย"))
    check("งานจัดโค้ด → refactor-safe มาก่อน",
          [r["name"] for r in S.skill_suggestions_for_task("จัดโค้ดใหม่ให้อ่านง่าย")][:1]
          == ["refactor-safe"])
    check("งานเทสต์ → pytest-first",
          [r["name"] for r in S.skill_suggestions_for_task("รันเทสต์แล้วแก้ให้ผ่าน")][:1]
          == ["pytest-first"])
    check("ข้อความสั้นเกินไป = ไม่เสนอ", S.skill_suggestions_for_task("สวัสดี") == [])
    check("คําว่าง = ไม่เสนอ", S.skill_suggestions_for_task("") == [])
    check("รันไม่เกิน limit", len(S.skill_suggestions_for_task("เอกสาร รายงาน เทสต์ ไฟล์", limit=2)) <= 2)

    # ติดตั้งแล้ว = ไม่เสนอซ้ำ
    S.install_catalog_skill("thai-docs")
    check("ติดตั้งแล้วไม่เสนออีก",
          "thai-docs" not in [r["name"] for r in S.skill_suggestions_for_task("ช่วยเขียนเอกสาร")])
    # ที่เคยถูกปฏิเสธ = ไม่ถามซ้ำในเซสชัน
    S._SKILL_AUTOSUGGEST["asked"].add("pytest-first")
    check("ที่เคยข้าม = ไม่เสนอในเซสชันนี้",
          "pytest-first" not in [r["name"] for r in S.skill_suggestions_for_task("รันเทสต์แล้วแก้")])
    S._SKILL_AUTOSUGGEST["asked"].clear()

    # ---------------- 2) สวิตช์ปิด
    check("เปิดเป็นค่าเริ่มต้น", S._skill_suggest_enabled() is True)
    os.environ["SOONAI_NO_SKILL_SUGGEST"] = "1"
    check("ปิดด้วย env", S._skill_suggest_enabled() is False and
          S.autosuggest_skill("ช่วยเขียนเอกสารให้อ่านง่าย") == [])
    os.environ.pop("SOONAI_NO_SKILL_SUGGEST", None)
    S.load_config = lambda: {"agent": {"auto_skill": False}}
    check("ปิดด้วย config", S._skill_suggest_enabled() is False and
          S.autosuggest_skill("ช่วยเขียนเอกสารให้อ่านง่าย") == [])
    S.load_config = lambda: {"agent": {"auto_skill": True}}

    # ---------------- 3) โหมดไม่ interactive
    got = S.autosuggest_skill("ช่วยเขียนเอกสาร README ฉบับละเอียด")   # thai-docs ติดตั้งแล้ว
    check("ตัวที่ติดตั้งแล้วไม่ถูกเสนอ (ได้ตัวถัดไปหรือว่าง)",
          all(n != "thai-docs" for n in got), got)
    got2 = S.autosuggest_skill("ย้ายไฟล์รูปไปโฟลเดอร์ใหม่")
    check("ไม่ interactive + ไม่ auto_yes = ไม่ติดตั้งเอง", got2 == [], got2)
    log = S.console.file.getvalue()
    check("บอกคําสั่งติดตั้งให้ผู้ใช้", "/skills add windows-files" in log, log[-200:])
    check("จดว่าถามแล้ว (ไม่ถามซ้ำ)",
          "windows-files" in S._SKILL_AUTOSUGGEST["asked"], S._SKILL_AUTOSUGGEST["asked"])
    check("เรียกซ้ำ = ว่าง", S.autosuggest_skill("ย้ายไฟล์รูปไปโฟลเดอร์ใหม่") == [])

    S._SKILL_AUTOSUGGEST["asked"].clear()
    ready = S.autosuggest_skill("ย้ายไฟล์รูปไปโฟลเดอร์ใหม่", auto_yes=True)
    check("auto_yes = ติดตั้งให้เลย", ready == ["windows-files"], ready)
    check("ไฟล์ SKILL.md ถูกสร้าง", (Path(roots[0]) / "windows-files" / "SKILL.md").is_file())
    check("ติดตั้งแล้วไม่เสนอซ้ำอัตโนมัติ", S.autosuggest_skill("ย้ายไฟล์อีก", auto_yes=True) == [])

    # ---------------- 4) โหมด interactive (ถามก่อน)
    S._SKILL_AUTOSUGGEST["asked"].clear()
    _orig_stdin = sys.stdin
    sys.stdin = FakeTty()
    S.Prompt = argparse.Namespace(ask=lambda *a, **k: "y")
    try:
        ok_y = S.autosuggest_skill("ทำรายงาน excel จาก csv")
        check("interactive y = ติดตั้งตัวที่เสนอ", ok_y == ["excel-report"], ok_y)
        check("ไฟล์ถูกสร้าง", (Path(roots[0]) / "excel-report" / "SKILL.md").is_file())

        S._SKILL_AUTOSUGGEST["asked"].clear()
        S.Prompt = argparse.Namespace(ask=lambda *a, **k: "n")
        ok_n = S.autosuggest_skill("งานทดสอบโค้ดให้ผ่าน")
        check("interactive n = ไม่ติดตั้ง", ok_n == [])
        check("n แล้วจดว่าถามแล้ว (ไม่กวนซ้ำ)",
              "pytest-first" in S._SKILL_AUTOSUGGEST["asked"], S._SKILL_AUTOSUGGEST["asked"])

        S._SKILL_AUTOSUGGEST["asked"].clear()
        S.Prompt = argparse.Namespace(ask=lambda *a, **k: "a")
        ok_a = S.autosuggest_skill("งานทดสอบและทำรายงานเอกสารไฟล์")
        check("interactive a = ติดตั้งทุกตัวที่ตรง", len(ok_a) >= 1, ok_a)
    finally:
        sys.stdin = _orig_stdin
        S.Prompt = _orig[3]
    S._SKILL_AUTOSUGGEST["asked"].clear()

    # ---------------- 5) hint ให้ agent อ่านสกิล
    msgs = [{"role": "system", "content": "sys"}]
    S._hint_use_skill(msgs, ["thai-docs"])
    check("hint: ใส่ชื่อสกิล", "thai-docs" in msgs[0]["content"] and "read_skill" in msgs[0]["content"],
          msgs[0]["content"][:160])
    before = msgs[0]["content"]
    S._hint_use_skill(msgs, ["thai-docs"])
    check("hint: ไม่ใส่ซ้ำ", msgs[0]["content"] == before)
    check("hint: ไม่มี system = ไม่พัง",
          S._hint_use_skill([{"role": "user", "content": "x"}], ["a"])[0]["role"] == "user")
    check("hint: ชื่อว่าง = ไม่แก้",
          S._hint_use_skill([{"role": "system", "content": "s"}], [])[0]["content"] == "s")

    # ---------------- 6) tool install_skill + การขออนุญาต
    fresh = Path(tempfile.mkdtemp(prefix="soonai-autoskill-tool-"))
    S._SKILLS_TEST_ROOTS = [str(fresh)]      # เริ่มจากโฟลเดอร์ว่าง เพื่อทดสอบติดตั้งใหม่จิรง
    _tool_msg = S.run_tool("install_skill", {"name": "pytest-first"})
    check("tool: ติดตั้งตัวใหม่ได้", _tool_msg.startswith("ติดตั้ง pytest-first"), _tool_msg)
    check("tool: ไฟล์ถูกสร้าง", (fresh / "pytest-first" / "SKILL.md").is_file())
    check("tool: บอกให้อ่าน read_skill ต่อ", "read_skill" in _tool_msg, _tool_msg)
    check("tool: ติดตั้งอยู่แล้วบอกให้อ่านเลย",
          "ติดตั้งอยู่แล้ว" in S.run_tool("install_skill", {"name": "pytest-first"}))
    bad = S.run_tool("install_skill", {"name": "ไม่มีสกิลนี้"})
    check("tool: ชื่อผิด = ERROR + ทางเลือก", bad.startswith("ERROR:") and "search_skills" in bad, bad)
    check("tool: อยู่ใน KNOWN_TOOLS", "install_skill" in S.KNOWN_TOOLS)
    check("tool: ไม่ใช่ read-only (ต้องขออนุญาต)", "install_skill" not in S.READONLY_TOOLS)
    check("tool: ประกาศใน AGENT_TOOLS",
          any(d["function"]["name"] == "install_skill" for d in S.AGENT_TOOLS))
    check("approve: ไม่ interactive + ไม่ auto_yes = ปฏิเสธ",
          S.approve("install_skill", "ติดตั้ง skill", {"name": "thai-docs"}, False) is False)
    check("approve: auto_yes = ผ่าน",
          S.approve("install_skill", "ติดตั้ง skill", {"name": "thai-docs"}, True) is True)

    # ---------------- 7) agent_chat เรียก auto-suggest + แนบ hint
    calls = []
    _orig_auto = S.autosuggest_skill
    _orig_attach = S._attach_symbol_map
    _orig_post = S._post_chat
    _orig_conf = (S.approve, S.run_tool, S.console)
    S.autosuggest_skill = lambda task, auto_yes=False: (calls.append(task) or ["thai-docs"])
    S._attach_symbol_map = lambda m, **k: m
    payloads = []

    def _post(url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        payloads.append(payload)
        return Resp(200, {"choices": [{"message": {"content": "เสร็จแล้ว"}, "finish_reason": "stop"}]})

    S._post_chat = _post
    S.approve = lambda *a, **k: True
    S.run_tool = lambda *a, **k: "OK"
    S.console = Console(file=io.StringIO(), width=200, force_terminal=False)
    try:
        out, err, used, info = S.agent_chat(
            "openrouter", "m-test",
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "ช่วยเขียนเอกสารให้อ่านง่าย"}],
            0.2, auto_yes=True, max_steps=1)
    finally:
        S.autosuggest_skill = _orig_auto
        S._attach_symbol_map = _orig_attach
        S._post_chat = _orig_post
        S.approve, S.run_tool, S.console = _orig_conf
    check("agent_chat: เรียก auto-suggest ด้วยข้อความงานล่าสุด",
          calls and calls[0] == "ช่วยเขียนเอกสารให้อ่านง่าย", calls)
    sys_txt = (payloads[0].get("messages") or [{}])[0].get("content", "") if payloads else ""
    check("agent_chat: แนบ hint ให้อ่านสกิลก่อนลงมือ",
          "read_skill" in sys_txt and "thai-docs" in sys_txt, sys_txt[-200:])
    check("agent_chat: ตอบจบปกติ", out == "เสร็จแล้ว" and err == "", (out, err))
finally:
    (S._SKILLS_TEST_ROOTS, S.console, S.load_config, S.Prompt) = _orig
    os.environ.pop("SOONAI_NO_SKILL_SUGGEST", None)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL SKILL AUTOSUGGEST TESTS PASSED")
