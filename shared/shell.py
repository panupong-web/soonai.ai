# -*- coding: utf-8 -*-
"""shell: โหมด shell ของ agent (allowlist · sandbox · runner · ตรวจคำสั่งเทสต์)

ย้ายมาจาก soonai.py (Step 1) — ตั้งแต่รอบ "ลด bind" การพึ่งโมดูลอื่นเหลือ 2 ทาง:
- ``import runtime as R`` แล้วอ่าน seam/state ด้วย **attribute access**
  (``R.load_config()``, ``R._SHELL_OVERRIDE``, ``R.CONFIG_FILE``, ``R.USAGE``)
  ห้าม ``from runtime import X`` เพราะค่าอาจถูก rebind ทีหลัง (facade mirror ให้)
- import โมดูลพี่น้องตรง ๆ เมื่อชื่อนั้นเป็นของโมดูลนั้นจริง ๆ
ผลคือ ``depgraph.py`` รายงาน bind_refs ของโมดูลนี้ = 0
"""
import os
import re
import json
import subprocess
from pathlib import Path

import debug as _DBG    # โหมด debug: บันทึก traceback ของ exception ที่ถูกกลืน
import runtime as R


# ชื่อไฟล์ที่ agent ห้ามแตะผ่าน shell ด้วยพาธ relative (กันการหลบเลี่ยงง่าย ๆ)
_SHELL_SENSITIVE_NAMES = ("keys.json", "mcp.json", "team.json", "memory.json",
                          "audit.log", "debug_last.json", "crash.log")
def _sensitive_shell_hit(cmd):
    """คืนชื่อไฟล์ secret ถ้าคำสั่ง shell ดูเหมือนเข้าไปแตะ (คืน '' ถ้าไม่)
    เป็นการตรวจแบบ best-effort: shell ที่เปิดใช้เองไม่มีการรับประกันเรื่อง secret
    (กันได้แค่การพิมพ์ชื่อไฟล์ตรง ๆ — ใช้ wildcard/ตัวแปลภาษาเพื่อหลบได้)"""
    low = str(cmd or "").lower().replace("\\", "/")
    if not low:
        return ""
    for p in R._sensitive_paths():
        if p and p in low:
            return os.path.basename(p)
    for name in _SHELL_SENSITIVE_NAMES:
        if name in low:
            return name
    # config.json กว้างเกินกว่าจะกันด้วยชื่อเดี่ยว ๆ — ต้องมี shared อยู่ด้วย
    if "config.json" in low and "shared" in low:
        return "config.json"
    if "sessions/" in low and any(x in low for x in ("soonai", "localappdata", "appdata")):
        return "sessions/"
    return ""
_MCP_WRITE_HINTS = ("write", "edit", "delete", "remove", "create", "mkdir",
                    "move", "copy", "put", "save", "rm", "unlink")
# ── โหมด shell ของ agent: off (ค่าเริ่มต้น) / safe (อ่าน-เทสต์เท่านั้น) / on (เต็ม) ──
# off  : agent รันคำสั่งไม่ได้เลย (งานเขียนไฟล์ยังทำได้)
# safe : รันได้เฉพาะคำสั่งที่อยู่ใน allowlist (git อ่าน, เทสต์/lint, ดูเวอร์ชัน) แบบคำสั่งเดียว
#        ไม่มี pipe/ตัวเชื่อม/redirect · env ถูกตัดความลับ · cwd = โฟลเดอร์งาน · timeout · จำกัด output
# on   : เปิดเต็มเหมือนเดิม (ยังมี sandbox_deny + ขออนุญาตทุกครั้ง) — ผู้ใช้รับความเสี่ยงเอง
SHELL_MODES = ("off", "safe", "on")
_SAFE_SHELL_RES = (
    r"^git\s+(status|diff|log|show|branch|remote|ls-files|ls-tree|describe|rev-parse|blame|shortlog|stash list)\b",
    r"^(python|py)\s+-m\s+(pytest|unittest|ruff|mypy|black|flake8|compileall|json\.tool)\b",
    r"^(pytest|ruff|mypy|black|flake8)\b",
    r"^(npm|pnpm|yarn|bun)\s+(test|run\s+(test|lint|typecheck|check|build|format))\b",
    r"^(go|cargo|dotnet|swift)\s+(test|build|check|vet)\b",
    r"^make\s+(test|check|build|lint)\b",
    r"^(python|py|node|go|cargo|java|javac|php|ruby|dotnet|rustc|tsc|git|npm|pip|uv)\s+(--version|-v|-V)$",
    r"^(where|which)\s+[A-Za-z0-9._-]+$",
    r"^(dir|ls|pwd|echo)\b",
)
_SHELL_METACHARS = "|;&><`$\n\r%!()"
def _shell_mode():
    """โหมด shell ของ agent — override เฉพาะเซสชัน > SOONAI_ALLOW_AGENT_SHELL=1 (ของเดิม) ถือเป็น 'on'
    > config agent.shell > 'off'"""
    if R._SHELL_OVERRIDE["mode"] in SHELL_MODES:
        return R._SHELL_OVERRIDE["mode"]
    env = os.environ.get("SOONAI_ALLOW_AGENT_SHELL", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return "on"
    try:
        mode = str((R.load_config().get("agent") or {}).get("shell") or "").strip().lower()
    except Exception:
        mode = ""
    return mode if mode in SHELL_MODES else "off"
def set_shell_mode(mode, cfg=None, persist=True):
    """ตั้งโหมด shell — จำลง config ด้วยหรือเฉพาะเซสชันนี้
    (persist=False ใช้กับ /test ที่ขอความสามารถชั่วคราว ไม่เปลี่ยนค่าถาวรของผู้ใช้)
    คืนโหมดใหม่ หรือ '' ถ้าโหมดไม่ถูกต้อง"""
    m = str(mode or "").strip().lower()
    if m not in SHELL_MODES:
        return ""
    R._SHELL_OVERRIDE["mode"] = m
    if persist:
        try:
            cfg = cfg if isinstance(cfg, dict) else R.load_config()
            cfg.setdefault("agent", {})["shell"] = m
            R.save_json(R.CONFIG_FILE, cfg)
            R._SHELL_OVERRIDE["mode"] = None   # config กลายเป็นแหล่งความจริงถาวรแล้ว
        except Exception as e:
            _DBG.log_swallowed(e, "shell.py:set_shell_mode",
                               f"จำโหมด shell '{m}' ลง config ไม่ได้ — ใช้เฉพาะเซสชันนี้")
    return m
def _safe_shell_ok(command):
    """คำสั่งนี้รันได้ในโหมด safe ไหม — ต้องเป็นคำสั่งเดียว ไม่มี pipe/ตัวเชื่อม/redirect/ตัวแปร"""
    c = str(command or "").strip()
    if not c or len(c) > 300:
        return False
    if "&&" in c or "||" in c or any(ch in c for ch in _SHELL_METACHARS):
        return False
    low = re.sub(r"\s+", " ", c).strip().lower()
    if low in _detected_test_commands():
        return True
    return any(re.search(pat, low) for pat in _SAFE_SHELL_RES)
def _safe_env():
    """env ขั้นต่ำของโปรเซสลูก — ตัด API key/ความลับออกทั้งหมด (shell จึงอ่านความลับจาก env ไม่ได้)"""
    keep = ("PATH", "PATHEXT", "SystemRoot", "WINDIR", "ComSpec", "SystemDrive", "TEMP", "TMP",
            "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
            "PROGRAMFILES(X86)", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
            "LANG", "LC_ALL", "TERM")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SOONAI_IN_SANDBOX"] = "1"
    return env
class _KillTree:
    """Windows Job Object: ปิด handle = ลูกและหลานที่ยังค้างตายทั้งหมด
    (ปิดช่องที่ subprocess.kill() ฆ่าได้แค่โปรเซสตรง ๆ — ลูกที่ fork ต่อจะค้าง)"""

    _JOB_EXT = 9        # JobObjectExtendedLimitInformation
    _KILL_ON_CLOSE = 0x2000

    def __init__(self):
        self.job = None
        self.k32 = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

            class _IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in
                            ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                             "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

            class _BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                            ("PerJobUserTimeLimit", ctypes.c_longlong),
                            ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class _EXT(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO_COUNTERS),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            job = k32.CreateJobObjectW(None, None)
            if not job:
                return
            info = _EXT()
            info.BasicLimitInformation.LimitFlags = self._KILL_ON_CLOSE
            if not k32.SetInformationJobObject(job, self._JOB_EXT, ctypes.byref(info),
                                               ctypes.sizeof(info)):
                k32.CloseHandle(job)
                return
            self.k32, self.job = k32, job
        except Exception:
            self.job = None

    def assign(self, proc):
        if not self.job:
            return
        try:
            import ctypes
            self.k32.AssignProcessToJobObject(self.job, ctypes.c_void_p(int(proc._handle)))
        except Exception:
            pass

    def close(self):
        if self.job:
            try:
                self.k32.CloseHandle(self.job)
            except Exception:
                pass
            self.job = None
def run_command_safe(command, timeout=120, cwd=None, max_output=3000):
    """รันคำสั่งอย่างมีขอบเขต: env ขั้นต่ำ · cwd = โฟลเดอร์งาน · timeout · ฆ่าทั้งต้นไม้ · จำกัด output
    คืน dict {code, out, timed_out, error}"""
    flags = 0x08000000 if os.name == "nt" else 0        # CREATE_NO_WINDOW
    try:
        cwd = str(cwd or R.workspace_root())
    except Exception:
        cwd = None
    job = _KillTree()
    try:
        proc = subprocess.Popen(str(command), shell=True, cwd=cwd, env=_safe_env(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                errors="replace", creationflags=flags)
    except Exception as e:
        job.close()
        return {"code": -1, "out": "", "timed_out": False, "error": str(e)[:200]}
    job.assign(proc)
    try:
        out, _ = proc.communicate(timeout=max(1, int(timeout)))
        return {"code": proc.returncode, "out": (out or "")[-int(max_output):],
                "timed_out": False, "error": ""}
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        # ปิด job ก่อนอ่าน output ที่เหลือ: ลูกหลานที่ยังถือ pipe อยู่จะตายทันที
        # (ถ้ารอ communicate ก่อน ท่อยังไม่ปิด จะค้างเต็ม 5 วินาทีทุกครั้งที่ timeout)
        job.close()
        try:
            out, _ = proc.communicate(timeout=5)
        except Exception:
            out = ""
        return {"code": -9, "out": (out or "")[-int(max_output):], "timed_out": True,
                "error": f"หมดเวลา {int(timeout)} วินาที (ฆ่าทั้งโปรเซสแล้ว)"}
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return {"code": -1, "out": "", "timed_out": False, "error": str(e)[:200]}
    finally:
        job.close()          # ปิด job = โปรเซสลูกที่ยังค้างตายทั้งหมด
def _looks_like_safe_test_cmd(cmd):
    """บรรทัด test: ในไฟล์กำกับโปรเจกต์เชื่อได้เฉพาะทรง test-runner มาตรฐาน
    (กัน repo แปลกปลอมฝังคำสั่ง arbitrary แล้วได้สิทธิ์ safe-mode ฟรี)"""
    c = re.sub(r"\s+", " ", str(cmd or "").strip().strip("`")).strip()
    if not c or len(c) > 300:
        return False
    if "&&" in c or "||" in c or any(ch in c for ch in _SHELL_METACHARS):
        return False
    return any(re.search(pat, c.lower()) for pat in _SAFE_SHELL_RES)
def _project_test_commands(root=None):
    """คำสั่งเทสต์ที่ตรวจได้ในโปรเจกต์ เรียงตามความน่าเชื่อถือ
    ใช้ทั้ง allowlist ของโหมด safe และ tool run_tests"""
    root = Path(root or R.workspace_root())
    key = str(root)
    if R._TEST_CMD_CACHE["key"] == key:
        return R._TEST_CMD_CACHE["cmds"]
    cmds = []
    # 1) ไฟล์กำกับของโปรเจกต์: บรรทัด "test: <คำสั่ง>" / "ทดสอบ: <คำสั่ง>"
    for fname in ("AGENTS.md", "CLAUDE.md", ".soonai.md"):
        try:
            f = root / fname
            if f.is_file():
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines()[:200]:
                    m = re.match(r"^\s*(?:tests?|ทดสอบ)\s*[:=]\s*(.+?)\s*$", line, re.I)
                    if not m or not m.group(1) or m.group(1).startswith("["):
                        continue
                    raw = m.group(1).strip().strip("`").strip()
                    if raw and _looks_like_safe_test_cmd(raw):
                        cmds.append(raw)
        except Exception:
            pass
    # 2) node: package.json → scripts.test (เลือกตัวจัดการแพ็กเกจตามไฟล์ lock)
    try:
        pj = root / "package.json"
        if pj.is_file():
            scripts = (json.loads(pj.read_text(encoding="utf-8")).get("scripts") or {})
            if scripts.get("test") and "no test specified" not in str(scripts["test"]):
                pm = "npm"
                for lock, name in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
                                   ("bun.lockb", "bun")):
                    if (root / lock).is_file():
                        pm = name
                        break
                cmds.append(f"{pm} test")
    except Exception:
        pass
    # 3) python
    try:
        if ((root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file()
                or (root / "setup.cfg").is_file() or (root / "tests").is_dir()
                or any(root.glob("test_*.py")) or any(root.glob("*_test.py"))):
            cmds.append("python -m pytest -q")
    except Exception:
        pass
    # 4) ภาษาอื่น ๆ ตามไฟล์โปรเจกต์
    for marker, cmd in (("go.mod", "go test ./..."), ("Cargo.toml", "cargo test")):
        try:
            if (root / marker).is_file():
                cmds.append(cmd)
        except Exception:
            pass
    try:
        if (root / "Makefile").is_file():
            cmds.append("make test")
        if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
            cmds.append("dotnet test")
    except Exception:
        pass
    clean = [c for c in cmds if c and not any(ch in c for ch in "|;&><`$\n\r%!")]
    R._TEST_CMD_CACHE["key"] = key
    R._TEST_CMD_CACHE["cmds"] = tuple(dict.fromkeys(clean))
    return R._TEST_CMD_CACHE["cmds"]
def _detected_test_commands():
    try:
        return set(_project_test_commands())
    except Exception:
        return set()
def detect_test_command(root=None, index=0):
    """คำสั่งเทสต์ของโปรเจกต์ตัวที่ index ('' = ไม่เจอ)"""
    cmds = _project_test_commands(root)
    try:
        return cmds[int(index)] if cmds else ""
    except Exception:
        return ""
def run_tests_command(command="", timeout=600):
    """รันเทสต์ของโปรเจกต์ (หรือคำสั่งที่ผู้ใช้ระบุ) ผ่าน sandbox runner คืน (ข้อความ, ผ่าน?) """
    cmd = str(command or "").strip() or detect_test_command()
    if not cmd:
        return ("ERROR: ไม่พบคำสั่งเทสต์ของโปรเจกต์นี้ — ระบุเองได้ด้วย run_tests {\"command\": \"...\"}"
                " หรือเขียนบรรทัด 'test: <คำสั่ง>' ไว้ใน AGENTS.md", False)
    why = sandbox_deny(cmd) or _sensitive_shell_hit(cmd)
    if why:
        return f"ERROR: บล็อกคำสั่งเทสต์ที่น่าสงสัย: {why}", False
    res = run_command_safe(cmd, timeout=timeout, max_output=4000)
    ok = res["code"] == 0 and not res["timed_out"]
    head = f"$ {cmd}\n" if ok else f"$ {cmd}\nexit={res['code']}\n"
    if res["timed_out"]:
        head += "[" + res["error"] + "]\n"
    elif res["error"]:
        head += "[" + res["error"] + "]\n"
    out = head + res["out"]
    return out, ok
def _agent_shell_enabled():
    """Shell is an explicit, user-owned opt-in, never implied by --yes.

    A general shell can read files by aliases, wildcards, interpreters, or
    redirection, so it cannot be made a trustworthy secret boundary with a
    blacklist.  Keep it off unless the interactive user deliberately enables
    it in their process environment.
    """
    return _shell_mode() == "on"
def _compile_deny():
    """รวม regex คำสั่งทำลายระบบ (compile ครั้งเดียว)"""
    import re
    pats = [
        (r":\(\)\s*\{", "fork bomb"),
        (r"\bmkfs\b", "ฟอร์แมตดิสก์ (mkfs)"),
        (r"\bformat\s+[a-z]:", "ฟอร์แมตไดรฟ์ (format)"),
        (r"\bdel\b[^|&;]*/s[^|&;]*c:\\(windows|program files|programfiles|users|system32|\*|\s|$)", "ลบไฟล์ระบบ (del /s)"),
        (r"\b(rd|rmdir)\b[^|&;]*/s[^|&;]*c:\\(windows|program files|programfiles|users|system32|\*|\s|$)", "ลบโฟลเดอร์ระบบ (rd /s)"),
        (r"remove-item\b(?=[^|&;]*-recurse)(?=[^|&;]*c:\\(windows|program files|programfiles|users|system32|\*|\s|$))[^|&;]*", "ลบไฟล์ระบบ (Remove-Item -Recurse)"),
        (r"\bshutdown\s+/[sr]\b", "ปิด/รีสตาร์ทเครื่อง (shutdown)"),
        (r"\bstop-computer\b", "ปิดเครื่อง (Stop-Computer)"),
        (r"\brestart-computer\b", "รีสตาร์ทเครื่อง (Restart-Computer)"),
        (r"\breg\s+delete\s+hk(lm|cc|cr)\b", "ลบรีจิสทรีระบบ (reg delete)"),
        (r"\btakeown\b[^|&;]*c:\\", "ยึดไฟล์ระบบ (takeown)"),
        (r"\bicacls\s+c:\\", "แก้สิทธิ์ไฟล์ระบบ (icacls)"),
        (r"\bbcdedit\b", "แก้ boot config (bcdedit)"),
        (r"\bvssadmin\s+delete", "ลบ shadow copy (vssadmin)"),
        (r"\bwbadmin\s+delete", "ลบข้อมูลสำรอง (wbadmin)"),
        (r"\bcipher\s+/w:", "ล้างข้อมูลถาวร (cipher /w)"),
        (r"\bnet\s+user\b[^|&;]*/add\b", "สร้างยูสเซอร์ (net user /add)"),
        (r"\bchmod\b[^|&;]*\s777\s+/", "เปิดสิทธิ์ทั้งระบบ (chmod 777 /)"),
        (r"\bchown\s+-[a-z]*r[a-z]*\s+\S+\s+/", "เปลี่ยนเจ้าของทั้งระบบ (chown -R /)"),
        (r"powershell.*\s-e(nc\w*)?\s+[A-Za-z0-9+/=]{32,}", "รัน payload เข้ารหัส (powershell -enc)"),
    ]
    return [(re.compile(p, re.I), why) for p, why in pats]
_DENY_RES = _compile_deny()
_DENY_SYSROOTS = ("/", "/*", "~", "~/*", "$home", "${home}", "%systemdrive%\\",
                  "c:\\", "c:/", "c:\\*", "c:/*", "\\", "\\*", "/.")
def _rm_rf_root(low):
    """rm ที่มี -r และ -f พร้อมเป้าเป็นรากระบบ (คืน True = อันตราย)"""
    import re
    n = re.sub(r"\s+", " ", low or "").strip()
    for m in re.finditer(r"(?:^|[;&|])\s*(?:sudo\s+)?rm\s+(.*?)(?=[;&|]|$)", n):
        rest = (m.group(1) or "").strip()
        if not rest:
            continue
        toks = rest.split()
        flags = [t for t in toks if t.startswith("-")]
        targets = [t.strip("'\"") for t in toks
                   if not t.startswith("-") and t != "--"]
        if "--no-preserve-root" in flags:
            return True
        has_r = any("r" in f.lstrip("-").lower() or "R" in f.lstrip("-")
                    or f.lower() == "--recursive" for f in flags)
        has_f = any("f" in f.lstrip("-").lower() or f.lower() == "--force"
                    for f in flags)
        if has_r and has_f and any(t in _DENY_SYSROOTS for t in targets):
            return True
    return False
def sandbox_deny(command):
    """กันคำสั่ง shell ระดับทำลายเครื่อง (คืนเหตุผลภาษาไทย หรือ '' = ผ่าน)
    ใช้ทั้ง approve() (บล็อกแม้ auto_yes) และ run_tool() (กันชั้นที่สอง)"""
    import re
    c = str(command or "")
    if not c.strip():
        return ""
    low = c.lower()
    for rx, why in _DENY_RES:
        try:
            if rx.search(c):
                return why
        except Exception:
            pass
    try:
        if _rm_rf_root(low):
            return "ลบทั้งระบบ (rm -rf /)"
    except Exception:
        pass
    try:
        if re.search(r"\bdd\b.*\bof\s*=", c, re.I) and ("/dev/" in low or "\\\\.\\" in c):
            return "เขียนทับดิสก์โดยตรง (dd)"
    except Exception:
        pass
    return ""
