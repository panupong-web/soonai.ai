# -*- coding: utf-8 -*-
"""Golden test (characterization) — ล็อกพื้นผิว CLI ให้คงที่ระหว่าง refactor

เทียบ 3 อย่างกับ snapshot ใน golden/:
  1) `soonai --help`  (เรียกริงผ่าน subprocess, COLUMNS=80 → deterministic)
  2) `soonai --version`
  3) agent turn หนึ่งรอบ (mock เครือข่าย/tool/approve) — payload ที่ส่ง, tool ที่รัน,
     ข้อความที่พิมพ์, out/err, สรุปจบงาน

อัปเดต snapshot เมื่อเจตนาเปลี่ยน:  SOONAI_UPDATE_GOLDEN=1 python test_golden.py
ไม่มีเน็ต/ไม่มี key
"""
import difflib
import io
import json
import os
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent
GOLDEN = ROOT / "golden"
HELP_F = GOLDEN / "help.txt"
VER_F = GOLDEN / "version.txt"
AGENT_F = GOLDEN / "agent_turn.json"
UPDATE = os.environ.get("SOONAI_UPDATE_GOLDEN", "").strip().lower() in ("1", "true", "yes", "on")

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


def _cli_env():
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1",
                "COLUMNS": "80", "SOONAI_NO_BANNER": "1", "SOONAI_NO_SYMBOL_MAP": "1"})
    env.pop("SOONAI_ANIM", None)
    return env


def run_cli(*args):
    """เรียกริง CLI แล้วคืน (stdout รวม, exit code) แบบ normalize บางส่วน"""
    p = subprocess.run([sys.executable, str(ROOT / "soonai.py"), *args],
                       cwd=str(ROOT), env=_cli_env(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", input="")
    out = (p.stdout or "") + (p.stderr or "")
    return out.replace("\r\n", "\n").rstrip() + "\n", p.returncode


def _compare(name, golden_path, actual_text):
    """เทียบกับไฟล์ golden (UPDATE=เขียนทับ)"""
    actual_text = actual_text.replace("\r\n", "\n")
    if UPDATE:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual_text, encoding="utf-8")
        check(f"{name}: อัปเดต golden", True)
        return
    if not golden_path.is_file():
        check(f"{name}: มีไฟล์ golden", False, f"ไม่พบ {golden_path} — รันด้วย SOONAI_UPDATE_GOLDEN=1")
        return
    want = golden_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if want == actual_text:
        check(f"{name}: ตรงกับ golden", True)
        return
    diff = "".join(list(difflib.unified_diff(
        want.splitlines(keepends=True), actual_text.splitlines(keepends=True),
        fromfile="golden", tofile="actual", n=2))[:40])
    check(f"{name}: ตรงกับ golden", False, "\n" + diff)


# ---------------------------------------------------------------- 1) help
help_out, help_rc = run_cli("--help")
check("help: exit 0", help_rc == 0, help_rc)
_check_help = "usage: soonai" in help_out and "--agent" in help_out
check("help: มีหัว usage + option หลัก", _check_help)
_compare("help", HELP_F, help_out)

# ---------------------------------------------------------------- 2) version
ver_out, ver_rc = run_cli("--version")
check("version: exit 0", ver_rc == 0, ver_rc)
_compare("version", VER_F, ver_out)

# ---------------------------------------------------------------- 3) agent turn
def _agent_snapshot():
    import soonai as S
    from rich.console import Console

    class Resp:
        def __init__(self, status=200, payload=None):
            self.status_code = status
            self._p = payload or {}
            self.text = json.dumps(self._p)

        def json(self):
            return json.loads(self.text)

        def close(self):
            pass

    def oai(content="", tool_calls=None, finish="stop"):
        msg = {"content": content}
        if tool_calls:
            msg["tool_calls"] = [{"id": f"call_{i}", "type": "function",
                                  "function": {"name": n, "arguments": json.dumps(a)}}
                                 for i, (n, a) in enumerate(tool_calls)]
        return {"choices": [{"message": msg, "finish_reason": finish}]}

    workdir = tempfile.mkdtemp(prefix="soonai-golden-")
    os.chdir(workdir)
    responses = [
        Resp(payload=oai("", [("write_file", {"path": "hello.txt", "content": "hi"})])),
        Resp(payload=oai("เขียนไฟล์เสร็จแล้ว")),
    ]
    requests, tool_calls, approve_calls = [], [], []
    buf = io.StringIO()

    def post(url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=2):
        requests.append({"model": (payload or {}).get("model"),
                         "temperature": (payload or {}).get("temperature"),
                         "tools": [t.get("function", {}).get("name")
                                   for t in ((payload or {}).get("tools") or [])],
                         "messages": (payload or {}).get("messages")})
        return responses.pop(0) if responses else Resp(payload=oai("จบแล้ว"))

    orig = (S._post_chat, S.approve, S.run_tool, S.load_keys, S.load_config, S.console,
            S.Prompt, S._attach_symbol_map, S._attach_project_memory, S.project_snapshot,
            S.carryover_skills, S.autosuggest_skill, S.workspace_root)
    S._post_chat = post
    S.approve = lambda name, desc, fargs, auto_yes: (approve_calls.append(name) or True)
    S.run_tool = lambda name, fargs: (tool_calls.append((name, fargs)) or "OK: เขียนแล้ว")
    S.load_keys = lambda: {"openrouter": "k"}
    S.load_config = lambda: {"agent": {"auto_skill": False}}
    S.console = Console(file=buf, width=100, force_terminal=False)
    S.Prompt = type("P", (), {"ask": staticmethod(lambda *a, **k: "n")})
    S._attach_symbol_map = lambda m, **k: m
    S._attach_project_memory = lambda m: m
    S.project_snapshot = lambda *a, **k: ""
    S.carryover_skills = lambda auto_yes=False: []
    S.autosuggest_skill = lambda task, auto_yes=False: []
    S.workspace_root = lambda: Path(workdir)
    try:
        out, err, used, info = S.agent_chat(
            "openrouter", "m-golden",
            [{"role": "system", "content": "GOLDEN-SYS"},
             {"role": "user", "content": "สร้างไฟล์ hello.txt"}],
            0.2, auto_yes=True, max_steps=3)
    finally:
        (S._post_chat, S.approve, S.run_tool, S.load_keys, S.load_config, S.console,
         S.Prompt, S._attach_symbol_map, S._attach_project_memory, S.project_snapshot,
         S.carryover_skills, S.autosuggest_skill, S.workspace_root) = orig
        os.chdir(str(ROOT))

    def norm(t):
        s = str(t if t is not None else "")
        for w in (workdir, workdir.replace("\\", "/")):
            s = s.replace(w, "<WORKDIR>")
        return s.replace("\r\n", "\n")

    snap = {
        "requests": len(requests),
        "request_payloads": [
            {"model": r["model"], "temperature": r["temperature"], "tools": r["tools"],
             "messages": [{"role": m.get("role"), "content": norm(m.get("content"))}
                          for m in (r["messages"] or [])]}
            for r in requests],
        "tool_calls": [[n, norm(json.dumps(a, sort_keys=True, ensure_ascii=False))]
                       for n, a in tool_calls],
        "approve_calls": approve_calls,
        "used": used,
        "info": info,
        "out": norm(out),
        "err": norm(err),
        "console": norm(buf.getvalue()),
    }
    os.chdir(str(ROOT))
    return json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


snap_text = _agent_snapshot()
try:
    _snap_obj = json.loads(snap_text)
    check("agent: มีคำขอ 2 รอบ", _snap_obj.get("requests") == 2, _snap_obj.get("requests"))
    check("agent: รัน write_file", [c[0] for c in _snap_obj.get("tool_calls", [])] == ["write_file"],
          _snap_obj.get("tool_calls"))
    check("agent: คำตอบสุดท้ายถูกต้อง", _snap_obj.get("out") == "เขียนไฟล์เสร็จแล้ว", _snap_obj.get("out"))
except Exception as e:
    check("agent: snapshot parse ได้", False, e)

_compare("agent turn", AGENT_F, snap_text)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL GOLDEN TESTS PASSED")
