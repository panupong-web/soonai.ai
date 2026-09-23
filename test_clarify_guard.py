# -*- coding: utf-8 -*-
"""Guardrail ตอน generate: system prompt ที่จะยิงออกต้องมี CLARIFY_RULES (กันค่า config ถูกทับ)

เคส regression จริงที่ต้องคุ้ม:
- config/เซสชันเก่า ค้าง/ถูกทับด้วย default เก่า (มี prefix ของแชทแต่ไม่มี rules) → ซ่อมใน payload ก่อนยิง
- มี rules อยู่แล้ว → ไม่แตะ ไม่ซ้ำ
- aux prompt (สรุป/ชื่อเซสชัน/ที่ปรึกษาสกิล) และค่า custom ที่ผู้ใช้เขียนเอง → ไม่แตะ
- ไม่มี system message / messages ว่าง / None → ไม่พัง

จุดที่ guard ถูกเรียก (generate funnels ทั้งสองของโปรเจกต์):
- send_messages — แชทปกติ (ผ่าน show_reply) + aux ทุกเส้นทาง
- agent_chat — โหมด agent/ทีม/exec ก่อนเข้าลูป

ไม่แตะเน็ต (mock _post_chat / _agent_steps) · ไม่เขียนไฟล์
"""
import io
import json
import sys
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


def fixed():
    return S.CLARIFY_GUARD.get("fixed", 0)


AUX_TITLE = ("สรุปบทสนทนาต่อไปนี้เป็นภาษาไทยให้แม่น: ประเด็นหลัก, ข้อสรุป/การตัดสินใจ, "
             "งานที่ค้างอยู่ ตอบสั้นกระชับ")
CUSTOM_SYS = "ระบบสนทนาเฉพาะองค์กรของเราเอง ไม่ใช่ค่าเริ่มต้นของโปรแกรม"

# ================= A) ตัว guard โดยตรง =================
S.CLARIFY_GUARD["fixed"] = 0

m1 = [{"role": "system", "content": S.LEGACY_QUALITY_SYSTEM},
      {"role": "user", "content": "hi"}]
S.ensure_clarify_rules(m1)
c1 = m1[0]["content"]
check("A1: legacy ไม่มี rules → ซ่อมครบ",
      S.CLARIFY_MARKER in c1 and S.CLARIFY_RULES in c1
      and c1.startswith(S.LEGACY_QUALITY_SYSTEM), c1[:60])
check("A1: นับ guard 1 ครั้ง", fixed() == 1, fixed())

S.ensure_clarify_rules(m1)
check("A2: เรียกซ้ำ = ไม่ซ้ำ ไม่นับเพิ่ม", m1[0]["content"] == c1 and fixed() == 1, fixed())

m2 = [{"role": "system", "content": S.QUALITY_SYSTEM}, {"role": "user", "content": "hi"}]
before2 = m2[0]["content"]
S.ensure_clarify_rules(m2)
check("A3: QUALITY (มี rules แล้ว) → ไม่แตะ ไม่นับ",
      m2[0]["content"] == before2 and fixed() == 1, fixed())

m3 = [{"role": "system", "content": AUX_TITLE}, {"role": "user", "content": "สรุป"}]
S.ensure_clarify_rules(m3)
check("A4: aux prompt (สรุป/ชื่อเรื่อง) → ไม่แตะ ไม่นับ",
      m3[0]["content"] == AUX_TITLE and fixed() == 1, str(m3[0]["content"])[:50])

m4 = [{"role": "system", "content": CUSTOM_SYS}, {"role": "user", "content": "hi"}]
S.ensure_clarify_rules(m4)
check("A5: ค่า custom ของผู้ใช้ → เคารพ ไม่แตะ",
      m4[0]["content"] == CUSTOM_SYS and fixed() == 1)

m5 = [{"role": "user", "content": "hi"}]
out5 = S.ensure_clarify_rules(m5)
check("A6: ไม่มี system → ไม่พัง ไม่แตะ",
      out5 is m5 and fixed() == 1 and len(m5) == 1)
check("A7: None / [] → ไม่พัง",
      S.ensure_clarify_rules(None) is None
      and S.ensure_clarify_rules([]) == [] and fixed() == 1)


# ================= B) send_messages (แชทปกติ + aux ทุกเส้นทาง) =================
class Resp:
    """คำตอบปลอม: ใช้ .json() แบบไม่สตรีม และ .iter_lines() แบบ SSE"""

    def __init__(self, status=200, payload=None, text=None, sse=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text if text is not None else json.dumps(self._payload)
        self._sse = sse or []
        self.closed = False

    def json(self):
        if self._payload:
            return self._payload
        try:
            return json.loads(self.text)
        except Exception:
            return {}

    def iter_lines(self, decode_unicode=False):
        for line in self._sse:
            yield line

    def close(self):
        self.closed = True


def oai_json(content=""):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


class Fixture:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        # สำเนาลึก ณ ตอนส่งจริง (payload ถูก mutate ต่อระหว่าง retry/failover)
        snap = json.loads(json.dumps(payload, ensure_ascii=False)) if payload else payload
        self.requests.append({"url": url, "headers": headers, "payload": snap,
                              "stream": stream, "tag": tag, "retries": retries})
        if not self.responses:
            return Resp(payload=oai_json("จบ"))
        return self.responses.pop(0)


def run_send(fx, messages, **kw):
    """เรียก send_messages จริงโดย mock ชั้นเครือข่าย/failover ทั้งหมด"""
    orig = (S._post_chat, S.load_keys, S.load_config, S.console, S._wait_animated,
            S._failover_free, S._failover_provider, S._apply_provider_switch)
    S._post_chat = fx.post
    S.load_keys = lambda: {}
    S.load_config = lambda: {}
    S.console = Console(file=io.StringIO(), width=200)
    S._wait_animated = lambda *a, **k: None
    S._failover_free = lambda p, m, st, bd, sw, max_switches=2: ""
    S._failover_provider = lambda p, m: ("", "")
    S._apply_provider_switch = lambda *a: None
    try:
        return S.send_messages("openrouter", "m1", messages, 0.7, stream=False, **kw)
    finally:
        (S._post_chat, S.load_keys, S.load_config, S.console, S._wait_animated,
         S._failover_free, S._failover_provider, S._apply_provider_switch) = orig


S.CLARIFY_GUARD["fixed"] = 0
fx = Fixture([Resp(payload=oai_json("ตอบ"))])
out = run_send(fx, [{"role": "system", "content": S.LEGACY_QUALITY_SYSTEM},
                    {"role": "user", "content": "hi"}])
sys_b = fx.requests[0]["payload"]["messages"][0]["content"]
check("B1: send_messages ซ่อม system ก่อนเข้า driver",
      S.CLARIFY_MARKER in sys_b and S.CLARIFY_RULES in sys_b, str(sys_b)[:60])
check("B1: ยิงแล้วได้คำตอบปกติ", out == "ตอบ", out)
check("B2: counter ขึ้น 1", fixed() == 1, fixed())

fx2 = Fixture([Resp(payload=oai_json("ok"))])
run_send(fx2, [{"role": "system", "content": S.QUALITY_SYSTEM},
               {"role": "user", "content": "hi"}])
sys_b2 = fx2.requests[0]["payload"]["messages"][0]["content"]
check("B3: QUALITY ผ่าน send → ไม่ต่อซ้ำ ไม่นับ",
      sys_b2.count(S.CLARIFY_MARKER) == 1 and fixed() == 1, fixed())

fx3 = Fixture([Resp(payload=oai_json("ok"))])
run_send(fx3, [{"role": "system", "content": AUX_TITLE}, {"role": "user", "content": "x"}])
check("B4: aux ผ่าน send → payload ไม่ถูกแตะ",
      fx3.requests[0]["payload"]["messages"][0]["content"] == AUX_TITLE and fixed() == 1)


# ================= C) agent_chat (โหมด agent) =================
S.CLARIFY_GUARD["fixed"] = 0
cap_c = []


def fake_steps(*a, **k):
    msgs = a[2] if len(a) > 2 else []
    cap_c.append([dict(m) for m in msgs])
    return ("done", "", 0, {"steps": 1, "exhausted": False, "tools": [], "cap": 5})


orig_c = (S._agent_steps, S.console)
S._agent_steps = fake_steps
S.console = Console(file=io.StringIO(), width=200)
try:
    out_c, err_c, _used, _info = S.agent_chat(
        "openrouter", "a",
        [{"role": "system", "content": S.LEGACY_QUALITY_SYSTEM},
         {"role": "user", "content": "ทำงาน"}],
        0.2, auto_yes=True, max_steps=5, expect_tools=True)
finally:
    S._agent_steps, S.console = orig_c
sys_c = cap_c[0][0].get("content", "") if cap_c and cap_c[0] else ""
check("C1: agent_chat ซ่อม system ก่อนเข้าลูป",
      bool(cap_c) and S.CLARIFY_MARKER in sys_c and S.CLARIFY_RULES in sys_c,
      str(sys_c)[:60])
# agent_chat กระตุ้นซ้ำ 1 รอบเมื่อ expect_tools=True (ข้อความจึงซ้ำได้ — พฤติกรรมเดิม ไม่เกี่ยวกับ guard)
check("C2: counter ขึ้น 1 + จบงานได้",
      fixed() == 1 and out_c.startswith("done") and err_c == "", (fixed(), out_c, err_c))


# ================= D) source wiring (สองจุดเรียก ตรงสอง funnel) =================
src = Path("soonai.py").read_text(encoding="utf-8")
i_guard = src.find("def ensure_clarify_rules(")
i_send = src.find("def send_messages(")
i_agent = src.find("def agent_chat(")
check("D1: guard ถูกนิยามก่อน generate funnels ทั้งสอง",
      0 < i_guard < i_send and 0 < i_guard < i_agent, (i_guard, i_send, i_agent))
check("D2: เรียกในต้น send_messages (ก่อน _make_chat_driver)",
      "ensure_clarify_rules(messages)" in src[i_send:i_send + 1500]
      and src[i_send:i_send + 1500].find("ensure_clarify_rules")
      < src[i_send:i_send + 1500].find("_make_chat_driver"))
check("D3: เรียกในต้น agent_chat (ก่อน _ensure_mcp_hint)",
      "ensure_clarify_rules(messages)" in src[i_agent:i_agent + 900]
      and src[i_agent:i_agent + 900].find("ensure_clarify_rules")
      < src[i_agent:i_agent + 900].find("_ensure_mcp_hint"))
check("D4: call site = 2 (ไม่เรียกพร่ำเพรื่อ)",
      src.count("\n    ensure_clarify_rules(messages)") == 2,
      src.count("\n    ensure_clarify_rules(messages)"))

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL CLARIFY GUARD TESTS PASSED")
