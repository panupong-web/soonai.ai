# -*- coding: utf-8 -*-
"""Computer Use ระดับ OS (Windows-first, stdlib ล้วน ไม่เพิ่ม dependency)

- screenshot หน้าจอจริง (GDI BitBlt -> PNG ผ่าน zlib) + ย่อภาพ box-average
- mouse/keyboard ผ่าน SendInput (พิกัด agent 0-1000 แปลงเป็น pixel ข้างใน)
- หน้าต่าง/UI tree ผ่าน Win32 (EnumWindows/EnumChildWindows + WM_GETTEXT)
- OCR แบบ best-effort (ใช้ backend ถ้ามี ไม่งั้นบอกชัดว่าไม่มี)
- ไม่มี hard-coded coordinates: ทุก action รับพิกัด 0-1000 หรือค้นจาก UI tree

ข้อสำคัญ: โมดูลนี้คือ Computer Controller ตัวเปล่า — ไม่มี policy ใด ๆ
ทุกการเรียกจาก Agent ต้องผ่าน Permission Layer (shared/permissions.py +
gate ใน soonai.run_tool/approve) ก่อนเสมอ ห้ามเรียกตรง
"""
import binascii
import ctypes
import os
import shutil
import struct
import subprocess
import time
import zlib
from ctypes import wintypes
from pathlib import Path

MAX_TYPE_CHARS = 2000
MAX_WAIT_MS = 30000
DEFAULT_SHOT_WIDTH = 1280
SHOT_RETENTION_SECONDS = 24 * 60 * 60
SHOT_RETENTION_COUNT = 20
DEFAULT_SHOT_PIXELS = 1000000


class ComputerError(Exception):
    pass


def _need_win():
    if os.name != "nt":
        raise ComputerError("Computer Use รองรับ Windows เป็นหลัก (ตอนนี้อยู่บน %s)" % os.name)


def _u32():
    return ctypes.WinDLL("user32", use_last_error=True)


def _gdi():
    return ctypes.WinDLL("gdi32", use_last_error=True)


def _k32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


# ---------- screen ----------

def screen_size():
    """ขนาดจอหลัก (พิกเซล)"""
    _need_win()
    u = _u32()
    return (u.GetSystemMetrics(0), u.GetSystemMetrics(1))


def _grab_rgb():
    """แคปจอหลักคืน (RGB rows top-down, w, h)"""
    _need_win()
    u, g = _u32(), _gdi()
    w, h = screen_size()
    if w <= 0 or h <= 0:
        raise ComputerError("อ่านขนาดหน้าจอไม่ได้")
    SRCCOPY = 0x00CC0020
    hdc_s = u.GetDC(None)
    if not hdc_s:
        raise ComputerError("GetDC ล้มเหลว")
    hdc_m = g.CreateCompatibleDC(hdc_s)
    hbmp = g.CreateCompatibleBitmap(hdc_s, w, h)
    if not hdc_m or not hbmp:
        try:
            if hdc_m:
                g.DeleteDC(hdc_m)
            u.ReleaseDC(None, hdc_s)
        except Exception:
            pass
        raise ComputerError("สร้าง surface แคปจอไม่ได้")

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    try:
        old = g.SelectObject(hdc_m, hbmp)
        if not g.BitBlt(hdc_m, 0, 0, w, h, hdc_s, 0, 0, SRCCOPY):
            raise ComputerError("BitBlt ล้มเหลว")
        g.SelectObject(hdc_m, old)
        stride = ((w * 3 + 3) // 4) * 4
        buf = ctypes.create_string_buffer(stride * h)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = h  # บวก = bottom-up, พลิกแถวเอง (ชัวร์ทุกเวอร์ชัน)
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 24
        if not g.GetDIBits(hdc_m, hbmp, 0, h, buf, ctypes.byref(bmi), 0):
            raise ComputerError("GetDIBits ล้มเหลว")
        raw = bytes(buf)
        rgb_rows = [b"".join(
            line[i + 2:i + 3] + line[i + 1:i + 2] + line[i:i + 1]
            for i in range(0, w * 3, 3)) for line in
            (raw[(h - 1 - y) * stride:(h - 1 - y) * stride + w * 3] for y in range(h))]
        return rgb_rows, w, h
    finally:
        try:
            g.DeleteObject(hbmp)
        except Exception:
            pass
        try:
            g.DeleteDC(hdc_m)
        except Exception:
            pass
        try:
            u.ReleaseDC(None, hdc_s)
        except Exception:
            pass


def _scale_for(w, h, max_width=DEFAULT_SHOT_WIDTH, max_pixels=DEFAULT_SHOT_PIXELS):
    import math
    scale = 1.0
    if w > max_width:
        scale = min(scale, max_width / w)
    if w * h * scale * scale > max_pixels:
        scale = min(scale, math.sqrt(max_pixels / (w * h)))
    return scale


def downscale_rows(rows, w, h, max_width=DEFAULT_SHOT_WIDTH, max_pixels=DEFAULT_SHOT_PIXELS):
    """ย่อภาพแบบ box-average คืน (rows, w, h)"""
    scale = _scale_for(w, h, max_width, max_pixels)
    if scale >= 1.0:
        return rows, w, h
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    out = []
    for oy in range(nh):
        y0, y1 = int(oy / scale), min(h, int((oy + 1) / scale) or 1)
        line = bytearray()
        for ox in range(nw):
            x0, x1 = int(ox / scale), min(w, int((ox + 1) / scale) or 1)
            rs = gs = bs = n = 0
            for yy in range(y0, max(y0 + 1, y1)):
                row = rows[yy]
                for xx in range(x0, max(x0 + 1, x1)):
                    o = xx * 3
                    rs += row[o]
                    gs += row[o + 1]
                    bs += row[o + 2]
                    n += 1
            line += bytes((rs // n, gs // n, bs // n))
        out.append(bytes(line))
    return out, nw, nh


def blacken_regions(rows, w, h, rects_px):
    """ทาทับ region (pixel rects) ด้วยสีดำ — ใช้ redact พื้นที่ sensitive"""
    for rc in rects_px or []:
        try:
            x0, y0, x1, y1 = (max(0, int(rc[0])), max(0, int(rc[1])),
                              min(w, int(rc[2])), min(h, int(rc[3])))
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        for yy in range(y0, y1):
            row = bytearray(rows[yy])
            row[x0 * 3:x1 * 3] = b"\x00" * ((x1 - x0) * 3)
            rows[yy] = bytes(row)
    return rows


def _png_chunk(typ, data):
    return struct.pack(">I", len(data)) + typ + data + struct.pack(
        ">I", binascii.crc32(typ + data) & 0xFFFFFFFF)


def encode_png(rows, w, h):
    """RGB rows -> bytes PNG (filter 0 ทุกแถว)"""
    raw = b"".join(b"\x00" + r for r in rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(raw, 6)) + _png_chunk(b"IEND", b""))


def capture_screen(max_width=DEFAULT_SHOT_WIDTH, redact_fullres=()):
    """แคปจอ + ย่อ + redact (rect พิกเซลเต็ม) ในขั้นตอนเดียว
    คืน {"png": bytes, "width": w, "height": h} (ขนาดหลังย่อ)"""
    rows, w, h = _grab_rgb()
    scale = _scale_for(w, h, max_width)
    rects = []
    for rc in redact_fullres or []:
        try:
            rects.append([int(rc[0] * scale), int(rc[1] * scale),
                          int(rc[2] * scale), int(rc[3] * scale)])
        except Exception:
            pass
    rows, w, h = downscale_rows(rows, w, h, max_width=max_width)
    if rects:
        blacken_regions(rows, w, h, rects)
    return {"png": encode_png(rows, w, h), "width": w, "height": h}


def screenshot_png(max_width=DEFAULT_SHOT_WIDTH, redact_px=()):
    """แคปจอ + ย่อ (+ redact ถ้า rect ตรงสเกลภาพที่ย่อแล้ว)
    ต้องการ redact จากพิกเซลเต็มให้ใช้ capture_screen(redact_fullres=...)"""
    rows, w, h = _grab_rgb()
    rows, w, h = downscale_rows(rows, w, h, max_width=max_width)
    if redact_px:
        blacken_regions(rows, w, h, redact_px)
    return {"png": encode_png(rows, w, h), "width": w, "height": h}


def save_shot(png_bytes, out_dir, name=None):
    """Save a screenshot and retain only a small, recent local history."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    if not name:
        name = "shot_%s.png" % time.strftime("%Y%m%d-%H%M%S")
    p = d / name
    p.write_bytes(png_bytes)
    try:
        (d / "last.png").write_bytes(png_bytes)
    except Exception:
        pass
    try:
        now = time.time()
        shots = sorted(d.glob("shot_*.png"), key=lambda item: item.stat().st_mtime,
                       reverse=True)
        for index, item in enumerate(shots):
            if index >= SHOT_RETENTION_COUNT or now - item.stat().st_mtime > SHOT_RETENTION_SECONDS:
                try:
                    item.unlink()
                except OSError:
                    pass
    except OSError:
        pass
    return str(p)


def to_pixels(x, y, w=None, h=None):
    """พิกัด agent 0-1000 -> pixel (clamp + ปัด, ผิดรูปแบบ = error)"""
    if w is None or h is None:
        w, h = screen_size()
    try:
        fx, fy = float(x), float(y)
    except Exception:
        raise ComputerError("พิกัดต้องเป็นตัวเลข 0-1000 (ได้ %r, %r)" % (x, y))
    if not (0 <= fx <= 1000 and 0 <= fy <= 1000):
        raise ComputerError("พิกัดต้องอยู่ใน 0-1000 (ได้ %s, %s)" % (x, y))
    return (int(fx * w / 1000), int(fy * h / 1000))


def to_1000(x, y, w=None, h=None):
    """pixel -> พิกัด 0-1000"""
    if w is None or h is None:
        w, h = screen_size()
    return (int(x * 1000 / max(1, w)), int(y * 1000 / max(1, h)))


# ---------- mouse ----------

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send_input(*inputs):
    _need_win()
    u = _u32()
    arr = (_INPUT * len(inputs))(*inputs)
    n = u.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))
    if n != len(inputs):
        raise ComputerError("SendInput ส่งได้ %d/%d" % (n, len(inputs)))
    return n


def _mi(flags, data=0):
    i = _INPUT()
    i.type = 0
    i.u.mi = _MOUSEINPUT(0, 0, data, flags, 0, None)
    return i


MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000

_BUTTONS = {"left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
            "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
            "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP)}


def mouse_pos():
    """ตำแหน่งเคอร์เซอร์ปัจจุบัน (pixel)"""
    _need_win()
    pt = wintypes.POINT()
    if not _u32().GetCursorPos(ctypes.byref(pt)):
        raise ComputerError("อ่านตำแหน่งเมาส์ไม่ได้")
    return (pt.x, pt.y)


def mouse_move(x, y):
    """ย้ายเคอร์เซอร์ (พิกัด 0-1000)"""
    _need_win()
    px, py = to_pixels(x, y)
    if not _u32().SetCursorPos(px, py):
        raise ComputerError("ย้ายเมาส์ไม่ได้")
    time.sleep(0.05)
    return {"x": x, "y": y, "px": px, "py": py}


def _click_seq(button):
    b = str(button or "left").lower()
    if b not in _BUTTONS:
        raise ComputerError("ปุ่มเมาส์ต้องเป็น left/right/middle")
    dn, up = _BUTTONS[b]
    _send_input(_mi(dn), _mi(up))
    return b


def mouse_click(x, y, button="left"):
    """ย้าย + คลิก"""
    b = str(button or "left").lower()
    if b not in _BUTTONS:
        raise ComputerError("ปุ่มเมาส์ต้องเป็น left/right/middle")
    mouse_move(x, y)
    dn, up = _BUTTONS[b]
    _send_input(_mi(dn), _mi(up))
    time.sleep(0.08)
    return {"button": b, "x": x, "y": y}


def mouse_double_click(x, y, button="left"):
    """ย้าย + ดับเบิลคลิก"""
    mouse_click(x, y, button)
    time.sleep(0.06)
    b = str(button or "left").lower()
    dn, up = _BUTTONS[b]
    _send_input(_mi(dn), _mi(up))
    time.sleep(0.08)
    return {"button": b, "x": x, "y": y, "clicks": 2}


def mouse_drag(x1, y1, x2, y2, button="left", steps=12):
    """ลากจากจุดหนึ่งไปอีกจุด (พิกัด 0-1000)"""
    b = str(button or "left").lower()
    if b not in _BUTTONS:
        raise ComputerError("ปุ่มเมาส์ต้องเป็น left/right/middle")
    for v in (x1, y1, x2, y2):
        try:
            if not (0 <= float(v) <= 1000):
                raise ComputerError("พิกัดลากต้องอยู่ใน 0-1000")
        except ComputerError:
            raise
        except Exception:
            raise ComputerError("พิกัดลากต้องเป็นตัวเลข 0-1000")
    p1, p2 = to_pixels(x1, y1), to_pixels(x2, y2)
    u = _u32()
    u.SetCursorPos(*p1)
    time.sleep(0.08)
    dn, up = _BUTTONS[b]
    _send_input(_mi(dn))
    steps = max(2, min(60, int(steps or 12)))
    for i in range(1, steps + 1):
        u.SetCursorPos(int(p1[0] + (p2[0] - p1[0]) * i / steps),
                       int(p1[1] + (p2[1] - p1[1]) * i / steps))
        time.sleep(0.008)
    _send_input(_mi(up))
    time.sleep(0.08)
    return {"from": [x1, y1], "to": [x2, y2], "button": b}


def mouse_scroll(dy=3, dx=0):
    """สกรอลล์ (dy บวก = ขึ้น, ลบ = ลง หน่วยบรรทัด; dx = แนวนอน)"""
    _need_win()
    try:
        dy, dx = int(dy or 0), int(dx or 0)
    except Exception:
        raise ComputerError("scroll ต้องเป็นตัวเลข")
    dy, dx = max(-20, min(20, dy)), max(-20, min(20, dx))
    if dy:
        _send_input(_mi(MOUSEEVENTF_WHEEL, data=(dy * 120) & 0xFFFFFFFF))
    if dx:
        _send_input(_mi(MOUSEEVENTF_HWHEEL, data=(dx * 120) & 0xFFFFFFFF))
    time.sleep(0.1)
    return {"dy": dy, "dx": dx}


# ---------- keyboard ----------

KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004

_VK = {
    "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "win": 0x5B,
    "capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91,
    "printscreen": 0x2C, "pause": 0x13, "apps": 0x5D,
}
_VK.update({"f%d" % i: 0x6F + i for i in range(1, 25)})
_ALIAS = {"del": "delete", "ins": "insert", "pgup": "pageup", "pgdn": "pagedown",
          "return": "enter", "control": "ctrl", "cmd": "win",
          "windows": "win", "option": "alt"}


def _vk_down(vk):
    i = _INPUT()
    i.type = 1
    i.u.ki = _KEYBDINPUT(vk, 0, 0, 0, None)
    return i


def _vk_up(vk):
    i = _INPUT()
    i.type = 1
    i.u.ki = _KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, None)
    return i


def _uni(ch, up=False):
    i = _INPUT()
    i.type = 1
    i.u.ki = _KEYBDINPUT(0, ord(ch), (KEYEVENTF_KEYUP if up else 0) | KEYEVENTF_UNICODE, 0, None)
    return i


def resolve_key(name):
    """ชื่อปุ่ม -> (vk, need_shift) รองรับ a-z 0-9 ปุ่มพิเศษ F1-F24"""
    _need_win()
    s = str(name or "").strip().lower()
    s = _ALIAS.get(s, s)
    if s in _VK:
        return (_VK[s], False)
    if len(s) == 1:
        u = _u32()
        scan = u.VkKeyScanW(ord(s))
        if (scan & 0xFF) == 0xFF:
            raise ComputerError("ปุ่มไม่รู้จัก: %r" % name)
        return (scan & 0xFF, bool((scan >> 8) & 1))
    raise ComputerError("ปุ่มไม่รู้จัก: %r (เช่น enter/tab/esc/space/up/f5/win)" % name)


def press_key(name):
    """กดปุ่ม 1 ครั้ง (down+up)"""
    vk, shift = resolve_key(name)
    seq = [_vk_down(0x10)] if shift else []
    seq += [_vk_down(vk), _vk_up(vk)]
    if shift:
        seq.append(_vk_up(0x10))
    _send_input(*seq)
    time.sleep(0.05)
    return {"key": name}


def hotkey(keys):
    """กดปุ่มลัด เช่น ["ctrl","s"] (modifiers ค้างไว้ก่อน ปล่อยย้อนกลับ)"""
    if not keys or not isinstance(keys, (list, tuple)):
        raise ComputerError("hotkey ต้องเป็นลิสต์ชื่อปุ่ม เช่น ['ctrl','s']")
    if len(keys) > 5:
        raise ComputerError("hotkey ยาวเกิน (สูงสุด 5 ปุ่ม)")
    vks = [resolve_key(k)[0] for k in keys]
    for vk in vks[:-1]:
        _send_input(_vk_down(vk))
        time.sleep(0.03)
    _send_input(_vk_down(vks[-1]), _vk_up(vks[-1]))
    for vk in reversed(vks[:-1]):
        time.sleep(0.03)
        _send_input(_vk_up(vk))
    time.sleep(0.08)
    return {"hotkey": list(keys)}


def type_text(text, chunk=64, interval=0.004):
    """พิมพ์ข้อความ Unicode ตรงจุดโฟกัส (สูงสุด MAX_TYPE_CHARS ตัว)"""
    _need_win()
    s = str(text or "")
    if len(s) > MAX_TYPE_CHARS:
        raise ComputerError("ข้อความยาวเกิน %d ตัวอักษร" % MAX_TYPE_CHARS)
    n = 0
    for i in range(0, max(1, len(s)), chunk):
        seq = []
        for ch in s[i:i + chunk]:
            seq.append(_uni(ch, False))
            seq.append(_uni(ch, True))
        if seq:
            _send_input(*seq)
            n += len(s[i:i + chunk])
        time.sleep(interval)
    time.sleep(0.1)
    return {"typed": n}


def wait_ms(ms):
    """รอ (0-30000 ms) ให้ UI เปลี่ยน"""
    try:
        ms = int(ms)
    except Exception:
        raise ComputerError("wait ต้องเป็นตัวเลข ms")
    ms = max(0, min(MAX_WAIT_MS, ms))
    time.sleep(ms / 1000.0)
    return {"waited_ms": ms}


# ---------- windows / UI tree (Win32, ไม่ hard-code) ----------

def _win_text(hwnd):
    u = _u32()
    try:
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or ""
    except Exception:
        return ""


def _win_class(hwnd):
    try:
        buf = ctypes.create_unicode_buffer(256)
        n = _u32().GetClassNameW(hwnd, buf, 256)
        return buf.value if n else ""
    except Exception:
        return ""


def _win_rect(hwnd):
    try:
        r = wintypes.RECT()
        if not _u32().GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        return [r.left, r.top, r.right, r.bottom]
    except Exception:
        return None


def _exe_of(hwnd):
    try:
        pid = wintypes.DWORD()
        _u32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        k = _k32()
        h = k.OpenProcess(0x1000, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value or "").lower()
        finally:
            try:
                k.CloseHandle(h)
            except Exception:
                pass
    except Exception:
        pass
    return ""


def list_windows(visible_only=True, limit=100):
    """รายชื่อหน้าต่าง top-level (title/class/rect/exe) — หาแอปแบบไม่ hard-code"""
    _need_win()
    u = _u32()
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        try:
            if visible_only and not u.IsWindowVisible(hwnd):
                return True
            title = _win_text(hwnd)
            if visible_only and not title:
                return True
            out.append({"hwnd": int(hwnd), "title": title,
                        "class": _win_class(hwnd), "rect": _win_rect(hwnd),
                        "exe": _exe_of(hwnd)})
        except Exception:
            pass
        return True

    _list_windows_cb = cb  # กัน GC ระหว่าง Enum
    u.EnumWindows(cb, 0)
    return out[:max(1, int(limit or 100))]


def foreground_window():
    """หน้าต่างที่โฟกัสอยู่ตอนนี้"""
    _need_win()
    hwnd = _u32().GetForegroundWindow()
    if not hwnd:
        return {}
    return {"hwnd": int(hwnd), "title": _win_text(hwnd), "class": _win_class(hwnd),
            "rect": _win_rect(hwnd), "exe": _exe_of(hwnd)}


def _control_text(hwnd, cls):
    if _win_text(hwnd):
        return _win_text(hwnd)
    if "edit" in (cls or "").lower():
        try:
            buf = ctypes.create_unicode_buffer(4096)
            fn = _u32().SendMessageTimeoutW
            fn.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                           ctypes.c_ssize_t, wintypes.UINT, wintypes.UINT,
                           ctypes.POINTER(ctypes.c_ssize_t)]
            fn.restype = wintypes.LPARAM
            done = ctypes.c_ssize_t(0)
            fn(hwnd, 0x000D, 4095, ctypes.cast(buf, ctypes.c_void_p).value,
               0x0002, 800, ctypes.byref(done))
            return buf.value or ""
        except Exception:
            return ""
    return ""


def window_tree(hwnd=None, depth=0, max_depth=3, max_nodes=200, _count=None):
    """UI tree ของหน้าต่าง (children recursive + ข้อความ/rect)"""
    _need_win()
    if _count is None:
        _count = [0]
    if hwnd is None:
        fg = foreground_window()
        hwnd = fg.get("hwnd")
        if not hwnd:
            raise ComputerError("หาหน้าต่างโฟกัสไม่เจอ")
    if _count[0] >= max_nodes or depth > max_depth:
        return {}
    _count[0] += 1
    u = _u32()
    cls = _win_class(hwnd)
    node = {"hwnd": int(hwnd), "class": cls, "text": _control_text(hwnd, cls)[:300],
            "rect": _win_rect(hwnd), "children": []}
    if depth >= max_depth:
        return node
    kids = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(ch, _lp):
        kids.append(int(ch))
        return _count[0] < max_nodes

    _tree_cb = cb
    try:
        u.EnumChildWindows(hwnd, cb, 0)
    except Exception:
        pass
    for ch in kids:
        try:
            sub = window_tree(ch, depth + 1, max_depth, max_nodes, _count)
            if sub:
                node["children"].append(sub)
        except Exception:
            pass
    return node


def find_process_windows(exe_substr, visible_only=True):
    """หาหน้าต่างตามชื่อโปรแกรม (substring ไม่สนตัวพิมพ์) เช่น chrome, notepad"""
    want = str(exe_substr or "").lower().strip()
    if not want:
        raise ComputerError("ต้องระบุชื่อโปรแกรม")
    return [w for w in list_windows(visible_only=visible_only, limit=200)
            if want in (w.get("exe") or "") or want in (w.get("title") or "").lower()]


def focus_window(hwnd):
    """ดึงหน้าต่างขึ้นโฟกัส (best-effort: OS อาจปฏิเสธได้)"""
    _need_win()
    try:
        hwnd = int(hwnd)
    except Exception:
        raise ComputerError("hwnd ต้องเป็นตัวเลข")
    u = _u32()
    try:
        u.ShowWindow(hwnd, 9)  # SW_RESTORE
    except Exception:
        pass
    ok = bool(u.SetForegroundWindow(hwnd))
    time.sleep(0.15)
    return {"hwnd": hwnd, "focused": ok}


# ---------- OCR (best-effort: ใช้ backend ถ้ามี) ----------

def ocr_backends():
    """รายชื่อ OCR backend ที่ใช้ได้ตอนนี้ (ว่าง = ไม่มี)"""
    found = []
    for mod in ("pytesseract", "easyocr", "paddleocr"):
        try:
            __import__(mod)
            found.append("py:" + mod)
        except Exception:
            pass
    if shutil.which("tesseract"):
        found.append("exe:tesseract")
    return found


def ocr_image_file(path, lang="eng+tha"):
    """OCR ไฟล์ภาพ (ต้องมี backend) คืนข้อความ"""
    backends = ocr_backends()
    if not backends:
        raise ComputerError("ไม่มี OCR backend (ติดตั้ง Tesseract หรือ pip install pytesseract) — "
                            "ใช้ computer_vision หรือ UI tree แทนได้")
    last = ""
    if shutil.which("tesseract"):
        try:
            r = subprocess.run(["tesseract", str(path), "stdout", "-l", lang],
                               capture_output=True, text=True, timeout=60,
                               errors="replace")
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()[:6000]
            last = (r.stderr or "")[:200]
        except Exception as e:
            last = str(e)[:200]
    try:
        pt = __import__("pytesseract")
        from PIL import Image as _I  # type: ignore
        return pt.image_to_string(_I.open(path), lang="tha+eng")[:6000]
    except Exception as e:
        last = str(e)[:200]
    raise ComputerError("OCR ล้มเหลวทุก backend (%s)" % last)


def status():
    """สรุปความพร้อม Computer Use ของเครื่องนี้"""
    _need_win()
    w, h = screen_size()
    return {"os": os.name, "screen": [w, h],
            "ocr_backends": ocr_backends(),
            "mouse": True, "keyboard": True, "windows_api": True}
