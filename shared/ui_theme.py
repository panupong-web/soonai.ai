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


def rich_theme(classic=False):
    """สร้าง rich.theme.Theme — โทน luxe (ดีฟอลต์) หรือ classic (นีออนเดิม)

    remap ชื่อสีพื้นฐานเพื่อให้ทุก `[cyan]`/`[magenta]`/... ทั้งโปรแกรม
    เปลี่ยนเป็นโทนใหม่พร้อมกัน
    """
    from rich.theme import Theme
    if classic:
        return Theme({})
    t = {}
    t["cyan"] = PALETTE["accent"]
    t["bright_cyan"] = PALETTE["accent"]
    t["blue"] = PALETTE["accent"]
    t["bright_blue"] = PALETTE["accent"]
    t["magenta"] = PALETTE["accent2"]
    t["bright_magenta"] = PALETTE["accent2"]
    t["green"] = PALETTE["ok"]
    t["bright_green"] = PALETTE["ok"]
    t["yellow"] = PALETTE["warn"]
    t["bright_yellow"] = PALETTE["warn"]
    t["red"] = PALETTE["err"]
    t["bright_red"] = PALETTE["err"]
    t["dim"] = "grey54"
    return Theme(t)


def console_theme(theme_name="luxe"):
    """Theme ตามชื่อที่ตั้งใน config (ui.theme)"""
    return rich_theme(classic=(str(theme_name or "luxe").lower() == "classic"))


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
