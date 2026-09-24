# -*- coding: utf-8 -*-
"""
ศูนย์ AI — แชท AI ง่าย ๆ ผ่าน CLI

🚀 เริ่มใช้งาน:
  soonai              → เปิดห้องแชท (ใช้ได้เลยถ้าตั้งค่าแล้ว)
  soonai --agent      → ห้องแชทสั่งงานเครื่องได้
  soonai --resume     → คุยต่อรอบล่าสุด

📋 คำสั่งอื่น ๆ:
  soonai setup        → ตั้งค่าครั้งแรก (เลือกค่าย + ใส่ key)
  soonai providers    → ดูค่าย AI ทั้งหมด
  soonai models       → ดูโมเดลที่มี
"""
import argparse
import json
import os
import re
import shutil
import sys
import threading
import time
import types
import urllib.parse
from pathlib import Path

# Add shared folder to path
sys.path.insert(0, str(Path(__file__).parent / "shared"))

if os.name == "nt":
    try:
        import ctypes
        # หมายเหตุ: os.system("chcp 65001") ไม่มีผลกับ console ตัวจริง
        # เพราะรันใน child process — ต้องสั่ง kernel ตรง ๆ
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
# บังคับ UTF-8 ทั้งโปรเซส (กันไทยเพี้ยนเป็น ???? / mojibake ใน sessions/*.json)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
except Exception:
    pass

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner

from providers import (PROVIDERS, is_free_model, price_tier, price_str, model_label, get_key,
                       apply_custom_providers)

try:
    import symbols as _symbols_mod
    from symbols import CODE_SUFFIXES, SYMBOL_MAX_FILES, SYMBOL_MAX_PER_FILE, _JS_SYMBOL_RE, _GO_SYMBOL_RE, file_symbols, outline_text, _symbol_map_enabled, _attach_symbol_map  # noqa: F401
except Exception:
    _symbols_mod = None
try:
    import project as _project_mod
    from project import _expand_known_folders, _resolve_tool_path, SNAP_IGNORE, project_snapshot, MEMORY_FILENAMES, find_agents_files, project_memory, _attach_project_memory, INIT_HINT_FILES, collect_init_context, HEAVY_DIRS, IGNORE_FILES, MAX_SCAN_FILES, _ignore_patterns, _ignored_rel, iter_project_files  # noqa: F401
except Exception:
    _project_mod = None

try:
    import usage as _usage_mod
    from usage import EFFORT_BUDGET, est_tokens, messages_tokens, usage_reset, _pricing_cached, estimate_cost, usage_note, _track_usage, usage_line, context_budget, fit_messages  # noqa: F401
except Exception:
    _usage_mod = None
try:
    import shell as _shell_mod
    from shell import SHELL_MODES, _SAFE_SHELL_RES, _SHELL_METACHARS, _shell_mode, set_shell_mode, _safe_shell_ok, _safe_env, _KillTree, run_command_safe, _project_test_commands, _detected_test_commands, detect_test_command, run_tests_command, _agent_shell_enabled, _compile_deny, _DENY_RES, _DENY_SYSROOTS, _rm_rf_root, sandbox_deny, _SHELL_SENSITIVE_NAMES, _sensitive_shell_hit, _MCP_WRITE_HINTS  # noqa: F401
except Exception:
    _shell_mod = None

try:
    import skills as _skills_mod
    from skills import (  # noqa: F401
        SKILL_DIRNAME, _SKILLS_TEST_ROOTS, skills_dirs, parse_skill_md, skill_name_ok,
        load_skill_meta, scan_skills, read_skill_text, _ensure_skills_hint,
        _collect_skill_candidates, _safe_extract_zip, SKILL_CATALOG, skill_catalog_md,
        skill_catalog_names, is_catalog_skill, skill_catalog_table, install_catalog_skill,
        install_catalog_all, _git_source_parts, _looks_like_git, _stage_skill_git,
        _stage_skill_url, _stage_skill_source, install_skill, SKILL_SEARCH_SYNONYMS,
        _skill_search_terms, SKILL_SEARCH_STOP, _skill_score, search_catalog,
        search_github_skills, project_facts, _project_deps, SKILL_ADVISOR_SYSTEM,
        parse_skill_suggestions, ai_suggest_skills, SKILL_DECLINE_LIMIT, SKILL_FREQUENT_USE,
        _SKILL_STATE, _SKILL_CARRYOVER, _skill_state, _skill_state_save, _skill_decline_limit,
        skill_decline_count, skill_is_declined, skill_use_count, skill_used_often,
        skill_usage_boost, record_skill_decline, record_skill_use, block_skill,
        reset_skill_learning, skill_learning_table, frequent_skills_missing, carryover_skills,
        _SKILL_AUTOSUGGEST, _skill_suggest_enabled, skill_suggestions_for_task,
        _hint_use_skill, autosuggest_skill, skills_find_flow, remove_skill, skills_table,
        SKILL_TEMPLATE, scaffold_skill, skills_install_menu, cmd_skills)
except Exception:
    _skills_mod = None


try:
    from mcp_client import (hub as _MCP_HUB, agent_mcp_tools as _agent_mcp_tools,
                            call_mcp_tool as _call_mcp_tool, split_mcp_name as _split_mcp_name,
                            compact_tool_defs as _compact_mcp_tool_defs)
    _MCP_OK = True
except Exception:
    _MCP_HUB = None
    _MCP_OK = False

try:
    import permissions as _PERM
    _PERM_OK = True
except Exception:
    _PERM = None
    _PERM_OK = False

try:
    import ui_theme as _UI
    _UI_OK = True
except Exception:
    _UI = None
    _UI_OK = False


# เลเยอร์ UI/เรนเดอร์ (Step 3) — ตาราง/แบนเนอร์/กรอบอินพุต/บรรทัดสถานะ
try:
    import ui_render as _ui_render_mod
    from ui_render import (  # noqa: F401
    LOGO,
    _hex,
    neon,
    _rainbow_line,
    _rainbow_logo,
    _thai_attach,
    _clusters,
    welcome_popup,
    boot_sequence,
    show_banner,
    set_term_title,
    neo_table,
    rgb_hex,
    COSMOS_STARS,
    COSMOS_FAMILIES,
    COSMOS_TITLE,
    COSMOS_COMET,
    COSMOS_GLOW_R,
    _cosmos_on,
    _cosmos_hash,
    _unhex,
    _cosmos_fade,
    _cosmos_nebula,
    _cosmos_cell,
    _cosmos_edge,
    _cosmos_word,
    _input_style,
    INPUT_STYLE,
    build_input_bar,
    SLASH_COMMANDS,
    slash_suggestions,
    show_command_menu,
    short_model,
    _record_tools,
    _diff_stat_line,
    _status_extras,
    status_line,
    slow_statusline,
    current_summary,
    _term_width,
    _dwidth,
    box_title,
    input_box_top,
    locked_box_text,
    input_box_bottom,
    )
except Exception:
    _ui_render_mod = None

# ลูปห้องแชท + ตัวจัดการคำสั่ง "/" (Step 5) — โมดูล chat อ่าน seam ของ soonai
# ผ่าน `import runtime` (attribute access) จึงไม่มีการ bind ชื่อข้ามโมดูล
try:
    import chat as _chat_mod
    from chat import cmd_chat
except Exception:                    # pragma: no cover - กันไฟล์หาย/พัง
    _chat_mod = None

    def cmd_chat(args, keys, cfg):
        """fallback: โหลดโมดูล chat ไม่ได้ → แจ้งแล้วออก (CLI ยังไม่พังทั้งตัว)"""
        console.print("[red]โมดูล chat ใช้ไม่ได้ (ไม่พบ shared/chat.py)[/red]")
        return 1


# โหมด debug — เก็บ traceback ของ exception ที่ถูกกลืนลงไฟล์ log + หมุนไฟล์อัตโนมัติ
# (ปิดอยู่ = ไม่แตะดิสก์เลย · เปิดด้วย SOONAI_DEBUG=1 · ดู shared/debug.py)
try:
    import debug as _DBG
except Exception:                      # pragma: no cover - กันไฟล์หาย/พัง
    class _NoDebug:
        """fallback: ไม่มี shared/debug.py → กลืนเงียบเหมือนเดิม แต่ crash.log ยังถูกเขียน"""

        @staticmethod
        def enabled():
            return False

        @staticmethod
        def install_hooks():
            return False

        @staticmethod
        def note(*_a, **_k):
            return False

        @staticmethod
        def log_swallowed(*_a, **_k):
            return False

        @staticmethod
        def log_crash(text, where=""):
            try:
                (BASE_DIR / "crash.log").write_text(text, encoding="utf-8")
                return True
            except Exception:
                return False

    _DBG = _NoDebug()


# ── UI พื้นฐาน: ธีมสี + computer mod + tolerant stdio + console ──────────────
def _ui_theme_name():
    """ชื่อธีม UI จาก config (ค่าเริ่มต้น 'luxe' · 'classic' = นีออนเดิม)
    อ่านไฟล์ตรง ๆ เพราะถูกเรียกตอนสร้าง console (ก่อน load_config พร้อม)"""
    try:
        raw = json.loads((Path(__file__).parent / "shared" / "config.json")
                         .read_text(encoding="utf-8"))
        return str((raw.get("ui") or {}).get("theme") or "luxe").strip().lower()
    except Exception:
        return "luxe"


def _apply_ui_theme(name):
    """สลับธีม UI (luxe = เรียบหรู · classic = นีออนเดิม) + บันทึก config + สร้าง console ใหม่
    คืนชื่อธีมที่ใช้ หรือ '' ถ้าไม่ถูกต้อง"""
    global console
    name = str(name or "").strip().lower()
    if name not in ("luxe", "classic", "เรียบหรู", "นีออน"):
        return ""
    name = "classic" if name in ("classic", "นีออน") else "luxe"
    try:
        cfg = load_config()
        cfg.setdefault("ui", {})["theme"] = name
        save_json(CONFIG_FILE, cfg)
    except Exception:
        pass
    try:
        console = Console(legacy_windows=False,
                          theme=(_UI.console_theme(name) if _UI_OK else None))
    except Exception:
        pass
    return name


def _computer_mod():
    """โหลดโมดูล computer แบบ lazy (ไม่มีไฟล์ = error นุ่ม ๆ ไม่พัง CLI)"""
    try:
        import computer as _c
        return _c, ""
    except Exception as e:
        return None, f"ERROR: โมดูล computer ใช้ไม่ได้: {e}"

load_dotenv()


class _TolerantStdIO:
    """ห่อ stdout/stderr กัน crash Errno 22 บน Windows console (rich flush)
    กลืนเฉพาะ EINVAL — error อื่นยัง raise เหมือนเดิม"""

    def __init__(self, inner):
        self._inner = inner

    def _swallowable(self, e):
        return isinstance(e, OSError) and getattr(e, "errno", None) == 22

    def write(self, s):
        try:
            return self._inner.write(s)
        except OSError as e:
            if not self._swallowable(e):
                raise
            return len(s) if isinstance(s, str) else 0

    def writelines(self, lines):
        try:
            return self._inner.writelines(lines)
        except OSError as e:
            if not self._swallowable(e):
                raise

    def flush(self):
        try:
            return self._inner.flush()
        except OSError as e:
            if not self._swallowable(e):
                raise

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _tolerant_stdio():
    """ห่อ stdio ทั้งคู่ (เรียกครั้งเดียวตอนเข้า main — เทสต์เรียกฟังก์ชันตรงไม่โดน)"""
    import sys as _sys
    try:
        if not isinstance(_sys.stdout, _TolerantStdIO):
            _sys.stdout = _TolerantStdIO(_sys.stdout)
        if not isinstance(_sys.stderr, _TolerantStdIO):
            _sys.stderr = _TolerantStdIO(_sys.stderr)
    except Exception:
        pass

# ธีมกลาง: โทนเรียบหรู (remap ชื่อสีทั้ง CLI) · สลับเป็น 'classic' ได้ใน config ui.theme
console = Console(legacy_windows=False,
                  theme=(_UI.console_theme(_ui_theme_name()) if _UI_OK else None))

# path พื้นฐาน: นิยามที่ runtime (ให้โมดูลย่อย import ได้เอง ไม่ต้อง bind)
# แล้วดึงกลับมาใช้ชื่อเดิม — ทุกโมดูลจึงชี้ที่ object เดียวกัน
from runtime import BASE_DIR, CONFIG_FILE, KEYS_FILE, SHARED_DIR  # noqa: E402,F401


# ── ค่าคงที่โมดูล: DATA_DIR/VERSION + system prompts ทั้งหมด + AGENT_TOOLS ──────
def _data_dir():
    """โฟลเดอร์ข้อมูลระดับเครื่อง (sessions อยู่เครื่องใครเครื่องมัน ไม่ปนกับโปรเจค)"""
    try:
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(base) / "SoonAI"
        return Path.home() / ".soonai"
    except Exception:
        return BASE_DIR


DATA_DIR = _data_dir()
# ไฟล์ความเคยชินของสกิล (อยู่ที่นี่เพราะพึ่ง DATA_DIR) — โมดูล skills อ่านผ่าน bind
SKILL_STATE_FILE = (Path(os.environ["SOONAI_SKILL_STATE"]) if os.environ.get("SOONAI_SKILL_STATE")
                    else DATA_DIR / "skills_state.json")   # ทับด้วย env ได้ (ทดสอบ/ซิงก์ความจำ)
SESSIONS_DIR = DATA_DIR / "sessions"
TEAM_FILE = SHARED_DIR / "team.json"
MAX_STAFF = 5
VERSION = "2.32.0"
DEFAULT_SYSTEM = "คุณคือผู้ช่วย AI ภาคภาษาไทย ตอบกระชับ ชัดเจน"
# กฎจัดการข้อความกำกวม/ต้านคำตอบมั่ว (แชทปกติ + agent + ทีม) — เคสจริงที่พบ:
# ผู้ใช้พิมพ์สั้น ๆ ว่า "ใช้ mcp ดิ" แล้วโมเดลเดาเป็น Roblox พร้อมอ้างพาธ
# %LOCALAPPDATA%\Roblox\mcp.bat ที่ไม่มีอยู่จริง + ตอบวนเป็นชุดคำถามโดยไม่ให้สาระ
CLARIFY_RULES = (
    "เมื่อข้อความผู้ใช้สั้น/กำกวม (เช่น พิมพ์แค่คำว่า 'mcp'): ห้ามเลือกความหมายเอง "
    "ให้ถามชี้แจงสั้น ๆ 1 ครั้งพร้อมทางเลือกที่เป็นรูปธรรม — เรื่อง mcp เสนอ 2 ทาง: "
    "(ก) ระบบ MCP ของ SoonAI เอง (ดู soonai mcp catalog · ติดตั้ง soonai mcp install <ชื่อ> · "
    "ในแชทใช้ /mcp) (ข) MCP ทั่วไปของ client อื่น เช่น Claude/Cursor — ถ้าใช่ให้ถามว่าใช้ "
    "client ตัวไหนและต้องการเชื่อมต่อ service/API อะไร "
    "ห้ามอ้างไฟล์ โฟลเดอร์ พาธ โปรแกรม หรือบริการใด ๆ ที่ไม่ได้เห็นจริงจาก tools "
    "หรือบริบทที่ระบบแนบมา (ห้ามเดาพาธเฉพาะเครื่อง เช่น %LOCALAPPDATA%\\...) "
    "ทุกคำตอบต้องแนบสาระ/ข้อมูลที่เป็นประโยชน์อย่างน้อย 1 ส่วนควบคู่กับคำถาม "
    "รวมคำถามที่จำเป็นทั้งหมดไว้ในรอบเดียว ห้ามตอบวนเป็นชุดคำถามเรื่อย ๆ")
CLARIFY_MARKER = "ถามชี้แจงสั้น ๆ 1 ครั้ง"  # ใช้ตรวจว่า system prompt มีกฎนี้แล้วหรือยัง

LEGACY_QUALITY_SYSTEM = ("คุณคือผู้ช่วย AI ภาคภาษาไทยที่แม่นยำและตรงประเด็น "
                  "ตอบกระชับชัดเจนเป็นภาษาไทย (คงศัพท์เทคนิคอังกฤษไว้) "
                  "เรื่องข้อเท็จจริงตอบเฉพาะสิ่งที่มั่นใจ ถ้าไม่แน่ใจให้บอกตรง ๆ ว่าห้ามเดา "
                  "เรื่องโค้ดใช้เฉพาะ API/ไลบรารี/ฟังก์ชันที่มีอยู่จริง ห้ามสมมติชื่อ ตรวจ syntax ก่อนตอบทุกครั้ง "
                  "เขียนโค้ดได้ทุกภาษาบนโลกไม่จำกัด ถ้าผู้ใช้ไม่ระบุภาษาให้เลือกภาษาที่เหมาะกับงานที่สุด "
                  "สรุปจับประเด็นหลักก่อนเสมอแล้วค่อยลงรายละเอียด")  # ค่า default เก่าที่เคยเซฟลง config (ใช้ตรวจ migration)

QUALITY_SYSTEM = LEGACY_QUALITY_SYSTEM + " " + CLARIFY_RULES
AGENT_SYSTEM = ("คุณคือ coding agent สั่งงานเครื่องของผู้ใช้ได้ด้วย tools: "
                "glob/grep/read_file (สำรวจโค้ด) + make_dir/write_file/edit_file (สร้าง/แก้) "
                "+ list_dir/run_cmd (ตรวจ/รัน) "
                "+ outline (ดูโครงสร้างไฟล์แบบมีเลขบรรทัด) + run_tests (รันชุดเทสต์ของโปรเจกต์) "
                "งานไฟล์ในโปรเจกต์ใช้ tools ในเครื่องก่อน (list_dir/read_file/glob/grep/outline) "
                "tools เสริมนอกเครื่อง (mcp__*) ถูกซ่อนไว้ — ต้องใช้ค่อยเรียก mcp_tools ครั้งเดียวก่อน ห้ามเดาชื่อเอง "
                "ขั้นตอน: ดูแผนที่โปรเจกต์ที่ระบบแนบมาให้ก่อน แล้วค่อยสำรวจเพิ่มเฉพาะจุดที่ต้องใช้ "
                "ใช้ outline แทนการเปิดอ่านไฟล์ยาว ๆ เมื่อยังไม่รู้ว่าสัญลักษณ์อยู่บรรทัดไหน "
                "ถ้าผู้ใช้ถามหาสกิล/งานที่ควรมีสกิลช่วย ให้เรียก search_skills แล้วบอกชื่อ+คำสั่งติดตั้ง "
                "ถ้างานที่ทําตรงกับสกิลในแคตตาล็อกที่ยังไม่ติดตั้ง ให้เสนอผู้ใช้แล้วติดตั้งด้วย "
                "install_skill (ระบบจะถามอนุญาต) แล้วอ่าน read_skill ก่อนลงมือ "
                "ถ้าผลค้นบอกว่าผู้ใช้เคยปฏิเสธสกิลไหน ห้ามเสนอซ้ำและห้ามติดตั้งเอง "
                "เรียก tools หลายตัวพร้อมกันในรอบเดียวเมื่อไม่ขึ้นต่อกัน "
                "(เช่น สร้างหลายโฟลเดอร์/อ่านหลายไฟล์/เขียนหลายไฟล์ที่ไม่เกี่ยวกัน) "
                "แก้เป็นจุดด้วย edit_file (อย่าเขียนทั้งไฟล์ถ้าไม่จำเป็น) "
                "เมื่อผู้ใช้ขอให้สร้าง/เขียน/แก้ไขไฟล์หรือโฟลเดอร์ ให้เรียก tool ทันที "
                "ถ้าผู้ใช้ไม่บอกที่ตั้ง ให้ทำในโฟลเดอร์โปรเจกต์ปัจจุบัน (พาธ . หรือ relative) เสมอ "
                "ห้ามเดาพาธ absolute เอง ใช้ run_cmd เฉพาะเมื่อจำเป็นจริง ๆ "
                 "ถ้าเรียก function calling ตรง ๆ ไม่ได้ ให้เขียนแต่ละคำสั่งในบล็อก ```tool "
                 'เช่น ```tool {"name": "make_dir", "arguments": {"path": "C:/Shop"}} ``` '
                 "ขอบเขตปลอดภัย: ทำงานในโฟลเดอร์โปรเจกต์ปัจจุบันเป็นหลัก "
                 "ไฟล์นอกโฟลเดอร์ต้องขออนุญาตก่อนเสมอ "
                 "ห้ามรันคำสั่งทำลายระบบ (ลบทั้งไดรฟ์/ฟอร์แมต/fork bomb/payload เข้ารหัส) "
                 + CLARIFY_RULES)

# ระบบเลือกภาษาโค้ดอัตโนมัติ: เขียนได้ทุกภาษาบนโลก ไม่จำกัด
# (งาน, ภาษาแนะนำ, นามสกุล, วิธีรัน) — agent เลือกตามงานเมื่อผู้ใช้ไม่ระบุ
LANG_TABLE = [
    ("สคริปต์อัตโนมัติทั่วไป", "Python", ".py", "python app.py"),
    ("สคริปต์เฉพาะ Windows", "PowerShell", ".ps1", "powershell -File app.ps1"),
    ("สคริปต์ Linux/mac", "Bash", ".sh", "bash app.sh"),
    ("เว็บหลังบ้าน/API", "Python (FastAPI)", ".py", "uvicorn app:app"),
    ("เว็บหน้าเว็บโต้ตอบ", "TypeScript", ".ts", "npx vite"),
    ("CLI ทูลแจกจ่ายง่าย", "Go", ".go", "go run ."),
    ("งานระบบ/ประสิทธิภาพสูง", "Rust", ".rs", "cargo run"),
    ("ข้อมูล/AI/ML", "Python", ".py", "python train.py"),
    ("แอป Android", "Kotlin", ".kt", "gradle run"),
    ("แอป iOS/macOS", "Swift", ".swift", "swift run"),
    ("แอปเดสก์ท็อป", "Python", ".py", "python app.py"),
    ("เกม", "C#", ".cs", "dotnet run"),
    ("ฝังตัว/IoT", "C/C++", ".cpp", "arduino-cli compile"),
    ("เว็บคงที่/เอกสาร", "HTML+JS", ".html", "เปิดด้วยเบราว์เซอร์"),
]


def _lang_guide():
    """เรนเดอร์ตาราง + กฎเลือกภาษา ต่อท้าย AGENT_SYSTEM"""
    rows = "\n".join(f"- {job}: {lang} ({ext}, รัน: {run})"
                     for job, lang, ext, run in LANG_TABLE)
    return ("\nภาษาโค้ด: เขียนได้ทุกภาษาบนโลก ไม่จำกัดภาษา "
            "เลือกอัตโนมัติตามงานดังนี้:\n" + rows +
            "\nกฎ: 1) ผู้ใช้ระบุภาษา = ใช้ตามนั้นเสมอ "
            "2) มีโปรเจคอยู่แล้ว = ใช้ภาษาเดิมของโปรเจค (ดู AGENTS.md/ไฟล์เดิม) "
            "3) ไม่ระบุและไม่มีโปรเจค = เลือกจากตาราง งานคลุมเครือใช้ Python "
            "4) ตอบเสมอว่าเลือกภาษานี้เพราะอะไร (1 บรรทัด) + วิธีรัน "
            "5) ไฟล์เดียวจบก่อนเสมอ นามสกุลถูกต้อง "
            "6) เขียนเสร็จตรวจด้วย toolchain จริงผ่าน run_cmd ถ้ามี "
            "(python/node/go/cargo/javac/php/ruby/ฯลฯ) ไม่มีให้บอกวิธีติดตั้ง+รันแทน")


AGENT_SYSTEM += _lang_guide()

# โปรโตคอล Computer Use (บังคับด้วย Permission Layer ในโค้ด ไม่ใช่แค่คำสั่งนี้)
COMPUTER_USE = (
    "\nComputer Use: ควบคุมหน้าจอจริงด้วย tools computer_* (พิกัด 0-1000 เสมอ ห้าม hard-code พิกัด) "
    "วนลูป OBSERVE (computer_screenshot) → ANALYZE (computer_vision/computer_windows/computer_uielements/computer_ocr) "
    "→ SELECT+EXECUTE (1 action) → OBSERVE อีกครั้ง → VERIFY ว่าจอเปลี่ยนตามคาด → ตัดสินใจขั้นต่อไป "
    "หลัง action สำคัญทุกครั้งต้อง screenshot ตรวจก่อนเสมอ "
    "หา element ไม่เจอ/ล้มเหลว: screenshot ใหม่ + ใช้ OCR/UI tree เสริม + ลองวิธีอื่น (retry มีเพดาน แล้วรายงาน) "
    "action ทำลายข้อมูล/เปลี่ยนระบบ (ลบไฟล์ ฟอร์แมต ปิดเครื่อง firewall สิทธิ์ผู้ใช้ ติดตั้งโปรแกรม ส่งข้อความ/เมล อัปโหลดไฟล์ รันคำสั่งทำลาย) "
    "ต้องผ่านการยืนยันจากผู้ใช้ก่อนเสมอ ถูกปฏิเสธโดย Permission Layer ให้อธิบายเหตุผลแล้วเสนอทางอื่น "
    "(เช่น ขอสิทธิ์/ย้ายไปโฟลเดอร์ที่อนุญาต) ห้ามพยายามเลี่ยง permission เด็ดขาด")
AGENT_SYSTEM += COMPUTER_USE

AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "make_dir",
        "description": "สร้างโฟลเดอร์บนเครื่อง (สร้างโฟลเดอร์แม่ให้เอง)",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "พาธโฟลเดอร์ เช่น C:/Shop/assets"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "เขียน/สร้างไฟล์ (สร้างโฟลเดอร์แม่ให้เอง)",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "พาธไฟล์"},
            "content": {"type": "string", "description": "เนื้อไฟล์ทั้งหมด"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "อ่านไฟล์ข้อความ",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "default": 4000}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "ดูรายชื่อไฟล์ในโฟลเดอร์",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "default": "."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "run_cmd",
        "description": "รันคำสั่ง shell (ใช้เมื่อจำเป็นเท่านั้น · ต้องเปิดโหมด shell ก่อน)",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "คำสั่งที่จะรัน"}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "outline",
        "description": "ดูแผนที่สัญลักษณ์ (คลาส/ฟังก์ชัน + เลขบรรทัด) ของโปรเจกต์หรือโฟลเดอร์ — ประหยัดกว่าเปิดอ่านไฟล์ทั้งไฟล์",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "default": ".",
                     "description": "โฟลเดอร์หรือไฟล์ที่ต้องการดูโครงสร้าง"},
            "max_files": {"type": "integer", "default": 40}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "install_skill",
        "description": "ติดตั้ง skill จากแคตตาล็อกในเครื่อง (ระบบจะขออนุญาตผู้ใช้ก่อนเสมอ) แล้วใช้ read_skill อ่านวิธีทําได้ทันที",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "ชื่อ skill เช่น thai-docs"}},
            "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "search_skills",
        "description": "ค้น skill ที่ติดตั้งไว้และในแคตตาล็อกในเครื่องตามคําค้น (ใช้เมื่อผู้ใช้ถามหาสกิล/งานที่ควรใช้สกิลช่วย) — แนะนําให้ผู้ใช้ติดตั้งได้เลย",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "สิ่งที่ผู้ใช้อยากทํา/คําค้น เช่น 'ทํารายงาน excel'"},
            "web": {"type": "boolean", "default": False,
                    "description": "ค้นบน GitHub เพิ่มด้วย (ต้องมีเน็ต)"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "ค้นเว็บจริงผ่าน TinyFish Search API (คืน URL + หัวข้อ + สรุป) — ใช้เมื่อข้อมูลใหม่/อยู่นอกความรู้ (ต้องมี TINYFISH_API_KEY)",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "คำค้น"},
            "location": {"type": "string", "default": "US",
                         "description": "รหัสประเทศของผลค้น เช่น US/TH"},
            "language": {"type": "string", "default": "en",
                         "description": "รหัสภาษาของผลค้น เช่น en/th"},
            "intent": {"type": "string",
                       "description": "บอกว่าจะเอาผลไปทำอะไร (ยิ่งชัดผลยิ่งดี)"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "web_fetch",
        "description": "ดึงเนื้อหาเว็บเป็น markdown ผ่าน TinyFish Fetch API (คืน title + เนื้อหา) — ใช้หลัง web_search เพื่ออ่านหน้าจริง (ต้องมี TINYFISH_API_KEY)",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL เดียวที่จะดึง (http/https)"},
            "max_chars": {"type": "integer", "default": 8000,
                          "description": "ตัดผลเหลือกี่ตัวอักษร"},
            "intent": {"type": "string",
                       "description": "บอกว่าจะเอาเนื้อหาไปทำอะไร"}},
            "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "run_tests",
        "description": "รันชุดเทสต์/lint ของโปรเจกต์ (ตรวจคำสั่งให้เองถ้าไม่ระบุ) คืนผลจริงเพื่อตรวจงานตัวเอง",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "คำสั่งเทสต์ (ว่าง = ตรวจจากโปรเจกต์)"},
            "timeout": {"type": "integer", "default": 600}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "แก้ไฟล์เป็นจุดด้วยข้อความเดิม->ข้อความใหม่ (ต้องเจอ old_string จุดเดียว)",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string", "description": "ข้อความเดิมในไฟล์"},
            "new_string": {"type": "string", "description": "ข้อความใหม่"}},
            "required": ["path", "old_string", "new_string"]}}},
    {"type": "function", "function": {
        "name": "grep",
        "description": "ค้นข้อความในไฟล์ (regex) คืน ไฟล์:บรรทัด:เนื้อความ",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "regex ที่ค้นหา"},
            "path": {"type": "string", "default": ".",
                     "description": "ไฟล์หรือโฟลเดอร์ที่จะค้น"}},
            "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "glob",
        "description": "หาไฟล์ตาม pattern (เช่น **/*.py)",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "default": "**/*.py"},
            "path": {"type": "string", "default": "."}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": "อ่านเนื้อหา SKILL.md ฉบับเต็มของทักษะเสริมที่ติดตั้งไว้ (ใช้เมื่อตรงกับงาน)",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "ชื่อ skill เช่น pdf-fill"}},
            "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "mcp_tools",
        "description": "ดูรายชื่อ tools เสริมนอกเครื่อง (MCP) — เรียกครั้งเดียวเมื่อต้องใช้ของที่ tools ในเครื่องไม่มี แล้วค่อยเรียก mcp__* ในรอบถัดไป",
        "parameters": {"type": "object", "properties": {}},
        "required": []}},
    {"type": "function", "function": {
        "name": "computer_screenshot",
        "description": "แคปหน้าจอจริง (OBSERVE) คืนพาธไฟล์+ขนาดภาพ",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "computer_vision",
        "description": "วิเคราะห์ screenshot ล่าสุดด้วย Vision Model (หาปุ่ม/ช่องกรอก/เมนู/ข้อความ คืนพิกัด 0-1000)",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "คำถามถึงภาพ เช่น 'ช่องค้นหาอยู่พิกัดไหน ตอบเป็น x,y 0-1000'"},
            "provider": {"type": "string", "description": "ค่าย vision (ว่าง = ตาม config vision_provider/ค่ายแชท)"},
            "model": {"type": "string", "description": "โมเดล vision (ว่าง = ตาม config, 'auto' = หาตัวฟรีให้เอง)"}},
            "required": ["prompt"]}}},
    {"type": "function", "function": {
        "name": "computer_windows",
        "description": "รายชื่อหน้าต่างที่เปิดอยู่ (title/exe/ตำแหน่ง) หาแอปแบบไม่ hard-code",
        "parameters": {"type": "object", "properties": {
            "exe": {"type": "string", "description": "กรองชื่อโปรแกรม เช่น chrome (ว่าง = ทั้งหมด)"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "computer_uielements",
        "description": "UI tree ของหน้าต่าง (ปุ่ม/ช่องกรอก/ข้อความ + ตำแหน่ง) รองรับโฟกัสปัจจุบัน",
        "parameters": {"type": "object", "properties": {
            "hwnd": {"type": "integer", "description": "handle หน้าต่าง (ว่าง = หน้าต่างโฟกัส)"},
            "exe": {"type": "string", "description": "หรือระบุชื่อโปรแกรมแทน hwnd"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "computer_focus",
        "description": "ดึงหน้าต่างขึ้นโฟกัสโดยไม่คลิก (ระบุ exe หรือ hwnd)",
        "parameters": {"type": "object", "properties": {
            "exe": {"type": "string", "description": "ชื่อโปรแกรม เช่น chrome"},
            "hwnd": {"type": "integer", "description": "handle หน้าต่าง"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "computer_ocr",
        "description": "อ่านข้อความบนจอด้วย OCR (ถ้าเครื่องมี backend ไม่งั้นบอกชัด)",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "computer_move",
        "description": "ย้ายเมาส์ (พิกัด 0-1000)",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "number"}, "y": {"type": "number"}},
            "required": ["x", "y"]}}},
    {"type": "function", "function": {
        "name": "computer_click",
        "description": "คลิกซ้ายที่พิกัด 0-1000",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "number"}, "y": {"type": "number"}},
            "required": ["x", "y"]}}},
    {"type": "function", "function": {
        "name": "computer_double_click",
        "description": "ดับเบิลคลิกที่พิกัด 0-1000",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "number"}, "y": {"type": "number"}},
            "required": ["x", "y"]}}},
    {"type": "function", "function": {
        "name": "computer_right_click",
        "description": "คลิกขวาที่พิกัด 0-1000",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "number"}, "y": {"type": "number"}},
            "required": ["x", "y"]}}},
    {"type": "function", "function": {
        "name": "computer_drag",
        "description": "ลากเมาส์จากจุดหนึ่งไปอีกจุด (พิกัด 0-1000)",
        "parameters": {"type": "object", "properties": {
            "x1": {"type": "number"}, "y1": {"type": "number"},
            "x2": {"type": "number"}, "y2": {"type": "number"}},
            "required": ["x1", "y1", "x2", "y2"]}}},
    {"type": "function", "function": {
        "name": "computer_scroll",
        "description": "สกรอลล์ (dy บวก=ขึ้น ลบ=ลง)",
        "parameters": {"type": "object", "properties": {
            "dy": {"type": "integer", "default": 3},
            "dx": {"type": "integer", "default": 0}}, "required": []}}},
    {"type": "function", "function": {
        "name": "computer_type",
        "description": "พิมพ์ข้อความตรงจุดโฟกัส (ห้ามพิมพ์ secret ถ้าไม่จำเป็น)",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "ข้อความที่จะพิมพ์"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "computer_press",
        "description": "กดปุ่ม 1 ครั้ง (enter/tab/esc/space/ลูกศร/F1-F24/...)",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string", "description": "ชื่อปุ่ม"}},
            "required": ["key"]}}},
    {"type": "function", "function": {
        "name": "computer_hotkey",
        "description": "กดปุ่มลัด เช่น ['ctrl','s']",
        "parameters": {"type": "object", "properties": {
            "keys": {"type": "array", "items": {"type": "string"},
                      "description": "ลิสต์ชื่อปุ่ม"}}, "required": ["keys"]}}},
    {"type": "function", "function": {
        "name": "computer_wait",
        "description": "รอให้ UI เปลี่ยน (มิลลิวินาที สูงสุด 30000)",
        "parameters": {"type": "object", "properties": {
            "ms": {"type": "integer", "default": 1000}}, "required": []}}},
]


COMPUTER_TOOL_NAMES = ("computer_screenshot", "computer_vision", "computer_windows",
                       "computer_uielements", "computer_focus", "computer_ocr", "computer_move",
                       "computer_click", "computer_double_click", "computer_right_click",
                       "computer_drag", "computer_scroll", "computer_type",
                       "computer_press", "computer_hotkey", "computer_wait")


KNOWN_TOOLS = ("make_dir", "write_file", "read_file", "list_dir", "run_cmd", "run_tests",
               "edit_file", "grep", "glob", "outline", "read_skill", "mcp_tools",
               "search_skills", "install_skill", "web_search", "web_fetch") + COMPUTER_TOOL_NAMES
READONLY_TOOLS = ("read_file", "list_dir", "grep", "glob", "outline", "read_skill",
                  "search_skills", "mcp_tools", "web_search", "web_fetch")


INIT_SYSTEM = ("You draft AGENTS.md files: short operating instructions for an AI coding "
               "agent working in this repo. Match the repo language (Thai repo = Thai with "
               "English tech terms kept). Output ONLY the file content, no code fences, "
               "no explanations. Sections: ภาพรวมโปรเจกต์, คำสั่ง build/test/run, "
               "โครงสร้างสำคัญ, กฎการแก้โค้ด (do/don't สั้น ๆ). Keep under 40 lines.")


# ── คำสั่ง init: ร่าง AGENTS.md + ห้องแชทตั้งค่าโปรเจกต์ ─────────────────────
def draft_agents_md(provider, model, context):
    """ให้โมเดลร่างเนื้อหา AGENTS.md จากข้อมูลโปรเจกต์ (ล้มเหลว = raise)"""
    msgs = [{"role": "system", "content": INIT_SYSTEM},
            {"role": "user",
             "content": "ร่างเนื้อหาไฟล์ AGENTS.md สำหรับโปรเจกต์นี้:\n\n" + context}]
    out = send_messages(provider, model, msgs, 0.2, stream=False, effort="")
    return (out or "").strip()


def _cmd_init_chat(provider, model, keys, cfg):
    """/init: ร่าง AGENTS.md ด้วย AI + พรีวิว + บันทึกเมื่อยืนยัน"""
    target = Path.cwd() / "AGENTS.md"
    try:
        if target.is_file():
            console.print("[yellow]มี AGENTS.md อยู่แล้วในโฟลเดอร์นี้[/yellow]")
            try:
                cur = target.read_text(encoding="utf-8", errors="replace")
                console.print(Panel(cur[:1500], title="AGENTS.md ปัจจุบัน",
                                    border_style="cyan"))
            except Exception:
                pass
            try:
                if Prompt.ask("เขียนทับด้วยฉบับร่างใหม่?",
                               choices=["y", "n"], default="n") != "y":
                    console.print("[dim]ยกเลิก[/dim]")
                    return
            except (EOFError, KeyboardInterrupt):
                console.print()
                return
    except Exception:
        pass
    ctx = collect_init_context()
    if not ctx:
        console.print("[red]อ่านโครงโปรเจกต์ไม่ได้[/red]")
        return
    console.print("[dim](กำลังร่าง AGENTS.md จากโครงโปรเจกต์…)[/dim]")
    try:
        draft = draft_agents_md(provider, model, ctx)
    except Exception as e:
        console.print(f"[red]ร่างไม่สำเร็จ: {e}[/red]")
        return
    if not draft:
        console.print("[red]โมเดลตอบว่าง — ลองใหม่อีกครั้ง[/red]")
        return
    console.print(Panel(draft[:3000], title="ร่าง AGENTS.md", border_style="magenta"))
    try:
        if Prompt.ask("บันทึกเป็น AGENTS.md?", choices=["y", "n"], default="y") != "y":
            console.print("[dim]ยกเลิก (ไม่บันทึก)[/dim]")
            return
    except (EOFError, KeyboardInterrupt):
        console.print()
        return
    try:
        target.write_text(draft if draft.endswith("\n") else draft + "\n",
                          encoding="utf-8")
    except Exception as e:
        console.print(f"[red]บันทึกไม่ได้: {e}[/red]")
        return
    console.print(f"[green]บันทึก {target} แล้ว — agent จะอ่านอัตโนมัติตั้งแต่รอบถัดไป[/green]")


# ── git workflow (M4): ร่าง commit/PR ให้ แต่ "ไม่ push ไม่เปิด PR เอง" ────────
def _git_run(args, timeout=25):
    """รัน git ตรง ๆ (ไม่ผ่าน shell) ในโฟลเดอร์งาน คืน (code, ข้อความออก)"""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(workspace_root())] + [str(a) for a in args],
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        # rstrip เท่านั้น — ต้องคงช่องว่างนํ้าบรรทัดแรกของ git status --porcelain ไว้
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).rstrip()
    except FileNotFoundError:
        return -1, "เครื่องนี้ไม่มี git"
    except Exception as e:
        return -1, f"รัน git ไม่ได้: {e}"


def git_in_repo():
    code, _ = _git_run(["rev-parse", "--is-inside-work-tree"])
    return code == 0


def git_branch():
    """ชื่อสาขาปัจจุบัน ('' = ไม่รู้) — รองรับ repo ที่ยังไม่มี commit (unborn branch)"""
    code, out = _git_run(["rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0 and out and out.strip() != "HEAD":
        return out.splitlines()[0].strip()
    code2, out2 = _git_run(["symbolic-ref", "--short", "HEAD"])
    return out2.splitlines()[0].strip() if code2 == 0 and out2 else ""


def git_changes():
    """ไฟล์ที่ยังไม่ commit: [(สถานะ, พาธ), ...] จาก git status --porcelain"""
    code, out = _git_run(["status", "--porcelain"])
    if code != 0:
        return []
    items = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        items.append((line[:2].strip() or "??", path.strip().strip('"')))
    return items


def git_base_branch():
    """สาขาหลัก (ใช้เทียบ PR) — origin/HEAD ก่อน แล้วค่อย main/master"""
    code, out = _git_run(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if code == 0 and out:
        return out.strip().split("/")[-1]
    for name in ("main", "master"):
        code2, _ = _git_run(["rev-parse", "--verify", name])
        if code2 == 0:
            return name
    return ""


COMMIT_SYSTEM = (
    "You write one git commit message from a diff. Reply in Thai (keep English tech terms "
    "and identifiers). Line 1: imperative summary focused on WHY, <= 72 chars. "
    "Then one blank line and 2-4 short bullet lines. "
    "No markdown fences, no quotes around the whole message, no trailers. Return only the message.")


def draft_commit_message(provider, model, diff_text):
    """ร่างข้อความ commit จาก diff ('' = ร่างไม่ได้)"""
    if not str(diff_text or "").strip():
        return ""
    msgs = [{"role": "system", "content": COMMIT_SYSTEM},
            {"role": "user", "content": "diff:\n\n" + str(diff_text)[:12000]}]
    try:
        out = send_messages(provider, model, msgs, 0.2, stream=False, effort="", max_tokens=500)
    except Exception as e:
        console.print(f"[dim](ร่างข้อความ commit ไม่สำเร็จ: {e})[/dim]")
        return ""
    txt = fix_mojibake(out or "").strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt.split("\n", 1)[1] if "\n" in txt else txt
    return txt.strip()


def git_commit_flow(provider, model, auto_yes=False):
    """/commit: ร่างข้อความจาก diff → ยืนยัน → stage เฉพาะไฟล์ที่เปลี่ยน → commit
    ไม่ push เด็ดขาด (คืน True เมื่อ commit สำเร็จ)"""
    if not git_in_repo():
        console.print("[yellow]โฟลเดอร์นี้ไม่ใช่ git repo — ใช้ git init เองก่อน[/yellow]")
        return False
    changes = git_changes()
    if not changes:
        console.print("[dim]ไม่มีอะไรให้ commit (working tree สะอาด)[/dim]")
        return False
    diff_text, _why = git_diff_text()
    untracked = [p for st, p in changes if st == "??"]
    body = diff_text or ""
    if untracked:
        body += "\n\n[ไฟล์ใหม่ที่ยังไม่ track]\n" + "\n".join(untracked[:50])
    console.print(f"[dim]{len(changes)} ไฟล์เปลี่ยน · สาขา {git_branch() or '?'}[/dim]")
    with console.status("[cyan]กำลังร่างข้อความ commit…[/]", spinner="dots"):
        msg = draft_commit_message(provider, model, body)
    if not msg:
        msg = "ปรับปรุงโค้ดตามงานล่าสุด"
        console.print("[dim](ร่างไม่ได้ — ใช้ข้อความกลาง ๆ แทน)[/dim]")
    console.print(Panel(msg, title="ข้อความ commit ที่ร่างไว้", border_style="magenta"))
    if sys.stdin.isatty():
        try:
            if Prompt.ask("commit ด้วยข้อความนี้ไหม? (ไม่ push)",
                          choices=["y", "n"], default="n") != "y":
                console.print("[dim]ยกเลิก (ไม่ commit)[/dim]")
                return False
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False
    elif not auto_yes:
        console.print("[yellow]โหมดไม่ interactive ต้องส่ง --yes จึงจะ commit ได้[/yellow]")
        return False
    paths = [p for _st, p in changes]
    code, out = _git_run(["add", "--"] + paths, timeout=60)
    if code != 0:
        console.print(f"[red]stage ไม่สำเร็จ: {out[:300]}[/red]")
        return False
    code2, out2 = _git_run(["commit", "-m", msg], timeout=60)
    if code2 != 0:
        console.print(f"[red]commit ไม่สำเร็จ: {out2[:300]}[/red]")
        return False
    code3, out3 = _git_run(["log", "--oneline", "-1"])
    console.print(f"[green]commit แล้ว:[/green] {out3.splitlines()[0] if out3 else ''}")
    console.print("[dim](ไม่ได้ push — ตรวจดูก่อนแล้วค่อย git push เอง)[/dim]")
    return True


PR_SYSTEM = (
    "You draft a pull request from a branch diff. Reply in Thai (keep English tech terms). "
    "Start with 'TITLE: <short title>' on the first line, then a blank line, then sections: "
    "'## ทำอะไร', '## ทำไม', '## ทดสอบยังไง', '## ความเสี่ยง/หมายเหตุ'. "
    "Be specific about files and behavior. No markdown fences. Keep under 40 lines.")


def draft_pr_body(provider, model, base=""):
    """/pr: ร่าง title + body จาก diff เทียบสาขาหลัก แล้วบันทึกให้ (ไม่ push / ไม่เปิด PR)"""
    if not git_in_repo():
        console.print("[yellow]โฟลเดอร์นี้ไม่ใช่ git repo[/yellow]")
        return ""
    base = (base or git_base_branch() or "").strip()
    if not base:
        console.print("[yellow]หาสาขาหลักไม่เจอ — ใช้ /pr <สาขา> เช่น /pr main[/yellow]")
        return ""
    rng = f"{base}...HEAD"
    code, diff = _git_run(["diff", rng], timeout=30)
    _code2, stat = _git_run(["diff", "--stat", rng], timeout=30)
    if code != 0:
        console.print(f"[yellow]เทียบกับ {base} ไม่ได้: {diff[:200]}[/yellow]")
        return ""
    if not diff.strip() and not stat.strip():
        console.print(f"[dim]ไม่มีความต่างจาก {base} — commit งานก่อนแล้วลองใหม่[/dim]")
        return ""
    msgs = [{"role": "system", "content": PR_SYSTEM},
            {"role": "user", "content": f"[stat\n{stat[:2000]}]\n\n[diff]\n{diff[:14000]}"}]
    with console.status("[cyan]กำลังร่าง PR…[/]", spinner="dots"):
        try:
            out = send_messages(provider, model, msgs, 0.3, stream=False, effort="",
                                max_tokens=1000)
        except Exception as e:
            console.print(f"[red]ร่างไม่สำเร็จ: {e}[/red]")
            return ""
    txt = fix_mojibake(out or "").strip()
    if not txt:
        console.print("[red]โมเดลตอบว่าง — ลองใหม่[/red]")
        return ""
    target = Path.cwd() / ".soonai" / "pr-body.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(txt + "\n", encoding="utf-8")
        saved = f"บันทึกไว้ที่ {target}"
    except Exception as e:
        saved = f"(บันทึกไฟล์ไม่ได้: {e})"
    console.print(Panel(txt[:4000], title=f"ร่าง PR (เทียบ {base})", border_style="magenta"))
    console.print(f"[dim]{saved} — คัดลอกไปวางใน PR เอง (ระบบไม่ push/ไม่เปิด PR ให้)[/dim]")
    return txt


def git_diff_text(ref="HEAD", max_chars=12000):
    """diff + status ของ git repo คืน (ข้อความ, เหตุผลที่ว่าง)"""
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10,
                           errors="replace")
        if r.returncode != 0:
            return "", "ไม่ใช่ git repo (เข้าโฟลเดอร์โปรเจกต์ก่อน)"
    except FileNotFoundError:
        return "", "เครื่องนี้ไม่มี git"
    except Exception as e:
        return "", f"อ่าน git ไม่ได้: {e}"
    try:
        d = subprocess.run(["git", "diff", ref], capture_output=True, text=True,
                           timeout=15, encoding="utf-8", errors="replace")
        s = subprocess.run(["git", "status", "--short"], capture_output=True,
                           text=True, timeout=10, encoding="utf-8", errors="replace")
    except Exception as e:
        return "", f"อ่าน git ไม่ได้: {e}"
    diff = (d.stdout or "").strip()
    stat = (s.stdout or "").strip()
    if not diff and not stat:
        return "", "ไม่มีอะไรเปลี่ยน (working tree สะอาด)"
    text = ""
    if stat:
        text += "[git status]\n" + stat + "\n\n"
    if diff:
        text += "[git diff]\n" + diff
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (diff ยาว ตัดให้สั้น)"
    return text, ""


REVIEW_SYSTEM = ("You review code diffs. Reply in Thai (keep English tech terms). "
                 "Structure exactly: 1) สรุปว่าเปลี่ยนอะไร (สั้น) "
                 "2) ความเสี่ยง: แยก สูง/กลาง/ต่ำ พร้อมชื่อไฟล์ "
                 "3) จุดต้องแก้ก่อน push (ถ้าไม่มีให้บอกว่าไม่มี). "
                 "Be strict about secrets, destructive commands, migrations without "
                 "rollback, and untested logic. Keep under 60 lines.")


def _cmd_review_chat(provider, model):
    """/review: ให้ AI รีวิว diff ที่ยังไม่ commit + สรุปความเสี่ยง"""
    diff_text, why = git_diff_text()
    if why:
        console.print(f"[yellow]{why}[/yellow]")
        return
    console.print("[dim](กำลังรีวิว diff…)[/dim]")
    try:
        out = send_messages(
            provider, model,
            [{"role": "system", "content": REVIEW_SYSTEM},
             {"role": "user", "content": "รีวิว diff นี้:\n\n" + diff_text}],
            0.2, stream=False, effort="") or ""
    except Exception as e:
        console.print(f"[red]รีวิวไม่สำเร็จ: {e}[/red]")
        return
    if not out.strip():
        console.print("[red]โมเดลตอบว่าง — ลองใหม่อีกครั้ง[/red]")
        return
    console.print(Panel(Markdown(out), title="รีวิวโค้ด", border_style="magenta"))


def extract_text_calls(text):
    """ดึง tool calls ที่โมเดลเขียนเป็น JSON ในข้อความ (fallback เมื่อไม่ใช้ native calling)
    คืน [(name, args_dict)] รองรับทั้งบล็อก ```tool และ JSON ลอย ๆ"""
    import re
    from json import JSONDecoder
    dec = JSONDecoder()
    calls = []
    for m in re.finditer(r'"name"\s*:\s*"([A-Za-z0-9_]+)"', text or ""):
        name = m.group(1)
        if name not in KNOWN_TOOLS and not name.startswith("mcp__"):
            continue
        start = text.rfind("{", 0, m.start())
        if start < 0:
            continue
        try:
            obj, _ = dec.raw_decode(text[start:])
        except Exception:
            continue
        if not isinstance(obj, dict) or obj.get("name") != name:
            continue
        args = obj.get("arguments", obj.get("parameters", {}))
        calls.append((name, args if isinstance(args, dict) else {}))
    seen = set()
    uniq = []
    for n, a in calls:
        key = (n, json.dumps(a, sort_keys=True, ensure_ascii=False))
        if key not in seen:
            seen.add(key)
            uniq.append((n, a))
    return uniq


# ── MCP: เรียก tool ผ่าน mcp_client (hub/call/readonly) ─────────────────────
def mcp_hub_for_tools():
    """รายชื่อ MCP tools รูป OpenAI defs (ล้มเหลว = [] ไม่พัง agent)"""
    try:
        return _compact_mcp_tool_defs(_agent_mcp_tools()) if _MCP_OK else []
    except Exception:
        return []


def mcp_call_tool(name, args):
    try:
        if not _MCP_OK:
            return "ERROR: ระบบ MCP ใช้ไม่ได้"
        return _call_mcp_tool(name, args if isinstance(args, dict) else {})
    except Exception as e:
        return f"ERROR: MCP: {e}"


def _mcp_readonly(name):
    """MCP metadata is advisory, never sufficient to skip user approval.

    A server controls its own annotations and can mutate state behind a tool
    named as read-only.  Treat every MCP invocation as an external action.
    """
    return False


# ---------- Computer Use gate (Permission Layer ฝั่ง CLI) ----------

def _computer_policy():
    """นโยบาย computer ปัจจุบันจาก config (normalize แล้ว)
    grant_until รับเลข epoch หรือข้อความระยะเวลา ("30m"/"2h"/"1d")
    แบบระยะเวลาจะแปลงเป็นเวลาสิ้นสุดแล้วบันทึกกลับครั้งเดียว"""
    try:
        if _PERM_OK:
            cfg = load_config() or {}
            raw = cfg.get("computer")
            pol = _PERM.normalize_policy(raw)
            gu = raw.get("grant_until") if isinstance(raw, dict) else None
            if isinstance(gu, str):
                import re as _re
                m = _re.match(r"^\s*(\d+)\s*([smhd])\s*$", gu, _re.I)
                if m:
                    import time as _t
                    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2).lower()]
                    abs_ts = _t.time() + int(m.group(1)) * mult
                    pol["grant_until"] = abs_ts
                    try:
                        cfg["computer"] = dict(raw)
                        cfg["computer"]["grant_until"] = abs_ts
                        save_json(CONFIG_FILE, cfg)
                    except Exception:
                        pass
            return pol
    except Exception:
        pass
    return {"level": "off", "approval": "ask_risky", "grant_until": 0,
            "scope": {"screen": False, "mouse": False, "keyboard": False,
                      "browser": False, "terminal": False, "filesystem": "deny",
                      "system_settings": False, "apps_allow": [], "apps_deny": [],
                      "windows_allow": [], "regions": []}}


def _computer_fg():
    """หน้าต่างโฟกัสตอนนี้ (ล้มเหลว = {} = ข้ามเช็กฝั่งแอป)"""
    try:
        mod, err = _computer_mod()
        if mod is None:
            return {}
        return mod.foreground_window() or {}
    except Exception:
        return {}


def _computer_audit(action, target="", app="", permission="", result="",
                    reason="", tool_args=None, tool=""):
    try:
        mod, _ = _computer_mod()
        log = str(DATA_DIR / "computer" / "audit.log")
        if _PERM_OK:
            return _PERM.audit_append(log, action, target, app, permission,
                                      result, reason, tool_args, tool)
    except Exception:
        pass
    return False


def _computer_gate(name, args):
    """ประตู Permission->Scope->Safety คืน (allow, confirm, reason, permission)"""
    if not _PERM_OK:
        return False, False, "ระบบ permission ใช้ไม่ได้", "none"
    try:
        pol = _computer_policy()
        fg = _computer_fg() if name in _PERM.ACTION_TOOLS else {}
        d = _PERM.evaluate(name, args if isinstance(args, dict) else {}, pol, fg)
        return d["allow"], d["confirm"], d["reason"], d["permission"]
    except Exception as e:
        return False, False, f"ตรวจ permission ล้มเหลว: {e}", "none"


def computer_vision_analyze(prompt, provider="", model="", fresh_sec=10, max_width=1280):
    """Capture a fresh screenshot, redact denied apps, then call a Vision Model.
    provider/model: ที่ระบุ > config vision_* > ค่าแชทปัจจุบัน
    model = "auto" -> หาโมเดล vision ฟรีให้เอง (openrouter) + ลองตัวถัดไปเมื่อโดน 404/429"""
    import base64
    mod, err = _computer_mod()
    if mod is None:
        raise RuntimeError(err)
    cfg = load_config() or {}
    provider = (provider or "").strip() or (cfg.get("vision_provider") or "").strip() \
        or (cfg.get("provider") or "").strip()
    model = (model or "").strip() or (cfg.get("vision_model") or "").strip() \
        or (cfg.get("model") or "").strip()
    if provider not in PROVIDERS:
        raise RuntimeError(f"ไม่รู้จัก provider: {provider or '(ว่าง)'}")
    if not model:
        raise RuntimeError("ยังไม่เลือกโมเดล vision (ใส่ในคำสั่ง, config vision_model, หรือ 'auto')")
    out_dir = str(DATA_DIR / "computer")
    # redact หน้าต่างแอปต้องห้ามก่อนส่ง vision (mask ดำตาม rect เต็มจอ)
    deny_rects = []
    try:
        pol = _computer_policy()
        deny_pats = (pol.get("scope") or {}).get("apps_deny") or []
        if deny_pats and _PERM_OK:
            for w in mod.list_windows(visible_only=True, limit=100):
                hit = _PERM._match_any(w.get("exe", ""), deny_pats) or \
                    _PERM._match_any(w.get("title", ""), deny_pats)
                if hit and w.get("rect"):
                    deny_rects.append(w["rect"])
    except Exception:
        deny_rects = []
    # Always capture fresh.  Reusing last.png could upload an image captured
    # before a deny-list or privacy policy changed.
    shot = mod.capture_screen(max_width=max_width or 1280, redact_fullres=deny_rects)
    png, w, h = shot["png"], shot["width"], shot["height"]
    path = mod.save_shot(png, out_dir)
    b64 = base64.b64encode(png).decode("ascii")
    if model.strip().lower() == "auto":
        cands = discover_vision_models(provider)
        if not cands:
            raise RuntimeError("หาโมเดล vision ฟรีไม่เจอ (ระบุ model ตรง ๆ หรือเช็กเน็ต)")
    else:
        cands = [model]
    last_err = None
    for cand in cands[:3]:
        try:
            return _vision_call_once(provider, cand, prompt or "อธิบายภาพนี้สั้น ๆ",
                                     b64, w, h, path)
        except Exception as e:
            if not _vision_retryable(str(e)):
                raise
            last_err = e
    raise RuntimeError(f"vision ล้มเหลวทุกตัว ({last_err})")


def _vision_retryable(msg):
    """error แบบนี้ควรลองโมเดลถัดไปไหม (404/429/quota โมเดลใช้ไม่ได้ชั่วคราว)"""
    try:
        low = str(msg or "").lower()
    except Exception:
        return False
    return any(k in low for k in
               ("404", "429", "rate limit", "quota", "unavailable",
                "no longer available", "overloaded", "temporarily",
                "timed out", "timeout", "connection", "image",
                "clipboard", "cannot read", "does not support"))


VISION_DISCOVER_TTL = 24 * 3600


def discover_vision_models(provider, limit=8):
    """หารายชื่อโมเดล vision (openrouter: ฟรี + รับภาพ) + cache 24 ชม.
    provider อื่น = [] (ระบุ model ตรง ๆ)"""
    prov = (provider or "").strip()
    if prov != "openrouter":
        return []
    cache_p = DATA_DIR / "computer" / "vision_models.json"
    try:
        import time as _t
        d = json.loads(cache_p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("models") and \
                _t.time() - float(d.get("ts", 0)) < VISION_DISCOVER_TTL:
            return [m for m in d["models"] if isinstance(m, str)][:max(1, int(limit or 8))]
    except Exception:
        pass
    found = []
    try:
        ocfg = PROVIDERS.get("openrouter", {})
        key = get_key("openrouter", load_keys())
        headers = dict(ocfg.get("extra_headers", {}))
        if key:
            headers["Authorization"] = "Bearer " + key
        r = requests.get(ocfg.get("models_url") or "https://openrouter.ai/api/v1/models",
                         headers=headers, timeout=30)
        data = r.json().get("data", []) if r.status_code == 200 else []
        cands = []
        for m in data:
            if not isinstance(m, dict) or not m.get("id"):
                continue
            try:
                pr = m.get("pricing") or {}
                if float(pr.get("prompt", 1)) != 0 or float(pr.get("completion", 1)) != 0:
                    continue
            except Exception:
                continue
            if "image" not in str((m.get("architecture") or {}).get("modality", "")):
                continue
            cands.append(m["id"])
        prefer = ("qwen", "gemma", "mistral", "glm", "llama", "nemotron",
                  "dots", "inkling", "nex", "ling")

        def _rank(mid):
            low = str(mid).lower()
            for i, p in enumerate(prefer):
                if p in low:
                    return (0, i, len(str(mid)))
            return (1, 99, len(str(mid)))

        found = sorted(set(cands), key=_rank)[:max(1, int(limit or 8))]
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:discover_vision_models",
                           "หารายชื่อโมเดล vision ไม่ได้ — ต้องระบุโมเดลเอง")
        found = []
    try:
        import time as _t
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        cache_p.write_text(json.dumps({"ts": _t.time(), "models": found},
                                      ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return found


def _vision_call_once(provider, model, prompt, b64, w, h, path):
    """ยิง vision 1 ครั้ง (ล้มเหลว = raise)"""
    pcfg = PROVIDERS[provider]
    key = get_key(provider, load_keys())
    if pcfg.get("key_env") and not key and not pcfg.get("no_key"):
        raise RuntimeError(f"ยังไม่มี key ของ {provider} (soonai key set {provider} ...)")
    if pcfg.get("type") == "anthropic":
        body = {"model": model, "max_tokens": 2048, "messages": [{
            "role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt or "อธิบายภาพนี้สั้น ๆ"}] }]}
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        r = _post_chat("https://api.anthropic.com/v1/messages", headers=headers,
                       payload=body, timeout=_chat_timeout(False), stream=False,
                       tag="vision-anthropic")
        j = r.json()
        if r.status_code != 200:
            raise RuntimeError(format_api_error(provider, r.status_code, j))
        return fix_mojibake("".join(b.get("text", "") for b in j.get("content", [])
                                    if b.get("type") == "text"))
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    headers.update(pcfg.get("extra_headers", {}))
    body = {"model": model, "temperature": 0.2, "max_tokens": 2048, "messages": [{
        "role": "user", "content": [
            {"type": "text", "text": prompt or "อธิบายภาพนี้สั้น ๆ"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}]}
    r = _post_chat(pcfg["base"].rstrip("/") + "/chat/completions", headers=headers,
                   payload=body, timeout=_chat_timeout(False), stream=False,
                   tag="vision-openai")
    try:
        j = r.json()
    except Exception:
        raise RuntimeError(f"HTTP {r.status_code}: {(r.text or '')[:300]}")
    if r.status_code != 200:
        raise RuntimeError(format_api_error(provider, r.status_code, j))
    try:
        text = j["choices"][0]["message"]["content"] or ""
    except Exception:
        raise RuntimeError(f"ตอบกลับผิดรูป: {str(j)[:300]}")
    try:
        return fix_mojibake(text) + f"\n[ภาพ: {path} {w}x{h}]"
    except Exception:
        return text


# ── ไฟล์/พาธต้องห้าม: sensitive list + normalize path ───────────────────────
def _norm_path_str(p):
    """ทำพาธให้เทียบกันได้ (absolute + ตัวเล็ก + / เท่านั้น)"""
    try:
        return str(Path(p).resolve()).lower().replace("\\", "/")
    except Exception:
        return str(p or "").strip().lower().replace("\\", "/")


def _sensitive_paths():
    """ไฟล์ต้องห้าม agent แตะ: keys/config/MCP/ทีม + memory + audit + log ที่มีข้อมูลดิบ"""
    out = []
    for p in (KEYS_FILE, CONFIG_FILE, SHARED_DIR / "mcp.json", SHARED_DIR / "team.json",
              SHARED_DIR / ".machine_id", SHARED_DIR / ".models_cache.json",
              DATA_DIR / "memory.json", DATA_DIR / "computer" / "audit.log",
              BASE_DIR / "debug_last.json", BASE_DIR / "crash.log"):
        try:
            out.append(_norm_path_str(p))
        except Exception:
            pass
    return out


def _sensitive_dirs():
    """โฟลเดอร์ต้องห้ามทั้งโฟลเดอร์: ประวัติแชท (มีข้อความทั้งบทสนทนา) + ไฟล์ computer
    (ภาพหน้าจอ/audit) — ห้ามแตะทั้ง subtree ไม่ใช่แค่ไฟล์ที่รู้จัก"""
    out = []
    for p in (SESSIONS_DIR, DATA_DIR / "computer", BASE_DIR / "sessions"):
        try:
            out.append(_norm_path_str(p))
        except Exception:
            pass
    return out


def _normalized_tool_path(value):
    """Canonical path for policy checks (Windows separators/case included)."""
    try:
        s = str(value or "").strip()
        if s.lower().startswith("file://"):
            s = s[7:]
            if len(s) > 2 and s[0] == "/" and s[2] == ":":
                s = s[1:]  # file:///C:/... -> C:/...
        return str(_resolve_tool_path(s)).lower().replace("\\", "/")
    except Exception:
        return str(value or "").strip().lower().replace("\\", "/")


def _path_is_sensitive(p):
    """พาธนี้เป็นไฟล์/โฟลเดอร์ secret หรือไม่
    ใช้กับเครื่องมือที่เดินอ่านไฟล์เอง (grep/glob) ซึ่ง args ไม่ได้บอกพาธปลายทางตรง ๆ"""
    v = _normalized_tool_path(str(p))
    if not v:
        return False
    for s in _sensitive_paths():
        if s and v == s:
            return True
    for d in _sensitive_dirs():
        if d and (v == d or v.startswith(d + "/")):
            return True
    return False


# ── ตรวจพาธต้องห้ามใน args ของ tool ─────────────────────────────────────────
# คีย์ที่เก็บ "เนื้อหา" ไม่ใช่พาธ — ข้ามทั้ง subtree (เขียนไฟล์/เอกสารที่ "พูดถึง"
# พาธ secret ต้องทำได้ ไม่ใช่ถูกบล็อก) ส่วนคีย์อื่นทั้งหมดถูกมองว่าเป็นพาธได้
_CONTENT_KEYS = frozenset((
    "content", "text", "prompt", "body", "message", "code", "data", "query",
    "old_string", "new_string", "old_text", "new_text", "pattern",
))
_PATH_SEPS = ("/", "\\")
# เพดานการไล่ args (args มาจาก AI — กันโครงสร้างลึก/ใหญ่ผิดปกติ)
_ARGS_SCAN_MAX_DEPTH = 10
_ARGS_SCAN_MAX_NODES = 20000


def _sensitive_tokens(paths):
    """ชื่อไฟล์/โฟลเดอร์ต้องห้าม (ตัวเล็ก) ใช้เป็นตัวกรองเร็ว
    สตริงที่จะชนได้จริงต้องมีชื่อพวกนี้อยู่ข้างในเสมอ (เท่ากัน = มีชื่อเต็มในสตริง,
    อยู่ใต้โฟลเดอร์ = มีชื่อโฟลเดอร์เป็นส่วนของพาธ) — จึงใช้กรองก่อนโดยไม่ต้อง resolve"""
    out = set()
    for p in paths or ():
        try:
            b = os.path.basename(str(p).rstrip("/\\")).strip().lower()
        except Exception:
            continue
        if len(b) >= 4:
            out.add(b)
    return out


def _arg_path_candidates(value, tokens, _depth=0, _state=None):
    """ไล่ args ทุกชั้น คืนสตริงที่ "อาจเป็นพาธต้องห้าม" (สะสมใน _state)

    - ไล่ครบทุกระดับ: dict/list/tuple/set ซ้อนกันกี่ชั้นก็เจอ รวม dict ที่อยู่ใน
      list (เช่น ``{"files": [{"path": "shared/keys.json"}]}``) และ schema ที่ใช้
      พาธเป็น key ของ dict — ของเดิมดูแค่คีย์ที่รู้จัก + dict ซ้อนชั้นเดียว จึงหลุด
    - เก็บเฉพาะสตริงที่มีตัวคั่นพาธ หรือมีชื่อไฟล์/โฟลเดอร์ต้องห้ามอยู่ข้างใน
      (สตริงอื่นเทียบยังไงก็ไม่ชน) → ไล่โหนดได้เยอะโดยไม่ต้อง resolve ทีละอัน
    - ข้าม subtree ของคีย์เนื้อหา (_CONTENT_KEYS)
    """
    st = _state if isinstance(_state, dict) else {"nodes": 0, "out": []}
    if _depth > _ARGS_SCAN_MAX_DEPTH or st["nodes"] >= _ARGS_SCAN_MAX_NODES:
        return st["out"]
    st["nodes"] += 1
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return st["out"]
        low = s.lower()
        if (any(sep in s for sep in _PATH_SEPS)
                or any(tok in low for tok in tokens)):
            st["out"].append(s)
        return st["out"]
    if isinstance(value, dict):
        for k, v in value.items():
            if str(k).strip().lower() in _CONTENT_KEYS and isinstance(v, str):
                continue   # เนื้อหาแบบสตริง = ไม่ตีความเป็นพาธ (กันเท็จบวก)
                           # แต่ค่าเป็นโครงสร้างซ้อนยังต้องไล่ต่อ (พาธซ่อนในนั้นได้)
            _arg_path_candidates(k, tokens, _depth + 1, st)   # เผื่อพาธเป็น key
            _arg_path_candidates(v, tokens, _depth + 1, st)
        return st["out"]
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _arg_path_candidates(item, tokens, _depth + 1, st)
        return st["out"]
    return st["out"]


def _sensitive_hit(args, write=True):
    """หา "พาธต้องห้าม" ใน structured tool args (args มาจาก AI)

    พาธถูก canonicalize ก่อนเทียบ (relative/ตัวคั่น Windows/``file://`` จึงหลบไม่ได้)
    และไล่ค่าทุกชั้นแบบ recursive (ดู ``_arg_path_candidates``) — พาธที่ซ่อนใน
    list-of-dict/โครงสร้างซ้อนก็เจอ คืนชื่อไฟล์/โฟลเดอร์ที่ชน หรือ '' ถ้าไม่ชน
    (เขียน=True/False ต่างกันแค่ข้อความที่ caller ใช้ จึงไม่เปลี่ยนการตรวจ)
    """
    try:
        sensitive = _sensitive_paths()
        dirs = _sensitive_dirs()
    except Exception:
        return ""
    try:
        values = _arg_path_candidates(args, _sensitive_tokens(sensitive + dirs))
    except Exception:
        return ""
    normalized = []
    for v in values:
        try:
            normalized.append(_normalized_tool_path(v))
        except Exception:
            continue
    for p in sensitive:
        if p and any(v == p for v in normalized):
            return os.path.basename(p)
    for d in dirs:
        if d and any(v == d or v.startswith(d + "/") for v in normalized):
            return os.path.basename(d) + "/"
    return ""


def _sensitive_deny(name, args):
    """กัน AI เพิ่มสิทธิ์/ขโมย secret ให้ตัวเอง (บังคับในโค้ด ไม่ใช่แค่ prompt)
    คืนข้อความ ERROR หรือ '' ถ้าผ่าน"""
    try:
        n = str(name or "")
        a = args if isinstance(args, dict) else {}
        if n in ("write_file", "edit_file"):
            hit = _sensitive_hit(a, write=True)
            if hit:
                return f"ERROR: ห้าม agent เขียน {hit} (กันแก้สิทธิ์/ขโมย key ให้ตัวเอง)"
        if n in ("read_file", "grep", "glob", "list_dir"):
            hit = _sensitive_hit(a, write=False)
            if hit:
                return f"ERROR: ห้าม agent อ่าน {hit} (ไฟล์ secret)"
        if n == "run_cmd":
            try:
                cmd = str((a or {}).get("command", ""))
            except Exception:
                cmd = ""
            shell_hit = _sensitive_shell_hit(cmd)
            if shell_hit:
                return ("ERROR: ห้ามแตะ %s ผ่าน shell (กันแก้สิทธิ์/ขโมย key ให้ตัวเอง)"
                        % shell_hit)
        if n.startswith("mcp__"):
            try:
                tool_part = _split_mcp_name(n)[1] if _MCP_OK else ""
            except Exception:
                tool_part = ""
            low = str(tool_part or "").lower()
            if any(h in low for h in _MCP_WRITE_HINTS):
                hit = _sensitive_hit(a, write=True)
                if hit:
                    return f"ERROR: ห้าม MCP tool เขียน {hit}"
            else:
                hit = _sensitive_hit(a, write=False)
                if hit:
                    return f"ERROR: ห้าม MCP tool อ่าน {hit} (ไฟล์ secret)"
    except Exception:
        pass
    return ""


_MCP_DEFS_CACHE = {"defs": None}
_MCP_LAZY = {"loaded": False}  # True = mcp_tools เคยถูกเรียกในเทิร์นนี้ (คงไว้เพื่อความเข้ากันได้เดิม)
_MCP_ON = {"names": None}      # cache ชื่อ server ที่เปิดอยู่ (ล้างตอน agent_tools(refresh=True))


# ── agent tools + MCP lazy load + CLARIFY guard (ก่อนส่งเข้า LLM) ───────────
def _mcp_servers_on():
    """มี MCP server ที่เปิดอยู่ใน mcp.json ไหม (cache ต่อ process)

    มี = ส่ง MCP tools เข้า payload ตั้งแต่รอบแรกของทุกเทิร์น/ทุก session เลย
    (ไม่ต้องรอให้โมเดลเรียก mcp_tools ก่อน — เดิมทำให้ MCP ดูเหมือนใช้ไม่ได้จริง)
    ไม่มี = เงียบ ไม่ต่อ server ไม่เปลือง token (ตรงกับพฤติกรรมเดิม)
    """
    if _MCP_ON["names"] is None:
        try:
            cfg = _MCP_HUB.servers() if _MCP_OK else {}
        except Exception:
            cfg = {}
        _MCP_ON["names"] = [k for k, v in cfg.items()
                            if isinstance(v, dict) and v.get("enabled", True)]
    return bool(_MCP_ON["names"])


def agent_tools(refresh=False, include_mcp=None):
    """tools ที่ agent ใช้ได้: tools ในเครื่อง + MCP tools

    include_mcp=None (ดีฟอลต์): รวม MCP เมื่อมี server เปิดอยู่ใน mcp.json —
    ส่งตลอดทุกเทิร์น ทุก session (ต่อ server ครั้งแรกแล้ว cache ไว้) ·
    True/False = บังคับ (ใช้กับจอ soonai mcp)
    """
    if refresh:
        _MCP_ON["names"] = None   # config เปลี่ยน (add/rm/on/off) → นับ server ใหม่
    if include_mcp is None:
        want_mcp = _MCP_LAZY.get("loaded", False) or _mcp_servers_on()
    else:
        want_mcp = bool(include_mcp)
    if want_mcp:
        if refresh or _MCP_DEFS_CACHE["defs"] is None:
            _MCP_DEFS_CACHE["defs"] = list(AGENT_TOOLS) + mcp_hub_for_tools()
        return _MCP_DEFS_CACHE["defs"]
    return list(AGENT_TOOLS)


CLARIFY_GUARD = {"fixed": 0}  # นับครั้งที่ guard ซ่อม system prompt ก่อน generate (เทสต์/debug อ่านได้)


def ensure_clarify_rules(messages):
    """guardrail ตอน generate: system prompt ของแชทต้องมี CLARIFY_RULES ก่อนยิง API
    คุ้มเคส config ถูกทับด้วยค่าเก่า หรือเซสชันที่บันทึกไว้ก่อนกฎถูกเพิ่ม
    ซ่อมเฉพาะ payload ที่กำลังจะส่งนี้ ไม่เขียนทับไฟล์/ประวัติ
    aux prompt (สร้างชื่อ/สรุป/ที่ปรึกษาสกิล) และค่า custom ที่ผู้ใช้เขียนเอง = ไม่แตะ
    """
    try:
        if not messages or messages[0].get("role") != "system":
            return messages
        content = messages[0].get("content") or ""
        if CLARIFY_MARKER in content:
            return messages
        if LEGACY_QUALITY_SYSTEM[:40] not in content:
            # ไม่ใช่ system prompt ของแชท (aux) หรือเป็นค่าที่ผู้ใช้เขียนเอง → เคารพของเดิม
            return messages
        messages[0] = {"role": "system", "content": content + " " + CLARIFY_RULES}
        CLARIFY_GUARD["fixed"] = int(CLARIFY_GUARD.get("fixed", 0)) + 1
    except Exception:
        pass
    return messages


def _ensure_mcp_hint(messages):
    """บอกสถานะ MCP ต่อ system บรรทัดเดียว: มี server = รายชื่อ tools · ไม่มี server แต่ผู้ใช้เพิ่งพิมพ์ถึง mcp = บรรทัดชี้แจงกันโมเดลเดามั่ว"""
    try:
        if not messages or messages[0].get("role") != "system":
            return
        content = messages[0].get("content") or ""
        # marker ของตัว hint เองทั้งสองสาขา — ห้ามใช้คำว่า mcp_tools/mcp__ ตรวจแทน
        # เพราะ AGENT_SYSTEM มีคำเหล่านี้อยู่แล้ว (เคยทำให้โหมด agent ไม่ได้ hint เลย)
        if "[สถานะ MCP" in content or "Tools เสริมนอกเครื่อง (MCP: " in content:
            return
        try:
            from mcp_client import load_mcp_config as _load_mcp
            servers = _load_mcp()
            names = [k for k, v in (servers or {}).items()
                     if isinstance(v, dict) and v.get("enabled", True)]
        except Exception:
            names = []
        if not names:
            # ยังไม่มี server — ใส่เฉพาะตอนผู้ใช้เพิ่งพิมพ์ถึง mcp (กันโมเดลเดาเรื่องภายนอกมั่ว)
            last_user = ""
            for _m in reversed(messages or []):
                if isinstance(_m, dict) and _m.get("role") == "user" \
                        and isinstance(_m.get("content"), str):
                    last_user = _m["content"]
                    break
            if "mcp" not in last_user.lower():
                return
            messages[0] = {"role": "system",
                           "content": messages[0]["content"] +
                           "\n[สถานะ MCP ของ SoonAI] ยังไม่มี server ติดตั้ง — "
                           "ถ้าผู้ใช้ต้องการใช้ MCP ของ SoonAI: ดู soonai mcp catalog · "
                           "ติดตั้ง soonai mcp install <ชื่อ> · ในแชทใช้ /mcp · "
                           "ถ้าผู้ใช้หมายถึง MCP ของ client อื่น (Claude/Cursor ฯลฯ) "
                           "ให้ถามชี้แจงสั้น ๆ ว่าใช้ client ตัวไหน/เชื่อมต่อ service อะไร "
                           "ห้ามเดาว่าหมายถึงตัวไหน และห้ามอ้างไฟล์/พาธ ที่ไม่ได้เห็นจริง"}
            return
        messages[0] = {"role": "system",
                       "content": messages[0]["content"] +
                       "\nTools เสริมนอกเครื่อง (MCP: " + ", ".join(names[:5]) +
                       ") อยู่ในรายการ tools ของรอบนี้แล้ว — เรียก "
                       "mcp__<ชื่อserver>__<ชื่อtool> ได้เลย "
                       "(ดูรายชื่อด้วย mcp_tools ถ้าจำชื่อไม่ได้ ห้ามเดาชื่อเอง)"}
    except Exception:
        pass


# ── checkpoint: สำเนาไฟล์ก่อน agent แก้ ให้ย้อนกลับได้ (/undo) ─────────────
# เก็บแบบเป็นงาน ๆ: <DATA_DIR>/checkpoints/work-<วันเวลา>/index.json + blobs/*
# หลักการ: เฉพาะไฟล์ในโฟลเดอร์งาน · ไม่เก็บไฟล์ต้องห้าม · ไม่เก็บไฟล์ใหญ่ · จำกัดจำนวนต่อเนื่อง
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
CHECKPOINT_MAX_BUCKETS = 12       # เก็บงานล่าสุดกี่ชุด
CHECKPOINT_MAX_RECORDS = 200      # ต่อชุด
CHECKPOINT_MAX_BYTES = 2_000_000  # ต่อไฟล์
_CP = {"bucket": None, "lock": threading.Lock(), "off": False}


def checkpoint_enabled():
    """ปิดได้ด้วย config agent.checkpoints = false (หรือ _CP['off'] ในเทสต์)"""
    if _CP["off"]:
        return False
    try:
        return bool((load_config().get("agent") or {}).get("checkpoints", True))
    except Exception:
        return True


def _cp_prune():
    try:
        dirs = sorted([p for p in CHECKPOINT_DIR.iterdir() if p.is_dir()],
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for old in dirs[CHECKPOINT_MAX_BUCKETS:]:
            shutil.rmtree(old, ignore_errors=True)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:_cp_prune",
                           "กวาด checkpoint เก่าไม่ได้ — โฟลเดอร์จะบวมขึ้นเรื่อย ๆ")


def _cp_bucket():
    """โฟลเดอร์ checkpoint ของงานนี้ (สร้างครั้งแรกที่ใช้)"""
    with _CP["lock"]:
        cur = _CP["bucket"]
        if cur and Path(cur).is_dir():
            return Path(cur)
        name = time.strftime("work-%Y%m%d-%H%M%S") + f"-{os.getpid()}"
        d = CHECKPOINT_DIR / name
        (d / "blobs").mkdir(parents=True, exist_ok=True)
        save_json(d / "index.json", [])
        _CP["bucket"] = str(d)
        _cp_prune()
        return d


def _cp_index(d):
    idx = load_json(Path(d) / "index.json", [])
    return idx if isinstance(idx, list) else []


def checkpoint_file(path, tool="write_file"):
    """สำเนาไฟล์ก่อนแก้ — คืน record หรือ None (ปิดอยู่/นอกโฟลเดอร์งาน/ไฟล์ต้องห้าม/ใหญ่เกิน)"""
    if not checkpoint_enabled():
        return None
    try:
        try:
            p = _resolve_tool_path(path)
        except Exception:
            p = Path(path)
        if outside_workspace(p) or _path_is_sensitive(p):
            return None
        size = p.stat().st_size if p.is_file() else 0
        if size > CHECKPOINT_MAX_BYTES:
            return None
        d = _cp_bucket()
        with _CP["lock"]:
            index = _cp_index(d)
            seq = (index[-1].get("seq", 0) + 1) if index else 1
            rec = {"seq": seq, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "tool": tool,
                   "path": str(p), "had": p.is_file(), "size": size, "blob": ""}
            if rec["had"]:
                blob = d / "blobs" / f"{seq:04d}_{p.name}"
                blob.write_bytes(p.read_bytes())
                rec["blob"] = str(blob)
            index.append(rec)
            if len(index) > CHECKPOINT_MAX_RECORDS:
                index = index[-CHECKPOINT_MAX_RECORDS:]
            save_json(d / "index.json", index)
        return rec
    except Exception:
        return None


def checkpoint_records():
    d = _CP["bucket"]
    if not d or not Path(d).is_dir():
        return []
    return _cp_index(Path(d))


def checkpoint_diff(seq=None):
    """diff ไฟล์ปัจจุบันกับ checkpoint (seq ว่าง = ล่าสุด) — ใช้กับ /diff"""
    import difflib
    recs = checkpoint_records()
    if not recs:
        return "ยังไม่มี checkpoint ในงานนี้"
    rec = recs[-1] if seq in (None, "") else next(
        (r for r in recs if str(r.get("seq")) == str(seq)), None)
    if not rec:
        return f"ไม่พบ checkpoint #{seq}"
    try:
        old = (Path(rec["blob"]).read_text(encoding="utf-8", errors="replace")
               if rec.get("had") and Path(rec.get("blob") or "").is_file() else "")
        cur = Path(rec["path"])
        new = cur.read_text(encoding="utf-8", errors="replace") if cur.is_file() else ""
        lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                          "checkpoint #" + str(rec.get("seq")), "ตอนนี้",
                                          lineterm=""))
        return "\n".join(lines[:80]) if lines else "ไม่มีความต่างจาก checkpoint นี้"
    except Exception as e:
        return f"อ่าน diff ไม่ได้: {e}"


def undo_last(n=1):
    """ย้อนไฟล์จาก checkpoint ล่าสุด n รายการ — คืนข้อความสรุป"""
    recs = checkpoint_records()
    if not recs:
        return "ยังไม่มี checkpoint ในงานนี้ (ยังไม่มีอะไรถูกเขียนทับให้ย้อน)"
    n = max(1, int(n or 1))
    picked = recs[-n:]
    done, failed = [], []
    undone_ids = set()
    for rec in reversed(picked):
        try:
            target = Path(rec["path"])
            if rec.get("had"):
                blob = Path(rec.get("blob") or "")
                if not blob.is_file():
                    failed.append(rec["path"])
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob.read_bytes())
                done.append(f"คืนค่า: {rec['path']}")
            else:
                if target.is_file():
                    target.unlink()
                    done.append(f"ลบ (เดิมไม่มีไฟล์นี้): {rec['path']}")
                else:
                    done.append(f"ข้าม (ไม่มีไฟล์): {rec['path']}")
            undone_ids.add(id(rec))
        except Exception as e:
            failed.append(f"{rec['path']} ({e})")
    try:
        d = _CP["bucket"]
        if d and Path(d).is_dir():
            save_json(Path(d) / "index.json",
                      [r for r in recs if id(r) not in undone_ids])
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:undo_last",
                           "อัปเดตดัชนี checkpoint หลัง undo ไม่ได้ (ไฟล์ที่คืนแล้วยังถูกคืน)")
    out = "\n".join(done)
    if failed:
        out += ("\n" if out else "") + "ย้อนไม่ได้: " + ", ".join(failed)
    return out or "ไม่มีอะไรให้ย้อน"


# ── เครื่องมือ web ของ agent ผ่าน TinyFish (web infra ไม่ใช่ค่ายแชท) ──────────
# Search/Fetch ฟรี ~30 ครั้ง/นาที · key ที่ https://agent.tinyfish.ai/api-keys
TINYFISH_SEARCH_URL = "https://api.search.tinyfish.ai"
TINYFISH_FETCH_URL = "https://api.fetch.tinyfish.ai"
TINYFISH_KEY_HINT = ("ขอ key ฟรีที่ https://agent.tinyfish.ai/api-keys แล้วตั้งด้วย "
                     "env TINYFISH_API_KEY หรือ: soonai key set tinyfish YOUR_KEY "
                     "(หรือต่อ MCP ทั้งชุด: soonai mcp install tinyfish)")


def _tinyfish_key():
    """key ของ TinyFish: keys.json (soonai key set) ก่อน แล้วค่อย env TINYFISH_API_KEY"""
    try:
        return (get_key("tinyfish", load_keys()) or "").strip()
    except Exception:
        return ""


def _tinyfish_search(a):
    """ค้นเว็บผ่าน TinyFish Search API (GET · ฟรี ~30 ครั้ง/นาที)
    คืนข้อความผลลัพธ์ที่อ่านง่าย หรือ 'ERROR: ...' ไม่ raise"""
    a = a or {}
    q = str(a.get("query") or "").strip()
    if not q:
        return "ERROR: ต้องมี query"
    key = _tinyfish_key()
    if not key:
        return f"ERROR: ยังไม่มี TinyFish API key — {TINYFISH_KEY_HINT}"
    url = str((PROVIDERS.get("tinyfish") or {}).get("search_url")
              or TINYFISH_SEARCH_URL)
    params = {"query": q}
    for k in ("location", "language"):
        v = str(a.get(k) or "").strip()
        if v:
            params[k] = v
    intent = str(a.get("intent") or "").strip()
    if intent:
        params["intent"] = intent[:2000]
    try:
        r = _http_session().get(url, params=params,
                                headers={"X-API-Key": key}, timeout=10)
    except Exception as e:
        return f"ERROR: เชื่อมต่อ TinyFish ไม่ได้: {e}"
    if r.status_code != 200:
        return f"ERROR: TinyFish Search HTTP {r.status_code}: {(r.text or '')[:200]}"
    try:
        data = r.json()
    except Exception:
        return "ERROR: TinyFish ตอบกลับไม่ใช่ JSON"
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        return "(ไม่พบผลค้น)"
    out = []
    for i, it in enumerate(rows[:10], 1):
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip() or "(ไม่มีหัวข้อ)"
        u = str(it.get("url") or "").strip()
        snip = str(it.get("snippet") or "").strip()
        dom = str(it.get("domain") or "").strip()
        line = f"{i}. {title}" + (f" ({dom})" if dom else "")
        if u:
            line += f"\n   {u}"
        if snip:
            line += f"\n   {snip}"
        out.append(line)
    return "\n".join(out) or "(ไม่พบผลค้น)"


def _tinyfish_fetch(a):
    """ดึงหน้าเว็บเป็น markdown ผ่าน TinyFish Fetch API (POST · ฟรี)
    คืนข้อความ (title + url + เนื้อหาตัดทอน) หรือ 'ERROR: ...' ไม่ raise"""
    a = a or {}
    url = str(a.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return "ERROR: url ต้องขึ้นต้นด้วย http:// หรือ https://"
    key = _tinyfish_key()
    if not key:
        return f"ERROR: ยังไม่มี TinyFish API key — {TINYFISH_KEY_HINT}"
    try:
        mx = int(a.get("max_chars") or 8000)
    except Exception:
        mx = 8000
    mx = min(max(mx, 200), 20000)   # กันยัดทั้งหน้าเข้าคอนเทกซ์ตส์/OOM (เหมือน read_file)
    payload = {"urls": [url], "format": "markdown", "ttl": 600,
               "per_url_timeout_ms": 45000}
    intent = str(a.get("intent") or "").strip()
    if intent:
        payload["intent"] = intent[:2000]
    fetch_url = str((PROVIDERS.get("tinyfish") or {}).get("fetch_url")
                    or TINYFISH_FETCH_URL)
    try:
        r = _http_session().post(fetch_url, json=payload,
                                 headers={"X-API-Key": key}, timeout=60)
    except Exception as e:
        return f"ERROR: เชื่อมต่อ TinyFish ไม่ได้: {e}"
    if r.status_code != 200:
        return f"ERROR: TinyFish Fetch HTTP {r.status_code}: {(r.text or '')[:200]}"
    try:
        data = r.json()
    except Exception:
        return "ERROR: TinyFish ตอบกลับไม่ใช่ JSON"
    errs = data.get("errors") if isinstance(data, dict) else None
    results = data.get("results") if isinstance(data, dict) else None
    if not (isinstance(results, list) and results and isinstance(results[0], dict)):
        return "ERROR: ไม่มีผลลัพธ์" + (f": {str(errs)[:300]}" if errs else "")
    it = results[0]
    text = it.get("text")
    if isinstance(text, (dict, list)):
        try:
            text = json.dumps(text, ensure_ascii=False)
        except Exception:
            text = str(text)
    text = str(text or "")
    if not text.strip():
        return ("ERROR: ดึงหน้าได้แต่เนื้อหาว่าง"
                + (f" (errors: {str(errs)[:200]})" if errs else ""))
    title = str(it.get("title") or url)
    final = str(it.get("final_url") or it.get("url") or url)
    body = text[:mx] + (f"... (ตัดที่ {mx} ตัวอักษร — เรียกซ้ำด้วย max_chars มากขึ้น)"
                        if len(text) > mx else "")
    return f"{title}\n{final}\n\n{body}"


# ── run_tool: dispatch เครื่องมือฝั่งเครื่องทั้งหมด (fs/cmd/skill/web/mcp) ──
def run_tool(name, args):
    """รัน tool ฝั่งเครื่อง คืนข้อความผลลัพธ์ (ไม่มีการถามยืนยันในนี้)"""
    try:
        _deny = _sensitive_deny(name, args)
        if _deny:
            return _deny
        if str(name or "").startswith("mcp__"):
            return mcp_call_tool(name, args)
        if (name or "") in COMPUTER_TOOL_NAMES:
            return _run_computer_tool(name, args)
        if name == "make_dir":
            return _tool_make_dir(args)
        if name == "write_file":
            return _tool_write_file(args)
        if name == "read_file":
            return _tool_read_file(args)
        if name == "list_dir":
            return _tool_list_dir(args)
        if name == "run_cmd":
            return _tool_run_cmd(args)
        if name == "run_tests":
            return _tool_run_tests(args)
        if name == "edit_file":
            return _tool_edit_file(args)
        if name == "grep":
            return _tool_grep(args)
        if name == "install_skill":
            return _tool_install_skill(args)
        if name == "search_skills":
            return _tool_search_skills(args)
        if name == "web_search":
            return _tool_web_search(args)
        if name == "web_fetch":
            return _tool_web_fetch(args)
        if name == "mcp_tools":
            return _tool_mcp_tools()
        if name == "outline":
            return _tool_outline(args)
        if name == "glob":
            return _tool_glob(args)
        if name == "read_skill":
            return _tool_read_skill(args)
        extra = ""
        try:
            cached = _MCP_DEFS_CACHE.get("defs") or []
            mn = [t.get("function", {}).get("name", "") for t in cached
                  if t.get("function", {}).get("name", "").startswith("mcp__")]
            if mn:
                extra = " + MCP: " + ", ".join(mn[:20])
        except Exception:
            pass
        return (f"ERROR: ไม่รู้จัก tool {name} "
                f"(ที่มีให้ใช้: {', '.join(KNOWN_TOOLS)}{extra})")
    except Exception as e:
        return f"ERROR: {e}"


# ── ร่างกายของแต่ละ tool: ย้ายมาจากใน run_tool เดิมทั้งก้อน — เนื้อหาไม่เปลี่ยน แค่แยกฟังก์ชันให้อ่านง่าย ──
def _workspace_path_error(path):
    """Reject agent file access outside the active workspace."""
    if outside_workspace(path):
        return "ERROR: path outside workspace"
    return ""


def _tool_make_dir(args):
    error = _workspace_path_error(args.get("path", ""))
    if error:
        return error
    p = _resolve_tool_path(args["path"])
    p.mkdir(parents=True, exist_ok=True)
    return f"OK: สร้างโฟลเดอร์ {p}"


def _tool_write_file(args):
    error = _workspace_path_error(args.get("path", ""))
    if error:
        return error
    p = _resolve_tool_path(args["path"])
    checkpoint_file(p, "write_file")
    p.parent.mkdir(parents=True, exist_ok=True)
    data = args.get("content", "")
    p.write_text(data, encoding="utf-8")
    return f"OK: เขียนไฟล์ {p} ({len(data)} ตัวอักษร)"


def _tool_read_file(args):
    error = _workspace_path_error(args.get("path", ""))
    if error:
        return error
    p = _resolve_tool_path(args["path"])
    t = p.read_text(encoding="utf-8", errors="replace")
    try:
        mx = int(args.get("max_chars", 4000))
    except Exception:
        mx = 4000
    mx = min(max(mx, 1), 20000)  # กันยัดทั้งไฟล์เข้าคอนเทกซ์ตส์/OOM
    return t[:mx] + ("..." if len(t) > mx else "")


def _tool_list_dir(args):
    error = _workspace_path_error(args.get("path") or ".")
    if error:
        return error
    p = _resolve_tool_path(args.get("path") or ".")
    items = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
    return "\n".join(items) or "(ว่าง)"


def _tool_run_cmd(args):
    mode = _shell_mode()
    cmd = str((args if isinstance(args, dict) else {}).get("command", "") or "")
    if mode == "off":
        return ("ERROR: run_cmd ของ agent ปิดอยู่ — เปิดได้ด้วย /shell safe "
                "(อ่าน/เทสต์เท่านั้น) หรือ /shell on (เต็ม, รับความเสี่ยงเอง)")
    if mode == "safe" and not _safe_shell_ok(cmd):
        return ("ERROR: โหมด safe รันได้เฉพาะคำสั่งอ่าน/เทสต์ใน allowlist "
                "(คำสั่งเดียว ไม่มี pipe/redirect)")
    why = sandbox_deny(cmd)
    if why:
        return f"ERROR: บล็อกคำสั่งอันตราย: {why} (รันเองใน terminal ของคุณได้)"
    res = run_command_safe(cmd, timeout=120)
    head = "exit=-9 (timeout)" if res["timed_out"] else f"exit={res['code']}"
    if res["error"]:
        head += f" [{res['error']}]"
    return f"{head}\n" + res["out"]


def _tool_run_tests(args):
    if _shell_mode() == "off":
        return ("ERROR: ต้องเปิดโหมด shell ก่อน (safe ก็พอ) — พิมพ์ /shell safe "
                "หรือตั้ง config agent.shell")
    a = args if isinstance(args, dict) else {}
    if _shell_mode() == "safe":
        _cmd = str(a.get("command") or "").strip()
        _eff = _cmd or detect_test_command()
        if not _eff or not _safe_shell_ok(_eff):
            return ("ERROR: โหมด safe รันเทสต์ได้เฉพาะคำสั่งอ่าน/เทสต์ใน allowlist "
                    "(คำสั่งเดียว ไม่มี pipe/redirect)")
    try:
        timeout = int(a.get("timeout") or 600)
    except Exception:
        timeout = 600
    out, _ok = run_tests_command(str(a.get("command") or ""),
                                 timeout=min(max(timeout, 10), 1800))
    return out


def _tool_edit_file(args):
    error = _workspace_path_error(args.get("path", ""))
    if error:
        return error
    p = _resolve_tool_path(args["path"])
    o, n = args.get("old_string", ""), args.get("new_string", "")
    if not o:
        return "ERROR: ต้องระบุ old_string"
    t = p.read_text(encoding="utf-8", errors="replace")
    cnt = t.count(o)
    if cnt == 0:
        return "ERROR: หา old_string ไม่เจอในไฟล์"
    if cnt > 1:
        return f"ERROR: old_string เจอ {cnt} จุด ระบุให้เจาะจงกว่านี้"
    checkpoint_file(p, "edit_file")
    p.write_text(t.replace(o, n, 1), encoding="utf-8")
    return f"OK: แก้ไฟล์ {p}"


def _tool_grep(args):
    try:
        rx = re.compile(args.get("pattern", ""))
    except Exception as e:
        return f"ERROR: regex ไม่ถูกต้อง: {e}"
    root = _resolve_tool_path(args.get("path") or ".")
    targets = ([root] if root.is_file()
               else iter_project_files(root) if root.is_dir() else [])
    hits = []
    for f in targets:
        if not f.is_file() or _path_is_sensitive(f):
            continue  # ห้าม grep ไฟล์ secret (keys/session/log/audit)
        try:
            if f.stat().st_size > 500000:
                continue
            lines = f.read_text(encoding="utf-8", errors="strict").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                hits.append((f, i, line.strip()[:200]))
                if len(hits) >= 400:
                    break
        if len(hits) >= 400:
            break
    if not hits:
        return "(ไม่พบ)"
    # จัดอันดับให้ผลที่ควรอ่านก่อน: ไฟล์ที่เจอหลายจุด → ไฟล์ตื้น → ไฟล์โค้ด
    per = {}
    for f, i, txt in hits:
        per.setdefault(f, []).append((i, txt))

    def _rank(item):
        f, arr = item
        try:
            depth = len(f.relative_to(root).parts)
        except Exception:
            depth = 9
        return (-len(arr), depth, 0 if f.suffix.lower() in CODE_SUFFIXES else 1,
                str(f).lower())

    out = []
    for f, arr in sorted(per.items(), key=_rank):
        for i, txt in arr[:6]:
            out.append(f"{f}:{i}: {txt}")
            if len(out) >= 50:
                break
        if len(out) >= 50:
            break
    head = f"(เจอ {len(hits)} จุดใน {len(per)} ไฟล์" + (
        " — แสดง 50 แรก (แคบ path/pattern ลงเพื่อดูเฉพาะส่วน)" if len(out) >= 50 else ")")
    return head + "\n" + "\n".join(out)


def _tool_install_skill(args):
    nm = str((args if isinstance(args, dict) else {}).get("name") or "").strip().lower()
    if not is_catalog_skill(nm):
        rows = search_catalog(nm or "")
        hint = ", ".join(r["name"] for r in rows[:5]) or "soonai skills catalog"
        return (f"ERROR: ไม่มีสกิล '{nm}' ในแคตตาล็อกในเครื่อง (ที่ใกล้เคียง: {hint}) — "
                "ใช้ search_skills ค้นก่อน")
    if skill_is_declined(nm):
        return (f"ERROR: ผู้ใช้เคยปฏิเสธสกิล {nm} หลายครั้งจนระบบหยุดเสนอ — "
                f"ห้ามติดตั้งเอง ให้เสนองานด้วยวิธีอื่น หรือบอกผู้ใช้ให้เปิดคืนด้วย "
                f"/skills reset {nm} ก่อน")
    ok, msg = install_catalog_skill(nm)
    if not ok and "อยู่แล้ว" in msg:
        return f"สกิล {nm} ติดตั้งอยู่แล้ว — เรียก read_skill(\"{nm}\") อ่านวิธีทําได้เลย"
    if not ok:
        return f"ERROR: {msg}"
    try:
        agent_tools(refresh=True)
    except Exception:
        pass
    record_skill_use(nm)
    return f"{msg} — ต่อไปให้เรียก read_skill(\"{nm}\") อ่านวิธีทําแล้วทําตามขั้นตอนนั้น"


def _tool_search_skills(args):
    a = args if isinstance(args, dict) else {}
    q = str(a.get("query") or "").strip()
    rows = search_catalog(q, boost=skill_usage_boost)
    lines = []
    for r in rows[:8]:
        if r.get("declined"):
            lines.append(f"- {r['name']} (ผู้ใช้เคยปฏิเสธไว้จนระบบหยุดเสนอ — อย่าเสนอซ้ำ "
                         f"และอย่าติดตั้งเอง): {r['description']}")
        elif r["installed"]:
            lines.append(f"- {r['name']} (ติดตั้งอยู่แล้ว — เรียก read_skill อ่านได้เลย): "
                         f"{r['description']}")
        else:
            lines.append(f"- {r['name']} (ยังไม่ติดตั้ง — ขออนุญาตผู้ใช้แล้วเรียก "
                         f"install_skill(\"{r['name']}\") ได้เลย หรือให้ผู้ใช้สั่ง "
                         f"soonai skills add {r['name']}): {r['description']}")
    if a.get("web"):
        wr, why = search_github_skills(q)
        if why:
            lines.append(f"(ค้น GitHub: {why})")
        for r in wr[:5]:
            lines.append(f"- GitHub {r['repo']} ({r['path']}) — {r['description']} "
                         f"(ติดตั้ง: soonai skills add {r['repo']})")
    if not lines:
        return ("(ไม่พบ skill ที่ตรงกับคำค้นนี้ — ดูทั้งหมดได้ด้วย soonai skills catalog "
                "หรือสร้างใหม่ด้วย soonai skills new <ชื่อ>)")
    return "\n".join(lines[:12])


def _tool_web_search(args):
    return _tinyfish_search(args if isinstance(args, dict) else {})


def _tool_web_fetch(args):
    return _tinyfish_fetch(args if isinstance(args, dict) else {})


def _tool_mcp_tools():
    _MCP_LAZY["loaded"] = True
    try:
        defs = agent_tools(refresh=True, include_mcp=True)
    except Exception:
        defs = []
    rows = []
    for d in defs or []:
        fn = d.get("function", {}) if isinstance(d, dict) else {}
        qn = fn.get("name", "")
        if not qn.startswith("mcp__"):
            continue
        try:
            _srv, _tool = _split_mcp_name(qn) if _MCP_OK else (None, None)
        except Exception:
            _srv, _tool = None, None
        label = f"{_srv}/{_tool}" if _srv else qn
        desc = str(fn.get("description", "") or "").replace("\n", " ")[:80]
        rows.append(f"- {label}" + (f" — {desc}" if desc else ""))
        if len(rows) >= 30:
            break
    if not rows:
        return ("(ยังไม่มี MCP tools — เพิ่มด้วย soonai mcp add/install "
                "หรือเช็ก soonai mcp)")
    return ("MCP tools อยู่ใน payload แล้ว — เรียก mcp__* ได้เลย:\n"
            + "\n".join(rows))


def _tool_outline(args):
    max_files = 40
    try:
        max_files = min(60, max(1, int((args or {}).get("max_files") or 40)))
    except Exception:
        pass
    root = _resolve_tool_path((args or {}).get("path") or ".")
    return outline_text(root, max_files=max_files)


def _tool_glob(args):
    import fnmatch
    root = _resolve_tool_path(args.get("path") or ".")
    pat = str(args.get("pattern") or "**/*.py").replace("\\", "/")
    short = pat[3:] if pat.startswith("**/") else pat
    try:
        if root.is_file():
            cands = [root]
        elif root.is_dir():
            cands = iter_project_files(root)
        else:
            cands = []
        found = []
        for x in cands:
            if _path_is_sensitive(x):
                continue
            try:
                rel = str(x.relative_to(root)).replace("\\", "/")
            except Exception:
                rel = x.name
            if (fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, short)
                    or fnmatch.fnmatch(x.name, pat)):
                found.append(rel)
        found = sorted(found)[:100]
    except Exception as e:
        return f"ERROR: {e}"
    return "\n".join(found) or "(ไม่พบ)"


def _tool_read_skill(args):
    nm = (args.get("name", "") if isinstance(args, dict) else "") or ""
    t = read_skill_text(nm)
    if t:
        record_skill_use(nm)   # อ่านสกิลจริง = ใช้สกิลนั้น
    return t or "ERROR: ไม่พบ skill (ดูรายชื่อด้วย /skills)"


def _run_computer_tool(name, args):
    """รัน computer tool ผ่าน gate: re-check สด -> execute -> audit
    (approve() ตรวจรอบแรกไปแล้ว รอบนี้กันสิทธิ์ถูก revoke คั่นกลาง)"""
    a = args if isinstance(args, dict) else {}
    mod, err = _computer_mod()
    if mod is None:
        _computer_audit(name, tool=name, tool_args=a, permission="none",
                        result="DENIED", reason=err)
        return err
    fg = _computer_fg() if (_PERM_OK and name in _PERM.ACTION_TOOLS) else {}
    app = str((fg or {}).get("exe") or "")
    try:
        d = _PERM.evaluate(name, a, _computer_policy(), fg) if _PERM_OK \
            else {"allow": False, "confirm": False, "reason": "ไม่มีระบบ permission",
                  "risk": "denied", "permission": "none"}
    except Exception as e:
        d = {"allow": False, "confirm": False, "reason": f"gate ล้มเหลว: {e}",
             "risk": "denied", "permission": "none"}
    if not d["allow"]:
        _computer_audit(name, tool=name, tool_args=a, permission=d["permission"],
                        result="DENIED", reason=d["reason"], app=app)
        return (f"ERROR: Computer Use ถูกปฏิเสธ: {d['reason']} "
                "(ขอสิทธิ์/ปรับ scope ใน config แล้วลองใหม่)")
    try:
        out_dir = str(DATA_DIR / "computer")
        if name == "computer_screenshot":
            shot = mod.screenshot_png()
            path = mod.save_shot(shot["png"], out_dir)
            res, target = f"OK: screenshot {shot['width']}x{shot['height']} → {path}", path
        elif name == "computer_vision":
            text = computer_vision_analyze(a.get("prompt", ""), a.get("provider", ""),
                                           a.get("model", ""))
            res, target = text[:4000], "vision"
        elif name == "computer_windows":
            exe = (a.get("exe") or "").strip()
            wins = mod.find_process_windows(exe) if exe else mod.list_windows()
            lines = ["%d | %s [%s] %s" % (w.get("hwnd"), (w.get("title") or "")[:60],
                                          w.get("exe") or "?", w.get("rect")) for w in wins[:30]]
            res = "\n".join(lines) or "(ไม่เจอหน้าต่าง)"
            target = exe or "all-windows"
        elif name == "computer_uielements":
            hwnd = a.get("hwnd")
            if not hwnd and (a.get("exe") or "").strip():
                found = mod.find_process_windows(a["exe"].strip())
                if not found:
                    raise mod.ComputerError("ไม่เจอหน้าต่างของ %s" % a["exe"].strip())
                hwnd = found[0]["hwnd"]
            tree = mod.window_tree(int(hwnd) if hwnd else None, max_depth=2, max_nodes=120)
            res = json.dumps(tree, ensure_ascii=False)[:4000] or "(ว่าง)"
            target = "hwnd=%s" % (hwnd or "foreground")
        elif name == "computer_focus":
            hwnd = a.get("hwnd")
            if not hwnd and (a.get("exe") or "").strip():
                found = mod.find_process_windows(a["exe"].strip())
                if not found:
                    raise mod.ComputerError("ไม่เจอหน้าต่างของ %s" % a["exe"].strip())
                hwnd = found[0]["hwnd"]
            if not hwnd:
                raise mod.ComputerError("ต้องระบุ exe หรือ hwnd")
            r = mod.focus_window(int(hwnd))
            res = f"OK: โฟกัส hwnd={r['hwnd']}" + ("" if r["focused"] else " (OS ไม่ยอมให้โฟกัส)")
            target = "hwnd=%s" % r["hwnd"]
        elif name == "computer_ocr":
            shot = mod.screenshot_png()
            path = mod.save_shot(shot["png"], out_dir, "ocr.png")
            try:
                res = mod.ocr_image_file(path) or "(OCR ได้ว่าง)"
            except Exception as e:
                res = f"ERROR: {e}"
            target = path
        elif name == "computer_move":
            r = mod.mouse_move(a.get("x"), a.get("y"))
            res, target = f"OK: เมาส์ → ({r['x']},{r['y']})", "(%s,%s)" % (a.get("x"), a.get("y"))
        elif name == "computer_click":
            mod.mouse_click(a.get("x"), a.get("y"), a.get("button", "left"))
            res, target = f"OK: คลิก ({a.get('x')},{a.get('y')})", "(%s,%s)" % (a.get("x"), a.get("y"))
        elif name == "computer_double_click":
            mod.mouse_double_click(a.get("x"), a.get("y"), a.get("button", "left"))
            res = f"OK: ดับเบิลคลิก ({a.get('x')},{a.get('y')})"
            target = "(%s,%s)" % (a.get("x"), a.get("y"))
        elif name == "computer_right_click":
            mod.mouse_click(a.get("x"), a.get("y"), "right")
            res = f"OK: คลิกขวา ({a.get('x')},{a.get('y')})"
            target = "(%s,%s)" % (a.get("x"), a.get("y"))
        elif name == "computer_drag":
            mod.mouse_drag(a.get("x1"), a.get("y1"), a.get("x2"), a.get("y2"),
                           a.get("button", "left"))
            res = f"OK: ลาก ({a.get('x1')},{a.get('y1')})→({a.get('x2')},{a.get('y2')})"
            target = res[4:]
        elif name == "computer_scroll":
            r = mod.mouse_scroll(a.get("dy", 3), a.get("dx", 0))
            res, target = f"OK: สกรอลล์ dy={r['dy']} dx={r['dx']}", "scroll"
        elif name == "computer_type":
            r = mod.type_text(a.get("text", ""))
            res, target = f"OK: พิมพ์แล้ว {r['typed']} ตัวอักษร", "keyboard"
        elif name == "computer_press":
            mod.press_key(a.get("key", ""))
            res, target = f"OK: กด {a.get('key', '')}", "key=%s" % a.get("key", "")
        elif name == "computer_hotkey":
            keys = a.get("keys") or []
            mod.hotkey(list(keys))
            res, target = f"OK: hotkey {'+'.join(str(k) for k in keys)}", "hotkey"
        elif name == "computer_wait":
            r = mod.wait_ms(a.get("ms", 1000))
            res, target = f"OK: รอ {r['waited_ms']} ms", "wait"
        else:
            raise mod.ComputerError("ไม่รู้จัก computer tool " + str(name))
        _computer_audit(name, target=target, app=app, permission=d["permission"],
                        result=("FAILED" if str(res).startswith("ERROR:") else "SUCCESS"),
                        tool_args=a, tool=name)
        return res
    except Exception as e:
        try:
            msg = str(e)
        except Exception:
            msg = "error"
        _computer_audit(name, app=app, permission=d.get("permission", "?"),
                        result="FAILED", reason=msg[:200], tool_args=a, tool=name)
        return f"ERROR: {msg}"


_MCP_SHORT = {
    "list_directory": "ls", "list_directory_with_sizes": "ls+",
    "directory_tree": "tree", "read_text_file": "cat", "read_file": "cat",
    "read_media_file": "media", "read_multiple_files": "cat×N",
    "write_file": "write", "edit_file": "edit", "create_directory": "mkdir",
    "move_file": "mv", "search_files": "find", "get_file_info": "info",
    "list_allowed_directories": "roots",
}


# ── describe/approve: แสดงผล + ขออนุมัติการเรียก tool ────────────────────────
def _short_disp_path(p, keep=38):
    """ย่อพาธโชว์บนจอ: relative เทียบโฟลเดอร์งาน + ตัดเหลือท้ายที่สำคัญ"""
    try:
        s = str(p or "").replace("\\\\", "\\").strip().strip('"').strip("'")
        if not s:
            return ""
        try:
            rel = str(Path(s).resolve().relative_to(workspace_root())).replace("\\", "/")
            s = "." if rel == "." else rel
        except Exception:
            s = s.replace("\\", "/")
        if len(s) > keep:
            return "…" + s[-(keep - 1):]
        return s
    except Exception:
        try:
            return str(p)[:keep]
        except Exception:
            return ""


def _short_mcp_args(args):
    """ย่อ args ของ MCP เหลือที่ต้องอ่าน (พาธสั้น + รวมลิสต์เป็น ×N)"""
    try:
        if not args:
            return ""
        parts = []
        for k, v in list(args.items())[:4]:
            kl = str(k).lower()
            if kl in ("path", "file", "directory", "cwd", "uri", "target", "dest", "source"):
                parts.append(_short_disp_path(v))
            elif kl in ("paths", "files") and isinstance(v, (list, tuple)):
                parts.append(f"×{len(v)} {_short_disp_path(v[0])}" if v else "×0")
            elif kl in ("excludepatterns", "excludedpatterns", "ignore") and isinstance(v, (list, tuple)):
                parts.append(f"-{len(v)}เว้น")
            elif kl == "pattern":
                parts.append(f"~{str(v)[:24]}")
            else:
                s = _redact_echo(str(v).replace("\n", " ").strip())
                parts.append(f"{k}={s[:24]}" if len(s) > 24 else f"{k}={s}")
        out = ", ".join(p for p in parts if p)
        return out if len(out) <= 80 else out[:79] + "…"
    except Exception:
        return ""


_SECRET_ECHO_RE = re.compile(
    r"sk-[A-Za-z0-9]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|"
    r"AKIA[0-9A-Z]{12,}|bearer\s+[A-Za-z0-9\-._~+/]+=*|"
    r"(?:password|passwd|pwd|api[_-]?key|secret|token)\s*[:=]\s*\S+",
    re.IGNORECASE)


def _redact_echo(s):
    """ปิด secret ในข้อความโชว์จอ/log (กัน key หลุดเข้า approve prompt/SESSION_TOOLS)"""
    try:
        return _SECRET_ECHO_RE.sub("***", str(s or ""))
    except Exception:
        return str(s or "")


def describe_call(name, args):
    if str(name or "").startswith("mcp__"):
        try:
            server, tool = _split_mcp_name(name) if _MCP_OK else (None, None)
        except Exception:
            server, tool = None, None
        short = _MCP_SHORT.get(tool or "", tool or "")
        what = f"{server}/{short}" if server else name
        keys = _short_mcp_args(args if isinstance(args, dict) else {})
        return f"MCP {what}" + (f" ({keys})" if keys else "")
    if name == "make_dir":
        return f"สร้างโฟลเดอร์ {args.get('path', '')}"
    if name == "write_file":
        return f"เขียนไฟล์ {args.get('path', '')} ({len(args.get('content', ''))} ตัวอักษร)"
    if name == "read_file":
        return f"อ่านไฟล์ {args.get('path', '')}"
    if name == "list_dir":
        return f"ดูโฟลเดอร์ {args.get('path', '.')}"
    if name == "run_cmd":
        return f"รันคำสั่ง: {_redact_echo(args.get('command', ''))}"
    if name == "edit_file":
        return f"แก้ไฟล์ {args.get('path', '')}"
    if name == "grep":
        return f"ค้น '{args.get('pattern', '')}' ใน {args.get('path', '.')}"
    if name == "glob":
        return f"หาไฟล์ '{args.get('pattern', '')}' ใน {args.get('path', '.')}"
    if name == "read_skill":
        return f"อ่าน skill {args.get('name', '')}"
    if name == "mcp_tools":
        return "ดู tools เสริม MCP"
    if name == "web_search":
        _q = str(args.get("query", ""))
        return f"ค้นเว็บ: {_q[:60]}" + ("…" if len(_q) > 60 else "")
    if name == "web_fetch":
        _u = str(args.get("url", ""))
        return f"ดึงหน้าเว็บ: {_u[:60]}" + ("…" if len(_u) > 60 else "")
    if name == "computer_screenshot":
        return "แคปหน้าจอ"
    if name == "computer_vision":
        provider = args.get("provider") or "ตาม config"
        model = args.get("model") or "ตาม config"
        return (f"ส่งภาพหน้าจอไปวิเคราะห์กับ {provider}/{model}: "
                f"{_redact_echo(str(args.get('prompt', ''))[:60])}")
    if name == "computer_windows":
        return f"ดูหน้าต่าง ({args.get('exe', 'ทั้งหมด')})"
    if name == "computer_uielements":
        return f"อ่าน UI tree ({args.get('exe') or args.get('hwnd') or 'โฟกัส'})"
    if name == "computer_focus":
        return f"โฟกัสหน้าต่าง ({args.get('exe') or args.get('hwnd') or '?'})"
    if name == "computer_ocr":
        return "OCR หน้าจอ"
    if name in ("computer_click", "computer_double_click", "computer_right_click",
                "computer_move"):
        return f"เมาส์ {name[9:]} ({args.get('x')},{args.get('y')})"
    if name == "computer_drag":
        return (f"ลาก ({args.get('x1')},{args.get('y1')})→"
                f"({args.get('x2')},{args.get('y2')})")
    if name == "computer_scroll":
        return f"สกรอลล์ dy={args.get('dy', 3)}"
    if name == "computer_type":
        return f"พิมพ์ {len(str(args.get('text', '')))} ตัวอักษร"
    if name == "computer_press":
        return f"กดปุ่ม {args.get('key', '')}"
    if name == "computer_hotkey":
        return "hotkey %s" % "+".join(str(k) for k in (args.get("keys") or []))
    if name == "computer_wait":
        return f"รอ {args.get('ms', 1000)} ms"
    return f"เรียก {name}"


_ALLOW_ALL = {"on": False}
_SHELL_WARNED = {"shown": False}  # เตือนครั้งเดียวต่อโปรเซสว่ากำลังรันด้วย shell ที่ผู้ใช้เปิดเอง
_SHELL_OVERRIDE = {"mode": None}  # โหมดเฉพาะเซสชัน (เช่น /test เปิด safe ให้ชั่วคราว ไม่บันทึกลง config)
_ALLOWED_CMDS = set()
_FORCE_TOOLS = {"on": False}  # บังคับให้รอบถัดไปของ agent ต้องลงมือ (ใช้โดย /test)
_ACCESS = {"level": None}  # None=ยังไม่ถาม full=ทั้งหมด ask=ถามทุกครั้ง readonly=อ่านอย่างเดียว denied=ไม่ให้
_APPROVE_LOCK = threading.Lock()  # กันพร้อมต์ขออนุญาตชนกันตอนรันทีมขนาน
_STAFF_CTX = threading.local()  # ชื่อลูกน้องที่กำลังขออนุญาต (งานขนาน)
_TEAM_LOCK = threading.Lock()  # กันเขียน team.json ชนกันตอนรันทีมขนาน


_TEST_CMD_CACHE = {"key": None, "cmds": ()}


def _cmd_sig(name, fargs):
    """ลายเซ็นคำสั่งสำหรับจำรายคำสั่ง (run_cmd=คำสั่งเต็ม, ไฟล์=พาธ+hash เนื้อหา)"""
    import hashlib as _hl
    fargs = fargs if isinstance(fargs, dict) else {}

    def _h(s):
        try:
            return _hl.sha1(str(s or "").encode("utf-8")).hexdigest()[:12]
        except Exception:
            return "x"
    if str(name or "").startswith("mcp__"):
        try:
            s = json.dumps(fargs, sort_keys=True, ensure_ascii=False)
        except Exception:
            return f"{name}::"
        return f"{name}::{s}" if len(s) <= 300 else f"{name}::sha1:{_h(s)}"
    if name in ("run_cmd", "run_tests"):
        return f"{name}::{str(fargs.get('command', '')).strip()}"
    if name == "write_file":
        c = str(fargs.get("content", ""))
        return (f"{name}::{str(fargs.get('path', '')).strip().lower()}"
                f"::{len(c)}::{_h(c)}")
    if name == "edit_file":
        return (f"{name}::{str(fargs.get('path', '')).strip().lower()}"
                f"::{_h(fargs.get('old_string', ''))}"
                f"->{_h(fargs.get('new_string', ''))}")
    if name == "make_dir":
        return f"{name}::{str(fargs.get('path', '')).strip().lower()}"
    if name in ("computer_click", "computer_double_click", "computer_right_click",
                "computer_move"):
        return f"{name}::{fargs.get('x')},{fargs.get('y')}"
    if name == "computer_drag":
        return f"{name}::{fargs.get('x1')},{fargs.get('y1')},{fargs.get('x2')},{fargs.get('y2')}"
    if name in ("computer_press", "computer_type", "computer_hotkey", "computer_scroll",
                "computer_focus"):
        try:
            key = json.dumps(fargs, sort_keys=True, ensure_ascii=False)[:120]
        except Exception:
            key = ""
        return f"{name}::{key}"
    return f"{name}::"


_MCP_FS_FEED = {"list_directory", "list_directory_with_sizes", "directory_tree",
                "read_text_file", "read_file", "read_media_file",
                "read_multiple_files", "search_files", "get_file_info",
                "list_allowed_directories"}
_MCP_FEED_BUDGET = 2000
_MCP_RESULT_BUDGET = 4000
_MCP_FEED_LINES = 60


def _mutates_state(name):
    """tool นี้เปลี่ยนสถานะเครื่อง/ไฟล์ไหม (เปลี่ยน = ล้างแคชผลอ่าน MCP)"""
    try:
        n = str(name or "")
        if n in ("write_file", "edit_file", "make_dir", "run_cmd", "run_tests",
                 "install_skill"):
            return True
        if n in COMPUTER_TOOL_NAMES:
            return n not in ("computer_screenshot", "computer_windows",
                             "computer_uielements", "computer_ocr",
                             "computer_vision", "computer_wait")
        if n.startswith("mcp__"):
            return _mcp_tool_part(n) not in _MCP_FS_FEED
    except Exception:
        pass
    return False


def _mcp_tool_part(name):
    """ส่วนชื่อ tool ท้าย mcp__<server>__<tool> ('' = ไม่ใช่ MCP)"""
    try:
        if not str(name or "").startswith("mcp__"):
            return ""
        if _MCP_OK:
            _srv, _tool = _split_mcp_name(name)
            return _tool or ""
        return str(name).split("__", 1)[-1]
    except Exception:
        return ""


def _compact_tool_feed(name, result):
    """ย่อผล MCP ก่อนยัดกลับให้โมเดล พร้อมบอกชัดว่าตัดส่วนใดออก"""
    try:
        text = str(result or "")
        if not text or not str(name or "").startswith("mcp__"):
            return text
        original_len = len(text)
        if _mcp_tool_part(name) in _MCP_FS_FEED:
            lines = text.splitlines()
            if len(lines) > _MCP_FEED_LINES:
                text = ("\n".join(lines[:_MCP_FEED_LINES])
                        + f"\n… (ตัดเหลือ {_MCP_FEED_LINES}/{len(lines)} บรรทัด)")
            budget = _MCP_FEED_BUDGET
        else:
            budget = _MCP_RESULT_BUDGET
        if len(text) > budget:
            text = (text[:budget]
                    + f"\n… (ตัดเหลือ {budget}/{original_len} ตัวอักษร; เรียก tool เดิมด้วย filter/pagination ได้)")
        return text
    except Exception:
        try:
            return str(result or "")
        except Exception:
            return ""


def workspace_root():
    """โฟลเดอร์งานปัจจุบัน (คุก agent)"""
    try:
        return Path.cwd().resolve()
    except Exception:
        return Path(".").resolve()


def outside_workspace(p):
    """พาธอยู่นอกโฟลเดอร์งานปัจจุบันหรือไม่ (กัน agent เขียนมั่วทั้งเครื่อง)"""
    try:
        rp = _resolve_tool_path(p)
    except Exception:
        return False
    try:
        rp.relative_to(workspace_root())
        return False
    except Exception:
        return True


def preview_diff(name, fargs):
    """ตัวอย่าง diff ก่อนเขียน/แก้ไฟล์จริง (ว่าง = ไม่มีอะไรให้ดู)"""
    import difflib
    try:
        if name == "write_file":
            p = _resolve_tool_path(fargs.get("path", ""))
            old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            new = fargs.get("content", "")
        elif name == "edit_file":
            p = _resolve_tool_path(fargs.get("path", ""))
            old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            o = fargs.get("old_string", "")
            new = old.replace(o, fargs.get("new_string", ""), 1) if o and o in old else old
        else:
            return ""
        lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                          "เดิม", "ใหม่", lineterm=""))
        return "\n".join(lines[:60])
    except Exception:
        return ""


def device_access_popup():
    """ป็อปอัพขอสิทธิ์เข้าถึงเครื่องครั้งแรกของ session
    คืน full/ask/readonly/None(ปฏิเสธ)"""
    try:
        cwd = str(Path.cwd())
    except Exception:
        cwd = "."
    console.print(Panel(
        "[bold]agent ขออนุญาตเข้าถึงเครื่องเพื่อสร้างโปรเจกต์[/bold]\n"
        f"[dim]โฟลเดอร์ทำงาน: {cwd}[/dim]\n"
        "อ่าน/ค้นไฟล์: ทำได้เลยไม่ถาม\n"
        "สร้าง/แก้ไฟล์/รันคำสั่ง: ตามระดับที่เลือก",
        title="ขออนุญาตเข้าถึงเครื่อง", border_style="yellow"))
    console.print("[dim]1 = ทั้งหมดใน session นี้ (ไม่ถามอีก)\n"
                  "2 = ถามเป็นครั้ง ๆ ไป (แนะนำ)\n"
                  "3 = อ่านอย่างเดียว (ไม่เขียน/ไม่รัน)\n"
                  "0 = ไม่อนุญาต[/dim]")
    try:
        ans = Prompt.ask("อนุญาตระดับไหน?", choices=["1", "2", "3", "0"], default="2")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    return {"1": "full", "2": "ask", "3": "readonly"}.get(ans)


def approve(name, desc, fargs, auto_yes):
    """อ่าน/ค้นอย่างเดียวผ่านเลย นอกนั้นถามก่อนแบบมีตัวเลือกชัด ๆ
    y=ครั้งนี้ s=จำคำสั่งนี้ทั้ง session a=ทั้งหมด n=ไม่
    sandbox: คำสั่งทำลายระบบบล็อกทันที (แม้ auto_yes) งานนอกโฟลเดอร์บังคับถาม"""
    if name in ("run_cmd", "run_tests"):
        _r = _gate_shell(name, fargs)
        if _r is not None:
            return _r
    try:
        _sdeny = _sensitive_deny(name, fargs)
    except Exception:
        _sdeny = ""
    if _sdeny:
        console.print(f"[red]{_sdeny[7:] if _sdeny.startswith('ERROR: ') else _sdeny}[/red]")
        return False
    must_ask = False
    if (name or "") in COMPUTER_TOOL_NAMES:
        try:
            allow, confirm, reason, _perm = _computer_gate(name, fargs)
        except Exception as e:
            allow, confirm, reason = False, False, f"gate ล้มเหลว: {e}"
        if not allow:
            console.print(f"[red]Computer Use ถูกปฏิเสธ: {reason}[/red]")
            return False
        if confirm:
            must_ask = True
            console.print(f"[yellow]ต้องยืนยัน (high-risk): {reason}[/yellow]")
        else:
            return True
    if name in ("run_cmd", "run_tests") and _PERM_OK:
        try:
            _rwhy = _PERM.is_high_risk("run_cmd", fargs if isinstance(fargs, dict) else {})
            if _rwhy[0]:
                must_ask = True
                console.print(f"[yellow]ต้องยืนยัน (high-risk): {_rwhy[1]}[/yellow]")
        except Exception:
            pass
    force_ask = False
    if name in ("write_file", "edit_file", "make_dir"):
        try:
            force_ask = outside_workspace((fargs if isinstance(fargs, dict) else {}).get("path", ""))
        except Exception:
            force_ask = False
        if force_ask:
            console.print("[yellow](อยู่นอกโฟลเดอร์งาน — ต้องยืนยันเองทุกครั้ง)[/yellow]")
    if name in ("list_dir", "read_file", "glob", "grep", "outline", "search_skills"):
        # อ่านในโฟลเดอร์งานผ่านเลย — อ่านนอกโฟลเดอร์ต้องยืนยัน
        # (เนื้อไฟล์ที่อ่านจะถูกส่งไปให้ผู้ให้บริการ AI รอบถัดไป = ช่องทางข้อมูลออก)
        try:
            _out_scope = outside_workspace((fargs if isinstance(fargs, dict) else {}).get("path") or ".")
        except Exception:
            _out_scope = True
        if not _out_scope:
            return True
        force_ask = True
        console.print("[yellow](อ่านนอกโฟลเดอร์งาน — ต้องยืนยันเองทุกครั้ง)[/yellow]")
    if name == "read_skill":
        return True
    if name == "mcp_tools":
        return True  # แค่ลิสต์รายชื่อ tools (ต่อ server เกิดตอนรัน — mcp__* ยังต้อง approve แยกทุกครั้ง)
    if name in ("web_search", "web_fetch"):
        return True  # อ่านเว็บสาธารณะอย่างเดียว (TinyFish บล็อก localhost/private IP ฝั่งเซิร์ฟเวอร์เอง)
    if str(name or "").startswith("mcp__") and _mcp_readonly(name):
        return True
    if (auto_yes or _ALLOW_ALL["on"]) and not force_ask and not must_ask:
        return True
    if _cmd_sig(name, fargs) in _ALLOWED_CMDS:
        return True
    if not sys.stdin.isatty():
        return False
    with _APPROVE_LOCK:
        if _ACCESS["level"] is None:
            _ACCESS["level"] = device_access_popup()
    lvl = _ACCESS["level"]
    if lvl == "full" and not force_ask and not must_ask:
        return True
    if lvl in ("readonly", None):
        if lvl == "readonly":
            console.print("[dim](โหมดอ่านอย่างเดียว — ข้ามการเขียน/รัน)[/dim]")
        return False
    return _gate_prompt(name, desc, fargs)


# ── ตัวย่อยของ approve: ประตูเช็ค/ถามจริง (ย้ายจากใน approve — เนื้อเดิมล้วน) ──
def _gate_shell(name, fargs):
    mode = _shell_mode()
    cmd = str((fargs if isinstance(fargs, dict) else {}).get("command", "") or "")
    if mode == "off":
        console.print("[red]shell ของ agent ปิดอยู่ — เปิดแบบปลอดภัยได้ด้วย /shell safe "
                      "(อ่าน/เทสต์เท่านั้น) หรือ /shell on (เต็ม, รับความเสี่ยงเอง)[/red]")
        return False
    if mode == "safe" and name == "run_cmd" and not _safe_shell_ok(cmd):
        console.print("[red]โหมด safe รันได้เฉพาะคำสั่งอ่าน/เทสต์ใน allowlist "
                      "(คำสั่งเดียว ไม่มี pipe/redirect) — ใช้ /shell on ถ้าตั้งใจเปิดเต็ม[/red]")
        return False
    if not _SHELL_WARNED["shown"]:
        _SHELL_WARNED["shown"] = True
        if mode == "safe":
            console.print("[yellow]โหมด shell = safe: รันเฉพาะคำสั่งอ่าน/เทสต์ใน allowlist "
                          "แบบคำสั่งเดียว · env ตัดความลับ · cwd = โฟลเดอร์งาน · มี timeout[/yellow]")
        else:
            console.print("[yellow]โหมด shell = on: shell หลบ blacklist ได้ด้วย wildcard/"
                          "ตัวแปลภาษา จึงไม่ใช่ขอบเขตกัน secret ที่เชื่อถือได้ "
                          "ควรใช้กับงานที่ไว้ใจได้เท่านั้น[/yellow]")
    try:
        why = sandbox_deny(cmd)
    except Exception:
        why = ""
    if why:
        console.print(f"[red]บล็อกคำสั่งอันตราย: {why} (รันเองใน terminal ของคุณได้)[/red]")
        return False
    return None


def _gate_prompt(name, desc, fargs):
    diff = preview_diff(name, fargs)
    if diff:
        from rich.syntax import Syntax
        console.print(Panel(Syntax(diff, "diff"), title=f"ตัวอย่าง: {desc}",
                            border_style="yellow"))
    console.print("[dim]y = ครั้งนี้ · s = จำคำสั่งนี้ (ทั้ง session) · "
                  "a = ทั้งหมดทุกคำสั่ง · n = ไม่[/dim]")
    who = getattr(_STAFF_CTX, "name", "") or ""
    q = f"อนุญาต{f' [{who}]' if who else ''}: {desc}?"
    try:
        with _APPROVE_LOCK:
            ans = Prompt.ask(q, choices=["y", "s", "a", "n"], default="n")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    if ans == "a":
        _ALLOW_ALL["on"] = True
        console.print("[dim](อนุญาตทั้งหมดใน session นี้)[/dim]")
        return True
    if ans == "s":
        _ALLOWED_CMDS.add(_cmd_sig(name, fargs))
        console.print("[dim](จำคำสั่งนี้แล้ว ครั้งต่อไปไม่ถาม)[/dim]")
        return True
    return ans == "y"


def _is_tools_unsupported(resp):
    try:
        t = (resp.text or "")[:600].lower()
    except Exception:
        return False
    return "tool" in t and ("no endpoints" in t or "not support" in t)


# ── health + failover: คุม latency/โควต้า + สลับโมเดล/ค่ายอัตโนมัติ ──────────
_MODEL_DEAD = {}
LAST_MODEL_SWITCH = None
_MODEL_DEAD_TTL = 600  # จำโมเดลพังชั่วคราว 10 นาที (429 ธรรมดาจำแค่ 120 วิ — ดู _failover_free)
_MODEL_SWITCH_TTL = 1800  # switch ที่ไม่มีคน consume เกิน 30 นาที = ทิ้ง (กันของค้างข้ามวัน)
_HEALTH_LOCK = threading.Lock()  # กัน load→pick→mark แข่งกันตอนทีมรันพร้อมกัน
SLOW_TTL = 900        # statusline เตือน ⚠ นาน 15 นาทีหลัง timeout/ล่มล่าสุดของค่าย


def _health_file():
    """ไฟล์จำสุขภาพโมเดลข้ามโปรเซส (ทับด้วย SOONAI_HEALTH_FILE ในเทสต์ได้)"""
    try:
        ov = os.environ.get("SOONAI_HEALTH_FILE", "").strip()
        if ov:
            return Path(ov)
    except Exception:
        pass
    return DATA_DIR / "model_health.json"


def _health_load():
    """โหลด {dead:{k:ts_hasta}, fails:{k:n}, cursor:{p:i}, slow:{ค่าย:ts_timeout}} + ตัดหมดอายุ (พัง= {} ไม่ล่ม)"""
    import time as _t
    h = {"dead": {}, "fails": {}, "cursor": {}, "slow": {}}
    try:
        d = load_json(_health_file(), {})
        if isinstance(d, dict):
            for k in ("dead", "fails", "cursor", "slow"):
                if isinstance(d.get(k), dict):
                    h[k] = dict(d[k])
        now = _t.time()
        h["dead"] = {k: float(v) for k, v in h["dead"].items()
                     if isinstance(v, (int, float)) and float(v) > now}
        h["slow"] = {k: float(v) for k, v in h["slow"].items()
                     if isinstance(v, (int, float)) and 0 <= now - float(v) <= SLOW_TTL}
    except Exception:
        pass
    return h


def _health_key(provider, model):
    return f"{provider}||{model or ''}"


def _health_is_dead(h, provider, model, now=None):
    """ตายค้างดิสก์ไหม (model='' = ตายระดับค่าย)"""
    try:
        import time as _t
        now = now if now is not None else _t.time()
        return float((h.get("dead") or {}).get(_health_key(provider, model), 0)) > now
    except Exception:
        return False


def _health_fails(h, provider, model):
    try:
        return int((h.get("fails") or {}).get(_health_key(provider, model), 0))
    except Exception:
        return 0


def _health_mark_dead(h, provider, model, ttl):
    """จำตัวพัง + นับครั้งพัง + บันทึกดิสก์ (เงียบถ้าเขียนไม่ได้)"""
    try:
        import time as _t
        h.setdefault("dead", {})[_health_key(provider, model)] = _t.time() + max(1, int(ttl))
        k = _health_key(provider, model)
        h.setdefault("fails", {})[k] = _health_fails(h, provider, model) + 1
        save_json(_health_file(), h)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:_health_mark_dead",
                           f"จำสุขภาพโมเดล {provider}/{model} ลงดิสก์ไม่ได้ — จำในรอบนี้เท่านั้น")
    return h


def _health_note_ok(provider, model):
    """โมเดลตอบสำเร็จ: ล้างตัวนับพัง (ให้ดาวกลับมา)"""
    try:
        with _HEALTH_LOCK:
            h = _health_load()
            if _health_fails(h, provider, model) > 0:
                h.setdefault("fails", {})[_health_key(provider, model)] = 0
                save_json(_health_file(), h)
    except Exception:
        pass


def _health_note_slow(provider):
    """บันทึกว่าค่ายนี้เพิ่ง timeout/ล่ม — statusline โชว์ ⚠ ให้เห็นทันที (ระดับค่าย)"""
    try:
        import time as _t
        with _HEALTH_LOCK:
            h = _health_load()
            h.setdefault("slow", {})[str(provider)] = _t.time()
            save_json(_health_file(), h)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:_health_note_slow",
                           f"จำ timeout ของ {provider} ไม่ได้ — statusline จะไม่โชว์ ⚠")


def _unit_cost(provider, model, pricing):
    """ราคาต่อ input 1M tokens (USD) จาก pricing dict — ไม่รู้ราคา = 0.0"""
    try:
        pr = (pricing or {}).get(model) or {}
        if not isinstance(pr, dict):
            return 0.0

        def _f(k):
            try:
                return float(pr.get(k) or 0)
            except Exception:
                return 0.0

        if pr.get("prompt") is not None:      # openrouter: USD/token
            return _f("prompt") * 1e6
        if pr.get("hf_min_in") is not None:   # huggingface: USD/1M
            return _f("hf_min_in")
        if pr.get("puter_in") is not None:    # puter: เซนต์/1M
            return _f("puter_in") / 100.0
    except Exception:
        pass
    return 0.0


def _health_pick(h, provider, scored):
    """เลือกตัวแทน: พังน้อย → ฟรีแท้ก่อน tier → ถูก → วนคิว (rotation กันซ้ำตัวเดิม)"""
    ranked = sorted(scored, key=lambda t: (_health_fails(h, provider, t[0]),
                                           0 if t[1] == "free" else 1, t[2], t[0]))
    try:
        cur = int((h.get("cursor") or {}).get(provider, 0))
    except Exception:
        cur = 0
    pick = ranked[cur % len(ranked)][0]
    try:
        h.setdefault("cursor", {})[provider] = cur + 1
    except Exception:
        pass
    return pick


def _transient_fail(status, body_text):
    if status in (429, 502, 503, 504):
        return True
    t = (body_text if isinstance(body_text, str) else str(body_text or ""))[:600].lower()
    return "no endpoints" in t or "overloaded" in t or "temporarily" in t


def _is_anthropic_family(pid):
    """ค่ายนี้ใช้ Anthropic native API ไหม (ต้องสลับคลาส driver ไม่ใช่แค่เปลี่ยนชื่อ)"""
    try:
        return PROVIDERS.get(pid, {}).get("type") == "anthropic"
    except Exception:
        return False


def _agent_switch_driver(driver, np, nm):
    """สลับ driver ข้ามตระกูล (OpenAI<->Anthropic) คืน driver ที่ใช้ต่อ หรือ None"""
    try:
        cur = getattr(driver, "provider_key", "")
        if _is_anthropic_family(cur) == _is_anthropic_family(np):
            return driver if driver.switched_provider(np, nm) else None
        temp = getattr(driver, "temperature", 0.7)
        if _is_anthropic_family(np):
            return _AnthropicDriver(nm, temp)
        return _OpenAICompatDriver(np, nm, temp)
    except Exception:
        return None


def _chat_family(pid):
    """ตระกูล driver ของค่าย: anthropic / openai / ollama (สลับข้ามตระกูล = สร้าง driver ใหม่
    เพราะ url/payload ต่างกันคนละแบบ — เช่น ollama ต้องยิง /api/chat พร้อม options)"""
    if _is_anthropic_family(pid):
        return "anthropic"
    return "ollama" if pid == "ollama" else "openai"


def _chat_switch_driver(driver, np, nm, messages, temperature, stream,
                        effort, max_tokens, depth):
    """สลับ chat driver (เริ่มรอบใหม่บนค่ายใหม่) คืน driver หรือ None"""
    try:
        cur = getattr(driver, "provider_key", "")
        if _chat_family(cur) == _chat_family(np):
            return driver if driver.switch_provider(np, nm) else None
        return _make_chat_driver(np, nm, messages, temperature, stream,
                                 _chat_effort(np, effort), max_tokens, depth)
    except Exception:
        return None


def _paid_cost(pid, m, pricing):
    """ราคาต่อ 1M tokens สำหรับรอบจ่ายเงิน — ไม่รู้ราคา = inf (ไว้ท้ายสุด)"""
    try:
        pr = (pricing or {}).get(m)
        if not isinstance(pr, dict) or not pr:
            return float("inf")
        return _unit_cost(pid, m, pricing)
    except Exception:
        return float("inf")


def _is_model_not_found(status, body_text):
    """ตรวจเช็กว่า HTTP 400 เกิดจาก model ไม่มีอยู่จริง (ไม่ใช่ bad request ทั่วไป)"""
    if status != 400:
        return False
    t = (body_text if isinstance(body_text, str) else str(body_text or ""))[:1000].lower()
    return any(kw in t for kw in ("failed to load model", "model not found", "invalid model",
                                   "unknown model", "does not exist", "not a valid model"))


def _model_replacement_candidates(provider, model, body_text):
    """คืน slug ที่ endpoint แนะนำก่อนเริ่ม failover ไปโมเดลอื่น"""
    if isinstance(body_text, dict):
        parts = []

        def _collect(value):
            if isinstance(value, dict):
                for item in value.values():
                    _collect(item)
            elif isinstance(value, list):
                for item in value:
                    _collect(item)
            elif value is not None:
                parts.append(str(value))

        _collect(body_text)
        text = " ".join(parts)
    else:
        text = body_text if isinstance(body_text, str) else str(body_text or "")
    candidates = []
    # OpenRouter ใช้ :free เป็น routing variant; เมื่อ variant ถูกปิด
    # paid slug ของโมเดลเดียวกันมักยังใช้งานได้
    lower_text = text.lower()
    if (provider == "openrouter" and str(model).endswith(":free")
            and ("unavailable for free" in lower_text
                 or "paid version is available" in lower_text)):
        candidates.append(str(model)[:-5])
    # รองรับข้อความจาก gateway ที่บอก slug ใหม่โดยตรง
    patterns = (
        r"use\s+this\s*[\r\n ]+slug\s+instead\s*:\s*"
        r"([A-Za-z0-9][A-Za-z0-9._:/-]+)",
        r"use\s+(?:this\s+)?(?:model\s+)?(?:slug\s+)?(?:instead\s*[:\-]?\s*)"
        r"([A-Za-z0-9][A-Za-z0-9._:/-]+)",
        r"(?:use|try)\s+(?:the\s+)?(?:paid\s+)?(?:version|model)\s+"
        r"(?:with\s+)?(?:slug\s+)?([A-Za-z0-9][A-Za-z0-9._:/-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidates.append(match.group(1).rstrip(".,;)"))
    result = []
    for candidate in candidates:
        if candidate and candidate != model and candidate not in result:
            result.append(candidate)
    return result


def _should_try_provider(status, body_text):
    """เคสที่ย้ายข้ามค่ายแล้วมีลุ้น: โควต้าตาย / ล่มชั่วคราว / key ใช้ไม่ได้ / endpoint หาย
    400 (request ผิด) ไม่ย้าย — เปลี่ยนค่ายก็พังเหมือนเดิม
    ยกเว้น 400 ที่เกิดจาก model ไม่มี → สลับโมเดลได้"""
    if _is_model_not_found(status, body_text):
        return True
    try:
        if _quota_dead(status, body_text):
            return True
        if _transient_fail(status, body_text):
            return True
        if status in (401, 403, 404):
            return True
    except Exception:
        pass
    return False


def _failover_free(provider, model, status, body_text, switches_done, max_switches=2):
    """โมเดลฟรี/tier ล่มชั่วคราวหรือหายไป (404): จำตัวพังข้ามโปรเซส + เลือกตัวอื่นแบบไม่ซ้ำ
    เรียงตาม (พังน้อย → ฟรีแท้ก่อน tier → ราคาถูก → วนคิว) คืนโมเดลใหม่หรือ ''"""
    global LAST_MODEL_SWITCH
    import time as _t
    transient = _transient_fail(status, body_text)
    notfound = (status == 404) or _is_model_not_found(status, body_text)
    replacement = _model_replacement_candidates(provider, model, body_text)
    if replacement and switches_done < max_switches:
        LAST_MODEL_SWITCH = {"provider": provider, "from": model,
                             "to": replacement[0], "ts": _t.time()}
        return replacement[0]
    if switches_done >= max_switches or (not transient and not notfound):
        return ""
    try:
        models, pricing = get_models(provider)
    except Exception:
        return ""
    if price_tier(model, provider, pricing) not in ("free", "tier"):
        return ""
    # 429 ธรรมดา (เรทลิมิตรายวิ) จำสั้น ๆ · 404 (โมเดลหาย) จำยาว · อื่น 10 นาที
    ttl = 120 if status == 429 else (3600 if notfound else _MODEL_DEAD_TTL)
    with _HEALTH_LOCK:
        h = _health_load()
        now = _t.time()
        scored = []
        for m in models or []:
            if m == model:
                continue
            tier = price_tier(m, provider, pricing)
            if tier not in ("free", "tier"):
                continue  # ไม่ดึงตัวจ่ายเงินมาเผา
            if _MODEL_DEAD.get((provider, m), 0) > now:
                continue
            if _health_is_dead(h, provider, m, now):
                continue
            scored.append((m, tier, _unit_cost(provider, m, pricing)))
        if not scored:
            return ""
        newm = _health_pick(h, provider, scored)
        _MODEL_DEAD[(provider, model)] = now + ttl  # เก็บ deadline (TTL เดียวกับดิสก์)
        _health_mark_dead(h, provider, model, ttl)
    LAST_MODEL_SWITCH = {"provider": provider, "from": model, "to": newm,
                         "ts": _t.time()}
    console.print(f"[dim](โมเดล {short_model(model)} ใช้ไม่ได้ — สลับไป {short_model(newm)} ให้อัตโนมัติ)[/dim]")
    return newm


_QUOTA_DEAD = {}  # (provider[, model]) -> deadline ที่ห้ามใช้ถึง (จำข้าม loop ในโปรเซส)
_QUOTA_DEAD_TTL = 6 * 3600  # โควต้าตายจำ 6 ชม. (โควต้ารายเดือนไม่ฟื้นใน 10 นาที)


def _quota_dead(status, body_text):
    """โควต้า/เครดิตตายระดับบัญชี (สลับโมเดลค่ายเดิมไม่ช่วย) คืน True/False
    หมายเหตุ: 429 เรทลิมิตรายวินาทีถือว่าชั่วคราว (False) ให้ retry/failover เดิมจัดการ"""
    if status == 402:
        return True
    t = (body_text if isinstance(body_text, str) else str(body_text or ""))[:600].lower()
    if "rate limit" in t and not any(k in t for k in
                                     ("per-day", "perday", "daily", "quota", "credit", "month")):
        return False
    return any(k in t for k in ("deplet", "out of credit", "insufficient",
                                "billing", "payment", "purchase", "subscribe",
                                "quota", "per-day", "perday", "daily", "month"))


def _local_reachable(pid):
    """เช็กค่าย local แบบเงียบ ๆ (ไม่ถามผู้ใช้)"""
    try:
        url = {"ollama": "http://localhost:11434/api/tags",
               "lmstudio": "http://localhost:1234/v1/models"}.get(pid, "")
        if not url:
            return False
        return requests.get(url, timeout=2).status_code == 200
    except Exception:
        return False


def _failover_provider(provider, model, ttl=_QUOTA_DEAD_TTL):
    """หาค่ายอื่นที่มี key: รอบแรกฟรี/tier · รอบสองแบบจ่ายเงิน (ทางสุดท้าย)
    คืน (new_provider, new_model) หรือ ("","") — จำข้ามโปรเซส เรียงตาม
    (พังน้อย → ฟรีแท้ก่อน tier → ถูก → วนคิว · จ่ายเงินไว้ท้ายสุด ถูกสุดก่อน)
    ttl: โควต้าตายจำ 6 ชม. · ค่ายล่มชั่วคราวแล้วหมดตัวจำสั้น (เช่น 1800)"""
    import time as _t
    now = _t.time()
    try:
        ttl = max(60, int(ttl))
    except Exception:
        ttl = _QUOTA_DEAD_TTL
    with _HEALTH_LOCK:
        _QUOTA_DEAD[(provider, model)] = now + ttl
        _QUOTA_DEAD[provider] = now + ttl
        h = _health_load()
        _health_mark_dead(h, provider, model, ttl)
        _health_mark_dead(h, provider, "", ttl)  # จำระดับค่ายด้วย (ห้ามวนกลับค่ายเดิม)
    keys = load_keys()
    for pid, pcfg in PROVIDERS.items():
        if pid == provider or pcfg.get("type") == "anthropic" or pcfg.get("tool_only"):
            continue
        if _QUOTA_DEAD.get(pid, 0) > now:
            continue
        if pcfg.get("no_key"):
            if not _local_reachable(pid):
                continue
        elif not get_key(pid, keys):
            continue
        try:
            models, pricing = get_models(pid)
        except Exception:
            models, pricing = pcfg.get("fallback_models", []), {}
        if not models:
            models, pricing = pcfg.get("fallback_models", []), {}
        with _HEALTH_LOCK:
            h = _health_load()
            if _health_is_dead(h, pid, "", now):
                continue
            scored = [(m, price_tier(m, pid, pricing), _unit_cost(pid, m, pricing))
                      for m in models
                      if is_free_model(m, pid, pricing)
                      and _QUOTA_DEAD.get((pid, m), 0) < now
                      and not _health_is_dead(h, pid, m, now)]
            if not scored:
                continue
            newm = _health_pick(h, pid, scored)
            try:
                save_json(_health_file(), h)  # บันทึก cursor ที่หมุนไป
            except Exception as e:
                _DBG.log_swallowed(e, "soonai.py:_failover_provider",
                                   "บันทึก cursor การหมุนโมเดลฟรีไม่ได้ — รอบหน้าอาจหยิบตัวเดิม")
        console.print(f"[dim](โควต้า {PROVIDERS[provider]['name']} หมด — "
                      f"สลับไป {pcfg['name']} / {short_model(newm)} ให้อัตโนมัติ)[/dim]")
        return pid, newm
    # รอบสอง (ทางสุดท้าย): ฟรีหมดทุกค่ายแล้ว — ใช้ค่ายที่มี key แบบจ่ายเงิน ถูกสุดก่อน
    # (รวมตระกูล Anthropic ด้วย — มี key ถึงมา ไม่มี key ไม่แตะ)
    for pid, pcfg in PROVIDERS.items():
        if pid == provider or pcfg.get("tool_only"):
            continue
        if _QUOTA_DEAD.get(pid, 0) > now:
            continue
        if pcfg.get("no_key"):
            continue  # local ฟรีอยู่แล้ว — รอบแรกเก็บไป ถ้าไม่ติดคือใช้ไม่ได้
        if not get_key(pid, keys):
            continue
        try:
            models, pricing = get_models(pid)
        except Exception:
            models, pricing = pcfg.get("fallback_models", []), {}
        if not models:
            models, pricing = pcfg.get("fallback_models", []), {}
        with _HEALTH_LOCK:
            h = _health_load()
            if _health_is_dead(h, pid, "", now):
                continue
            cands = [(m, _paid_cost(pid, m, pricing))
                     for m in models
                     if _QUOTA_DEAD.get((pid, m), 0) < now
                     and not _health_is_dead(h, pid, m, now)]
            if not cands:
                continue
            cands.sort(key=lambda t: (_health_fails(h, pid, t[0]), t[1], t[0]))
            newm = cands[0][0]
            try:
                save_json(_health_file(), h)
            except Exception as e:
                _DBG.log_swallowed(e, "soonai.py:_failover_provider",
                                   "บันทึก cursor ของค่ายจ่ายเงินไม่ได้ — รอบหน้าอาจหยิบตัวเดิม")
        console.print(f"[dim](ฟรีหมดทุกค่ายแล้ว — สลับไป {pcfg['name']} / "
                      f"{short_model(newm)} แบบจ่ายเงิน)[/dim]")
        return pid, newm
    return "", ""


def _apply_provider_switch(new_provider, new_model, reason):
    """บันทึกการย้ายค่ายลง config + โชว์ panel (failover ข้าม provider)"""
    try:
        cfg = load_config()
        cfg["provider"] = new_provider
        cfg["model"] = new_model
        save_json(CONFIG_FILE, cfg)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:_apply_provider_switch",
                           f"จำการย้ายไปค่าย {new_provider} ไม่ได้ — รอบหน้าจะกลับไปใช้ค่าเดิม")
    try:
        console.print(Panel(
            f"[bold]{PROVIDERS[new_provider]['name']}[/bold] / {new_model}\n"
            f"[dim]สลับค่ายอัตโนมัติ: {reason}[/dim]",
            title="SoonAI chat", border_style="cyan"))
    except Exception:
        pass


def consume_model_switch(provider, model=None):
    """ดึงข้อมูลสลับโมเดลล่าสุด — รับเฉพาะตรงค่าย+ตรงโมเดลต้นทาง ไม่หมดอายุ
    (กันเธรด/รอบอื่นหยิบของคนอื่นไปใช้) ไม่ตรงเงื่อนไข = เก็บไว้ไม่ล้าง"""
    global LAST_MODEL_SWITCH
    sw = LAST_MODEL_SWITCH
    if not isinstance(sw, dict) or sw.get("provider") != provider:
        return None
    if model is not None and sw.get("from") != model:
        return None
    try:
        ts = sw.get("ts", None)
        if ts is not None and time.time() - float(ts) > _MODEL_SWITCH_TTL:
            LAST_MODEL_SWITCH = None
            return None
    except Exception:
        pass
    LAST_MODEL_SWITCH = None
    return sw


def apply_model_switch(provider, model, keys, cfg, sw=None):
    """ถ้ามีการสลับโมเดลอัตโนมัติ: อัปเดต cfg + โชว์ panel คืนโมเดลปัจจุบัน (หรือค่าเดิม)
    sw = switch ของรอบนี้โดยตรง (จาก info) — ไม่มีค่อย fallback global"""
    if sw is None:
        sw = consume_model_switch(provider, model)
    if not sw:
        return model
    if sw.get("from_provider") and sw.get("provider"):
        cfg["provider"] = sw["provider"]
        provider = sw["provider"]
    model = sw["to"]
    cfg["model"] = model
    try:
        save_json(CONFIG_FILE, cfg)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:apply_model_switch",
                           f"จำโมเดลที่สลับอัตโนมัติ ({model}) ไม่ได้ — รอบหน้าจะกลับไปใช้ค่าเดิม")
    console.print(Panel(f"[bold]{PROVIDERS[provider]['name']}[/bold] / {model}\n"
                        f"[dim]สลับอัตโนมัติจาก {sw['from']} (ใช้ไม่ได้)[/dim]",
                        title="SoonAI chat", border_style="cyan"))
    return model


DEFAULT_AGENT_STEPS = 40  # เพดานก้าวเริ่มต้น (กันลูปไม่รู้จบ/เผาโควต้าหลายค่าย)
AGENT_MAX_STEPS = None    # ตั้งจาก CLI --max-steps (None = ใช้ env/default, <=0 = ไม่จำกัด)


# ── นับ token (ประมาณ) + งบ context + ค่าใช้จ่ายโดยประมาณ ────────────────
# ไม่มี tokenizer จริง จึงประเมิน: ASCII ~4 ตัว/token · ตัวอักษรไทย/CJK ~1.5 ตัว/token
# ตัวเลขนี้ใช้เตือน/ตัดประวัติ ไม่ได้ใช้คิดเงินจริง
USAGE = {"calls": 0, "in": 0, "out": 0, "cost": 0.0}


def _kfmt(n):
    n = int(n or 0)
    return str(n) if n < 1000 else f"{n / 1000:.1f}k"


# ── agent loop: driver ทุกค่าย + ลูปเรียก tool + agent_chat ──────────────────
def _agent_step_cap(max_steps):
    """เพดานก้าว agent
    - ส่ง max_steps=N มาตรง ๆ = ใช้ค่านั้น (<=0 = ไม่จำกัด)
    - ไม่ส่ง = ใช้ --max-steps > SOONAI_MAX_STEPS > DEFAULT_AGENT_STEPS
    (ตั้ง 0/ติดลบ = ไม่จำกัด วนจนงานเสร็จหรือผู้ใช้กด Ctrl+C)"""
    if max_steps is not None:
        return max_steps if max_steps and max_steps > 0 else None
    if AGENT_MAX_STEPS is not None:
        return AGENT_MAX_STEPS if AGENT_MAX_STEPS > 0 else None
    raw = os.environ.get("SOONAI_MAX_STEPS", "")
    if str(raw).strip() == "":
        return DEFAULT_AGENT_STEPS
    try:
        v = int(str(raw).strip())
    except Exception:
        return DEFAULT_AGENT_STEPS
    return v if v > 0 else None


def format_agent_done(used, tools, exhausted, max_steps):
    """สรุปปิดงาน agent 1 บรรทัด คืน "" ถ้าไม่มีอะไรให้สรุป
    exhausted = หยุดเพราะชนเพดานก้าว (ยังไม่จบงาน)"""
    tools = tools or []
    if used <= 0 and not tools:
        return ""
    denied = sum(1 for _, st, _ in tools if st == "denied")
    failed = sum(1 for _, st, _ in tools if st == "error")
    wrote = sum(1 for n, st, _ in tools
                if st == "ok" and n in ("write_file", "edit_file", "make_dir"))
    parts = [f"รัน {used} คำสั่ง"]
    if wrote:
        parts.append(f"สร้าง/แก้ไฟล์ {wrote}")
    if denied:
        parts.append(f"ปฏิเสธ {denied}")
    if failed:
        parts.append(f"ล้มเหลว {failed}")
    if exhausted:
        cap = str(max_steps or "")
        parts.append("หยุดที่เพดานก้าว" + (f" {cap}" if cap.isdigit() else "") +
                     " — พิมพ์ต่อเพื่อทำต่อ (หรือ --max-steps 0 = ไม่จำกัด)")
        return "⚠ ยังไม่จบ: " + ", ".join(parts)
    return "✅ เสร็จแล้ว: " + ", ".join(parts)


def agent_summary_line(info, with_usage=True):
    """คืนสรุปบรรทัดเดียวจาก info ของ agent_chat ('' ถ้าไม่มีอะไรให้สรุป)
    ต่อท้ายด้วยการใช้ token/ค่าใช้จ่ายโดยประมาณถ้ามีข้อมูล"""
    if not info:
        return ""
    tools = info.get("tools") or []
    ran = sum(1 for _, st, _ in tools if st != "denied")
    base = format_agent_done(ran, tools,
                             info.get("exhausted", False), info.get("cap", 0))
    if with_usage:
        u = usage_line()
        if u:
            base = (base + " · " + u) if base else u
    return base


def _agent_info(steps, tools, cap, exhausted):
    """ข้อมูลสรุปของลูป agent (ใช้ร่วมกันทั้ง OpenAI-compatible และ Anthropic)"""
    return {"steps": steps, "exhausted": exhausted, "tools": list(tools or []),
            "cap": cap}


class _AgentDriver:
    """ตัวขับ API ของแต่ละค่าย — เก็บเฉพาะส่วนที่ต่างกัน
    (สร้างคำขอ / อ่านคำตอบ / กู้ error) ส่วนลูปอยู่ที่ _agent_loop ที่เดียว
    เพื่อให้พฤติกรรมสองค่ายไม่เพี้ยนออกจากกันเมื่อแก้ที่ไหนสักที่"""

    provider_key = ""
    tag = ""
    retries = 4           # retries ของคำขอหลัก
    fallback_retries = 2  # retries ของคำขอ fallback (ยิงใหม่แบบไม่มี tools)
    can_drop_tools = False       # ยิงใหม่แบบไม่มี tools ได้ไหม
    can_switch_provider = False  # สลับข้ามค่ายได้ไหมเมื่อโควต้าหมด

    def set_key(self):
        """(สร้างใหม่) url + headers จาก key ปัจจุบัน"""
        raise NotImplementedError

    def request(self, messages, force_first, first_step):
        """คืน (url, headers, payload, tag) ของคำขอรอบนี้"""
        raise NotImplementedError

    def fallback_payload(self, payload):
        """payload สำหรับยิงใหม่แบบไม่มี tools (None = ค่ายนี้ไม่มีโหมดนี้)"""
        return None

    def parse(self, resp):
        """คืน (content, calls) — calls ต้องเป็นรูป OpenAI tool_calls เสมอ"""
        raise NotImplementedError

    def switched_provider(self, new_provider, new_model):
        """รับแจ้งว่าสลับค่ายแล้ว (คืน False = ค่ายนี้สลับไม่ได้)"""
        return False

    def error_message(self, status, body):
        return format_api_error(self.provider_key, status, body)


class _OpenAICompatDriver(_AgentDriver):
    """ค่ายมาตรฐาน OpenAI: POST <base>/chat/completions + tool_calls"""

    can_drop_tools = True
    can_switch_provider = True
    tag = "agent-openai"

    def __init__(self, provider, model, temperature):
        self.provider_key = provider
        self.model = model
        self.temperature = temperature
        self.url, self.headers = "", {}
        self.set_key()

    def set_key(self):
        cfg = PROVIDERS[self.provider_key]
        key = get_key(self.provider_key, load_keys())
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        headers.update(cfg.get("extra_headers", {}))
        self.headers = headers
        self.url = cfg["base"].rstrip("/") + "/chat/completions"

    def request(self, messages, force_first, first_step):
        payload = {"model": self.model, "messages": messages,
                   "temperature": self.temperature,
                   "stream": False, "tools": agent_tools(),
                   "tool_choice": "required" if (force_first and first_step) else "auto",
                   "max_tokens": 8192}
        if self.provider_key == "openrouter":
            # บังคับ route เฉพาะ endpoint ที่รองรับ tools (ตาม docs OpenRouter)
            payload["provider"] = {"require_parameters": True}
        return self.url, self.headers, payload, self.tag

    def fallback_payload(self, payload):
        return {k: v for k, v in payload.items()
                if k not in ("tools", "tool_choice", "provider")}

    def parse(self, resp):
        msg = resp.json()["choices"][0]["message"] or {}
        return fix_mojibake(msg.get("content") or ""), list(msg.get("tool_calls") or [])

    def switched_provider(self, new_provider, new_model):
        self.provider_key = new_provider
        self.model = new_model
        self.set_key()
        return True


class _AnthropicDriver(_AgentDriver):
    """Anthropic Messages API (native): system แยกออก + tool_use/tool_result blocks"""

    tag = "agent-anthropic"
    provider_key = "anthropic"
    can_switch_provider = True  # ย้ายออกไปค่ายอื่นได้ (ผ่าน _agent_switch_driver ข้ามตระกูล)

    def __init__(self, model, temperature):
        self.model = model
        self.temperature = temperature
        self.url, self.headers = "", {}
        self.set_key()

    def set_key(self):
        self.url = "https://api.anthropic.com/v1/messages"
        self.headers = {"x-api-key": get_key("anthropic", load_keys()),
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"}

    def request(self, messages, force_first, first_step):
        system, msgs = _to_anthropic_messages(messages)
        body = {"model": self.model, "max_tokens": 8192, "temperature": self.temperature,
                "messages": msgs, "tools": _anthropic_tools(),
                "tool_choice": ({"type": "any"} if (force_first and first_step)
                                else {"type": "auto"})}
        if system:
            body["system"] = system
        return self.url, self.headers, body, self.tag

    def parse(self, resp):
        data = resp.json()
        content, calls = "", []
        for b in data.get("content", []) or []:
            if b.get("type") == "text":
                content += b.get("text", "")
            elif b.get("type") == "tool_use":
                calls.append({"id": b.get("id", ""), "type": "function",
                              "function": {"name": b.get("name", ""),
                                           "arguments": json.dumps(b.get("input", {}),
                                                                   ensure_ascii=False)}})
        return fix_mojibake(content), calls


def _agent_loop(driver, messages, auto_yes=False, on_text=None, max_steps=None,
                force_first=False):
    """ลูปร่วมของ agent ทุกค่าย (ส่วนที่ต่างกันอยู่ใน driver)
    ส่งคำขอ → รัน tool → ส่งผลกลับ → วนจนกว่าจะเสร็จ
    หยุดเมื่อ โมเดลเลิกเรียก tool / error / ชนเพดานก้าว / เรียก tool ที่ไม่มีอยู่ซ้ำ / Ctrl+C
    คืน (ข้อความที่ตอบรวม, error หรือ '', จำนวน tool ที่รัน, info)"""
    collected = ""
    used = 0
    repeat_err = 0
    switches = 0
    switched = None  # switch ล่าสุดของรอบนี้ (ส่งต่อผ่าน info — ไม่พึ่ง global ข้ามเธรด)
    steps = 0
    tools_log = []
    seen_feeds = {}  # sig MCP ที่ได้ผลแล้วในรอบนี้ → ข้ามเรียกซ้ำ (กัน model วน list/read เดิม)
    try:
        _MCP_LAZY["loaded"] = False  # เริ่มรอบใหม่แบบ lean — MCP โหลดเมื่อเรียก mcp_tools เท่านั้น
    except Exception:
        pass
    import itertools
    cap = _agent_step_cap(max_steps)
    ctx_dropped = 0
    net_fails = 0   # timeout/conn ต่อเนื่อง (กันวน failover ทั้งวันเมื่อเน็ตบ้านดับ)
    for step_i in (range(cap) if cap else itertools.count()):
        steps = step_i + 1
        messages, _fit_dropped = fit_messages(messages)
        if _fit_dropped > ctx_dropped:
            ctx_dropped = _fit_dropped
            console.print(f"[dim](ตัดประวัติเก่าให้อยู่ในงบ context ~{_kfmt(context_budget())} "
                          f"token — ตัดไป {ctx_dropped} ข้อความ)[/dim]")
        with console.status(f"[cyan]กำลังคิด… (agent รอบ {step_i + 1})[/]", spinner="dots"):
            url, headers, payload, tag = driver.request(messages, force_first, step_i == 0)
            try:
                r = _post_chat(url, headers=headers, payload=payload,
                               timeout=_chat_timeout(False),
                               stream=False, tag=tag, retries=driver.retries)
            except Exception as e:
                if not _is_timeout_error(e):
                    return (collected, f"ERROR: {e}", used,
                            _agent_info(steps, tools_log, cap, False))
                net_fails += 1
                friendly = _friendly_timeout(e)
                _health_note_slow(driver.provider_key)
                if net_fails > 2:
                    # เน็ต/ค่ายล่มต่อเนื่อง — พอแล้ว คืน error ไทยให้อ่านรู้เรื่อง
                    return (collected, f"ERROR: {friendly}", used,
                            _agent_info(steps, tools_log, cap, False))
                _sig = _agent_timeout_failover(driver, friendly, switches)
                if _sig[0] == "abort":
                    return (collected, f"ERROR: {friendly}", used,
                            _agent_info(steps, tools_log, cap, False))
                driver, switches, switched = _sig[1], _sig[2], _sig[3]
                continue
            if (driver.can_drop_tools and r.status_code == 404 and "tools" in payload
                    and _is_tools_unsupported(r)):
                r, _m = _agent_tools_fallback(driver, r, url, headers, payload, tag)
                if _m is not None:
                    return (collected, f"ERROR: {_m}", used,
                            _agent_info(steps, tools_log, cap, False))
            if r.status_code != 200:
                _sig = _agent_status_failover(driver, r, switches)
                if _sig[0] == "fail":
                    body = _sig[1]
                    return (collected, f"ERROR: {driver.error_message(r.status_code, body)}", used,
                            _agent_info(steps, tools_log, cap, False))
                driver, switches, switched = _sig[1], _sig[2], _sig[3]
                continue
            try:
                content, calls = driver.parse(r)
            except Exception:
                try:
                    _dbg = str(r.text or "")[:150]
                except Exception:
                    _dbg = ""
                return (collected, "ERROR: อ่านคำตอบไม่ได้" + (f" ({_dbg})" if _dbg else ""),
                        used, _agent_info(steps, tools_log, cap, False))
            _track_usage(driver.provider_key, driver.model, payload, content)
            _health_note_ok(driver.provider_key, driver.model)
            if content and not calls:
                # fallback: โมเดลที่ไม่รองรับ native calling จะเขียน JSON มาในข้อความ
                # text_only = ห้ามยัดกลับเป็น tool_calls/tool role (id ปลอยที่ API ไม่รู้จัก → 400)
                for i, (tname, targs) in enumerate(extract_text_calls(content)):
                    calls.append({"id": f"textcall-{i}", "text_only": True,
                                  "type": "function",
                                  "function": {"name": tname,
                                               "arguments": json.dumps(targs, ensure_ascii=False)}})
        if content:
            collected += content
            if on_text:
                on_text(content)
        if not calls:
            _info = _agent_info(steps, tools_log, cap, False)
            if switched:
                _info["model_switch"] = switched
            return collected, "", used, _info
        native = [c for c in calls if not c.get("text_only")]
        if native:
            messages.append({"role": "assistant", "content": content,
                             "tool_calls": [{"id": c.get("id"), "type": "function",
                                             "function": {"name": (c.get("function") or {}).get("name", ""),
                                                          "arguments": (c.get("function") or {}).get("arguments", "{}")}}
                                            for c in native]})
        else:
            # tool call มาจากข้อความล้วน: เก็บเป็น assistant ปกติ + ส่งผลกลับเป็น user
            messages.append({"role": "assistant", "content": content})
        text_results = []
        for c in calls:
            parsed, value = _parse_agent_tool_call(c)
            if not parsed:
                result = value
                messages.append({"role": "tool", "tool_call_id": c.get("id"),
                                 "content": result})
                _agent_tool_log("tool arguments", "invalid", result, False, {}, tools_log)
                continue
            name, fargs = value
            desc = describe_call(name, fargs)
            allowed, result, used = _agent_tool_exec(name, fargs, desc, auto_yes,
                                                     seen_feeds, used)
            _agent_tool_log(desc, name, result, allowed, fargs, tools_log)
            repeat_err, _rep = _agent_tool_repeat(result, c, repeat_err, messages)
            if _rep:
                return (collected,
                        ("เลิกแล้ว: AI เรียก tool ที่ไม่มีอยู่ซ้ำ ๆ "
                         "(ใช้ได้แค่: make_dir, write_file, edit_file, read_file, "
                         "list_dir, grep, glob, outline, run_cmd, run_tests, read_skill, "
                         "search_skills, computer_* "
                         "+ tools ที่ขึ้นต้น mcp__)"),
                        used, _agent_info(steps, tools_log, cap, False))
            _agent_tool_feed(name, result, c, text_results, messages)
        if text_results:
            messages.append({"role": "user",
                             "content": ("ผลจากการเรียก tool ที่โมเดลเขียนมาเป็นข้อความ "
                                         "(ไม่ใช่ native tool call):\n\n" +
                                         "\n\n".join(text_results))})
            text_results = []
    if not collected and used == 0:
        _info = _agent_info(steps, tools_log, cap, True)
        if switched:
            _info["model_switch"] = switched
        return collected, ("ERROR: ชนเพดานก้าวก่อนได้ผล (พิมพ์ต่อเพื่อทำต่อ "
                           "หรือ --max-steps 0 = ไม่จำกัด)"), used, _info
    _info = _agent_info(steps, tools_log, cap, cap is not None and steps > 0)
    if switched:
        _info["model_switch"] = switched
    return collected, "", used, _info


# ── ร่างกายของ _agent_loop: ย้ายมาจากในลูปเดิมทั้งก้อน — เนื้อหาไม่เปลี่ยน ลูปยังเป็นคนตัดสินใจจากสัญญาณที่คืนมา ──
# timeout ในลูป -> คืน ("retry", driver, switches, switched) หรือ ("abort",)
def _agent_timeout_failover(driver, friendly, switches):
    newm = ""
    try:
        newm = _failover_free(driver.provider_key, driver.model, 504,
                              friendly, switches)
    except Exception:
        newm = ""
    if newm:
        switched = {"provider": driver.provider_key, "from": driver.model,
                    "to": newm, "ts": time.time()}
        driver.model = newm
        switches += 1
        return ("retry", driver, switches, switched)
    np = nm = ""
    nd = None
    if driver.can_switch_provider:
        _old_p, _old_m = driver.provider_key, driver.model
        try:
            np, nm = _failover_provider(_old_p, _old_m, ttl=1800)
            nd = _agent_switch_driver(driver, np, nm) if np else None
        except Exception:
            nd = None
    if np and nd:
        driver = nd
        _apply_provider_switch(np, nm, "อ่านคำตอบเกินเวลา — ลองค่ายอื่น")
        switched = {"provider": np, "from": _old_m, "to": nm,
                    "ts": time.time(), "from_provider": _old_p}
        return ("retry", driver, switches, switched)
    return ("abort",)


# ปลายทางไม่รองรับ tools -> ยิงใหม่แบบข้อความ: คืน (r, None)=ok / (None, msg)=error
def _agent_tools_fallback(driver, r, url, headers, payload, tag):
    # ปลายทางไม่มี endpoint รองรับ tools — ยิงใหม่แบบข้อความ แล้วอ่านคำสั่งจากข้อความ
    plain = driver.fallback_payload(payload)
    if plain is not None:
        try:
            r.close()
        except Exception:
            pass
        console.print("[dim](ปลายทางไม่รองรับ tools — ตอบเป็นข้อความแล้วอ่านคำสั่งแทน)[/dim]")
        try:
            r = _post_chat(url, headers=headers, payload=plain,
                           timeout=_chat_timeout(False),
                           stream=False, tag=tag, retries=driver.fallback_retries)
        except Exception as e:
            if _is_timeout_error(e):
                _health_note_slow(driver.provider_key)
            _m = _friendly_timeout(e) if _is_timeout_error(e) else str(e)
            return None, _m
    return r, None


# status != 200 ในลูป -> คืน ("retry", driver, switches, switched) หรือ ("fail", body)
def _agent_status_failover(driver, r, switches):
    try:
        body = r.text[:800]
    except Exception:
        body = ""
    if driver.can_switch_provider and _quota_dead(r.status_code, body):
        old_name = PROVIDERS[driver.provider_key]["name"]
        _old_p, _old_m = driver.provider_key, driver.model
        np, nm = _failover_provider(driver.provider_key, driver.model)
        nd = _agent_switch_driver(driver, np, nm)
        if np and nd:
            driver = nd
            _apply_provider_switch(np, nm, f"โควต้า {old_name} หมด")
            switched = {"provider": np, "from": _old_m, "to": nm,
                        "ts": time.time(), "from_provider": _old_p}
            return ("retry", driver, switches, switched)
    newm = _failover_free(driver.provider_key, driver.model, r.status_code, body,
                          switches)
    if newm:
        switched = {"provider": driver.provider_key, "from": driver.model,
                    "to": newm, "ts": time.time()}
        driver.model = newm
        switches += 1
        return ("retry", driver, switches, switched)
    if driver.can_switch_provider and _should_try_provider(r.status_code, body):
        # ในค่ายหมดตัวแล้ว (หรือ key/endpoint ค่ายนี้ใช้ไม่ได้) → ลองค่ายอื่น จำสั้น
        _old_p, _old_m = driver.provider_key, driver.model
        np, nm = _failover_provider(driver.provider_key, driver.model, ttl=1800)
        nd = _agent_switch_driver(driver, np, nm)
        if np and nd:
            driver = nd
            _apply_provider_switch(
                np, nm,
                f"{PROVIDERS[_old_p]['name']} ใช้ไม่ได้ — ลองค่ายอื่น")
            switched = {"provider": np, "from": _old_m, "to": nm,
                        "ts": time.time(), "from_provider": _old_p}
            return ("retry", driver, switches, switched)
    return ("fail", body)


# approve + รัน tool + update seen_feeds (ข้าม mcp ซ้ำ/ล้างเมื่อ state เปลี่ยน)
def _agent_tool_exec(name, fargs, desc, auto_yes, seen_feeds, used):
    hook_ok, hook_error = _run_project_hook("before_tool", name)
    if not hook_ok:
        return False, hook_error, used
    allowed = approve(name, desc, fargs, auto_yes)
    if allowed:
        used += 1
        try:
            _sig = _cmd_sig(name, fargs)
        except Exception:
            _sig = ""
        if _sig and _sig in seen_feeds and str(name or "").startswith("mcp__"):
            result = f"(ใช้ผลเดิมของ {desc} — ไม่เรียกซ้ำ)"
        else:
            result = run_tool(name, fargs)
            after_ok, after_error = _run_project_hook("after_tool", name)
            if not after_ok:
                result = after_error
            if (_sig and str(name or "").startswith("mcp__")
                    and not str(result).startswith("ERROR:")):
                seen_feeds[_sig] = True
            if not str(result).startswith("ERROR:") and _mutates_state(name):
                seen_feeds.clear()  # เขียน/รันอะไรแล้ว ผลอ่านเดิมหมดอายุทันที
    else:
        result = "ผู้ใช้ปฏิเสธการทำงานนี้"
    return allowed, result, used


# สรุปผลเรียก tool หนึ่งบรรทัด + บันทึก tools_log
def _agent_tool_log(desc, name, result, allowed, fargs, tools_log):
    first = (str(result).splitlines() or [""])[0][:150]
    if allowed and name in ("write_file", "edit_file") \
            and not str(result).startswith("ERROR:"):
        _stat_ln = _diff_stat_line(name, fargs)
        if _stat_ln:
            first += f" ({_stat_ln})"
    console.print(f"[cyan][tool][/] {desc} → [dim]{first}[/dim]")
    if allowed:
        tools_log.append((name, "error" if str(result).startswith("ERROR:") else "ok", first))
    else:
        tools_log.append((name, "denied", first))
    _record_tools([tools_log[-1]])


def _run_project_hook(event, tool):
    """Run an explicitly configured, safe project hook around a tool action."""
    if event not in ("before_tool", "after_tool"):
        return False, "ERROR: unknown project hook"
    try:
        path = Path(workspace_root()) / ".soonai" / "hooks.json"
        if not path.is_file() or path.stat().st_size > 100_000:
            return True, ""
        config = json.loads(path.read_text(encoding="utf-8"))
        command = ((config.get(event) or {}).get(tool)
                   if isinstance(config, dict) else None)
        if not command:
            return True, ""
        command = str(command).strip()
        if not _safe_shell_ok(command):
            return False, f"ERROR: project hook {event}/{tool} ไม่ผ่าน safe-shell"
        result = run_command_safe(command, timeout=30, cwd=workspace_root(), max_output=1000)
        if result.get("timed_out") or result.get("code") != 0:
            return False, f"ERROR: project hook {event}/{tool} failed"
        return True, ""
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return False, f"ERROR: อ่าน project hook ไม่ได้: {exc}"


def _parse_agent_tool_call(call):
    """Parse one model tool call without silently converting invalid JSON to {}."""
    fn = call.get("function") if isinstance(call, dict) else None
    fn = fn if isinstance(fn, dict) else {}
    name = str(fn.get("name") or "").strip()
    raw = fn.get("arguments")
    if not name:
        return False, "ERROR: tool call ไม่มีชื่อ tool"
    try:
        args = json.loads(raw or "{}")
    except (TypeError, ValueError) as exc:
        return False, f"ERROR: arguments ของ tool {name} ไม่ใช่ JSON ที่ถูกต้อง: {exc}"
    if not isinstance(args, dict):
        return False, f"ERROR: arguments ของ tool {name} ต้องเป็น JSON object"
    return True, (name, args)


# นับ tool ที่ไม่รู้จักเรียกซ้ำ -> คืน (repeat_err, ต้องหยุดลูปไหม)
def _agent_tool_repeat(result, c, repeat_err, messages):
    if str(result).startswith("ERROR: ไม่รู้จัก tool"):
        repeat_err += 1
        if repeat_err >= 2:
            messages.append({"role": "tool", "tool_call_id": c.get("id"),
                             "content": str(result)[:4000]})
            return repeat_err, True
    else:
        repeat_err = 0
    return repeat_err, False


# ส่ง feed ของผล tool เข้า messages (text_only -> text_results)
def _agent_tool_feed(name, result, c, text_results, messages):
    if c.get("text_only"):
        try:
            _feed = _compact_tool_feed(name, result)
        except Exception:
            _feed = str(result)
        _budget = _MCP_FEED_BUDGET if str(name or "").startswith("mcp__") else 4000
        text_results.append(f"[ผล {name}]\n{_feed[:_budget]}")
    else:
        try:
            _feed = _compact_tool_feed(name, result)
        except Exception:
            _feed = str(result)
        _budget = _MCP_FEED_BUDGET if str(name or "").startswith("mcp__") else 4000
        messages.append({"role": "tool", "tool_call_id": c.get("id"),
                         "content": _feed[:_budget]})


def _anthropic_tools():
    return [{"name": t["function"]["name"],
             "description": t["function"].get("description", ""),
             "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}})}
            for t in agent_tools()]


def _to_anthropic_messages(messages):
    """แปลง history เป็นรูปแบบ Anthropic คง tool_use/tool_result blocks + กัน role ซ้ำติดกัน"""
    system, out = "", []
    for m in messages or []:
        role, content = m.get("role", "user"), m.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system += content + "\n"
            continue
        if role == "assistant" and m.get("tool_calls"):
            blocks = []
            if content:
                blocks.append({"type": "text", "text": content})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    inp = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    inp = {}
                blocks.append({"type": "tool_use", "id": tc.get("id", ""),
                               "name": fn.get("name", ""),
                               "input": inp if isinstance(inp, dict) else {}})
            item = {"role": "assistant", "content": blocks}
        elif role == "tool":
            item = {"role": "user", "content": [{"type": "tool_result",
                                                 "tool_use_id": m.get("tool_call_id", ""),
                                                 "content": str(content)}]}
        else:
            item = {"role": "assistant" if role == "assistant" else "user",
                    "content": content if isinstance(content, str) else str(content)}
        if out and out[-1]["role"] == item["role"]:
            prev = out[-1]["content"]
            cur = item["content"]
            prev_blocks = prev if isinstance(prev, list) else [{"type": "text", "text": prev}]
            cur_blocks = cur if isinstance(cur, list) else [{"type": "text", "text": cur}]
            out[-1]["content"] = prev_blocks + cur_blocks
        else:
            out.append(item)
    return system.strip(), out


def _agent_steps(provider, model, messages, temperature, auto_yes=False, on_text=None,
                 max_steps=None, force_first=False):
    """ลูป agent รอบเดียวของค่าย OpenAI-compatible (โควต้าหมด = สลับข้ามค่ายให้อัตโนมัติ)
    คืน (ข้อความที่ตอบรวม, error หรือ '', จำนวน tool ที่รัน, info)
    force_first = บังคับเรียก tool ในรอบแรก (งานชัดว่าให้ลงมือทำ)"""
    if PROVIDERS[provider].get("type") == "anthropic":
        return ("", "agent mode ยังไม่รองรับ Claude ใน CLI ตอนนี้", 0,
                _agent_info(0, [], 0, False))
    return _agent_loop(_OpenAICompatDriver(provider, model, temperature), messages,
                       auto_yes=auto_yes, on_text=on_text, max_steps=max_steps,
                       force_first=force_first)


def _agent_steps_anthropic(model, messages, temperature, auto_yes=False, on_text=None,
                           max_steps=None, force_first=False):
    """ลูป agent ผ่าน Anthropic Messages API (native) — ใช้ลูปร่วมตัวเดียวกับค่าย OpenAI
    คืน (ข้อความ, error, จำนวน tool ที่รัน, info)"""
    return _agent_loop(_AnthropicDriver(model, temperature), messages,
                       auto_yes=auto_yes, on_text=on_text, max_steps=max_steps,
                       force_first=force_first)


FILEOP_HINTS = (
    "สร้างไฟล์", "เขียนไฟล์", "สร้างโฟลเดอร์", "สร้างโฟลเดอร์", "แก้ไฟล์",
    "แก้ไขไฟล์", "ลบไฟล์", "ลบโฟลเดอร์", "บันทึกไฟล์", "สร้างเว็บ",
    "สร้างโปรเจค", "สร้างโปรเจกต์", "ทำเว็บ", "ทำเว็บ",
    "อ่านไฟล์", "ดูไฟล์", "รันคำสั่ง",
    "create file", "write file", "save file", "edit file", "delete file",
    "make dir", "mkdir", "create folder", "create directory",
    "create project", "build website",
)
QUESTION_HINTS = ("?", "วิธี", "อย่างไร", "ยังไง", "ทำไม", "คืออะไร", "หมายความ", "สอนหน่อย")

NUDGE = ("คำสั่งเดิมยังค้างอยู่: ใช้ tool ที่ระบบให้มา "
         "(glob/grep/read_file สำรวจ แล้ว make_dir/write_file/edit_file ลงมือ) "
         "ทำงานให้เสร็จทันที ห้ามตอบปฏิเสธหรืออธิบายวิธีทำแทน")


def fileop_intent(text):
    """ข้อความนี้ดูเหมือนสั่งงานไฟล์/เครื่อง (ไม่ใช่คำถามวิธีทำ) หรือไม่"""
    t = (text or "").lower()
    if any(q in t for q in QUESTION_HINTS):
        return False
    return any(k in t for k in FILEOP_HINTS)


def env_context():
    """บอกพาธจริงของเครื่องให้โมเดล (กันเดา username มั่วอย่าง C:/Users/YourUsername)"""
    import os
    try:
        home = str(Path.home())
        desktop = str(Path.home() / "Desktop")
        cwd = str(Path.cwd())
        return (f"[เครื่องนี้: {os.name} | โฮม: {home} | Desktop: {desktop} | "
                f"โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้นสำหรับสร้างไฟล์ ถ้าผู้ใช้ไม่บอกที่อื่น): {cwd} | "
                f"ใช้พาธเหล่านี้ตรง ๆ ห้ามเดา username เอง]")
    except Exception:
        return ""


def agent_chat(provider, model, messages, temperature, auto_yes=False, on_text=None,
               max_steps=None, expect_tools=False, force_first=False):
    """วนลูปเรียก tool จนงานเสร็จ ไม่จำกัดก้าว (หยุดเมื่อโมเดลเลิกเรียก tool / error / Ctrl+C)
    กระตุ้นซ้ำ 1 รอบถ้าโมเดลไม่เรียก tool ทั้งที่ควรเรียก
    คืน (ข้อความรวม, error หรือ '', จำนวน tool ที่รัน, info)"""
    ensure_clarify_rules(messages)
    _ensure_mcp_hint(messages)
    _ensure_skills_hint(messages)
    # auto-suggest: งานนี้ตรงกับ skill ที่ยังไม่ติดตั้งไหม (ถามก่อนติดตั้งเสมอ)
    try:
        _task_txt = ""
        for _m in reversed(messages or []):
            if isinstance(_m, dict) and _m.get("role") == "user" \
                    and isinstance(_m.get("content"), str):
                _task_txt = _m["content"]
                break
        # พกสกิลที่ผู้ใช้ใช้บ่อยข้ามโฟลเดอร์ (ครั้งเดียวต่อเซสชัน) + สกิลที่ตรงกับงานนี้
        _auto_ready = carryover_skills(auto_yes=auto_yes)
        for _nm in autosuggest_skill(_task_txt, auto_yes=auto_yes):
            if _nm not in _auto_ready:
                _auto_ready.append(_nm)
        if _auto_ready:
            _ensure_skills_hint(messages)
            _hint_use_skill(messages, _auto_ready)
    except Exception:
        pass
    _attach_symbol_map(messages)
    if PROVIDERS[provider].get("type") == "anthropic":
        def step_fn():
            return _agent_steps_anthropic(model, messages, temperature,
                                          auto_yes=auto_yes, on_text=on_text,
                                          max_steps=max_steps,
                                          force_first=force_first)
    else:
        def step_fn():
            return _agent_steps(provider, model, messages, temperature,
                                auto_yes=auto_yes, on_text=on_text,
                                max_steps=max_steps,
                                force_first=force_first)
    total, used_total = "", 0
    last_info = {"steps": 0, "exhausted": False, "tools": []}
    kept_switch = None
    for attempt in range(2):
        collected, err, used, info = step_fn()
        total += collected
        used_total += used
        last_info = info
        try:
            if (info or {}).get("model_switch"):
                kept_switch = (info or {})["model_switch"]
            elif kept_switch:
                last_info = dict(last_info or {})
                last_info["model_switch"] = kept_switch
        except Exception:
            pass
        if err or used > 0 or not expect_tools or attempt == 1:
            return total, err, used_total, last_info
        if collected:
            messages.append({"role": "assistant", "content": collected})
        messages.append({"role": "user", "content": NUDGE})
        console.print("[dim](โมเดลยังไม่เรียก tool — กระตุ้นอีกครั้ง…)[/dim]")
    return total, "", used_total, last_info


# ================= AGI: ตั้งเป้าแล้วทำเอง + จำข้าม session =================
AGI_PLAN_MAX_STEPS = 12
AGI_STEP_RETRY = 3
MEMORY_FILE = DATA_DIR / "memory.json"
MEMORY_MAX_FACTS = 50
_REFLECTED_SIDS = set()


def agi_plan_goal(provider, model, goal, temperature=0.3):
    """แตกเป้าหมายใหญ่เป็นขั้นสั้น ๆ คืน [str] (สูงสุด AGI_PLAN_MAX_STEPS, ไม่ได้ = [])"""
    import re
    try:
        env = env_context()
    except Exception:
        env = ""
    msgs = [{"role": "system",
             "content": ("You break a big goal into short ordered steps. Reply in Thai. "
                         f"Output numbered lines 'N. ...' only, max {AGI_PLAN_MAX_STEPS} steps. "
                         "Each step = one concrete action doable with file/read/run tools. "
                         "No intro, no outro.")},
            {"role": "user",
             "content": f"เป้าหมาย:\n{(goal or '')[:2000]}\n\n{env}\n\nแตกเป็นขั้น:"}]
    try:
        out = send_messages(provider, model, msgs, temperature,
                            stream=False, effort="", max_tokens=800) or ""
    except Exception:
        return []
    steps = []
    for line in out.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\d+)[).:：]\s*(.+)$", s)
        if m:
            s = m.group(2).strip()
        elif s[0] in "*-•–-":
            s = s[1:].strip()
            m2 = re.match(r"^(\d+)[).:：]\s*(.+)$", s)
            if m2:
                s = m2.group(2).strip()
        else:
            continue
        if not s or len(s) < 2:
            continue
        try:
            s = _clean_title(s, 100)
        except Exception:
            pass
        if s and s not in steps:
            steps.append(s)
        if len(steps) >= AGI_PLAN_MAX_STEPS:
            break
    return steps


def _agi_auto_heuristic(text):
    """เกณฑ์ด่านแรกในเครื่อง: งานไฟล์ที่ดูหลายขั้น (ไม่ยิง API)"""
    t = str(text or "")
    if not fileop_intent(t):
        return False
    tl = t.lower()
    multi = sum(1 for k in FILEOP_HINTS if k and k in tl) >= 2
    long_multi = len(t) >= 40 and any(
        w in t for w in ("และ", "แล้ว", "จากนั้น", "เสร็จแล้ว", "พร้อม", "ทั้ง", "ทีละ"))
    numbered = bool(__import__("re").search(r"(^|\n)\s*[12][).:]", t))
    return multi or long_multi or numbered


def agi_should_auto(provider, model, question):
    """ด่านสอง: ถามโมเดลสั้น ๆ ว่าเป็นเป้าหมายใหญ่หลายขั้นหรือไม่ (ล้มเหลว = False)"""
    msgs = [{"role": "system",
             "content": ("Decide if the user request needs multi-step autonomous work "
                         "(plan + file edits + run + verify). "
                         "Reply with ONLY one word: YES or NO.")},
            {"role": "user", "content": f"งานนี้ต้องทำหลายขั้นเองหรือไม่:\n{(question or '')[:800]}"}]
    try:
        out = (send_messages(provider, model, msgs, 0.0,
                             stream=False, effort="", max_tokens=20) or "").strip().upper()
    except Exception:
        return False
    return out.startswith("YES") or "ใช่" in out or out.startswith("TRUE")


def agi_check_step(provider, model, goal, step, result_tail):
    """ตรวจขั้นสั้น ๆ แบบเงียบ คืน (ok: bool, note: str)"""
    msgs = [{"role": "system",
             "content": ("You verify one completed step of a bigger goal. "
                         "Reply in Thai, format EXACTLY: PASS or FAIL: <1 line reason>. "
                         "Nothing else.")},
            {"role": "user",
             "content": (f"เป้าหมาย: {(goal or '')[:500]}\nขั้น: {step}\n"
                         f"ผลที่ทำมา:\n{(result_tail or '')[-2000:]}")}]
    try:
        out = (send_messages(provider, model, msgs, 0.2,
                             stream=False, effort="", max_tokens=300) or "").strip()
    except Exception as e:
        return False, f"ตรวจไม่ได้: {e}"
    up = out.upper()
    if up.startswith("PASS"):
        return True, out[4:].strip(" :")
    if up.startswith("FAIL"):
        return False, out[4:].strip(" :")
    return True, out[:200]


def agi_run_loop(provider, model, history, goal, temperature, auto_yes, on_text=None):
    """รันเป้าหมายแบบ planner → executor → verifier คืน (สรุป, error)"""
    steps = agi_plan_goal(provider, model, goal)
    if not steps:
        return "", "แตกแผนไม่ได้ — ลองเล่าเป้าหมายให้ชัดขึ้น หรือสั่งทีละขั้น"
    console.print(Panel("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)),
                        title=f"AGI เป้าหมาย ({len(steps)} ขั้น)", border_style="cyan"))
    transcript = list(history or [])
    report = []
    for i, step in enumerate(steps, 1):
        console.print(f"[bold cyan][AGI {i}/{len(steps)}][/] {step}")
        step_user = (f"[AGI เป้าหมายหลัก: {goal}]\nทำขั้นที่ {i}/{len(steps)}: {step}\n"
                     "เสร็จแล้วสรุปสั้น ๆ 1-2 บรรทัดว่าทำอะไรไป")
        note, step_msgs = "", None
        ok_step, used_total, last_err = False, 0, ""
        for attempt in range(1, AGI_STEP_RETRY + 1):
            if step_msgs is None:
                step_msgs = _agent_msgs(transcript + [{"role": "user", "content": step_user}])
            else:
                step_msgs = step_msgs + [{"role": "user",
                                          "content": f"ครั้งก่อนติด: {note} แก้แล้วทำขั้นนี้ต่อ"}]
            try:
                collected, err, used, _info = agent_chat(
                    provider, model, step_msgs, temperature, auto_yes=auto_yes,
                    expect_tools=True, force_first=(attempt == 1), on_text=on_text)
            except (TurnCancelled, KeyboardInterrupt):
                raise
            except Exception as e:
                err, collected, used = f"ERROR: {e}", "", 0
            used_total += used
            if err:
                last_err = err
                break
            ok_step, note = agi_check_step(provider, model, goal, step, collected)
            transcript.append({"role": "user", "content": step_user})
            transcript.append({"role": "assistant",
                               "content": f"[AGI ขั้น {i}/{len(steps)}: {step}]\n{collected[-1500:]}"})
            if ok_step:
                break
            console.print(f"[yellow](ขั้น {i} ยังไม่ผ่าน: {note} — ลองใหม่ {attempt}/{AGI_STEP_RETRY})[/yellow]")
        if last_err:
            report.append(f"❌ ขั้น {i} {step}: {last_err}")
            return ("AGI หยุดกลางคัน:\n" + "\n".join(report), last_err)
        if ok_step:
            report.append(f"✅ ขั้น {i} {step}")
        else:
            report.append(f"⚠️ ขั้น {i} {step}: ไม่ผ่านตรวจ ({note}) — ข้ามไปขั้นต่อไป")
    return ("AGI เสร็จ:\n" + "\n".join(report), "")


def _agent_msgs(history):
    """ประกอบ messages สำหรับ agent: system + AGENT_SYSTEM + env + snapshot + memory โปรเจค"""
    msgs = list(history or [])
    if msgs and msgs[0].get("role") == "system":
        msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n" + AGENT_SYSTEM}
    else:
        msgs = [{"role": "system", "content": AGENT_SYSTEM}] + msgs
    try:
        _env = env_context()
        if _env and msgs and msgs[0].get("role") == "system":
            msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n" + _env}
    except Exception:
        pass
    try:
        snap = project_snapshot()
        if snap and msgs and msgs[0].get("role") == "system":
            msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n" + snap}
    except Exception:
        pass
    try:
        _attach_project_memory(msgs)
    except Exception:
        pass
    return msgs


# ── memory + reflect + JSON utils (จำข้าม session) ───────────────────────────
def load_memory(path=None):
    """โหลดความจำระยะยาว {facts: [...], updated} (ไม่มี/พัง = ว่าง)"""
    try:
        d = json.loads(Path(path or MEMORY_FILE).read_text(encoding="utf-8"))
        facts = [str(x).strip() for x in d.get("facts", []) if str(x).strip()]
        return {"facts": facts[:MEMORY_MAX_FACTS], "updated": d.get("updated", "")}
    except Exception:
        return {"facts": [], "updated": ""}


def save_memory(mem, path=None):
    try:
        from datetime import datetime
        mem = {"facts": list((mem or {}).get("facts", []))[:MEMORY_MAX_FACTS],
               "updated": datetime.now().isoformat(timespec="seconds")}
        _atomic_write_text(path or MEMORY_FILE, json.dumps(mem, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def memory_block(mem=None, max_chars=1500):
    """บล็อกความจำสำหรับแปะท้าย system prompt (ว่าง = '')"""
    try:
        facts = (mem if mem is not None else load_memory()).get("facts", [])
    except Exception:
        return ""
    facts = [f for f in facts if f]
    if not facts:
        return ""
    text = "\n[ความจำระยะยาว AGI — ใช้ประกอบการตอบ]\n" + \
        "\n".join(f"- {f}" for f in facts)
    return text[:max_chars]


def attach_memory(history):
    """เติม memory ลง system message (ครั้งเดียว) คืน True ถ้าเติม"""
    try:
        if not history or history[0].get("role") != "system":
            return False
        if "[ความจำระยะยาว" in (history[0].get("content") or ""):
            return False
        block = memory_block()
        if not block:
            return False
        history[0] = {"role": "system", "content": history[0]["content"] + block}
        return True
    except Exception:
        return False


def remember_fact(text, path=None):
    """จำข้อเท็จจริง 1 ข้อ (ตัดซ้ำ/คุมยาว/คุมจำนวน) คืน True ถ้าบันทึกใหม่"""
    try:
        clean = _clean_title(text, 200)
    except Exception:
        clean = str(text or "").strip()
    if not clean:
        return False
    mem = load_memory(path)
    norm = clean.lower()
    for f in mem["facts"]:
        fl = f.lower()
        if fl == norm or norm in fl or fl in norm:
            return False
    mem["facts"].append(clean)
    mem["facts"] = mem["facts"][-MEMORY_MAX_FACTS:]
    return save_memory(mem, path)


def _parse_json_block(text):
    """ดึง JSON object ก้อนแรกจากข้อความโมเดล (ไม่ได้ = {})"""
    import re
    try:
        s = re.sub(r"^```[a-zA-Z]*|```$", "", str(text or "").strip(),
                   flags=re.MULTILINE).strip()
        start = s.find("{")
        end = s.rfind("}")
        if start < 0 or end <= start:
            return {}
        d = json.loads(s[start:end + 1])
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def reflect_session(provider, model, history):
    """สกัดข้อเท็จจริงถาวร + โน้ต AGENTS.md จากบทสนทนา คืน (facts, notes)"""
    convo = [m for m in (history or []) if isinstance(m, dict)
             and m.get("role") in ("user", "assistant")][-30:]
    if sum(1 for m in convo if m.get("role") == "user") < 2:
        return [], []
    lines = []
    for m in convo:
        c = str(m.get("content", "") or "")
        lines.append(f"{m.get('role')}: {c[:300]}")
    known = "; ".join(load_memory().get("facts", [])[-20:])
    msgs = [{"role": "system",
             "content": ("You extract durable long-term memory from a chat. Reply in Thai, "
                         "JSON ONLY: {\"facts\": [...], \"agents_notes\": [...]}. "
                         "facts = user preferences, project conventions, paths, toolchains "
                         "(max 8, short). agents_notes = notes for AGENTS.md (max 5, short). "
                         "Skip chit-chat. NEVER include passwords, tokens, keys, secrets.")},
            {"role": "user",
             "content": (f"จำไว้แล้ว: {known}\n\nบทสนทนา:\n" + "\n".join(lines) +
                         "\n\nสกัดเป็น JSON:")}]
    try:
        out = send_messages(provider, model, msgs, 0.2,
                            stream=False, effort="", max_tokens=600) or ""
    except Exception:
        return [], []
    d = _parse_json_block(out)

    def _clean_list(v):
        out = []
        for x in (v or [])[:8]:
            try:
                s = _clean_title(x, 200)
            except Exception:
                s = ""
            if s and s not in out:
                out.append(s)
        return out

    return _clean_list(d.get("facts")), _clean_list(d.get("agents_notes"))[:5]


def maybe_reflect(provider, model, history, sid):
    """สะท้อนบทสนทนาเป็นความจำเมื่อจบ session (ถามก่อนบันทึกเสมอ)"""
    key = sid or "unsaved"
    if key in _REFLECTED_SIDS:
        return
    if not sys.stdin.isatty():
        return
    try:
        facts, notes = reflect_session(provider, model, history)
    except Exception:
        return
    if not facts and not notes:
        return
    _REFLECTED_SIDS.add(key)
    try:
        lines = []
        for f in facts:
            lines.append(f"  • จำ: {f}")
        for n in notes:
            lines.append(f"  • โน้ต AGENTS.md: {n}")
        console.print(Panel("\n".join(lines), title="AGI สะท้อนบทสนทนา",
                            border_style="magenta"))
        if Prompt.ask("บันทึกความจำ + โน้ตเหล่านี้?", choices=["y", "n"],
                      default="y") != "y":
            console.print("[dim]ไม่บันทึก[/dim]")
            return
        for f in facts:
            remember_fact(f)
        if notes:
            try:
                agf = Path.cwd() / "AGENTS.md"
                cur = agf.read_text(encoding="utf-8") if agf.is_file() else "# AGENTS.md\n"
                add = [n for n in notes if n not in cur]
                if add:
                    if "บันทึกจาก SOONAI" not in cur:
                        cur += "\n## บันทึกจาก SOONAI (auto)\n"
                    cur += "".join(f"- {n}\n" for n in add)
                    agf.write_text(cur, encoding="utf-8")
                    console.print(f"[green]อัปเดต {agf} แล้ว[/green]")
            except Exception as e:
                console.print(f"[yellow]เขียน AGENTS.md ไม่ได้: {e}[/yellow]")
        console.print("[green]บันทึกความจำแล้ว — รอบหน้าจำได้[/green]")
    except (EOFError, KeyboardInterrupt):
        console.print()

def load_json(path, default):
    """อ่าน JSON — ไฟล์หาย = ค่าเริ่มต้นเงียบ ๆ (ยังไม่ตั้งค่าครั้งแรก)
    แต่ไฟล์มีอยู่แล้วอ่านไม่ได้ (พัง/สิทธิ์/ถูกล็อก) = เก็บ traceback ลง debug log"""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:load_json", f"อ่าน {path} ไม่ได้ — ใช้ค่าเริ่มต้น")
        return default


def _atomic_write_text(path, text, encoding="utf-8"):
    """Write a text file without leaving a partial target on interruption."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(".%s.%s.%s.tmp" % (target.name, os.getpid(), threading.get_ident()))
    try:
        temp.write_text(text, encoding=encoding)
        os.replace(temp, target)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def save_json(path, obj):
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


# ---------- เก็บ API key แบบเข้ารหัสด้วย DPAPI ของผู้ใช้ (Windows) ----------
# keys.json ยังเป็น JSON เหมือนเดิม แต่ค่าถูกห่อด้วย "dpapi:<base64>"
# - เครื่องอื่น/ผู้ใช้อื่นอ่านไม่ได้ (ถอดรหัสไม่ผ่าน = คืน '' ให้ใส่ key ใหม่)
# - ถ้าเข้ารหัสไม่ได้ (ไม่ใช่ Windows / DPAPI ล่ม) จะเก็บข้อความเดิม = ใช้ได้เหมือนเก่า
_KEYS_ENC_PREFIX = "dpapi:"
_KEYS_WARN = {"shown": False}


def _dpapi_blob_call(fn_name, data):
    """เรียก CryptProtectData/CryptUnprotectData คืน bytes หรือ None"""
    if os.name != "nt" or not data:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _BLOB()
        fn = getattr(crypt32, fn_name)
        if not fn(ctypes.byref(blob_in), None, None, None, None, 0x01,
                  ctypes.byref(blob_out)):
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            try:
                kernel32.LocalFree(blob_out.pbData)
            except Exception:
                pass
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:_dpapi_blob_call", f"เรียก {fn_name} ไม่สำเร็จ")
        return None


def _encode_key(value):
    """เข้ารหัส key 1 ตัว (เข้ารหัสไม่ได้ = คืนข้อความเดิม)"""
    s = str(value or "")
    if not s:
        return ""
    blob = _dpapi_blob_call("CryptProtectData", s.encode("utf-8"))
    if not blob:
        return s
    import base64 as _b64
    return _KEYS_ENC_PREFIX + _b64.b64encode(blob).decode("ascii")


def _decode_key(value):
    """ถอดรหัส key 1 ตัว (ค่าเดิมที่เป็น plaintext คืนตามเดิม)"""
    s = value if isinstance(value, str) else ""
    if not s.startswith(_KEYS_ENC_PREFIX):
        return s
    import base64 as _b64
    try:
        raw = _b64.b64decode(s[len(_KEYS_ENC_PREFIX):], validate=True)
    except Exception:
        return ""
    dec = _dpapi_blob_call("CryptUnprotectData", raw)
    if dec is None:
        if not _KEYS_WARN["shown"]:
            _KEYS_WARN["shown"] = True
            console.print("[yellow]อ่าน key ที่เข้ารหัสไม่ได้ (คนละผู้ใช้/คนละเครื่อง) — "
                          "ใส่ใหม่ด้วย: soonai key set <ค่าย> <KEY>[/yellow]")
        return ""
    try:
        return dec.decode("utf-8")
    except Exception:
        return ""


def save_keys(keys):
    """บันทึก keys แบบเข้ารหัส (ตัดค่าว่างทิ้ง) — เขียนแบบ atomic
    ใช้แทน save_json(KEYS_FILE, ...) ทุกจุด ห้ามเขียน keys.json ตรง ๆ"""
    out = {}
    for k, v in (keys or {}).items():
        if isinstance(v, str) and v.strip():
            out[str(k)] = _encode_key(v.strip())
    save_json(KEYS_FILE, out)
    try:
        os.chmod(KEYS_FILE, 0o600)  # Windows = read-only bit, POSIX = rw เจ้าของเท่านั้น
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:save_keys", "ตั้งสิทธิ์ไฟล์ keys ไม่ได้ (key ยังถูกบันทึกแล้ว)")


def load_keys():
    """อ่าน keys + ถอดรหัส (ไฟล์หาย/พัง/ถอดรหัสไม่ได้ = {} ไม่ล่ม)"""
    d = load_json(KEYS_FILE, {})
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        if not isinstance(v, str):
            continue
        got = _decode_key(v)
        if got:
            out[str(k)] = got
    return out


def load_config():
    cfg = load_json(CONFIG_FILE, {})
    cfg.setdefault("provider", "ollama")
    cfg.setdefault("model", "")
    cfg.setdefault("temperature", 0.7)
    cfg.setdefault("system", DEFAULT_SYSTEM)
    cfg.setdefault("auto_approve", False)
    cfg.setdefault("agi_auto", True)
    cfg.setdefault("vision_provider", "")
    cfg.setdefault("vision_model", "")
    cfg.setdefault("computer", {})
    # ชั้นความปลอดภัยของ agent: shell = off/safe/on · checkpoints = สำเนาไฟล์ก่อนแก้ (/undo)
    cfg.setdefault("agent", {})
    try:
        if not isinstance(cfg["agent"], dict):
            cfg["agent"] = {}
        cfg["agent"].setdefault("shell", "off")
        cfg["agent"].setdefault("checkpoints", True)
        cfg["agent"].setdefault("auto_skill", True)   # เสนอติดตั้งสกิลที่ตรงกับงาน
        cfg["agent"].setdefault("skill_decline_limit", SKILL_DECLINE_LIMIT)  # ปฏิเสธกี่ครั้ง = หยุดเสนอ
    except Exception:
        cfg["agent"] = {"shell": "off", "checkpoints": True}
    # งบ context (token) สำหรับย่อประวัติอัตโนมัติ
    cfg.setdefault("context_budget", 24000)
    cfg.setdefault("boost", True)
    cfg.setdefault("effort", "")
    cfg.setdefault("update_url", "")
    cfg.setdefault("skipped_version", "")
    cfg.setdefault("last_update_check", 0)
    # เติม system prompt คุณภาพเฉพาะตอนไฟล์ยังไม่มีค่านี้ (ไม่ทับค่าที่ผู้ใช้ตั้งไว้เอง)
    if not cfg.get("system"):
        cfg["system"] = QUALITY_SYSTEM
        try:
            save_json(CONFIG_FILE, cfg)
        except Exception:
            pass
    # ต่อกฎจัดการข้อความกำกวมเข้า system prompt เมื่อยังไม่มี (นับ marker ใน CLARIFY_RULES)
    # ครอบทั้ง default เก่าที่เคยเซฟค้างและค่าที่ผู้ใช้เขียนเอง — ต่อท้ายไม่ทับข้อความเดิม ทำครั้งเดียว
    elif CLARIFY_MARKER not in str(cfg.get("system")):
        cfg["system"] = str(cfg["system"]).rstrip() + " " + CLARIFY_RULES
        try:
            save_json(CONFIG_FILE, cfg)
        except Exception:
            pass
    return cfg


# ── sessions: id/ชื่อ/compact/save/load + team/staff ──────────────────────────
def _session_id():
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _clean_title(text, limit=40):
    """ชื่อหัวข้อปลอดภัย: บรรทัดเดียว ไม่มีอักขระควบคุม ตัดตามกลุ่มตัวอักษรไทย
    (ไม่ตัดกลางสระ/วรรณยุกต์)"""
    import unicodedata
    s = str(text or "").replace("\r", "\n").split("\n", 1)[0].strip()
    s = "".join(" " if c == "\t" else c for c in s
                if c == "\t" or unicodedata.category(c)[0] != "C").strip()
    if not s:
        return ""
    try:
        groups = _clusters(s)
    except Exception:
        groups = list(s)
    if len(groups) > max(1, int(limit)):
        s = "".join(groups[:max(1, int(limit))])
    return s


_MIGRATED_SESSIONS = {"done": False}


def _migrate_legacy_sessions(dest=None, sources=None):
    """ย้าย sessions เก่าที่ค้างในโฟลเดอร์โปรเจคมารวมที่ระดับเครื่อง (ครั้งเดียวต่อโปรเซส)
    ไฟล์ซ้ำ id เก็บอันที่ updated ใหม่กว่า — ไม่ทับของใหม่ ไม่ลบมั่ว"""
    if _MIGRATED_SESSIONS["done"]:
        return 0
    _MIGRATED_SESSIONS["done"] = True
    try:
        dest = Path(dest or SESSIONS_DIR)
        dest.mkdir(parents=True, exist_ok=True)
    except Exception:
        return 0
    if sources is None:
        try:
            legacy = BASE_DIR / "sessions"
        except Exception:
            return 0
        sources = [] if legacy.resolve() == dest.resolve() else [legacy]
    moved = 0
    for src in sources:
        try:
            files = sorted(Path(src).glob("*.json"))
        except Exception as e:
            _DBG.log_swallowed(e, "soonai.py:_migrate_legacy_sessions",
                               f"อ่านรายการ session เก่าใน {src} ไม่ได้ — ข้ามโฟลเดอร์นี้")
            continue
        for f in files:
            try:
                if f.resolve() == (dest / f.name).resolve():
                    continue
            except Exception as e:
                _DBG.log_swallowed(e, "soonai.py:_migrate_legacy_sessions",
                                   f"เทียบพาธของ session {f.name} ไม่ได้ — ไปต่อ")
            try:
                new = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                _DBG.log_swallowed(e, "soonai.py:_migrate_legacy_sessions",
                                   f"ไฟล์ session เก่า {f.name} อ่านไม่ได้ — ข้ามไฟล์นี้")
                continue
            # อันไหนอันนั้น: ย้ายเฉพาะไฟล์ sessions จริง (มี messages)
            # ไฟล์อื่น (mcp.json, skills, ฯลฯ) หลงมาอยู่ตรงนี้ก็ไม่แตะ
            if not isinstance(new, dict) or not isinstance(new.get("messages"), list):
                continue
            target = dest / f.name
            if target.exists():
                try:
                    old = json.loads(target.read_text(encoding="utf-8"))
                    ko = (old.get("updated", "") or "")
                    kn = (new.get("updated", "") or "")
                    if ko or kn:
                        if kn <= ko:
                            f.unlink()  # ในเครื่องใหม่กว่า ลบตัวซ้ำเก่าทิ้ง
                        # ถ้าในเครื่องเก่ากว่า: เก็บ legacy ไว้ที่เดิม ไม่ทับของใหม่
                        continue
                except Exception as e:
                    _DBG.log_swallowed(e, "soonai.py:_migrate_legacy_sessions",
                                       f"เทียบเวลาของ session ซ้ำ {f.name} ไม่ได้ — เก็บเป็น -legacy")
                # เทียบไม่ได้ (ไฟล์พัง/ไม่มีเวลา) = ย้ายแบบเปลี่ยนชื่อ กันข้อมูลหาย
                alt = dest / f"{f.stem}-legacy.json"
                if not alt.exists():
                    try:
                        alt.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
                        f.unlink()
                        moved += 1
                    except Exception as e:
                        _DBG.log_swallowed(e, "soonai.py:_migrate_legacy_sessions",
                                           f"เก็บ session ซ้ำ {f.name} เป็น -legacy.json ไม่ได้")
                continue
            try:
                nm = new.get("name", "")
                fixed = _clean_title(fix_mojibake(nm)) if nm else ""
                if fixed and fixed != nm:
                    new["name"] = fixed
                target.write_text(json.dumps(new, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                f.unlink()
                moved += 1
            except Exception as e:
                _DBG.log_swallowed(e, "soonai.py:_migrate_legacy_sessions",
                                   f"ย้าย session เก่า {f.name} เข้าโฟลเดอร์ใหม่ไม่ได้")
    return moved


def list_sessions():
    _migrate_legacy_sessions()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            _DBG.log_swallowed(e, "soonai.py:list_sessions",
                               f"ไฟล์ session เสียหาย — ข้าม {f.name}")
            continue
        # อันไหนอันนั้น: ข้ามไฟล์ที่ไม่ใช่ sessions (mcp/skills/ไฟล์อื่น)
        if not isinstance(d, dict) or not isinstance(d.get("messages"), list):
            continue
        try:
            mt = f.stat().st_mtime
        except Exception:
            mt = 0
        rows.append((f, d, mt))
    # อันที่ใช้งานล่าสุดขึ้นก่อน (updated → mtime → ชื่อไฟล์)
    rows.sort(key=lambda r: (r[1].get("updated", "") or "", r[2], r[0].stem), reverse=True)
    out = []
    for f, d, _mt in rows:
        msgs = d.get("messages", []) if isinstance(d, dict) else []
        users = [m.get("content", "") for m in msgs
                 if isinstance(m, dict) and m.get("role") == "user"]
        raw_name = (d.get("name", "") if isinstance(d, dict) else "") or \
            (users[0] if users else "")
        try:
            shown = _clean_title(fix_mojibake(raw_name)) or "-"
            # ชื่อยังมั่ว (ทักทาย/คำสั่ง/ถูกตัด) → โชว์ข้อความแรกที่สื่อหัวข้อได้แทน
            # (โชว์อย่างเดียว ไม่แตะไฟล์ — หัวข้อจริงค่อยให้ AI สร้างตอน resume/save)
            if _title_is_weak(shown):
                shown = _fallback_title(msgs) or shown
        except Exception:
            shown = "-"
        out.append({"id": f.stem, "name": shown,
                    "provider": d.get("provider", "") if isinstance(d, dict) else "",
                    "model": d.get("model", "") if isinstance(d, dict) else "",
                    "turns": sum(1 for m in msgs
                                 if isinstance(m, dict) and m.get("role") == "user"),
                    "updated": d.get("updated", "") if isinstance(d, dict) else ""})
    return out


MAX_SESSIONS = 10
COMPACT_MARK = "(บทสนทนาก่อนหน้าถูกย่อ"
COMPACT_KEEP = 12


def _max_sessions():
    """จำนวน session ที่เก็บไว้ (ค่าเริ่มต้น 10 · ปรับได้ที่ config max_sessions)"""
    try:
        v = int(load_config().get("max_sessions") or 0)
    except Exception:
        v = 0
    return v if v > 0 else MAX_SESSIONS


def _split_compacted(messages):
    """ถ้า messages ผ่านการย่อประวัติ (มี marker) คืน (True, ส่วนท้ายหลังสรุป)
    ไม่มี marker คืน (False, None)"""
    nonsys = [i for i, m in enumerate(messages or [])
              if isinstance(m, dict) and m.get("role") != "system"]
    for pos, i in enumerate(nonsys):
        m = messages[i]
        if m.get("role") == "user" and str(m.get("content", "")).startswith(COMPACT_MARK):
            return True, [messages[j] for j in nonsys[pos + 2:]]
    return False, None


def _overlap_len(old, tail, cap):
    """ความยาวส่วนซ้ำมากสุดระหว่างหาง old กับหัว tail (กันกินข้อความใหม่ด้วย cap)"""
    n = min(len(old), len(tail), cap)
    for ln in range(n, 0, -1):
        if tail[:ln] == old[-ln:]:
            return ln
    return 0


# คำ/โครงที่ไม่ใช่หัวข้อจริง (ทักทาย · คำสั่ง · โครงสร้างที่ boost แต่งไว้)
_TITLE_WEAK_PREFIXES = ("เป้าหมาย:", "บริบท:", "คำถาม:", "goal:", "context:", "question:")
_TITLE_WEAK_MIN = 8          # สั้นกว่านี้ = ไม่สื่อหัวข้อ (เช่น 'สวัดดี', 'hi')


def _title_is_weak(name):
    """ชื่อหัวข้อใช้ไม่ได้ (ทักทาย/คำสั่ง/ถูกตัด/ขึ้นต้นโครง boost) → ควรสร้างใหม่

    เดิมหัวข้อ = ข้อความแรกของผู้ใช้ ซึ่งมักเป็น 'สวัดดี' · 'hi' · '/test ...'
    หรือ prompt ที่ boost แต่งแล้วถูกตัดกลางคำ → ดูมั่ว ไม่ตรงประเด็น"""
    s = str(name or "").strip()
    if not s:
        return True
    if s.startswith("/"):                    # '/test git --version → ผ่าน'
        return True
    low = s.lower().rstrip("!?.")
    if low in _BOOST_SKIP:                   # 'สวัสดี' · 'hi' · 'thanks'
        return True
    if s.lower().startswith(_TITLE_WEAK_PREFIXES):   # 'เป้าหมาย: ...' (โครง boost)
        return True
    return len(s) < _TITLE_WEAK_MIN


def gen_session_title(provider, model, messages, temperature=0.2):
    """สร้างหัวข้อสั้น ๆ ที่ตรงประเด็นจากบทสนทนาจริง (คืน '' ถ้าสร้างไม่ได้)

    ต่างจากเดิม (เอาข้อความแรกมาตัด) ตรงที่ดู "ทั้งบทสนทนา" แล้วสรุปเป็นหัวข้อ"""
    convo = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "")
        if role not in ("user", "assistant"):
            continue
        c = str(m.get("content") or "").strip()
        if not c or c.startswith(COMPACT_MARK):
            continue
        convo.append(f"{role}: {c[:400]}")
        if len(convo) >= 8:
            break
    if len(convo) < 2:
        return ""     # ยังคุยไม่ถึง 2 รอบ = ยังสรุปหัวข้อไม่ได้
    msgs = [{"role": "system",
             "content": ("ตั้งหัวข้อบทสนทนาภาษาไทยให้สั้นและตรงประเด็นที่สุด ไม่เกิน 7 คำ "
                         "จับสาระหลักของบทสนทนา (ไม่ใช่คำทักทาย) "
                         "ตอบเฉพาะหัวข้อบรรทัดเดียว ห้ามมีเครื่องหมายคำพูด ห้ามมีคำนำ ห้ามเครื่องหมาย markdown")},
            {"role": "user", "content": "\n".join(convo)}]
    try:
        out = send_messages(provider, model, msgs, temperature,
                            stream=False, effort="", max_tokens=60)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:gen_session_title",
                           "สร้างหัวข้อ session ไม่ได้ — ใช้ชื่อเดิมต่อ")
        return ""
    title = _clean_title(fix_mojibake(str(out or "").strip().strip('"')), limit=60)
    # โมเดลยังคืนของมั่ว/คำทักทาย → ถือว่าสร้างไม่สำเร็จ
    return "" if _title_is_weak(title) else title


_TITLE_ATTEMPT_MAX = 3       # เพดานลองให้ AI สร้างหัวข้อ (กันยิงซ้ำทุกเทิร์นเมื่อโมเดลพัง)


def _title_needs_ai(d, force=False):
    """True = ยังต้องให้ AI สร้างหัวข้อ (ชื่อมั่ว/ว่าง · ยังไม่เคยสร้าง · ยังไม่เกินเพดานลอง)

    เช็กแบบ cheap ไม่ยิง AI — เรียกก่อนเปิดสปินเนอร์กันกะพริบฟรีทุกเทิร์น"""
    if not isinstance(d, dict):
        return False
    if force:
        return True
    if d.get("title_ai"):
        return False                              # ให้ AI สร้างแล้ว = พอ
    if int(d.get("title_attempts", 0) or 0) >= _TITLE_ATTEMPT_MAX:
        return False                              # ลองครบเพดานแล้ว = อย่าซ้ำ
    return _title_is_weak(str(d.get("name", "") or ""))


def _fallback_title(msgs):
    """หัวข้อสำรอง (ไม่ยิง AI) — เอาข้อความแรกที่พอสื่อหัวข้อได้
    ข้ามคำทักทาย/คำสั่ง/ข้อความสั้นที่ดูมั่ว เช่น 'สวัดดี' · 'hi' · '/test ...'"""
    for m in msgs or []:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        t = _clean_title(fix_mojibake(str(m.get("content") or "")), limit=40)
        if t and not _title_is_weak(t):
            return t
    return ""


def ensure_session_title(sid, provider, model, messages, force=False):
    """ถ้าหัวข้อ session ยังมั่ว/ว่าง → สร้างหัวข้อจาก AI แล้วบันทึก คืนชื่อปัจจุบัน

    ทำงานอย่างมาก 1 ครั้งต่อ session (กันด้วยธง title_ai · เพดาน title_attempts)
    force=True = สร้างใหม่ถึงแม้ชื่อเดิมจะดูดี (ใช้ตอนผู้ใช้สั่ง /rename auto)"""
    f = SESSIONS_DIR / f"{sid}.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(d, dict):
        return ""
    cur = str(d.get("name", "") or "")
    if not _title_needs_ai(d, force):
        return cur
    if provider in ("ollama", "lmstudio"):
        # โมเดล local บนเครื่องธรรมดาใช้ตั้งหัวข้อไม่คุ้ม (CPU ~3 tok/s → สปินเนอร์ค้างเปล่า)
        # คงชื่อปัจจุบัน ไม่นับ attempt — สลับค่ายแล้ว AI ตั้งหัวข้อให้ใหม่ได้ตามปกติ
        return cur
    d["title_attempts"] = int(d.get("title_attempts", 0) or 0) + 1
    msgs = d.get("messages", [])
    new = gen_session_title(provider, model, msgs)
    if not new:
        new = _fallback_title(msgs)     # AI ไม่ได้ = ใช้หัวข้อสำรองก่อน (ไม่ให้ค้างชื่อมั่ว)
        if new:
            d["name"] = new             # ไม่ปิดธง title_ai — AI ยังสู้ต่อได้ภายหลัง
    else:
        d["name"] = new
        d["title_ai"] = True
    try:
        _atomic_write_text(f, json.dumps(d, ensure_ascii=False, indent=2))
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:ensure_session_title",
                           "บันทึกหัวข้อ session ไม่ได้")
    return str(d.get("name", "") or "")


def save_session(sid, provider, model, messages, name=""):
    """บันทึกบทสนทนาลงไฟล์ (เก็บ 100 ข้อความล่าสุด) เกิน MAX_SESSIONS ลบที่ใช้น้อยสุดทิ้ง คืน id
    ถ้า messages ผ่านการย่อประวัติ จะต่อส่วนใหม่ท้ายของเดิมที่บันทึกไว้ — แชทเก่าไม่หาย"""
    from datetime import datetime
    _migrate_legacy_sessions()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    f = SESSIONS_DIR / f"{sid}.json"
    old = {}
    if f.exists():
        try:
            old = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    old_msgs = old.get("messages", []) if isinstance(old, dict) else []
    old_non_sys = [m for m in old_msgs if isinstance(m, dict) and m.get("role") != "system"]
    has_mark, tail = _split_compacted(messages or [])
    if has_mark and old_non_sys:
        sys_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"]
        if not sys_msgs:
            sys_msgs = [m for m in old_msgs if isinstance(m, dict) and m.get("role") == "system"]
        merged = old_non_sys + tail[_overlap_len(old_non_sys, tail, COMPACT_KEEP):]
        messages = sys_msgs + merged
    users = [m.get("content", "") for m in messages if m.get("role") == "user"]
    # เผย field เก่าไว้ก่อน (title_ai/title_attempts/...) — ไม่งั้นธงหัวข้อถูกเช็ดทุกเทิร์น
    # แล้ว AI จะถูกยิงสร้างหัวข้อซ้ำแล้วซ้ำเล่า
    d = {**(old if isinstance(old, dict) else {}),
         "id": sid, "created": old.get("created", now), "updated": now,
         "provider": provider, "model": model,
         "name": _clean_title(name or old.get("name") or (users[0] if users else "")),
         "messages": messages[-100:]}
    try:
        _atomic_write_text(f, json.dumps(d, ensure_ascii=False, indent=2))
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:save_session",
                           f"เขียน session {sid} ไม่ได้ — ประวัติรอบนี้จะหาย")
    try:
        keep = _max_sessions()
        removed = []
        for it in list_sessions()[keep:]:
            if it["id"] != sid:
                try:
                    (SESSIONS_DIR / f"{it['id']}.json").unlink()
                    removed.append(it["id"])
                except Exception as e:
                    _DBG.log_swallowed(e, "soonai.py:save_session",
                                       f"ลบ session เก่า {it['id']} ไม่ได้ — จะค้างในโฟลเดอร์")
        if removed:
            console.print(f"[dim](เก็บ session ล่าสุด {keep} อัน — ลบเก่า {len(removed)} อัน · "
                          f"ปรับได้ที่ config max_sessions)[/dim]")
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:save_session",
                           f"กวาด session เก่าไม่ได้ (เก็บไว้ {keep}) — โฟลเดอร์จะบวมขึ้น")
    return sid


def touch_session(sid):
    """แตะเวลาอัปเดตของ session (resume = ใช้งานล่าสุด → ขึ้นอันที่ 1) คืน True/False"""
    from datetime import datetime
    try:
        f = SESSIONS_DIR / f"{sid}.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d["updated"] = datetime.now().isoformat(timespec="seconds")
        _atomic_write_text(f, json.dumps(d, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def resolve_session(ref):
    items = list_sessions()
    if not items:
        return None
    if not ref or ref in ("last", "1"):
        return items[0]
    for it in items:
        if it["id"] == ref or it["id"].startswith(ref):
            return it
    if str(ref).isdigit():
        i = int(ref) - 1
        if 0 <= i < len(items):
            return items[i]
    return None


def load_session_messages(sid):
    try:
        d = json.loads((SESSIONS_DIR / f"{sid}.json").read_text(encoding="utf-8"))
        return d.get("messages", [])
    except Exception:
        return []


def load_team(path=None):
    """โหลดทีมงาน [{name, provider, model, role}] (ไฟล์หาย/พัง = [] )"""
    try:
        d = json.loads(Path(path or TEAM_FILE).read_text(encoding="utf-8"))
        team = d.get("staff", []) if isinstance(d, dict) else []
        return [s for s in team if isinstance(s, dict) and s.get("name")]
    except Exception:
        return []


def save_team(team, path=None):
    try:
        _atomic_write_text(path or TEAM_FILE,
                           json.dumps({"staff": team}, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def resolve_staff(team, ref):
    """หา staff จากลำดับ (1-based) หรือชื่อ (case-insensitive)"""
    if not team or not (ref or "").strip():
        return None
    ref = ref.strip()
    if ref.isdigit():
        i = int(ref) - 1
        if 0 <= i < len(team):
            return team[i]
        return None
    low = ref.lower()
    for s in team:
        if str(s.get("name", "")).lower() == low:
            return s
    for s in team:
        if low in str(s.get("name", "")).lower():
            return s
    return None


def pick_staff(team, ref, prompt_msg):
    """หา staff จาก ref; ถ้าไม่ได้และมี tty เปิดเมนูให้เลือกแทน
    คืน staff หรือ None (ยกเลิก/ใช้ไม่ได้/ไม่เจอ)"""
    s = resolve_staff(team, ref) if ref else None
    if s or not sys.stdin.isatty():
        return s
    picked = fuzzy_pick(
        prompt_msg,
        [(x.get("name", ""),
          f"{x.get('name', '')} — {(x.get('role', '') or '')[:40]} "
          f"({x.get('provider', '')} / {(x.get('model', '') or '')[:30]})")
         for x in team])
    if picked:
        return resolve_staff(team, picked)
    return None


def staff_system(staff):
    """ประกอบ system context ประจำตัวลูกน้อง (role + กฎ agent + ล็อกบทบาท)"""
    name = staff.get("name", "staff")
    role = staff.get("role", "") or "ผู้ช่วยทั่วไป"
    lock = (f"กฎเหล็กประจำตำแหน่ง (ห้ามแหกเด็ดขาด):\n"
            f"1) คุณคือ {name} ตำแหน่ง {role} เท่านั้น ห้ามรับบทคนอื่น ห้ามอ้างตำแหน่งอื่น\n"
            f"2) งานไหนอยู่นอกบทบาท: ทำเฉพาะส่วนที่ตรงบทบาท แล้วระบุชัดว่าส่วนที่เหลือต้องให้ตำแหน่งอะไรทำต่อ\n"
            f"3) ทำงานร่วมกับลูกน้องคนอื่นแบบบริษัทใหญ่: ส่งต่องานชัดเจน ไม่แย่งงาน ไม่ทำซ้ำงานคนอื่น\n"
            f"4) ลงท้ายคำตอบทุกครั้งด้วยบรรทัด: [ตำแหน่ง: {role}]")
    return (f"คุณคือ {name} พนักงานในบริษัท ตำแหน่งหน้าที่: {role}\n"
            f"ทำงานตามบทบาทนี้อย่างเคร่งครัด ตอบกระชับเป็นภาษาไทย\n"
            + lock + "\n" + AGENT_SYSTEM)


def cmd_sessions(args, keys, cfg):
    action = getattr(args, "action", None)
    if action == "rm":
        target = getattr(args, "target", "") or ""
        it = resolve_session(target)
        if not it:
            console.print("[yellow]ไม่พบ session นั้น[/yellow]")
            return 1
        try:
            (SESSIONS_DIR / f"{it['id']}.json").unlink()
            console.print(f"[green]ลบ session {it['id']} แล้ว[/green]")
        except Exception as e:
            console.print(f"[red]{e}[/red]")
            return 1
        return 0
    items = list_sessions()
    if not items:
        console.print("[dim]ยังไม่มีบทสนทนาที่บันทึก — คุยในห้องแชทแล้วระบบจะบันทึกอัตโนมัติ[/dim]")
        return 0
    table = neo_table(title=f"บทสนทนาที่บันทึก ({len(items)})", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("id", style="dim")
    table.add_column("ชื่อ", style="white")
    table.add_column("ค่าย/โมเดล", style="white")
    table.add_column("รอบ", justify="right")
    table.add_column("ใช้ล่าสุด", style="dim")
    for i, it in enumerate(items[:30], 1):
        table.add_row(str(i), it["id"], it["name"] or "-",
                      f"{it['provider']} / {(it['model'] or '')[:40]}", str(it["turns"]),
                      (it["updated"] or "")[5:16].replace("T", " "))
    console.print(table)
    console.print("[dim]คุยต่อด้วย: soonai --resume [ลำดับ/id] · ลบด้วย: soonai sessions rm [id]\n"
                  "เก็บสูงสุด 10 บทสนทนา (เกินลบใช้น้อยสุดอัตโนมัติ)[/dim]")
    return 0


# ── คำสั่ง soonai mcp: catalog + add/install/use + ตารางสถานะ ────────────────
def _mcp_status_table(status, tools_by_server=None):
    table = neo_table(title="MCP servers", show_lines=False)
    table.add_column("ชื่อ", style="cyan")
    table.add_column("สถานะ", style="white")
    table.add_column("tools", justify="right")
    table.add_column("รายละเอียด", style="dim")
    for name, st in status.items():
        if not st.get("enabled", True):
            state, detail = "[dim]ปิดอยู่[/dim]", st.get("error", "")
        elif st.get("connected"):
            state, detail = "[green]ต่อติด[/green]", st.get("server", "")
        else:
            state, detail = "[red]ต่อไม่ติด[/red]", (st.get("error", "") or "")[:60]
        n = st.get("tools", 0)
        if tools_by_server and name in tools_by_server and n:
            detail = (detail + " " if detail else "") + ", ".join(tools_by_server[name][:6])
            if n > 6:
                detail += f" (+{n - 6})"
        table.add_row(name, state, str(n), detail)
    return table


def mcp_catalog_load():
    """อ่าน shared/mcp_catalog.json (หาย/พัง = {} — ไม่พังคำสั่ง) คืน {ชื่อ: spec}"""
    try:
        d = json.loads((SHARED_DIR / "mcp_catalog.json").read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return {}
        return {k: v for k, v in (d.get("servers") or {}).items()
                if isinstance(v, dict)}
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:mcp_catalog_load",
                           "อ่าน mcp_catalog.json ไม่ได้ — 'mcp install' จะใช้ไม่ได้")
        return {}


def cmd_mcp(args, keys=None, cfg=None):
    """จัดการ MCP servers (tools เสริมให้ agent ผ่าน stdio)"""
    if not _MCP_OK:
        console.print("[red]ระบบ MCP ใช้ไม่ได้ (ไม่พบ mcp_client.py)[/red]")
        return 1
    from mcp_client import hub
    action = (getattr(args, "action", None) or "list").lower()
    target = (getattr(args, "target", "") or "").strip()
    if action == "add":
        return _mcp_cmd_add(hub, args, target)
    if action == "catalog":
        return _mcp_cmd_catalog(hub)
    if action == "install":
        return _mcp_cmd_install(hub, args, target)
    if action == "rm":
        return _mcp_cmd_rm(hub, target)
    if action in ("on", "off"):
        return _mcp_cmd_onoff(hub, action, target)
    if action == "refresh":
        agent_tools(refresh=True)
        action = "list"
    if action == "test":
        return _mcp_cmd_test(hub, target)
    if action == "tools":
        return _mcp_cmd_tools(target)
    return _mcp_cmd_list(hub)


# ── ตัวย่อยของ cmd_mcp: แยกตาม action (ย้ายจากใน cmd_mcp — เนื้อเดิมล้วน) ──
def _mcp_cmd_add(hub, args, target):
    name = target
    rest = list(getattr(args, "rest", []) or [])
    if not name or not rest:
        console.print("[yellow]ใช้แบบนี้: soonai mcp add <ชื่อ> -- <คำสั่ง> [args...] [--env KEY=VAL ...]\n"
                      "เช่น: soonai mcp add fs -- npx -y @modelcontextprotocol/server-filesystem C:/Shop\n"
                      "ใช้ ${cwd} แทน path = ตามโฟลเดอร์ปัจจุบัน (ตามโปรเจคที่เปิดอยู่)[/yellow]")
        return 1
    env = {}
    for kv in getattr(args, "env", []) or []:
        if "=" in kv:
            k, v = kv.split("=", 1)
            env[k.strip()] = v
    console.print(hub.add_server(name, rest[0], rest[1:], env))
    agent_tools(refresh=True)
    return 0


def _mcp_cmd_catalog(hub):
    cat = mcp_catalog_load()
    if not cat:
        console.print("[yellow]อ่าน mcp_catalog.json ไม่ได้หรือยังว่าง[/yellow]")
        return 1
    table = neo_table(title="MCP catalog — ติดตั้งด้วย soonai mcp install <ชื่อ>",
                      show_lines=False)
    table.add_column("ชื่อ", style="cyan")
    table.add_column("คำอธิบาย", style="white")
    table.add_column("หมวด", justify="center")
    installed = hub.servers()
    for nm, sp in cat.items():
        mark = "[green]ติดตั้งแล้ว[/green] " if nm in installed else ""
        table.add_row(nm, mark + str(sp.get("description", ""))[:70],
                      str(sp.get("category", "")))
    console.print(table)
    return 0


def _mcp_cmd_install(hub, args, target):
    name = target
    cat = mcp_catalog_load()
    if not name:
        console.print("[yellow]ดูรายชื่อ: soonai mcp catalog · "
                      "ติดตั้ง: soonai mcp install <ชื่อ>[/yellow]")
        return 1
    spec = cat.get(name)
    if not spec:
        hint = ", ".join(list(cat)[:8]) or "(ว่าง)"
        console.print(f"[red]ไม่มี '{name}' ใน mcp_catalog.json[/red] "
                      f"[dim](ที่มี: {hint})[/dim]")
        return 1
    merged = dict(spec)
    env = {k: v for k, v in (spec.get("env") or {}).items()
           if isinstance(v, str)}
    for kv in getattr(args, "env", []) or []:
        if "=" in kv:
            k, v = kv.split("=", 1)
            env[k.strip()] = v
    merged["env"] = env
    console.print(hub.add_server_spec(name, merged))
    agent_tools(refresh=True)
    if spec.get("requires_auth"):
        console.print("[dim]server นี้ต้อง auth — ครั้งแรกที่เรียก mcp__* จะมีขั้นตอน "
                      "ลงชื่อเข้าใช้ (OAuth เปิดเบราว์เซอร์) · ใส่ค่าเพิ่มด้วย --env KEY=VAL"
                      "[/dim]")
    console.print(f"[dim]ทดสอบ: soonai mcp test {name} · "
                  f"ดู tools: soonai mcp tools {name}[/dim]")
    return 0


def _mcp_cmd_rm(hub, target):
    if not target:
        console.print("[yellow]ใช้แบบนี้: soonai mcp rm <ชื่อ>[/yellow]")
        return 1
    console.print(hub.remove_server(target))
    agent_tools(refresh=True)
    return 0


def _mcp_cmd_onoff(hub, action, target):
    if not target:
        console.print(f"[yellow]ใช้แบบนี้: soonai mcp {action} <ชื่อ>[/yellow]")
        return 1
    console.print(hub.set_enabled(target, action == "on"))
    agent_tools(refresh=True)
    return 0


def _mcp_cmd_test(hub, target):
    if not target:
        console.print("[yellow]ใช้แบบนี้: soonai mcp test <ชื่อ>[/yellow]")
        return 1
    spec = hub.servers().get(target)
    if not spec:
        console.print(f"[yellow]ไม่มี server '{target}'[/yellow]")
        return 1
    from mcp_client import client_for_spec
    c = client_for_spec(spec, label=target)
    try:
        info = c.connect(timeout=30)
        tools = c.list_tools()
        console.print(f"[green]ต่อติด: {info.get('name', target)} "
                      f"{info.get('version', '')} — {len(tools)} tools[/green]")
        for t in tools:
            console.print(f"  · {t.get('name', '')} — {(t.get('description', '') or '')[:80]}")
        return 0
    except Exception as e:
        console.print(f"[red]ต่อไม่ติด: {e}[/red]")
        return 1
    finally:
        c.close()


def _mcp_cmd_tools(target):
    defs = agent_tools(include_mcp=True)
    shown = 0
    for d in defs:
        fn = d.get("function", {})
        if not fn.get("name", "").startswith("mcp__"):
            continue
        if target and not fn["name"].startswith(f"mcp__{target}__"):
            continue
        console.print(f"[cyan]{fn['name']}[/cyan] — {(fn.get('description', '') or '')[:100]}")
        shown += 1
    if not shown:
        console.print("[dim]ยังไม่มี MCP tools — เพิ่มด้วย soonai mcp add[/dim]")
    return 0


def _mcp_cmd_list(hub):
    status = hub.status()
    if not status:
        console.print("[dim]ยังไม่มี MCP server — เพิ่มด้วย:\n"
                      "  soonai mcp catalog  (ดูของสำเร็จรูป เช่น tinyfish)\n"
                      "  soonai mcp install <ชื่อ>\n"
                      "  soonai mcp add <ชื่อ> -- <คำสั่ง> [args...]\n"
                      "เช่น: soonai mcp add fs -- npx -y @modelcontextprotocol/server-filesystem C:/Shop[/dim]")
        return 0
    by_server = {}
    for d in agent_tools(include_mcp=True):
        fn = d.get("function", {})
        qn = fn.get("name", "")
        if qn.startswith("mcp__"):
            parts = qn.split("__")
            by_server.setdefault(parts[1] if len(parts) > 1 else "?", []).append(
                "__".join(parts[2:]) if len(parts) > 2 else qn)
    console.print(_mcp_status_table(status, by_server))
    try:
        from mcp_client import expand_mcp_spec as _expand
        for _name, _spec in hub.servers().items():
            try:
                _ex = _expand(_spec)
                if _ex.get("url") and not _ex.get("command"):
                    _line = str(_ex.get("url", ""))
                else:
                    _parts = [str(_ex.get("command", ""))] + \
                        [str(a) for a in (_ex.get("args") or [])]
                    _line = " ".join(p for p in _parts if p)
            except Exception:
                _line = ""
            if _line:
                console.print(f"[dim]· {_name} → {_line[:130]}[/dim]")
    except Exception:
        pass
    console.print("[dim]soonai mcp catalog · install <ชื่อ> · tools [ชื่อ] · test <ชื่อ> · "
                  "on/off/rm <ชื่อ> · refresh · ในห้องแชทใช้ /mcp · "
                  "${cwd} ใน args = ตามโฟลเดอร์ปัจจุบัน[/dim]")
    return 0


MODELS_CACHE_FILE = SHARED_DIR / ".models_cache.json"
MODELS_CACHE_TTL = 24 * 3600  # 24 ชม.


# ── models catalog: cache + ดึงรายการจากค่าย + tier/ราคา ────────────────────
def _read_models_cache():
    try:
        d = json.loads(MODELS_CACHE_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_models_cache(cache):
    try:
        MODELS_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2)[:2000000],
            encoding="utf-8")
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:_write_models_cache",
                           "เขียน cache รายการโมเดลไม่ได้ — จะดึงรายการใหม่ทุกครั้ง")


def _fetch_models_live(provider):
    """ดึงรายชื่อโมเดล + pricing จาก API ของค่ายนั้นตรง ๆ (ล้มเหลว = raise)"""
    cfg = PROVIDERS[provider]
    keys = load_keys()
    key = get_key(provider, keys)
    url = (cfg.get("models_url") or "").strip()
    if not url or url.startswith("native:"):
        raise RuntimeError("no-remote")
    headers = {}
    if key:
        if provider == "anthropic":
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        else:
            headers = {"Authorization": f"Bearer {key}"}
    headers.update(cfg.get("extra_headers", {}))
    # Ollama ใช้ endpoint ต่างจาก /models
    if provider == "ollama":
        r = _http_session().get("http://localhost:11434/api/tags", timeout=10)
        j = r.json()
        names = [m.get("name", "") for m in j.get("models", [])
                 if isinstance(m, dict) and m.get("name")]
        if not names:
            raise RuntimeError("empty")
        return names, {}
    # Puter ใช้ public endpoint รูปแบบของตัวเอง: {"models": [{id, costs{prompt_tokens, completion_tokens}, ...}]}
    if provider == "puter":
        r = _http_session().get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        j = r.json()
        items = j.get("models", []) if isinstance(j, dict) else []
        models, pricing = [], {}
        for it in items:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            mid = str(it["id"])
            if mid.endswith(":batch"):
                continue  # batch API ไม่ใช่แชทโต้ตอบ
            models.append(mid)
            costs = it.get("costs") if isinstance(it.get("costs"), dict) else {}
            if costs:
                try:
                    pin = float(costs.get("prompt_tokens", 0))
                    pout = float(costs.get("completion_tokens", 0))
                except Exception:
                    pin, pout = 0, 0
                pricing[mid] = {"puter_in": pin, "puter_out": pout}
        if not models:
            raise RuntimeError("empty")
        return models, pricing
    r = _http_session().get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    j = r.json()
    items = j.get("data", []) if isinstance(j, dict) else []
    models, pricing = [], {}
    for it in items:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        mid = it["id"]
        models.append(mid)
        # เก็บราคาดิบไว้ให้ price_str/price_tier ใช้ (openrouter มี prompt/completion)
        pr = {}
        for k in ("prompt", "completion", "puter_in", "puter_out",
                  "hf_min_in", "hf_free"):
            if k in it:
                pr[k] = it[k]
        inner = it.get("pricing") if isinstance(it.get("pricing"), dict) else None
        if inner:
            for k in ("prompt", "completion"):
                if k in inner:
                    pr[k] = inner[k]
        if pr:
            pricing[mid] = pr
    if not models:
        raise RuntimeError("empty")
    return models, pricing


def get_models(provider, refresh=False):
    """ดึงโมเดลล่าสุด + ราคา (cache 24 ชม. ใน .models_cache.json)
    ออฟไลน์/ดึงไม่ได้ = fallback_models ของค่ายนั้น
    คืน (models, pricing)"""
    import time as _t
    cfg = PROVIDERS.get(provider, {})
    fallback = list(cfg.get("fallback_models", []))
    try:
        cache = _read_models_cache()
    except Exception:
        cache = {}
    if not refresh:
        hit = cache.get(provider) if isinstance(cache, dict) else None
        if isinstance(hit, dict) and hit.get("models"):
            try:
                if _t.time() - float(hit.get("ts", 0)) < MODELS_CACHE_TTL:
                    pr = hit.get("pricing") if isinstance(hit.get("pricing"), dict) else {}
                    return list(hit["models"]), pr
            except Exception:
                pass
    try:
        models, pricing = _fetch_models_live(provider)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:get_models",
                           f"ดึงรายการโมเดลของ {provider} ไม่ได้ — ใช้รายการสำรอง")
        return fallback, {}
    try:
        cache[provider] = {"v": 2, "ts": _t.time(),
                           "models": models, "pricing": pricing}
        _write_models_cache(cache)
    except Exception:
        pass
    return models, pricing


def empty_list_hint(provider):
    if provider == "huggingface":
        return ("HuggingFace ไม่มีโมเดล $0 — ทั้งหมดกินเครดิตรายเดือน "
                "(endpoint เก่าปิดไปแล้ว) ของฟรี $0 ดูที่ Ollama / OpenRouter :free / Groq")
    return ""


def tier_label(tier):
    if tier == "free":
        return "[green]ฟรี[/]"
    if tier == "tier":
        return "[yellow]tier[/]"
    return "[dim]จ่าย[/]"


# ── TUI (M6): บรรทัดสถานะ + log tool ของ session ─────────────────────────
SESSION_TOOLS = []          # [(name, status, สรุปสั้น)] ของ session นี้ (สำหรับ /tools)
SESSION_TOOLS_MAX = 200
_STATUS_CACHE = {"t": 0.0, "extra": None, "ttl": 5.0}


def require_usable(provider, keys):
    if PROVIDERS[provider].get("tool_only"):
        return (f"{PROVIDERS[provider]['name']} ไม่ใช่ค่ายแชท (ไม่มี endpoint คุยโมเดล) — "
                "ใช้เป็นเครื่องมือ web ของ agent แทน (web_search/web_fetch · "
                "soonai mcp install tinyfish)")
    if not PROVIDERS[provider].get("no_key") and not get_key(provider, keys):
        return (f"ยังไม่มี key ของ {PROVIDERS[provider]['name']} "
                f"— รันคำสั่ง: soonai setup  หรือ  soonai key set {provider} YOUR_KEY")
    return ""


# ── net/timeout: error ภาษาไทย + timeout + HTTP session/post กลาง ───────────
def fix_mojibake(text):
    """ซ่อมข้อความไทยที่ถูกถอดรหัสผิดเป็นลาติน (เช่น à¸ª) กลับเป็นไทย
    ปลอดภัย: ข้อความปกติ/ภาษาอื่นไม่โดนแตะ (ถอดกลับไม่ได้จะคงเดิม)"""
    import re

    def _fix_run(m):
        s = m.group(0)
        if not any("\x80" <= c <= "\xff" for c in s):
            return s
        try:
            return s.encode("latin1").decode("utf-8")
        except Exception:
            return s

    if not isinstance(text, str) or not text:
        return text
    return re.sub(r"[\x20-\xff]+", _fix_run, text)


def _debug_dump(tag, resp):
    try:
        if _DBG.enabled():
            body = resp.content[:20000].decode("utf-8", errors="replace")
            (BASE_DIR / "debug_last.json").write_text(
                json.dumps({"tag": tag, "status": resp.status_code,
                            "content_type": resp.headers.get("Content-Type", ""),
                            "body": body}, ensure_ascii=False, indent=2),
                encoding="utf-8")
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:_debug_dump", "เขียน debug_last.json ไม่ได้")


def _friendly_conn_error(url, e):
    """แปล connection error ของ server local เป็นวิธีแก้ภาษาไทย (None = ไม่ใช่เคสนี้)"""
    s = f"{url} {e}".lower()
    if "refused" not in s and "10061" not in s and "failed to establish" not in s:
        return None
    if "11434" in s:
        return ("เชื่อมต่อ Ollama ไม่ได้ (ยังไม่รัน) — เปิดโปรแกรม Ollama "
                "หรือรัน `ollama serve` แล้วลองใหม่")
    if "1234" in s:
        return ("เชื่อมต่อ LM Studio ไม่ได้ (ยังไม่รัน) — เปิด LM Studio → "
                "โหลดโมเดล → กด Start Server (port 1234) แล้วลองใหม่")
    return None


class NetTimeoutError(RuntimeError):
    """อ่าน/ต่อเครือข่ายเกินเวลา — ต่างจาก error ของคำขอตรงที่
    ระบบ retry/failover ต่อได้ (ไม่ใช่ความผิดของ key/payload)"""


_NET_TIMEOUT_KW = ("read timed out", "read timeout", "timed out", "timeout error",
                   "connection aborted", "connection reset", "connection broken",
                   "incompleteread", "max retries exceeded", "name resolution",
                   "proxy error", "ssl:", "socket timeout")


def _is_read_timeout(e):
    """server รับคำขอแล้วแต่ตอบ/ส่งช้าเกิน read timeout (ลองซ้ำก็ช้าเหมือนเดิม)"""
    try:
        import requests as _rq
        if isinstance(e, _rq.exceptions.ReadTimeout):
            return True
    except Exception:
        pass
    s = str(e or "").lower()
    return "read timed out" in s or "read timeout" in s


def _is_timeout_error(e):
    """Exc เครือข่าย/timeout ไหม (รวม string ดิบจาก urllib3 ที่ leak ออกมา)"""
    if isinstance(e, NetTimeoutError):
        return True
    try:
        import requests as _rq
        if isinstance(e, (_rq.exceptions.Timeout, _rq.exceptions.ConnectionError)):
            return True
    except Exception:
        pass
    s = str(e or "").lower()
    return any(kw in s for kw in _NET_TIMEOUT_KW)


def _friendly_timeout(e):
    """ข้อความไทยสำหรับ timeout/conn — ไม่โชว์ string ดิบของ urllib3 ให้ผู้ใช้อีก"""
    return ("เชื่อมต่อ/อ่านคำตอบเกินเวลา (ค่ายตอบช้าหรือเครือข่ายไม่เสถียร) — "
            "ระบบลองใหม่และสลับโมเดล/ค่ายให้แล้ว ถ้ายังเจอซ้ำ: ปรับเวลาใน soonai setup "
            "(หน้า Timeout) หรือเพิ่ม chat_timeout (วินาที) ใน shared/config.json")


def _chat_timeout(stream):
    """timeout ของคำขอแชททุกค่าย: คืน (connect, read) วินาที
    - read ของ non-stream = ทั้งคำตอบมาทีเดียว → ต้องนาน (คำตอบยาว/thinking นาน เดิม 120s สั้นไป)
    - read ของ stream = เว้นช่วงระหว่าง chunk → พอประมาณ (โมเดล thinking บางตัวเงียบยาว)
    ทับได้ด้วย chat_timeout / connect_timeout ใน shared/config.json"""
    try:
        cfg = load_config() or {}
    except Exception:
        cfg = {}
    key = "chat_timeout_stream" if stream else "chat_timeout"
    try:
        read = int(cfg.get(key) or 0)
    except Exception:
        read = 0
    if read <= 0 and stream:
        try:
            read = int(cfg.get("chat_timeout") or 0)  # legacy: ค่าเดียวใช้ทั้งสองแบบ
        except Exception:
            read = 0
    if read <= 0:
        read = 180 if stream else 240
    try:
        conn = int(cfg.get("connect_timeout") or 15)
    except Exception:
        conn = 15
    return (max(5, conn), max(30, read))


def _wait_animated(seconds, text, _console=None):
    """รอแบบมีอนิเมชันนับถอยหลังจริง (แถบ + ตัวเลขลดทุก 0.25s) โหมด pipe นอนเฉยๆ"""
    import time as _t
    import math
    total = max(1, int(math.ceil(seconds)))
    con = _console or console
    if not con.is_terminal:
        _t.sleep(total)
        return
    try:
        from rich.live import Live
        with Live("", console=con, transient=True, refresh_per_second=8) as live:
            start = _t.monotonic()
            while True:
                el = _t.monotonic() - start
                left = total - el
                if left <= 0:
                    break
                done = min(20, int((el / total) * 20))
                live.update(f"{text} [cyan]{'█' * done}{'░' * (20 - done)}[/] {left:.0f}s")
                _t.sleep(0.25)
    except Exception:
        _t.sleep(total)


_HTTP = threading.local()


def _http_session():
    """requests.Session แยกต่อเธรด (keep-alive ต่อเธรด + ปลอดภัยตอนรันทีมขนาน)
    requests.Session ไม่รับประกันว่า thread-safe: ใช้ตัวเดียวข้ามเธรดอาจชนกันได้"""
    s = getattr(_HTTP, "session", None)
    if s is None:
        s = requests.Session()
        _HTTP.session = s
    return s


def _post_chat(url, headers, payload, timeout, stream, tag, retries=2):
    """POST พร้อมลองใหม่เมื่อเจอ 502/503/504 (gateway ล่มชั่วคราว)"""
    last_exc = RuntimeError("เชื่อมต่อไม่ได้")
    for i in range(retries + 1):
        try:
            r = _http_session().post(url, headers=headers, json=payload,
                                     timeout=timeout, stream=stream)
        except Exception as e:
            friendly = _friendly_conn_error(url, e)
            if friendly:
                raise RuntimeError(friendly)
            last_exc = e
            # read timeout = server รับแล้วแต่ช้า — ลองซ้ำก็ช้าเหมือนเดิม
            # ข้าม retry เด้งไปให้ failover (สลับโมเดล/ค่าย) จัดการเลย
            if i < retries and not _is_read_timeout(e):
                _wait_animated(2 * (i + 1), "(เชื่อมต่อล่ม — รอแล้วลองใหม่…)")
                continue
            if _is_timeout_error(e):
                raise NetTimeoutError(_friendly_timeout(e)) from None
            raise
        r.encoding = "utf-8"
        _debug_dump(tag, r)
        if r.status_code in (429, 502, 503, 504) and i < retries:
            try:
                r.close()
            except Exception:
                pass
            wait = 3 * (i + 1)
            if r.status_code == 429:
                try:
                    wait = max(wait, min(int(r.headers.get("Retry-After", 0)), 60))
                except Exception:
                    pass
            _wait_animated(wait, f"(HTTP {r.status_code} — ลองใหม่ {i + 1}/{retries}…)")
            continue
        return r
    raise last_exc


def _effort():
    try:
        return (load_config().get("effort", "") or "").strip().lower()
    except Exception:
        return ""


def _chat_effort(provider, effort):
    """effort ที่ใช้จริง: None = เอาจาก config · ค่ามั่ว = ปิด · ค่าย local ไม่ต้องส่ง param"""
    if effort is None:
        effort = _effort()
    if effort not in EFFORT_BUDGET:
        effort = ""
    if effort and provider in ("ollama", "lmstudio"):
        effort = ""  # โมเดล local คิดเองอยู่แล้ว ไม่ต้องส่ง param
    return effort


def _resp_body(resp, limit=800):
    """ข้อความจาก response แบบปลอดภัย (อ่านไม่ได้ = '')"""
    try:
        return str(resp.text or "")[:limit]
    except Exception:
        return ""


# ── chat driver ทุกค่าย + send_messages (ลูปเดียว สลับค่าย/โมเดลเอง) ────────
class _ChatDriver:
    """ตัวขับแชทของค่ายหนึ่ง ๆ — เก็บเฉพาะส่วนที่ต่างกัน
    (สร้างคำขอ / ยิง / อ่านคำตอบ / ขอต่อเมื่อคำตอบโดนตัด)
    ลูปหลัก (failover · ต่อคำตอบ · emit) อยู่ที่ send_messages ที่เดียว"""

    provider_key = ""
    tag = ""
    stream = False
    supports_stream = False               # สตรีมทีละชิ้นได้จริงไหม
    supports_switch = False               # สลับข้ามค่ายได้ไหมเมื่อโควต้าหมด
    emit_per_round = False                # เรียก on_chunk ทุกรอบ (ไม่ใช่รวบครั้งเดียว)
    swallows_continuation_errors = False  # ขอต่อไม่สำเร็จ = ใช้คำตอบเท่าที่มี
    max_rounds = 1

    def spec(self):
        """คืน (url, headers, payload) ของรอบนี้"""
        raise NotImplementedError

    def send(self, url, headers, payload):
        """ยิงคำขอ 1 ครั้ง (+ retry เฉพาะค่ายถ้ามี)"""
        return _post_chat(url, headers=headers, payload=payload,
                          timeout=_chat_timeout(self.stream),
                          stream=self.stream, tag=self.tag)

    def read(self, resp, emit):
        """คืน (ข้อความของรอบนี้, เหตุผลที่จบ) — สตรีมจะ emit ทีละชิ้นเอง"""
        raise NotImplementedError

    def error_body(self, resp):
        """ข้อความ error ที่จะส่งให้ format_api_error"""
        return _resp_body(resp)

    def should_continue(self, finish, round_i):
        """คำตอบโดนตัด = ต้องขอต่อไหม"""
        return False

    def continue_with(self, text):
        """เตรียมรอบถัดไปให้ต่อจากคำตอบเดิม"""
        return None

    def set_model(self, model):
        self.model = model

    def switch_provider(self, provider, model):
        """รับแจ้งว่าสลับค่ายแล้ว (คืน False = ค่ายนี้สลับไม่ได้)"""
        return False

    def error_message(self, status, body):
        return format_api_error(self.provider_key, status, body)


class _OpenAIChatDriver(_ChatDriver):
    """ค่ายมาตรฐาน OpenAI: POST <base>/chat/completions (สตรีมได้จริง)"""

    tag = "chat-openai"
    supports_stream = True
    supports_switch = True
    emit_per_round = True
    max_rounds = 3

    def __init__(self, provider, model, messages, temperature, stream, effort, max_tokens):
        self.provider_key = provider
        self.model = model
        self.temperature = temperature
        self.stream = stream
        self.effort = effort
        self.max_tokens = max_tokens
        self.messages_list = list(messages)
        self.payload = None
        self.trans_retried = False
        self.set_key()

    def set_key(self):
        cfg = PROVIDERS[self.provider_key]
        key = get_key(self.provider_key, load_keys())
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        headers.update(cfg.get("extra_headers", {}))
        self.headers = headers
        self.url = cfg["base"].rstrip("/") + "/chat/completions"

    def spec(self):
        if self.payload is None:
            body = {"model": self.model, "messages": list(self.messages_list),
                    "temperature": self.temperature, "stream": self.stream,
                    "max_tokens": self.max_tokens or 16384}
            if self.effort:
                body["reasoning_effort"] = self.effort
            self.payload = body
        return self.url, self.headers, self.payload

    def _post_strip(self, url, headers, payload):
        """ยิง + ถ้า 400 เพราะพารามิเตอร์ไม่รองรับ ให้ตัดตัวนั้นแล้วลองใหม่"""
        r = _post_chat(url, headers=headers, payload=payload,
                       timeout=_chat_timeout(self.stream),
                       stream=self.stream, tag=self.tag)
        if r.status_code == 400:
            low = _resp_body(r, 600).lower()
            drop = [k for k in ("max_tokens", "max_completion_tokens", "reasoning_effort")
                    if k in payload and k.replace("_", " ") in low.replace("_", " ")]
            if ("reasoning_effort" in payload and "reasoning_effort" not in drop
                    and "think" in low):
                drop.append("reasoning_effort")  # บางค่ายเรียกชื่อว่า think แล้วปฏิเสธ
            if drop:
                for k in drop:
                    payload.pop(k, None)
                try:
                    r.close()
                except Exception:
                    pass
                console.print(f"[dim](ค่ายนี้ไม่รับ {', '.join(drop)} — ลองใหม่แบบไม่มี)[/dim]")
                r = _post_chat(url, headers=headers, payload=payload,
                               timeout=_chat_timeout(self.stream),
                               stream=self.stream, tag=self.tag)
        return r

    def send(self, url, headers, payload):
        r = self._post_strip(url, headers, payload)
        if (r.status_code == 400 and not self.trans_retried
                and "provider returned error" in _resp_body(r).lower()):
            # OpenRouter ล่มชั่วคราวฝั่ง provider — รอแล้วลองใหม่ครั้งเดียวก่อนยอมแพ้
            self.trans_retried = True
            try:
                r.close()
            except Exception:
                pass
            _wait_animated(4, "(ค่ายสะดุดชั่วคราว — รอแล้วลองใหม่…)")
            r = self._post_strip(url, headers, payload)
        return r

    def read(self, resp, emit):
        if not self.stream:
            j = resp.json()
            text = fix_mojibake(j["choices"][0]["message"]["content"] or "")
            emit(text)
            return text, (j.get("choices") or [{}])[0].get("finish_reason", "")
        full, finish = "", ""
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                s = line.strip()
                if not s.startswith("data:"):
                    continue
                data = s[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                except Exception:
                    continue
                if not isinstance(j, dict):
                    continue
                if j.get("error"):
                    raise RuntimeError(format_api_error(self.provider_key, 200, j))
                ch = (j.get("choices") or [{}])[0]
                d = (ch.get("delta") or {}).get("content", "")
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
                if d:
                    full += d
                    emit(d)
        except Exception as e:
            # สตรีมขาดกลางระหว่างอ่าน: คืนคำตอบบางส่วนดีกว่าล้างทิ้ง/โยน exc ดิบ
            # (error ของผู้ให้บริการ = RuntimeError จากข้างบน → ส่งต่อตามเดิม)
            if full and not isinstance(e, RuntimeError) and _is_timeout_error(e):
                console.print("[dim](สตรีมขาดกลางระหว่างทาง — คืนคำตอบบางส่วนที่ได้มา)[/dim]")
                return full, finish
            raise
        return full, finish

    def should_continue(self, finish, round_i):
        return finish == "length" and round_i < self.max_rounds - 1

    def continue_with(self, text):
        console.print("[dim](ตอบยังไม่จบ — ขอต่อ…)[/dim]")
        self.payload["messages"] = self.payload["messages"] + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "continue"}]

    def switch_provider(self, provider, model):
        self.provider_key = provider
        self.set_key()
        self.payload["model"] = model
        self.model = model
        return True

    def set_model(self, model):
        self.model = model
        self.payload["model"] = model


class _OllamaChatDriver(_ChatDriver):
    """ค่าย Ollama — ยิง native /api/chat ไม่ใช่ /v1/chat/completions

    เหตุผล (พิสูจน์จากเครื่องจริง): endpoint /v1 ของ ollama เมิน field "options"
    → num_ctx ติดค่า default 4096 เสมอ พอ system/history ใหญ่กว่านั้น โมเดลเห็น
    คำถามโดนตัดแล้วเหลือที่น้อยจนตอบไม่ทันจบ (finish=length) → วงจรขอต่อวน
    รอบละนาที ๆ แต่ /api/chat รับ options.num_ctx จริง (ยืนยันทาง /api/ps)

    ปรับขนาด context ได้: คีย์ ollama_num_ctx ใน shared/config.json (default 8192)
    เร็วขึ้นอีกเท่าตัวกับโมเดล thinking สาย qwen3: ใส่ think:false (r1 ฝัง thinking
    ในตัวจึงไม่มีผล — ไม่ error เพราะ ollama เมินได้)
    max_tokens → options.num_predict · stream/ต่อคำตอบเมื่อโดนตัดเหมือนตระกูล OpenAI"""

    tag = "chat-ollama"
    supports_stream = True
    supports_switch = True      # ข้ามค่ายได้ (switch_provider สร้าง headers/url ใหม่)
    emit_per_round = True
    max_rounds = 3

    def __init__(self, model, messages, temperature, max_tokens):
        self.provider_key = "ollama"
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.messages_list = list(messages)
        self.payload = None
        self.set_key()

    def set_key(self):
        cfg = PROVIDERS[self.provider_key]
        key = get_key(self.provider_key, load_keys())
        headers = {"Content-Type": "application/json"}
        if key:  # ปกติ ollama ไม่ต้องมี key — ใส่ให้เผื่อ proxy หน้า server
            headers["Authorization"] = f"Bearer {key}"
        headers.update(cfg.get("extra_headers", {}))
        self.headers = headers
        self.url = "http://localhost:11434/api/chat"

    def _num_ctx(self):
        try:
            n = int((load_config() or {}).get("ollama_num_ctx") or 0)
        except Exception:
            n = 0
        return n if n >= 2048 else 8192

    def spec(self):
        if self.payload is None:
            opts = {"num_ctx": self._num_ctx(), "temperature": self.temperature}
            if self.max_tokens:
                opts["num_predict"] = int(self.max_tokens)
            self.payload = {"model": self.model, "messages": list(self.messages_list),
                            "stream": self.stream, "think": False, "options": opts}
        return self.url, self.headers, self.payload

    def read(self, resp, emit):
        if not self.stream:
            j = resp.json()
            m = j.get("message") or {}
            text = fix_mojibake(m.get("content") or "")
            emit(text)
            return text, j.get("done_reason", "")
        full, finish = "", ""
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    j = json.loads(line.strip())
                except Exception:
                    continue
                if not isinstance(j, dict):
                    continue
                m = j.get("message") or {}
                d = m.get("content") or ""
                if j.get("done"):
                    finish = j.get("done_reason", "")
                if d:
                    full += d
                    emit(d)
        except Exception as e:
            # สตรีมขาดกลางคัน: เก็บคำตอบที่ได้แล้วแจ้งเบา ๆ ดีกว่าพังทั้งเทิร์น
            if full and not isinstance(e, RuntimeError) and _is_timeout_error(e):
                console.print("[dim](สตรีมขาดกลางระหว่างทาง — คืนคำตอบบางส่วนที่ได้มา)[/dim]")
                return full, finish
            raise
        return full, finish

    def should_continue(self, finish, round_i):
        return finish == "length" and round_i < self.max_rounds - 1

    def continue_with(self, text):
        console.print("[dim](ตอบยังไม่จบ — ขอต่อ…)[/dim]")
        self.payload["messages"] = self.payload["messages"] + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "continue"}]

    def switch_provider(self, provider, model):
        self.provider_key = provider
        self.set_key()          # คลาสนี้ set_key ผูก url ค่ายตาม provider_key ไว้แล้ว
        self.payload["model"] = model
        self.model = model
        return True

    def set_model(self, model):
        self.model = model
        self.payload["model"] = model


class _AnthropicChatDriver(_ChatDriver):
    """Anthropic Messages API: คำตอบไม่สตรีม · system แยก · thinking ได้"""

    tag = "chat-anthropic"
    provider_key = "anthropic"
    supports_stream = False
    supports_switch = True  # ย้ายออกไปค่ายอื่นได้ (ผ่าน _chat_switch_driver ข้ามตระกูล)
    emit_per_round = False
    swallows_continuation_errors = True
    max_rounds = 3

    def __init__(self, model, messages, temperature, eff, max_tokens, depth=0):
        self.model = model
        self.temperature = temperature
        self.effort = eff
        self.depth = depth
        self.base_messages = list(messages)
        self.extra = []          # ข้อความต่อท้ายเมื่อคำตอบโดนตัด
        self.no_thinking = False  # ค่ายปฏิเสธ thinking แล้ว = ปิดถาวรในรอบนี้
        self.thinking = False
        self.set_key()

    def set_key(self):
        self.url = "https://api.anthropic.com/v1/messages"
        self.headers = {"x-api-key": get_key("anthropic", load_keys()),
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"}

    def spec(self):
        system, msgs = "", []
        for m in list(self.base_messages) + list(self.extra):
            if m.get("role") == "system":
                system += m.get("content", "") + "\n"
            else:
                msgs.append({"role": m["role"] if m["role"] in ("user", "assistant") else "user",
                             "content": m.get("content", "")})
        body = {"model": self.model, "max_tokens": 8192, "temperature": self.temperature,
                "messages": msgs}
        self.thinking = (not self.no_thinking) and self.effort in EFFORT_BUDGET
        if self.thinking:
            budget = EFFORT_BUDGET[self.effort]
            body["temperature"] = 1
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
            body["max_tokens"] = budget + 8192
        if system.strip():
            body["system"] = system.strip()
        return self.url, self.headers, body

    def send(self, url, headers, payload):
        r = _post_chat(url, headers=headers, payload=payload,
                       timeout=_chat_timeout(False),
                       stream=False, tag=self.tag)
        if r.status_code == 400 and "thinking" in payload and "think" in _resp_body(r, 600).lower():
            # โมเดลนี้ไม่รองรับ thinking — ต้องสร้าง body ใหม่ที่ปิด thinking จริง ๆ
            console.print("[dim](โมเดลนี้ไม่รองรับ thinking — ลองใหม่แบบปกติ)[/dim]")
            self.no_thinking = True
            try:
                r.close()
            except Exception:
                pass
            url, headers, payload = self.spec()
            r = _post_chat(url, headers=headers, payload=payload,
                           timeout=_chat_timeout(False),
                           stream=False, tag=self.tag)
        return r

    def read(self, resp, emit):
        j = resp.json()
        return (fix_mojibake("".join(b.get("text", "") for b in j.get("content", [])
                                     if b.get("type") == "text")),
                j.get("stop_reason", ""))

    def error_body(self, resp):
        try:
            return resp.json()
        except Exception:
            return _resp_body(resp)

    def should_continue(self, finish, round_i):
        return finish == "max_tokens" and not self.thinking and self.depth < 1

    def continue_with(self, text):
        self.depth += 1
        self.effort = ""   # คำตอบต่อไม่เปิด thinking (ตามพฤติกรรมเดิม)
        self.extra = self.extra + [{"role": "assistant", "content": text},
                                   {"role": "user", "content": "continue"}]


def _make_chat_driver(provider, model, messages, temperature, stream, effort, max_tokens, depth):
    """เลือกตัวขับตามชนิดค่าย (ที่เดียวในโค้ด — เพิ่มค่ายใหม่แก้ตรงนี้)"""
    if PROVIDERS[provider].get("type") == "anthropic":
        return _AnthropicChatDriver(model, messages, temperature, effort, max_tokens, depth)
    if provider == "ollama":
        # native /api/chat: /v1 ของ ollama เมิน options → num_ctx ติด 4096 คำตอบไม่จบ
        return _OllamaChatDriver(model, messages, temperature, max_tokens)
    return _OpenAIChatDriver(provider, model, messages, temperature, stream, effort, max_tokens)


def send_messages(provider, model, messages, temperature, stream=True, on_chunk=None, effort=None,
                  _depth=0, max_tokens=None):
    """ส่งแชทครั้งเดียว คืนข้อความตอบ เรียก on_chunk ทุกชิ้นที่สตรีมมา
    - ลูปเดียวทุกค่าย ส่วนที่ต่างอยู่ที่ driver (OpenAI-compatible / Anthropic)
    - เพดาน output สูง + ต่อคำตอบเองเมื่อโดนตัด (length) สูงสุด 2 ทบ
    - effort = low/medium/high เปิด reasoning (เฉพาะค่ายที่รองรับ)
    - max_tokens = ครอบเพดาน output (เช่น boost ใช้ค่าน้อยเพื่อจบไว)"""
    # guardrail: system ของแชทต้องมี CLARIFY_RULES ก่อนเข้า driver (ซ่อมเฉพาะ payload นี้)
    ensure_clarify_rules(messages)
    driver = _make_chat_driver(provider, model, messages, temperature, stream,
                               _chat_effort(provider, effort), max_tokens, _depth)

    def emit(t):
        if t and on_chunk:
            on_chunk(t)

    full = ""
    switches = 0
    swallow_round = False
    ok_rounds = 0  # รอบที่อ่านสำเร็จ (failover ไม่กินโควต้าขอต่อ length)
    for _attempt in range(driver.max_rounds + 8):
        try:
            url, headers, payload = driver.spec()
            r = driver.send(url, headers, payload)
            if r.status_code != 200:
                _sig = _send_status_failover(driver, r, switches, swallow_round,
                                             messages, temperature, stream,
                                             effort, max_tokens, _depth)
                if _sig[0] == "raise":
                    body = _sig[1]
                    raise RuntimeError(driver.error_message(r.status_code, body))
                driver, switches, swallow_round = _sig[1], _sig[2], _sig[3]
                continue
            text, finish = driver.read(r, emit)
            _track_usage(driver.provider_key, driver.model, payload, text)
            _health_note_ok(driver.provider_key, driver.model)
            full += text
            if not (text or "").strip() and driver.should_continue(finish, ok_rounds):
                # ขอต่อด้วยข้อความว่างไม่ได้ — ผู้ให้บริการที่เข้มจะตอบ 400
                # (เกิดกับโมเดลที่คืนข้อความว่างทั้งที่ finish_reason = length)
                console.print("[dim](โมเดลตอบว่างทั้งที่คำตอบถูกตัด — ไม่ขอต่อ)[/dim]")
                finish = ""
            if driver.should_continue(finish, ok_rounds):
                driver.continue_with(text)
                ok_rounds += 1
                swallow_round = True
                continue
            if driver.stream and driver.supports_stream and not full:
                raise RuntimeError("สตรีมว่างเปล่า (ลองเปลี่ยนโมเดล หรือรันอีกครั้ง)")
            if not driver.emit_per_round:
                emit(full)
            return fix_mojibake(full)
        except Exception as e:
            if not (swallow_round and driver.swallows_continuation_errors):
                if not _is_timeout_error(e):
                    raise
                # timeout/conn ไม่มี status code → เดิมไม่เคยเข้า failover เลย
                # (ผู้ใช้เห็น string ดิบของ urllib3 ทุกค่าย) — จัดการเหมือน HTTP 504 ชั่วคราว
                _sig = _send_timeout_failover(driver, e, switches, messages,
                                              temperature, stream, effort,
                                              max_tokens, _depth)
                if _sig[0] == "fail":
                    body = _sig[1]
                    raise NetTimeoutError(body) from None
                driver, switches = _sig[1], _sig[2]
                continue
            break  # ขอต่อไม่สำเร็จ = ใช้คำตอบเท่าที่มี (พฤติกรรมเดิม)
    if not driver.emit_per_round:
        emit(full)
    return fix_mojibake(full)


# ── ตัวย่อยของ send_messages: failover ตอน status != 200 / อ่านเกินเวลา (คืนสัญญาณให้ลูปเดิมตัดสินใจ) ──
# status != 200 -> แทนโมเดล/สลับค่าย: คืน ("retry", driver, switches, swallow) หรือ ("raise", body)
def _send_status_failover(driver, r, switches, swallow_round, messages, temperature, stream, effort, max_tokens, _depth):
    body = driver.error_body(r)
    replacements = _model_replacement_candidates(
        driver.provider_key, driver.model, body)
    if replacements:
        global LAST_MODEL_SWITCH
        old_model = driver.model
        replacement = replacements[0]
        driver.set_model(replacement)
        switches += 1
        LAST_MODEL_SWITCH = {
            "provider": driver.provider_key,
            "from": old_model,
            "to": replacement,
            "ts": time.time(),
        }
        console.print(
            f"[dim](โมเดล {short_model(old_model)} ใช้ไม่ได้ — "
            f"ลอง slug {short_model(replacement)} แทน)[/dim]")
        return ("retry", driver, switches, swallow_round)
    if driver.supports_switch and _quota_dead(r.status_code, body):
        old_name = PROVIDERS[driver.provider_key]["name"]
        np, nm = _failover_provider(driver.provider_key, driver.model)
        nd = _chat_switch_driver(driver, np, nm, messages, temperature,
                                 stream, effort, max_tokens, _depth)
        if np and nd:
            driver = nd
            _apply_provider_switch(np, nm, f"โควต้า {old_name} หมด")
            swallow_round = False
            return ("retry", driver, switches, swallow_round)
    newm = _failover_free(driver.provider_key, driver.model, r.status_code,
                          body, switches)
    if newm:
        driver.set_model(newm)
        switches += 1
        swallow_round = False
        return ("retry", driver, switches, swallow_round)
    if driver.supports_switch and _should_try_provider(r.status_code, body):
        # ในค่ายหมดตัวแล้ว (หรือ key/endpoint ค่ายนี้ใช้ไม่ได้) → ลองค่ายอื่น จำสั้น
        _old_p = driver.provider_key
        np, nm = _failover_provider(driver.provider_key, driver.model, ttl=1800)
        nd = _chat_switch_driver(driver, np, nm, messages, temperature,
                                 stream, effort, max_tokens, _depth)
        if np and nd:
            driver = nd
            _apply_provider_switch(
                np, nm, f"{PROVIDERS[_old_p]['name']} ใช้ไม่ได้ — ลองค่ายอื่น")
            swallow_round = False
            return ("retry", driver, switches, swallow_round)
    return ("raise", body, switches, swallow_round)


# อ่านเกินเวลาในลูป -> คืน ("retry", driver, switches) หรือ ("fail", body)
def _send_timeout_failover(driver, e, switches, messages, temperature, stream, effort, max_tokens, _depth):
    body = _friendly_timeout(e)
    _health_note_slow(driver.provider_key)
    newm = ""
    try:
        newm = _failover_free(driver.provider_key, driver.model, 504,
                              body, switches)
    except Exception:
        newm = ""
    if newm:
        driver.set_model(newm)
        switches += 1
        console.print(f"[dim](ตอบช้าเกินเวลา — สลับเป็นโมเดล {newm} แล้วลองใหม่)[/dim]")
        return ("retry", driver, switches)
    np = nm = ""
    nd = None
    if driver.supports_switch:
        try:
            np, nm = _failover_provider(driver.provider_key, driver.model,
                                        ttl=1800)
            if np:
                nd = _chat_switch_driver(driver, np, nm, messages, temperature,
                                         stream, effort, max_tokens, _depth)
        except Exception:
            nd = None
    if np and nd:
        driver = nd
        _apply_provider_switch(np, nm, "อ่านคำตอบเกินเวลา — ลองค่ายอื่น")
        return ("retry", driver, switches)
    return ("fail", body, switches)


# ── error ภาษาไทย + rotation + สปินเนอร์ + ตั้งชื่อหัวข้อ/compact ────────────
def format_api_error(provider, status, body_text):
    """แปลง error ดิบจาก provider เป็นข้อความภาษาไทยที่แก้ได้จริง"""
    msg, code = "", ""
    try:
        j = json.loads(body_text) if isinstance(body_text, str) else body_text
        if isinstance(j, list):
            j = j[0] if j else {}
        if isinstance(j, dict):
            err = j.get("error", "")
            if isinstance(err, dict):
                msg = err.get("message", "") or str(err)[:300]
                # OpenRouter ซ่อนรายละเอียดไว้ใน metadata (provider ล่มชั่วคราว ฯลฯ)
                meta = err.get("metadata") or {}
                if isinstance(meta, dict):
                    detail = meta.get("raw") or meta.get("provider_name") or ""
                    if detail and str(detail) not in msg:
                        msg = f"{msg} [{str(detail)[:200]}]".strip()
            else:
                msg = str(err) or j.get("message", "")
            code = (j.get("code", "") or (err.get("code", "") if isinstance(err, dict) else ""))
    except Exception:
        msg = str(body_text)[:300]
    if not isinstance(msg, str):
        msg = str(msg)
    code = str(code or "")
    if provider == "puter" and (code == "subscription_required" or status == 402):
        return ("Puter ปฏิเสธ: บัญชีฟรีใช้ API/CLI ไม่ได้ (ต้องมี subscription) — "
                "ใช้ Groq / Gemini / OpenRouter (soonai setup) แทน")
    if status == 402 or _quota_dead(status, msg):
        pname = PROVIDERS.get(provider, {}).get("name", provider)
        return (f"เครดิต/โควต้า {pname} หมด (HTTP {status}): {msg[:150]} — "
                f"ระบบลองสลับค่ายอัตโนมัติแล้ว ถ้ายังไม่ได้: soonai use <ค่ายอื่น> <โมเดลฟรี> "
                f"(ดูค่าย: soonai providers) หรือเติมเครดิต")
    if status == 401 or "auth" in code.lower() or "auth" in msg.lower():
        return f"key ใช้ไม่ได้ (HTTP {status}): {msg or 'ตรวจสอบ key อีกครั้ง'}"
    if status == 404 or "not found" in msg.lower():
        return f"ไม่พบโมเดล/endpoint (HTTP {status}): {msg}"
    if _is_model_not_found(status, body_text):
        return (f"โมเดลไม่ถูกต้องหรือหายไปจาก OpenRouter (HTTP {status}): "
                f"{msg or 'ลองใช้โมเดลอื่น (soonai models ดูรายชื่อ)'}")
    if status == 429 or "quota" in msg.lower() or "limit" in msg.lower() or "rate" in msg.lower():
        return (f"โควต้าหมดหรือถูกจำกัด (HTTP {status}): {msg} "
                f"(โมเดลฟรีจำกัดเรท — รอสักครู่แล้วลองใหม่ หรือสลับโมเดลอื่น)")
    return f"HTTP {status}: {msg or 'ไม่มีรายละเอียด'}"


def retired_model_suggestion(err_text):
    """ดึงชื่อโมเดลทดแทนจากข้อความปลดระวาง (เช่น 'use models/gemini-3.6-flash')"""
    import re
    m = re.search(r"use (?:models/)?([A-Za-z0-9.\-_]+)", str(err_text or ""), re.I)
    return m.group(1) if m else ""


def offer_rotation(provider, model, keys, cfg):
    """ติดเรทลิมิต: เสนอสลับไปโมเดลฟรีตัวอื่นค่ายเดียวกัน คืนโมเดลใหม่หรือ ''"""
    try:
        models, pricing = get_models(provider)
    except Exception:
        return ""
    cands = [m for m in models
             if m != model and is_free_model(m, provider, pricing)][:40]
    if not cands:
        return ""
    console.print("[yellow]โมเดลนี้ติดเรทลิมิต — สลับไปตัวฟรีอื่นชั่วคราวไหม? "
                  "(กด ↑+Enter ส่งข้อความเดิมซ้ำได้เลย)[/yellow]")
    picked = fuzzy_pick("เลือกโมเดล (Esc = ไม่สลับ):",
                        [(m, model_label(m, provider, pricing)) for m in cands])
    if picked and picked not in ("", None):
        cfg["model"] = picked
        save_json(CONFIG_FILE, cfg)
        console.print(f"[green]สลับเป็น {picked} แล้ว[/green]")
        return picked
    return ""


def maybe_migrate_model(provider, model, err_text, keys, cfg):
    """ถ้า error บอกว่าโมเดลปลดแล้วและมีตัวแทน: เสนอสลับ + บันทึก คืนโมเดลใหม่หรือ ''"""
    sug = retired_model_suggestion(err_text)
    if not sug or not sys.stdin.isatty():
        return ""
    try:
        models, _ = get_models(provider)
    except Exception:
        models = []
    if models and sug not in models:
        return ""
    try:
        if Prompt.ask(f"โมเดล {model} ถูกปลดแล้ว เปลี่ยนเป็น {sug} เลยไหม?",
                      choices=["y", "n"], default="y") != "y":
            return ""
    except (EOFError, KeyboardInterrupt):
        console.print()
        return ""
    cfg["model"] = sug
    save_json(CONFIG_FILE, cfg)
    console.print(f"[green]เปลี่ยนเป็น {sug} แล้ว — พิมพ์ข้อความเดิมอีกครั้งได้เลย[/green]")
    return sug


LAST_SEND_ERROR = ""


def run_with_spinner(label, fn, *args, **kwargs):
    """รัน fn (blocking · เช่น AI call) พร้อมสปินเนอร์ + วินาทีนับสด

    ปัญหาเดิม: ขั้นอย่าง boost/verify ค้างเงียบ ๆ ดูเหมือนแฮงค์
    วิธีนี้โชว์ "กำลังทำ X… 3s" ให้เห็นว่ากำลังทำงานจริง
    fn รันครั้งเดียวเสมอ — ถ้าเปิด Live ไม่ได้ก็รันตรง ๆ ไม่ให้งานล่ม"""
    class _Elapsed:
        def __init__(self):
            self.t0 = time.time()

        def __rich__(self):
            el = time.time() - self.t0
            timer = f" [dim]{el:.0f}s[/dim]" if el >= 1 else ""
            return Spinner("dots", text=f"{label}{timer}")

    live = None
    try:
        live = Live(_Elapsed(), console=console, refresh_per_second=8)
        live.start()
    except Exception:
        live = None
    try:
        return fn(*args, **kwargs)
    finally:
        if live is not None:
            try:
                live.stop()
            except Exception:
                pass


def refresh_session_title(sid, provider, model, messages,
                          label="กำลังตั้งหัวข้อบทสนทนา…"):
    """สร้างหัวข้อ session จาก AI ถ้ายังไม่มี/ยังมั่ว — เรียกหลัง save/resume

    เช็กก่อนแบบ cheap แล้วค่อยเปิดสปินเนอร์ (กันกะพริบฟรีทุกเทิร์น)
    ยังไม่ต้องสร้าง = คืนชื่อเดิมทันที ไม่มี AI call ไม่มีสปินเนอร์"""
    try:
        f = SESSIONS_DIR / f"{sid}.json"
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not _title_needs_ai(d):
        return str((d or {}).get("name", "") or "") if isinstance(d, dict) else ""
    try:
        return run_with_spinner(label, ensure_session_title,
                                sid, provider, model, messages) or \
            str(d.get("name", "") or "")
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:refresh_session_title",
                           "ตั้งหัวข้อ session ไม่สำเร็จ — ใช้ชื่อเดิมต่อ")
        return str(d.get("name", "") or "")


_TITLE_JOBS = set()
_TITLE_JOBS_LOCK = threading.Lock()


def refresh_session_title_async(sid, provider, model, messages):
    """ตั้งชื่อ session เบื้องหลังโดยไม่บล็อก prompt หลังคำตอบหลักจบ"""
    if not sid:
        return
    key = str(sid)
    with _TITLE_JOBS_LOCK:
        if key in _TITLE_JOBS:
            return
        _TITLE_JOBS.add(key)

    snapshot = [dict(m) for m in (messages or []) if isinstance(m, dict)]

    def _work():
        try:
            refresh_session_title(key, provider, model, snapshot)
        except Exception as e:
            _DBG.log_swallowed(e, "soonai.py:refresh_session_title_async",
                               "ตั้งหัวข้อ session เบื้องหลังไม่สำเร็จ")
        finally:
            with _TITLE_JOBS_LOCK:
                _TITLE_JOBS.discard(key)

    threading.Thread(target=_work, name=f"soonai-title-{key}", daemon=True).start()


def show_reply(provider, model, messages, temperature, effort=None):
    """สตรีมคำตอบแบบ markdown สด ๆ (โชว์สปินเนอร์ก่อนโทเคนแรก) คืนข้อความเต็ม"""
    global LAST_SEND_ERROR
    LAST_SEND_ERROR = ""
    import time
    full = ""
    t0 = time.time()
    thinking_note = ""
    if provider in ("ollama", "lmstudio"):
        pname = PROVIDERS.get(provider, {}).get("name", provider).split(" ")[0]
        thinking_note = f" ({pname} กำลังโหลดโมเดลเข้าแรม — ครั้งแรกอาจช้าหน่อย)"

    class _Thinking:
        """สปินเนอร์รอโทเคนแรก — โชว์วินาทีที่ผ่านไปให้เห็นว่ากำลังทำงานจริง (ไม่ค้าง)"""

        def __init__(self):
            self.text = ""
            self.t0 = time.time()
            self._spin = Spinner("dots", text=self._label())

        def _label(self):
            el = time.time() - self.t0
            # โชว์เวลาเฉพาะเมื่อเกิน 1 วิ — กันข้อความกระตุกทุกเฟรม
            timer = f" [dim]{el:.0f}s[/dim]" if el >= 1.0 else ""
            return f"กำลังคิด…{timer}{thinking_note}"

        def __rich__(self):
            if not self.text:
                self._spin = Spinner("dots", text=self._label())
                return self._spin
            try:
                return Markdown(self.text)
            except Exception:
                return self.text

    state = _Thinking()
    try:
        # refresh 10fps = ตัวเลขวินาที/สปินเนอร์ขยับเห็นชัด ไม่ดูค้าง
        with Live(state, console=console, refresh_per_second=10) as live:
            def cb(ch):
                nonlocal full
                full += ch
                state.text = fix_mojibake(full)
                live.update(state)
            send_messages(provider, model, messages, temperature, stream=True, on_chunk=cb,
                          effort=effort)
    except Exception as e:
        LAST_SEND_ERROR = str(e)
        console.print(f"[red]ERROR: {e}[/red]")
        return ""
    if full:
        full = fix_mojibake(full)
        _u = usage_line()
        console.print(f"[dim]({time.time() - t0:.1f}s · {len(full)} ตัวอักษร"
                      f"{' · รวม session ' + _u if _u else ''})[/dim]")
    return full


def build_transcript(messages, per_msg=800, total=12000):
    lines = []
    for m in messages or []:
        role = m.get("role", "")
        if role == "system":
            continue
        c = str(m.get("content", "") or "")
        if role == "tool":
            c = "(ผล tool: " + c[:300] + ")"
            who = "ระบบ"
        else:
            c = c[:per_msg]
            who = "ผู้ใช้" if role == "user" else "AI"
        lines.append(f"{who}: {c}")
    return "\n".join(lines)[:total]


def summarize_text(provider, model, transcript):
    tmp = [{"role": "system", "content": "สรุปบทสนทนาต่อไปนี้เป็นภาษาไทยให้แม่น: ประเด็นหลัก, ข้อสรุป/การตัดสินใจ, งานที่ค้างอยู่ ตอบสั้นกระชับ"},
           {"role": "user", "content": "สรุปบทสนทนานี้:\n\n" + transcript}]
    try:
        return send_messages(provider, model, tmp, 0.2, stream=False, effort="") or ""
    except KeyboardInterrupt:
        console.print("[dim](ยกเลิกย่อประวัติ)[/dim]")
        return ""
    except Exception as e:
        console.print(f"[dim](สรุปไม่สำเร็จ: {e})[/dim]")
        return ""


def auto_compact_history(provider, model, history, keep_last=COMPACT_KEEP):
    """ประวัติยาวเกิน → สรุปส่วนเก่าเก็บไว้ คืน history ใหม่ (เรียกอัตโนมัติ)
    ยาว = จำนวนข้อความเกิน หรือกิน context เกิน ~70% ของงบ token"""
    non_sys = [m for m in history if m.get("role") != "system"]
    try:
        over_tokens = messages_tokens(non_sys) > int(context_budget() * 0.7)
    except Exception:
        over_tokens = False
    by_count = len(non_sys) > 16 and len(non_sys) - keep_last >= 4
    by_token = over_tokens and len(non_sys) - keep_last >= 2
    if not (by_count or by_token):
        return history
    old, recent = non_sys[:-keep_last], non_sys[-keep_last:]
    reason = ("ประวัติกิน context ~%s token เกินงบ" % _kfmt(messages_tokens(non_sys))
              if by_token and not by_count else "ประวัติยาวแล้ว")
    console.print(f"[dim]({reason} — กำลังย่อส่วนเก่าเป็นสรุป…)[/dim]")
    summary = summarize_text(provider, model, build_transcript(old))
    if not summary:
        return history
    sys_msgs = [m for m in history if m.get("role") == "system"]
    new_hist = sys_msgs + [
        {"role": "user", "content": COMPACT_MARK + "อัตโนมัติ เหลือสรุปด้านล่าง)"},
        {"role": "assistant", "content": summary}] + recent
    console.print("[dim](ย่อประวัติแล้ว)[/dim]")
    return new_hist


# คำสั้น ๆ ที่ boost จะคืนคำเดิมอยู่แล้ว (ตาม BOOST_SYSTEM) → ข้าม AI call เปล่า ๆ
_BOOST_SKIP = frozenset({
    "hi", "hello", "hey", "thanks", "thank you", "thx", "ok", "okay", "bye",
    "good morning", "good night", "yes", "no", "y", "n",
    "สวัสดี", "สวัสดีครับ", "สวัสดีค่ะ", "ดีครับ", "ดีค่ะ", "หวัดดี",
    "ขอบคุณ", "ขอบคุณครับ", "ขอบคุณค่ะ", "โอเค", "ได้", "ใช่", "ไม่",
    "ครับ", "ค่ะ", "จ้า", "ฮัลโหล",
})

BOOST_SYSTEM = ("Rewrite the user's rough chat prompt into a clear, precise, effective prompt. "
                "Keep the same language (Thai stays Thai). Preserve intent exactly, add no new requirements. "
                "If the message is just a short greeting or small talk (hi, hello, thanks, etc.), "
                "return it EXACTLY as-is with no expansion. "
                 "Otherwise structure: goal + context + desired output format. "
                 "Return ONLY the rewritten prompt, no explanations, no template labels.")


BOOST_EN_SYSTEM = ("Translate the user's Thai chat prompt into precise, faithful English. "
                   "Keep the exact same intent: add no new requirements, drop nothing. "
                   "Keep code, file paths, command names, numbers, URLs and proper nouns "
                   "UNCHANGED and untranslated. Keep anything already in English as-is. "
                   "If the message is already English (or just a short greeting/small talk "
                   "like hi, hello, thanks), return it EXACTLY as-is. "
                   "Return ONLY the translated prompt, no explanations, no quotes, "
                   "no template labels.")


BOOST_MODES = ("off", "th", "en")


# ── boost/verify + pickers (fuzzy/AI choices) ────────────────────────────────
def boost_mode(cfg):
    """โหมด boost: off=ปิด th=เกลาภาษาไทย en=แปลเป็นอังกฤษ (True เก่า = th)"""
    try:
        v = (cfg or {}).get("boost", True)
    except Exception:
        return "th"
    if v is True:
        return "th"
    s = str(v or "").strip().lower()
    if s in ("en", "english", "อังกฤษ"):
        return "en"
    if s in ("off", "false", "0", "ปิด", ""):
        return "off"
    return "th"


class TurnCancelled(Exception):
    """ผู้ใช้กด Ctrl+C กลางรอบ — ยกเลิกเทิร์นนี้กลับไปรอคำสั่ง (ไม่ล่ม)"""


def boost_worth_it(raw, mode):
    """เช็กว่าคุ้มยิง boost ไหม (ข้ามเมื่อรู้ว่าโมเดลคืนคำเดิม ประหยัด 1 round-trip)

    boost = AI call แยกต่างหากก่อนคำถามจริง → ข้อความสั้น/ทักทายไม่คุ้ม
    (โมเดลจะคืนคำเดิมอยู่แล้วตาม BOOST_SYSTEM — เสีย latency เปล่า ๆ)"""
    t = str(raw or "").strip()
    if not t:
        return False
    # สั้นเกินไป = ไม่มีอะไรให้เกลา แต่กิน 1 round-trip เต็ม ๆ → ข้าม
    if len(t) < 20:
        return False
    # ทักทาย/ขอบคุณ/คำสั้น ๆ ที่ BOOST_System คืนคำเดิมอยู่แล้ว → ข้าม
    if t.lower().rstrip("!?.") in _BOOST_SKIP:
        return False
    if t.isascii() and str(mode or "th").strip().lower() == "en":
        return False  # โหมดแปลอังกฤษเจออังกฤษอยู่แล้ว = คืนคำเดิมชัวร์
    return True


def boost_prompt(provider, model, raw, mode="th"):
    """เกลาพร้อมดิบ (th) หรือแปลอังกฤษตรงตัว (en) ก่อนส่งจริง (ล้มเหลว = ใช้ข้อความเดิม)"""
    sys = BOOST_EN_SYSTEM if str(mode or "th").strip().lower() == "en" else BOOST_SYSTEM
    if not boost_worth_it(raw, mode):
        return str(raw or "").strip().strip('"').strip() or str(raw or "")
    cap = min(4000, max(600, len(str(raw or ""))))
    try:
        out = send_messages(provider, model,
                            [{"role": "system", "content": sys},
                             {"role": "user", "content": raw}],
                            0.3, stream=False, effort="", max_tokens=cap)
        out = (out or "").strip().strip('"').strip()
        return out if out else raw
    except KeyboardInterrupt:
        console.print("[dim](ยกเลิกแต่งประโยค)[/dim]")
        raise TurnCancelled()
    except Exception:
        console.print("[dim](boost ไม่สำเร็จ ใช้ข้อความเดิม)[/dim]")
        return raw


def verify_answer(provider, model, question, answer, temperature=0.2):
    tmp = [{"role": "system", "content": "คุณคือผู้ตรวจสอบความถูกต้อง จับผิดโค้ด/API/ข้อเท็จจริงอย่างเข้มงวด"},
           {"role": "user", "content": f"คำถามเดิม:\n{question[:4000]}\n\nคำตอบที่ให้ไป:\n{answer[:6000]}\n\nตรวจสอบความถูกต้อง ชี้ข้อผิดพลาดพร้อมคำตอบที่แก้แล้ว ถ้าถูกอยู่แล้วให้ยืนยันสั้น ๆ"}]
    console.print("[bold green]ผลทวนสอบ:[/]")
    return show_reply(provider, model, tmp, temperature)


def fuzzy_pick(message, items):
    """เลือกแบบพิมพ์ค้นหา + ลูกศร (items = [(value, label)])
    คืน value / '' ถ้ากดยกเลิก / None ถ้าใช้ไม่ได้ (ให้ caller ใช้วิธีสำรอง)"""
    if not sys.stdin.isatty():
        return None
    try:
        from InquirerPy import inquirer
        ans = inquirer.fuzzy(
            message=message,
            choices=[{"name": label, "value": value} for value, label in items],
            max_height=12,
        ).execute()
        return ans if isinstance(ans, str) else ""
    except Exception:
        return None


CHOICE_CUSTOM = "พิมพ์เอง…"
N_CHOICES = 5  # ช้อย AI 5 ข้อ + ข้อ 6 พิมพ์เอง


def ai_make_choices(provider, model, question, n=N_CHOICES, temperature=0.3):
    """วิเคราะห์คำถามแล้วแตกเป็นตัวเลือกสั้น ๆ n ข้อ คืน [str] (ล้มเหลว = [])"""
    import re
    msgs = [{"role": "system",
             "content": ("You break a vague user request into distinct choices. "
                         "Reply in Thai. "
                         f"Output EXACTLY {n} lines, each one short option starting with 'N. ' "
                         "(e.g. '1. ...'). No intro, no outro, no explanations. "
                         "Each option = one concrete interpretation or action, max 1 line.")},
            {"role": "user",
             "content": f"แตกคำขอนี้เป็น {n} ตัวเลือก:\n{(question or '')[:1500]}"}]
    try:
        out = send_messages(provider, model, msgs, temperature,
                            stream=False, effort="", max_tokens=600) or ""
    except Exception:
        return []
    opts = []
    leftovers = []
    for line in out.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\d+)[).:：]\s*(.+)$", s)
        if m:
            s = m.group(2).strip()
        elif s[0] in "*-•–-":
            s = s[1:].strip()
            m2 = re.match(r"^(\d+)[).:：]\s*(.+)$", s)
            if m2:
                s = m2.group(2).strip()
        else:
            if len(s) >= 2:
                leftovers.append(s)
            continue
        if not s or len(s) < 2:
            continue
        try:
            s = _clean_title(s, 60)
        except Exception:
            pass
        if s and s not in opts:
            opts.append(s)
        if len(opts) >= n:
            break
    if len(opts) < 2:
        # โมเดลไม่ทำตามฟอร์แมต: รับทุกบรรทัดที่ไม่ซ้ำแทน
        for s in leftovers:
            try:
                s = _clean_title(s, 60)
            except Exception:
                pass
            if s and s not in opts:
                opts.append(s)
            if len(opts) >= n:
                break
    return opts[:n]


def pick_with_ai(provider, model, question, temperature=0.2):
    """ช้อย 6 ข้อ (5 ตัวเลือก AI + ข้อ 6 พิมพ์เอง) คืนข้อความที่เลือก
    '' = ยกเลิก, แตกช้อยไม่ได้ = ส่งคำถามเดิม"""
    try:
        console.print("[dim](กำลังวิเคราะห์คำถามเป็นตัวเลือก…)[/dim]")
        opts = ai_make_choices(provider, model, question, N_CHOICES, temperature)
    except (EOFError, KeyboardInterrupt):
        console.print()
        return ""
    except Exception as e:
        console.print(f"[yellow]สร้างช้อยไม่ได้ ({e}) — ส่งคำถามเดิม[/yellow]")
        return question
    if len(opts) < 2:
        console.print("[yellow]AI แตกตัวเลือกไม่ได้ — ส่งคำถามเดิม[/yellow]")
        return question
    items = [(o, f"{i}. {o}") for i, o in enumerate(opts, 1)]
    items.append((CHOICE_CUSTOM, f"{len(items) + 1}. {CHOICE_CUSTOM}"))
    picked = fuzzy_pick("เลือกข้อที่ตรงที่สุด:", items)
    if picked is None and sys.stdin.isatty():
        # สำรองแบบพิมพ์หมายเลข
        try:
            for _, label in items:
                console.print(f"  {label}")
            n = console.input("เลือกหมายเลข (0 = ยกเลิก): ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return ""
        if not n.isdigit() or not (1 <= int(n) <= len(items)):
            return ""
        picked = items[int(n) - 1][0]
    if picked == CHOICE_CUSTOM:
        try:
            return Prompt.ask("พิมพ์คำตอบของคุณ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return ""
    return picked or ""


def sessions_dialog(items):
    """ไดอะล็อกเลือก session แบบคลิกเมาส์/ลูกศรได้
    คืน ('resume', id) / ('new',) / ('cancel',) / ('unavailable',)"""
    if not sys.stdin.isatty():
        return ("unavailable",)
    try:
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
        from prompt_toolkit.layout import Layout
        from prompt_toolkit.styles import Style
        from prompt_toolkit.widgets import Button, Dialog
    except Exception:
        return ("unavailable",)

    result = {}
    kb = KeyBindings()
    kb.add("down")(focus_next)
    kb.add("up")(focus_previous)
    kb.add("tab")(focus_next)
    kb.add("s-tab")(focus_previous)

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result=("cancel",))

    def _make_choose(value):
        def _go():
            try:
                from prompt_toolkit.application.current import get_app
                get_app().exit(result=value)
            except Exception:
                result["v"] = value
        return _go

    buttons = []
    for it in (items or [])[:MAX_SESSIONS]:
        label = f"▶ {_clean_title(it.get('name') or '-', 32)}  ·  {it.get('provider', '')}/{short_model(it.get('model', ''), 28)}  ·  {it.get('turns', 0)} รอบ"
        buttons.append(Button(label, handler=_make_choose(("resume", it["id"]))))
    buttons.append(Button("➕ แชทใหม่", handler=_make_choose(("new",))))
    buttons.append(Button("✕ ยกเลิก", handler=_make_choose(("cancel",))))

    try:
        from prompt_toolkit.layout.containers import HSplit
        dialog = Dialog(title="บทสนทนาที่บันทึก (คลิกเมาส์ / ลูกศร+Enter)",
                        body=HSplit(buttons, padding=1),
                        modal=True)
        app = Application(layout=Layout(dialog), key_bindings=kb,
                          mouse_support=True, full_screen=False,
                          style=Style.from_dict({"dialog.body": "bg:#1a2230"}))
        out = app.run()
        if out is not None:
            return out
        return result.get("v", ("cancel",))
    except Exception:
        return ("unavailable",)


def pick_model(provider, keys, free_only=False, search="", refresh=False):
    """ให้ผู้ใช้เลือกโมเดลจากลิสต์ล่าสุด คืนชื่อโมเดลหรือ '' """
    err = require_usable(provider, keys)
    if err:
        console.print(f"[yellow]{err}[/yellow]")
        return ""
    with console.status("กำลังดึงรายชื่อโมเดลล่าสุด…"):
        models, pricing = get_models(provider, refresh=refresh)
    if search:
        models = [m for m in models if search.lower() in m.lower()]
    if free_only:
        models = [m for m in models if is_free_model(m, provider, pricing)]
        # Sort free models: prioritize smaller/faster models
        def speed_key(m):
            ml = m.lower()
            score = 0
            for kw in ["mini", "small", "nano", "flash", "lite", "tiny", "micro", "1b", "3b", "7b", "8b"]:
                if kw in ml:
                    score -= 10
            for kw in ["ultra", "large", "xl", "xxl", "70b", "120b", "235b", "405b", "550b"]:
                if kw in ml:
                    score += 100
            return score
        models.sort(key=speed_key)
    if not models:
        console.print("[yellow]ไม่พบโมเดลตามเงื่อนไข (ลองปิด --free-only หรือเปลี่ยนคำค้น)[/yellow]")
        hint = empty_list_hint(provider)
        if hint:
            console.print(f"[dim]{hint}[/dim]")
        return ""
    picked = fuzzy_pick("Select model:",
                        [(m, model_label(m, provider, pricing)) for m in models])
    if picked:
        return picked
    if picked == "":
        return ""
    table = neo_table(title=f"{PROVIDERS[provider]['name']} — {len(models)} โมเดล",
                  show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("model", style="white")
    table.add_column("ราคา", justify="center")
    for i, m in enumerate(models[:30], 1):
        ps = price_str(provider, m, pricing)
        table.add_row(str(i), m, tier_label(price_tier(m, provider, pricing)) + (f" {ps}" if ps else ""))
    console.print(table)
    if len(models) > 30:
        console.print("[dim]แสดง 30 ตัวแรก — ใช้ --search เพื่อค้นหาเพิ่มเติม[/dim]")
    console.print("[dim]ป้ายราคา: [green]Free[/]=$0 · [yellow]tier[/]=ฟรีในโควต้า · [dim]paid=เสียเงิน[/dim][/dim]")
    try:
        n = int(Prompt.ask("หมายเลขโมเดล (0 = ยกเลิก)", default="1"))
    except Exception:
        return ""
    if n < 1 or n > min(30, len(models)):
        return ""
    return models[n - 1]


# ── คำสั่ง CLI: providers/models/key/use/setup/status/exec/ask ───────────────
def cmd_providers(args, keys, cfg):
    table = neo_table(title="SoonAI — ผู้ให้บริการทั้งหมด", show_lines=False)
    table.add_column("ID", style="cyan")
    table.add_column("ชื่อ", style="white")
    table.add_column("key", justify="center")
    table.add_column("ฟรี", justify="center")
    for pid, p in PROVIDERS.items():
        has = "[green]มี[/green]" if (get_key(pid, keys) or p.get("no_key")) else "[red]-[/red]"
        free = "[green]free-tier[/green]" if p.get("is_free_tier") else ""
        name = ("[bold]* [/bold]" if pid == cfg.get("provider") else "") + p["name"]
        table.add_row(pid, name, has, free)
    console.print(table)
    tool_only = [pid for pid, p in PROVIDERS.items() if p.get("tool_only")]
    if tool_only:
        console.print(f"[dim]{', '.join(tool_only)} = web tools ของ agent (web_search/web_fetch "
                      "หรือ soonai mcp install tinyfish) — ไม่ใช่ค่ายแชท เลือกเป็นค่ายหลักไม่ได้[/dim]")
    console.print("[dim]* = ค่าเริ่มต้นปัจจุบัน (เปลี่ยนด้วย soonai use PROVIDER MODEL)[/dim]")


def cmd_models(args, keys, cfg):
    provider = args.provider or cfg.get("provider", "ollama")
    if provider not in PROVIDERS:
        console.print(f"[red]ไม่รู้จัก provider: {provider}[/red]")
        return 1
    if PROVIDERS[provider].get("tool_only"):
        console.print(f"[yellow]{PROVIDERS[provider]['name']} ไม่ใช่ค่ายแชท (ไม่มี endpoint "
                      "คุยโมเดล) — เป็น web tools ของ agent แทน (web_search/web_fetch)[/yellow]")
        return 1
    err = require_usable(provider, keys)
    if err:
        console.print(f"[yellow]{err}[/yellow]")
        return 1
    with console.status("กำลังดึงรายชื่อโมเดลล่าสุด…"):
        models, pricing = get_models(provider, refresh=args.refresh)
    table = neo_table(title=f"{PROVIDERS[provider]['name']} — {len(models)} โมเดล", show_lines=False)
    table.add_column("model", style="white")
    table.add_column("ราคา", justify="center")
    shown = n_free = n_tier = 0
    for m in models:
        tier = price_tier(m, provider, pricing)
        if tier == "free":
            n_free += 1
        elif tier == "tier":
            n_tier += 1
        if args.free_only and tier == "paid":
            continue
        if args.search and args.search.lower() not in m.lower():
            continue
        table.add_row(m, tier_label(tier) + (f" {ps}" if (ps := price_str(provider, m, pricing)) else ""))
        shown += 1
    console.print(table)
    console.print(f"[dim]แสดง {shown}/{len(models)} โมเดล "
                  f"([green]ฟรี {n_free}[/] · [yellow]tier {n_tier}[/] · [dim]จ่าย {len(models) - n_free - n_tier}[/dim])[/dim]")
    console.print("[dim]ฟรี=$0 · tier=ฟรีในโควต้า · จ่าย=เสียเงิน[/dim]")
    return 0


def cmd_key(args, keys, cfg):
    if args.action == "list":
        table = neo_table(title="API keys (เก็บในเครื่องเท่านั้น)", show_lines=False)
        table.add_column("ID", style="cyan")
        table.add_column("สถานะ")
        for pid, p in PROVIDERS.items():
            if p.get("no_key"):
                table.add_row(pid, "[green]ไม่ต้องใช้ key[/green]")
            elif get_key(pid, keys):
                table.add_row(pid, "[green]บันทึกแล้ว[/green]")
            else:
                table.add_row(pid, f"[dim]ยังไม่มี — ขอได้ที่ {p.get('key_url', '')}[/dim]")
        console.print(table)
    elif args.action == "set":
        if args.provider not in PROVIDERS:
            console.print(f"[red]ไม่รู้จัก provider: {args.provider}[/red]")
            return 1
        if PROVIDERS[args.provider].get("no_key"):
            console.print(f"[yellow]{args.provider} ไม่ต้องใช้ key[/yellow]")
            return 1
        key = (args.key or "").strip()
        if not key:
            # ไม่ส่ง KEY มาทาง argv (โผล่ history/ps) → ถามแบบซ่อนจอแทน
            if not sys.stdin.isatty():
                console.print("[red]โหมด pipe: ระบุ key มาด้วย "
                              "(soonai key set PROVIDER KEY)[/red]")
                return 1
            console.print("[dim]พิมพ์/วาง key (ไม่แสดงบนจอ) แล้ว Enter[/dim]")
            try:
                key = _ask_secret(f"API key ของ {args.provider}")
            except (EOFError, KeyboardInterrupt):
                console.print()
                return 1
            if not key:
                console.print("[yellow]ยกเลิก (ไม่ได้ใส่ key)[/yellow]")
                return 1
        keys[args.provider] = key
        save_keys(keys)
        console.print(f"[green]บันทึก key ของ {args.provider} แล้ว[/green]")
    elif args.action == "rm":
        keys.pop(args.provider, None)
        save_keys(keys)
        console.print(f"ลบ key ของ {args.provider} แล้ว")
    return 0


def cmd_provider(args, keys, cfg):
    """จัดการ provider แบบ OpenAI-compatible ที่ผู้ใช้เพิ่มเอง"""
    action = args.action
    if action in ("list", "ls"):
        custom = [pid for pid, spec in PROVIDERS.items() if spec.get("custom")]
        if not custom:
            console.print("[dim]ยังไม่มี custom provider — เพิ่มด้วย: "
                          "soonai provider add NAME URL MODEL[/dim]")
            return 0
        for pid in custom:
            spec = PROVIDERS[pid]
            console.print(f"[cyan]{pid}[/cyan] — {spec['name']} · {spec['base']} · "
                          f"{', '.join(spec.get('fallback_models', [])) or '(ไม่ระบุโมเดล)'}")
        return 0
    if action == "rm":
        pid = str(args.name or "").strip().lower()
        custom = cfg.get("custom_providers", {})
        if not isinstance(custom, dict) or pid not in custom:
            console.print(f"[red]ไม่พบ custom provider: {pid}[/red]")
            return 1
        custom.pop(pid, None)
        if cfg.get("provider") == pid:
            cfg["provider"], cfg["model"] = "ollama", ""
        keys.pop(pid, None)
        save_keys(keys)
        save_json(CONFIG_FILE, cfg)
        apply_custom_providers(cfg)
        console.print(f"[green]ลบ custom provider '{pid}' แล้ว[/green]")
        return 0
    pid = str(args.name or "").strip().lower()
    base = str(args.url or "").strip().rstrip("/")
    model = str(args.model or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", pid):
        console.print("[red]ชื่อใช้ a-z, 0-9, _ หรือ - และต้องขึ้นต้นด้วยตัวอักษร[/red]")
        return 1
    if pid in PROVIDERS and not PROVIDERS[pid].get("custom"):
        console.print(f"[red]ชื่อ '{pid}' ชนกับ provider ในระบบ[/red]")
        return 1
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        console.print("[red]URL ต้องเป็น http(s) URL ที่ถูกต้อง[/red]")
        return 1
    if base.endswith("/chat/completions"):
        base = base[:-len("/chat/completions")].rstrip("/")
    if not model:
        console.print("[red]ต้องระบุ model เริ่มต้น[/red]")
        return 1
    custom = cfg.setdefault("custom_providers", {})
    if not isinstance(custom, dict):
        custom = cfg["custom_providers"] = {}
    headers = {}
    for item in args.header or []:
        if "=" not in item:
            console.print(f"[red]header ต้องเป็น NAME=VALUE: {item}[/red]")
            return 1
        key, value = item.split("=", 1)
        if key.strip().lower() in {"authorization", "x-api-key", "api-key"}:
            console.print("[red]ห้ามเก็บ auth header ใน config ใช้ API key/env แทน[/red]")
            return 1
        headers[key.strip()] = value.strip()
    custom[pid] = {"name": args.display_name or pid, "base": base, "model": model,
                   "models": [model], "models_url": args.models_url or (base + "/models"),
                   "extra_headers": headers, "key_env": args.key_env or ""}
    save_json(CONFIG_FILE, cfg)
    apply_custom_providers(cfg)
    if args.api_key:
        keys[pid] = args.api_key.strip()
        save_keys(keys)
    elif not get_key(pid, keys) and sys.stdin.isatty():
        key = _ask_secret(f"API key ของ {pid} (Enter = ใช้ env/ข้าม)").strip()
        if key:
            keys[pid] = key
            save_keys(keys)
    console.print(f"[green]เพิ่ม provider '{pid}' แล้ว[/green] — ใช้: "
                  f"soonai use {pid} {model}")
    return 0


def cmd_use(args, keys, cfg):
    if args.provider not in PROVIDERS:
        console.print(f"[red]ไม่รู้จัก provider: {args.provider}[/red]")
        return 1
    if PROVIDERS[args.provider].get("tool_only"):
        console.print(f"[red]{PROVIDERS[args.provider]['name']} ไม่ใช่ค่ายแชท — เลือกเป็น "
                      "provider หลักไม่ได้ (ใช้เป็นเครื่องมือ web: web_search/web_fetch หรือ "
                      "soonai mcp install tinyfish)[/red]")
        return 1
    cfg["provider"] = args.provider
    if args.model:
        m = ensure_model_valid(args.provider, args.model, keys)
        if not m:
            return 1
        cfg["model"] = m
    save_json(CONFIG_FILE, cfg)
    console.print(f"[green]ตั้งค่าเริ่มต้น: {cfg['provider']} / {cfg.get('model') or '(ยังไม่เลือกโมเดล)'}[/green]")


def cmd_pull(args, keys, cfg):
    """ดาวน์โหลดโมเดล Ollama มาใช้บนเครื่อง (ฟรี) พร้อมแถบความคืบหน้า"""
    from rich.progress import Progress, BarColumn, DownloadColumn, TextColumn, TransferSpeedColumn
    model = args.model.strip()
    try:
        ok = requests.get("http://localhost:11434/api/tags", timeout=3).status_code == 200
    except Exception:
        ok = False
    if not ok:
        console.print("[red]ติดต่อ Ollama ไม่ได้ — เปิดโปรแกรม Ollama ก่อน[/red]")
        return 1
    console.print(f"กำลังดาวน์โหลดโมเดล [bold]{model}[/bold] (ครั้งแรกไฟล์ใหญ่ รอสักครู่)…")
    try:
        r = requests.post("http://localhost:11434/api/pull", json={"name": model},
                          timeout=3600, stream=True)
    except Exception as e:
        console.print(f"[red]ERROR: {e}[/red]")
        return 1
    if r.status_code != 200:
        try:
            console.print(f"[red]ERROR: {r.json().get('error', r.text[:300])}[/red]")
        except Exception:
            console.print(f"[red]ERROR: HTTP {r.status_code}[/red]")
        return 1
    task_id = None
    try:
        with Progress(TextColumn("{task.description}"), BarColumn(),
                      DownloadColumn(), TransferSpeedColumn()) as prog:
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                if "error" in j:
                    console.print(f"[red]ERROR: {j['error']}[/red]")
                    return 1
                status = j.get("status", "")
                total, done = j.get("total") or 0, j.get("completed") or 0
                if total:
                    if task_id is None:
                        task_id = prog.add_task(status, total=total)
                    prog.update(task_id, total=total, completed=done, description=status)
                elif status and status != "success":
                    console.print(f"[dim]{status}[/dim]")
                if status == "success":
                    break
    except KeyboardInterrupt:
        console.print("\n[yellow]ยกเลิกแล้ว[/yellow]")
        return 1
    console.print(f"[green]พร้อมใช้: {model}[/green]")
    return 0


def cmd_auto(args, keys, cfg):
    """ดู/เปิด/ปิด อนุมัติอัตโนมัติ (จำถาวรใน config.json)"""
    if args.state in ("on", "off"):
        cfg["auto_approve"] = (args.state == "on")
        save_json(CONFIG_FILE, cfg)
    on = bool(cfg.get("auto_approve"))
    if on:
        console.print("[yellow]AUTO-APPROVE: เปิดอยู่ — agent จะเขียนไฟล์/รันคำสั่งทันทีโดยไม่ถาม "
                      "(ปิดด้วย soonai auto off)[/yellow]")
    else:
        console.print("[dim]auto-approve: ปิดอยู่ (ถาม y/n ทุกครั้ง) — เปิดด้วย soonai auto on[/dim]")
    return 0


def cmd_status(args, keys, cfg):
    try:
        _cwd = str(Path.cwd())
    except Exception:
        _cwd = "."
    _shell = _shell_mode()
    _shell_txt = {"off": "[dim]off (agent รันคำสั่งไม่ได้)[/dim]",
                  "safe": "[green]safe (อ่าน/เทสต์ใน allowlist)[/green]",
                  "on": "[yellow]on (เต็ม — รับความเสี่ยงเอง)[/yellow]"}.get(_shell, _shell)
    _tcmd = detect_test_command() or "(ไม่พบ)"
    _cps = len(checkpoint_records())
    try:
        _st = _skill_state()
        _sk_learn = (f"ใช้บ่อย {sum(1 for n in _st['used'] if skill_used_often(n))} · "
                     f"หยุดเสนอ {sum(1 for n in _st['declined'] if skill_is_declined(n))}")
        if not _st["used"] and not _st["declined"]:
            _sk_learn = "[dim]ยังไม่จดอะไร[/dim]"
    except Exception:
        _sk_learn = "-"
    console.print(Panel(
        f"provider เริ่มต้น: [bold]{cfg.get('provider')}[/bold] / {cfg.get('model') or '(ยังไม่เลือก)'}\n"
        f"ที่ทำงานปัจจุบัน: [bold]{_cwd}[/bold]\n"
        f"keys ที่บันทึก: [bold]{len(keys)}[/bold] ({', '.join(sorted(keys)) or '-'})\n"
        f"auto-approve: {'[yellow]เปิดอยู่ (ไม่ถามก่อนเขียน)[/yellow]' if cfg.get('auto_approve') else '[dim]ปิดอยู่[/dim]'}\n"
        f"shell ของ agent: {_shell_txt}\n"
        f"ธีม UI: [dim]{_ui_theme_name()}[/dim] [dim](/theme สลับ)"
        f"[/dim]\n"
        f"คำสั่งเทสต์ของโปรเจกต์: [dim]{_tcmd}[/dim]\n"
        f"งบ context: [dim]~{_kfmt(context_budget())} token[/dim] · "
        f"checkpoint ในงานนี้: [dim]{_cps} รายการ[/dim]\n"
        f"ความจำสกิลของคุณ: [dim]{_sk_learn}[/dim] "
        f"[dim](soonai skills learning)[/dim]",
                        title="SoonAI status", border_style="cyan"))
    for name, url in (("ollama", "http://localhost:11434/api/tags"),
                      ("lmstudio", "http://localhost:1234/v1/models")):
        try:
            ok = requests.get(url, timeout=2).status_code == 200
        except Exception:
            ok = False
        console.print(f"local {name}: {'[green]ONLINE[/green]' if ok else '[red]offline[/red]'}")


def _ask_seconds(label, default, lo, hi):
    """ถามค่าวินาทีใน setup: Enter/ค่าเดิม = คงไว้ · ผิดรูป/นอกช่วง = ไม่แก้ (คืน None)"""
    try:
        raw = Prompt.ask(f"{label} (วินาที, Enter = คง {default})",
                         default=str(default)).strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    if not raw or raw == str(default):
        return None
    try:
        v = int(float(raw))
    except ValueError:
        console.print(f"[yellow]'{raw}' ไม่ใช่ตัวเลข — คงค่าเดิม {default}[/yellow]")
        return None
    if v < lo or v > hi:
        console.print(f"[yellow]ต้องอยู่ระหว่าง {lo}–{hi} วินาที — คงค่าเดิม {default}[/yellow]")
        return None
    return v


def setup_timeouts(cfg):
    """หน้าตั้งค่า timeout ใน `soonai setup` — ปรับได้เองไม่ต้องแก้ config.json
    บันทึกลง config แล้ว (มีผลทุกค่าย/ทุกโมเดล) · คืน True ถ้ามีการเปลี่ยนค่า"""
    conn, ns = _chat_timeout(False)          # ค่าที่ใช้อยู่ตอนนี้
    st = _chat_timeout(True)[1]
    console.print(Panel(
        "นานเกินไป = คำตอบยาว/โมเดล thinking โดนตัดกลางทาง · "
        "สั้นเกินไป = ค่ายตอบช้าหน่อยระบบสลับทิ้ง\n"
        f"ตอนนี้: เชื่อมต่อ {conn}s · สตรีม {st}s (เว้นช่วงระหว่าง chunk) · "
        f"ไม่สตรีม {ns}s (รอทั้งคำตอบ)",
        title="Timeout", border_style="cyan"))
    try:
        want = Prompt.ask("ปรับ timeout ไหม?", choices=["y", "n"], default="n")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    if want != "y":
        return False
    changed = {}
    v = _ask_seconds("เชื่อมต่อ (connect)", conn, 5, 120)
    if v is not None:
        changed["connect_timeout"] = v
    v = _ask_seconds("สตรีม — เว้นช่วงนานสุดระหว่าง chunk", st, 30, 600)
    if v is not None:
        changed["chat_timeout_stream"] = v
    v = _ask_seconds("ไม่สตรีม — รอทั้งคำตอบนานสุด", ns, 30, 900)
    if v is not None:
        changed["chat_timeout"] = v
    if not changed:
        console.print("[dim]คงค่า timeout เดิมไว้[/dim]")
        return False
    cfg.update(changed)
    save_json(CONFIG_FILE, cfg)
    for k in ("connect_timeout", "chat_timeout_stream", "chat_timeout"):
        if k in changed:
            console.print(f"  · {k} = {changed[k]}s")
    console.print("[dim]มีผลกับทุกค่าย/ทุกโมเดลทันทีที่ส่งคำขอครั้งถัดไป[/dim]")
    return True


def cmd_setup(args, keys, cfg):
    console.print(Panel("ตั้งค่า SoonAI ครั้งแรก — เลือกค่าย ใส่ key เลือกโมเดล เสร็จแล้วแชทได้เลย",
                        title="Setup"))
    cmd_providers(args, keys, cfg)
    # เลือกค่าย + หัวข้อ ➕ เพิ่มค่ายเอง (เหมือนเมนู /provider) —
    # fuzzy_pick ใช้ไม่ได้ใน pipe → fallback เป็น Prompt พร้อมคีย์เวิร์ด "add"
    provider = ""
    try:
        while True:
            fp = fuzzy_pick("เลือก provider:",
                            [(p, f"{p} — {s['name']}") for p, s in PROVIDERS.items()
                             if not s.get("tool_only")]
                            + [(ADD_PROVIDER_CHOICE,
                                "➕ เพิ่มค่ายเอง — OpenAI-compatible (URL + API key)")])
            if fp == ADD_PROVIDER_CHOICE:
                provider = add_custom_provider_flow(keys, cfg) or ""
            elif fp:
                provider = fp
            elif fp == "":
                console.print("[yellow]ยกเลิก setup[/yellow]")
                return 1
            else:
                provider = Prompt.ask("เลือก provider (พิมพ์ add = เพิ่มค่ายเอง)",
                                      default=cfg.get("provider", "ollama")).strip()
                if (provider.lower() in ("add", "เพิ่ม", "เพิ่มค่ายเอง", "+")
                        and provider not in PROVIDERS):
                    provider = add_custom_provider_flow(keys, cfg) or ""
            if not provider:
                continue        # ยกเลิก/ไม่ผ่านตอนเพิ่มค่าย → ถามใหม่
            if provider not in PROVIDERS:
                console.print(f"[red]ไม่รู้จัก provider: {provider}[/red]")
                return 1
            break
    except (EOFError, KeyboardInterrupt):
        console.print()
        return 1
    ensure_key(provider, keys)
    free_only = Prompt.ask("กรองเฉพาะโมเดลฟรี?", choices=["y", "n"], default="y") == "y"
    search = Prompt.ask("ค้นหาโมเดล (Enter = ทั้งหมด)", default="").strip()
    model = pick_model(provider, keys, free_only=free_only, search=search, refresh=True)
    if not model:
        return 1
    cfg["provider"] = provider
    cfg["model"] = model
    save_json(CONFIG_FILE, cfg)
    try:
        setup_timeouts(cfg)
    except (EOFError, KeyboardInterrupt):
        console.print()
    except Exception:
        pass
    # ติดตั้ง skill ชุดแนะนําให้เลย (ไม่ต้องไปหาที่โหลดเอง)
    try:
        if not scan_skills():
            try:
                _want = Prompt.ask("ติดตั้งชุด skill แนะนําให้เลยไหม? (ใช้ได้ทันที ไม่ต้องโหลดอะไร)",
                                   choices=["y", "n"], default="y")
            except (EOFError, KeyboardInterrupt):
                console.print()
                _want = "n"
            if _want == "y":
                _n, _msg = install_catalog_all()
                console.print(f"[green]{_msg}[/green]" if _n else f"[dim]{_msg}[/dim]")
    except Exception:
        pass
    console.print(Panel(f"พร้อมแล้ว! คุยได้เลยด้วยคำสั่ง: [bold]soonai[/bold]\n"
                        f"({PROVIDERS[provider]['name']} / {model})", title="Done"))
    return 0


def ensure_model_valid(provider, model, keys):
    """กันคู่ค่าย/โมเดลผิดก่อนส่งจริง (ต้นเหตุ error 400 invalid model)
    คืนโมเดลที่จะใช้ (อาจเป็นตัวที่เลือกใหม่) / '' = ยกเลิก / ค่าเดิมในโหมด pipe"""
    if not model:
        return ""
    try:
        models, pricing = get_models(provider)
    except Exception:
        return model
    if not models or model in models:
        return model
    import difflib
    sug = difflib.get_close_matches(model, models, n=8, cutoff=0.3)
    extra = ""
    if provider in ("ollama", "lmstudio"):
        extra = f" (ถ้ายังไม่เคยโหลด: soonai pull {model.split(':')[0]})"
    console.print(f"[yellow]'{model}' ไม่อยู่ในรายชื่อของ {PROVIDERS[provider]['name']}{extra}[/yellow]")
    if sug:
        console.print("[dim]ใกล้เคียง: " + ", ".join(sug[:5]) + "[/dim]")
    if not sys.stdin.isatty():
        return model
    items = [("__keep__", f"ใช้ '{model}' ต่อไป (ฉันแน่ใจ)")]
    items += [(m, model_label(m, provider, pricing)) for m in (sug or models[:50])]
    picked = fuzzy_pick("เลือกโมเดลใหม่ (Esc = ยกเลิก):", items)
    if picked is None:
        return model
    if picked == "__keep__":
        return model
    return picked or ""


def resolve_model(provider, model_arg, keys, free_only=False, search=""):
    if model_arg:
        return model_arg
    cfg = load_config()
    if cfg.get("model") and cfg.get("provider") == provider:
        return cfg["model"]
    return pick_model(provider, keys, free_only=free_only, search=search)


def nothing_done_reason(msgs=None):
    """อธิบายว่าทำไม AI ไม่ได้ทำอะไร: แยกปฏิเสธเอง vs โมเดลว่าง"""
    denies = sum(1 for m in msgs or []
                 if m.get("role") == "tool" and "ปฏิเสธ" in str(m.get("content", "")))
    if denies:
        return (f"[yellow](คุณปฏิเสธคำสั่งทั้งหมด {denies} ครั้ง AI เลยไม่ได้ทำอะไร — "
                f"กด `a` เพื่ออนุญาตรวดเดียว หรือสั่งใหม่)[/yellow]")
    return ("[yellow](โมเดลตอบว่าง — ลองสั่งใหม่อีกครั้ง/เปลี่ยนโมเดล "
            f"ถ้าเป็นบ่อยตั้ง SOONAI_DEBUG=1 แล้วลองใหม่ — log อยู่ที่ {_DBG.log_path()})[/yellow]")


class _StdoutToStderr:
    """ชั่วคราว: ย้าย log ของ console ไป stderr เพื่อให้ stdout มีแต่ผลลัพธ์ที่เครื่องอ่านได้"""

    def __enter__(self):
        global console
        self._old = console
        console = Console(file=sys.stderr, no_color=True)
        return console

    def __exit__(self, *exc):
        global console
        console = self._old
        return False


def cmd_exec(args, keys, cfg):
    """โหมด headless สำหรับสคริปต์/CI: รันงานเดียวแล้วจบ
    --json = stdout มี JSON ก้อนเดียว (log ทั้งหมดไป stderr)
    exit code: 0 สำเร็จ · 1 ผิดพลาด · 130 ยกเลิก"""
    global AGENT_MAX_STEPS
    started = time.time()
    want_json = bool(getattr(args, "json", False))
    out_stream = sys.stdout
    provider = args.provider or cfg.get("provider", "ollama")
    result = {"ok": False, "task": args.task, "provider": provider, "model": "",
              "answer": "", "tools": [], "steps": 0,
              "usage": {"calls": 0, "in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0},
              "error": "", "duration_s": 0.0}

    def emit(code):
        result["duration_s"] = round(time.time() - started, 3)
        result["usage"] = {"calls": USAGE["calls"], "in_tokens": USAGE["in"],
                           "out_tokens": USAGE["out"], "cost_usd": round(USAGE["cost"], 6)}
        if want_json:
            try:
                out_stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_stream.flush()
            except Exception:
                pass
        return code

    if provider not in PROVIDERS:
        result["error"] = f"ไม่รู้จัก provider: {provider}"
        console.print(f"[red]{result['error']}[/red]")
        return emit(1)
    if not PROVIDERS[provider].get("no_key") and not get_key(provider, keys):
        result["error"] = f"ค่าย {provider} ยังไม่มี API key (soonai key set {provider} YOUR_KEY)"
        console.print(f"[red]{result['error']}[/red]")
        return emit(1)
    model = resolve_model(provider, getattr(args, "model", "") or "", keys,
                          free_only=getattr(args, "free_only", False),
                          search=getattr(args, "search", "") or "")
    if not model:
        result["error"] = "เลือกโมเดลไม่ได้"
        return emit(1)
    result["model"] = model
    if getattr(args, "max_steps", None) is not None:
        AGENT_MAX_STEPS = args.max_steps
    messages = []
    if cfg.get("system"):
        messages.append({"role": "system", "content": cfg["system"]})
    messages.append({"role": "user", "content": args.task})
    if messages[0].get("role") == "system":
        messages[0] = {"role": "system", "content": messages[0]["content"] + "\n" + AGENT_SYSTEM}
    else:
        messages.insert(0, {"role": "system", "content": AGENT_SYSTEM})
    _env = env_context()
    if _env:
        messages[0] = {"role": "system", "content": messages[0]["content"] + "\n" + _env}
    try:
        snap = project_snapshot()
        if snap:
            messages[0] = {"role": "system", "content": messages[0]["content"] + "\n" + snap}
    except Exception:
        pass
    _attach_project_memory(messages)
    if not want_json:
        console.print(f"[dim]{PROVIDERS[provider]['name']} / {model}[/dim]")
    usage_reset()

    def on_text(t):
        if not want_json:
            console.print(Markdown(t))

    _want_tools = fileop_intent(args.task)
    ctx = _StdoutToStderr() if want_json else None
    try:
        if ctx:
            ctx.__enter__()
        try:
            ans, err, _u, _info = agent_chat(
                provider, model, messages, args.temperature,
                auto_yes=getattr(args, "yes", False) or cfg.get("auto_approve", False),
                expect_tools=_want_tools, force_first=_want_tools, on_text=on_text)
        finally:
            if ctx:
                ctx.__exit__(None, None, None)
    except (TurnCancelled, KeyboardInterrupt):
        result["error"] = "ยกเลิก"
        return emit(130)
    if err:
        result["error"] = str(err)
        console.print(f"[red]{err}[/red]")
        return emit(1)
    if not ans:
        result["error"] = "agent ไม่ได้ทำงานนี้ (ไม่มีผลลัพธ์)"
        return emit(1)
    info = _info or {}
    result["ok"] = True
    result["answer"] = ans
    result["steps"] = info.get("steps", 0)
    result["tools"] = [{"name": n, "status": s, "summary": d}
                       for n, s, d in (info.get("tools") or [])]
    if not want_json:
        _sum = agent_summary_line(_info)
        if _sum:
            console.print(f"[dim]{_sum}[/dim]")
    return emit(0)


def cmd_ask(args, keys, cfg):
    provider = args.provider or cfg.get("provider", "ollama")
    if provider not in PROVIDERS:
        console.print(f"[red]ไม่รู้จัก provider: {provider}[/red]")
        return 1
    if not ensure_key(provider, keys):
        return 1
    if not ensure_local_server(provider):
        return 1
    model = resolve_model(provider, args.model, keys,
                          free_only=args.free_only, search=args.search)
    if not model:
        return 1
    model = ensure_model_valid(provider, model, keys)
    if not model:
        return 1
    messages = []
    if cfg.get("system"):
        messages.append({"role": "system", "content": cfg["system"]})
    messages.append({"role": "user", "content": args.question})
    console.print(f"[dim]{PROVIDERS[provider]['name']} / {model}[/dim]")
    if getattr(args, "boost", False):
        bq = boost_prompt(provider, model, args.question)
        if bq and bq != args.question:
            if sys.stdin.isatty() and _DBG.enabled():
                console.print(f"[dim]พร้อมที่ปรับแล้ว: {bq}[/dim]")
            messages[-1] = {"role": "user", "content": bq}
    if getattr(args, "agent", False):
        if messages and messages[0].get("role") == "system":
            messages[0] = {"role": "system",
                           "content": messages[0]["content"] + "\n" + AGENT_SYSTEM}
        else:
            messages.insert(0, {"role": "system", "content": AGENT_SYSTEM})
        _env = env_context()
        if _env and messages and messages[0].get("role") == "system":
            messages[0] = {"role": "system", "content": messages[0]["content"] + "\n" + _env}
        try:
            snap = project_snapshot()
            if snap and messages and messages[0].get("role") == "system":
                messages[0] = {"role": "system",
                               "content": messages[0]["content"] + "\n" + snap}
        except Exception:
            pass
        _attach_project_memory(messages)
        try:
            ans, err, _u, _info = agent_chat(provider, model, messages, args.temperature,
                                          auto_yes=getattr(args, "yes", False) or cfg.get("auto_approve", False),
                                          expect_tools=fileop_intent(args.question),
                                          force_first=fileop_intent(args.question),
                                          on_text=lambda t: console.print(Markdown(t)))
        except (TurnCancelled, KeyboardInterrupt):
            console.print("[dim](ยกเลิกแล้ว)[/dim]")
            return 130
        if err:
            console.print(f"[red]{err}[/red]")
            return 1
        if not ans:
            console.print(nothing_done_reason(messages))
            return 1
        _sum = agent_summary_line(_info)
        if _sum:
            console.print(f"[dim]{_sum}[/dim]")
        _sw = ((_info or {}).get("model_switch")
               or consume_model_switch(provider, model))
        if _sw:
            cfg["model"] = _sw["to"]
            save_json(CONFIG_FILE, cfg)
            console.print(f"[dim](สลับไป {_sw['to']} ให้อัตโนมัติ)[/dim]")
        return 0
    if not console.is_terminal or args.no_stream:
        try:
            text = send_messages(provider, model, messages, args.temperature, stream=False,
                                 effort=getattr(args, "effort", "") or None)
        except (TurnCancelled, KeyboardInterrupt):
            console.print("[dim](ยกเลิกแล้ว)[/dim]")
            return 130
        except Exception as e:
            console.print(f"[red]ERROR: {e}[/red]")
            return 1
        console.print(Markdown(text) if console.is_terminal else text)
        return 0
    try:
        ans = show_reply(provider, model, messages, args.temperature,
                         effort=getattr(args, "effort", "") or None)
    except (TurnCancelled, KeyboardInterrupt):
        console.print("[dim](ยกเลิกแล้ว)[/dim]")
        return 130
    if ans:
        _sw = consume_model_switch(provider)
        if _sw:
            cfg["model"] = _sw["to"]
            save_json(CONFIG_FILE, cfg)
            console.print(f"[dim](สลับไป {_sw['to']} ให้อัตโนมัติ)[/dim]")
        return 0
    console.print(nothing_done_reason(messages))
    return 1


# ── local server + ถาม key แบบซ่อนจอ + เพิ่มค่ายเอง ────────────────────────
def ensure_local_server(provider):
    """ค่าย local: เช็คว่าเซิร์ฟเวอร์รันอยู่ไหม (Ollama เสนอรันให้, LM Studio บอกวิธี)
    คืน True ถ้าพร้อมคุย"""
    import time as _t
    if provider == "ollama":
        url = "http://localhost:11434/api/tags"
    elif provider == "lmstudio":
        url = "http://localhost:1234/v1/models"
    else:
        return True
    try:
        if requests.get(url, timeout=2).status_code == 200:
            return True
    except Exception:
        pass
    if provider == "lmstudio":
        console.print("[yellow]LM Studio ยังไม่รัน — เปิด LM Studio → โหลดโมเดล → "
                      "กด Start Server (port 1234) แล้วลองใหม่[/yellow]")
        return False
    if sys.stdin.isatty():
        try:
            if Prompt.ask("Ollama ยังไม่รัน เปิดให้เลยไหม?",
                          choices=["y", "n"], default="y") == "y":
                import shutil as _shutil
                if not _shutil.which("ollama"):
                    console.print("[red]ไม่พบคำสั่ง ollama — ติดตั้ง Ollama ก่อน: "
                                  "https://ollama.com/download[/red]")
                    console.print("[dim]หรือรัน `ollama serve` ด้วยตัวเอง[/dim]")
                    return False
                import subprocess
                try:
                    subprocess.Popen(["ollama", "serve"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (FileNotFoundError, OSError):
                    console.print("[red]เปิด Ollama ไม่ได้ — ติดตั้งหรือเพิ่ม ollama ลง PATH ก่อน[/red]")
                    console.print("[dim]https://ollama.com/download[/dim]")
                    return False
                for _ in range(15):
                    _t.sleep(1)
                    try:
                        if requests.get(url, timeout=2).status_code == 200:
                            console.print("[green]Ollama พร้อมแล้ว[/green]")
                            return True
                    except Exception:
                        pass
        except (EOFError, KeyboardInterrupt):
            console.print()
    console.print("[yellow]เปิดโปรแกรม Ollama (หรือรัน `ollama serve`) แล้วลองใหม่[/yellow]")
    return False


def _erase_last_line():
    """ลบบรรทัดปัจจุบันทิ้ง (หลังกรอก secret — ไม่เหลือแม้แต่ **** ให้นับความยาว)"""
    try:
        sys.stdout.write("\x1b[1A\x1b[2K")
        sys.stdout.flush()
    except Exception:
        pass


def _enable_vt():
    """เปิด ANSI บน console Windows (ให้คำสั่งลบบรรทัดใช้ได้)"""
    try:
        if os.name != "nt":
            return
        import ctypes
        _k = ctypes.windll.kernel32
        _h = _k.GetStdHandle(-11)
        _mode = ctypes.c_ulong()
        if _k.GetConsoleMode(_h, ctypes.byref(_mode)):
            _k.SetConsoleMode(_h, _mode.value | 0x0004)
    except Exception:
        pass


def _ask_secret_win(prompt_text):
    """อ่าน secret บน Windows ทีละปุ่ม โชว์ * ทุกตัว กด Enter แล้วลบบรรทัดทิ้ง
    (พิมพ์/วางไม่หลุดขึ้นจอ แถมไม่เหลือร่องรอยให้นับ)"""
    import msvcrt as _ms
    _enable_vt()
    out = sys.stdout
    out.write(str(prompt_text) + " ")
    out.flush()
    buf = []
    while True:
        ch = _ms.getwch()
        if ch in ("\r", "\n"):
            _erase_last_line()
            break
        if ch == "\x03":
            _erase_last_line()
            raise KeyboardInterrupt
        if ch == "\x1a":
            raise EOFError
        if ch == "\x08":
            if buf:
                buf.pop()
                out.write("\b \b")
                out.flush()
            continue
        if ch in ("\x00", "\xe0"):
            try:
                _ms.getwch()  # กลืนครึ่งหลังของปุ่มพิเศษ (ลูกศร/F1-12)
            except Exception:
                pass
            continue
        if ord(ch) < 32:
            continue  # ปุ่มควบคุมอื่นข้าม
        buf.append(ch)
        out.write("*")
        out.flush()
    return "".join(buf).strip()


def _ask_secret(prompt_text):
    """ถาม secret โชว์ * ทุกตัวอักษร (Windows อ่านทีละปุ่ม · ระบบอื่นใช้ getpass · pipe อ่าน stdin ตรง)"""
    if not sys.stdin.isatty():
        return (sys.stdin.readline() or "").strip()
    if os.name == "nt":
        try:
            return _ask_secret_win(prompt_text)
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception:
            pass
    try:
        import getpass as _gp
        out = _gp.getpass(f"{prompt_text} ").strip()
        _erase_last_line()
        return out
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        return Prompt.ask(prompt_text, password=True).strip()


def ensure_key(provider, keys):
    """ถ้าค่ายนี้ยังไม่มี key: เสนอเปิดหน้าขอ key ในเบราว์เซอร์ + ให้วาง key ตรงนี้เลย
    คืน True ถ้าพร้อมใช้ (มี key อยู่แล้ว / ไม่ต้องใช้ key / เพิ่งวางให้)"""
    if PROVIDERS[provider].get("tool_only"):
        console.print(f"[yellow]{PROVIDERS[provider]['name']} ไม่ใช่ค่ายแชท (ไม่มี endpoint "
                      "คุยโมเดล) — เป็น web tools ของ agent (web_search/web_fetch · "
                      "soonai mcp install tinyfish)[/yellow]")
        return False
    if PROVIDERS[provider].get("no_key") or get_key(provider, keys):
        return True
    cfg = PROVIDERS[provider]
    console.print(f"[yellow]ค่าย {cfg['name']} ต้องใช้ API key[/yellow]")
    console.print(f"ขอ key ฟรีได้ที่: {cfg.get('key_url', '')}")
    if provider == "puter":
        console.print("[dim]หมายเหตุ: บัญชีฟรีของ Puter ใช้ API/CLI ไม่ได้ "
                      "ต้องมี subscription[/dim]")
    try:
        if sys.stdin.isatty() and Prompt.ask(
                "เปิดหน้าเว็บขอ key ในเบราว์เซอร์ไหม?",
                choices=["y", "n"], default="y") == "y":
            import webbrowser
            webbrowser.open(cfg.get("key_url", ""))
        if not sys.stdin.isatty():
            console.print("[dim]โหมด pipe — ใส่ key ด้วย: "
                          f"soonai key set {provider} YOUR_KEY[/dim]")
            return False
        key = _ask_secret(f"วาง API key ของ {provider}:").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    if key:
        keys[provider] = key
        save_keys(keys)
        console.print("[green]บันทึก key แล้ว[/green]")
        return True
    console.print("[dim]ข้ามไปก่อน — ใส่ทีหลังด้วย: "
                  f"soonai key set {provider} YOUR_KEY[/dim]")
    return False


ADD_PROVIDER_CHOICE = "__add_custom_provider__"


def add_custom_provider_flow(keys, cfg, url_prefill=""):
    """เพิ่มค่ายเอง (OpenAI-compatible) ระหว่างเมนูเปลี่ยนค่าย
    ถาม ชื่อ/URL/โมเดล → cmd_provider add (ถาม key แบบซ่อนจอเองเมื่อเป็น tty)
    url_prefill = ใส่ค่าล่วงหน้าในช่อง URL (เช่น /connect <URL>)
    คืน pid ใหม่ถ้าสำเร็จ / None ถ้ายกเลิกหรือไม่ผ่านตรวจสอบ"""
    try:
        name = Prompt.ask("ชื่อค่ายใหม่ (a-z, 0-9, _, -)", default="").strip().lower()
        url = Prompt.ask("Base URL (เช่น https://api.example.com/v1)", default=url_prefill).strip()
        model = Prompt.ask("โมเดลเริ่มต้น", default="").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    ns = argparse.Namespace(action="add", name=name, url=url, model=model,
                            display_name="", models_url="", api_key=None,
                            key_env="", header=[])
    try:
        rc = cmd_provider(ns, keys, cfg)
    except Exception as e:
        console.print(f"[red]เพิ่มค่ายไม่สำเร็จ: {e}[/red]")
        return None
    return name if rc == 0 else None


# ── เปลี่ยน/เชื่อมต่อค่าย: switch_provider + /connect ───────────────────────
def switch_provider(keys, cfg):
    """ให้ผู้ใช้เลือกค่ายใหม่ + โมเดล (เหมือน dropdown บนเว็บ) คืน (provider, model) หรือ None
    มีหัวข้อ ➕ เพิ่มค่ายเอง — เพิ่มเสร็จ = เลือกค่ายนั้นต่อทันที (กด Esc ยกเลิก = วนดูเมนูใหม่)"""
    pid = ""
    while not pid:
        cmd_providers(argparse.Namespace(), keys, cfg)
        fp = fuzzy_pick("Select provider:",
                        [(p, f"{p} — {spec['name']}") for p, spec in PROVIDERS.items()
                         if not spec.get("tool_only")]
                        + [(ADD_PROVIDER_CHOICE,
                            "➕ เพิ่มค่ายเอง — OpenAI-compatible (URL + API key)")])
        if fp == ADD_PROVIDER_CHOICE:
            pid = add_custom_provider_flow(keys, cfg) or ""
            continue
        if fp:
            pid = fp
        elif fp == "":
            return None
        else:
            pid = Prompt.ask("เลือกค่าย (provider id)", default=cfg.get("provider", "ollama")).strip()
        if pid and pid not in PROVIDERS:
            console.print(f"[red]ไม่รู้จัก provider: {pid}[/red]")
            return None
    if not ensure_key(pid, keys):
        return None
    if not ensure_local_server(pid):
        return None
    model = pick_model(pid, keys)
    if not model:
        return None
    cfg["provider"] = pid
    cfg["model"] = model
    save_json(CONFIG_FILE, cfg)
    return pid, model


def _connect_ping(pid, model):
    """ยิง chat สั้น ๆ 1 ครั้งตรงถึงค่าย (ไม่ผ่าน failover/retry — ผลต้องจริงของค่ายนั้น)
    คืน (True, คำตอบสั้น) หรือ (False, ข้อความ error ที่อ่านออก)"""
    try:
        driver = _make_chat_driver(
            pid, model, [{"role": "user", "content": "พิมพ์คำว่า ok"}],
            0.0, False, _chat_effort(pid, None), 16, 0)
        url, headers, payload = driver.spec()
        r = driver.send(url, headers, payload)
        status = getattr(r, "status_code", 0)
        if status != 200:
            return False, driver.error_message(status, driver.error_body(r))
        text, _finish = driver.read(r, lambda t: None)
        return True, (text or "").strip().replace("\n", " ")[:80]
    except Exception as e:
        return False, str(e)


def connect_provider(keys, cfg, target=""):
    """/connect — เชื่อมต่อค่าย AI: เลือก/เพิ่มค่าย → key → โมเดล → ทดสอบยิงจริง 1 รอบ
    เชื่อมผ่าน = ตั้งเป็นค่ายหลัก · ไม่ผ่าน = คืนค่าเดิม (ไม่ทิ้งค่ายพังไว้)
    target: ว่าง = เมนู (มี ➕ เพิ่มค่ายเอง) · ชื่อค่าย · http(s) URL = เพิ่มค่ายจาก URL
    คืน (provider, model) ถ้าสำเร็จ / None"""
    target = str(target or "").strip()
    prev_p, prev_m = cfg.get("provider"), cfg.get("model")
    picked = None
    if target.startswith(("http://", "https://")):
        pid = add_custom_provider_flow(keys, cfg, url_prefill=target)
        if not pid:
            return None
        model = pick_model(pid, keys)
        if not model:
            return None
        picked = (pid, model)
    elif target:
        pid = target.lower()
        if pid not in PROVIDERS:
            console.print(f"[red]ไม่รู้จักค่าย: {pid}[/red] — พิมพ์ /connect เฉย ๆ "
                          "เพื่อเลือกจากเมนู (มี ➕ เพิ่มค่ายเอง)")
            return None
        if not ensure_key(pid, keys):
            return None
        model = pick_model(pid, keys)
        if not model:
            return None
        picked = (pid, model)
    else:
        picked = switch_provider(keys, cfg)  # เมนู + ➕เพิ่มค่ายเอง + key + โมเดล + บันทึกแล้ว
        if not picked:
            return None
    pid, model = picked
    with console.status(f"กำลังทดสอบการเชื่อมต่อ {pid}/{model} …"):
        ok, info = _connect_ping(pid, model)
    if not ok:
        console.print(f"[red]เชื่อมไม่ผ่าน:[/red] {info}")
        if cfg.get("provider") != prev_p or cfg.get("model") != prev_m:
            cfg["provider"], cfg["model"] = prev_p, prev_m
            save_json(CONFIG_FILE, cfg)
        console.print("[dim]ยังไม่ตั้งเป็นค่ายหลัก — แก้ key แล้วลอง /connect ใหม่[/dim]")
        return None
    cfg["provider"], cfg["model"] = pid, model
    save_json(CONFIG_FILE, cfg)
    console.print(f"[green]เชื่อมต่อสำเร็จ ✓ {PROVIDERS[pid]['name']} / {model}[/green]"
                  + (f"[dim] — ตอบ: {info}[/dim]" if info else ""))
    return pid, model


# สถานะเปิด/ปิดอนิเมชันจักรวาล (ตัวคำนวณ/เรนเดอร์ย้ายไป shared/ui_render.py แล้ว)
_COSMOS_MODE = {"on": None}


UPDATE_CHECK_TTL = 24 * 3600
_UPDATE_SCHEME_WARNED = {"shown": False}


# ── self-update: ตรวจ/ติดตั้งเวอร์ชันใหม่ + restart ──────────────────────────
def _parse_version(v):
    parts = []
    for x in str(v or "").strip().lstrip("vV").split("."):
        try:
            parts.append(int(x))
        except Exception:
            parts.append(0)
    return tuple((parts + [0, 0, 0])[:3])


def fetch_latest_meta(url, timeout=5):
    """ดึง {version, notes, url} จาก update_url (None ถ้าไม่ได้/ล้มเหลว)"""
    if not (url or "").strip():
        return None
    try:
        r = requests.get(url.strip(), timeout=timeout)
        if r.status_code != 200:
            return None
        d = r.json()
        if not isinstance(d, dict) or not d.get("version"):
            return None
        return {"version": str(d["version"]), "notes": str(d.get("notes", "")),
                "url": str(d.get("url", ""))}
    except Exception:
        return None


def check_update(cfg, force=False):
    """คืน meta ถ้ามีเวอร์ชันใหม่กว่า (เช็คไม่เกินวันละครั้ง ยกเว้น force)"""
    import time as _t
    url = (cfg.get("update_url") or "").strip()
    if not url:
        return None
    if not url.lower().startswith("https://"):
        # metadata อัปเดตคือขาเชื่อถือได้จากภายนอก — บังคับ https เท่านั้น
        if not _UPDATE_SCHEME_WARNED["shown"]:
            _UPDATE_SCHEME_WARNED["shown"] = True
            console.print("[yellow]update_url ต้องเป็น https:// เท่านั้น — "
                          "ข้ามการเช็คอัปเดตอัตโนมัติ[/yellow]")
        return None
    now = _t.time()
    try:
        last = float(cfg.get("last_update_check", 0) or 0)
    except Exception:
        last = 0
    if not force and now - last < UPDATE_CHECK_TTL:
        return None
    cfg["last_update_check"] = now
    try:
        save_json(CONFIG_FILE, cfg)
    except Exception as e:
        _DBG.log_swallowed(e, "soonai.py:check_update",
                           "จำเวลาเช็คอัปเดตล่าสุดไม่ได้ — จะยิงเช็คซ้ำทุกครั้งที่เปิดโปรแกรม")
    meta = fetch_latest_meta(url)
    if not meta:
        return None
    if _parse_version(meta["version"]) <= _parse_version(VERSION):
        return None
    if meta["version"] == (cfg.get("skipped_version") or "") and not force:
        return None
    return meta


def do_update(cfg, meta):
    """อัปเดตผ่าน git pull ถ้ามี remote ไม่งั้นบอกวิธีทำมือ"""
    import subprocess
    try:
        rem = subprocess.run(["git", "-C", str(BASE_DIR), "remote"],
                             capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        console.print("[yellow]เครื่องนี้ไม่มี git — อัปเดตมือตามลิงก์นี้: "
                      f"{meta.get('url') or 'ติดต่อผู้ดูแล'}[/yellow]")
        return False
    except Exception as e:
        console.print(f"[red]ตรวจ git ไม่ได้: {e}[/red]")
        return False
    if rem.returncode != 0 or not rem.stdout.strip():
        console.print("[yellow]ยังไม่ผูก remote — push โปรเจกต์ขึ้น GitHub ก่อน "
                      "แล้วรันคำสั่งนี้ใหม่[/yellow]")
        if meta.get("url"):
            console.print(f"[dim]ดาวน์โหลด/ดูรายละเอียด: {meta['url']}[/dim]")
        return False
    console.print(f"[dim]ดึงจาก remote: {rem.stdout.strip().replace(chr(10), ', ')}[/dim]")
    try:
        # กันงานที่ยังไม่ commit หาย — pull อัตโนมัติเฉพาะ working tree สะอาด
        st = subprocess.run(["git", "-C", str(BASE_DIR), "status", "--porcelain"],
                            capture_output=True, text=True, timeout=15)
        if st.returncode == 0 and (st.stdout or "").strip():
            console.print("[yellow]มีไฟล์ที่แก้/ยังไม่ commit — ยกเลิกอัปเดตอัตโนมัติ "
                          "(commit หรือ stash ก่อน แล้วรัน soonai update ใหม่)[/yellow]")
            return False
    except Exception as e:
        # ตรวจ working tree ไม่ได้ = ไปต่อ (พฤติกรรมเดิม) แต่ต้องมีร่องรอยว่าทำไม
        _DBG.log_swallowed(e, "soonai.py:do_update",
                           "ตรวจ working tree ก่อน pull ไม่ได้ — ไปต่อ (งานที่ยังไม่ commit อาจถูกทับ)")
    try:
        r = subprocess.run(["git", "-C", str(BASE_DIR), "pull", "--ff-only"],
                           capture_output=True, text=True, timeout=120)
    except Exception as e:
        console.print(f"[red]pull ไม่ได้: {e}[/red]")
        return False
    if r.returncode == 0:
        if "already up to date" in (r.stdout or "").lower():
            console.print("[green]เป็นเวอร์ชันล่าสุดอยู่แล้ว[/green]")
            return True
        console.print(f"[green]อัปเดตเป็น {meta['version']} แล้ว — กำลังรีสตาร์ท…[/green]")
        restart_program()
        return True
    console.print(f"[yellow]pull ไม่สำเร็จ (อาจมีแก้ไฟล์ค้าง):\n{(r.stderr or '')[:400]}[/yellow]")
    return False


def restart_program():
    """รีสตาร์ทตัวเองด้วยเวอร์ชันใหม่ (ใช้หลังอัปเดตสำเร็จ)"""
    import os
    script = str(BASE_DIR / "soonai.py")
    args = [sys.executable, script] + sys.argv[1:]
    try:
        console.print("[dim]รีสตาร์ท…[/dim]")
        os.execv(sys.executable, args)
    except Exception as e:
        console.print(f"[yellow]รีสตาร์ทเองไม่ได้ ({e}) — ปิดแล้วเปิด `soonai` ใหม่[/yellow]")


def update_popup(cfg, meta):
    """ป็อปอัพแจ้งเวอร์ชันใหม่ คืน True ถ้าอัปเดตแล้ว"""
    notes = (meta.get("notes") or "")[:500] or "—"
    console.print(Panel(f"[bold]มี SoonAI เวอร์ชันใหม่: {VERSION} → {meta['version']}[/bold]\n{notes}",
                        title="🎉 อัปเดต", border_style="green"))
    console.print("[dim]u = อัปเดตเลย · s = ข้ามเวอร์ชันนี้ · l = เตือนทีหลัง[/dim]")
    try:
        ans = Prompt.ask("เลือก", choices=["u", "s", "l"], default="l")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    if ans == "s":
        cfg["skipped_version"] = meta["version"]
        try:
            save_json(CONFIG_FILE, cfg)
        except Exception:
            pass
        return False
    if ans != "u":
        return False
    return do_update(cfg, meta)


def cmd_update(args, keys, cfg):
    meta = check_update(cfg, force=True)
    if not meta:
        console.print(f"[green]เป็นเวอร์ชันล่าสุดแล้ว (v{VERSION})[/green]")
        return 0
    if not sys.stdin.isatty():
        console.print(f"[yellow]มีเวอร์ชันใหม่: {meta['version']} — {meta.get('notes', '')[:200]}[/yellow]")
        return 0
    update_popup(cfg, meta)
    return 0


MAX_PIN_BLANKS = 8


# ── pin input + ทีม/พนักงาน: รันงานขนาน + merge ผล ────────────────────────
def paint_pinned_input(provider=None, model=None, agent=False, auto_yes=False, effort="", file=None):
    """ดันบาร์ลงล่างแบบพอดี (ไม่ยืดเกิน)
    ไม่พิมพ์สถานะที่นี่ — สถานะอยู่ในขอบบนของกรอบพิมพ์แล้ว (box_title) พิมพ์ซ้ำจะเบิ้ล 2 บรรทัด
    ไม่วาดบทสนทนาซ้ำ (ของที่พิมพ์ไปแล้วอยู่ใน scrollback ครบ)"""
    if file is None:
        if not sys.stdin.isatty():
            return
        f = sys.stdout
    else:
        f = file
    try:
        import shutil
        size = shutil.get_terminal_size((80, 24))
        H = max(12, size.lines)
    except Exception:
        return
    try:
        blanks = min(max(0, (H - 2) - 1), MAX_PIN_BLANKS)
        f.write("\n" * (blanks + 1))
        f.flush()
    except Exception:
        pass


def _handle_staff_error(team, s, err, keys, cfg):
    """จัดการ err ของงานลูกน้อง (ย้าย/สลับโมเดล + บันทึกทีม) คืนข้อความบอกต่อหรือ ''"""
    try:
        _migrated = maybe_migrate_model(s.get("provider"), s.get("model"), err, keys, cfg)
    except Exception:
        _migrated = None
    if _migrated:
        s["model"] = _migrated
        try:
            with _TEAM_LOCK:
                save_team(team)
        except Exception:
            pass
        return f"อัปเดตโมเดลของ {s.get('name')} เป็น {_migrated} แล้ว"
    if "429" in (err or ""):
        try:
            _rot = offer_rotation(s.get("provider"), s.get("model"), keys, cfg)
        except Exception:
            _rot = None
        if _rot:
            s["model"] = _rot
            try:
                with _TEAM_LOCK:
                    save_team(team)
            except Exception:
                pass
            return f"สลับโมเดลของ {s.get('name')} เป็น {_rot} แล้ว"
    return ""


def _run_single_staff(s, task, keys, cfg, temperature, auto_yes, on_text=None):
    """สั่งงานลูกน้อง 1 คน (ไม่พิมพ์เอง) คืน dict ผลลัพธ์ไว้รวมผลทีม"""
    base = {"staff": s, "name": s.get("name", "?"), "provider": s.get("provider", ""),
            "model": s.get("model", ""), "ans": "", "err": "",
            "tools": [], "summary": "", "msgs": []}
    try:
        if not ensure_key(s["provider"], keys):
            base["err"] = "ไม่มี API key"
            return base
        if not ensure_local_server(s["provider"]):
            base["err"] = "local server ไม่พร้อม"
            return base
    except Exception as e:
        base["err"] = str(e)
        return base
    sys_text = staff_system(s)
    try:
        _env = env_context()
        if _env:
            sys_text += "\n" + _env
    except Exception:
        pass
    try:
        snap = project_snapshot()
        if snap:
            sys_text += "\n" + snap
    except Exception:
        pass
    msgs = [{"role": "system", "content": sys_text},
            {"role": "user",
             "content": task + f"\n\n[ย้ำบทบาท: คุณคือ {s.get('name', '?')} "
                               f"ตำแหน่ง {s.get('role', '') or 'ผู้ช่วยทั่วไป'} — ทำเฉพาะงานในบทบาทนี้]"}]
    _attach_project_memory(msgs)
    base["msgs"] = msgs
    try:
        ans, err, _u, info = agent_chat(s["provider"], s["model"], msgs, temperature,
                                        auto_yes=auto_yes, expect_tools=True,
                                        force_first=True, on_text=on_text)
    except Exception as e:
        base["err"] = str(e)
        return base
    base["ans"] = ans or ""
    base["err"] = err or ""
    try:
        _msw = (info or {}).get("model_switch") or {}
        if _msw.get("to"):
            if _msw.get("from_provider"):
                base["provider"] = _msw.get("provider", base["provider"])
            base["model"] = _msw["to"]
    except Exception:
        pass
    try:
        base["tools"] = list((info or {}).get("tools", []))
        base["summary"] = agent_summary_line(info or {}) or ""
    except Exception:
        pass
    return base


def run_staff_tasks(staff_list, task, keys, cfg, temperature, auto_yes,
                    on_text=None, max_workers=5):
    """รันงานพร้อมกันหลายคน (ThreadPool) คืนลิสต์ผลตามลำดับที่ส่งมา"""
    from concurrent.futures import ThreadPoolExecutor
    staff_list = list(staff_list or [])
    if not staff_list:
        return []
    results = [None] * len(staff_list)

    def _one(i, s):
        _STAFF_CTX.name = s.get("name", "")
        try:
            results[i] = _run_single_staff(s, task, keys, cfg, temperature,
                                           auto_yes, on_text)
        except Exception as e:
            results[i] = {"staff": s, "name": s.get("name", "?"),
                          "provider": s.get("provider", ""),
                          "model": s.get("model", ""), "ans": "", "err": str(e),
                          "tools": [], "summary": "", "msgs": []}
        finally:
            _STAFF_CTX.name = ""

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(staff_list)))) as ex:
        list(ex.map(lambda t: _one(t[0], t[1]), enumerate(staff_list)))
    return results


def parse_tellall_targets(team, rest):
    """แยก /tellall [@a,@b] <งาน> คืน (รายชื่อลูกน้อง, งาน)"""
    team = list(team or [])
    task = (rest or "").strip()
    if not task.startswith("@"):
        return team, task
    refpart, _, taskpart = task.partition(" ")
    refs = [x.strip().lstrip("@").strip() for x in refpart.split(",")]
    picked, seen = [], set()
    for r in refs:
        if not r:
            continue
        s = resolve_staff(team, r)
        if s is not None and id(s) not in seen:
            seen.add(id(s))
            picked.append(s)
    return picked, taskpart.strip()


def format_team_merge(results):
    """ตารางสรุปผลทีม (Auto-merge view)"""
    table = neo_table(title=f"สรุปงานทีม ({len(results or [])} คน)")
    table.add_column("ลูกน้อง", style="cyan")
    table.add_column("บทบาท", style="white")
    table.add_column("ค่าย/โมเดล", style="white")
    table.add_column("tools", justify="right")
    table.add_column("สถานะ")
    table.add_column("สรุป", style="dim")
    for r in results or []:
        ans, err = r.get("ans") or "", r.get("err") or ""
        if err:
            status, summ = "[red]ล้มเหลว[/]", err[:70]
        elif not ans:
            status, summ = "[yellow]ไม่มีงานออก[/]", "-"
        else:
            status = "[green]เสร็จ[/]"
            raw = (r.get("summary") or ans).strip()
            summ = raw.splitlines()[0][:80] if raw else "-"
        table.add_row(r.get("name", "?"),
                      str(((r.get("staff") or {}).get("role", "")) or "-")[:30],
                      f"{r.get('provider', '')} / {(r.get('model', '') or '')[:28]}",
                      str(len(r.get("tools", []))), status, summ)
    return table


# ── ลูปห้องแชท + ตัวจัดการคำสั่ง "/" ย้ายไป shared/chat.py (Step 5) ──


def cmd_demo(args):
    """โชว์กรอบจักรวาลอนิเมชันอย่างเดียว (ไม่ใช้เน็ต ไม่ใช้ key)
    พิมพ์อะไรก็ได้แล้ว Enter — โชว์ข้อความที่พิมพ์แล้วจบ (Ctrl+C ออก)"""
    from prompt_toolkit.application import Application
    from prompt_toolkit.styles import Style

    if not sys.stdin.isatty():
        console.print("[yellow]demo ต้องรันใน terminal จริง (ไม่ใช่ pipe)[/yellow]")
        return 1
    cfg = load_config()
    status = box_title(cfg.get("provider", "openrouter"),
                       cfg.get("model", "") or "demo-model",
                       effort=cfg.get("effort", ""))
    layout, buf, kb = build_input_bar(None, status)
    app = Application(layout=layout, key_bindings=kb,
                      style=Style.from_dict(INPUT_STYLE),
                      full_screen=False, erase_when_done=True)
    console.print("[dim]กรอบจักรวาลเดโม — พิมพ์แล้วกด Enter (Ctrl+C ออก)[/dim]")
    try:
        out = app.run()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return 0
    console.print(f"[dim]คุณพิมพ์: {(out or '').strip()}[/dim]")
    return 0


# ── คำสั่ง git ย่อย: git/commit/undo/test ───────────────────────────────────
def cmd_git(args, keys, cfg):
    """แสดงสถานะ git (status/diff/branch/log)"""
    if not git_in_repo():
        console.print("[yellow]โฟลเดอร์นี้ไม่ใช่ git repo[/yellow]")
        return 1
    action = getattr(args, "git_action", "status")
    if action == "status" or action is None:
        code, out = _git_run(["status", "--short"])
        changes = git_changes()
        if changes:
            table = neo_table(title=f"Git status — สาขา {git_branch() or '?'}",
                              show_lines=False)
            table.add_column("สถานะ", justify="center")
            table.add_column("ไฟล์")
            for st, p in changes[:50]:
                table.add_row(st, p)
            console.print(table)
            console.print(f"[dim]{len(changes)} ไฟล์เปลี่ยน · [bold]{len([p for s,p in changes if s=='??'])} untracked[/dim]")
        else:
            console.print("[green]Working tree สะอาด[/green]")
        return 0
    if action == "diff":
        code, out = _git_run(["diff", "--stat"])
        console.print(out or "(ไม่มี diff)")
        return 0
    if action == "log":
        code, out = _git_run(["log", "--oneline", "-10"])
        console.print(out or "(ไม่มี log)")
        return 0
    if action == "branch":
        branches, _ = _git_run(["branch", "--list"])
        cur = git_branch()
        console.print(f"[bold]สาขาปัจจุบัน:[/bold] {cur}")
        console.print("[dim]สาขาทั้งหมด:[/dim]")
        for line in branches.splitlines():
            marker = "[green]*[/]" if cur in line else " "
            console.print(f"  {marker} {line.strip()}")
        return 0
    return 0


def cmd_commit(args, keys, cfg):
    """ร่างข้อความ commit จาก diff แล้ว commit (ไม่ push)"""
    ok = git_commit_flow(
        args.provider or cfg.get("provider", ""),
        args.model or cfg.get("model", ""),
        auto_yes=args.yes
    )
    return 0 if ok else 1


def cmd_undo(args, keys, cfg):
    """ย้อนกลับ commit ล่าสุด + คืนสถานะจาก checkpoint"""
    if not git_in_repo():
        console.print("[yellow]ไม่ใช่ git repo[/yellow]")
        return 1
    code, out = _git_run(["log", "--oneline", "-1"])
    if code != 0:
        console.print("[yellow]ไม่มี commit ให้ย้อนกลับ[/yellow]")
        return 1
    last_commit = out.splitlines()[0] if out else "unknown"
    console.print(f"[yellow]ย้อนกลับ commit: {last_commit}[/yellow]")
    code, out = _git_run(["reset", "--soft", "HEAD~1"])
    if code != 0:
        console.print(f"[red]ย้อนกลับไม่สำเร็จ: {out}[/red]")
        return 1
    # พยายามคืนจาก checkpoint ถ้ามี
    try:
        records = checkpoint_records()
        if records:
            latest = records[0]
            console.print(f"[dim]พบ checkpoint ล่าสุด: {latest.get('timestamp', '?')}[/dim]")
            console.print("[dim]ใช้ soonai checkpoint restore เพื่อคืนไฟล์[/dim]")
    except Exception:
        pass
    console.print("[green]ย้อนกลับสำเร็จ — ไฟล์กลับไปอยู่ก่อน commit[/green]")
    return 0


def cmd_test(args, keys, cfg):
    """รันเทสต์อัตโนมัติ (pytest) แสดงผลลัพธ์"""
    import subprocess
    import time
    test_dir = args.path or "."
    console.print(f"[cyan]กำลังรันเทสต์ใน {test_dir}…[/cyan]")
    t0 = time.time()
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", test_dir, "-q", "--tb=short"],
            capture_output=False, timeout=300, encoding="utf-8"
        )
    except subprocess.TimeoutExpired:
        console.print("[red]เทสต์ใช้เวลาเกิน 5 นาที[/red]")
        return 1
    except FileNotFoundError:
        console.print("[yellow]ไม่พบ pytest — ติดตั้ง: pip install -r requirements-dev.txt[/yellow]")
        return 1
    elapsed = time.time() - t0
    passed = result.returncode == 0
    status = "[green]✅ ผ่าน[/green]" if passed else "[red]❌ ล้มเหลว[/red]"
    console.print(f"[dim]เสร็จใน {elapsed:.1f}s {status}[/dim]")
    return 0 if passed else 1


# ── argparse + main() ────────────────────────────────────────────────────────
def build_parser():
    ap = argparse.ArgumentParser(prog="soonai", description="SoonAI CLI — แชทบอททุกค่ายจาก cmd/PowerShell")
    ap.add_argument("--version", action="version", version=f"soonai {VERSION}")
    # flag ห้องแชท (ใช้กับ soonai เฉย ๆ ไม่มีคำสั่งย่อย)
    ap.add_argument("--provider", help="ค่าย AI สำหรับห้องแชท")
    ap.add_argument("--model", help="โมเดลสำหรับห้องแชท")
    ap.add_argument("--temperature", type=float, default=None,
                    help="อุณหภูมิคำตอบ (ว่าง = ตาม config)")
    ap.add_argument("--free-only", action="store_true", help="ห้องแชทใช้เฉพาะโมเดลฟรี")
    ap.add_argument("--search", default="", help="ค้นชื่อโมเดลห้องแชท")
    ap.add_argument("--agent", action="store_true", help="เปิดโหมดสั่งงานเครื่องตั้งแต่เริ่ม")
    ap.add_argument("--yes", action="store_true", help="อนุญาตทุก action โดยไม่ถาม (ระวัง)")
    ap.add_argument("--no-boot", action="store_true", help="ข้ามจอต้อนรับ")
    ap.add_argument("--no-banner", action="store_true", help="ซ่อนโลโก้ SOONAI ด้านบน")
    ap.add_argument("--effort", choices=["low", "medium", "high"], default="",
                    help="โหมด reasoning ห้องแชท (เฉพาะค่ายที่รองรับ)")
    ap.add_argument("--resume", nargs="?", const="last", default=None,
                    help="คุยต่อ session เดิม (ลำดับ/id/ว่าง=ล่าสุด)")
    ap.add_argument("--max-steps", type=int, default=None,
                    help="เพดานก้าวของ agent (0 = ไม่จำกัด · ค่าเริ่มต้น 40)")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("setup", help="ตัวช่วยตั้งค่าครั้งแรก (แนะนำ)")

    p = sub.add_parser("ask", help="ถามครั้งเดียวแล้วจบ")
    p.add_argument("question")
    p.add_argument("--provider")
    p.add_argument("--model")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--no-stream", action="store_true")
    p.add_argument("--free-only", action="store_true")
    p.add_argument("--search", default="")
    p.add_argument("--agent", action="store_true", help="ให้สั่งงานเครื่องได้")
    p.add_argument("--yes", action="store_true", help="อนุญาตทุก action โดยไม่ถาม (ระวัง)")
    p.add_argument("--effort", choices=["low", "medium", "high"], default="",
                   help="โหมด reasoning (เฉพาะค่ายที่รองรับ)")
    p.add_argument("--boost", action="store_true", help="เกลาพร้อมก่อนส่ง")
    p.add_argument("--max-steps", type=int, default=None,
                   help="เพดานก้าวของ agent (0 = ไม่จำกัด · ค่าเริ่มต้น 40)")

    p = sub.add_parser("exec", help="โหมด headless สำหรับสคริปต์/CI (ทำงานเดียวแล้วจบ)")
    p.add_argument("task", help="งานที่ให้ทำ (เช่น 'รันเทสต์แล้วแก้ให้ผ่าน')")
    p.add_argument("--json", action="store_true", help="stdout เป็น JSON ก้อนเดียว (log ไป stderr)")
    p.add_argument("--provider")
    p.add_argument("--model")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--free-only", action="store_true")
    p.add_argument("--search", default="")
    p.add_argument("--yes", action="store_true", help="อนุญาตทุก action โดยไม่ถาม (ระวัง)")
    p.add_argument("--max-steps", type=int, default=None,
                   help="เพดานก้าวของ agent (0 = ไม่จำกัด · ค่าเริ่มต้น 40)")

    sub.add_parser("providers", help="ดูรายชื่อผู้ให้บริการ")

    p = sub.add_parser("provider", help="เพิ่ม/ลบ provider แบบ OpenAI-compatible ด้วย URL + API key")
    p.add_argument("action", choices=["add", "rm", "list", "ls"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("url", nargs="?", default="")
    p.add_argument("model", nargs="?", default="")
    p.add_argument("--display-name", default="")
    p.add_argument("--models-url", default="")
    p.add_argument("--api-key", default="")
    p.add_argument("--key-env", default="", help="ชื่อ environment variable ที่เก็บ API key")
    p.add_argument("--header", action="append", default=[], help="header ที่ไม่ใช่ secret: NAME=VALUE")

    p = sub.add_parser("models", help="ดูโมเดลล่าสุดของค่ายนั้น")
    p.add_argument("--provider")
    p.add_argument("--free-only", action="store_true")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--search", default="")

    p = sub.add_parser("key", help="จัดการ API keys")
    p.add_argument("action", choices=["list", "set", "rm"])
    p.add_argument("provider", nargs="?")
    p.add_argument("key", nargs="?")

    p = sub.add_parser("use", help="ตั้งค่าเริ่มต้น")
    p.add_argument("provider")
    p.add_argument("model", nargs="?", default="")

    p = sub.add_parser("pull", help="ดาวน์โหลดโมเดล Ollama มาใช้บนเครื่อง (ฟรี)")
    p.add_argument("model", help="เช่น qwen3, llama3.1, deepseek-r1, gemma3")

    p = sub.add_parser("auto", help="เปิด/ปิดอนุมัติอัตโนมัติ (จำถาวร ไม่ต้องกด y)")
    p.add_argument("state", nargs="?", choices=["on", "off"], default="")

    p = sub.add_parser("sessions", help="ดู/ลบ บทสนทนาที่บันทึกไว้")
    p.add_argument("action", nargs="?", choices=["rm"], default=None)
    p.add_argument("target", nargs="?", default="")

    p = sub.add_parser("mcp", help="ต่อ MCP servers (tools เสริมให้ agent)")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "catalog", "install", "tools", "test", "add", "rm",
                            "on", "off", "refresh"])
    p.add_argument("target", nargs="?", default="")
    p.add_argument("rest", nargs="*", default=[])
    p.add_argument("--env", action="append", default=[],
                   help="ตัวแปรแวดล้อมให้ server (KEY=VAL ใส่ซ้ำได้)")

    p = sub.add_parser("skills", help="จัดการ skills เสริมให้ agent (มีชุดในตัวติดตั้งได้เลย)")
    p.add_argument("action", nargs="?", default="menu",
                   choices=["menu", "list", "show", "add", "install", "rm",
                            "catalog", "all", "new", "find", "search", "suggest",
                            "learning", "reset", "decline", "forget"])
    p.add_argument("target", nargs="?", default="",
                   help="คำค้นหรือชื่อ skill (โหมด find/search = คำค้น/สิ่งที่อยากทำ)")
    p.add_argument("rest", nargs="*", default=[])
    p.add_argument("--force", "-f", action="store_true", help="เขียนทับ skill ที่มีอยู่")
    p.add_argument("--web", action="store_true", help="ค้น skill บน GitHub เพิ่มด้วย")
    p.add_argument("--ai", action="store_true",
                   help="ให้ AI ดูโปรเจกต์+คำค้นแล้วเสนอ skill (ใช้กับ find/search)")
    p.add_argument("--install", action="store_true",
                   help="ติดตั้งทุกตัวที่ค้นเจอ/ที่ AI เสนอโดยไม่ถาม")

    sub.add_parser("status", help="เช็คสถานะ local + keys")

    sub.add_parser("demo", help="โชว์กรอบจักรวาลอนิเมชัน (ไม่ใช้เน็ต)")

    sub.add_parser("update", help="เช็ค + อัปเดตเป็นเวอร์ชันล่าสุด")

    # ── Git commands ──
    p = sub.add_parser("git", help="สถานะ/ประวัติ git")
    p.add_argument("git_action", nargs="?", default="status",
                   choices=["status", "diff", "log", "branch"])
    p.add_argument("--provider", help="ค่าย AI สำหรับร่าง commit")
    p.add_argument("--model", help="โมเดลสำหรับร่าง commit")

    p = sub.add_parser("commit", help="ร่างข้อความ + commit (ไม่ push)")
    p.add_argument("--provider", help="ค่าย AI สำหรับร่าง commit")
    p.add_argument("--model", help="โมเดลสำหรับร่าง commit")
    p.add_argument("--yes", action="store_true", help="commit โดยไม่ถาม")

    p = sub.add_parser("undo", help="ย้อนกลับ commit ล่าสุด + คืน checkpoint")

    p = sub.add_parser("test", help="รันเทสต์อัตโนมัติ")
    p.add_argument("path", nargs="?", default=".", help="โฟลเดอร์เทสต์")

    return ap


def main(argv=None):
    global AGENT_MAX_STEPS
    _tolerant_stdio()
    # เปิดโหมด debug = ติดตั้งตาข่ายจับ exception ที่ปกติหายเงียบ (thread/finalizer)
    # ไม่ log argv เพราะอาจมี key อยู่ในบรรทัดคำสั่ง (เช่น `soonai key set openai sk-...`)
    _DBG.install_hooks()
    keys = load_keys()
    cfg = load_config()
    apply_custom_providers(cfg)
    ap = build_parser()
    args = ap.parse_args(argv)
    AGENT_MAX_STEPS = getattr(args, "max_steps", None)
    set_term_title("soonaiTH")
    if not args.cmd:
        return cmd_chat(argparse.Namespace(
            provider=args.provider, model=args.model,
            temperature=(args.temperature if args.temperature is not None
                         else cfg.get("temperature", 0.7)),
            free_only=args.free_only, search=args.search or "",
            agent=args.agent, yes=args.yes, no_boot=args.no_boot,
            no_banner=args.no_banner, effort=args.effort or "",
            resume=args.resume), keys, cfg)
    if args.cmd == "setup":
        return cmd_setup(args, keys, cfg)
    if args.cmd == "ask":
        return cmd_ask(args, keys, cfg)
    if args.cmd == "exec":
        return cmd_exec(args, keys, cfg)
    if args.cmd == "providers":
        return cmd_providers(args, keys, cfg)
    if args.cmd == "provider":
        return cmd_provider(args, keys, cfg)
    if args.cmd == "models":
        return cmd_models(args, keys, cfg)
    if args.cmd == "key":
        if args.action == "set" and not args.provider:
            console.print("[yellow]ใช้แบบนี้: soonai key set PROVIDER [KEY] "
                          "(ไม่ใส่ KEY = ถามแบบซ่อนจอ)  (ดูรายชื่อ: soonai providers)[/yellow]")
            return 1
        if args.action == "rm" and not args.provider:
            console.print("[yellow]ใช้แบบนี้: soonai key rm PROVIDER[/yellow]")
            return 1
        return cmd_key(args, keys, cfg)
    if args.cmd == "use":
        return cmd_use(args, keys, cfg)
    if args.cmd == "status":
        return cmd_status(args, keys, cfg)
    if args.cmd == "demo":
        return cmd_demo(args)
    if args.cmd == "update":
        return cmd_update(args, keys, cfg)
    if args.cmd == "pull":
        return cmd_pull(args, keys, cfg)
    if args.cmd == "auto":
        return cmd_auto(args, keys, cfg)
    if args.cmd == "sessions":
        return cmd_sessions(args, keys, cfg)
    if args.cmd == "mcp":
        return cmd_mcp(args, keys, cfg)
    if args.cmd == "skills":
        return cmd_skills(args, keys, cfg)
    if args.cmd == "git":
        return cmd_git(args, keys, cfg)
    if args.cmd == "commit":
        return cmd_commit(args, keys, cfg)
    if args.cmd == "undo":
        return cmd_undo(args, keys, cfg)
    if args.cmd == "test":
        return cmd_test(args, keys, cfg)
    ap.print_help()
    return 0


# ── การแยกโมดูล: ผูก state เข้า runtime + จดเจ้าของชื่อ + ติด facade ────────
# ให้ทุก state/seam มี object เดียวที่ซับโมดูลใช้ร่วมกันได้
# และทำให้ `soonai.X = ...` จากภายนอก (เช่น เทสต์) mirror ลง runtime ด้วย
# (ฟังก์ชันที่ rebind ด้วย `global` ภายในจะเขียนลงโมดูลตรง ๆ — ตอนย้ายโค้ดจริง
#  ให้เปลี่ยนมาใช้ runtime.X = ... แทน)
try:
    import runtime as _RT
    _RT.mirror_globals(globals())
    # จดเจ้าของชื่อ (re-export provenance) ก่อน bind — ทุกโมดูลยังมีแต่ชื่อของตัวเอง
    # ทำให้ `soonai.X = ...` จากภายนอก (เทสต์) ส่งผลถึงโค้ด *ภายใน* โมดูลที่นิยาม X เอง
    # ถึงโมดูลนั้นไม่ถูก bind แล้วก็ตาม (จำลองพฤติกรรมตอนยังเป็นโมดูลเดียว)
    _RT.register_owners(
        (_symbols_mod, _project_mod, _usage_mod, _shell_mod, _skills_mod,
        _ui_render_mod), globals())
    # ไม่มีโมดูลไหนต้อง bind แล้ว (bind_refs = 0 ทุกตัว) — ทุกโมดูลอ่าน seam ผ่าน
    # `import runtime` เอง การจดเจ้าของชื่อข้างบนพอสำหรับให้ `soonai.X = ...`
    # จากภายนอก (เทสต์) ส่งผลถึงโค้ดภายในโมดูลนั้นด้วย
    # (เก็บ bind_module ไว้ใช้กับ cli_ui/commands ที่ยังไม่ได้ย้าย)
except Exception:
    _RT = None


class _SoonaiModule(types.ModuleType):
    """โมดูล façade: อ่าน/เขียนเหมือนเดิม แต่ mirror การเขียนลง runtime อัตโนมัติ"""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)      # global ของโมดูล (โค้ดเดิมเห็นทันที)
        if _RT is not None and not name.startswith("__"):
            try:
                setattr(_RT, name, value)     # mirror ให้ซับโมดูลในอนาคต
                _RT.propagate(name, value)    # อัปเดตซับโมดูลที่ผูกชื่อไว้ด้วย
            except Exception:
                pass

    def __getattr__(self, name):
        # เรียกเฉพาะเมื่อหา attribute ปกติไม่เจอ → ลองดูที่ runtime
        if _RT is not None:
            try:
                return getattr(_RT, name)
            except AttributeError:
                pass
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


try:
    sys.modules[__name__].__class__ = _SoonaiModule
except Exception:
    pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except (TurnCancelled, KeyboardInterrupt):
        try:
            console.print()
            console.print("[dim](ยกเลิกแล้ว)[/dim]")
        except Exception:
            pass
        raise SystemExit(130)
    except BaseException:
        import traceback
        try:
            # crash.log ต่อท้ายแล้วหมุนไฟล์เอง (เดิมเขียนทับ = ร่องรอยเก่าหายหมด)
            # พร้อมสำเนาลง debug log ถ้าเปิดโหมดอยู่
            _DBG.log_crash(traceback.format_exc())
        except Exception:
            pass
        traceback.print_exc()
        try:
            input("โปรแกรมล่ม — ก๊อปข้อความด้านบนส่งมาให้ดู แล้วกด Enter เพื่อปิด...")
        except Exception:
            pass
        raise SystemExit(1)
