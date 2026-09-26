# -*- coding: utf-8 -*-
"""Characterization test ของ agent loop (ล็อกพฤติกรรมก่อน/หลัง refactor)

ครอบทั้งเส้น OpenAI-compatible และ Anthropic แบบ native:
- รัน tool + ส่งผลกลับ / ปฏิเสธ / tool ที่ไม่มีอยู่ซ้ำ
- text fallback (โมเดลเขียน JSON ในข้อความ)
- failover: 429 → สลับโมเดลค่ายเดิม · 402 → สลับค่าย (เฉพาะ OpenAI-compatible)
- 404 tools ไม่รองรับ → ยิงใหม่แบบไม่มี tools
- เพดานก้าว (cap) + info
ไม่มีเน็ต/ไม่มี key: mock _post_chat + approve + run_tool ทั้งหมด
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
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)
        self.closed = False

    def json(self):
        return json.loads(self.text) if isinstance(self.text, str) and self.text else self._payload

    def close(self):
        self.closed = True


NO_TOOLS_MSG = "No endpoints found that support tool use."


def oai(content="", tool_calls=None, finish="stop"):
    msg = {"content": content}
    if tool_calls:
        msg["tool_calls"] = [{"id": f"call_{i}", "type": "function",
                              "function": {"name": n, "arguments": json.dumps(a)}}
                             for i, (n, a) in enumerate(tool_calls)]
    return {"choices": [{"message": msg, "finish_reason": finish}]}


def anth(blocks):
    return {"content": blocks, "stop_reason": "end_turn"}


class Fixture:
    """mock ชั้นเครือข่าย + approve + tool runner ให้ agent loop ทำงานแบบไม่แตะของจริง"""

    def __init__(self, responses, approve_ok=True, tool_result="OK: ทำแล้ว"):
        self.responses = list(responses)
        self.requests = []          # (url, payload)
        self.approve_calls = []
        self.tool_calls = []
        self.approve_ok = approve_ok
        self.tool_result = tool_result

    def post(self, url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        self.requests.append({"url": url, "payload": payload, "headers": headers,
                              "tag": tag, "retries": retries})
        r = self.responses.pop(0) if self.responses else Resp(payload=oai("จบแล้ว"))
        return r

    def approve(self, name, desc, fargs, auto_yes):
        self.approve_calls.append((name, fargs))
        return self.approve_ok if callable(self.approve_ok) is False else self.approve_ok

    def tool(self, name, fargs):
        self.tool_calls.append((name, fargs))
        return self.tool_result if callable(self.tool_result) is False else self.tool_result


def with_fixture(fx, fn, failover_free=None, failover_provider=None, keys=None):
    orig = (S._post_chat, S.approve, S.run_tool, S.load_keys, S.console,
            S._failover_free, S._failover_provider)
    S._post_chat = fx.post
    S.approve = fx.approve
    S.run_tool = fx.tool
    S.load_keys = lambda: dict(keys or {})
    S.console = Console(file=io.StringIO(), width=200, force_terminal=False)
    S._failover_free = failover_free or (lambda p, m, st, bd, sw, max_switches=2: "")
    S._failover_provider = failover_provider or (lambda p, m: ("", ""))
    try:
        return fn()
    finally:
        (S._post_chat, S.approve, S.run_tool, S.load_keys, S.console,
         S._failover_free, S._failover_provider) = orig


# ---------------------------------------------------------------- OpenAI-compatible
def t_openai_runs_tools():
    fx = Fixture([Resp(payload=oai("", [("read_file", {"path": "a.txt"}),
                                      ("list_dir", {"path": "."})])),
                  Resp(payload=oai("เสร็จแล้ว"))])

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "ดูไฟล์"}],
                              0.2, auto_yes=True, max_steps=5)

    out, err, used, info = with_fixture(fx, run)
    check("oai: tool 2 ตัวถูกรัน", used == 2 and len(fx.tool_calls) == 2, (used, fx.tool_calls))
    check("oai: คำตอบรวมถูกต้อง", out == "เสร็จแล้ว" and err == "", (out, err))
    msgs = fx.requests[1]["payload"]["messages"]
    check("oai: assistant มี tool_calls 2 อัน",
          any(m.get("role") == "assistant" and len(m.get("tool_calls") or []) == 2 for m in msgs))
    check("oai: มี tool role ตอบกลับ 2 อัน",
          sum(1 for m in msgs if m.get("role") == "tool") == 2)
    check("oai: info.cap", info.get("cap") == 5, info)
    check("oai: ใช้ tag agent-openai", fx.requests[0]["tag"] == "agent-openai")
    check("oai: retries=4", fx.requests[0]["retries"] == 4, fx.requests[0]["retries"])
    check("oai: ไม่มี Authorization เมื่อไม่มี key",
          "Authorization" not in fx.requests[0]["headers"])
    check("oai: tool_calls หายไปแล้วในขั้นที่โมเดลตอบจบ",
          info["steps"] == 2, info)


def t_openai_denied():
    fx = Fixture([Resp(payload=oai("", [("write_file", {"path": "x.txt", "content": "hi"})])),
                  Resp(payload=oai("ไม่ทำก็ได้"))])
    fx.approve_ok = False

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "เขียนไฟล์"}],
                              0.2, auto_yes=False, max_steps=5)

    out, err, used, info = with_fixture(fx, run)
    check("oai: ปฏิเสธ = ไม่รัน tool", used == 0 and not fx.tool_calls, fx.tool_calls)
    check("oai: ยังตอบกลับได้", out == "ไม่ทำก็ได้")
    check("oai: log ว่า denied", info["tools"][0][1] == "denied", info["tools"])
    msgs = fx.requests[1]["payload"]["messages"]
    check("oai: ส่งสารปฏิเสธกลับเป็น tool result",
          any(m.get("role") == "tool" and "ปฏิเสธ" in str(m.get("content")) for m in msgs))


def t_openai_unknown_tool_bails():
    calls = [("no_such_tool", {"a": 1})] * 2
    fx = Fixture([Resp(payload=oai("", [calls[0]])),
                  Resp(payload=oai("", [calls[1]]))])
    fx.tool_result = "ERROR: ไม่รู้จัก tool no_such_tool (ที่มีให้ใช้: ...)"

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "x"}],
                              0.2, auto_yes=True, max_steps=5)

    out, err, used, info = with_fixture(fx, run)
    check("oai: tool ไม่รู้จักซ้ำ 2 ครั้ง = เลิก",
          err.startswith("เลิกแล้ว") and len(fx.requests) == 2, (err, len(fx.requests)))
    check("oai: นับ tool ที่รันไว้", used == 2, used)


def t_openai_transient_model_switch():
    fx = Fixture([Resp(429, text='{"error":"rate limit"}'), Resp(payload=oai("ต่อได้"))])
    seen = []

    def ff(provider, model, status, body, switches, max_switches=2):
        seen.append((provider, model, status))
        return "m2" if switches == 0 else ""

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "hi"}],
                              0.2, max_steps=5)

    out, err, used, info = with_fixture(fx, run, failover_free=ff)
    check("oai: 429 → สลับโมเดลค่ายเดิม", seen == [("openrouter", "m1", 429)], seen)
    check("oai: ยิงซ้ำด้วยโมเดลใหม่", fx.requests[1]["payload"]["model"] == "m2",
          fx.requests[1]["payload"]["model"])
    check("oai: จบงานได้หลังสลับ", out == "ต่อได้" and err == "", (out, err))


def t_openai_quota_switches_provider():
    fx = Fixture([Resp(402, text='{"error":"depleted credits"}'),
                  Resp(payload=oai("ค่ายใหม่ตอบ"))])
    switched = []

    def fp(provider, model):
        return "groq", "llama-3.3-70b-versatile"

    def ap(np_, nm, reason):
        switched.append((np_, nm))

    orig_ap = S._apply_provider_switch
    S._apply_provider_switch = ap
    try:
        def run():
            return S._agent_steps("huggingface", "Qwen/Qwen3-32B",
                                  [{"role": "user", "content": "hi"}], 0.2, max_steps=5)
        out, err, used, info = with_fixture(fx, run, failover_provider=fp)
    finally:
        S._apply_provider_switch = orig_ap
    check("oai: 402 → สลับค่าย", switched == [("groq", "llama-3.3-70b-versatile")], switched)
    check("oai: ใช้ URL ค่ายใหม่", "groq.com" in fx.requests[1]["url"], fx.requests[1]["url"])
    check("oai: ใช้โมเดลค่ายใหม่",
          fx.requests[1]["payload"]["model"] == "llama-3.3-70b-versatile")
    check("oai: จบงานได้ที่ค่ายใหม่", out == "ค่ายใหม่ตอบ" and err == "", (out, err))


def t_openai_error_no_failover():
    fx = Fixture([Resp(500, text='{"error":{"message":"boom"}}')])

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "hi"}],
                              0.2, max_steps=5)

    out, err, used, info = with_fixture(fx, run)
    check("oai: error อื่นคืนข้อความไทย",
          err.startswith("ERROR: ") and "boom" in err, err)
    check("oai: ไม่รัน tool", used == 0 and not fx.tool_calls)


def t_openai_tools_unsupported_404():
    fx = Fixture([Resp(404, text=NO_TOOLS_MSG), Resp(payload=oai("ตอบแบบข้อความ"))])

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "hi"}],
                              0.2, max_steps=5)

    out, err, used, info = with_fixture(fx, run)
    check("oai: 404 tools → ยิงใหม่ (2 คำขอ)", len(fx.requests) == 2, len(fx.requests))
    second = fx.requests[1]["payload"]
    check("oai: คำขอที่สองไม่มี tools/tool_choice/provider",
          "tools" not in second and "tool_choice" not in second and "provider" not in second,
          sorted(second))
    check("oai: คำขอที่สองใช้ retries ปกติ (2)", fx.requests[1]["retries"] == 2,
          fx.requests[1]["retries"])
    check("oai: ได้คำตอบหลัง fallback", out == "ตอบแบบข้อความ" and err == "", (out, err))


def t_openai_text_fallback():
    fx = Fixture([Resp(payload=oai('```tool {"name": "list_dir", "arguments": {"path": "."}} ```')),
                  Resp(payload=oai("เรียบร้อย"))])

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "ดูไฟล์"}],
                              0.2, auto_yes=True, max_steps=3)

    out, err, used, info = with_fixture(fx, run)
    check("oai: text call ถูกรัน", used == 1 and fx.tool_calls[0][0] == "list_dir", fx.tool_calls)
    msgs = fx.requests[1]["payload"]["messages"]
    check("oai: ไม่มี tool_calls ปลอม",
          not any(m.get("role") == "assistant" and m.get("tool_calls") for m in msgs))
    check("oai: ไม่มี tool role ที่ id ปลอม",
          not any(m.get("role") == "tool" for m in msgs))
    check("oai: ผลส่งกลับเป็นข้อความ user",
          any(m.get("role") == "user" and "ผลจากการเรียก tool" in str(m.get("content"))
              for m in msgs))


def t_openai_cap_and_on_text():
    fx = Fixture([Resp(payload=oai("ก", [("list_dir", {"path": "."})])) for _ in range(3)])
    fx.tool_result = "OK: 3 ไฟล์"
    seen_text = []

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "ลูป"}],
                              0.2, auto_yes=True, max_steps=3, on_text=seen_text.append)

    out, err, used, info = with_fixture(fx, run)
    check("oai: ชนเพดาน = exhausted", info["exhausted"] is True and info["steps"] == 3, info)
    check("oai: info.cap", info["cap"] == 3, info)
    check("oai: on_text ถูกเรียกทุกครั้ง", seen_text == ["ก", "ก", "ก"], seen_text)
    check("oai: ข้อความรวมครบ", out == "กกก", out)
    check("oai: สรุปบอกว่ายังไม่จบ",
          "เพดาน" in S.format_agent_done(used, info["tools"], info["exhausted"], info["cap"]))


def t_openai_force_first_tool_choice():
    fx = Fixture([Resp(payload=oai("จบ"))])

    def run():
        return S._agent_steps("mistral", "m1", [{"role": "user", "content": "hi"}],
                              0.2, max_steps=2, force_first=True)

    with_fixture(fx, run)
    check("oai: force_first ส่ง tool_choice=required",
          fx.requests[0]["payload"]["tool_choice"] == "required")
    check("oai: ไม่ใช่ openrouter = ไม่ส่ง provider param",
          "provider" not in fx.requests[0]["payload"])


def t_openai_anthropic_guard():
    def run():
        return S._agent_steps("anthropic", "claude-x", [{"role": "user", "content": "hi"}], 0.2)

    out, err, used, info = with_fixture(Fixture([]), run)
    check("oai: ค่าย anthropic ถูกกันไว้ที่ _agent_steps",
          used == 0 and "ยังไม่รองรับ" in err, err)
    check("oai: guard คืน 4 ค่า", isinstance(info, dict) and info.get("steps") == 0, info)


# ---------------------------------------------------------------------- Anthropic
def t_anthropic_runs_tools():
    fx = Fixture([Resp(payload=anth([{"type": "text", "text": "กำลังดู"},
                                     {"type": "tool_use", "id": "tu_1", "name": "read_file",
                                      "input": {"path": "a.txt"}}])),
                  Resp(payload=anth([{"type": "text", "text": "เสร็จแล้ว"}]))])

    def run():
        return S._agent_steps_anthropic("claude-sonnet-4-5",
                                        [{"role": "system", "content": "sys"},
                                         {"role": "user", "content": "ดูไฟล์"}],
                                        0.2, auto_yes=True, max_steps=5)

    out, err, used, info = with_fixture(fx, run)
    check("anth: รัน tool", used == 1 and fx.tool_calls == [("read_file", {"path": "a.txt"})],
          fx.tool_calls)
    check("anth: รวมข้อความ text", out == "กำลังดูเสร็จแล้ว" and err == "", (out, err))
    body = fx.requests[0]["payload"]
    check("anth: ยิงไป /v1/messages", "api.anthropic.com/v1/messages" in fx.requests[0]["url"])
    check("anth: tag agent-anthropic", fx.requests[0]["tag"] == "agent-anthropic")
    check("anth: system แยกออกจาก messages",
          body.get("system") == "sys" and all(m["role"] != "system" for m in body["messages"]),
          body.get("system"))
    check("anth: tool_choice auto", body["tool_choice"] == {"type": "auto"})
    check("anth: headers ใช้ x-api-key",
          "x-api-key" in fx.requests[0]["headers"] and "Authorization" not in fx.requests[0]["headers"])
    second = fx.requests[1]["payload"]["messages"]
    check("anth: assistant ส่ง tool_use block",
          any(m["role"] == "assistant" and any(b.get("type") == "tool_use"
                                               for b in (m["content"] if isinstance(m["content"], list) else []))
              for m in second))
    check("anth: tool result ส่งเป็น user/tool_result",
          any(m["role"] == "user" and any(b.get("type") == "tool_result"
                                          for b in (m["content"] if isinstance(m["content"], list) else []))
              for m in second))


def t_anthropic_force_first_and_denied():
    fx = Fixture([Resp(payload=anth([{"type": "tool_use", "id": "tu_1", "name": "write_file",
                                      "input": {"path": "x.txt", "content": "hi"}}])),
                  Resp(payload=anth([{"type": "text", "text": "ok"}]))])
    fx.approve_ok = False

    def run():
        return S._agent_steps_anthropic("claude-haiku-4-5",
                                        [{"role": "user", "content": "เขียนไฟล์"}],
                                        0.2, auto_yes=False, max_steps=5, force_first=True)

    out, err, used, info = with_fixture(fx, run)
    check("anth: force_first ส่ง tool_choice any",
          fx.requests[0]["payload"]["tool_choice"] == {"type": "any"})
    check("anth: ปฏิเสธ = ไม่รัน", used == 0 and not fx.tool_calls)
    check("anth: log denied", info["tools"][0][1] == "denied", info["tools"])


def t_anthropic_model_switch_and_error():
    fx = Fixture([Resp(429, text='{"error":{"message":"rate limit"}}'),
                  Resp(400, text='{"error":{"message":"bad model"}}')])
    seen = []

    def ff(provider, model, status, body, switches, max_switches=2):
        seen.append((provider, model, status))
        return "claude-haiku-4-5" if switches == 0 else ""

    def run():
        return S._agent_steps_anthropic("claude-sonnet-4-5", [{"role": "user", "content": "hi"}],
                                        0.2, max_steps=5)

    out, err, used, info = with_fixture(fx, run, failover_free=ff)
    check("anth: 429 → สลับโมเดล", seen and seen[0] == ("anthropic", "claude-sonnet-4-5", 429), seen)
    check("anth: คำขอที่สองใช้โมเดลใหม่",
          fx.requests[1]["payload"]["model"] == "claude-haiku-4-5")
    check("anth: error สุดท้ายเป็นข้อความไทย", err.startswith("ERROR: "), err)


def t_anthropic_cap():
    fx = Fixture([Resp(payload=anth([{"type": "tool_use", "id": "t", "name": "list_dir",
                                      "input": {"path": "."}}])) for _ in range(2)])

    def run():
        return S._agent_steps_anthropic("claude-x", [{"role": "user", "content": "ลูป"}],
                                        0.2, auto_yes=True, max_steps=2)

    out, err, used, info = with_fixture(fx, run)
    check("anth: ชนเพดาน = exhausted", info["exhausted"] is True and info["steps"] == 2, info)
    check("anth: info.cap", info["cap"] == 2, info)


def t_anthropic_text_fallback():
    fx = Fixture([Resp(payload=anth([{"type": "text",
                                      "text": '```tool {"name": "list_dir", "arguments": {"path": "."}} ```'}])),
                  Resp(payload=anth([{"type": "text", "text": "เรียบร้อย"}]))])

    def run():
        return S._agent_steps_anthropic("claude-x", [{"role": "user", "content": "ดูไฟล์"}],
                                        0.2, auto_yes=True, max_steps=3)

    out, err, used, info = with_fixture(fx, run)
    check("anth: text call ถูกรัน", used == 1 and fx.tool_calls[0][0] == "list_dir", fx.tool_calls)
    second = fx.requests[1]["payload"]["messages"]
    check("anth: ไม่มี tool_use ปลอมจากข้อความ",
          not any(b.get("type") == "tool_use"
                  for m in second if isinstance(m.get("content"), list)
                  for b in m["content"]))
    check("anth: ผลส่งกลับเป็นข้อความ user",
          any(m["role"] == "user" and "ผลจากการเรียก tool" in str(m.get("content"))
              for m in second))


def t_mcp_cache_invalidated_on_write():
    fx = Fixture([Resp(payload=oai("", [("mcp__fs__read_text_file", {"path": "a.txt"})])),
                  Resp(payload=oai("", [("write_file", {"path": "a.txt", "content": "v2"})])),
                  Resp(payload=oai("", [("mcp__fs__read_text_file", {"path": "a.txt"})])),
                  Resp(payload=oai("จบ"))])
    reads = []

    def tool(name, fargs):
        if name.startswith("mcp__"):
            reads.append(name)
            return "เนื้อหา v1" if len(reads) == 1 else "เนื้อหา v2"
        return "OK: เขียนแล้ว"

    fx.tool = tool

    def run():
        return S._agent_steps("openrouter", "m1", [{"role": "user", "content": "x"}],
                              0.2, auto_yes=True, max_steps=6)

    out, err, used, info = with_fixture(fx, run)
    check("mcp: อ่านซ้ำหลังเขียนต้องเรียกใหม่ (ไม่คืนของเก่าค้าง)",
          reads == ["mcp__fs__read_text_file", "mcp__fs__read_text_file"], reads)
    check("mcp: จบงานได้", out == "จบ" and err == "", (out, err))


def t_project_hooks_wrap_tool_execution():
    fx = Fixture([Resp(payload=oai("", [("read_file", {"path": "a.txt"})])),
                  Resp(payload=oai("done"))])
    hooks = []
    original_hook = S._run_project_hook
    S._run_project_hook = lambda event, tool: (hooks.append((event, tool)), (True, ""))[1]
    try:
        out, err, used, info = with_fixture(fx, lambda: S._agent_steps(
            "openrouter", "m1", [{"role": "user", "content": "read"}],
            0.2, auto_yes=True, max_steps=3))
    finally:
        S._run_project_hook = original_hook
    check("hooks: before/after wrap tool execution",
          hooks == [("before_tool", "read_file"), ("after_tool", "read_file")], hooks)
    check("hooks: agent tool still completes", out == "done" and err == "" and used == 1,
          (out, err, used))


def t_concurrent_same_model_switch():
    import threading
    import tempfile as _tf
    import os as _os
    tmp_h = _os.path.join(_tf.gettempdir(),
                          f"soonai-health-conc-{_os.getpid()}.json")
    try:
        _os.remove(tmp_h)
    except Exception:
        pass
    _old = (S.get_models, S.load_keys, S._post_chat, S.approve, S.run_tool,
            S.console, dict(S._MODEL_DEAD), dict(S._QUOTA_DEAD),
            S.LAST_MODEL_SWITCH, _os.environ.get("SOONAI_HEALTH_FILE"))
    _os.environ["SOONAI_HEALTH_FILE"] = tmp_h
    S.get_models = lambda pid, refresh=False: (["m1:free", "m2:free", "m3:free"], {})
    S.load_keys = lambda: {}
    S._MODEL_DEAD.clear()
    S._QUOTA_DEAD.clear()
    S.LAST_MODEL_SWITCH = None
    _local = threading.local()

    def post(url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        n = getattr(_local, "n", 0) + 1
        _local.n = n
        if n == 1:
            return Resp(429, text='{"error":"rate limit"}')
        return Resp(payload=oai("done"))

    S._post_chat = post
    S.approve = lambda name, desc, fargs, auto_yes: True
    S.run_tool = lambda name, fargs: "OK"
    S.console = Console(file=io.StringIO(), width=200)
    results = [None, None]

    def work(i):
        try:
            out, err, used, info = S._agent_steps(
                "openrouter", "m0:free", [{"role": "user", "content": "hi"}],
                0.2, auto_yes=True, max_steps=5)
            results[i] = (out, err, (info or {}).get("model_switch"))
        except Exception as e:  # noqa: BLE001
            results[i] = ("", f"RAISED: {e}", None)

    try:
        threads = [threading.Thread(target=work, args=(i,)) for i in (0, 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        for t in threads:
            check("conc: เธรดจบไม่ค้าง", not t.is_alive())
        ok = all(r and r[0] == "done" and r[1] == "" for r in results), results
        check("conc: ทั้งสองจบงานได้", ok[0], ok[1])
        tos = sorted(r[2]["to"] for r in results if r and r[2])
        check("conc: switch คนละตัว (ไม่หยิบของกัน)",
              len(tos) == 2 and tos[0] != tos[1], tos)
    finally:
        (S.get_models, S.load_keys, S._post_chat, S.approve, S.run_tool,
         S.console, _md, _qd, _lm, _env) = _old
        S._MODEL_DEAD.clear()
        S._MODEL_DEAD.update(_md)
        S._QUOTA_DEAD.clear()
        S._QUOTA_DEAD.update(_qd)
        S.LAST_MODEL_SWITCH = _lm
        if _env is None:
            _os.environ.pop("SOONAI_HEALTH_FILE", None)
        else:
            _os.environ["SOONAI_HEALTH_FILE"] = _env
        try:
            _os.remove(tmp_h)
        except Exception:
            pass


def t_agent_chat_keeps_switch():
    import time as _t
    orig = (S._agent_steps, S.console)
    calls = {"n": 0}

    def fake_steps(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("", "", 0, {"steps": 1, "exhausted": False, "tools": [],
                                "cap": 5,
                                "model_switch": {"provider": "openrouter", "from": "a",
                                                 "to": "b", "ts": _t.time()}})
        return ("done", "", 0, {"steps": 1, "exhausted": False, "tools": [],
                                "cap": 5})

    S._agent_steps = fake_steps
    S.console = Console(file=io.StringIO(), width=200)
    try:
        out, err, used, info = S.agent_chat(
            "openrouter", "a", [{"role": "system", "content": "T"},
                                {"role": "user", "content": "hi"}],
            0.2, auto_yes=True, max_steps=5, expect_tools=True)
    finally:
        S._agent_steps, S.console = orig
    check("chat: attempt 2 ไม่ทิ้ง switch ของรอบแรก",
          (info or {}).get("model_switch", {}).get("to") == "b", info)
    check("chat: จบงานได้", out == "done" and err == "", (out, err))


def t_shared_helpers():
    sys_text, msgs = S._to_anthropic_messages(
        [{"role": "system", "content": "a"},
         {"role": "user", "content": "u1"},
         {"role": "user", "content": "u2"},
         {"role": "assistant", "content": "a1"},
         {"role": "tool", "tool_call_id": "c1", "content": "res"}])
    check("helper: system รวมกัน", sys_text == "a")
    check("helper: role ซ้ำถูกยุบ", len(msgs) == 3, msgs)
    check("helper: role ซ้ำถูกยุบเป็น user เดียว",
          msgs[0]["role"] == "user" and len(msgs[0]["content"]) == 2, msgs[0])
    check("helper: tool → user/tool_result",
          msgs[2]["role"] == "user" and msgs[2]["content"][0]["type"] == "tool_result", msgs[2])
    tools = S._anthropic_tools()
    check("helper: แปลง tool defs", all("input_schema" in t and "name" in t for t in tools[:3]))


for fn in (t_openai_runs_tools, t_openai_denied, t_openai_unknown_tool_bails,
           t_openai_transient_model_switch, t_openai_quota_switches_provider,
           t_openai_error_no_failover, t_openai_tools_unsupported_404,
           t_openai_text_fallback, t_openai_cap_and_on_text,
           t_openai_force_first_tool_choice, t_openai_anthropic_guard,
           t_anthropic_runs_tools, t_anthropic_force_first_and_denied,
           t_anthropic_model_switch_and_error, t_anthropic_cap,
           t_anthropic_text_fallback, t_shared_helpers,
           t_mcp_cache_invalidated_on_write, t_project_hooks_wrap_tool_execution,
           t_concurrent_same_model_switch,
           t_agent_chat_keeps_switch):
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
print("ALL AGENT LOOP TESTS PASSED")
