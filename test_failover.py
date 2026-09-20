# -*- coding: utf-8 -*-
"""Regression: โควต้าหมด (402) ต้องสลับค่ายอัตโนมัติ ไม่ตายกลางทาง."""
import json
import os
import sys
import tempfile
import time

# แยกไฟล์จำสุขภาพโมเดลของเทสต์ (กันแตะของจริง + กันรันซ้ำเพี้ยน)
_tmp_health = os.path.join(tempfile.gettempdir(),
                           f"soonai-health-test-{os.getpid()}.json")
os.environ["SOONAI_HEALTH_FILE"] = _tmp_health
try:
    os.remove(_tmp_health)
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import soonai as S  # noqa: E402 - ต้อง sys.path.insert ก่อน

HF_MSG = ("You have depleted your monthly included credits. "
          "Purchase pre-paid credits to continue using Inference Providers. "
          "Alternatively, subscribe to PRO to get 20x more included usage.")

# 1) ตรวจจับโควต้าตาย
assert S._quota_dead(402, "anything") is True
assert S._quota_dead(200, HF_MSG) is True
assert S._quota_dead(429, "Rate limit exceeded, retry in 5s") is False
assert S._quota_dead(429, "free-models-per-day limit reached") is True
assert S._quota_dead(200, "ok") is False
assert S._quota_dead(500, "overloaded") is False
assert S._quota_dead(200, None) is False
print("ok 1: _quota_dead")

# 2) เลือกค่ายสำรอง (mock keys/models)
orig = (S.load_keys, S.get_models, S._local_reachable, S.save_json,
        S._post_chat, S._failover_provider)
S.load_keys = lambda: {"openrouter": "x"}
S.get_models = lambda pid, refresh=False: (
    (["a:free", "b-paid"], {"a:free": {"prompt": 0, "completion": 0}})
    if pid == "openrouter" else ([], {}))
S._local_reachable = lambda pid: False
S._QUOTA_DEAD.clear()
try:
    np, nm = S._failover_provider("huggingface", "Qwen/Qwen3-32B")
    assert (np, nm) == ("openrouter", "a:free"), (np, nm)
    assert S._QUOTA_DEAD.get("huggingface") and S._QUOTA_DEAD.get(("huggingface", "Qwen/Qwen3-32B"))
    S._QUOTA_DEAD["openrouter"] = time.time() + 3600
    assert S._failover_provider("huggingface", "m") == ("", "")
    print("ok 2: _failover_provider")

    # 3) ข้อความไทยตอนหมดทาง
    msg = S.format_api_error("huggingface", 402, HF_MSG)
    assert ("เครดิต" in msg or "โควต้า" in msg) and "soonai use" in msg, msg
    print("ok 3: format_api_error 402")

    # 4) agent loop: 402 -> สลับค่าย -> 200 จบงาน
    S._QUOTA_DEAD.clear()
    S.save_json = lambda *a, **k: True

    class FakeResp:
        def __init__(self, code, payload):
            self.status_code = code
            self.text = payload if isinstance(payload, str) else json.dumps(payload)

        def json(self):
            return json.loads(self.text)

    calls = []

    def fake_post(url, headers=None, payload=None, timeout=0, stream=False,
                  tag="", retries=0):
        calls.append((url, (payload or {}).get("model")))
        if "huggingface" in url:
            return FakeResp(402, {"error": HF_MSG})
        return FakeResp(200, {"choices": [{"message": {"content": "done",
                                                      "tool_calls": []}}]})

    S._post_chat = fake_post
    out, err, used, info = S._agent_steps(
        "huggingface", "Qwen/Qwen3-32B", [{"role": "user", "content": "hi"}],
        0.2, auto_yes=True, max_steps=5)
    assert err == "" and out == "done" and used == 0, (out, err, used)
    assert len(calls) == 2 and "openrouter" in calls[1][0] \
        and calls[1][1] == "a:free", calls
    print("ok 4: agent 402 -> switch provider -> done")

    # 5) send_messages เส้น ask: 402 -> สลับ -> 200
    S._failover_provider = lambda p, m: ("openrouter", "z:free")
    calls2 = []

    def fake_post2(url, headers=None, payload=None, timeout=0, stream=False,
                   tag="", retries=0):
        calls2.append((url, (payload or {}).get("model")))
        if "huggingface" in url:
            return FakeResp(402, {"error": HF_MSG})
        return FakeResp(200, {"choices": [{"message": {"content": "ok2"}}]})

    S._post_chat = fake_post2
    res = S.send_messages("huggingface", "Qwen/Qwen3-32B",
                          [{"role": "user", "content": "hi"}], 0.2, stream=False)
    assert res == "ok2", res
    assert len(calls2) == 2 and "openrouter" in calls2[1][0] \
        and calls2[1][1] == "z:free", calls2
    print("ok 5: send_messages 402 -> switch -> done")
finally:
    (S.load_keys, S.get_models, S._local_reachable, S.save_json,
     S._post_chat, S._failover_provider) = orig
    S._QUOTA_DEAD.clear()

# 6) หมุนโมเดลไม่ซ้ำ (rotation) + จำข้ามโปรเซส
S.get_models = lambda pid, refresh=False: (["m1:free", "m2:free", "m3:free"], {})
S._MODEL_DEAD.clear()
S.LAST_MODEL_SWITCH = None
picks = []
cur = "m0:free"
for _ in range(3):
    nm = S._failover_free("openrouter", cur, 429, "Rate limit exceeded", 0)
    assert nm and nm != cur, (cur, nm)
    picks.append(nm)
    cur = nm
assert len(set(picks)) == 3, f"ต้องได้ 3 ตัวไม่ซ้ำ: {picks}"
print("ok 6: rotation ไม่วนตัวเดิม:", picks)

# จำข้ามโปรเซส: ล้าง RAM แล้วต้องยังข้ามตัวที่ตายค้างดิสก์
S.get_models = lambda pid, refresh=False: (
    ["m1:free", "m2:free", "m3:free", "m4:free"], {})
S._MODEL_DEAD.clear()
nm = S._failover_free("openrouter", "m9:free", 503, "overloaded", 0)
assert nm in ("m3:free", "m4:free"), nm  # ต้องไม่ย้อนไป m0/m1/m2 ที่ตายค้างดิสก์
print("ok 7: ข้ามตัวตายค้างดิสก์แม้ RAM ถูกล้าง:", nm)

# 8) ราคาต่อ 1M tokens (money-aware)
assert S._unit_cost("openrouter", "m", {"m": {"prompt": 1e-6, "completion": 0}}) == 1.0
assert S._unit_cost("huggingface", "m", {"m": {"hf_min_in": 2.5}}) == 2.5
assert S._unit_cost("puter", "m", {"m": {"puter_in": 50}}) == 0.5
assert S._unit_cost("groq", "m", {}) == 0.0
print("ok 8: _unit_cost")

# 9) TTL: 429 ธรรมดาจำสั้น (120s), ตัวอื่นจำ 600s
S.get_models = lambda pid, refresh=False: (["t1:free", "t2:free", "t3:free"], {})
S._MODEL_DEAD.clear()
S._failover_free("openrouter", "t1:free", 429, "Rate limit exceeded", 0)
S._failover_free("openrouter", "t2:free", 503, "overloaded", 0)
h = S._health_load()
now = time.time()
k1 = S._health_key("openrouter", "t1:free")
k2 = S._health_key("openrouter", "t2:free")
assert 60 < h["dead"][k1] - now < 180, h["dead"][k1] - now
assert 500 < h["dead"][k2] - now < 700, h["dead"][k2] - now
print("ok 9: TTL 429=120s / อื่น=600s")

# 10) consume รับเฉพาะตรงค่าย+ตรงโมเดลต้นทาง (กันหยิบของเธรด/รอบอื่น)
S.LAST_MODEL_SWITCH = {"provider": "openrouter", "from": "a",
                       "to": "b", "ts": time.time()}
assert S.consume_model_switch("groq") is None
assert S.LAST_MODEL_SWITCH is not None, "ค่ายไม่ตรงต้องไม่ล้าง"
assert S.consume_model_switch("openrouter", "other") is None
assert S.LAST_MODEL_SWITCH is not None, "โมเดลต้นทางไม่ตรงต้องไม่ล้าง"
got = S.consume_model_switch("openrouter", "a")
assert got and got["to"] == "b" and S.LAST_MODEL_SWITCH is None, got
S.LAST_MODEL_SWITCH = {"provider": "openrouter", "from": "a",
                       "to": "b", "ts": time.time() - 4000}
assert S.consume_model_switch("openrouter", "a") is None, "หมดอายุ 30 นาทีต้องทิ้ง"
print("ok 10: consume match-guard + expiry")

# 11) apply รับ switch ตรงจาก info ได้ (ไม่พึ่ง global)
_rsj = S.save_json
S.save_json = lambda *a, **k: True
try:
    cfg = {}
    nm = S.apply_model_switch("openrouter", "a", {}, cfg,
                              {"provider": "openrouter", "from": "a",
                               "to": "c:free", "ts": time.time()})
    assert nm == "c:free" and cfg.get("model") == "c:free", (nm, cfg)
    assert S.apply_model_switch("openrouter", "a", {}, {}) == "a"
finally:
    S.save_json = _rsj
print("ok 11: apply explicit sw + fallback ว่าง")

# ตั้งแต่นี้: กันเขียน config จริง แต่ให้ health file (temp) เขียนได้ปกติ
_real_sj = S.save_json


def _fake_sj(path, obj):
    if str(path) == str(S.CONFIG_FILE):
        return True
    return _real_sj(path, obj)


S.save_json = _fake_sj

# 12) เกทข้ามค่าย: โควต้า/ล่มชั่วคราว/401/403/404 ไปต่อ · 400 หยุด
assert S._should_try_provider(402, "anything") is True
assert S._should_try_provider(429, "Rate limit exceeded") is True
assert S._should_try_provider(503, "overloaded") is True
assert S._should_try_provider(401, "invalid api key") is True
assert S._should_try_provider(403, "forbidden") is True
assert S._should_try_provider(404, "not found") is True
assert S._should_try_provider(400, "unsupported parameter") is False
assert S._should_try_provider(200, "ok") is False
print("ok 12: _should_try_provider")

# 13) 404 = โมเดลหาย: จำยาว + ไปตัวถัดไปค่ายเดิม
S.get_models = lambda pid, refresh=False: (["n1:free", "n2:free"], {})
S._MODEL_DEAD.clear()
nm = S._failover_free("openrouter", "n1:free", 404, "model not found", 0)
assert nm == "n2:free", nm
h = S._health_load()
now = time.time()
assert 3000 < h["dead"][S._health_key("openrouter", "n1:free")] - now < 4200
print("ok 13: 404 ไปตัวถัดไป + จำ 3600s")

# 14) ค่ายเดิมหมดตัว (429) → ข้ามค่ายอัตโนมัติ
S._MODEL_DEAD.clear()
S._QUOTA_DEAD.clear()
S.LAST_MODEL_SWITCH = None
S.load_keys = lambda: {"openrouter": "x", "groq": "y"}
S.get_models = lambda pid, refresh=False: (
    (["m1:free"], {}) if pid == "openrouter" else (["g1:free"], {}))
S._local_reachable = lambda pid: False


class FakeResp2:
    def __init__(self, code, payload):
        self.status_code = code
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        return json.loads(self.text)


_calls14 = []


def _fake_post14(url, headers=None, payload=None, timeout=0, stream=False,
                 tag="", retries=0):
    _calls14.append((url, (payload or {}).get("model")))
    if "groq" in url:
        return FakeResp2(200, {"choices": [{"message": {"content": "done",
                                                       "tool_calls": []}}]})
    return FakeResp2(429, {"error": "Rate limit exceeded, retry in 5s"})


_orig_post = S._post_chat
S._post_chat = _fake_post14
try:
    out, err, used, info = S._agent_steps(
        "openrouter", "m1:free", [{"role": "user", "content": "hi"}],
        0.2, auto_yes=True, max_steps=5)
finally:
    S._post_chat = _orig_post
assert err == "" and out == "done", (out, err)
assert len(_calls14) == 2 and "groq" in _calls14[1][0] \
    and _calls14[1][1] == "g1:free", _calls14
assert (info or {}).get("model_switch", {}).get("from_provider") == "openrouter", info
print("ok 14: 429 ค่ายหมดตัว → ข้ามค่าย + info บอกค่ายเดิม")

# 15) 401 (key ใช้ไม่ได้) → ข้ามค่าย
S._MODEL_DEAD.clear()
S._QUOTA_DEAD.clear()
S.LAST_MODEL_SWITCH = None
_calls15 = []


def _fake_post15(url, headers=None, payload=None, timeout=0, stream=False,
                 tag="", retries=0):
    _calls15.append((url, (payload or {}).get("model")))
    if "groq" in url:
        return FakeResp2(200, {"choices": [{"message": {"content": "ok401",
                                                       "tool_calls": []}}]})
    return FakeResp2(401, {"error": {"message": "invalid api key"}})


S._post_chat = _fake_post15
try:
    out, err, used, info = S._agent_steps(
        "openrouter", "m1:free", [{"role": "user", "content": "hi"}],
        0.2, auto_yes=True, max_steps=5)
finally:
    S._post_chat = _orig_post
assert err == "" and out == "ok401", (out, err)
assert len(_calls15) == 2 and "groq" in _calls15[1][0], _calls15
print("ok 15: 401 → ข้ามค่าย")

# 16) 400 (request ผิด) → ไม่เผาค่ายอื่น
S._MODEL_DEAD.clear()
S._QUOTA_DEAD.clear()
_calls16 = []


def _fake_post16(url, headers=None, payload=None, timeout=0, stream=False,
                 tag="", retries=0):
    _calls16.append(url)
    return FakeResp2(400, {"error": {"message": "unsupported parameter"}})


S._post_chat = _fake_post16
try:
    out, err, used, info = S._agent_steps(
        "openrouter", "m1:free", [{"role": "user", "content": "hi"}],
        0.2, auto_yes=True, max_steps=5)
finally:
    S._post_chat = _orig_post
assert err.startswith("ERROR:") and len(_calls16) == 1, (out, err, _calls16)
print("ok 16: 400 ไม่ข้ามค่าย")

# 17) ttl ข้ามค่ายแบบสั้น (ล่มชั่วคราว ≠ โควต้าตาย 6 ชม.)
S._QUOTA_DEAD.clear()
np, nm = S._failover_provider("huggingface", "m", ttl=1800)
assert (np, nm) == ("groq", "g1:free"), (np, nm)
now = time.time()
assert 1500 < S._QUOTA_DEAD["huggingface"] - now < 2100, S._QUOTA_DEAD["huggingface"]
h = S._health_load()
k = S._health_key("huggingface", "m")
assert 1500 < h["dead"][k] - now < 2100
print("ok 17: ttl สั้นจำทั้ง RAM+ดิสก์")

# 18) รอบจ่ายเงิน: มี key ถึงมา (Anthropic) · มีฟรีต้องเอาฟรีก่อน
S._QUOTA_DEAD.clear()
S._MODEL_DEAD.clear()
S.load_keys = lambda: {"anthropic": "k"}
S.get_models = lambda pid, refresh=False: (
    (["claude-x"], {}) if pid == "anthropic" else ([], {}))
S._local_reachable = lambda pid: False
np, nm = S._failover_provider("openrouter", "m")
assert (np, nm) == ("anthropic", "claude-x"), (np, nm)
S.load_keys = lambda: {"openrouter": "x", "anthropic": "k"}
S.get_models = lambda pid, refresh=False: (
    (["m:free"], {}) if pid == "openrouter"
    else ((["claude-x"], {}) if pid == "anthropic" else ([], {})))
S._QUOTA_DEAD.clear()
S._MODEL_DEAD.clear()
S.load_keys = lambda: {"groq": "x", "anthropic": "k"}
S.get_models = lambda pid, refresh=False: (
    (["g:free"], {}) if pid == "groq"
    else ((["claude-x"], {}) if pid == "anthropic" else ([], {})))
np, nm = S._failover_provider("fireworks", "f")
assert np == "groq", (np, nm)
print("ok 18: paid ทางสุดท้าย · ฟรีมาก่อนเสมอ")

# 19) agent ข้ามตระกูลจริง: openrouter 429 → claude ตอบจบ
S._MODEL_DEAD.clear()
S._QUOTA_DEAD.clear()
S.LAST_MODEL_SWITCH = None
S.load_keys = lambda: {"openrouter": "x", "anthropic": "y"}
S.get_models = lambda pid, refresh=False: (
    (["m1:free"], {}) if pid == "openrouter"
    else ((["claude-x"], {}) if pid == "anthropic" else ([], {})))


class FakeResp3:
    def __init__(self, code, payload):
        self.status_code = code
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        return json.loads(self.text)


_calls19 = []


def _fake_post19(url, headers=None, payload=None, timeout=0, stream=False,
                 tag="", retries=0):
    _calls19.append(url)
    if "anthropic" in url:
        return FakeResp3(200, {"content": [{"type": "text", "text": "done"}],
                               "stop_reason": "end_turn"})
    return FakeResp3(429, {"error": "Rate limit exceeded, retry in 5s"})


S._post_chat = _fake_post19
try:
    out, err, used, info = S._agent_steps(
        "openrouter", "m1:free", [{"role": "user", "content": "hi"}],
        0.2, auto_yes=True, max_steps=5)
finally:
    S._post_chat = _orig_post
assert err == "" and out == "done", (out, err)
assert len(_calls19) == 2 and "anthropic" in _calls19[1], _calls19
_sw19 = (info or {}).get("model_switch") or {}
assert _sw19.get("provider") == "anthropic" \
    and _sw19.get("from_provider") == "openrouter", _sw19
print("ok 19: agent ข้าม OpenAI→Anthropic จบงาน")

# 20) helper สลับ driver: ตระกูลเดิมใช้ตัวเดิม · ข้ามตระกูลสร้างใหม่
S.load_keys = lambda: {"anthropic": "y", "groq": "z"}
_d = S._OpenAICompatDriver("openrouter", "m", 0.2)
_same = S._agent_switch_driver(_d, "groq", "g")
assert _same is _d and _d.provider_key == "groq" and _d.model == "g"
_d2 = S._OpenAICompatDriver("openrouter", "m", 0.2)
_cross = S._agent_switch_driver(_d2, "anthropic", "claude-x")
assert type(_cross).__name__ == "_AnthropicDriver" and _cross.model == "claude-x"
_back = S._agent_switch_driver(_cross, "groq", "g")
assert type(_back).__name__ == "_OpenAICompatDriver" and _back.provider_key == "groq"
_c = S._OpenAIChatDriver("openrouter", "m", [], 0.2, False, "", None)
_cc = S._chat_switch_driver(_c, "anthropic", "claude-x", [], 0.2, False, "", None, 0)
assert type(_cc).__name__ == "_AnthropicChatDriver"
assert S._AnthropicDriver.can_switch_provider is True
print("ok 20: driver ข้ามตระกูลทั้ง agent/chat")

try:
    os.remove(_tmp_health)
except Exception:
    pass

print("ALL FAILOVER TESTS PASSED")
