# -*- coding: utf-8 -*-
"""project: ย้ายมาจาก soonai.py (Step 1 · verbatim)
โค้ดอ้างชื่อภายนอกผ่านการ bind จาก soonai ตอน import (ดู runtime.bind_module)
"""
import os
from pathlib import Path


def _expand_known_folders(p):
    """ขยายชื่อโฟลเดอร์พิเศษ ('Desktop/x', 'เดสก์ท็อป', 'Documents', 'Downloads' …) เป็นพาธจริง
    กันโมเดลเดาผิดแล้วได้พาธซ้อนแบบ <โปรเจกต์>/Desktop
    ถ้ามีโฟลเดอร์ชื่อนั้นในที่ปัจจุบันอยู่แล้ว จะใช้แบบ relative ตามเดิม"""
    s = str(p or "").strip().replace("/", os.sep)
    if not s:
        return s
    home = Path.home()
    table = {
        "desktop": home / "Desktop",
        "เดสก์ท็อป": home / "Desktop",
        "documents": home / "Documents",
        "เอกสาร": home / "Documents",
        "downloads": home / "Downloads",
        "ดาวน์โหลด": home / "Downloads",
        "home": home,
    }
    first = s.split(os.sep)[0].strip().lower()
    if first not in table:
        return s
    if not os.path.isabs(s):
        try:
            # มีโฟลเดอร์ชื่อนี้ในที่ปัจจุบันอยู่แล้ว = หมายถึงในโปรเจกต์ ใช้แบบ relative
            if Path(s.split(os.sep)[0]).expanduser().is_dir():
                return s
        except Exception:
            pass
    rest = os.sep.join(x for x in s.split(os.sep)[1:] if x not in ("", "."))
    base = table[first]
    return str(base if not rest else base / rest)
def _resolve_tool_path(p):
    return Path(_expand_known_folders(p)).expanduser().resolve()
SNAP_IGNORE = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist",
               "build", ".next", "target", ".idea", ".vscode"}
def project_snapshot(root=".", max_files=100, max_depth=4, max_chars=6000):
    """แผนที่โครงโปรเจกต์แบบเร็ว (ข้ามโฟลเดอร์หนัก) แนบให้ agent เข้าใจงานโดยไม่ต้องสำรวจเอง"""
    base = Path(root or ".").expanduser().resolve()
    lines, count = [], [0]

    def walk(dirpath, depth, prefix):
        if depth > max_depth or count[0] >= max_files:
            return
        try:
            entries = sorted(os.scandir(dirpath), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception:
            return
        for e in entries:
            if count[0] >= max_files:
                break
            if e.name in SNAP_IGNORE or e.name.startswith("."):
                if e.name not in (".env.example",):
                    continue
            try:
                is_dir = e.is_dir()
            except Exception:
                continue
            count[0] += 1
            lines.append(f"{prefix}{e.name}/" if is_dir else f"{prefix}{e.name}")
            if is_dir:
                walk(e.path, depth + 1, prefix + "  ")

    try:
        rel = os.path.relpath(base, Path.cwd())
    except Exception:
        rel = str(base)
    walk(str(base), 0, "")
    head = f"[โครงสร้างโปรเจกต์ {rel}]\n"
    text = head + "\n".join(lines)
    if count[0] >= max_files:
        text += f"\n... (แสดง {max_files} รายการแรก)"
    return text[:max_chars]
MEMORY_FILENAMES = ("AGENTS.md", "Agents.md", "agents.md")
def find_agents_files(root=None, max_up=6):
    """หา AGENTS.md จากโฟลเดอร์ปัจจุบันไล่ขึ้นไปถึงราก (กันอ่านผิดโปรเจกต์)
    คืนลิสต์พาธจากชั้นบนสุด(กว้าง)ลงมาชั้นล่างสุด(เจาะจง)"""
    try:
        cur = Path(root or ".").expanduser().resolve()
    except Exception:
        return []
    found = []
    for _ in range(max_up + 1):
        for name in MEMORY_FILENAMES:
            try:
                p = cur / name
                if p.is_file():
                    found.append(p)
                    break
            except Exception:
                pass
        try:
            parent = cur.parent
        except Exception:
            break
        if parent == cur:
            break
        cur = parent
    found.reverse()
    return found
def project_memory(root=None, max_chars=4000):
    """อ่าน AGENTS.md ทุกชั้น (บน->ล่าง) รวมเป็นความจำโปรเจกต์ให้ agent (ว่าง = '')"""
    parts = []
    try:
        files = find_agents_files(root)
    except Exception:
        return ""
    for p in files:
        try:
            t = p.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if not t:
            continue
        try:
            rel = p.relative_to(Path.cwd())
        except Exception:
            rel = p
        parts.append(f"[AGENTS.md: {rel}]\n{t}")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (ตัดให้สั้น)"
    return text
def _attach_project_memory(messages):
    """เติมความจำโปรเจกต์ (AGENTS.md) ต่อท้าย system prompt (มีแล้วไม่เติมซ้ำ)"""
    try:
        if not messages or messages[0].get("role") != "system":
            return messages
        if "[AGENTS.md:" in (messages[0].get("content") or ""):
            return messages
        mem = project_memory()
        if mem:
            messages[0] = {"role": "system",
                           "content": messages[0]["content"] + "\n" + mem}
    except Exception:
        pass
    return messages
INIT_HINT_FILES = ("package.json", "pyproject.toml", "requirements.txt",
                   "README.md", "go.mod", "Cargo.toml", ".env.example")
def collect_init_context(max_chars=6000):
    """เก็บข้อมูลโปรเจกต์สำหรับร่าง AGENTS.md (โครง + ไฟล์สำคัญ)"""
    parts = []
    try:
        snap = project_snapshot()
        if snap:
            parts.append(snap)
    except Exception:
        pass
    for name in INIT_HINT_FILES:
        try:
            p = Path.cwd() / name
            if p.is_file() and p.stat().st_size < 20000:
                t = p.read_text(encoding="utf-8", errors="replace").strip()
                if t:
                    parts.append(f"[ไฟล์: {name}]\n{t[:1500]}")
        except Exception:
            pass
    return "\n\n".join(parts)[:max_chars]
# ---------- เดินไฟล์ในโปรเจกต์แบบมีมารยาท (ใช้ร่วมกันโดย grep/glob/snapshot) ----------
HEAVY_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "env",
              "dist", "build", ".next", "out", "target", ".idea", ".vscode",
              ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "coverage",
              "htmlcov", "vendor", "Pods", "DerivedData", "bin", "obj", ".cache"}
IGNORE_FILES = (".gitignore", ".soonaiignore", ".ignore")
MAX_SCAN_FILES = 4000
def _ignore_patterns(root):
    """อ่าน pattern จาก .gitignore/.soonaiignore (แบบง่าย ไม่ต้องมี git)
    รองรับ # ความเห็น, ! (ยกเลิก), ชื่อโฟลเดอร์ลงท้าย /"""
    pats = []
    for name in IGNORE_FILES:
        try:
            p = Path(root) / name
            if not p.is_file() or p.stat().st_size > 200000:
                continue
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or s.startswith("!"):
                    continue
                pats.append(s.rstrip("/").lstrip("/"))
        except Exception:
            continue
    return pats
def _ignored_rel(rel, name, patterns):
    """พาธ relative นี้ถูก ignore ไหม (เดาแบบ git: ชื่อโฟลเดอร์/ไฟล์/ครอบแม่)"""
    import fnmatch
    if name in HEAVY_DIRS:
        return True
    for pat in patterns:
        if not pat:
            continue
        if "/" in pat:
            if fnmatch.fnmatch(rel, pat) or rel.startswith(pat + "/"):
                return True
            continue
        if fnmatch.fnmatch(name, pat):
            return True
        for part in rel.split("/")[:-1]:  # โฟลเดอร์แม่ถูก ignore = ลูกก็ ignore
            if fnmatch.fnmatch(part, pat):
                return True
    return False
def iter_project_files(root=".", limit=MAX_SCAN_FILES):
    """เดินไฟล์ทั้งโปรเจกต์: ข้ามโฟลเดอร์หนัก + ตาม .gitignore/.soonaiignore
    คืนลิสต์ Path (ว่างถ้า root ไม่ใช่โฟลเดอร์) — ใช้แทน rglob เพื่อไม่กวาด node_modules/.venv"""
    import os as _os
    base = Path(root)
    if not base.is_dir():
        return []
    patterns = _ignore_patterns(base)
    out = []
    for cur, dirs, files in _os.walk(str(base)):
        try:
            rel_cur = str(Path(cur).relative_to(base)).replace("\\", "/")
        except Exception:
            rel_cur = ""
        if rel_cur == ".":
            rel_cur = ""
        dirs[:] = [d for d in dirs
                   if not _ignored_rel((rel_cur + "/" + d) if rel_cur else d, d, patterns)]
        for f in files:
            rel = (rel_cur + "/" + f) if rel_cur else f
            if _ignored_rel(rel, f, patterns):
                continue
            out.append(Path(cur) / f)
            if len(out) >= max(1, int(limit or MAX_SCAN_FILES)):
                return out
    return out
