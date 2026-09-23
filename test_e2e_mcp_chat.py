# -*- coding: utf-8 -*-
"""E2E เคส "ใช้ mcp ดิ": system prompt (CLARIFY_RULES) + MCP hint ทำงานร่วมกันในแชทเดียว

จำลองเทิร์นแชทตาม cmd_chat จริง (shared/chat.py):
  st.history = [system(cfg)] + user("ใช้ mcp ดิ")
  → สำเนา _send → R._ensure_mcp_hint(_send) → R.show_reply(..., _send, ...)

ครอบ:
A) payload มี rules ครบ + hint ครบพร้อมกัน ไม่หักล้างกัน · st.history ไม่ถูก mutate · ย้ำซ้ำ = เดียว
B) มี server = hint โชว์เฉพาะ server ที่เปิด · rules ยังครบ
C) ไม่พิมพ์ถึง mcp = ไม่มี hint แต่ rules ยังครบ
D) ไม่มีคำว่า Roblox/mcp.bat ใน payload (เคสเดาผิดจากเคสรายงานต้องไม่เกิดซ้ำ)
E) โหมด agent (_agent_msgs + hint) = CLARIFY + AGENT + hint ครบ บนสำเนา · server branch ไม่ซ้ำ
F) config จริงของเครื่อง (โหลดผ่าน load_config) → payload มี marker + hint พร้อมกัน
G) wire จริงใน shared/chat.py: เรียก hint บนสำเนาก่อน show_reply ไม่ส่ง st.history ตรง ๆ

ไม่แตะเน็ต · ไม่เขียนไฟล์ (patch save_json ตอนโหลด config · patch load_mcp_config)
"""
import sys
from pathlib import Path

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


USER_Q = "ใช้ mcp ดิ"


def make_history(text=USER_Q, system=None):
    """เหมือน cmd_chat ห้องแชทใหม่: system จาก cfg แล้วผู้ใช้พิมพ์ถาม"""
    return [{"role": "system", "content": system or S.QUALITY_SYSTEM},
            {"role": "user", "content": text}]


def send_like_chat(history, servers=None):
    """ขั้นก่อน show_reply ของ cmd_chat: สำเนารายการ → แนบ hint → คืน payload"""
    srv = {} if servers is None else servers
    MC.load_mcp_config = lambda *a, **k: dict(srv)
    send = list(history)
    S._ensure_mcp_hint(send)
    return send


_orig_load_mcp = MC.load_mcp_config
try:
    # ---------- A) ไม่มี server + ถาม mcp = rules + hint พร้อมกันใน payload เดียว ----------
    hist = make_history()
    send = send_like_chat(hist, servers={})
    sys_txt = send[0]["content"]
    check("A: payload เป็น system+user ครบ",
          send[0]["role"] == "system" and send[-1] == {"role": "user", "content": USER_Q})
    check("A: CLARIFY_RULES อยู่ครบเป๊ะใน payload", S.CLARIFY_RULES in sys_txt)
    for needle in (S.CLARIFY_MARKER, "ห้ามอ้างไฟล์", "%LOCALAPPDATA%",
                   "ห้ามตอบวนเป็นชุดคำถาม", "mcp catalog"):
        check(f"A: rules มี: {needle}", needle in sys_txt)
    check("A: hint สถานะ MCP แนบมาพร้อม rules",
          "[สถานะ MCP ของ SoonAI]" in sys_txt and "ยังไม่มี server" in sys_txt
          and "soonai mcp catalog" in sys_txt)
    check("A: st.history ไม่ถูก mutate (session ไม่ bake hint)",
          hist[0]["content"] == S.QUALITY_SYSTEM
          and "[สถานะ MCP" not in hist[0]["content"])
    S._ensure_mcp_hint(send)
    check("A: ย้ำซ้ำ = hint เดียว", send[0]["content"].count("[สถานะ MCP") == 1)

    # ---------- B) มี server = hint โชว์เฉพาะ server ที่เปิด ----------
    histB = make_history()
    sendB = send_like_chat(histB, servers={"context7": {"enabled": True},
                                           "deepwiki": {"enabled": False}})
    tB = sendB[0]["content"]
    check("B: hint โชว์ชื่อ server ที่เปิดอยู่", "(MCP: context7" in tB)
    segB = tB[tB.find("Tools เสริม"):] if "Tools เสริม" in tB else ""
    check("B: server ที่ปิดไม่โผล่ใน hint", "deepwiki" not in segB and "(MCP:" in segB, segB[:80])
    check("B: rules ยังครบ + history ไม่ถูก mutate",
          S.CLARIFY_RULES in tB and histB[0]["content"] == S.QUALITY_SYSTEM)

    # ---------- C) ไม่พิมพ์ถึง mcp = ไม่มี hint แต่ rules ยังครบ ----------
    sendC = send_like_chat(make_history(text="สวัสดี วันนี้อากาศเป็นไง"), servers={})
    tC = sendC[0]["content"]
    check("C: ไม่พิมพ์ถึง mcp = ไม่มี hint", "[สถานะ MCP" not in tC and "Tools เสริม" not in tC)
    check("C: แต่ rules ยังครบ", S.CLARIFY_RULES in tC)

    # ---------- D) ไม่มีคำว่า Roblox/mcp.bat (เคสเดาผิดจากรายงานต้องไม่เกิดซ้ำ) ----------
    check("D: ไม่มี Roblox/mcp.bat ใน payload เลย",
          "Roblox" not in sys_txt and "mcp.bat" not in sys_txt)

    # ---------- E) โหมด agent = CLARIFY + AGENT + hint ครบ บนสำเนา ----------
    MC.load_mcp_config = lambda *a, **k: {}
    histE = make_history()
    msgsE = S._agent_msgs(histE)   # cmd_chat โหมด agent ประกอบ msgs บนสำเนา
    S._ensure_mcp_hint(msgsE)      # agent_chat เรียกตอนต้นลูป
    tE = msgsE[0]["content"]
    check("E: agent payload = CLARIFY + AGENT_SYSTEM + hint ครบพร้อมกัน",
          S.CLARIFY_RULES in tE and S.AGENT_SYSTEM in tE
          and "[สถานะ MCP ของ SoonAI]" in tE)
    check("E: history ต้นฉบับไม่ถูก mutate",
          histE[0]["content"] == S.QUALITY_SYSTEM and len(histE) == 2)
    MC.load_mcp_config = lambda *a, **k: {"context7": {}}
    msgsE2 = S._agent_msgs(make_history())
    S._ensure_mcp_hint(msgsE2)
    S._ensure_mcp_hint(msgsE2)
    check("E: server branch แทรกครั้งเดียวเมื่อเรียกซ้ำ",
          msgsE2[0]["content"].count("Tools เสริมนอกเครื่อง (MCP: ") == 1)

    # ---------- F) config จริงของเครื่อง → payload มีครบ ----------
    _save = S.save_json
    S.save_json = lambda *a, **k: None   # กันเขียนไฟล์ตอนโหลด (migration ทำงานในหน่วยความจำ)
    try:
        cfg = S.load_config()
    finally:
        S.save_json = _save
    real_sys = str(cfg.get("system") or "")
    check("F: cfg ของเครื่องมี system prompt", bool(real_sys.strip()))
    histF = make_history(system=real_sys)
    sendF = send_like_chat(histF, servers={})
    tF = sendF[0]["content"]
    check("F: config จริง → payload มี marker rules + hint พร้อมกัน",
          S.CLARIFY_MARKER in tF and "[สถานะ MCP ของ SoonAI]" in tF)
    check("F: history ไม่ถูก mutate", histF[0]["content"] == real_sys)

    # ---------- G) wire จริงใน shared/chat.py ----------
    chat_src = Path("shared/chat.py").read_text(encoding="utf-8")
    i_hint = chat_src.find("R._ensure_mcp_hint(_send)")
    i_show = chat_src.find("R.show_reply(st.provider, st.model, _send,")
    check("G: cmd_chat แนบ hint บนสำเนาก่อน show_reply",
          i_hint != -1 and i_show != -1 and i_hint < i_show)
    check("G: ไม่มีจุดส่ง st.history ตรง ๆ อีกแล้ว",
          "R.show_reply(st.provider, st.model, st.history," not in chat_src)
finally:
    MC.load_mcp_config = _orig_load_mcp

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL E2E MCP CHAT TESTS PASSED")
