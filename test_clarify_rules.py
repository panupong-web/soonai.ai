# -*- coding: utf-8 -*-
"""Regression: กฎจัดการข้อความกำกวม + MCP grounding (เคส "ใช้ mcp ดิ" → เดา Roblox มั่ว)

3 ข้อผิดพลาดจริงที่ต้องไม่ให้เกิดซ้ำ:
1) สมมติความหมายมั่ว (MCP = Roblox) → ต้องถามชี้แจงพร้อมทางเลือกเป็นรูปธรรม
2) อ้างไฟล์/พาธ ที่ไม่มีอยู่จริง (%LOCALAPPDATA%\\Roblox\\mcp.bat) → ห้ามอ้างของที่ไม่ได้เห็นจริง
3) ตอบวนเป็นชุดคำถามโดยไม่ให้สาระ → ต้องให้ข้อมูลคู่กับคำถาม รวมถามรอบเดียว

สิ่งที่เทสต์:
- CLARIFY_RULES อยู่ใน QUALITY_SYSTEM (แชทปกติ) และ AGENT_SYSTEM (agent/ทีม/exec)
- staff_system (ลูกน้อง) ได้กฎด้วย
- load_config migration: default เก่าที่เคยเซฟลง config = อัปเดตใหม่ · ค่าที่ผู้ใช้แก้เอง = ไม่แตะ
- _ensure_mcp_hint: ไม่มี server + ผู้ใช้พิมพ์ถึง mcp → แทรกบรรทัดสถานะจริงของ SoonAI
  · ไม่พูดถึง mcp → ไม่แทรก · มี server → บรรทัดเดิม · ไม่แทรกซ้ำ

ไม่แตะเน็ต · ไม่เขียน config จริง (patch save_json/load_mcp_config)
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import mcp_client as MC  # noqa: E402
import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------- 1) กฎอยู่ใน prompt ทั้งสอง + ครอบ 3 ข้อผิดพลาด ----------
NEEDLES = [
    ("ถามชี้แจง", "ถามชี้แจงเมื่อกำกวม"),
    ("ทางเลือกที่เป็นรูปธรรม", "ทางเลือกเป็นรูปธรรม"),
    ("mcp catalog", "ชี้ทาง MCP ของ SoonAI ที่ถูกต้อง"),
    ("Claude/Cursor", "ทางเลือก MCP ของ client อื่น"),
    ("ห้ามอ้างไฟล์", "ห้ามอ้างของที่ไม่ได้เห็นจริง"),
    ("%LOCALAPPDATA%", "ตัวอย่างพาธที่ห้ามเดา"),
    ("รอบเดียว", "รวมคำถามรอบเดียว ห้ามวนลูป"),
]
for needle, label in NEEDLES:
    check(f"QUALITY_SYSTEM มี: {label}", needle in S.QUALITY_SYSTEM, needle)
    check(f"AGENT_SYSTEM มี: {label}", needle in S.AGENT_SYSTEM, needle)

check("QUALITY_SYSTEM = legacy เดิมไม่หาย + ต่อท้ายด้วยกฎ",
      S.QUALITY_SYSTEM.startswith(S.LEGACY_QUALITY_SYSTEM)
      and S.CLARIFY_RULES in S.QUALITY_SYSTEM)
staff = S.staff_system({"name": "ทดสอบ", "role": "ทดสอบ"})
check("staff_system (ลูกน้อง) ได้กฎกำกวมด้วย",
      "ถามชี้แจง" in staff and "ห้ามอ้างไฟล์" in staff)

# ---------- 2) load_config migration: default เก่าอัปเดต · ค่าผู้ใช้ไม่แตะ ----------
_orig_save, _orig_load_json = S.save_json, S.load_json
saved = {}


def fake_save(fn, data):
    saved["n"] = saved.get("n", 0) + 1
    saved["cfg"] = dict(data)


S.save_json = fake_save
try:
    # 2a) default เก่าที่เคยเซฟค้าง = อัปเดตเป็นใหม่ (เคสนี้คือ config จริงของเครื่อง)
    S.load_json = lambda *a, **k: {"system": S.LEGACY_QUALITY_SYSTEM,
                                   "provider": "openrouter"}
    cfg = S.load_config()
    check("migration: default เก่า = ถูกแทนด้วยค่าใหม่ (มีกฎ)",
          cfg.get("system") == S.QUALITY_SYSTEM and "ถามชี้แจง" in cfg["system"],
          str(cfg.get("system"))[:80])
    check("migration: บันทึกลง config จริง", saved.get("n", 0) >= 1)
    check("migration: ค่าอื่นไม่หาย", cfg.get("provider") == "openrouter", cfg)

    # 2b) ค่าที่ผู้ใช้แก้เอง = ต่อกฎท้าย ไม่ทับข้อความเดิม
    saved.clear()
    S.load_json = lambda *a, **k: {"system": "system ที่ผู้ใช้เขียนเองด้วยน้ำมือ"}
    cfg2 = S.load_config()
    check("migration: ค่าผู้ใช้ = ต่อกฎท้าย ไม่ทับข้อความเดิม",
          str(cfg2.get("system")).startswith("system ที่ผู้ใช้เขียนเองด้วยน้ำมือ")
          and "ถามชี้แจง" in str(cfg2.get("system")) and saved.get("n", 0) >= 1,
          (str(cfg2.get("system"))[:60], saved))

    # 2c) มีกฎแล้ว = ไม่ทำซ้ำ ไม่เขียนไฟล์
    saved.clear()
    S.load_json = lambda *a, **k: {"system": S.QUALITY_SYSTEM}
    cfg3 = S.load_config()
    check("migration: มีกฎแล้ว = ไม่ทำซ้ำ ไม่เขียนไฟล์",
          cfg3.get("system") == S.QUALITY_SYSTEM and not saved,
          (str(cfg3.get("system"))[-60:], saved))
finally:
    S.save_json, S.load_json = _orig_save, _orig_load_json

# ---------- 3) _ensure_mcp_hint: grounding ตามสถานะจริง + ไม่แทรกซ้ำ ----------
_orig_mc = MC.load_mcp_config


def mk(user_txt):
    return [{"role": "system", "content": "SYS"},
            {"role": "user", "content": user_txt}]


try:
    # 3a) ไม่มี server + ผู้ใช้พิมพ์ถึง mcp → บรรทัดสถานะจริงของ SoonAI
    MC.load_mcp_config = lambda *a, **k: {}
    msgs = mk("ใช้ mcp ดิ")
    S._ensure_mcp_hint(msgs)
    c = msgs[0]["content"]
    check("hint: ไม่มี server + พิมพ์ถึง mcp = แทรกบรรทัดสถานะจริง",
          "[สถานะ MCP ของ SoonAI]" in c and "mcp catalog" in c, c)
    check("hint: บรรทัดสถานะสั่งถามชี้แจงแทนการเดา",
          "ถามชี้แจง" in c and "ห้ามเดา" in c, c)
    check("hint: ข้อความเดิมไม่หาย", c.startswith("SYS"))
    before = msgs[0]
    S._ensure_mcp_hint(msgs)
    check("hint: แทรกซ้ำได้แค่รอบเดียว", msgs[0] is before)

    # 3b) ไม่ได้พิมพ์ถึง mcp = ไม่แทรกอะไรเลย
    msgs2 = mk("สวัสดีครับ ช่วยวิเคราะห์โค้ดหน่อย")
    S._ensure_mcp_hint(msgs2)
    check("hint: ไม่พิมพ์ถึง mcp = ไม่แทรก", msgs2[0]["content"] == "SYS",
          msgs2[0]["content"])

    # 3c) case ไม่พิมพ์ตัวพิมพ์ใหญ่-เล็กตรง ๆ
    msgs2b = mk("ใช้ MCP ดิ")
    S._ensure_mcp_hint(msgs2b)
    check("hint: จับ MCP ตัวพิมพ์ใหญ่ด้วย",
          "[สถานะ MCP" in msgs2b[0]["content"])

    # 3d) มี server = บรรทัดเดิม (ไม่ว่าผู้ใช้จะพูดถึง mcp ไหม)
    MC.load_mcp_config = lambda *a, **k: {"fs": {"enabled": True},
                                          "web": {"enabled": False}}
    msgs3 = mk("เปิดโปรเจกต์ให้หน่อย")
    S._ensure_mcp_hint(msgs3)
    c3 = msgs3[0]["content"]
    check("hint: มี server = บรรทัดรายชื่อเดิม (กรอง enabled)",
          "Tools เสริมนอกเครื่อง (MCP: fs)" in c3
          and "mcp_tools" in c3 and "web" not in c3.split("Tools เสริม")[1][:60], c3)
    check("hint: บรรทัด server เดิมไม่แทรกซ้ำ", msgs3[0] is not None)
    before3 = msgs3[0]
    S._ensure_mcp_hint(msgs3)
    check("hint: server มีซ้ำ = ครั้งเดียว", msgs3[0] is before3)
finally:
    MC.load_mcp_config = _orig_mc

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL CLARIFY RULES TESTS PASSED")
