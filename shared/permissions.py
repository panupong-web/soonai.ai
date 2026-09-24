# -*- coding: utf-8 -*-
"""Permission Layer สำหรับ Computer Use — security boundary ที่บังคับในโค้ด

สถาปัตยกรรม: AI -> run_tool -> gate() -> computer.py (ห้ามเรียกตรง)
ทุก action ต้องผ่าน: Permission Check -> Scope Check -> Safety Check
-> Execute -> Log (+ Verify อยู่ใน agent prompt loop)

ค่าเริ่มต้น DENY: ไม่มี permission = ห้ามควบคุม, ไม่มี scope = ห้ามเข้าถึง
AI เพิ่ม permission ให้ตัวเองไม่ได้ (ไม่มี tool grant + เขียนไฟล์สิทธิ์ถูกบล็อกในโค้ด)

โมดูลนี้ standalone (ไม่ import soonai) รับ ctx จาก caller:
  ctx = {"level":..., "approval":..., "grant_until":..., "scope":{...}, "fg":{exe,title,class}}
"""
import json
import re
import time
from pathlib import Path

import debug as _DBG    # โหมด debug: บันทึก traceback ของ exception ที่ถูกกลืน

LEVELS = ("off", "read_only", "interact", "full")
APPROVALS = ("auto", "ask_risky", "confirm_all")

READ_TOOLS = {"computer_screenshot", "computer_windows", "computer_uielements",
              "computer_ocr", "computer_wait"}
ACTION_MOUSE = {"computer_click", "computer_double_click", "computer_right_click",
                "computer_move", "computer_drag", "computer_scroll"}
ACTION_KEYS = {"computer_type", "computer_press", "computer_hotkey"}
ACTION_FOCUS = {"computer_focus"}
ACTION_TOOLS = ACTION_MOUSE | ACTION_KEYS | ACTION_FOCUS
COMPUTER_TOOLS = READ_TOOLS | ACTION_TOOLS | {"computer_vision"}
# Vision exports the current screen to an external model, so it must obey the
# same foreground-window policy as an action even though it does not click.
WINDOW_SCOPED_READ_TOOLS = {"computer_vision"}

# tool -> capability ที่ต้องมีใน scope
TOOL_CAP = {}
TOOL_CAP.update({t: "screen" for t in
                 ("computer_screenshot", "computer_windows", "computer_uielements",
                  "computer_ocr", "computer_vision")})
TOOL_CAP.update({t: "mouse" for t in ACTION_MOUSE})
TOOL_CAP.update({t: "keyboard" for t in ACTION_KEYS})
# computer_focus ไม่ผูก capability ใด — ใช้กฎ level>=interact ข้างล่างแทน
# computer_wait ไม่ผูก capability ใด (แค่หน่วงเวลา)

TERMINAL_EXES = {"windowsterminal.exe", "powershell.exe", "pwsh.exe", "cmd.exe",
                 "wt.exe", "alacritty.exe", "wezterm-gui.exe", "conemu64.exe",
                 "windowsterminal.exe", "terminus.exe"}
BROWSER_EXES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
                "opera.exe", "vivaldi.exe", "arc.exe", "chromium.exe"}
SETTINGS_EXES = {"systemsettings.exe", "control.exe", "mmc.exe", "regedit.exe",
                 "regedt32.exe", "secpol.msc", "gpedit.msc"}

SCOPE_DEFAULTS = {"screen": True, "mouse": True, "keyboard": True,
                  "browser": True, "terminal": False, "filesystem": "deny",
                  "system_settings": False,
                  "apps_allow": [], "apps_deny": [],
                  "windows_allow": [], "regions": []}


def default_policy():
    """นโยบายเริ่มต้น: ปิดหมด (DENY)"""
    return {"level": "off", "approval": "ask_risky", "grant_until": 0,
            "scope": dict(SCOPE_DEFAULTS)}


def normalize_policy(raw):
    """รวม config ผู้ใช้กับค่า default (ไม่พังถ้าไฟล์แหว่ง)"""
    p = default_policy()
    try:
        r = dict(raw or {})
    except Exception:
        return p
    if r.get("level") in LEVELS:
        p["level"] = r["level"]
    if r.get("approval") in APPROVALS:
        p["approval"] = r["approval"]
    try:
        p["grant_until"] = float(r.get("grant_until") or 0)
    except Exception:
        p["grant_until"] = 0
    try:
        sc = dict(r.get("scope") or {})
    except Exception:
        sc = {}
    for k, v in SCOPE_DEFAULTS.items():
        if k in sc:
            if k in ("apps_allow", "apps_deny", "windows_allow", "regions"):
                p["scope"][k] = sc[k] if isinstance(sc[k], list) else v
            elif k == "filesystem":
                p["scope"][k] = sc[k] if sc[k] in ("deny", "project", "allow") else v
            else:
                p["scope"][k] = bool(sc[k])
    return p


def grant_active(pol, now=None):
    """permission ยังมีผลไหม (หมดเวลา = revoke อัตโนมัติ)"""
    try:
        if (pol or {}).get("level", "off") == "off":
            return False, "ไม่มี permission (ค่าเริ่มต้น DENY — เปิดใน config computer.level)"
        gu = float((pol or {}).get("grant_until") or 0)
        if gu > 0 and (now or time.time()) >= gu:
            return False, "permission หมดเวลาแล้ว (revoke อัตโนมัติ)"
        return True, ""
    except Exception:
        return False, "อ่าน permission ไม่ได้"


def _match_any(text, patterns):
    t = str(text or "").lower()
    for p in patterns or []:
        if p and str(p).lower() in t:
            return str(p)
    return ""


def _fg_cat(fg):
    """จำแนกหน้าต่างโฟกัส: browser/terminal/settings/other/unknown"""
    exe = str((fg or {}).get("exe") or "").lower()
    if not exe:
        return "unknown"
    if exe in TERMINAL_EXES:
        return "terminal"
    if exe in BROWSER_EXES:
        return "browser"
    if exe in SETTINGS_EXES:
        return "settings"
    return "other"


def _fg_open(scope):
    """scope เปิดกว้างทุกแอปจริงไหม (เปิดกว้าง = fg ว่างก็แตะได้ · จำกัดอะไรไว้ = fail-closed)"""
    try:
        sc = scope or {}
        return bool(sc.get("browser", False) and sc.get("terminal", False)
                    and sc.get("system_settings", False)
                    and not sc.get("apps_allow") and not sc.get("windows_allow")
                    and not sc.get("apps_deny"))
    except Exception:
        return False


def _in_regions(x, y, regions):
    if not regions:
        return True, ""
    try:
        fx, fy = float(x), float(y)
    except Exception:
        return False, "พิกัดไม่ใช่ตัวเลข"
    for rc in regions:
        try:
            rx, ry = float(rc.get("x", 0)), float(rc.get("y", 0))
            rw, rh = float(rc.get("w", 1000)), float(rc.get("h", 1000))
        except Exception:
            continue
        if rx <= fx <= rx + rw and ry <= fy <= ry + rh:
            return True, ""
    return False, "พิกัดอยู่นอก region ที่อนุญาต"


def _points_of(tool, args):
    """ดึงจุด (x,y) ที่ action จะแตะ (click/move/drag) — ไม่มี = []"""
    a = args if isinstance(args, dict) else {}
    pts = []

    def _pt(x, y):
        try:
            return (float(x), float(y))
        except Exception:
            return None

    if tool in ("computer_click", "computer_double_click", "computer_right_click",
                "computer_move"):
        p = _pt(a.get("x"), a.get("y"))
        if p:
            pts.append(p)
    elif tool == "computer_drag":
        for k in (("x1", "y1"), ("x2", "y2")):
            p = _pt(a.get(k[0]), a.get(k[1]))
            if p:
                pts.append(p)
    return pts


# รูปแบบ secret (พิมพ์/ส่ง = high-risk + redact log)
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{8,}", r"gh[pousr]_[A-Za-z0-9]{8,}", r"xox[baprs]-[A-Za-z0-9-]{8,}",
    r"AKIA[0-9A-Z]{12,}", r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    r"(?i)\bapi[_-]?key\s*[:=]\s*\S{6,}", r"(?i)\bpassword\s*[:=]\s*\S{3,}",
    r"(?i)\btoken\s*[:=]\s*\S{6,}", r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*",
]
_SECRET_RES = None


def _secret_res():
    global _SECRET_RES
    if _SECRET_RES is None:
        _SECRET_RES = [re.compile(p) for p in SECRET_PATTERNS]
    return _SECRET_RES


def looks_secret(text):
    """ข้อความดูเหมือน secret หรือไม่"""
    try:
        s = str(text or "")
    except Exception:
        return False
    return any(rx.search(s) for rx in _secret_res())


# คำสั่ง run_cmd ที่ต้องบังคับ confirm เสมอ (แม้ auto_yes) — บล็อกจริงอยู่ใน sandbox
HIGH_RISK_RUN = [
    (r"\bdel\b", "ลบไฟล์ (del)"),
    (r"\berase\b", "ลบไฟล์ (erase)"),
    (r"\brd\b[^|&;]*/s", "ลบโฟลเดอร์ (rd /s)"),
    (r"\brm\b", "ลบไฟล์ (rm)"),
    (r"\bremove-item\b", "ลบไฟล์/โฟลเดอร์ (Remove-Item)"),
    (r"\bshred\b|\bdd\b", "ทำลายข้อมูล (shred/dd)"),
    (r"\bshutdown\b|\brestart-computer\b|\bstop-computer\b", "ปิด/รีสตาร์ทเครื่อง"),
    (r"netsh\b[^\n]*firewall|advfirewall|New-NetFirewallRule|Remove-NetFirewallRule", "เปลี่ยน firewall"),
    (r"\bufw\b|\biptables\b", "เปลี่ยน firewall"),
    (r"\bnet\s+user\b|\bnet\s+localgroup\b|\busermod\b|\buseradd\b|\bdscl\b", "เปลี่ยนสิทธิ์ผู้ใช้"),
    (r"chmod\s+[47]77|chmod\s+-R\s*777|\bchown\b", "เปลี่ยนสิทธิ์ไฟล์ระบบ"),
    (r"Set-MpPreference|Set-MpThreat|reg\s+(add|delete)\b", "เปลี่ยน security settings/registry"),
    (r"secpol|gpedit", "เปลี่ยน security policy"),
    (r"winget\s+install|choco\s+install|scoop\s+install|pip\s+install|npm\s+(i|install)\s+-g", "ติดตั้งซอฟต์แวร์"),
    (r"Send-MailMessage|SendGrid|mail\s+-s\b", "ส่งอีเมล/ข้อความ"),
    (r"\bscp\b|\brsync\b|curl[^\n]*(-T\s|--upload-file|--data-binary)|pscp\b", "อัปโหลดไฟล์"),
    (r"Invoke-WebRequest[^\n]*-Method\s+(Post|Put)[^\n]*-InFile|Invoke-RestMethod[^\n]*-InFile", "อัปโหลดไฟล์"),
]
_HIGH_RISK_RES = None


def _high_risk_res():
    global _HIGH_RISK_RES
    if _HIGH_RISK_RES is None:
        _HIGH_RISK_RES = [(re.compile(p, re.I), why) for p, why in HIGH_RISK_RUN]
    return _HIGH_RISK_RES


def high_risk_run_reason(command):
    """คืนเหตุผลถ้าคำสั่ง run_cmd เข้าข่าย high-risk (ต้อง confirm)"""
    try:
        s = str(command or "")
    except Exception:
        return ""
    for rx, why in _high_risk_res():
        try:
            if rx.search(s):
                return why
        except Exception:
            pass
    return ""


def is_high_risk(tool, args):
    """(bool, เหตุผล) — action นี้ต้องบังคับ confirm ไหม"""
    a = args if isinstance(args, dict) else {}
    if tool == "computer_vision":
        return True, "จะส่งภาพหน้าจอไปวิเคราะห์กับผู้ให้บริการ AI ภายนอก"
    if tool == "computer_type" and looks_secret(a.get("text", "")):
        return True, "ข้อความเหมือน secret (key/token/รหัส) — ยืนยันก่อนพิมพ์ + ไม่บันทึก"
    if tool == "computer_press" and str(a.get("key", "")).strip().lower() in ("delete", "del"):
        return True, "ปุ่ม Delete อาจลบข้อมูล"
    if tool == "computer_hotkey":
        try:
            keys = [str(k).strip().lower() for k in (a.get("keys") or [])]
        except Exception:
            keys = []
        if keys == ["alt", "f4"]:
            return True, "Alt+F4 ปิดหน้าต่าง (งานอาจหาย)"
        if "delete" in keys:
            return True, "hotkey มี Delete"
    if tool == "run_cmd":
        why = high_risk_run_reason(a.get("command", ""))
        if why:
            return True, why
    return False, ""


def evaluate(tool, args, pol, fg=None, now=None):
    """ประตูหลัก: Permission -> Scope -> Safety
    คืน {"allow":bool, "confirm":bool, "reason":str, "risk":str, "permission":str}"""
    pol = normalize_policy(pol)
    lvl = pol["level"]
    if tool not in COMPUTER_TOOLS:
        return {"allow": True, "confirm": False, "reason": "ไม่ใช่ computer tool",
                "risk": "none", "permission": lvl}
    ok, why = grant_active(pol, now)
    if not ok:
        return {"allow": False, "confirm": False, "reason": why,
                "risk": "denied", "permission": lvl}
    # READ_ONLY แตะได้แค่อ่านจอ — ห้าม mouse/keyboard/focus เด็ดขาด
    if lvl == "read_only" and tool in ACTION_TOOLS:
        return {"allow": False, "confirm": False,
                "reason": "READ_ONLY ทำได้แค่อ่านจอ (ห้าม mouse/keyboard)",
                "risk": "denied", "permission": lvl}
    # focus เปลี่ยน foreground — ต้อง INTERACT ขึ้นไป
    if tool in ACTION_FOCUS and lvl not in ("interact", "full"):
        return {"allow": False, "confirm": False,
                "reason": "ต้องมีสิทธิ์ INTERACT ขึ้นไป",
                "risk": "denied", "permission": lvl}
    a = args if isinstance(args, dict) else {}
    scope = pol["scope"]
    # 1) capability scope
    need = TOOL_CAP.get(tool)
    if need and not scope.get(need, False):
        return {"allow": False, "confirm": False,
                "reason": "scope ห้าม %s (เปิดใน config computer.scope)" % need,
                "risk": "denied", "permission": lvl}
    # 2) app/window scope: actions and externally exported vision are scoped.
    if tool in ACTION_TOOLS | WINDOW_SCOPED_READ_TOOLS:
        deny_hit = _match_any((fg or {}).get("exe", ""), scope.get("apps_deny")) or \
            _match_any((fg or {}).get("title", ""), scope.get("apps_deny"))
        if deny_hit:
            return {"allow": False, "confirm": False,
                    "reason": "แอปนี้อยู่ใน deny list (%s)" % deny_hit,
                    "risk": "denied", "permission": lvl}
        allow_list = scope.get("apps_allow") or []
        if allow_list:
            hit = _match_any((fg or {}).get("exe", ""), allow_list) or \
                _match_any((fg or {}).get("title", ""), allow_list)
            if not hit:
                return {"allow": False, "confirm": False,
                        "reason": "แอปนี้ไม่อยู่ใน allow list",
                        "risk": "denied", "permission": lvl}
        wallow = scope.get("windows_allow") or []
        if wallow:
            wtext = "%s %s" % ((fg or {}).get("title", ""), (fg or {}).get("class", ""))
            if not _match_any(wtext, wallow):
                return {"allow": False, "confirm": False,
                        "reason": "หน้าต่างนี้ไม่อยู่ใน windows_allow",
                        "risk": "denied", "permission": lvl}
        # 3) หมวดแอป (browser/terminal/settings)
        cat = _fg_cat(fg)
        if cat == "unknown" and not _fg_open(scope):
            return {"allow": False, "confirm": False,
                    "reason": "ระบุหน้าต่างโฟกัสไม่ได้และ scope จำกัดแอปไว้ "
                              "(fail-closed — ลองใหม่หรือเปิด scope ให้กว้างขึ้น)",
                    "risk": "denied", "permission": lvl}
        if cat == "browser" and not scope.get("browser", False):
            return {"allow": False, "confirm": False,
                    "reason": "scope ห้าม browser", "risk": "denied", "permission": lvl}
        if cat == "terminal" and not scope.get("terminal", False):
            return {"allow": False, "confirm": False,
                    "reason": "scope ห้าม terminal", "risk": "denied", "permission": lvl}
        if cat == "settings" and not scope.get("system_settings", False):
            return {"allow": False, "confirm": False,
                    "reason": "scope ห้าม system settings", "risk": "denied", "permission": lvl}
        # 4) region scope (เฉพาะ action ที่มีพิกัด)
        for (px, py) in _points_of(tool, a):
            inside, rwhy = _in_regions(px, py, scope.get("regions") or [])
            if not inside:
                return {"allow": False, "confirm": False,
                        "reason": "พิกัด (%.0f, %.0f) %s" % (px, py, rwhy or "อยู่นอก scope"),
                        "risk": "denied", "permission": lvl}
    # 5) safety: high-risk ต้อง confirm เสมอ
    risky, rwhy = is_high_risk(tool, a)
    if risky:
        return {"allow": True, "confirm": True, "reason": rwhy,
                "risk": "risky", "permission": lvl}
    if pol["approval"] == "confirm_all" and tool in ACTION_TOOLS:
        return {"allow": True, "confirm": True, "reason": "โหมด confirm ทุก action",
                "risk": "none", "permission": lvl}
    return {"allow": True, "confirm": False, "reason": "อยู่ใน scope",
            "risk": "none", "permission": lvl}


# ---------- audit (ไม่บันทึก secret/plaintext) ----------

def redact_args(tool, args):
    """ย่อ args สำหรับ audit log (type บันทึกแค่จำนวนตัวอักษร)"""
    try:
        a = dict(args) if isinstance(args, dict) else {}
    except Exception:
        return {}
    if tool == "computer_type":
        return {"chars": len(str(a.get("text", "")))}
    if tool == "computer_vision":
        p = str(a.get("prompt", "") or "")
        return {"prompt": p[:120], "provider": a.get("provider", ""),
                "model": a.get("model", "")}
    out = {}
    for k, v in a.items():
        s = str(v)
        out[k] = s[:200]
    return out


def audit_append(log_path, action, target="", app="", permission="", result="",
                 reason="", tool_args=None, tool=""):
    """เขียน audit 1 บรรทัด (JSONL) + หมุนไฟล์เมื่อเกิน ~1MB"""
    try:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = {"t": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "action": str(action or "")[:60],
                 "target": str(target or "")[:200],
                 "app": str(app or "")[:120],
                 "permission": str(permission or "")[:20],
                 "result": str(result or "")[:20],
                 "reason": str(reason or "")[:200],
                 "args": redact_args(tool, tool_args)}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:
            if p.stat().st_size > 1048576:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                p.write_text("\n".join(lines[-4000:]) + "\n", encoding="utf-8")
        except Exception as e:
            _DBG.log_swallowed(e, "permissions.py:audit_append",
                               "ตัด audit log ให้เล็กลงไม่ได้ — ไฟล์จะบวมขึ้น")
        return True
    except Exception as e:
        _DBG.log_swallowed(e, "permissions.py:audit_append",
                           f"เขียน audit log ไม่ได้ ({action}) — ไม่มีร่องรอยการอนุญาต")
        return False
