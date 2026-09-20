# -*- coding: utf-8 -*-
"""Characterization test ของ send_messages (ล็อกสตรีมมิ่ง + retry ก่อน refactor)

ครอบ: สตรีมทีละชิ้น · คำตอบไม่มีข้อมูล · ตัดพารามิเตอร์ที่ไม่รองรับ (400) ·
400 "provider returned error" · 429→สลับโมเดล · 402→สลับค่าย · คำตอบโดนตัด (length/max_tokens) ·
thinking ของ Anthropic · on_chunk ถูกเรียกแบบไหน · effort ต่อค่าย
ไม่แตะเน็ต/ไม่ใช้ key (mock _post_chat + failover + wait)
"""
import io
import json
import sys

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


def sse(*chunks, finish=None):
    """สร้าง SSE: content ทีละชิ้น + finish_reason (มีบรรทัดเสียปนไปด้วย)"""
    lines = ["", ": keep-alive", "event: message"]
    for c in chunks:
        lines.append("data: " + json.dumps({"choices": [{"delta": {"content": c}}]}))
    if finish:
        lines.append("data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": finish}]}))
    lines.append("ไม่ใช่ data: บรรทัดนี้ต้องถูกข้าม")
    lines.append("data: [DONE]")
    return lines


def oai_json(content="", finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


def anth_json(text="", stop="end_turn", thinking=False):
    blocks = []
    if thinking:
        blocks.append({"type": "thinking", "thinking": "คิดอยู่"})
    if text:
        blocks.append({"type": "text", "text": text})
    return {"content": blocks, "stop_reason": stop}


class Fixture:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        # สำเนาลึก: payload ถูก mutate ต่อ (ตัดพารามิเตอร์/สลับโมเดล) — เก็บภาพ ณ ตอนส่งจริง
        snap = json.loads(json.dumps(payload, ensure_ascii=False)) if payload else payload
        self.requests.append({"url": url, "headers": headers, "payload": snap,
                              "stream": stream, "tag": tag, "retries": retries})
        if not self.responses:
            return Resp(payload=oai_json("จบ"))
        return self.responses.pop(0)


def run_send(fx, *, provider="openrouter", model="m1", messages=None, **kw):
    """เรียก send_messages จริงโดย mock ชั้นเครือข่าย/failover (คืน (ผลลัพธ์, fx))"""
    filled = {"stream": False}
    filled.update(kw)
    orig = (S._post_chat, S.load_keys, S.load_config, S.console, S._wait_animated,
            S._failover_free, S._failover_provider, S._apply_provider_switch)
    S._post_chat = fx.post
    S.load_keys = lambda: {}
    S.load_config = lambda: {}
    S.console = Console(file=io.StringIO(), width=200)
    S._wait_animated = lambda *a, **k: None
    S._failover_free = filled.pop("_failover_free", lambda p, m, st, bd, sw, max_switches=2: "")
    S._failover_provider = filled.pop("_failover_provider", lambda p, m: ("", ""))
    S._apply_provider_switch = filled.pop("_apply_provider_switch", lambda *a: None)
    try:
        out = S.send_messages(provider, model,
                             messages or [{"role": "user", "content": "hi"}], 0.7, **filled)
        return out
    finally:
        (S._post_chat, S.load_keys, S.load_config, S.console, S._wait_animated,
         S._failover_free, S._failover_provider, S._apply_provider_switch) = orig


# ------------------------------------------------------------------ streaming
def t_stream_chunks():
    fx = Fixture([Resp(sse=sse("สวัสดี ", "ชาวโลก", finish="stop"))])
    got = []
    out = run_send(fx, stream=True, on_chunk=got.append)
    check("stream: รวมข้อความถูกต้อง", out == "สวัสดี ชาวโลก", out)
    check("stream: on_chunk ทีละชิ้น", got == ["สวัสดี ", "ชาวโลก"], got)
    check("stream: ข้ามบรรทัดที่ไม่ใช่ data/DONE",
          fx.requests[0]["payload"]["stream"] is True and fx.requests[0]["tag"] == "chat-openai")


def t_stream_error_chunk():
    fx = Fixture([Resp(payload={}, sse=["data: " + json.dumps({"error": {"message": "boom"}})])])
    try:
        run_send(fx, stream=True)
        check("stream: error ในชิ้นข้อมูลต้อง raise", False, "ไม่ raise")
    except RuntimeError as e:
        check("stream: error ในชิ้นข้อมูลต้อง raise", "boom" in str(e), str(e))


def t_stream_empty():
    fx = Fixture([Resp(payload={}, sse=["data: [DONE]"])])
    try:
        run_send(fx, stream=True)
        check("stream: ว่างเปล่าต้อง raise", False, "ไม่ raise")
    except RuntimeError as e:
        check("stream: ว่างเปล่าต้อง raise", "สตรีมว่าง" in str(e), str(e))


def t_stream_length_continue():
    fx = Fixture([Resp(payload={}, sse=sse("ครึ่งแรก", finish="length")),
                  Resp(payload={}, sse=sse("ครึ่งหลัง", finish="stop"))])
    got = []
    out = run_send(fx, stream=True, on_chunk=got.append)
    check("stream: โดนตัดแล้วขอต่อ", out == "ครึ่งแรกครึ่งหลัง", out)
    check("stream: ขอต่อ 2 คำขอ", len(fx.requests) == 2, len(fx.requests))
    second = fx.requests[1]["payload"]["messages"]
    check("stream: คำขอที่สองแนบ assistant + continue",
          second[-2] == {"role": "assistant", "content": "ครึ่งแรก"}
          and second[-1] == {"role": "user", "content": "continue"}, second[-2:])


# ------------------------------------------------------------------ non-stream
def t_nonstream_basic():
    fx = Fixture([Resp(payload=oai_json("ตอบครั้งเดียว"))])
    got = []
    out = run_send(fx, stream=False, on_chunk=got.append)
    check("non-stream: ผลลัพธ์", out == "ตอบครั้งเดียว")
    check("non-stream: on_chunk ครั้งเดียว", got == ["ตอบครั้งเดียว"], got)
    check("non-stream: max_tokens เริ่มต้น 16384",
          fx.requests[0]["payload"]["max_tokens"] == 16384, fx.requests[0]["payload"])
    check("non-stream: messages ถูกคัดลอก (ไม่แก้ของเดิม)",
          fx.requests[0]["payload"]["messages"] is not None)


def t_nonstream_length_rounds():
    fx = Fixture([Resp(payload=oai_json("1", finish="length")),
                  Resp(payload=oai_json("2", finish="length")),
                  Resp(payload=oai_json("3", finish="length"))])
    got = []
    out = run_send(fx, stream=False, on_chunk=got.append)
    check("non-stream: ต่อคำตอบไม่เกิน 3 รอบ", len(fx.requests) == 3 and out == "123",
          (len(fx.requests), out))
    check("non-stream: on_chunk ทุกรอบ", got == ["1", "2", "3"], got)


def t_drop_unsupported_params():
    fx = Fixture([Resp(400, text=json.dumps({"error": {"message":
                                                       "Unsupported parameter: 'max_tokens' is not supported"}})),
                  Resp(payload=oai_json("สำเร็จ"))])
    out = run_send(fx, stream=False, effort="medium")
    first, second = fx.requests[0]["payload"], fx.requests[1]["payload"]
    check("400: ตัด max_tokens ที่ค่ายไม่รับ", "max_tokens" not in second and "max_tokens" in first,
          sorted(second))
    check("400: ยังคง reasoning_effort ที่ไม่ได้ถูกร้อง", second.get("reasoning_effort") == "medium",
          second.get("reasoning_effort"))
    check("400: ได้คำตอบหลังลองใหม่", out == "สำเร็จ", out)


def t_drop_reasoning_on_think():
    fx = Fixture([Resp(400, text=json.dumps({"error": {"message": "reasoning_effort think not supported"}})),
                  Resp(payload=oai_json("ok"))])
    out = run_send(fx, stream=False, effort="high")
    check("400: ค่ายที่บอก 'think' ตัด reasoning_effort",
          "reasoning_effort" not in fx.requests[1]["payload"], sorted(fx.requests[1]["payload"]))
    check("400: ได้คำตอบ", out == "ok", out)


def t_retry_provider_error_once():
    fx = Fixture([Resp(400, text=json.dumps({"error": {"message": "provider returned error"}})),
                  Resp(payload=oai_json("รอบสองผ่าน"))])
    out = run_send(fx, stream=False)
    check("400 provider error: ลองใหม่ครั้งเดียวแล้วจบ",
          len(fx.requests) == 2 and out == "รอบสองผ่าน", (len(fx.requests), out))


def t_transient_model_failover():
    fx = Fixture([Resp(429, text=json.dumps({"error": "rate limit"})),
                  Resp(payload=oai_json("ค่ายเดิม โมเดลใหม่"))])
    seen = []

    def ff(provider, model, status, body, switches, max_switches=2):
        seen.append((provider, model, status, switches))
        return "m2" if switches == 0 else ""

    out = run_send(fx, stream=False, _failover_free=ff)
    check("429: สลับโมเดลค่ายเดิม", seen == [("openrouter", "m1", 429, 0)], seen)
    check("429: คำขอถัดไปใช้โมเดลใหม่", fx.requests[1]["payload"]["model"] == "m2")
    check("429: ได้คำตอบ", out == "ค่ายเดิม โมเดลใหม่", out)


def t_quota_switch_provider():
    fx = Fixture([Resp(402, text=json.dumps({"error": "depleted credits"})),
                  Resp(payload=oai_json("ค่ายใหม่"))])
    switched = []
    out = run_send(fx, provider="huggingface", model="Qwen/Qwen3-32B", stream=False,
                   _failover_provider=lambda p, m: ("groq", "llama-3.3-70b-versatile"),
                   _apply_provider_switch=lambda np_, nm, reason: switched.append((np_, nm)))
    check("402: สลับค่าย", switched == [("groq", "llama-3.3-70b-versatile")], switched)
    check("402: ใช้ URL ค่ายใหม่", "groq.com" in fx.requests[1]["url"], fx.requests[1]["url"])
    check("402: ใช้โมเดลค่ายใหม่",
          fx.requests[1]["payload"]["model"] == "llama-3.3-70b-versatile")
    check("402: ได้คำตอบ", out == "ค่ายใหม่", out)


def t_error_raises():
    fx = Fixture([Resp(500, text=json.dumps({"error": {"message": "boom"}}))])
    try:
        run_send(fx, stream=False)
        check("500: raise RuntimeError", False, "ไม่ raise")
    except RuntimeError as e:
        check("500: raise RuntimeError พร้อมข้อความไทย", "boom" in str(e), str(e))


def t_effort_payloads():
    fx = Fixture([Resp(payload=oai_json("a"))])
    run_send(fx, stream=False, effort="medium")
    check("effort: ส่ง reasoning_effort", fx.requests[0]["payload"]["reasoning_effort"] == "medium")
    fx2 = Fixture([Resp(payload=oai_json("b"))])
    run_send(fx2, provider="ollama", model="llama3.1", stream=False, effort="medium")
    check("effort: ค่าย local ไม่ส่ง reasoning_effort",
          "reasoning_effort" not in fx2.requests[0]["payload"], sorted(fx2.requests[0]["payload"]))
    fx3 = Fixture([Resp(payload=oai_json("c"))])
    run_send(fx3, stream=False, effort="bogus")
    check("effort: ค่ามั่ว = ปิด", "reasoning_effort" not in fx3.requests[0]["payload"])
    fx4 = Fixture([Resp(payload=oai_json("d"))])
    run_send(fx4, stream=False, max_tokens=600, effort="low")
    check("max_tokens: ใช้ค่าที่ส่งมา", fx4.requests[0]["payload"]["max_tokens"] == 600)


# ------------------------------------------------------------------ anthropic
def t_anthropic_basic_and_system():
    fx = Fixture([Resp(payload=anth_json("สวัสดี"))])
    got = []
    out = run_send(fx, provider="anthropic", model="claude-x", stream=True, on_chunk=got.append,
                   messages=[{"role": "system", "content": "sys"},
                             {"role": "user", "content": "hi"}])
    body = fx.requests[0]["payload"]
    check("anth: system แยกออก", body.get("system") == "sys" and body["messages"][0]["role"] == "user",
          body.get("system"))
    check("anth: ยิงไม่สตรีม + tag", fx.requests[0]["stream"] is False
          and fx.requests[0]["tag"] == "chat-anthropic")
    check("anth: max_tokens 8192", body["max_tokens"] == 8192, body["max_tokens"])
    check("anth: on_chunk ครั้งเดียวตอนจบ", got == ["สวัสดี"], got)
    check("anth: ผลลัพธ์", out == "สวัสดี", out)


def t_anthropic_thinking():
    fx = Fixture([Resp(payload=anth_json("คิดแล้วตอบ"))])
    run_send(fx, provider="anthropic", model="claude-x", stream=False, effort="medium")
    body = fx.requests[0]["payload"]
    check("anth: effort เปิด thinking", body.get("thinking") == {"type": "enabled",
                                                                 "budget_tokens": 10000}, body.get("thinking"))
    check("anth: thinking บังคับ temperature=1", body["temperature"] == 1, body["temperature"])
    check("anth: ขยาย max_tokens", body["max_tokens"] == 10000 + 8192, body["max_tokens"])


def t_anthropic_thinking_rejected_retry():
    """ค่ายที่ปฏิเสธ thinking: คาดหวัง "ลองใหม่แบบไม่เปิด thinking" (พฤติกรรมที่ควรเป็น)"""
    fx = Fixture([Resp(400, text=json.dumps({"error": {"message":
                                                       "thinking is not supported for this model"}})),
                  Resp(payload=anth_json("ตอบแบบปกติ"))])
    out = run_send(fx, provider="anthropic", model="claude-x", stream=False, effort="medium")
    check("anth: 400 thinking → ยิงใหม่ 2 ครั้ง", len(fx.requests) == 2, len(fx.requests))
    if len(fx.requests) == 2:
        check("anth: คำขอที่สอง 'ไม่' เปิด thinking",
              "thinking" not in fx.requests[1]["payload"], sorted(fx.requests[1]["payload"]))
    check("anth: ได้คำตอบแบบไม่ thinking", out == "ตอบแบบปกติ", out)


def t_anthropic_length_continue():
    fx = Fixture([Resp(payload=anth_json("ครึ่งแรก", stop="max_tokens")),
                  Resp(payload=anth_json("ครึ่งหลัง", stop="end_turn"))])
    got = []
    out = run_send(fx, provider="anthropic", model="claude-x", stream=False, on_chunk=got.append)
    check("anth: max_tokens → ขอต่อ", out == "ครึ่งแรกครึ่งหลัง", out)
    check("anth: ขอต่อแค่ครั้งเดียว", len(fx.requests) == 2, len(fx.requests))
    second = fx.requests[1]["payload"]
    check("anth: คำขอต่อไม่มี thinking",
          "thinking" not in second and second["temperature"] == 0.7, sorted(second))
    check("anth: on_chunk ครั้งเดียวกับข้อความรวม", got == ["ครึ่งแรกครึ่งหลัง"], got)


def t_anthropic_failover_and_error():
    fx = Fixture([Resp(429, text=json.dumps({"error": {"message": "rate limit"}})),
                  Resp(payload=anth_json("โมเดลใหม่"))])
    seen = []

    def ff(provider, model, status, body, switches, max_switches=2):
        seen.append((provider, model, status))
        return "claude-haiku-4-5"

    out = run_send(fx, provider="anthropic", model="claude-sonnet-4-5", stream=False,
                   _failover_free=ff)
    check("anth: 429 → สลับโมเดล", seen == [("anthropic", "claude-sonnet-4-5", 429)], seen)
    check("anth: คำขอที่สองใช้โมเดลใหม่",
          fx.requests[1]["payload"]["model"] == "claude-haiku-4-5")
    check("anth: ได้คำตอบ", out == "โมเดลใหม่", out)

    fx2 = Fixture([Resp(500, text=json.dumps({"error": {"message": "boom"}}))])
    try:
        run_send(fx2, provider="anthropic", model="claude-x", stream=False)
        check("anth: error อื่น raise", False, "ไม่ raise")
    except RuntimeError as e:
        check("anth: error อื่น raise ข้อความไทย", "boom" in str(e), str(e))


for fn in (t_stream_chunks, t_stream_error_chunk, t_stream_empty, t_stream_length_continue,
           t_nonstream_basic, t_nonstream_length_rounds, t_drop_unsupported_params,
           t_drop_reasoning_on_think, t_retry_provider_error_once, t_transient_model_failover,
           t_quota_switch_provider, t_error_raises, t_effort_payloads,
           t_anthropic_basic_and_system, t_anthropic_thinking,
           t_anthropic_thinking_rejected_retry, t_anthropic_length_continue,
           t_anthropic_failover_and_error):
    try:
        fn()
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAILS.append(f"{fn.__name__} raised {e}")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)
print("ALL SEND_MESSAGES TESTS PASSED")
