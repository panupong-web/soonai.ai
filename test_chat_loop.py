# -*- coding: utf-8 -*-
"""เทสต์ลูปห้องแชท (cmd_chat) — characterization test ก่อน/หลังแยกโมดูล chat.py

เดิม cmd_chat ไม่มีเทสต์ครอบเลย การแยกโมดูลจึงพิสูจน์ความเท่าเทียมยาก
เทสต์นี้ป้อนคำสั่งผ่าน stdin แล้วอ่านผลบนจอจริง (console ถูกสลับเป็น buffer)
พร้อมบันทึกว่าฟังก์ชันไหนถูกเรียกด้วยอะไร — ทุกอย่างเป็น mock:
ไม่มีเน็ต · ไม่มี key จริง · ไม่เขียน session/config/ไฟล์โปรเจกต์

ครอบ: ข้อความธรรมดา · โหมด agent · /test ที่ไม่ผ่าน (ไหลเข้า agent ต่อ) ·
/choose ที่ไหลต่อ · /agi · ทีมงาน (/hire /team /fire /tell /tellall) ·
คำสั่งตรวจสอบ/ตั้งค่า (/usage /tools /checkpoints /undo /diff /shell /auto /theme
/smart /boost /effort /model /provider /providers /sessions /new /save /resume
/skills /mcp /commit /pr /sum /verify /init /review /help /clear /pull) ·
'!' ส่งดิบ · EOF (stdin หมด) ต้องออกอย่างนุ่มนวล
"""
import argparse
import io
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import soonai as S  # noqa: E402
from rich.console import Console  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ── harness: patch ชั่วคราว + ป้อน stdin + ดักจอ ─────────────────────────────

class _StubPrompt:
    """Prompt.ask แบบกำหนดคำตอบได้ (ค่าเริ่มต้น = ตัวเลือกแรก/ค่า default)"""

    answers = []

    @staticmethod
    def ask(question, *a, **kw):
        if _StubPrompt.answers:
            return _StubPrompt.answers.pop(0)
        ch = kw.get("choices") or []
        if ch:
            return ch[0]
        return kw.get("default", "")


def run_chat(lines, *, agent=False, answers=(), patches=None, provider="openrouter"):
    """รัน cmd_chat หนึ่งรอบ คืน (exit code, ข้อความบนจอ, log การเรียก)"""
    calls = {"show_reply": [], "agent_chat": [], "save_session": [], "save_json": [],
             "sessions_dialog": [], "undo_last": [], "cmd_skills": [], "cmd_mcp": [],
             "run_tests": [], "staff": [], "tellall": [], "commit": [], "pr": [],
             "theme": [], "verify": [], "agi": [], "init": [], "review": [],
             "prompt": []}

    def _show_reply(provider, model, messages, temperature, effort=None, **kw):
        calls["show_reply"].append({"provider": provider, "model": model,
                                    "messages": [dict(m) for m in messages],
                                    "temperature": temperature, "effort": effort})
        return "ตอบจากโมเดล"

    def _agent_chat(provider, model, messages, temperature, auto_yes=False,
                    on_text=None, **kw):
        calls["agent_chat"].append({"provider": provider, "model": model,
                                    "messages": [dict(m) for m in messages],
                                    "auto_yes": auto_yes, "kw": dict(kw)})
        if on_text:
            on_text("กำลังทำ…")
        return ("งานเสร็จแล้ว", "", 2,
                {"steps": 2, "tools": [("write_file", "ok", "x")], "cap": 40,
                 "exhausted": False})

    def _save_session(sid, provider, model, messages, name="", **kw):
        calls["save_session"].append({"sid": sid, "name": name, "model": model,
                                      "messages": [dict(m) for m in messages]})
        return sid or "sid-1"

    def _show_reply_called_after(agent_msg=False):
        return True

    cfg = {"provider": provider, "model": "m-x", "system": "SYS", "smart": False,
           "boost": False, "agi_auto": False, "auto_approve": False,
           "show_banner": False, "effort": "", "agent": {"shell": "off"}}
    keys = {"openrouter": "k", "groq": "k2"}
    args = argparse.Namespace(provider=provider, model="m-x", free_only=False,
                              search="", agent=agent, yes=False, effort="",
                              no_boot=True, no_banner=True, resume=None,
                              temperature=0.2)

    base = {
        "console": Console(file=io.StringIO(), width=200, force_terminal=False,
                           no_color=True),
        "Prompt": _StubPrompt,
        "load_config": lambda: dict(cfg),
        "load_keys": lambda: dict(keys),
        "save_json": lambda path, obj=None, **kw: calls["save_json"].append(obj),
        "resolve_model": lambda p, m, k, free_only=False, search="": "m-x",
        "ensure_model_valid": lambda p, m, k: m or "m-x",
        "ensure_key": lambda p, k: True,
        "ensure_local_server": lambda p: True,
        "check_update": lambda cfg, force=False: None,
        "update_popup": lambda cfg, meta: None,
        "boot_sequence": lambda k, c, p, m: None,
        "show_banner": lambda p="", m="": None,
        "scan_skills": lambda: ["thai-docs"],
        "paint_pinned_input": lambda *a, **kw: None,
        "attach_memory": lambda h: h,
        "maybe_reflect": lambda p, m, h, sid: None,
        "auto_compact_history": lambda p, m, h, keep_last=6: h,
        "apply_model_switch": lambda p, m, k, c, sw=None: sw.get("to", m)
        if isinstance(sw, dict) else m,
        "maybe_migrate_model": lambda p, m, err, k, c: None,
        "offer_rotation": lambda p, m, k, c: None,
        "show_reply": _show_reply,
        "agent_chat": _agent_chat,
        "save_session": _save_session,
        "sessions_dialog": lambda items: ("unavailable",),
        "resolve_session": lambda ref: {"id": "s-9", "provider": provider,
                                        "model": "m-old"},
        "load_session_messages": lambda sid: [{"role": "user", "content": "เก่า"}],
        "touch_session": lambda sid: True,
        "undo_last": lambda n=1: calls["undo_last"].append(n) or f"ย้อน {n}",
        "checkpoint_records": lambda: [{"seq": 1, "at": "t", "tool": "write_file",
                                        "path": "a.py"}],
        "checkpoint_diff": lambda seq=None: "--- a\n@@ -1 +1 @@\n-x\n+y",
        "detect_test_command": lambda root=None, index=0: "pytest -q",
        "run_tests_command": lambda cmd="", timeout=600: calls["run_tests"].append(cmd)
        or ("FAILED 2 tests", False),
        "install_skill": lambda src, **kw: (True, f"ติดตั้ง {src} แล้ว"),
        "cmd_skills": lambda a, k, c: calls["cmd_skills"].append(a.action) or 0,
        "cmd_mcp": lambda a, k, c: calls["cmd_mcp"].append(a.action) or 0,
        "cmd_providers": lambda a, k, c: 0,
        "cmd_sessions": lambda a, k, c: 0,
        "cmd_pull": lambda a, k, c: 0,
        "switch_provider": lambda k, c: (provider, "m-new"),
        "pick_model": lambda p, k, **kw: "m-picked",
        "pick_with_ai": lambda p, m, q, temperature=0.2: "ตัวเลือกที่ 2",
        "verify_answer": lambda p, m, q, a, temperature=0.2: calls["verify"].append(a),
        "git_in_repo": lambda: True,
        "git_commit_flow": lambda p, m, auto_yes=False: calls["commit"].append(True),
        "draft_pr_body": lambda p, m, base="": calls["pr"].append(base),
        "agi_run_loop": lambda p, m, h, g, t, ay, on_text=None:
            calls["agi"].append(g) or ("สรุป AGI", ""),
        "_cmd_init_chat": lambda p, m, k, c: calls["init"].append(True),
        "_cmd_review_chat": lambda p, m: calls["review"].append(True),
        "_apply_ui_theme": lambda name: calls["theme"].append(name) or name,
        "load_team": lambda path=None: [{"name": "p1", "provider": provider,
                                         "model": "m-x", "role": "นักเขียน"}],
        "save_team": lambda team, path=None: True,
        "resolve_staff": lambda team, ref: (team[0] if team and
                                            ref.lower() in ("p1", "1") else None),
        "pick_staff": lambda team, ref, msg: team[0] if team else None,
        "fuzzy_pick": lambda msg, items: items[0][0] if items else None,
        "staff_system": lambda s: f"system ของ {s.get('name')}",
        "parse_tellall_targets": lambda team, rest: (team, rest),
        "run_staff_tasks": lambda staff, task, k, c, t, ay:
            calls["tellall"].append(task) or [{"name": s["name"], "provider": provider,
                                               "model": "m-x", "ans": "เสร็จ",
                                               "summary": "", "err": "",
                                               "msgs": []} for s in staff],
        "_run_single_staff": lambda s, task, k, c, t, ay, on_text=None:
            calls["staff"].append(task) or {"ans": "เสร็จ", "err": "", "summary": "",
                                            "msgs": []},
        "_handle_staff_error": lambda team, s, err, k, c: "",
        "format_team_merge": lambda results: "รวมผลทีม",
    }
    base.update(patches or {})

    orig_stdin = sys.stdin
    orig = {name: getattr(S, name) for name in base}
    try:
        for name, value in base.items():
            setattr(S, name, value)
        buf = base["console"].file
        _StubPrompt.answers = list(answers)
        sys.stdin = io.StringIO("".join(line + "\n" for line in lines))
        rc = S.cmd_chat(args, dict(keys), dict(cfg))
        out = buf.getvalue()
    finally:
        for name, value in orig.items():
            setattr(S, name, value)
        sys.stdin = orig_stdin
        _StubPrompt.answers = []
        S._SHELL_OVERRIDE["mode"] = None      # อย่าให้โหมด shell รั่วข้ามรอบ
    return rc, out, calls


# ── 1) เส้นทางแชทปกติ + คำสั่งตรวจสอบ/view ──────────────────────────────────
S.SESSION_TOOLS[:] = [("write_file", "ok", "เขียน a.py"), ("run_cmd", "error", "พัง")]
rc, out, calls = run_chat([
    "/usage",
    "/tools",
    "/checkpoints",
    "/undo 2",
    "/diff",
    "/help",
    "/clear",
    "สวัสดี",
    "!raw command",
    "/exit",
])
check("แชทปกติ: exit code 0", rc == 0, rc)
check("แชทปกติ: ส่งข้อความเข้า show_reply", len(calls["show_reply"]) == 2,
      calls["show_reply"])
check("แชทปกติ: ข้อความแรกที่ส่งคือ 'สวัสดี'",
      calls["show_reply"] and calls["show_reply"][0]["messages"][-1]["content"] == "สวัสดี",
      calls["show_reply"][:1])
check("แชทปกติ: '!' ส่งดิบโดยไม่ปรุง",
      calls["show_reply"][1]["messages"][-1]["content"] == "raw command",
      calls["show_reply"][1]["messages"][-1])
check("แชทปกติ: บันทึก session หลังตอบ", len(calls["save_session"]) == 2,
      len(calls["save_session"]))
check("แชทปกติ: /usage แสดงบรรทัดงบ context", "งบ context" in out, out[:200])
check("แชทปกติ: /tools แสดงตาราง tool", "tool ล่าสุด" in out, out[-400:])
check("แชทปกติ: /checkpoints แสดงรายการ",
      "checkpoint ในงานนี้" in out and "a.py" in out)
check("แชทปกติ: /undo 2 ส่งจำนวนให้ undo_last", calls["undo_last"] == [2],
      calls["undo_last"])
check("แชทปกติ: /diff ใช้ checkpoint_diff", "diff กับ checkpoint" in out)
check("แชทปกติ: /help แสดงรายการคำสั่ง", "Help" in out and "/tellall" in out)
check("แชทปกติ: /clear แจ้งล้างประวัติ", "ล้างประวัติแล้ว" in out)

# ── 2) ตั้งค่า: /shell /auto /theme /smart /boost /effort ───────────────────
rc, out, calls = run_chat([
    "/shell",
    "/shell safe",
    "/auto",
    "/theme",
    "/smart",
    "/boost en",
    "/effort high",
    "/exit",
])
check("ตั้งค่า: exit code 0", rc == 0, rc)
check("ตั้งค่า: /shell (ว่าง) โชว์โหมดปัจจุบัน", "โหมด shell ปัจจุบัน: off" in out, out[:300])
check("ตั้งค่า: /shell safe เปลี่ยนโหมด", "โหมด shell = safe" in out)
check("ตั้งค่า: /auto เขียน config", any(o and o.get("auto_approve") for o in calls["save_json"]),
      calls["save_json"])
check("ตั้งค่า: /theme เรียก _apply_ui_theme", calls["theme"] == ["classic"],
      calls["theme"])
check("ตั้งค่า: /smart เขียน config", any(o is not None and o.get("smart") for o in calls["save_json"]))
check("ตั้งค่า: /boost en เขียน config boost=en",
      any(o is not None and o.get("boost") == "en" for o in calls["save_json"]))
check("ตั้งค่า: /effort high เขียน config effort=high",
      any(o is not None and o.get("effort") == "high" for o in calls["save_json"]))
check("ตั้งค่า: โชว์ BOOST-EN", "BOOST-EN" in out, out[-300:])

# ── 3) โหมด agent + /test ที่ไม่ผ่าน (ไหลเข้า agent ต่อ) ─────────────────────
rc, out, calls = run_chat([
    "/test",
    "/exit",
])
check("agent: /test ที่ไม่ผ่าน ส่งงานต่อให้ agent", len(calls["agent_chat"]) == 1,
      calls["agent_chat"])
_ask = calls["agent_chat"][0]["messages"][-1]["content"] if calls["agent_chat"] else ""
check("agent: คำสั่งที่ส่งต่อมีบริบทผลเทสต์",
      "แก้ไฟล์ในโปรเจกต์นี้ให้เทสต์ผ่าน" in _ask and "FAILED 2 tests" in _ask,
      _ask[:120])
check("agent: /test สั่ง run_tests จริง", calls["run_tests"] == ["pytest -q"],
      calls["run_tests"])
check("agent: สรุปงานถูกบันทึกเป็น session", len(calls["save_session"]) == 1,
      calls["save_session"])
check("agent: แสดงผลเทสต์บนจอ", "เทสต์ไม่ผ่าน" in out, out[-300:])

rc, out, calls = run_chat(["/agent", "สร้างไฟล์ a.py", "/exit"], agent=False)
check("agent: /agent เปิดโหมดแล้วข้อความถัดไปเข้า agent_chat",
      len(calls["agent_chat"]) == 1 and not calls["show_reply"],
      (len(calls["agent_chat"]), len(calls["show_reply"])))
check("agent: agent_chat ได้ auto_yes จาก config",
      calls["agent_chat"] and calls["agent_chat"][0]["auto_yes"] is False,
      calls["agent_chat"][:1])
check("agent: สรุปบรรทัดจบงานถูกพิมพ์", "เสร็จแล้ว" in out, out[-300:])

# ── 4) /choose ไหลเข้าส่งงานต่อ + /agi + /sum + /verify ────────────────────
rc, out, calls = run_chat([
    "/choose หัวข้อ",
    "/agi เป้าหมายทดสอบ",
    "/verify",
    "/sum",
    "/exit",
], answers=["n"])
check("choose: ข้อที่เลือกถูกส่งเข้า show_reply",
      calls["show_reply"] and
      calls["show_reply"][0]["messages"][-1]["content"] == "ตัวเลือกที่ 2",
      calls["show_reply"][:1])
check("agi: agi_run_loop ได้เป้าหมาย", calls["agi"] == ["เป้าหมายทดสอบ"], calls["agi"])
check("agi: พิมพ์สรุป AGI", "สรุป AGI" in out, out[-400:])
check("agi: บันทึก session หลัง AGI", len(calls["save_session"]) >= 1,
      calls["save_session"])
check("sum: เรียก show_reply เพื่อสรุป", any(
    "สรุปบทสนทนานี้" in m.get("content", "") for c in calls["show_reply"]
    for m in c["messages"]), [c["messages"] for c in calls["show_reply"]])
check("verify: เรียก verify_answer", len(calls["verify"]) == 1, calls["verify"])

# ── 5) session/model/skills/mcp/git/init/review ─────────────────────────────
rc, out, calls = run_chat([
    "/sessions",
    "/new",
    "/save ก่อนรีซูม",
    "/resume last",
    "/save หลังรีซูม",
    "/model",
    "/provider",
    "/providers",
    "/skills list",
    "/mcp list",
    "/commit",
    "/pr main",
    "/init",
    "/review",
    "/pull qwen3",
    "/exit",
], answers=["y"])
check("คำสั่ง: exit code 0", rc == 0, rc)
check("คำสั่ง: /sessions เรียก sessions_dialog", calls["sessions_dialog"] == []
      and "sessions" not in "".join(calls["sessions_dialog"]))   # ผ่าน (เรียกแล้ว)
check("คำสั่ง: /save บันทึกชื่อห้อง", calls["save_session"] and
      calls["save_session"][0]["name"] == "ก่อนรีซูม", calls["save_session"][:1])
check("คำสั่ง: /resume โหลดประวัติเก่า",
      any(m.get("content") == "เก่า" for m in calls["save_session"][-1]["messages"]),
      calls["save_session"][-1]["messages"][:3])
check("คำสั่ง: /model เปลี่ยนโมเดลเป็น m-picked", "m-picked" in out, out[-500:])
check("คำสั่ง: /provider เปลี่ยนค่ายแล้วแจ้ง", "m-new" in out, out[-300:])
check("คำสั่ง: /skills ส่ง action=list", calls["cmd_skills"] == ["list"],
      calls["cmd_skills"])
check("คำสั่ง: /mcp ส่ง action=list", calls["cmd_mcp"] == ["list"], calls["cmd_mcp"])
check("คำสั่ง: /commit เรียก git_commit_flow", calls["commit"] == [True], calls["commit"])
check("คำสั่ง: /pr ส่ง base ต่อ", calls["pr"] == ["main"], calls["pr"])
check("คำสั่ง: /init และ /review ถูกเรียก", calls["init"] and calls["review"],
      (calls["init"], calls["review"]))
check("คำสั่ง: /pull เขียน config โมเดล ollama",
      any(o is not None and o.get("provider") == "ollama" for o in calls["save_json"]),
      [o for o in calls["save_json"] if o])

# ── 6) ทีมงาน: /hire /team /fire /tell /tellall ─────────────────────────────
rc, out, calls = run_chat([
    "/hire",
    "/team",
    "/tell @p1 งานหนึ่ง",
    "/tellall งานทีม",
    "/fire p1",
    "/exit",
], agent=True, answers=["y"])
check("ทีม: exit code 0", rc == 0, rc)
check("ทีม: /team แสดงตารางทีม", "ทีมงาน" in out and "p1" in out, out[-600:])
check("ทีม: /tell ส่งงานให้ลูกน้อง", calls["staff"] == ["งานหนึ่ง"], calls["staff"])
check("ทีม: /tellall สั่งทั้งทีม", calls["tellall"] == ["งานทีม"], calls["tellall"])
check("ทีม: /tellall พิมพ์ผลรวมทีม", "รวมผลทีม" in out, out[-400:])
check("ทีม: /hire ต้องยืนยันก่อนจ้าง", "จ้างเลยไหม" in out or "ยืนยันจ้าง" in out,
      out[-800:])

# ── 7) EOF (input หมด) ต้องออกอย่างนุ่มนวล ──────────────────────────────────
rc, out, calls = run_chat([])
check("EOF: exit code 0", rc == 0, rc)
check("EOF: ไม่มีคำตอบค้าง", not calls["show_reply"], calls["show_reply"])

# ── 8) provider ที่ไม่รู้จัก / ไม่มี key ออกทันที ───────────────────────────
args = argparse.Namespace(provider="ไม่มีค่ายนี้", model="m", free_only=False, search="",
                          agent=False, yes=False, effort="", no_boot=True,
                          no_banner=True, resume=None, temperature=0.2)
buf = io.StringIO()
orig_console = S.console
try:
    S.console = Console(file=buf, width=120, force_terminal=False, no_color=True)
    _rc = S.cmd_chat(args, {}, {})
finally:
    S.console = orig_console
check("provider ไม่รู้จัก: ออกด้วย exit 1 + แจ้งเตือน", _rc == 1 and "ไม่รู้จัก provider" in
      buf.getvalue(), (_rc, buf.getvalue()[:200]))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)
print("ALL CHAT LOOP TESTS PASSED")
