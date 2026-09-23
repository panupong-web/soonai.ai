# -*- coding: utf-8 -*-
"""ศูนย์รวม state/seam ที่ใช้ร่วมกันของ CLI — Step 0 ของการแยกโมดูล

ยังไม่ย้ายโค้ด: โมดูลนี้แค่ "ถือ" ตัวแปร state ที่ทุกโมดูลจะต้องใช้ร่วมกัน
(ตัวเดียว object เดียว) เพื่อให้อนาคตย้ายฟังก์ชันไปโมดูลย่อยแล้วอ่าน/เขียน
ตัวเดียวกันได้โดยไม่ต้องส่งต่อพารามิเตอร์

กลไก:
- soonai.py เรียก ``mirror_globals(globals())`` ตอนท้าย import → คัดลอก
  ค่าปัจจุบันของ state ทั้งหมดมาไว้ที่นี่ (object เดียวกัน ไม่ copy)
- facade ที่ติดตั้งบนโมดูล soonai จะ mirror ทุกครั้งที่มีการ ``soonai.X = ...``
  มาจากภายนอก (เช่น เทสต์) ลงที่นี่ด้วย → อนาคตซับโมดูลอ่านค่าได้ตรงกัน

หมายเหตุ: ฟังก์ชันที่ใช้ ``global x; x = ...`` ภายในจะเขียนลง __dict__ ของ
soonai ตรง ๆ (ไม่ผ่าน facade) — ตอนย้ายโค้ดจริงให้เปลี่ยนเป็น ``runtime.x = ...``

── วิธีใช้จากโมดูลย่อย (กฎเดียวทั้งโปรเจกต์) ────────────────────────────────
1) ``import runtime as R`` แล้วอ่าน/เขียนด้วย **attribute access** เท่านั้น:
   ``R.load_config()``, ``R.USAGE["calls"] += 1``, ``R.CONFIG_FILE``
2) **ห้าม** ``from runtime import load_config, USAGE`` — ชื่อเหล่านี้อาจถูก
   rebind ทีหลัง (เทสต์/ฟังก์ชันที่เปลี่ยนค่า) และสำเนาที่ import ไว้จะกลายเป็น
   "ของเก่า" ทันที (attribute access เห็นค่าใหม่เสมอเพราะ facade mirror ให้)
3) ชื่อที่เป็นของโมดูลพี่น้องจริง ๆ (เช่น iter_project_files ของ project.py)
   ให้ import โมดูลนั้นตรง ๆ ไม่ต้องผ่าน runtime
"""
import threading
from pathlib import Path

# ── path พื้นฐานของโปรเจกต์ (ให้โมดูลย่อย import ได้โดยไม่ต้องรอ soonai) ──────
_THIS_FILE = Path(__file__).resolve()
SHARED_DIR = _THIS_FILE.parent          # shared/
BASE_DIR = SHARED_DIR.parent            # รากโปรเจกต์ (ที่มี soonai.py)
KEYS_FILE = SHARED_DIR / "keys.json"
CONFIG_FILE = SHARED_DIR / "config.json"

# ── state container (ค่าเริ่มต้นตรงกับ soonai.py ปัจจุบัน) ───────────────────
_MCP_DEFS_CACHE = {"defs": None}
_MCP_LAZY = {"loaded": False}  # True = โหลด MCP tools เข้า payload แล้ว (ตั้งโดย mcp_tools, รีเซ็ตทุกรอบ agent loop)
_SKILL_STATE = {"data": None}
_SKILL_CARRYOVER = {"done": False}
_SKILL_AUTOSUGGEST = {"asked": set()}
_CP = {"bucket": None, "lock": threading.Lock(), "off": False}
_ALLOW_ALL = {"on": False}
_SHELL_WARNED = {"shown": False}
_SHELL_OVERRIDE = {"mode": None}
_ALLOWED_CMDS = set()
_FORCE_TOOLS = {"on": False}
_ACCESS = {"level": None}
_TEST_CMD_CACHE = {"key": None, "cmds": ()}
_MODEL_DEAD = {}
_QUOTA_DEAD = {}
USAGE = {"calls": 0, "in": 0, "out": 0, "cost": 0.0}
_REFLECTED_SIDS = set()
_KEYS_WARN = {"shown": False}
_MIGRATED_SESSIONS = {"done": False}
SESSION_TOOLS = []
_STATUS_CACHE = {"t": 0.0, "extra": None, "ttl": 5.0}
_COSMOS_MODE = {"on": None}
_UPDATE_SCHEME_WARNED = {"shown": False}

# ── scalar seam (ถูก rebind ด้วย global) ───────────────────────────────────
AGENT_MAX_STEPS = None
LAST_SEND_ERROR = ""
LAST_MODEL_SWITCH = ""

# ชื่อ seam/state ที่ "รู้จัก" (ใช้ประกอบการอ้างอิง/ตรวจสอบ)
KNOWN_SEAMS = tuple(
    n for n in globals() if (n.startswith("_") or n.isupper()) and n not in
    ("KNOWN_SEAMS",))


def mirror_globals(ns, only_missing=False):
    """คัดลอก state จาก namespace ของ soonai มาไว้ที่ runtime (object เดียวกัน)

    - only_missing=False (ดีฟอลต์): ทับค่าที่นี่ด้วยค่าจาก ns เสมอ (ns เป็นแหล่งจริงตอน import)
    - only_missing=True: ใส่เฉพาะชื่อที่ยังไม่มี
    ข้าม dunder และของที่ import (module/function) เพื่อไม่ให้ผูกกันเกินจำเป็น
    """
    import types as _t
    n = 0
    for name, value in list(ns.items()):
        if name.startswith("__"):
            continue
        if isinstance(value, _t.ModuleType):
            continue
        if only_missing and name in globals():
            continue
        globals()[name] = value
        n += 1
    return n


# โมดูลย่อยที่ถูก "ผูกชื่อ" จาก soonai (สำหรับโค้ดที่ย้ายมาแบบ verbatim)
_BOUND_MODULES = []


def bind_module(mod, ns):
    """ให้โมดูลย่อยเห็นชื่อจาก namespace ของ soonai (โอนเฉพาะชื่อที่โมดูลยังไม่มี)
    ทำให้โค้ดที่ย้ายมาแบบ verbatim เรียกชื่อเดิมได้โดยไม่ต้องแก้
    + propagate() จะช่วยให้การ patch จากภายนอก (soonai.X = ...) อัปเดตโมดูลที่ผูกไว้ด้วย

    สถานะปัจจุบัน: **ไม่มีโมดูลไหนใช้แล้ว** (symbols/project/usage/shell/skills/
    ui_render/chat ล้วนอ่าน seam ผ่าน ``import runtime`` → depgraph bind_refs = 0)
    เก็บไว้สำหรับบล็อกที่ยังไม่ได้ย้าย (cli_ui · commands) และกันของเก่า
    — ถ้าเรียกแล้วไม่มีชื่อขาดจริง จะเป็น no-op"""
    if mod is None:
        return mod
    g = getattr(mod, "__dict__", None)
    if g is None:
        return mod
    for name, value in ns.items():
        if name.startswith("__"):
            continue
        if name not in g:
            g[name] = value
    if mod not in _BOUND_MODULES:
        _BOUND_MODULES.append(mod)
    return mod


# เจ้าของชื่อ: ชื่อที่ soonai re-export มาจากโมดูลไหน (ตรวจด้วย identity ตอน import)
# ใช้ทำ "propagate ย้อนกลับ" → `soonai.X = ...` ต้องมีผลกับโค้ด *ภายใน* โมดูล
# ที่นิยาม X เอง ด้วย (จำลองพฤติกรรมตอนยังเป็นโมดูลเดียว)
_OWNERS = {}


def register_owners(mods, ns):
    """จดว่าชื่อใดใน ns (namespace ของ soonai) ถูก re-export มาจากโมดูลใด
    เกณฑ์: วัตถุเดียวกันจริง (identity) — ไม่เดาจากชื่อ"""
    for m in mods:
        if m is None:
            continue
        g = getattr(m, "__dict__", None)
        if not isinstance(g, dict):
            continue
        for name, value in list(g.items()):
            if name.startswith("__"):
                continue
            try:
                same = ns.get(name) is value
            except Exception:
                same = False
            if not same:
                continue
            owners = _OWNERS.setdefault(name, [])
            if m not in owners:
                owners.append(m)
    return _OWNERS


def owners(name):
    return list(_OWNERS.get(name, ()))


def owner_map():
    """สำเนาทะเบียนเจ้าของชื่อทั้งหมด: {ชื่อ: [โมดูลที่เป็นเจ้าของ]} (ใช้ในเทสต์)"""
    return {k: list(v) for k, v in _OWNERS.items()}


def propagate(name, value):
    """อัปเดตชื่อที่ถูก patch ให้โมดูลที่เกี่ยวข้องเห็นค่าใหม่ตรงกัน
    - โมดูลที่ถูก bind: เขียนทุกชื่อ (โมดูลยังเรียกชื่อเดิมแบบ bare)
    - โมดูลที่ถือ "กรรมสิทธิ์" ชื่อนั้น: เขียนด้วย เพื่อให้การเรียก *ภายใน* โมดูล
      ที่ใช้ชื่อเดียวกันเห็นค่าที่ patch (เทียบเท่าตอนเป็นโมดูลเดียว)"""
    targets = list(_BOUND_MODULES) + [m for m in _OWNERS.get(name, ())
                                      if m not in _BOUND_MODULES]
    for m in targets:
        try:
            m.__dict__[name] = value
        except Exception:
            pass


def bound_modules():
    return list(_BOUND_MODULES)


def get(name, default=None):
    """อ่าน seam/state (คืน default ถ้าไม่มี)"""
    return globals().get(name, default)


def set(name, value):  # noqa: A001 - ตั้งใจใช้ชื่อสั้นให้ซับโมดูลเรียกง่าย
    """เขียน seam/state"""
    globals()[name] = value
    return value
