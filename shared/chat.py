# -*- coding: utf-8 -*-
"""chat: ลูปห้องแชท + ตัวจัดการคำสั่ง "/" ของ CLI (แยกออกจาก soonai.py — Step 5)

เดิมคือ ``cmd_chat`` ฟังก์ชันเดียว ~1,081 บรรทัดใน soonai.py ตอนนี้แบ่งหน้าที่ชัด:
- ``ChatState``        สภาพของห้อง 1 ห้อง (แทนตัวแปร local เดิมของ cmd_chat)
- ``_framed_input`` / ``read_input``  ชั้นอ่านอินพุต (prompt_toolkit + กรอบ)
- ``_agi_turn``        เป้าหมายแบบ AGI 1 รอบ (วางแผน→ทำ→ตรวจ)
- ``handle_command``   ตัวจัดการคำสั่ง "/" ทุกตัว (คืน True = จัดการแล้ว)
- ``cmd_chat``         bootstrap + ลูปแชท + ส่งงานโมเดล (ทางเข้าเดิมของ CLI)

วิธีอ่าน seam/state (กฎเดียวกับโมดูลย่อยอื่น):
- ``import runtime as R`` แล้วอ่านด้วย **attribute access** เท่านั้น (``R.console``,
  ``R.agent_chat``, ``R.PROVIDERS``) → ``soonai.X = ...`` จากภายนอก (เทสต์) มีผล
  กับโค้ดในโมดูลนี้ด้วย เพราะ facade mirror + propagate ให้
- ห้าม ``from X import Y`` ข้ามโมดูล เพราะสำเนาที่ import ไว้จะกลายเป็นของเก่า
  ทันทีที่ถูก patch → depgraph จึงรายงาน bind_refs = 0 และไม่มีชื่อถูกฉีดเข้าโมดูล
"""
import argparse
import os
import re
import sys
from pathlib import Path

from rich import box
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import debug as _DBG    # โหมด debug: บันทึก traceback ของ exception ที่ถูกกลืน
import runtime as R      # noqa: F401 - ศูนย์ seam/state (attribute access เท่านั้น)


class ChatState:
    """สภาพของห้องแชท 1 ห้อง — แทนตัวแปร local เดิมของ cmd_chat

    ตัวจัดการคำสั่งต้องแก้ provider/model/history/sid/agent/... ได้ จึงส่ง
    object เดียวต่อ (ค่าจริงถูกกำหนดใน cmd_chat ตอน bootstrap เหมือนเดิม)
    """

    __slots__ = ("args", "keys", "cfg", "provider", "model", "history", "sid",
                 "agent", "auto_yes", "effort", "temperature", "q",
                 "ptk_session", "ptk_history")

    def __init__(self, args, keys, cfg):
        self.args, self.keys, self.cfg = args, keys, cfg
        self.provider = ""
        self.model = ""
        self.history = []
        self.sid = None
        self.agent = False
        self.auto_yes = False
        self.effort = ""
        self.temperature = getattr(args, "temperature", 0.7)
        self.q = ""
        self.ptk_session = None
        self.ptk_history = None

def _framed_input(st):
    """แถบพิมพ์กรอบจักรวาลอนิเมชัน (วาดสดตอนพิมพ์) คืนข้อความที่พิมพ์"""
    from prompt_toolkit.application import Application
    from prompt_toolkit.styles import Style

    # ชื่อกรอบเอาแค่ ค่าย/โมเดล ส่วนโหมด+สถานะไปอยู่บรรทัดสถานะ (ไม่ซ้ำกัน)
    _bname = R.box_title(st.provider, st.model)
    _sl = R.status_line(st.provider, st.model, st.agent, st.auto_yes, st.effort)
    layout, buf, kb = R.build_input_bar(
        st.ptk_history, f"{_bname} · {_sl}" if _sl else _bname)
    app = Application(
        layout=layout,
        key_bindings=kb,
        style=Style.from_dict(R.INPUT_STYLE),
        full_screen=False,
        erase_when_done=True,
    )
    return app.run()
def read_input(st):
    if sys.stdin.isatty():
        try:
            return _framed_input(st)
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception as e:
            # ชั้นกรอบอินพุตพัง (prompt_toolkit/เทอร์มินัล) → ตกไปใช้ prompt ธรรมดา
            _DBG.log_swallowed(e, "chat.py:read_input", "กรอบอินพุตพัง — ใช้ prompt ธรรมดาแทน")
    if st.ptk_session is not None:
        try:
            R.console.print(R.input_box_top(st.provider, st.model, st.agent, st.auto_yes, st.effort),
                          style="cyan", highlight=False)
            q = st.ptk_session.prompt("> ", placeholder="Ask Soonai to do anything…")
            R.console.print(R.input_box_bottom(), style="dim", highlight=False)
            return q
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception as e:
            R.console.print(f"[dim](โหมดพิมพ์พิเศษใช้ไม่ได้ สลับเป็นแบบธรรมดา: {e})[/dim]")
            try:
                st.ptk_session.app.exit(exception=e, style="class:aborting")
            except Exception:
                pass
            return R.console.input("[bold cyan]คุณ: [/]")
    return R.console.input("[bold cyan]คุณ: [/]")
def _agi_turn(st, goal):
    """รันเป้าหมายแบบ AGI 1 รอบ (วางแผน→ทำ→ตรวจ) แล้วบันทึกประวัติ"""
    st.agent = True
    st.history.append({"role": "user", "content": goal})
    R.console.print(Text(f"> {goal}", style="cyan"))
    try:
        summary, err = R.agi_run_loop(
            st.provider, st.model, st.history, goal, st.temperature, st.auto_yes,
            on_text=lambda t: R.console.print(Markdown(t)))
    except (R.TurnCancelled, KeyboardInterrupt):
        st.history.pop()
        R.console.print("[dim](AGI หยุดแล้ว — กลับมารอคำสั่ง)[/dim]")
        return
    if err:
        R.console.print(f"[red]{err}[/red]")
        st.history.pop()
        _migrated = R.maybe_migrate_model(st.provider, st.model, err, st.keys, st.cfg)
        if _migrated:
            st.model = _migrated
        elif "429" in err:
            _rot = R.offer_rotation(st.provider, st.model, st.keys, st.cfg)
            if _rot:
                st.model = _rot
    elif summary:
        st.model = R.apply_model_switch(st.provider, st.model, st.keys, st.cfg)
        st.history.append({"role": "assistant", "content": summary})
        R.console.print(Panel(Markdown(summary), title="AGI สรุป",
                            border_style="green"))
        st.history = R.auto_compact_history(st.provider, st.model, st.history)
        st.sid = R.save_session(st.sid or R._session_id(), st.provider, st.model, st.history)
        st.history = st.history[-21:]
    else:
        st.history.pop()
        R.console.print("[dim](AGI ไม่ได้อะไรกลับมา)[/dim]")
EXIT = "exit"        # ค่าที่ handle_command คืนเมื่อต้องออกจากห้องแชท (เดิมคือ break)


def handle_command(st, q):
    """จัดการคำสั่ง "/" ทุกตัว — คืนค่าบอกลูปแชทว่าต้องทำอะไรต่อ

    - ``True``    จัดการแล้ว → กลับไปอ่านอินพุตใหม่
    - ``EXIT``    ผู้ใช้สั่งออก (/exit, /quit, exit, quit) → จบลูปแชท
    - ``False``   ไม่ใช่คำสั่งที่รู้จัก หรือเป็นคำสั่งที่ตั้งใจไหลต่อไปส่งงานโมเดล
      (เช่น /choose และ /test ที่ไม่ผ่าน ซึ่งแก้ ``st.q`` ไว้ให้ลูปด้านนอกใช้ต่อ)
    """
    if q.lower() == "/choose" or q.lower().startswith("/choose "):
        parts = q.split(None, 1)
        topic = parts[1].strip() if len(parts) > 1 else ""
        if not topic:
            try:
                topic = R.Prompt.ask("จะให้แตกหัวข้ออะไรเป็นช้อย").strip()
            except (EOFError, KeyboardInterrupt):
                R.console.print()
                return True
            if not topic:
                return True
        try:
            st.q = R.pick_with_ai(st.provider, st.model, topic)
        except (EOFError, KeyboardInterrupt):
            R.console.print()
            return True
        if not q:
            return True
    if q.lower() == "/agi auto" or q.lower().startswith("/agi auto "):
        parts = q.split(None, 2)
        arg = parts[2].strip().lower() if len(parts) > 2 else ""
        if arg in ("on", "เปิด", "1", "true"):
            st.cfg["agi_auto"] = True
            R.save_json(R.CONFIG_FILE, st.cfg)
            R.console.print("[green]AGI อัตโนมัติ: เปิดแล้ว[/green]")
        elif arg in ("off", "ปิด", "0", "false"):
            st.cfg["agi_auto"] = False
            R.save_json(R.CONFIG_FILE, st.cfg)
            R.console.print("[dim]AGI อัตโนมัติ: ปิดแล้ว (ใช้ /agi สั่งเองได้)[/dim]")
        else:
            R.console.print(f"[dim]AGI อัตโนมัติ: {'เปิด' if st.cfg.get('agi_auto', True) else 'ปิด'} "
                          "(ใช้: /agi auto on|off)[/dim]")
        return True
    if q.lower() == "/agi" or q.lower().startswith("/agi "):
        parts = q.split(None, 1)
        goal = parts[1].strip() if len(parts) > 1 else ""
        if not goal:
            try:
                goal = R.Prompt.ask("เป้าหมาย AGI").strip()
            except (EOFError, KeyboardInterrupt):
                R.console.print()
                return True
            if not goal:
                return True
        _agi_turn(st, goal)
        return True
    if q.lower() in ("/exit", "/quit", "exit", "quit"):
        R.maybe_reflect(st.provider, st.model, st.history, st.sid)
        return EXIT
    if q.lower() == "/clear":
        st.history = [m for m in st.history if m.get("role") == "system"]
        R.console.print("[dim](ล้างประวัติแล้ว)[/dim]")
        return True
    if q.lower() == "/shell" or q.lower().startswith("/shell "):
        parts = q.split(None, 1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        if arg == "":
            cur = R._shell_mode()
            R.console.print(Panel(
                f"โหมด shell ปัจจุบัน: [bold]{cur}[/bold]\n"
                "[dim]off  = agent รันคำสั่งไม่ได้เลย (ค่าเริ่มต้น)\n"
                "safe = รันเฉพาะคำสั่งอ่าน/เทสต์ใน allowlist แบบคำสั่งเดียว "
                "(env ตัดความลับ · cwd = โฟลเดอร์งาน · timeout 120s)\n"
                "on   = เปิดเต็ม (รับความเสี่ยงเอง)[/dim]\n"
                "ใช้: /shell off | /shell safe | /shell on",
                title="shell ของ agent", border_style="cyan"))
            return True
        if arg not in R.SHELL_MODES:
            R.console.print("[yellow]ใช้: /shell off|safe|on[/yellow]")
            return True
        if arg == "on" and sys.stdin.isatty():
            try:
                if R.Prompt.ask("โหมด on คือ shell เต็ม — shell หลบ blacklist ได้ "
                              "จึงกัน secret ไม่ได้แน่นอน รับทราบไหม?",
                              choices=["y", "n"], default="n") != "y":
                    R.console.print("[dim]ยกเลิก[/dim]")
                    return True
            except (EOFError, KeyboardInterrupt):
                R.console.print()
                return True
        if R.set_shell_mode(arg, st.cfg):
            R.console.print(f"[green]โหมด shell = {arg}[/green]")
            if arg == "safe":
                cmd0 = R.detect_test_command()
                R.console.print(f"[dim](คำสั่งอ่าน/เทสต์ที่อนุญาตในโหมด safe"
                              f"{' เช่น: ' + cmd0 if cmd0 else ''})[/dim]")
        else:
            R.console.print("[red]บันทึกโหมดไม่ได้[/red]")
        return True
    if q.lower() == "/checkpoints":
        recs = R.checkpoint_records()
        if not recs:
            R.console.print("[dim]ยังไม่มี checkpoint ในงานนี้ (ยังไม่มีไฟล์ถูกเขียนทับ)[/dim]")
        else:
            t = Table(title=f"checkpoint ในงานนี้ ({len(recs)} รายการ)", box=box.SIMPLE)
            t.add_column("#")
            t.add_column("เวลา")
            t.add_column("tool")
            t.add_column("ไฟล์")
            for r in recs[-15:]:
                t.add_row(str(r.get("seq")), str(r.get("at", "")), str(r.get("tool", "")),
                          str(r.get("path", "")))
            R.console.print(t)
            R.console.print("[dim]/undo = ย้อนล่าสุด · /undo 3 = ย้อน 3 ไฟล์ · "
                          "/diff ดูความต่างจาก checkpoint[/dim]")
        return True
    if q.lower() == "/undo" or q.lower().startswith("/undo "):
        parts = q.split(None, 1)
        try:
            n = int(parts[1]) if len(parts) > 1 else 1
        except Exception:
            n = 1
        R.console.print(R.undo_last(n))
        return True
    if q.lower() == "/diff" or q.lower().startswith("/diff "):
        parts = q.split(None, 1)
        seq = parts[1].strip() if len(parts) > 1 else None
        d = R.checkpoint_diff(seq)
        if d.startswith("---") or "\n@@ " in d:
            from rich.syntax import Syntax
            R.console.print(Panel(Syntax(d, "diff", word_wrap=True),
                                title="diff กับ checkpoint", border_style="yellow"))
        else:
            R.console.print(f"[dim]{d}[/dim]")
        return True
    if q.lower() == "/tools" or q.lower().startswith("/tools "):
        parts = q.split(None, 1)
        try:
            n = int(parts[1]) if len(parts) > 1 else 15
        except Exception:
            n = 15
        rows = R.SESSION_TOOLS[-max(1, n):]
        if not rows:
            R.console.print("[dim]ยังไม่มี tool ถูกเรียกในเซสชันนี้[/dim]")
            return True
        t = Table(title=f"tool ล่าสุด {len(rows)}/{len(R.SESSION_TOOLS)} รายการ", box=box.SIMPLE)
        t.add_column("#")
        t.add_column("tool")
        t.add_column("ผล")
        t.add_column("สรุป")
        base_n = max(0, len(R.SESSION_TOOLS) - len(rows))
        colors = {"ok": "green", "error": "red", "denied": "yellow"}
        for idx, (nm, st, sm) in enumerate(rows, base_n + 1):
            t.add_row(str(idx), nm, f"[{colors.get(st, 'dim')}]{st or '-'}[/]", sm[:90])
        R.console.print(t)
        return True
    if q.lower() == "/commit" or q.lower().startswith("/commit "):
        if not R.git_in_repo():
            R.console.print("[yellow]โฟลเดอร์นี้ไม่ใช่ git repo[/yellow]")
            return True
        try:
            R.git_commit_flow(st.provider, st.model, auto_yes=st.auto_yes)
        except (R.TurnCancelled, KeyboardInterrupt):
            R.console.print("[dim](ยกเลิกการ commit)[/dim]")
        R._STATUS_CACHE["extra"] = None      # ให้บรรทัดสถานะอ่าน git ใหม่
        return True
    if q.lower() == "/pr" or q.lower().startswith("/pr "):
        parts = q.split(None, 1)
        base2 = parts[1].strip() if len(parts) > 1 else ""
        try:
            R.draft_pr_body(st.provider, st.model, base2)
        except (R.TurnCancelled, KeyboardInterrupt):
            R.console.print("[dim](ยกเลิกร่าง PR)[/dim]")
        return True
    if q.lower() == "/usage":
        R.console.print(f"[dim]{R.usage_line() or 'ยังไม่มีการเรียกโมเดลในเซสชันนี้'} · "
                      f"งบ context ~{R._kfmt(R.context_budget())} token · "
                      f"shell={R._shell_mode()}[/dim]")
        return True
    if q.lower() == "/test" or q.lower().startswith("/test "):
        _, _, tail = q.partition(" ")
        cmd_t = tail.strip() or R.detect_test_command()
        if not cmd_t:
            R.console.print("[yellow]ไม่พบคำสั่งเทสต์ของโปรเจกต์นี้ — พิมพ์ /test <คำสั่ง> "
                          "หรือเขียนบรรทัด 'test: <คำสั่ง>' ไว้ใน AGENTS.md[/yellow]")
            return True
        R.console.print(f"[dim]คำสั่งเทสต์: {cmd_t}[/dim]")
        if R._shell_mode() == "off" and R.set_shell_mode("safe", st.cfg, persist=False):
            R.console.print("[dim](เปิด shell = safe ให้เฉพาะเซสชันนี้ เพื่อให้ agent รันเทสต์"
                          "ซ้ำเองได้ — ไม่ได้แก้ config; จะปิดถาวร/เปิดเต็มใช้ /shell)[/dim]")
        if sys.stdin.isatty():
            try:
                if R.Prompt.ask("รันเลยไหม?", choices=["y", "n"], default="y") != "y":
                    R.console.print("[dim]ยกเลิก[/dim]")
                    return True
            except (EOFError, KeyboardInterrupt):
                R.console.print()
                return True
        out_t, ok_t = R.run_tests_command(cmd_t, timeout=900)
        R.console.print(Panel(out_t[-3000:] or "(ไม่มี output)", title="ผลเทสต์",
                            border_style="green" if ok_t else "red"))
        if ok_t:
            R.console.print("[green]เทสต์ผ่าน ✅[/green]")
            st.history.append({"role": "user", "content": f"/test {cmd_t} → ผ่าน"})
            st.sid = R.save_session(st.sid or R._session_id(), st.provider, st.model, st.history)
            return True
        R.console.print("[yellow]เทสต์ไม่ผ่าน — ส่งผลจริงให้ agent หาสาเหตุและแก้ต่อ…[/yellow]")
        st.agent = True
        R._FORCE_TOOLS["on"] = True
        st.q = (f"แก้ไฟล์ในโปรเจกต์นี้ให้เทสต์ผ่าน — รันเทสต์ด้วยคำสั่ง `{cmd_t}` แล้วไม่ผ่าน "
             f"นี่คือผลจริง:"
             f"\n\n{out_t[-2500:]}\n\n"
             f"หาสาเหตุจากโค้ดจริง (อ่านไฟล์ที่เกี่ยวข้อง) แก้ให้ถูกจุด "
             f"แล้วเรียก tool run_tests ซ้ำเพื่อยืนยันว่าผ่านจริง")
    if q.lower() == "/agent":
        st.agent = not st.agent
        R.console.print("[green]เปิดโหมดสั่งงานเครื่องแล้ว "
                      "(สร้างไฟล์/โฟลเดอร์/รันคำสั่งได้ จะถามก่อนทำ)[/green]"
                      if st.agent else "[dim]ปิดโหมดสั่งงานเครื่องแล้ว[/dim]")
        return True
    if q.lower() in ("/hire", "/team") or q.lower().startswith(("/fire ", "/tell ")):
        if not st.agent:
            R.console.print("[yellow]คำสั่งทีมใช้ได้เฉพาะตอนเปิด /agent[/yellow]")
            return True
    if q.lower() == "/hire":
        team = R.load_team()
        if len(team) >= R.MAX_STAFF:
            R.console.print(f"[yellow]ทีมเต็มแล้ว (สูงสุด {R.MAX_STAFF} คน) — /fire ออกก่อน[/yellow]")
            return True
        fp = R.fuzzy_pick("Select provider:",
                        [(pid, f"{pid} — {p['name']}") for pid, p in R.PROVIDERS.items()
                         if not p.get("tool_only")])
        if fp:
            pid = fp
        elif fp == "":
            return True
        else:
            try:
                pid = R.Prompt.ask("เลือกค่าย (provider id)",
                                 default=st.cfg.get("provider", "ollama")).strip()
            except Exception:
                return True
        if pid not in R.PROVIDERS:
            R.console.print(f"[red]ไม่รู้จัก provider: {pid}[/red]")
            return True
        if not R.ensure_key(pid, st.keys):
            return True
        if not R.ensure_local_server(pid):
            return True
        m = R.pick_model(pid, st.keys)
        if not m:
            return True
        try:
            default_name = f"staff{len(team) + 1}"
            name = R.Prompt.ask("ชื่อลูกน้อง", default=default_name).strip() or default_name
            if R.resolve_staff(team, name):
                R.console.print("[yellow]ชื่อนี้มีแล้ว — ตั้งชื่ออื่น[/yellow]")
                return True
            role = R.Prompt.ask("ตำแหน่ง/บริบทงาน (เช่น นักเขียนโค้ด Python เน้นโค้ดสะอาด)").strip()
            if not role:
                role = "ผู้ช่วยทั่วไป"
        except Exception:
            return True
        staff = {"name": name, "provider": pid, "model": m, "role": role}
        R.console.print(Panel(f"[bold]{name}[/bold] · {pid} / {m}\n[dim]{role}[/dim]",
                            title="ยืนยันจ้าง (บรีฟงานที่จะส่งให้ดูด้านล่าง)", border_style="green"))
        R.console.print(f"[dim]{R.staff_system(staff)[:400]}[/dim]")
        try:
            if R.Prompt.ask("จ้างเลยไหม?", choices=["y", "n"], default="y") != "y":
                return True
        except Exception:
            return True
        team.append(staff)
        R.save_team(team)
        R.console.print(f"[green]จ้าง {name} แล้ว ({len(team)}/{R.MAX_STAFF}) — สั่งงานด้วย /tell @{name} ...[/green]")
        return True
    if q.lower() == "/team":
        team = R.load_team()
        if not team:
            R.console.print("[dim]ยังไม่มีลูกน้อง — จ้างด้วย /hire (สูงสุด 5 คน)[/dim]")
            return True
        table = R.neo_table(title=f"ทีมงาน ({len(team)}/{R.MAX_STAFF})", show_lines=False)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("ชื่อ", style="white")
        table.add_column("ค่าย/โมเดล", style="white")
        table.add_column("ตำแหน่ง", style="white")
        for i, s in enumerate(team, 1):
            table.add_row(str(i), s.get("name", ""),
                          f"{s.get('provider', '')} / {(s.get('model', '') or '')[:40]}",
                          (s.get("role", "") or "")[:60])
        R.console.print(table)
        return True
    if q.lower() == "/fire" or q.lower().startswith("/fire "):
        parts = q.split(None, 1)
        ref = parts[1].strip() if len(parts) > 1 else ""
        team = R.load_team()
        if not team:
            R.console.print("[dim]ยังไม่มีลูกน้อง — ไม่มีใครให้ไล่ออก[/dim]")
            return True
        s = R.pick_staff(team, ref, "เลือกคนที่จะไล่ออก (Esc = ยกเลิก):")
        if not s:
            if not ref and sys.stdin.isatty():
                R.console.print("[dim]ยกเลิกแล้ว[/dim]")
            elif ref:
                R.console.print("[yellow]ไม่เจอลูกน้องคนนี้[/yellow]")
            else:
                R.console.print("[yellow]ใช้: /fire <ลำดับ|ชื่อ>[/yellow]")
            return True
        team = [x for x in team
                if str(x.get("name", "")).lower() != str(s.get("name", "")).lower()]
        R.save_team(team)
        R.console.print(f"[green]ไล่ {s.get('name')} ออกแล้ว ({len(team)}/{R.MAX_STAFF})[/green]")
        return True
    if q.lower() == "/tell" or q.lower().startswith("/tell "):
        parts = q.split(None, 2)
        ref = parts[1].lstrip("@").strip() if len(parts) > 1 else ""
        task = parts[2].strip() if len(parts) > 2 else ""
        team = R.load_team()
        if not team:
            R.console.print("[yellow]ยังไม่มีลูกน้อง — จ้างด้วย /hire ก่อน[/yellow]")
            return True
        s = R.resolve_staff(team, ref) if ref else None
        if not s:
            picked = R.fuzzy_pick(
                "เลือกลูกน้อง:",
                [(x.get("name", ""),
                  f"{x.get('name', '')} — {(x.get('role', '') or '')[:40]} "
                  f"({x.get('provider', '')} / {(x.get('model', '') or '')[:30]})")
                 for x in team])
            if picked:
                s = R.resolve_staff(team, picked)
            elif picked == "":
                return True
            else:
                R.console.print("[yellow]ไม่เจอลูกน้องคนนี้ — ดูรายชื่อด้วย /team[/yellow]")
                return True
        if not s:
            if not ref:
                R.console.print("[yellow]ใช้: /tell @<ชื่อ|ลำดับ> <งานที่สั่ง>[/yellow]")
            else:
                R.console.print("[yellow]ไม่เจอลูกน้องคนนี้ — ดูรายชื่อด้วย /team[/yellow]")
            return True
        if not task:
            try:
                task = R.Prompt.ask(f"งานที่จะสั่ง @{s.get('name')}").strip()
            except Exception:
                return True
            if not task:
                return True
        if not R.ensure_key(s["provider"], st.keys):
            return True
        if not R.ensure_local_server(s["provider"]):
            return True
        R.console.print(f"[bold green]{s.get('name')} ({s.get('provider')} / {s.get('model')}) รับงาน:[/]")
        try:
            res = R._run_single_staff(s, task, st.keys, st.cfg, st.temperature, st.auto_yes,
                                    on_text=lambda t: R.console.print(Markdown(t)))
        except (R.TurnCancelled, KeyboardInterrupt):
            R.console.print("[dim](ยกเลิกแล้ว — กลับมารอคำสั่ง)[/dim]")
            return True
        if res["err"]:
            R.console.print(f"[red]{res['err']}[/red]")
            _msg = R._handle_staff_error(team, s, res["err"], st.keys, st.cfg)
            if _msg:
                R.console.print(f"[dim]{_msg}[/dim]")
        elif not res["ans"]:
            R.console.print(R.nothing_done_reason(res["msgs"]))
        else:
            if res["summary"]:
                R.console.print(f"[dim]{res['summary']}[/dim]")
        return True
    if q.lower() == "/tellall" or q.lower().startswith("/tellall "):
        rest = q[len("/tellall"):].strip()
        team = R.load_team()
        if not team:
            R.console.print("[yellow]ยังไม่มีลูกน้อง — จ้างด้วย /hire ก่อน[/yellow]")
            return True
        targets, task = R.parse_tellall_targets(team, rest)
        if rest.startswith("@") and not targets:
            R.console.print("[yellow]ไม่เจอลูกน้องที่ระบุ — ดูรายชื่อด้วย /team[/yellow]")
            return True
        if not task:
            try:
                task = R.Prompt.ask("งานที่จะสั่งทีม").strip()
            except Exception:
                return True
            if not task:
                return True
        ready = []
        for s in targets:
            try:
                if not R.ensure_key(s["provider"], st.keys):
                    R.console.print(f"[yellow]ข้าม {s.get('name')}: ไม่มี key[/yellow]")
                    return True
                if not R.ensure_local_server(s["provider"]):
                    R.console.print(f"[yellow]ข้าม {s.get('name')}: local server ไม่พร้อม[/yellow]")
                    return True
            except Exception as e:
                R.console.print(f"[yellow]ข้าม {s.get('name')}: {e}[/yellow]")
                return True
            ready.append(s)
        if not ready:
            return True
        R.console.print(f"[bold green]สั่งงานพร้อมกัน {len(ready)} คน: {task}[/]")
        try:
            results = R.run_staff_tasks(ready, task, st.keys, st.cfg, st.temperature, st.auto_yes)
        except (R.TurnCancelled, KeyboardInterrupt):
            R.console.print("[dim](ยกเลิกแล้ว — รอให้ลูกน้องที่รับงานไปจบก่อน แล้วกลับมารอคำสั่ง)[/dim]")
            return True
        for r in results:
            head = f"{r.get('name')} ({r.get('provider')} / {r.get('model')})"
            if r.get("err"):
                R.console.print(f"[red]{head} ล้มเหลว: {r.get('err')}[/red]")
                _msg = R._handle_staff_error(team, r.get("staff") or {}, r.get("err"), st.keys, st.cfg)
                if _msg:
                    R.console.print(f"[dim]{_msg}[/dim]")
            elif not r.get("ans"):
                R.console.print(f"[yellow]{head}: {R.nothing_done_reason(r.get('msgs') or [])}[/yellow]")
            else:
                body = r["ans"] if len(r["ans"]) <= 2000 else r["ans"][:2000] + "\n... (ตัดให้สั้น)"
                R.console.print(Panel(Markdown(body), title=head, border_style="green"))
                if r.get("summary"):
                    R.console.print(f"[dim]{r['summary']}[/dim]")
        R.console.print(R.format_team_merge(results))
        return True
    if q.lower() == "/auto":
        st.cfg["auto_approve"] = not st.cfg.get("auto_approve", False)
        R.save_json(R.CONFIG_FILE, st.cfg)
        st.auto_yes = st.cfg["auto_approve"]
        R.console.print("[yellow]AUTO-APPROVE: เปิดแล้ว — ไม่ถาม y อีก (จำถาวร)[/yellow]"
                      if st.auto_yes else "[dim]ปิด auto-approve แล้ว (ถาม y/n เหมือนเดิม)[/dim]")
        return True
    if q.lower() == "/theme" or q.lower().startswith("/theme "):
        parts = q.split(None, 1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        if not arg:
            cur = R._ui_theme_name()
            arg = "classic" if cur == "luxe" else "luxe"
        picked = R._apply_ui_theme(arg)
        if not picked:
            R.console.print("[yellow]ใช้: /theme luxe|classic[/yellow]")
        else:
            R._COSMOS_MODE["on"] = None   # ให้ค่า animation อ่านใหม่ตาม config
            R.console.print(f"[green]ธีม UI = {picked}[/green]"
                          + (" [dim](เรียบหรู)[/dim]" if picked == "luxe"
                             else " [dim](นีออนเดิม)[/dim]"))
        return True
    if q.lower() == "/smart":
        st.cfg["smart"] = not st.cfg.get("smart", True)
        R.save_json(R.CONFIG_FILE, st.cfg)
        R.console.print("[green]SMART: เปิดแล้ว — ย่อประวัติเอง + ตรวจโค้ดเอง[/green]"
                      if st.cfg["smart"] else "[dim]ปิด smart แล้ว (ต้องสั่ง /sum /verify เอง)[/dim]")
        return True
    if q.lower() == "/boost" or q.lower().startswith("/boost "):
        parts = q.split(None, 1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        if not arg:
            picked = R.fuzzy_pick("เลือกโหมด boost:", [
                ("th", "th — เกลาภาษาไทยให้คม (ค่าเดิม)"),
                ("en", "en — แปลไทยเป็นอังกฤษตรงตัว (โมเดลไม่เก่งไทย)"),
                ("off", "off — ปิด ส่งตามที่พิมพ์"),
            ])
            if picked is None:
                # popup ใช้ไม่ได้ → สลับเปิด/ปิดแบบเดิม
                arg = "off" if R.boost_mode(st.cfg) != "off" else "th"
            elif picked == "":
                return True
            else:
                arg = picked
        if arg in ("en", "english", "อังกฤษ"):
            st.cfg["boost"] = "en"
        elif arg in ("th", "thai", "ไทย"):
            st.cfg["boost"] = "th"
        elif arg in ("off", "ปิด", "0", "false"):
            st.cfg["boost"] = False
        elif arg in ("on", "เปิด", "1"):
            st.cfg["boost"] = "th"
        else:
            R.console.print("[yellow]ใช้: /boost [th|en|off] (ว่าง = เลือกจากเมนู)[/yellow]")
            return True
        R.save_json(R.CONFIG_FILE, st.cfg)
        _bm = R.boost_mode(st.cfg)
        if _bm == "en":
            R.console.print("[green]BOOST-EN: เปิดแล้ว — แปลไทยเป็นอังกฤษตรงตัวก่อนส่ง (เหมาะกับโมเดลไม่เก่งไทย)[/green]")
        elif _bm == "th":
            R.console.print("[green]BOOST: เปิดแล้ว — เกลาพร้อมดิบให้อัตโนมัติ (! นำหน้าคือส่งดิบ)[/green]")
        else:
            R.console.print("[dim]ปิด boost แล้ว (ส่งตามที่พิมพ์)[/dim]")
        return True
    if q.lower() == "/effort" or q.lower().startswith("/effort "):
        parts = q.split(None, 1)
        lv = parts[1].strip().lower() if len(parts) > 1 else ""
        if not lv:
            picked = R.fuzzy_pick("Select effort:", [
                ("low", "low — คิดน้อย เร็ว+ถูก"),
                ("medium", "medium — สมดุล"),
                ("high", "high — คิดลึก ช้า+แพงหน่อย"),
                ("off", "off — ปิด (ปกติ)"),
            ])
            if picked is None:
                pass
            elif picked == "":
                return True
            else:
                lv = picked
        if lv in ("low", "medium", "high", "off"):
            st.cfg["effort"] = "" if lv == "off" else lv
            R.save_json(R.CONFIG_FILE, st.cfg)
        elif lv:
            R.console.print("[yellow]ใช้: low / medium / high / off[/yellow]")
        eff = st.cfg.get("effort", "")
        R.console.print(f"[magenta]reasoning effort: {eff or 'off (ปกติ)'}[/magenta]")
        return True
    if q.lower() == "/sessions":
        picked = R.sessions_dialog(R.list_sessions())
        if picked[0] == "resume":
            it = R.resolve_session(picked[1])
            if not it:
                R.console.print("[yellow]ไม่พบ session นั้น[/yellow]")
                return True
            R.maybe_reflect(st.provider, st.model, st.history, st.sid)
            st.provider, st.model = it["provider"], it["model"]
            st.history = R.load_session_messages(it["id"]) or []
            if st.cfg.get("system") and not any(m.get("role") == "system" for m in st.history):
                st.history.insert(0, {"role": "system", "content": st.cfg["system"]})
            st.sid = it["id"]
            R.touch_session(st.sid)
            _ttl = R.refresh_session_title(st.sid, st.provider, st.model,
                                            st.history) or it.get("name", "")
            R.console.print(Panel(f"[bold]{R.PROVIDERS[st.provider]['name']}[/bold] / {st.model}\n"
                                + (f"[bold]{_ttl}[/bold]\n" if _ttl else "")
                                + f"[dim]คุยต่อ session {st.sid}[/dim]",
                                title="SoonAI chat", border_style="cyan"))
            _replay_history(st.history)
        elif picked[0] == "new":
            R.maybe_reflect(st.provider, st.model, st.history, st.sid)
            st.history = [m for m in st.history if m.get("role") == "system"]
            st.sid = None
            R.console.print("[dim](เริ่มบทสนทนาใหม่ — ของเดิมบันทึกไว้แล้ว)[/dim]")
            R.console.print(f"[dim]ปัจจุบัน: {R.current_summary(st.provider, st.model)}[/dim]")
        elif picked[0] == "unavailable":
            R.cmd_sessions(argparse.Namespace(action=None, target=None), st.keys, st.cfg)
        return True
    if q.lower() == "/new":
        R.maybe_reflect(st.provider, st.model, st.history, st.sid)
        st.history = [m for m in st.history if m.get("role") == "system"]
        st.sid = None
        R.console.print("[dim](เริ่มบทสนทนาใหม่ — ของเดิมบันทึกไว้แล้ว ดูด้วย /sessions)[/dim]")
        R.console.print(f"[dim]ปัจจุบัน: {R.current_summary(st.provider, st.model)}[/dim]")
        return True
    if q.lower() == "/save" or q.lower().startswith("/save "):
        parts = q.split(None, 1)
        nm = parts[1].strip() if len(parts) > 1 else ""
        st.sid = R.save_session(st.sid or R._session_id(), st.provider, st.model, st.history, name=nm)
        R.console.print(f"[green]บันทึก session {st.sid} แล้ว[/green]")
        return True
    if q.lower() == "/mcp" or q.lower().startswith("/mcp "):
        parts = q.split()
        sub2 = parts[1].lower() if len(parts) > 1 else "list"
        arg2 = parts[2] if len(parts) > 2 else ""
        if not R._MCP_OK:
            R.console.print("[red]ระบบ MCP ใช้ไม่ได้ (ไม่พบ mcp_client.py)[/red]")
            return True
        from mcp_client import hub as _hub
        if sub2 == "add":
            try:
                nm = R.Prompt.ask("ชื่อ server (A-Za-z0-9_-)").strip()
                cmdline = R.Prompt.ask("คำสั่ง + args (เช่น: npx -y @modelcontextprotocol/server-filesystem C:/Shop)").strip()
            except (EOFError, KeyboardInterrupt):
                R.console.print()
                return True
            import shlex
            try:
                bits = shlex.split(cmdline, posix=os.name != "nt")
            except Exception:
                bits = cmdline.split()
            if not nm or not bits:
                R.console.print("[yellow]ข้อมูลไม่ครบ ยกเลิก[/yellow]")
                return True
            R.console.print(_hub.add_server(nm, bits[0], bits[1:]))
            R.agent_tools(refresh=True)
        elif sub2 in ("rm", "on", "off", "test", "tools", "refresh", "list",
                      "install", "catalog"):
            R.cmd_mcp(argparse.Namespace(action=sub2, target=arg2, rest=[], env=[]),
                    st.keys, st.cfg)
        else:
            R.console.print("[dim]/mcp [list|catalog|install <ชื่อ>|tools|test|on|off|rm|"
                            "refresh|add] [ชื่อ][/dim]")
        return True
    if q.lower() == "/skills" or q.lower().startswith("/skills "):
        _, _, tail = q.partition(" ")
        bits = tail.split(None, 1)
        sub2 = bits[0].lower() if bits else "menu"
        arg2 = bits[1].strip() if len(bits) > 1 else ""
        force = bool(re.search(r"(^|\s)(--force|-f)(\s|$)", arg2))
        arg2 = re.sub(r"(^|\s)(--force|-f)(\s|$)", " ", arg2).strip()
        if sub2 in ("add", "install"):
            if not arg2:
                try:
                    arg2 = R.Prompt.ask("ชื่อ skill ในแคตตาล็อก/owner/repo/URL/โฟลเดอร์/.zip").strip()
                except (EOFError, KeyboardInterrupt):
                    R.console.print()
                    return True
            if not arg2:
                R.console.print("[yellow]ยกเลิก[/yellow]")
                return True
            ok, msg = R.install_skill(arg2, force=force)
            R.console.print(f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
            if ok:
                try:
                    R.agent_tools(refresh=True)
                except Exception:
                    pass
        elif sub2 in ("rm", "show", "list", "catalog", "all", "new", "menu",
                      "learning", "reset", "decline", "forget"):
            tgt = arg2.split(None, 1)[0] if arg2 else ""
            R.cmd_skills(argparse.Namespace(action=sub2, target=tgt, rest=[], force=force),
                       st.keys, st.cfg)
        elif sub2 in ("find", "search", "suggest"):
            web2 = bool(re.search(r"(^|\s)--web(\s|$)", arg2))
            inst2 = bool(re.search(r"(^|\s)--install(\s|$)", arg2))
            ai2 = bool(re.search(r"(^|\s)--ai(\s|$)", arg2))
            q2 = re.sub(r"(^|\s)--(web|install|ai)(\s|$)", " ", arg2).strip()
            if not q2 and sys.stdin.isatty():
                try:
                    q2 = R.Prompt.ask("อยากได้สกิลช่วยเรื่องอะไร? (Enter = ให้ AI ดูโปรเจกต์เอง)",
                                    default="").strip()
                except (EOFError, KeyboardInterrupt):
                    R.console.print()
                    return True
            R.skills_find_flow(st.provider, st.model, question=q2, web=web2,
                             install_now=inst2, force=force, use_ai=ai2)
        else:
            R.console.print("[dim]/skills [list|show|add|install|rm|catalog|all|new|"
                          "find|search|learning|reset|decline] [ชื่อ/คำค้น] "
                          "[--web] [--install] [--force][/dim]")
        return True
    if q.lower() == "/skill" or q.lower().startswith("/skill "):
        _, _, _sa = q.partition(" ")
        _web2 = bool(re.search(r"(^|\s)--web(\s|$)", _sa))
        _inst2 = bool(re.search(r"(^|\s)--install(\s|$)", _sa))
        _ai2 = bool(re.search(r"(^|\s)--ai(\s|$)", _sa))
        _q2 = re.sub(r"(^|\s)--(web|install|force|ai)(\s|$)", " ", _sa).strip()
        if not _q2 and sys.stdin.isatty():
            # โหมด pipe ไม่ถาม (กันกินบรรทัดถัดไปของ input) — ใช้โหมดให้ AI ดูโปรเจกต์แทน
            try:
                _q2 = R.Prompt.ask("อยากได้สกิลช่วยเรื่องอะไร? "
                                 "(Enter = ให้ AI ดูโปรเจกต์แล้วเสนอเอง)", default="").strip()
            except (EOFError, KeyboardInterrupt):
                R.console.print()
                return True
        try:
            R.skills_find_flow(st.provider, st.model, question=_q2, web=_web2, install_now=_inst2,
                             use_ai=_ai2)
        except (R.TurnCancelled, KeyboardInterrupt):
            R.console.print("[dim](ยกเลิก)[/dim]")
        return True
    if q.lower() == "/sum" or q.lower().startswith("/sum "):
        parts = q.split(None, 1)
        try:
            n = int(parts[1]) if len(parts) > 1 else 30
        except Exception:
            n = 30
        convo = [m for m in st.history if m.get("role") in ("user", "assistant")][-n:]
        text = R.build_transcript(convo)
        if len(text) < 20:
            R.console.print("[dim]ยังไม่มีอะไรให้สรุป[/dim]")
            return True
        tmp = [{"role": "system", "content": "สรุปบทสนทนาต่อไปนี้เป็นภาษาไทยให้แม่น: ประเด็นหลัก, ข้อสรุป/การตัดสินใจ, งานที่ค้างอยู่ ตอบสั้นกระชับ"},
               {"role": "user", "content": "สรุปบทสนทนานี้:\n\n" + text}]
        R.console.print("[bold green]สรุป:[/]")
        summary = R.show_reply(st.provider, st.model, tmp, 0.2, effort="")
        if summary:
            st.sid = R.save_session(st.sid or R._session_id(), st.provider, st.model, st.history)
            try:
                if R.Prompt.ask("ย่อประวัติเหลือแค่สรุปนี้ไหม?", choices=["y", "n"], default="n") == "y":
                    keep_sys = [m for m in st.history if m.get("role") == "system"]
                    st.history = keep_sys + [
                        {"role": "user", "content": R.COMPACT_MARK + "เหลือสรุปด้านล่าง)"},
                        {"role": "assistant", "content": summary}]
                    st.sid = R.save_session(st.sid, st.provider, st.model, st.history)
                    R.console.print("[dim](ย่อประวัติแล้ว)[/dim]")
            except (EOFError, KeyboardInterrupt):
                R.console.print()
        return True
    if q.lower() == "/verify":
        past = [m for m in st.history if m.get("role") in ("user", "assistant")]
        if len(past) < 2:
            R.console.print("[dim]ยังไม่มีคำตอบให้ทวนสอบ[/dim]")
            return True
        last_q = next((m.get("content", "") for m in reversed(past) if m.get("role") == "user"), "")
        last_a = next((m.get("content", "") for m in reversed(past) if m.get("role") == "assistant"), "")
        _v = R.verify_answer(st.provider, st.model, last_q, last_a)
        return True
    if q.lower() == "/resume" or q.lower().startswith("/resume "):
        parts = q.split(None, 1)
        ref = parts[1].strip() if len(parts) > 1 else "last"
        it = R.resolve_session(ref)
        if not it:
            R.console.print("[yellow]ไม่พบ session นั้น[/yellow]")
            return True
        st.provider, st.model = it["provider"], it["model"]
        st.history = R.load_session_messages(it["id"]) or []
        if st.cfg.get("system") and not any(m.get("role") == "system" for m in st.history):
            st.history.insert(0, {"role": "system", "content": st.cfg["system"]})
        st.sid = it["id"]
        R.touch_session(st.sid)
        _ttl = R.refresh_session_title(st.sid, st.provider, st.model,
                                       st.history) or it.get("name", "")
        R.console.print(Panel(f"[bold]{R.PROVIDERS[st.provider]['name']}[/bold] / {st.model}\n"
                            + (f"[bold]{_ttl}[/bold]\n" if _ttl else "")
                            + f"[dim]คุยต่อ session {st.sid}[/dim]",
                            title="SoonAI chat", border_style="cyan"))
        _replay_history(st.history)
        return True
    if q.lower() == "/model":
        m2 = R.pick_model(st.provider, st.keys)
        if m2:
            st.model = m2
            st.cfg["model"] = m2
            R.save_json(R.CONFIG_FILE, st.cfg)
            R.console.print(f"[green]เปลี่ยนเป็น: {st.model}[/green]")
            R.console.print(f"[dim]ปัจจุบัน: {R.current_summary(st.provider, st.model)}[/dim]")
        return True
    if q.lower() == "/providers":
        R.cmd_providers(st.args, st.keys, st.cfg)
        return True
    if q.lower() == "/init" or q.lower().startswith("/init "):
        try:
            R._cmd_init_chat(st.provider, st.model, st.keys, st.cfg)
        except (R.TurnCancelled, KeyboardInterrupt):
            R.console.print("[dim](ยกเลิกแล้ว — กลับมารอคำสั่ง)[/dim]")
        return True
    if q.lower() == "/review" or q.lower().startswith("/review "):
        try:
            R._cmd_review_chat(st.provider, st.model)
        except (R.TurnCancelled, KeyboardInterrupt):
            R.console.print("[dim](ยกเลิกแล้ว — กลับมารอคำสั่ง)[/dim]")
        return True
    if q.lower() == "/help":
        R.console.print(Panel("พิมพ์ [bold]/[/] จะมีรายการคำสั่งเด้งให้เลือกทันที (ลูกศร + Enter)\n"
                            "หรือกด Enter ทั้งที่พิมพ์แค่ / เพื่อเปิดเมนูลัด\n"
                            "/exit ออก · /clear ล้างประวัติ · /new เริ่มใหม่\n"
                             "/sum สรุปบทสนทนา (+ย่อประวัติ) · /verify ทวนสอบคำตอบล่าสุด\n"
                             "/test รันเทสต์โปรเจกต์ (ไม่ผ่าน = ส่งให้ agent แก้) · "
                             "/shell off|safe|on · /undo ย้อนไฟล์ · /diff · /usage · /tools\n"
                             "/commit ร่าง+commit ให้ (ไม่ push) · /pr ร่าง PR ให้\n"
                             "/skill <คําค้น> หาสกิลที่เหมาะ (เว้นว่าง = ให้ AI ดูโปรเจกต์ให้) · "
                             "/skills all ติดตั้งชุดแนะนํา\n"
                             "/choose [เรื่อง] แตกเป็นช้อย 6 ข้อ (ข้อ 6 พิมพ์เอง) เลือกแล้วส่งต่อเลย\n"
                             "/agi [เป้าหมาย] ตั้งเป้าแล้ว AI วางแผน+ทำ+ตรวจเอง (/agi auto on|off)\n"
                            "/smart เปิด/ปิดย่อประวัติ+ตรวจโค้ดอัตโนมัติ (ปกติเปิดอยู่)\n"
                             "/boost [th|en|off] ไทย/อังกฤษ/ปิด ว่าง=เมนู (! นำหน้าคือส่งดิบ)\n"
                            "/effort low|medium|high|off เร่ง reasoning โมเดล (เฉพาะค่ายที่รองรับ)\n"
                            "/model เปลี่ยนโมเดล (ในค่ายเดิม)\n"
                            "/provider เปลี่ยนค่าย (เช่น groq / gemini / openrouter) + เลือกโมเดลใหม่\n"
                            "/pull <ชื่อโมเดล> โหลดโมเดลใหม่มาใช้บนเครื่อง (เช่น /pull qwen3)\n"
                             "/agent เปิด/ปิดโหมดสั่งงานเครื่อง (สร้างไฟล์/โฟลเดอร์/รันคำสั่งได้)\n"
                             "/init ร่าง AGENTS.md ประจำโปรเจกต์ด้วย AI (agent จำเองทุกรอบ)\n"
                             "/review ให้ AI รีวิว diff ที่ยังไม่ commit + สรุปความเสี่ยง\n"
                             "[blue]— agent · ทีมงานลูกน้อง —[/]\n"
                             "[blue]/hire จ้างลูกน้อง · /team ดูทีม · /fire ไล่ออก · /tell สั่งงาน · /tellall สั่งทั้งทีมพร้อมกัน[/]\n"
                             "/auto เปิด/ปิดอนุมัติอัตโนมัติ (ไม่ต้องกด y จำถาวร)\n"
                             "/mcp ดู/ต่อ MCP servers (tools เสริมให้ agent)\n"
                             "/skills ดู/ติดตั้ง skills เสริม (SKILL.md มาตรฐาน)\n"
                             "/providers ดูรายชื่อค่ายทั้งหมด", title="Help", border_style="magenta"))
        return True
    if q.lower() == "/pull" or q.lower().startswith("/pull "):
        parts = q.split(None, 1)
        mname = parts[1].strip() if len(parts) > 1 else R.Prompt.ask(
            "ชื่อโมเดล (เช่น qwen3, llama3.1, deepseek-r1, gemma3)").strip()
        if mname:
            if R.cmd_pull(argparse.Namespace(model=mname), st.keys, st.cfg) == 0:
                if R.Prompt.ask(f"ตั้ง {mname} เป็นโมเดลหลักเลยไหม?",
                              choices=["y", "n"], default="y") == "y":
                    st.cfg["provider"] = "ollama"
                    st.cfg["model"] = mname
                    R.save_json(R.CONFIG_FILE, st.cfg)
                    st.provider, st.model = "ollama", mname
                    st.history = [m for m in st.history if m.get("role") == "system"]
                    R.console.print(f"[green]ใช้ {mname} แล้ว[/green]")
        return True
    if q.lower() == "/provider":
        newp = R.switch_provider(st.keys, st.cfg)
        if newp:
            st.provider, st.model = newp
            st.history = [m for m in st.history if m.get("role") == "system"]
            R.console.print(Panel(f"[bold]{R.PROVIDERS[st.provider]['name']}[/bold] / {st.model}\n"
                                "[dim]เปลี่ยนค่ายแล้ว ล้างประวัติให้ใหม่[/dim]",
                                title="SoonAI chat", border_style="cyan"))
        return True
    return False


def _replay_history(history, limit=6):
    """โชว์บทสนทนาล่าสุดตอน resume — เดิมโหลดเข้า memory เฉย ๆ ไม่โชว์
    ผู้ใช้เลยนึกว่าแชทเก่าไม่กลับมา"""
    msgs = [m for m in history or []
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            and str(m.get("content") or "").strip()
            and not str(m.get("content") or "").startswith(R.COMPACT_MARK)]
    if not msgs:
        return
    tail = msgs[-limit:]
    skipped = len(msgs) - len(tail)
    note = f" · ตัดข้างบน {skipped} ข้อความ" if skipped else ""
    R.console.print(f"[dim]── ย้อนดูบทสนทนาล่าสุด ({len(msgs)} ข้อความ{note}) ──[/dim]")
    for m in tail:
        text = str(m.get("content") or "").strip()
        if len(text) > 400:
            text = text[:400] + " …"
        if m.get("role") == "user":
            R.console.print(Text(f"> {text}", style="cyan"))
        else:
            R.console.print(Text(text, style="dim"))
    R.console.print("[dim]── จบการย้อนดู ──[/dim]")


def cmd_chat(args, keys, cfg):
    """ห้องแชท (ทางเข้าเดิมของ CLI) — bootstrap → ลูปอ่านคำสั่ง → ส่งงานโมเดล"""
    st = ChatState(args, keys, cfg)
    if sys.stdin.isatty():
        # โหมด debug เปิดอยู่ = โชว์สรุปว่า exception ถูกกลืนซ้ำที่จุดไหนบ้าง (จาก log ที่ค้าง)
        # เฉพาะตอนคุยกับคน (ไม่พิมพ์ใส่ pipe/โหมดเครื่องอ่าน output)
        for _line in _DBG.startup_lines():
            R.console.print(_line, style="dim", highlight=False)
        try:
            _um = R.check_update(st.cfg)
            if _um:
                R.update_popup(st.cfg, _um)
        except Exception as e:
            _DBG.log_swallowed(e, "chat.py:cmd_chat", "ตรวจอัปเดตตอนเปิดห้องไม่สำเร็จ")
    st.provider = st.args.provider or st.cfg.get("provider", "ollama")
    if st.provider not in R.PROVIDERS:
        R.console.print(f"[red]ไม่รู้จัก provider: {st.provider}[/red]")
        return 1
    if not R.ensure_key(st.provider, st.keys):
        return 1
    if not R.ensure_local_server(st.provider):
        return 1
    st.sid = None
    resume_ref = getattr(st.args, "resume", None)
    if resume_ref:
        it = R.resolve_session(resume_ref)
        if not it:
            R.console.print("[yellow]ไม่พบ session นั้น — ดูรายการด้วย soonai sessions[/yellow]")
            return 1
        st.provider, st.model = it["provider"], it["model"]
        st.history = R.load_session_messages(it["id"]) or []
        if st.cfg.get("system") and not any(m.get("role") == "system" for m in st.history):
            st.history.insert(0, {"role": "system", "content": st.cfg["system"]})
        R.attach_memory(st.history)
        st.sid = it["id"]
        R.touch_session(st.sid)
        st.model = R.ensure_model_valid(st.provider, st.model, st.keys)
        if not st.model:
            return 1
        _ttl = R.refresh_session_title(st.sid, st.provider, st.model,
                                       st.history) or it.get("name", "")
        R.console.print(f"[green]คุยต่อ session {st.sid} ({len([m for m in st.history if m.get('role') == 'user'])} รอบ)[/green]")
        if _ttl:
            R.console.print(f"[dim]หัวข้อ: {_ttl}[/dim]")
        _replay_history(st.history)
    else:
        st.model = R.resolve_model(st.provider, st.args.model, st.keys,
                              free_only=st.args.free_only, search=st.args.search)
        if not st.model:
            return 1
        st.model = R.ensure_model_valid(st.provider, st.model, st.keys)
        if not st.model:
            return 1
        st.history = []
        if st.cfg.get("system"):
            st.history.append({"role": "system", "content": st.cfg["system"]})
        R.attach_memory(st.history)
    st.agent = bool(getattr(st.args, "agent", False))
    st.auto_yes = bool(getattr(st.args, "yes", False) or st.cfg.get("auto_approve", False))
    R._ACCESS["level"] = None
    R._ALLOWED_CMDS.clear()
    st.effort = (getattr(st.args, "effort", "") or st.cfg.get("effort", "") or "").strip().lower()
    if st.effort not in R.EFFORT_BUDGET:
        st.effort = ""
    if not getattr(st.args, "no_boot", False):
        R.boot_sequence(st.keys, st.cfg, st.provider, st.model)
    if not getattr(st.args, "no_banner", False) and st.cfg.get("show_banner", True):
        R.show_banner(R.PROVIDERS[st.provider]['name'], st.model)
    auto_tag = " · [yellow]AUTO[/yellow]" if st.auto_yes else ""
    eff_tag = f" · [magenta]⚡{st.effort}[/magenta]" if st.effort else ""
    try:
        _cwd = str(Path.cwd())
    except Exception:
        _cwd = "."
    R.console.print(Panel(f"[bold]{R.PROVIDERS[st.provider]['name']}[/bold] / {st.model}{auto_tag}{eff_tag}\n"
                        f"[dim]ที่ทำงาน: {_cwd} (agent สร้างไฟล์ตรงนี้ถ้าไม่บอกที่อื่น)[/dim]\n"
                        "[dim]พิมพ์ / มีคำสั่งเด้งให้เลือก · /agent สั่งงานเครื่อง · /auto ไม่ต้องกด y · /help[/dim]",
                        title="SoonAI chat", border_style="cyan"))
    try:
        _have_skills = bool(R.scan_skills())
    except Exception:
        _have_skills = True
    if not _have_skills:
        R.console.print("[dim]ยังไม่มี skills — ติดตั้งชุดแนะนําทันที: [bold]/skills all[/bold] "
                      "(หรือดูรายการ: /skills catalog)[/dim]")
    use_live_input = sys.stdin.isatty()
    st.ptk_session = None
    if use_live_input:
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import Completer, Completion
            from prompt_toolkit.history import InMemoryHistory
            from prompt_toolkit.styles import Style

            class _SlashCompleter(Completer):
                def get_completions(self, document, complete_event):
                    word = document.text_before_cursor
                    for cmd, desc in R.slash_suggestions(word):
                        yield Completion(cmd, start_position=-len(word),
                                         display_meta=desc)

            st.ptk_session = PromptSession(history=InMemoryHistory(),
                                        completer=_SlashCompleter(),
                                        style=Style.from_dict({"": "#00e5ff bold"}))
        except Exception:
            st.ptk_session = None
    st.ptk_history = None
    try:
        from prompt_toolkit.history import InMemoryHistory as _IMH
        st.ptk_history = _IMH()
    except Exception:
        st.ptk_history = None
    while True:
        R.paint_pinned_input(st.provider, st.model, st.agent, st.auto_yes, st.effort)
        try:
            q = read_input(st).strip()
        except (EOFError, KeyboardInterrupt):
            R.console.print()
            R.maybe_reflect(st.provider, st.model, st.history, st.sid)
            break
        if not q:
            continue
        if q == "/" or q.lower() in ("/menu", "menu"):
            q = R.show_command_menu()
            if not q:
                continue
        st.q = q
        _cmd = handle_command(st, q)
        if _cmd == EXIT:            # /exit · /quit · exit · quit
            break
        if _cmd:
            continue
        q = st.q            # คำสั่งอาจแก้คำถามไว้ให้ไหลต่อ (เช่น /choose · /test)
        if (not st.agent and sys.stdin.isatty() and R.fileop_intent(q)):
            _agi_fired = False
            if st.cfg.get("agi_auto", True) and R._agi_auto_heuristic(q):
                try:
                    if R.agi_should_auto(st.provider, st.model, q):
                        R.console.print("[dim](เข้าโหมด AGI ให้แล้ว — วางแผนเอง ทำเอง ตรวจเอง)[/dim]")
                        _agi_turn(st, q)
                        _agi_fired = True
                except (EOFError, KeyboardInterrupt):
                    R.console.print()
                    _agi_fired = True
                except Exception as e:
                    R.console.print(f"[dim](AGI อัตโนมัติใช้ไม่ได้: {e} — ถามแบบปกติ)[/dim]")
            if not _agi_fired:
                try:
                    if R.Prompt.ask("งานนี้ต้องสั่งงานเครื่อง เปิดโหมด agent เลยไหม?",
                                  choices=["y", "n"], default="y") == "y":
                        st.agent = True
                        R.console.print("[dim](เปิด agent ให้แล้ว)[/dim]")
                except (EOFError, KeyboardInterrupt):
                    R.console.print()
                    pass
        if q.startswith("!"):
            q = q[1:].strip()
            if not q:
                continue
        elif not q.startswith("/") and not st.agent and R.boost_mode(st.cfg) != "off" and sys.stdin.isatty():
            _bm = R.boost_mode(st.cfg)
            if R.boost_worth_it(q, _bm):
                try:
                    # สปินเนอร์ + วินาทีนับ — ให้เห็นว่ากำลังเกลาคำถาม (ไม่ค้างเงียบ)
                    enhanced = R.run_with_spinner(
                        "กำลังเตรียมคำถาม…",
                        R.boost_prompt, st.provider, st.model, q, _bm)
                except (R.TurnCancelled, KeyboardInterrupt):
                    R.console.print("[dim](ยกเลิกแล้ว — กลับมารอคำสั่ง)[/dim]")
                    continue
                if enhanced and enhanced != q:
                    if _DBG.enabled():
                        R.console.print(f"[dim]พร้อมที่ปรับแล้ว: {enhanced}[/dim]")
                    q = enhanced
        st.history.append({"role": "user", "content": q})
        R.console.print(Text(f"> {q}", style="cyan"))
        R.console.print(Text.assemble(("AI [", "bold green"), (R.short_model(st.model), "bold green"),
                                    ("]:", "bold green")))
        if st.agent:
            msgs = R._agent_msgs(st.history)
            _force_tools = bool(R._FORCE_TOOLS["on"])
            R._FORCE_TOOLS["on"] = False
            try:
                ans, err, _u, _info = R.agent_chat(st.provider, st.model, msgs, st.temperature,
                                          auto_yes=st.auto_yes,
                                          expect_tools=R.fileop_intent(q) or _force_tools,
                                          force_first=R.fileop_intent(q) or _force_tools,
                                          on_text=lambda t: R.console.print(Markdown(t)))
            except (R.TurnCancelled, KeyboardInterrupt):
                st.history.pop()
                R.console.print("[dim](ยกเลิกแล้ว — กลับมารอคำสั่ง)[/dim]")
                continue
            if err:
                R.console.print(f"[red]{err}[/red]")
                st.history.pop()
                _migrated = R.maybe_migrate_model(st.provider, st.model, err, st.keys, st.cfg)
                if _migrated:
                    st.model = _migrated
                elif "429" in err:
                    _rot = R.offer_rotation(st.provider, st.model, st.keys, st.cfg)
                    if _rot:
                        st.model = _rot
            elif ans:
                st.model = R.apply_model_switch(st.provider, st.model, st.keys, st.cfg,
                                           (_info or {}).get("model_switch"))
                st.history.append({"role": "assistant", "content": ans})
                _sum = R.agent_summary_line(_info)
                if _sum:
                    R.console.print(f"[dim]{_sum}[/dim]")
                if st.cfg.get("smart", True) and "```" in ans:
                    try:
                        R.verify_answer(st.provider, st.model, q, ans)
                    except (R.TurnCancelled, KeyboardInterrupt):
                        R.console.print("[dim](ข้ามการตรวจ)[/dim]")
                st.history = R.auto_compact_history(st.provider, st.model, st.history)
                st.sid = R.save_session(st.sid or R._session_id(), st.provider, st.model, st.history)
                R.refresh_session_title(st.sid, st.provider, st.model, st.history)
                st.history = st.history[-21:]
            else:
                R.console.print(R.nothing_done_reason(msgs))
                st.history.pop()
            continue
        try:
            # แนบ hint MCP บนสำเนาก่อนส่ง — st.history ที่บันทึก session ห้ามมี hint ค้างข้ามเทิร์น
            _send = list(st.history)
            R._ensure_mcp_hint(_send)
            ans = R.show_reply(st.provider, st.model, _send, st.temperature, effort=st.effort)
        except (R.TurnCancelled, KeyboardInterrupt):
            st.history.pop()
            R.console.print("[dim](ยกเลิกแล้ว — กลับมารอคำสั่ง)[/dim]")
            continue
        if ans:
            st.model = R.apply_model_switch(st.provider, st.model, st.keys, st.cfg)
            st.history.append({"role": "assistant", "content": ans})
            if st.cfg.get("smart", True) and "```" in ans:
                try:
                    R.verify_answer(st.provider, st.model, q, ans)
                except (R.TurnCancelled, KeyboardInterrupt):
                    R.console.print("[dim](ข้ามการตรวจ)[/dim]")
            st.history = R.auto_compact_history(st.provider, st.model, st.history)
            st.sid = R.save_session(st.sid or R._session_id(), st.provider, st.model, st.history)
            R.refresh_session_title(st.sid, st.provider, st.model, st.history)
            st.history = st.history[-21:]
        else:
            st.history.pop()
            if R.LAST_SEND_ERROR:
                _migrated = R.maybe_migrate_model(st.provider, st.model, R.LAST_SEND_ERROR, st.keys, st.cfg)
                if _migrated:
                    st.model = _migrated
                elif "429" in R.LAST_SEND_ERROR:
                    _rot = R.offer_rotation(st.provider, st.model, st.keys, st.cfg)
                    if _rot:
                        st.model = _rot
            else:
                R.console.print(R.nothing_done_reason(st.history))
    return 0
