# -*- coding: utf-8 -*-
"""Regression: Permission Layer (Computer Use) fail-closed + ขอบเขต scope
- fg ระบุไม่ได้ (unknown) + scope จำกัดแอป = ปฏิเสธ (ไม่หลุดเป็น other)
- fg ว่าง + scope เปิดกว้างทุกแอป = อนุญาต (ไม่บล็อกงานปกติ)
- หมวด browser/terminal/settings เดิมยังบังคับ
- action ไม่มีพิกัด/ไม่อยู่ใน scope capability = ปฏิเสธ
ไม่แตะ Win32 จริง (ส่ง fg จำลองเข้า evaluate ตรง ๆ)
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import permissions as P  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


def pol(**kw):
    base = {"level": "interact", "approval": "auto", "grant_until": 0,
            "scope": dict(P.SCOPE_DEFAULTS)}
    base.update(kw)
    return base


OPEN = {"screen": True, "mouse": True, "keyboard": True, "browser": True,
        "terminal": True, "filesystem": "deny", "system_settings": True,
        "apps_allow": [], "apps_deny": [], "windows_allow": [], "regions": []}

CLICK = {"x": 10, "y": 10}
TERM_FG = {"exe": "WindowsTerminal.exe", "title": "PowerShell", "class": ""}

# 1) fg ว่าง + scope ดีฟอลต์ (terminal ปิด) = ปฏิเสธ (fail-closed)
r = P.evaluate("computer_click", CLICK, pol(), fg={})
check("unknown fg + scope จำกัด = deny", r["allow"] is False, r)

# 2) fg ว่าง + เปิดกว้างทุกแอป = อนุญาต
r = P.evaluate("computer_click", CLICK, pol(scope=dict(OPEN)), fg={})
check("unknown fg + scope เปิดกว้าง = allow", r["allow"] is True, r)

# 3) terminal จริง + terminal ปิด = ปฏิเสธ (พฤติกรรมเดิม)
r = P.evaluate("computer_click", CLICK, pol(), fg=dict(TERM_FG))
check("terminal fg + terminal ปิด = deny", r["allow"] is False, r)

# 4) terminal จริง + เปิด terminal = อนุญาต
sc = dict(P.SCOPE_DEFAULTS)
sc["terminal"] = True
r = P.evaluate("computer_click", CLICK, pol(scope=sc), fg=dict(TERM_FG))
check("terminal fg + terminal เปิด = allow", r["allow"] is True, r)

# 5) เครื่องมืออ่านจอไม่โดนเกทแอป (แค่ต้องมี capability)
r = P.evaluate("computer_screenshot", {}, pol(), fg={})
check("screenshot + fg ว่าง = allow", r["allow"] is True, r)

# 6) ปิด mouse capability = คลิกไม่ได้แม้ fg เปิดกว้าง
sc = dict(OPEN)
sc["mouse"] = False
r = P.evaluate("computer_click", CLICK, pol(scope=sc), fg=dict(TERM_FG))
check("mouse ปิด = deny", r["allow"] is False, r)

# 7) deny list ชนะ (พฤติกรรมเดิม)
sc = dict(OPEN)
sc["apps_deny"] = ["windowsterminal"]
r = P.evaluate("computer_click", CLICK, pol(scope=sc), fg=dict(TERM_FG))
check("apps_deny ชนะ", r["allow"] is False, r)

# 8) level off = ปิดหมด (พฤติกรรมเดิม)
r = P.evaluate("computer_screenshot", {}, pol(level="off"), fg={})
check("level off = deny", r["allow"] is False, r)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL PERMISSIONS TESTS PASSED")
