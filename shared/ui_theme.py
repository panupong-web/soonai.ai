# -*- coding: utf-8 -*-
"""ธีมกลางของ UI — โทน "เรียบหรู" (restrained · one accent · readable)

แนวคิด:
- พื้นเป็นสีเทอร์มินัลของผู้ใช้ ไม่ยัดสีพื้นหลัง
- accent เดียว (soft indigo) ที่เหลือเป็นกลาง muted/faint
- เส้นขอบบางสีจาง ไม่ใช่ neon/magenta
- leverage สูงสุด: remap ชื่อสีพื้นฐานของ Rich (cyan/magenta/green/...)
  ผ่าน Theme → ทั้ง CLI เปลี่ยนโทนพร้อมกันโดยไม่ต้องแก้ทุก call site
- เคารพ NO_COLOR / TERM=dumb (ปิดสีแล้วยังอ่านได้ทุกบรรทัด)

ใช้:  from ui_theme import PALETTE, rich_theme, glyph, GLYPH
"""
import os

# ── palette (hex) — โทนกลางหม่น + accent เดียว ────────────────────────────
PALETTE = {
    "accent":  "#8ab4f8",   # ฟ้าเทาอ่อน — accent เดียวของทั้ง UI
    "accent2": "#b4a7e8",   # ม่วงหม่น (เน้นรอง)
    "text":    "#e6e6e6",
    "muted":   "#9aa0a6",   # ป้าย/คำอธิบาย
    "faint":   "#5f6368",   # เส้น/ตัวคั่น
    "ok":      "#9ccc9c",
    "warn":    "#e0c98a",
    "err":     "#e0a0a0",
    "code":    "#c9d1d9",
}

THEMES = {
    "luxe": dict(PALETTE),
    "classic": {
        **PALETTE,
        "accent": "#00e5ff",
        "accent2": "#ff2fd6",
        "muted": "#b8b8b8",
        "faint": "#666666",
    },
    "aurora": {
        **PALETTE,
        "accent": "#72f1b8",
        "accent2": "#7aa2f7",
        "muted": "#a6c8b6",
        "faint": "#536b61",
    },
    "sunset": {
        **PALETTE,
        "accent": "#ff9e64",
        "accent2": "#f7768e",
        "muted": "#d8b08c",
        "faint": "#755c4c",
    },
    "ocean": {
        **PALETTE,
        "accent": "#4cc9f0",
        "accent2": "#4361ee",
        "muted": "#9ec5d6",
        "faint": "#426273",
    },
    "forest": {
        **PALETTE,
        "accent": "#8ac926",
        "accent2": "#198754",
        "muted": "#b8d39a",
        "faint": "#526b3a",
    },
    "cyberpunk": {
        **PALETTE,
        "accent": "#fcee0a",
        "accent2": "#ff003c",
        "muted": "#e0dc82",
        "faint": "#706c25",
    },
    "mono": {
        **PALETTE,
        "accent": "#ffffff",
        "accent2": "#bdbdbd",
        "muted": "#b0b0b0",
        "faint": "#666666",
    },
}


def theme_names():
    return tuple(THEMES)


def palette_for(name):
    return dict(THEMES.get(str(name or "").strip().lower(), THEMES["luxe"]))


def apply_theme(name):
    selected = str(name or "").strip().lower()
    if selected not in THEMES:
        return ""
    PALETTE.clear()
    PALETTE.update(THEMES[selected])
    return selected

# ── glyph ─────────────────────────────────────────────────────────────────
GLYPH = {"ok": "✓", "err": "✗", "warn": "!", "bullet": "·", "arrow": "→",
         "prompt": "❯", "dot": "•", "rule": "─"}


def color_ok():
    """สีเปิดได้ไหม — เคารพ NO_COLOR / TERM=dumb"""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return True


def glyph(name, fallback="·"):
    """glyph แบบ ASCII-safe เมื่อสี/ยูนิโค้ดไม่เหมาะ"""
    return GLYPH.get(name, fallback)


def rich_theme(palette=None):
    """สร้าง rich.theme.Theme จาก palette (ค่าเริ่มต้น = PALETTE ปัจจุบัน)

    remap ชื่อสีพื้นฐานเพื่อให้ทุก `[cyan]`/`[magenta]`/... ทั้งโปรแกรม
    เปลี่ยนเป็นโทนใหม่พร้อมกัน
    """
    from rich.theme import Theme
    p = palette or PALETTE
    t = {}
    t["cyan"] = p["accent"]
    t["bright_cyan"] = p["accent"]
    t["blue"] = p["accent"]
    t["bright_blue"] = p["accent"]
    t["magenta"] = p["accent2"]
    t["bright_magenta"] = p["accent2"]
    t["green"] = p["ok"]
    t["bright_green"] = p["ok"]
    t["yellow"] = p["warn"]
    t["bright_yellow"] = p["warn"]
    t["red"] = p["err"]
    t["bright_red"] = p["err"]
    t["dim"] = "grey54"
    return Theme(t)


def console_theme(theme_name="luxe"):
    """Theme ตามชื่อที่ตั้งใน config (ui.theme) — ทุกธีมรวมทั้ง classic ใช้ palette ของตัวเอง"""
    apply_theme(theme_name)
    return rich_theme(palette=PALETTE)


def style(name):
    """สไตล์ rich ของสี name ('' ถ้าปิดสี)"""
    if not color_ok():
        return ""
    return PALETTE.get(name, "")


def markup(text, name, fallback=""):
    """ห่อข้อความด้วยแท็กสี name (คืนข้อความเปล่า ๆ ถ้าปิดสี/ไม่มีสไตล์นั้น)

    จำเป็นต้องใช้แทน f"[{style('x')}]{text}[/]" ตรง ๆ เพราะเมื่อ NO_COLOR/TERM=dumb
    style() คืน '' → ได้แท็กว่าง `[]…[/]` ซึ่ง Rich โยน MarkupError
    ("closing tag '[/]' has nothing to close")
    """
    s = style(name) or fallback
    if not s:
        return str(text)
    return f"[{s}]{text}[/]"


def rule(width=0):
    try:
        import shutil
        w = width or shutil.get_terminal_size((80, 24)).columns
    except Exception:
        w = width or 80
    return markup(GLYPH["rule"] * max(1, w), "faint")


def logo_style():
    """สีของโลโก้ (monochrome accent ไม่ไล่รุ้ง)"""
    return PALETTE["accent"]
