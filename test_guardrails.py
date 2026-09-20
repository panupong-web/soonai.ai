# -*- coding: utf-8 -*-
"""Regression: guardrails ที่เพิ่มหลังรีวิว
- ไฟล์/โฟลเดอร์ secret ห้าม agent แตะ (รวม session/debug/crash/models cache)
- พาธต้องห้ามที่ซ่อนใน args โครงสร้างซ้อน (dict ใน list · ใช้เป็น key) ต้องถูกจับทุกระดับ
  แต่ข้อความ/โค้ด/คำค้นที่แค่ "พูดถึง" พาธ ต้องไม่ถูกบล็อก (เท็จบวก)
- อ่านในโฟลเดอร์งานผ่านทันที · อ่านนอกโฟลเดอร์ต้องยืนยัน
- keys เข้ารหัสตอนเก็บ (Windows DPAPI) + ถอดกลับได้
- เพดานก้าว agent มีค่าเริ่มต้น + ปรับได้ (--max-steps / SOONAI_MAX_STEPS)
- tool call ที่โมเดลเขียนเป็นข้อความ ต้องไม่ถูกยัดกลับเป็น tool_calls ปลอม
"""
import argparse
import json
import os
import sys
import tempfile
import threading
import time

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


def blk(tool, args):
    return bool(S._sensitive_deny(tool, args))


# 1) ไฟล์ secret เดิม + ที่เพิ่มใหม่ + โฟลเดอร์ต้องห้ามทั้งอัน
check("block keys.json (relative)", blk("read_file", {"path": "shared/keys.json"}))
check("block keys.json (case/sep)",
      blk("read_file", {"path": "SHARED" + os.sep + "KEYS.JSON"}))
check("block keys.json (dotdot)",
      blk("read_file", {"path": "shared/../shared/keys.json"}))
check("block config.json write",
      blk("write_file", {"path": "shared/config.json", "content": "x"}))
check("block team.json", blk("edit_file", {"path": "shared/team.json",
                                           "old_string": "a", "new_string": "b"}))
check("block crash.log", blk("read_file", {"path": "crash.log"}))
check("block debug_last.json", blk("read_file", {"path": "debug_last.json"}))
check("block session transcript",
      blk("read_file", {"path": str(S.SESSIONS_DIR / "20260101-000000.json")}))
check("block session transcript (grep)",
      blk("grep", {"pattern": "key", "path": str(S.SESSIONS_DIR)}))
check("block computer screenshot dir",
      blk("read_file", {"path": str(S.DATA_DIR / "computer" / "last.png")}))
check("block mcp secret via MCP tool",
      blk("mcp__fs__read_text_file", {"path": "shared/keys.json"}))
check("block secret via nested MCP arg",
      blk("mcp__fs__read_text_file", {"file": {"path": "shared/keys.json"}}))
check("block secret via paths list",
      blk("mcp__fs__read_multiple_files", {"paths": ["shared/keys.json"]}))
check("block secret via uri",
      blk("mcp__fs__read_text_file", {"uri": "file://" + str(S.KEYS_FILE)}))
check("block session dir via directory key",
      blk("mcp__fs__list_directory", {"directory": str(S.SESSIONS_DIR)}))
check("block keys.json write via paths list",
      blk("mcp__fs__edit_file", {"paths": ["shared/keys.json"]}))
for path in ("shared/permissions.py", "soonai.py", "sessions_note.txt"):
    check(f"allow normal read {path}", not blk("read_file", {"path": path}))

# 1c) พาธต้องห้ามที่ซ่อนในโครงสร้างซ้อน (dict ใน list · ซ้อนหลายชั้น · ใช้เป็น key)
#     ของเดิมดูแค่คีย์ที่รู้จัก + dict ซ้อนชั้นเดียว → เคสกลุ่มนี้หลุดทั้งหมด
check("block secret in list-of-dict (MCP write)",
      blk("mcp__fs__write_file", {"files": [{"path": "shared/keys.json"}]}))
check("block secret in list-of-dict (MCP read)",
      blk("mcp__fs__read_multiple_files", {"files": [{"path": "shared/keys.json"}]}))
check("block secret ซ้อน 3 ชั้น",
      blk("mcp__fs__edit_file",
          {"op": {"targets": [{"file": {"path": "shared/keys.json"}}]}}))
check("block secret in list-in-list",
      blk("mcp__fs__write_file", {"batch": [["shared/keys.json"]]}))
check("block secret ที่เป็น key ของ dict",
      blk("mcp__fs__write_many", {"files": {"shared/keys.json": "x"}}))
check("block session dir in list-of-dict",
      blk("mcp__fs__list_directory", {"dirs": [{"directory": str(S.SESSIONS_DIR)}]}))
check("block keys.json ผ่าน uri ใน list",
      blk("mcp__fs__read_file", {"uris": [{"uri": "file://" + str(S.KEYS_FILE)}]}))
check("block secret ในโครงซ้อนของ edit_file",
      blk("edit_file", {"path": "notes.md", "targets": [{"path": "shared/keys.json"}]}))
check("block secret ท้าย list ยาว (ไม่หลุดด้วยการอำพราง)",
      blk("mcp__fs__write_file",
          {"files": [{"path": f"dummy{i}.txt"} for i in range(4999)] +
                    [{"path": "shared/keys.json"}]}))
check("block พาธที่ซ่อนใน content แบบโครงสร้าง (ของเดิมจับได้ ต้องไม่หลุด)",
      blk("mcp__fs__write_many", {"content": {"path": "shared/keys.json"}}))
check("block พาธที่ซ่อนใน list ของ content",
      blk("mcp__fs__write_many", {"content": ["บรรทัดปกติ", "shared/keys.json"]}))
# เท็จบวก: สตริงที่ "พูดถึง" พาธ (เนื้อหา/คำค้น) ไม่ใช่การแตะพาธ → ต้องไม่บล็อก
check("allow content ที่พูดถึงพาธ",
      not blk("write_file", {"path": "docs/notes.md",
                             "content": "คีย์อยู่ที่ shared/keys.json ห้าม commit"}))
check("allow old_string/new_string ที่พูดถึงพาธ",
      not blk("edit_file", {"path": "docs/notes.md", "old_string": "shared/keys.json",
                            "new_string": "shared/keys.json.bak"}))
check("allow grep pattern ที่เป็นพาธ",
      not blk("grep", {"pattern": "shared/keys.json", "path": "."}))
check("allow คำค้นที่เป็นพาธ", not blk("mcp__x__search", {"query": "shared/keys.json"}))
# ความทนทาน: args ลึก/ใหญ่/ชนิดแปลก ต้องไม่พังและไม่ค้าง
_deep = _cur = {}
for _i in range(60):
    _cur["next"] = {}
    _cur = _cur["next"]
_cur["path"] = "shared/keys.json"
try:
    _deep_hit = S._sensitive_hit({"a": _deep})
    check("args ลึกเกินเพดาน: ไม่พัง (หยุดที่ _ARGS_SCAN_MAX_DEPTH)", _deep_hit == "",
          _deep_hit)
except Exception as _e:
    check("args ลึกเกินเพดาน: ไม่พัง (หยุดที่ _ARGS_SCAN_MAX_DEPTH)", False, _e)
for _weird in (None, 0, True, "shared/keys.json", [{"path": "shared/keys.json"}],
               {"n": None, "b": True, "i": 5}):
    try:
        S._sensitive_hit(_weird)
        check(f"sensitive_hit ไม่พังกับ {type(_weird).__name__}", True)
    except Exception as _e:
        check(f"sensitive_hit ไม่พังกับ {type(_weird).__name__}", False, _e)
_ts = time.perf_counter()
_blk_big = blk("mcp__x__write", {"files": [{"path": f"f{i}.txt"} for i in range(5000)]})
_elapsed = time.perf_counter() - _ts
check("args ใหญ่ 5k: ตรวจเร็วและไม่พัง", _blk_big is False and _elapsed < 2.0, _elapsed)

# 1b) เครื่องมือที่เดินอ่านไฟล์เอง (grep/glob) ต้องข้ามไฟล์ secret
check("path_is_sensitive keys.json", S._path_is_sensitive(S.KEYS_FILE))
check("path_is_sensitive session dir child",
      S._path_is_sensitive(os.path.join(str(S.SESSIONS_DIR), "x.json")))
check("path_is_sensitive normal file", not S._path_is_sensitive(os.path.join(os.getcwd(), "soonai.py")))
_grep = S.run_tool("grep", {"pattern": "sk-", "path": "."})
check("grep skips secret files", "keys.json" not in _grep, _grep[:200])
_glob = S.run_tool("glob", {"pattern": "**/*.json", "path": "."})
check("glob skips secret files", "keys.json" not in _glob and "team.json" not in _glob,
      _glob[:200])

# 2) shell: ตรวจชื่อไฟล์ secret แบบ relative ได้ (best-effort)
check("shell hit keys.json", S._sensitive_shell_hit("type shared/keys.json") == "keys.json")
check("shell hit copy keys.json",
      S._sensitive_shell_hit("copy shared\\keys.json %TEMP%\\k.txt") == "keys.json")
check("shell hit debug_last", S._sensitive_shell_hit("cat debug_last.json") == "debug_last.json")
check("shell miss config alone", S._sensitive_shell_hit("cat config.json") == "")
check("shell hit shared config",
      S._sensitive_shell_hit("cat shared/config.json") == "config.json")
check("shell miss harmless", S._sensitive_shell_hit("git status") == "")

# 3) อ่านในโฟลเดอร์งานผ่าน · นอกโฟลเดอร์ต้องยืนยัน (โหมด pipe = ปฏิเสธ)
check("outside_workspace('.') is inside", not S.outside_workspace("."))
check("outside_workspace('..') is outside", S.outside_workspace(".."))
check("approve allows read in workspace",
      S.approve("read_file", "อ่าน requirements.txt", {"path": "requirements.txt"}, True) is True)
if not sys.stdin.isatty():
    check("approve denies out-of-workspace read (pipe)",
          S.approve("read_file", "อ่านไฟล์นอกโฟลเดอร์",
                    {"path": "../secret-outside.txt"}, True) is False)
else:
    print("skip: out-of-workspace read check (interactive TTY)")

# 4) เพดานก้าว agent
orig_global = S.AGENT_MAX_STEPS
try:
    S.AGENT_MAX_STEPS = None
    os.environ.pop("SOONAI_MAX_STEPS", None)
    check("default step cap = 40", S._agent_step_cap(None) == S.DEFAULT_AGENT_STEPS)
    os.environ["SOONAI_MAX_STEPS"] = "7"
    check("env step cap = 7", S._agent_step_cap(None) == 7)
    os.environ["SOONAI_MAX_STEPS"] = "0"
    check("env 0 = unlimited", S._agent_step_cap(None) is None)
    os.environ["SOONAI_MAX_STEPS"] = "-3"
    check("env negative = unlimited", S._agent_step_cap(None) is None)
    os.environ.pop("SOONAI_MAX_STEPS", None)
    S.AGENT_MAX_STEPS = 3
    check("CLI flag wins over env", S._agent_step_cap(None) == 3)
    check("explicit arg wins over flag", S._agent_step_cap(9) == 9)
    check("explicit 0 = unlimited", S._agent_step_cap(0) is None)
    S.AGENT_MAX_STEPS = 0
    check("CLI 0 = unlimited", S._agent_step_cap(None) is None)
finally:
    S.AGENT_MAX_STEPS = orig_global
    os.environ.pop("SOONAI_MAX_STEPS", None)
check("summary warns on cap hit",
      "เพดาน" in S.format_agent_done(40, [("list_dir", "ok", "x")], True, 40))
check("summary plain when done",
      S.format_agent_done(2, [("write_file", "ok", "x")], False, 40).startswith("✅"))
_sum_denied = S.agent_summary_line({"tools": [("write_file", "denied", "x")],
                                    "exhausted": False, "cap": 40, "steps": 1},
                                   with_usage=False)
check("summary ไม่นับ denied เป็นรัน",
      "รัน 0 คำสั่ง" in _sum_denied and "ปฏิเสธ 1" in _sum_denied, _sum_denied)

# 4b) read_file clamp + consume ตรงค่าย + cmdsig ผูกเนื้อหา + redact + stdio
_big = S.run_tool("read_file", {"path": "soonai.py", "max_chars": 10 ** 9})
check("read_file clamp เพดาน 20000", len(_big) <= 20000 + 10, len(_big))
S.LAST_MODEL_SWITCH = {"provider": "openrouter", "from": "a", "to": "b"}
check("consume ค่ายไม่ตรงไม่ล้าง",
      S.consume_model_switch("groq") is None and S.LAST_MODEL_SWITCH is not None)
check("consume ค่ายตรงได้ของ + ล้าง",
      S.consume_model_switch("openrouter") == {"provider": "openrouter",
                                               "from": "a", "to": "b"}
      and S.LAST_MODEL_SWITCH is None)
_sig_a = S._cmd_sig("write_file", {"path": "x", "content": "a"})
check("cmdsig write เนื้อหาต่าง sig ต่าง",
      _sig_a != S._cmd_sig("write_file", {"path": "x", "content": "b"}))
check("cmdsig write เนื้อหาเดิม sig เดิม",
      _sig_a == S._cmd_sig("write_file", {"path": "x", "content": "a"}))
_desc = S.describe_call("run_cmd", {"command": "deploy --api-key sk-abcdefgh12345678"})
check("describe ซ่อน secret", "***" in _desc and "sk-abcdefgh" not in _desc, _desc)


class _BadIO:
    def write(self, s):
        raise OSError(22, "Invalid argument")

    def flush(self):
        raise OSError(22, "Invalid argument")


try:
    _w = S._TolerantStdIO(_BadIO())
    _w.write("x")
    _w.flush()
    check("stdio กลืนแค่ Errno 22", True)
except Exception as e:
    check("stdio กลืนแค่ Errno 22", False, e)


class _BadIO5:
    def write(self, s):
        raise OSError(5, "I/O error")

    def flush(self):
        raise OSError(5, "I/O error")


try:
    S._TolerantStdIO(_BadIO5()).flush()
    check("stdio ไม่กลืน error อื่น", False, "ควร raise")
except OSError:
    check("stdio ไม่กลืน error อื่น", True)

# 5) max_sessions ปรับได้
orig_cfg = S.load_config
try:
    S.load_config = lambda: {"max_sessions": 25}
    check("config max_sessions honored", S._max_sessions() == 25)
    S.load_config = lambda: {}
    check("max_sessions default", S._max_sessions() == S.MAX_SESSIONS)
finally:
    S.load_config = orig_cfg

# 6) keys เข้ารหัสตอนเก็บ (DPAPI บน Windows) + ถอดกลับได้
orig_keys_file = S.KEYS_FILE
tmpdir = tempfile.mkdtemp(prefix="soonai-keys-")
try:
    S.KEYS_FILE = os.path.join(tmpdir, "keys.json")
    S.save_keys({"openrouter": "sk-test-1234567890", "groq": ""})
    raw = json.loads(open(S.KEYS_FILE, encoding="utf-8").read())
    got = S.load_keys()
    check("keys round-trip", got.get("openrouter") == "sk-test-1234567890", got)
    check("empty key dropped", "groq" not in got)
    if os.name == "nt":
        check("keys encrypted at rest",
              str(raw.get("openrouter", "")).startswith(S._KEYS_ENC_PREFIX)
              and "sk-test" not in json.dumps(raw))
        check("wrong-user blob reads as empty",
              S._decode_key(S._KEYS_ENC_PREFIX + "bm90LWEtYmxvYg==") == "")
    else:
        print("skip: DPAPI checks (non-Windows)")
finally:
    S.KEYS_FILE = orig_keys_file

# 6b) รับ key ต้องซ่อนจอ (****) ไม่สะท้อนตัวอักษร
_orig_ask, _orig_stdin = S.Prompt.ask, sys.stdin


class _FakeTTY:
    def isatty(self):
        return True

    def readline(self):
        raise AssertionError("tty ต้องไม่ถูกอ่านตรง")


class _FakePipe:
    def isatty(self):
        return False

    def readline(self):
        return "  piped-key-123  \n"


try:
    sys.stdin = _FakePipe()
    check("pipe: อ่าน stdin ตัดช่องว่าง",
          S._ask_secret("key:") == "piped-key-123")
finally:
    sys.stdin = _orig_stdin

if os.name == "nt":
    import msvcrt as _ms_mod
    import io as _io_mod
    _orig_getwch, _orig_stdout, _orig_stdin4 = _ms_mod.getwch, sys.stdout, sys.stdin
    try:
        sys.stdin = _FakeTTY()
        _chars = iter(list("k-x") + ["\r"])
        _ms_mod.getwch = lambda: next(_chars)
        _buf = _io_mod.StringIO()
        sys.stdout = _buf
        _got = S._ask_secret("key:")
        _out = _buf.getvalue()
    finally:
        _ms_mod.getwch, sys.stdout, sys.stdin = _orig_getwch, _orig_stdout, _orig_stdin4
    check("tty: อ่านครบ", _got == "k-x", _got)
    check("tty: โชว์ * ทุกตัว ไม่หลุดตัวจริง",
          _out == "key: ***\x1b[1A\x1b[2K" and "k-x" not in _out, repr(_out))
    try:
        sys.stdin = _FakeTTY()
        _chars2 = iter(["a", "b", "\x08", "c", "\r"])
        _ms_mod.getwch = lambda: next(_chars2)
        _buf2 = _io_mod.StringIO()
        sys.stdout = _buf2
        _got2 = S._ask_secret("key:")
        _out2 = _buf2.getvalue()
    finally:
        _ms_mod.getwch, sys.stdout, sys.stdin = _orig_getwch, _orig_stdout, _orig_stdin4
    check("tty: backspace ลบได้", _got2 == "ac" and _out2.count("*") == 3
          and _out2.endswith("\x1b[1A\x1b[2K"),
          (_got2, repr(_out2)))
else:
    print("skip: ปุ่มกด msvcrt (non-Windows)")

_orig_save_keys, _orig_ask_secret, _orig_stdin2 = S.save_keys, S._ask_secret, sys.stdin
try:
    saved = {}
    sys.stdin = _FakeTTY()
    S.save_keys = lambda keys: saved.update(keys)
    S._ask_secret = lambda prompt: "k-masked"
    _args = argparse.Namespace(action="set", provider="groq", key=None)
    check("key set ไม่ส่ง KEY มาถามแบบซ่อนจอ",
          S.cmd_key(_args, {}, {}) == 0 and saved == {"groq": "k-masked"}, saved)
    saved.clear()
    _args2 = argparse.Namespace(action="set", provider="groq", key="k-arg")
    check("key set ส่ง KEY มาตรง ๆ ยังใช้ได้",
          S.cmd_key(_args2, {}, {}) == 0 and saved == {"groq": "k-arg"}, saved)
    S._ask_secret = lambda prompt: ""
    check("key set เว้นว่าง = ยกเลิก",
          S.cmd_key(argparse.Namespace(action="set", provider="groq", key=None),
                    {}, {}) == 1)
finally:
    S.save_keys, S._ask_secret, sys.stdin = _orig_save_keys, _orig_ask_secret, _orig_stdin2

_orig_ask2, _orig_stdin3, _orig_save3 = S.Prompt.ask, sys.stdin, S.save_keys
_orig_asksec = S._ask_secret
try:
    sys.stdin = _FakeTTY()
    S.Prompt.ask = staticmethod(lambda *a, **k: "n")
    captured = []
    S._ask_secret = lambda prompt: (captured.append(prompt) or "k-x")
    saved3 = {}
    S.save_keys = lambda keys: saved3.update(keys)
    check("ensure_key ถามผ่านช่องซ่อนจอ",
          S.ensure_key("groq", {}) is True and saved3 == {"groq": "k-x"}, saved3)
    check("ensure_key ไม่มีข้อความ (Enter = ข้าม) แล้ว",
          captured and "(Enter" not in captured[0], captured)
finally:
    S.Prompt.ask, sys.stdin, S.save_keys = _orig_ask2, _orig_stdin3, _orig_save3
    S._ask_secret = _orig_asksec

# 7) session http ต้องไม่แชร์ข้ามเธรด
seen = {}


def _grab(tag):
    seen[tag] = S._http_session()


ts = [threading.Thread(target=_grab, args=(i,)) for i in range(3)]
[t.start() for t in ts]
[t.join() for t in ts]
check("http session per thread", len({id(v) for v in seen.values()}) == 3)
check("http session stable in thread", S._http_session() is S._http_session())

# 8) tool call จากข้อความ: ห้ามยัดเป็น tool_calls ปลอม (id ที่ API ไม่รู้จัก)
orig_post = S._post_chat
recorded = []


class _Resp:
    def __init__(self, payload):
        self.status_code = 200
        self.text = json.dumps(payload)

    def json(self):
        return json.loads(self.text)


def fake_post(url, headers=None, payload=None, timeout=0, stream=False, tag="", retries=0):
    recorded.append(payload)
    if len(recorded) == 1:
        return _Resp({"choices": [{"message": {
            "content": '```tool {"name": "list_dir", "arguments": {"path": "."}} ```'}}]})
    return _Resp({"choices": [{"message": {"content": "เสร็จแล้ว"}}]})


try:
    S._post_chat = fake_post
    out, err, used, info = S._agent_steps(
        "openrouter", "some/model:free", [{"role": "user", "content": "ดูไฟล์"}],
        0.2, auto_yes=True, max_steps=3)
    check("text fallback ran tool", used == 1, used)
    check("text fallback finished", out.endswith("เสร็จแล้ว") and err == "", (out, err))
    second = recorded[1]["messages"]
    check("no fabricated tool_calls",
          not any(m.get("role") == "assistant" and m.get("tool_calls") for m in second))
    check("no tool role message with fake id",
          not any(m.get("role") == "tool" and "textcall" in str(m.get("tool_call_id"))
                  for m in second))
    check("tool result sent back as user text",
          any(m.get("role") == "user" and "ผลจากการเรียก tool" in str(m.get("content"))
              for m in second))
    check("info carries cap", info.get("cap") == 3, info)
finally:
    S._post_chat = orig_post

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)
print("ALL GUARDRAIL TESTS PASSED")
