# -*- coding: utf-8 -*-
"""Regression: ประมาณ token + งบ context + ค่าใช้จ่ายโดยประมาณ
- est_tokens: อังกฤษ ~4 ตัว/token · ไทย/CJK ~1.5 ตัว/token
- messages_tokens รวม overhead ต่อข้อความ
- estimate_cost ตามรูปแบบ pricing ของแต่ละค่าย (จาก cache เท่านั้น)
- usage_note/usage_line สะสมถูกต้อง + รีเซ็ตได้
- fit_messages ตัดของเก่าออกโดยไม่ทิ้ง tool result แบบกำพร้า และอยู่ในงบ
ไม่แตะเน็ต (ราคาป้อนผ่าน monkeypatch)
"""
import os
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------------------------------------------------------------- 1) est_tokens
check("est: ว่าง = 0", S.est_tokens("") == 0 and S.est_tokens(None) == 0)
check("est: อังกฤษ 4 ตัว ~ 1-2 token", 1 <= S.est_tokens("abcd") <= 2, S.est_tokens("abcd"))
check("est: อังกฤษ 400 ตัว ~ 100 token", 95 <= S.est_tokens("a" * 400) <= 105,
      S.est_tokens("a" * 400))
thai = S.est_tokens("สวัสดีครับ")
check("est: ไทยนับแพงกว่าอังกฤษต่อตัวอักษร",
      thai > S.est_tokens("a" * len("สวัสดีครับ")) / 2, thai)
check("est: รับ dict/list/obj ได้", S.est_tokens({"a": "b"}) > 0 and S.est_tokens(["x"]) > 0)

check("messages_tokens: บวก overhead ต่อข้อความ",
      S.messages_tokens([{"role": "user", "content": "abcd"}]) == 4 + S.est_tokens("abcd"),
      S.messages_tokens([{"role": "user", "content": "abcd"}]))
check("messages_tokens: นับ tool_calls ด้วย",
      S.messages_tokens([{"role": "assistant", "content": "",
                          "tool_calls": [{"id": "c1", "type": "function",
                                          "function": {"name": "read_file",
                                                       "arguments": "{\"path\": \"a\"}"}}]}]) > 4)

# ---------------------------------------------------------------- 2) ค่าใช้จ่าย
_orig_pricing = S._pricing_cached
try:
    S._pricing_cached = lambda provider: {
        "gpt-x": {"prompt": 1e-6, "completion": 2e-6},
        "hf-y": {"hf_min_in": 1.0, "hf_min_out": 2.0},
        "puter-z": {"puter_in": 100.0, "puter_out": 200.0},
        "free-a": {"prompt": 0, "completion": 0},
    }
    check("cost openrouter (USD/token)",
          abs(S.estimate_cost("openrouter", "gpt-x", 1000, 500) - 0.002) < 1e-9,
          S.estimate_cost("openrouter", "gpt-x", 1000, 500))
    check("cost huggingface (USD/1M)",
          abs(S.estimate_cost("huggingface", "hf-y", 1000, 500) - 0.002) < 1e-9,
          S.estimate_cost("huggingface", "hf-y", 1000, 500))
    check("cost puter (เซนต์/1M)",
          abs(S.estimate_cost("puter", "puter-z", 1000, 500) - 0.002) < 1e-9,
          S.estimate_cost("puter", "puter-z", 1000, 500))
    check("cost โมเดลฟรี = 0", S.estimate_cost("openrouter", "free-a", 9999, 9999) == 0)
    check("cost โมเดลไม่รู้จัก = 0", S.estimate_cost("openrouter", "nope", 100, 100) == 0)

    # ------------------------------------------------------------ 3) สะสม usage
    S.usage_reset()
    check("usage_line ว่างตอนยังไม่ใช้", S.usage_line() == "")
    S._track_usage("openrouter", "free-a",
                   {"messages": [{"role": "user", "content": "abcd"}], "system": "abcd"},
                   "abcd")
    check("track: นับ 1 call", S.USAGE["calls"] == 1, S.USAGE)
    check("track: in = messages + system", S.USAGE["in"] == 4 + 2 + 2, S.USAGE)
    check("track: out = ข้อความตอบ", S.USAGE["out"] == 2, S.USAGE)
    check("track: โมเดลฟรีไม่คิดเงิน", S.USAGE["cost"] == 0, S.USAGE)
    S.usage_note("openrouter", "gpt-x", 1000, 500)
    check("usage_note: บวกเข้าไป", S.USAGE["in"] == 1008 and S.USAGE["out"] == 502, S.USAGE)
    check("usage_note: คิดค่าใช้จ่าย", abs(S.USAGE["cost"] - 0.002) < 1e-9, S.USAGE)
    line = S.usage_line()
    check("usage_line มี calls และ tok", "calls" in line and "tok" in line, line)
    check("usage_line มีราคาโดยประมาณ", "$" in line, line)
    S.usage_reset()
    check("usage_reset ล้างหมด", S.USAGE == {"calls": 0, "in": 0, "out": 0, "cost": 0.0}, S.USAGE)
finally:
    S._pricing_cached = _orig_pricing

# ---------------------------------------------------------------- 4) งบ context
_orig_load = S.load_config
_orig_env = os.environ.pop("SOONAI_CONTEXT_BUDGET", None)
try:
    S.load_config = lambda: {}
    check("budget: ค่าเริ่มต้น 24000", S.context_budget() == 24000)
    S.load_config = lambda: {"context_budget": 8000}
    check("budget: อ่านจาก config", S.context_budget() == 8000)
    S.load_config = lambda: {"context_budget": 50}
    check("budget: ค่าเล็กเกินไปถูกเมิน", S.context_budget() == 24000)
    os.environ["SOONAI_CONTEXT_BUDGET"] = "5000"
    check("budget: env ทับ config", S.context_budget() == 5000)

    msgs = [{"role": "system", "content": "sys"},
            {"role": "user", "content": "x" * 4000},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "read_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "y" * 100},
            {"role": "user", "content": "งานล่าสุด"}]
    def _has_orphan_tool(ms):
        ids = set()
        for m in ms:
            if m.get("role") == "assistant":
                ids |= {tc.get("id") for tc in (m.get("tool_calls") or []) if isinstance(tc, dict)}
            elif m.get("role") == "tool" and m.get("tool_call_id") not in ids:
                return True
        return False

    check("fit: ชุดเดิมต้องไม่มี orphan อยู่แล้ว", _has_orphan_tool(msgs) is False)
    fit, dropped = S.fit_messages(msgs, budget=200)
    check("fit: ตัดของเก่าออก", dropped >= 1 and len(fit) < len(msgs), (dropped, len(fit)))
    check("fit: คง system ไว้", fit[0]["role"] == "system" and fit[0]["content"] == "sys", fit)
    check("fit: คงงานล่าสุดไว้", fit[-1]["content"] == "งานล่าสุด", fit)
    check("fit: ไม่เหลือ tool result กำพร้า", _has_orphan_tool(fit) is False, fit)
    check("fit: อยู่ในงบ", S.messages_tokens(fit) <= 200, S.messages_tokens(fit))

    # งบเล็กมาก: ต้องตัด assistant ที่มี tool_calls พร้อมผลลัพธ์ของมันด้วยกัน
    big = [{"role": "system", "content": "s"},
           {"role": "user", "content": "a" * 2000},
           {"role": "assistant", "content": "",
            "tool_calls": [{"id": "c9", "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"}}]},
           {"role": "tool", "tool_call_id": "c9", "content": "b" * 2000},
           {"role": "user", "content": "งานล่าสุด"}]
    fit2, dropped2 = S.fit_messages(big, budget=100)
    check("fit: งบเล็กตัดคู่ tool_call/tool_result ด้วยกัน",
          dropped2 >= 3 and _has_orphan_tool(fit2) is False, (dropped2, fit2))
    check("fit: งบเล็กอยู่ในงบ", S.messages_tokens(fit2) <= 100, S.messages_tokens(fit2))
    check("fit: งบเล็กคงงานล่าสุด", fit2[-1]["content"] == "งานล่าสุด", fit2)
    check("fit: ชุดเดิมไม่ถูกแก้ (ไม่ mutate)",
          len(msgs) == 5 and msgs[0]["content"] == "sys", len(msgs))

    same, d0 = S.fit_messages([{"role": "system", "content": "s"},
                               {"role": "user", "content": "hi"}], budget=100000)
    check("fit: ไม่ตัดเมื่ออยู่ในงบ", d0 == 0 and len(same) == 2)
finally:
    S.load_config = _orig_load
    if _orig_env is None:
        os.environ.pop("SOONAI_CONTEXT_BUDGET", None)
    else:
        os.environ["SOONAI_CONTEXT_BUDGET"] = _orig_env

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL USAGE TESTS PASSED")
