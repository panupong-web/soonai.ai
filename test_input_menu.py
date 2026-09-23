# -*- coding: utf-8 -*-
"""เมนู / ต้องแสดง "เหนือ" แถบพิมพ์ (แทรก in-flow ในกรอบ) ไม่ใช่ Float ห้อยลงล่าง
- root layout = HSplit ไม่ใช่ FloatContainer · ไม่มี Float/ycursor เหลือใน build_input_bar
- ลำดับในกรอบ: หัวกรอบ → เมนู CompletionsMenu → แถบพิมพ์ (เมนูอยู่เหนือกว่าเสมอ)
- probe จริง (pipe input + PlainTextOutput ไม่แตะเทอร์มินัล): พิมพ์ "/" แล้วแถวเมนู
  ต้องมี index น้อยกว่าแถวแถบพิมพ์ · ไม่พิมพ์อะไรกรอบต้องเป็น 4 แถว · escape ปิดกลับ 4 แถว
ไม่แตะเน็ต/ไม่แตะ config (จอจำลอง 40x80 ในหน่วยความจำ)
"""
import asyncio
import inspect
import io
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

from prompt_toolkit import Application  # noqa: E402
from prompt_toolkit.application import create_app_session  # noqa: E402
from prompt_toolkit.data_structures import Size  # noqa: E402
from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.layout.containers import Float, VSplit  # noqa: E402
from prompt_toolkit.layout.controls import BufferControl  # noqa: E402
from prompt_toolkit.layout.menus import CompletionsMenu  # noqa: E402
from prompt_toolkit.output.plain_text import PlainTextOutput  # noqa: E402
from prompt_toolkit.styles import Style  # noqa: E402

import ui_render as U  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


def walk(container):
    """เดินต้นไม้ layout ทั้งหมด"""
    yield container
    for child in getattr(container, "children", []):
        yield from walk(child)


def has_buffer(container):
    """มี BufferControl ฝังอยู่ใน subtree นี้ไหม
    (BufferControl อยู่ที่ Window.content ไม่ใช่ children — ต้องมองทั้งสองที่)"""
    for c in walk(container):
        if isinstance(c, BufferControl):
            return True
        if isinstance(getattr(c, "content", None), BufferControl):
            return True
    return False


# ---------- 1) โครงสร้าง layout: เมนูเป็น in-flow อยู่ "ก่อน" แถบพิมพ์
layout, buf, kb = U.build_input_bar(None, "openrouter / test-model")
root = layout.container
check("root = HSplit (ไม่ใช่ FloatContainer)",
      type(root).__name__ == "HSplit", type(root).__name__)
kids = list(getattr(root, "children", []))
menu_i = next((i for i, k in enumerate(kids) if isinstance(k, CompletionsMenu)), -1)
input_i = next((i for i, k in enumerate(kids)
                if isinstance(k, VSplit) and has_buffer(k)), -1)
check("มีเมนู CompletionsMenu ในลำดับ", menu_i >= 0, f"kids={len(kids)}")
check("มีแถบพิมพ์ในลำดับ", input_i >= 0, f"kids={len(kids)}")
check("เมนูอยู่ก่อนแถบพิมพ์ = อยู่เหนือกว่า",
      0 <= menu_i < input_i, f"menu={menu_i} input={input_i}")
check("หัวกรอบอยู่บนสุด เมนูอยู่ใต้หัวกรอบ", menu_i == 1, f"menu={menu_i}")

check("ไม่มี Float เลยในต้นไม้ layout",
      not any(isinstance(c, Float) for c in walk(root)))
src = inspect.getsource(U.build_input_bar)
check("ไม่เหลือ ycursor/FloatContainer ใน build_input_bar (กัน regression)",
      "ycursor" not in src and "FloatContainer" not in src)

# ---------- 2) probe จริง: ยิงแอป prompt_toolkit แล้วอ่านจอบนหน่วยความจำ
class _Sim(PlainTextOutput):
    """จอจำลอง 40x80 — ไม่แตะเทอร์มินัลจริง"""

    def get_size(self):
        return Size(rows=40, columns=80)

    def get_rows_below_cursor_position(self):
        return 30


def _rows(app):
    """คืน {row_index: text} ของเฟรมล่าสุด"""
    screen = app.renderer.last_rendered_screen
    if screen is None:
        return {}
    out = {}
    for y in sorted(screen.data_buffer.keys()):
        row = screen.data_buffer[y]
        out[y] = "".join((row[x].char if x in row else " ")
                         for x in range(0, 78))
    return out


async def _probe():
    layout2, buf2, kb2 = U.build_input_bar(None, "openrouter / test-model")
    with create_pipe_input() as pipe:
        with create_app_session(input=pipe, output=_Sim(io.StringIO())):
            app = Application(layout=layout2, key_bindings=kb2,
                              style=Style.from_dict(U.INPUT_STYLE),
                              full_screen=False, erase_when_done=True)

            async def driver():
                for _ in range(50):  # รอแอปเริ่ม (ไม่ต้องพึ่ง timing เป๊ะ)
                    await asyncio.sleep(0.1)
                    if getattr(app, "is_running", False):
                        break
                await asyncio.sleep(0.3)
                r0 = _rows(app)
                check("ไม่พิมพ์อะไร = กรอบ 4 แถว (เมนูซ่อน สูง 0)",
                      any("└" in t for t in r0.values())
                      and any("│>" in t for t in r0.values()),
                      repr(list(r0.values())[:4]))
                check("ตอนนี้ยังไม่มีเมนู /model",
                      not any("/model" in t for t in r0.values()))

                pipe.send_text("/")
                await asyncio.sleep(0.7)
                r1 = _rows(app)
                input_rows = [y for y, t in r1.items() if "> /" in t]
                menu_rows = [y for y, t in r1.items() if "/model" in t]
                check("พิมพ์ / แล้วมีเมนู /model ขึ้น", bool(menu_rows),
                      repr(list(r1.values())[:8]))
                check("พิมพ์ / แล้วมีแถบพิมพ์", bool(input_rows),
                      repr(list(r1.values())[:8]))
                if menu_rows and input_rows:
                    check("แถวเมนู < แถวพิมพ์ = เมนูอยู่เหนือ (ไม่ห้อยล่าง)",
                          min(menu_rows) < min(input_rows),
                          f"menu={min(menu_rows)} input={min(input_rows)}")
                    check("เมนูอยู่ใต้หัวกรอบ (หัวกรอบ = row 0)",
                          min(menu_rows) >= 1, f"menu={min(menu_rows)}")

                pipe.send_text("\x1b")  # escape ปิดเมนู
                await asyncio.sleep(1.6)
                r2 = _rows(app)
                check("escape ปิดเมนู = กรอบกลับ 4 แถว",
                      any("└" in t for t in r2.values())
                      and any("/model" not in t for t in r2.values())
                      and not [y for y, t in r2.items() if "/provider" in t],
                      repr(list(r2.values())[:6]))
                try:
                    if app.is_running:
                        app.exit(result="done")
                except Exception:
                    pass

            task = asyncio.ensure_future(driver())
            try:
                await asyncio.wait_for(app.run_async(), 20)
            except Exception as e:
                check("แอป probe รันจนจบ", False, f"{type(e).__name__}: {e}")
            try:
                await asyncio.wait_for(task, 5)
            except Exception as e:
                check("driver probe จบ", False, f"{type(e).__name__}: {e}")


try:
    asyncio.run(asyncio.wait_for(_probe(), 30))
    check("probe จบไม่ค้าง", True)
except Exception as e:
    check("probe จบไม่ค้าง", False, f"{type(e).__name__}: {e}")

if FAILS:
    print(f"\nFAIL {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("\nALL PASSED")
