# -*- coding: utf-8 -*-
"""ทดสอบระบบหัวข้อ session: _title_is_weak · _fallback_title · save_session
รักษาธง · ensure_session_title (AI สำเร็จ/ล้มเหลว) · refresh_session_title
(ข้ามสปินเนอร์เมื่อไม่ต้องทำอะไร)"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, r"C:\Users\opc\Desktop\soonaiTH")
import soonai as S  # noqa: E402

fails = []


def check(label, cond, extra=""):
    mark = "OK  " if cond else "FAIL"
    if not cond:
        fails.append(label)
    print(f"{mark} {label}" + (f" | {extra}" if extra else ""))


# ── ใช้โฟลเดอร์ชั่วคราวแทน SESSIONS_DIR จริง ─────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="soonai_title_test_"))
S.SESSIONS_DIR = tmp

LONG_Q = "ช่วยวิเคราะห์โครงสร้างโปรเจกต์ roblox-mcp-server แล้วสรุปเป็นตารางให้หน่อย"
MSGS = [{"role": "system", "content": "sys"},
        {"role": "user", "content": "สวัดดี"},
        {"role": "assistant", "content": "สวัสดีครับ"},
        {"role": "user", "content": LONG_Q},
        {"role": "assistant", "content": "นี่คือตารางโครงสร้างไฟล์ทั้งหมด..."}]

# 1) _title_is_weak จับชื่อมั่ว
for text, want in [("สวัดดี", True), ("hi", True), ("", True),
                   ("/test git --version → ผ่าน", True),
                   ("เป้าหมาย: เชื่อมต่อ MCP Server", True),
                   ("ทำเว็ป จัดการ บริหาร หุ้น", False),
                   ("สร้างโปรเจค บริหาร ธุรกิจ หุ้น", False)]:
    check(f"_title_is_weak({text[:30]!r}) == {want}",
          S._title_is_weak(text) == want, f"got={S._title_is_weak(text)}")

# 2) _fallback_title ข้ามคำทักทาย → เอาข้อความแรกที่สื่อหัวข้อได้
fb = S._fallback_title([{"role": "user", "content": "สวัสดี"},
                        {"role": "user", "content": "hi"},
                        {"role": "user", "content": LONG_Q}])
check("_fallback_title ข้ามทักทาย เอาข้อความที่สื่อหัวข้อ", fb == S._clean_title(LONG_Q, limit=40), repr(fb))
check("_fallback_title คืน '' เมื่อมีแต่คำทักทาย",
      S._fallback_title([{"role": "user", "content": "hi"}]) == "")

# 3) save_session เก็บ field เก่า (title_ai/title_attempts) ไม่ให้หาย
sid = "20260922-999999"
S.save_session(sid, "ollama", "test-model", MSGS)
p = tmp / f"{sid}.json"
d = json.loads(p.read_text(encoding="utf-8"))
check("ชื่อเริ่มต้น = ข้อความแรก (มั่ว)", d["name"] == "สวัดดี", repr(d["name"]))
d["title_ai"] = True
d["title_attempts"] = 2
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
S.save_session(sid, "ollama", "test-model",
               MSGS + [{"role": "user", "content": "คำถามใหม่"},
                       {"role": "assistant", "content": "คำตอบใหม่"}])
d2 = json.loads(p.read_text(encoding="utf-8"))
check("save_session ครั้งที่ 2 รักษา title_ai", d2.get("title_ai") is True)
check("save_session ครั้งที่ 2 รักษา title_attempts", d2.get("title_attempts") == 2,
      repr(d2.get("title_attempts")))
check("save_session อัปเดต messages ใหม่จริง",
      any(m.get("content") == "คำถามใหม่" for m in d2["messages"]))

# 4) ensure_session_title — AI สำเร็จ → ตั้งชื่อ + ปิดธง
sid2 = "20260922-888888"
S.save_session(sid2, "ollama", "test-model", MSGS)
_orig_gen = S.gen_session_title
S.gen_session_title = lambda *a, **k: "วิเคราะห์โครงสร้าง Roblox MCP"
got = S.ensure_session_title(sid2, "ollama", "test-model", MSGS)
d3 = json.loads((tmp / f"{sid2}.json").read_text(encoding="utf-8"))
check("AI สำเร็จ → ชื่อใหม่", d3["name"] == "วิเคราะห์โครงสร้าง Roblox MCP", repr(got))
check("AI สำเร็จ → title_ai=True", d3.get("title_ai") is True)
check("ensure รอบ 2 ไม่ยิง AI ซ้ำ (ชื่อดีแล้ว)",
      S.ensure_session_title(sid2, "ollama", "test-model", MSGS) == "วิเคราะห์โครงสร้าง Roblox MCP")

# 5) ensure_session_title — AI ล้มเหลว → fallback จากข้อความจริง (ไม่ค้างชื่อมั่ว)
sid5 = "20260922-444444"
S.save_session(sid5, "ollama", "test-model", MSGS)   # fresh: ชื่อ 'สวัดดี' ไม่มีธง
p5 = tmp / f"{sid5}.json"
S.gen_session_title = lambda *a, **k: ""
got = S.ensure_session_title(sid5, "ollama", "test-model", MSGS)
d4 = json.loads(p5.read_text(encoding="utf-8"))
check("AI ล้มเหลว → fallback เป็นข้อความแรกที่สื่อหัวข้อ",
      d4["name"] == S._clean_title(LONG_Q, limit=40), repr(d4["name"]))
check("AI ล้มเหลว → ไม่ปิดธง title_ai (ยังสู้ต่อได้)", not d4.get("title_ai"))
check("AI ล้มเหลว → title_attempts นับ +1", d4.get("title_attempts") == 1,
      repr(d4.get("title_attempts")))

# 5b) เพดาน attempts — session ที่มีแต่คำทักทาย (fallback ก็ช่วยไม่ได้) + AI พังตลอด
sid6 = "20260922-333333"
S.save_session(sid6, "ollama", "test-model",
               [{"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Hello!"}])   # ชื่อ 'hi' อ่อนทุกทาง
p6 = tmp / f"{sid6}.json"
ai_calls = []
S.gen_session_title = lambda *a, **k: (ai_calls.append(1), "")[1]
for _ in range(6):
    S.ensure_session_title(sid6, "ollama", "test-model", MSGS)
check("AI พังตลอด → ยิงไม่เกินเพดาน 3 ครั้ง (เรียก 6 รอบ)",
      len(ai_calls) == 3, f"calls={len(ai_calls)}")
d6 = json.loads(p6.read_text(encoding="utf-8"))
check("ครบเพดาน → attempts หยุดที่ 3", d6.get("title_attempts") == 3,
      repr(d6.get("title_attempts")))

# 6) refresh_session_title — ข้ามสปินเนอร์เมื่อไม่ต้องทำอะไร
spinner_calls = []
_orig_spin = S.run_with_spinner
S.run_with_spinner = lambda label, fn, *a, **k: (spinner_calls.append(label), fn(*a, **k))[1]
S.gen_session_title = lambda *a, **k: "ไม่ควรถูกเรียก"
n1 = S.refresh_session_title(sid2, "ollama", "test-model", MSGS)  # title_ai แล้ว
check("refresh (หัวข้อดีแล้ว) ไม่เปิดสปินเนอร์ ไม่ยิง AI", not spinner_calls, repr(n1))
n2 = S.refresh_session_title("20260922-777777", "ollama", "test-model", MSGS)  # ไม่มีไฟล์
check("refresh (ไฟล์ไม่มี) คืน '' นิ่ง ๆ", n2 == "" and not spinner_calls, repr(n2))
S.run_with_spinner = _orig_spin
S.gen_session_title = _orig_gen

# 7) list_sessions โชว์ fallback เมื่อชื่อยังมั่ว (ไม่แตะไฟล์)
sid3 = "20260922-666666"
S.save_session(sid3, "ollama", "test-model",
               [{"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Hello! How can I help?"},
                {"role": "user", "content": "รีวิวโค้ดไฟล์ main.py ให้หน่อยว่ามีบั๊กไหม"},
                {"role": "assistant", "content": "พบ 3 จุดที่ควรแก้..."}])
items = {it["id"]: it for it in S.list_sessions()}
check("list_sessions fallback แทน 'hi' ด้วยข้อความที่สื่อหัวข้อ",
      items.get(sid3, {}).get("name") == "รีวิวโค้ดไฟล์ main.py ให้หน่อยว่ามีบั๊กไหม",
      items.get(sid3, {}).get("name", "??"))
sid4 = "20260922-555555"
S.save_session(sid4, "ollama", "test-model", MSGS)   # name='สวัดดี' มั่ว
items = {it["id"]: it for it in S.list_sessions()}
check("list_sessions fallback โชว์ข้อความที่สื่อหัวข้อแทน 'สวัดดี'",
      items.get(sid4, {}).get("name") == S._clean_title(LONG_Q, limit=40),
      repr(items.get(sid4, {}).get("name")))
# ไฟล์ต้นฉบับไม่ถูกแก้ (โชว์อย่างเดียว)
raw = json.loads((tmp / f"{sid4}.json").read_text(encoding="utf-8"))
check("list_sessions ไม่เขียนทับไฟล์ (ชื่อในไฟล์ยัง 'สวัดดี')", raw["name"] == "สวัดดี")

print()
if fails:
    print("FAIL:", len(fails))
    sys.exit(1)
print("PASS: ระบบหัวข้อ session ทั้งหมดถูกต้อง")
