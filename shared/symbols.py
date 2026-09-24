# -*- coding: utf-8 -*-
"""symbols: แผนที่สัญลักษณ์ของไฟล์/โปรเจกต์ให้ agent อ่านแบบประหยัด token

ย้ายมาจาก soonai.py (Step 1) — การพึ่งโมดูลอื่นทำตรง ๆ แล้ว:
- ``import project`` สำหรับ iter_project_files/_resolve_tool_path (โมดูลพี่น้อง)
- ``import runtime as R`` สำหรับ seam (load_config, _path_is_sensitive)
จึงไม่มี bind_refs เหลือใน ``depgraph.py``
"""
import os
import re
from pathlib import Path

import project as _project
import runtime as R


# ── แผนที่สัญลักษณ์ (M5): ให้ agent เข้าใจโครงไฟล์โดยไม่ต้องอ่านทั้งไฟล์ ──────
CODE_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".go", ".rs",
                 ".java", ".kt", ".cs", ".rb", ".php", ".swift", ".cpp", ".cc", ".c", ".h")
SYMBOL_MAX_FILES = 40
SYMBOL_MAX_PER_FILE = 60
_JS_SYMBOL_RE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(function|class|const|let|var|type|interface|enum)\s+([A-Za-z_$][\w$]*)", re.M)
_GO_SYMBOL_RE = re.compile(r"^(func|type)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", re.M)
def file_symbols(path, max_symbols=SYMBOL_MAX_PER_FILE):
    """สัญลักษณ์ระดับบนของไฟล์ — Python ใช้ ast (แม่น) · ภาษาอื่นใช้ regex
    คืน list ของ (บรรทัด, ป้ายชื่อ)"""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        size = p.stat().st_size
        # ast ทนไฟล์ใหญ่ได้ ส่วน regex จำกัดไว้กันไฟล์รวมขนาดมหาศาล
        if size > (2_000_000 if suffix == ".py" else 800_000):
            return []
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    if suffix == ".py":
        try:
            import ast
            out = []
            for node in ast.parse(text).body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append((node.lineno, f"def {node.name}"))
                elif isinstance(node, ast.ClassDef):
                    out.append((node.lineno, f"class {node.name}"))
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            out.append((sub.lineno, f"    {node.name}.{sub.name}"))
                elif isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id.isupper():
                            out.append((node.lineno, f"{t.id} ="))
                if len(out) >= max_symbols:
                    break
            return out[:max_symbols]
        except SyntaxError:
            return []
    rx = _GO_SYMBOL_RE if suffix == ".go" else (
        _JS_SYMBOL_RE if suffix in CODE_SUFFIXES else None)
    if rx is None:
        return []
    out = []
    for m in rx.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        out.append((line, f"{m.group(1)} {m.group(2)}"))
        if len(out) >= max_symbols:
            break
    return out
def outline_text(path=".", max_files=SYMBOL_MAX_FILES, budget=6000):
    """แผนที่สัญลักษณ์ของไฟล์โค้ดใต้ path (path: บรรทัด: สัญลักษณ์) สำหรับ agent"""
    root = _project._resolve_tool_path(path or ".")
    if root.is_file():
        if R._path_is_sensitive(root):
            return f"(อ่าน {root.name} ไม่ได้ — ไฟล์ secret)"
        files = [root]
    elif root.is_dir():
        files = [f for f in _project.iter_project_files(root)
                 if f.suffix.lower() in CODE_SUFFIXES and not R._path_is_sensitive(f)]
    else:
        return "(ไม่พบไฟล์)"
    lines, shown = [], 0
    for f in files:
        if shown >= max_files:
            break
        syms = file_symbols(f)
        if not syms:
            continue
        shown += 1
        if root.is_file():
            rel = f.name
        else:
            try:
                rel = str(f.relative_to(root)).replace("\\", "/")
            except Exception:
                rel = f.name
        try:
            n = f.stat().st_size
        except Exception:
            n = 0
        lines.append(f"{rel} ({n} bytes)")
        lines += [f"  {ln}: {label}" for ln, label in syms]
        lines.append("")
    if not lines:
        return f"(ไม่พบไฟล์โค้ดที่มีสัญลักษณ์ใน {root})"
    if shown >= max_files:
        lines.append(f"... (แสดง {max_files} ไฟล์แรก)")
    text = "\n".join(lines)
    return text[:budget] if len(text) > budget else text
def _symbol_map_enabled():
    if os.environ.get("SOONAI_NO_SYMBOL_MAP"):
        return False
    try:
        return bool((R.load_config().get("agent") or {}).get("symbol_map", True))
    except Exception:
        return True
def _attach_symbol_map(messages, budget=2500, max_files=12):
    """แนบแผนที่สัญลักษณ์ให้ agent แทนการอ่านทั้งไฟล์ (ครั้งเดียวต่อคำขอ)"""
    try:
        if not _symbol_map_enabled() or not messages:
            return messages
        if messages[0].get("role") != "system":
            return messages
        if "[แผนที่สัญลักษณ์" in (messages[0].get("content") or ""):
            return messages
        text = outline_text(".", max_files=max_files, budget=budget)
        if text.startswith("(ไม่พบ"):
            return messages
        messages[0] = {"role": "system", "content": messages[0]["content"] +
                       "\n[แผนที่สัญลักษณ์โปรเจกต์ — อ่านเพิ่มเฉพาะจุดที่ต้องใช้ "
                       "หรือเรียก tool outline ถ้าต้องการละเอียดกว่า]\n" + text}
    except Exception:
        pass
    return messages
