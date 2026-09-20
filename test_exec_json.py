# -*- coding: utf-8 -*-
"""Regression: soonai exec (headless สำหรับสคริปต์/CI)
- --json: stdout มี JSON ก้อนเดียว (log ไป stderr) · exit code ตามผลงาน
- 0 = สำเร็จ (ok:true) · 1 = ผิดพลาด (ok:false + error) · JSON มี tools/usage/steps
- parser ต่อ subcommand exec ถูกต้อง
ไม่แตะเน็ต/ไม่ใช้ key จริง: mock _post_chat + approve + run_tool + resolve_model
"""
import argparse
import contextlib
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

    def json(self):
        try:
            return json.loads(self.text)
        except Exception:
            return self._payload

    def close(self):
        pass


def oai(content="", tool_calls=None, finish="stop"):
    msg = {"content": content}
    if tool_calls:
        msg["tool_calls"] = [{"id": f"call_{i}", "type": "function",
                              "function": {"name": n, "arguments": json.dumps(a)}}
                             for i, (n, a) in enumerate(tool_calls)]
    return {"choices": [{"message": msg, "finish_reason": finish}]}


def exec_args(task, json_mode=True, yes=True, max_steps=6):
    return argparse.Namespace(task=task, json=json_mode, provider="ollama", model="m-test",
                              temperature=0.2, free_only=False, search="", yes=yes,
                              max_steps=max_steps)


def run_exec(responses, args, approve_ok=True, tool_result="OK: เขียนไฟล์แล้ว"):
    """รัน cmd_exec แบบไม่แตะเน็ต คืน (exit code, stdout, stderr ที่ดักไว้)"""
    orig = (S._post_chat, S.approve, S.run_tool, S.load_config, S.load_keys, S.console,
            S.resolve_model, S.project_snapshot, S._attach_project_memory,
            S._failover_free, S._failover_provider)
    box = list(responses)
    logs = io.StringIO()

    def post(url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        return box.pop(0) if box else Resp(payload=oai("จบแล้ว"))

    S._post_chat = post
    S.approve = lambda name, desc, fargs, auto_yes: approve_ok
    S.run_tool = lambda name, fargs: tool_result
    S.load_config = lambda: {"provider": "ollama", "model": "m-test", "system": "คุณคือผู้ช่วย",
                             "agent": {"shell": "safe"}}
    S.load_keys = lambda: {}
    S.console = Console(file=logs, width=200, force_terminal=False)
    S.resolve_model = lambda provider, model, keys, **kw: model or "m-test"
    S.project_snapshot = lambda: ""
    S._attach_project_memory = lambda messages: None
    S._failover_free = lambda p, m, st, bd, sw, max_switches=2: ""
    S._failover_provider = lambda p, m: ("", "")
    out = io.StringIO()
    err = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = S.cmd_exec(args, {}, S.load_config())
    finally:
        (S._post_chat, S.approve, S.run_tool, S.load_config, S.load_keys, S.console,
         S.resolve_model, S.project_snapshot, S._attach_project_memory,
         S._failover_free, S._failover_provider) = orig
    return code, out.getvalue(), err.getvalue(), logs.getvalue()


# ---------------------------------------------------------------- 1) parser
ap = S.build_parser()
a = ap.parse_args(["exec", "รันเทสต์แล้วแก้ให้ผ่าน", "--json", "--max-steps", "3"])
check("parser: subcommand exec", a.cmd == "exec" and a.task == "รันเทสต์แล้วแก้ให้ผ่าน")
check("parser: --json/--max-steps", a.json is True and a.max_steps == 3)

# ---------------------------------------------------------------- 2) สำเร็จ
code, stdout, stderr, _logs = run_exec(
    [Resp(payload=oai("", [("run_tests", {"command": "python -m pytest -q"})])),
     Resp(payload=oai("แก้แล้วและเทสต์ผ่าน"))],
    exec_args("รันเทสต์แล้วแก้ให้ผ่าน"))
check("exec: exit code 0", code == 0, code)
lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
check("exec --json: stdout มีบรรทัดเดียว", len(lines) == 1, lines)
data = json.loads(lines[0]) if lines else {}
check("exec --json: ok = true", data.get("ok") is True, data)
check("exec --json: มีคำตอบ", data.get("answer") == "แก้แล้วและเทสต์ผ่าน", data.get("answer"))
check("exec --json: model/provider", data.get("model") == "m-test" and data.get("provider") == "ollama",
      data)
check("exec --json: มี tools ที่ใช้", any(t.get("name") == "run_tests" for t in data.get("tools") or []),
      data.get("tools"))
check("exec --json: steps >= 2", data.get("steps", 0) >= 2, data.get("steps"))
check("exec --json: usage มี in/out token", data["usage"]["in_tokens"] > 0
      and data["usage"]["out_tokens"] > 0, data.get("usage"))
check("exec --json: duration มีค่า", data.get("duration_s", 0) >= 0, data.get("duration_s"))
check("exec --json: error ว่าง", data.get("error") == "", data.get("error"))

# ---------------------------------------------------------------- 3) ผิดพลาด
code2, stdout2, _err2, logs2 = run_exec([Resp(status=500, text='{"error":"boom"}')],
                                       exec_args("ทำอะไรสักอย่าง"))
check("exec: error → exit 1", code2 == 1, code2)
d2 = json.loads(stdout2.strip().splitlines()[-1])
check("exec: ok = false", d2.get("ok") is False, d2)
check("exec: มีข้อความ error", bool(d2.get("error")), d2)
check("exec: error ภาษาไทย/มี HTTP",
      "HTTP" in d2["error"] or "boom" in d2["error"], d2.get("error"))

# ---------------------------------------------------------------- 4) ยังไม่มี key
_old_keys = S.load_keys
key_code, key_out, _k_err, _k_logs = run_exec([], exec_args("งาน"), )
check("exec: ollama ไม่ต้องใช้ key ก็ผ่าน", key_code == 0, key_code)

# ---------------------------------------------------------------- 5) โหมดไม่ใช่ json
code3, stdout3, _e3, logs3 = run_exec(
    [Resp(payload=oai("คำตอบแบบข้อความ"))], exec_args("ถามเฉย ๆ", json_mode=False))
check("exec (ไม่ json): exit 0", code3 == 0, code3)
check("exec (ไม่ json): คำตอบไป console ไม่ใช่ stdout JSON", stdout3.strip() == "", stdout3[:80])
check("exec (ไม่ json): มี log ที่ console", "คำตอบแบบข้อความ" in logs3, logs3[:200])

# ---------------------------------------------------------------- 6) ยกเลิกกลางทาง
def _cancel(*a, **k):
    raise S.TurnCancelled()


_orig_agent = S.agent_chat
S.agent_chat = _cancel
try:
    with contextlib.redirect_stdout(io.StringIO()):
        code4 = S.cmd_exec(exec_args("งาน"), {}, {"provider": "ollama", "model": "m-test"})
finally:
    S.agent_chat = _orig_agent
check("exec: ยกเลิก → exit 130", code4 == 130, code4)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL EXEC TESTS PASSED")
