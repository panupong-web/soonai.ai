# -*- coding: utf-8 -*-
"""Regression: MCP server จริงผ่าน stdio — พิสูจน์ว่าโหมด debug จับ "การหลุดของ server" ได้

ต่างจากเทสต์อื่น: อันนี้ **สตาร์ทโปรเซสจริง** (สตับ MCP server ตัวเล็กที่เขียนขึ้นในเทมเพอร์รารี)
คุยผ่าน stdio จริง แล้วสั่งให้มันตายแบบต่าง ๆ เพื่อดูว่า debug log บันทึกหรือไม่

สิ่งที่ล็อกไว้:
- เส้นทางปกติ (initialize → tools/list) ทำงานกับ server จริงได้ + **ไม่มีร่องรอยเด้ง** (ไม่มีสัญญาณเท็จ)
- server ตายเองหลัง initialize → reader thread จบที่ EOF ซึ่งเดิมเงียบสนิท ตอนนี้ต้องมีร่องรอย
  พร้อมชื่อ server/คำสั่ง + exit code (แยกได้ว่า server ตัวไหนหลุด)
- server หลุดตั้งแต่ตอน initialize (ตายทันที) → ได้ {} แบบเดิม แต่มีร่องรอยให้ตาม
- **close() ที่ตั้งใจ = ต้องไม่ถูกบันทึกว่า "หลุด"** (กัน false positive ตอนปิดโปรแกรม)
- บรรทัดขยะบน stdout (server พิมพ์ log ปน) ไม่ทำให้หลุด และไม่ถูกบันทึกทีละบรรทัด
- stderr ของ server ถูกเก็บไว้จริง (พิสูจน์ว่าสตับเป็นโปรเซสจริงและ đường stderr ทำงาน)
- สรุปของโหมด debug (startup_lines/summary) เห็นจุดนี้ด้วย
ทุกโปรเซสปิดจนหมด · ไม่แตะเน็ต · ไม่แตะไฟล์จริงของเครื่อง
"""
import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

TMP = Path(tempfile.mkdtemp(prefix="soonai-mcptest-"))
LOG = TMP / "debug.log"
os.environ["SOONAI_DEBUG_LOG"] = str(LOG)
os.environ["SOONAI_CRASH_LOG"] = str(TMP / "crash.log")
os.environ["SOONAI_DEBUG"] = "1"
os.environ.pop("SOONAI_DEBUG_MAX_BYTES", None)
os.environ.pop("SOONAI_DEBUG_BACKUPS", None)

import debug as D  # noqa: E402
import mcp_client as MC  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------- สตับ MCP server (โปรเซสจริง) ----------
STUB = TMP / "stub_mcp_server.py"
STUB.write_text(textwrap.dedent('''
    # -*- coding: utf-8 -*-
    """สตับ MCP server ตัวเล็ก — พูด JSON-RPC ผ่าน stdio จริง (ใช้ทดสอบการหลุด)"""
    import json
    import os
    import sys
    import threading

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"


    def note(msg):
        sys.stderr.write(msg + "\\n")
        sys.stderr.flush()


    def send(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\\n")
        sys.stdout.flush()


    note("stub เริ่มทำงาน mode=" + MODE)
    if MODE == "noise":
        # server บางตัวพิมพ์ log ปนออกมา stdout (ไม่ใช่ JSON-RPC)
        sys.stdout.write("ของจริงมักมีบรรทัดแบบนี้ปนมา\\n")
        sys.stdout.flush()
    if MODE == "silent-exit":
        note("ปิดตัวทันทีก่อนตอบ initialize")
        os._exit(0)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if MODE == "noise":
            sys.stdout.write("ยังพิมพ์ log ปนอยู่\\n")
            sys.stdout.flush()
        try:
            msg = json.loads(line)
        except Exception:
            continue
        method = msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg.get("id"), "result": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "serverInfo": {"name": "stub", "version": "9.9"}}})
            if MODE == "self-exit":
                # ตายเองหลังตอบ initialize — จำลอง server ที่ crash
                threading.Timer(0.3, lambda: os._exit(3)).start()
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": msg.get("id"), "result": {"tools": [
                {"name": "echo", "description": "สวัสดี", "inputSchema": {"type": "object"}}]}})
        elif "id" in msg:
            send({"jsonrpc": "2.0", "id": msg.get("id"), "result": {}})
''').lstrip(), encoding="utf-8")


def reset_log():
    for p in [LOG] + [D._part(LOG, i) for i in range(1, 5)]:
        try:
            p.unlink()
        except OSError:
            pass


def wait_for(pred, timeout=8.0, step=0.05):
    end = time.time() + timeout
    while True:
        if pred():
            return True
        if time.time() >= end:
            return pred()
        time.sleep(step)


def client_for(mode, label=""):
    return MC.MCPClient(command=sys.executable, args=[str(STUB), mode],
                        env={"SOONAI_MCP_STUB": mode}, label=label)


def drops():
    """รายการที่บันทึกว่าอ่าน stdout ของ server จบลง"""
    return [e for e in D.entries() if e["where"] == "mcp_client.py:_reader"]


def raises(fn):
    """คืน True เมื่อ fn โยน exception (ชื่อให้อ่านตรงความหมาย)"""
    try:
        fn()
    except Exception:
        return True
    return False


# ---------- 1) เส้นทางปกติกับ server จริง ----------
reset_log()
c1 = client_for("normal")
info1 = c1.connect(timeout=15)
tools = c1.list_tools(timeout=10)
time.sleep(0.2)
c1.close()
time.sleep(0.4)
check("สตาร์ท server จริงผ่าน stdio + initialize ผ่าน",
      isinstance(info1, dict) and info1.get("name") == "stub", info1)
check("tools/list ได้เครื่องมือจาก server จริง",
      [t.get("name") for t in tools] == ["echo"], tools)
check("stderr ของ server ถูกเก็บไว้ (เป็นโปรเซสจริง)",
      any("stub เริ่มทำงาน" in ln for ln in c1._stderr_log), list(c1._stderr_log))
check("เส้นทางปกติ = ไม่มีร่องรอยเลย (ไม่มีสัญญาณเท็จ)", D.entries() == [], D.entries()[:2])


# ---------- 2) บรรทัดขยะบน stdout ----------
reset_log()
c2 = client_for("noise")
info2 = c2.connect(timeout=15)
tools2 = c2.list_tools(timeout=10)
time.sleep(0.2)
c2.close()
time.sleep(0.4)
check("server ที่พิมพ์ขยะปน stdout ยังเชื่อมต่อได้", info2.get("name") == "stub", info2)
check("ขยะไม่ทำให้เครื่องมือหาย", [t.get("name") for t in tools2] == ["echo"])
check("ขยะทีละบรรทัดไม่ถูกบันทึก (สัญญาณยังคม)", D.entries() == [], D.entries()[:2])


# ---------- 3) server ตายเองหลัง initialize = การหลุดจริง ----------
reset_log()
c3 = client_for("self-exit")
info3 = c3.connect(timeout=15)
found = wait_for(lambda: any("หลุดเอง" in e["note"] for e in drops()))
check("initialize ผ่านก่อนที่ server จะตาย", info3.get("name") == "stub", info3)
check("server ตายเอง = debug log จับได้ (เดิมเงียบสนิท)", found, D.entries())
e3 = (drops() or [{}])[0]
check("บอกได้ว่า server ตัวไหนหลุด (คำสั่ง+อาร์กิวเมนต์)",
      "stub_mcp_server.py" in e3.get("note", "") and "self-exit" in e3.get("note", ""),
      e3.get("note"))
check("ความหมายของเหตุการณ์มาก่อนพาธ (บรรทัดสรุปจึงอ่านออก)",
      e3.get("note", "").startswith("MCP server หลุดเอง"), e3.get("note"))
check("บอก exit code ของ server ที่ตาย", "exit code 3" in e3.get("note", ""), e3.get("note"))
check("การหลุดแบบนี้เป็น note ไม่ใช่ exception (ไม่มี traceback ปลอม)",
      e3.get("exc") == "", e3)
check("สรุปในโหมด debug เห็นจุดนี้",
      any("mcp_client.py:_reader" in ln for ln in D.startup_lines()), D.startup_lines())
check("เรียก request หลัง server ตาย = error ที่อ่านออก",
      raises(lambda: c3.request("tools/list", {}, timeout=1)))
c3.close()


# ---------- 4) หลุดตั้งแต่ตอน initialize ----------
reset_log()
c4 = client_for("silent-exit")
info4 = c4.connect(timeout=10)
check("server หลุดตอน initialize = ยังคืนค่าไม่พังแบบเดิม",
      isinstance(info4, dict) and not info4.get("name"), info4)
check("หลุดตอน initialize = มีร่องรอยให้ตาม", wait_for(lambda: drops() != []), D.entries())
check("log ไม่ว่าง (มีอย่างน้อยเหตุการณ์หลุด)", D.entries() != [])
rows = {r["where"]: r["count"] for r in D.summary(0)}
check("สรุปรวบยอดเห็นการหลุดของ MCP server",
      rows.get("mcp_client.py:_reader", 0) >= 1, rows)
c4.close()


# ---------- 5) ปิดเอง (close) = ต้องไม่ถูกกล่าวหาว่าหลุด ----------
reset_log()
c5 = client_for("normal")
c5.connect(timeout=15)
time.sleep(0.2)
c5.close()
time.sleep(0.6)
check("close() ที่ตั้งใจ = ไม่มีร่องรอย 'หลุด' เลย (กัน false positive)",
      D.entries() == [], D.entries()[:2])


# ---------- 6) หลุดแล้วเชื่อมต่อใหม่ได้ + ป้ายชื่อ server ใน log ----------
reset_log()
c6 = client_for("self-exit", label="fs")     # จำลองชื่อ server ใน mcp.json
c6.connect(timeout=15)
wait_for(lambda: drops() != [])
check("log บอกป้ายชื่อ server ด้วย (แยกได้แม้ใช้คำสั่งเดียวกัน)",
      any("— fs (" in e.get("note", "") for e in drops()), [e.get("note") for e in drops()])
try:
    c6.request("tools/list", {}, timeout=1)
except Exception:
    pass
info6 = c6.connect(timeout=15)          # สตาร์ทใหม่ (กระบวนการเดิมตายไปแล้ว)
check("หลังหลุดสามารถ connect ใหม่ได้จริง", info6.get("name") == "stub", info6)
c6.close()
time.sleep(0.4)

# ---------- 7) ระดับ hub (mcp.json จริง) — หลาย server พร้อมกัน ----------
import json  # noqa: E402

hub_cfg = TMP / "mcp_hub.json"
hub_cfg.write_text(json.dumps({"servers": {
    "fs": {"command": sys.executable, "args": [str(STUB), "self-exit"],
           "env": {}, "enabled": True},
    "calc": {"command": sys.executable, "args": [str(STUB), "normal"],
             "env": {}, "enabled": True},
}}, ensure_ascii=False), encoding="utf-8")
reset_log()
hub = MC.MCPHub(path=hub_cfg)
hub_defs = hub.refresh(force=True)
names = sorted(d["function"]["name"] for d in hub_defs)
check("hub ต่อ server จริงจาก mcp.json พร้อมกันได้",
      names == ["mcp__calc__echo", "mcp__fs__echo"], names)
hub_st = hub.status()
check("hub รายงานว่าต่อติด + จำนวน tools",
      hub_st["calc"]["connected"] and hub_st["calc"]["tools"] == 1, hub_st)
check("hub: เส้นทางปกติยังไม่มีร่องรอย", D.entries() == [], D.entries()[:2])
check("hub: server ที่ตายเองถูกบันทึกพร้อมป้ายชื่อ 'fs'",
      wait_for(lambda: any("— fs (" in e.get("note", "") for e in drops())),
      [e.get("note") for e in D.entries()[:3]])
check("hub: server ที่ยังดี ('calc') ไม่ถูกกล่าวถึง",
      not any("— calc (" in e.get("note", "") for e in D.entries()))
hub.close_all()
time.sleep(0.4)
check("hub: close_all() ตอนปิดโปรแกรม = ไม่มีร่องรอยหลุดเพิ่ม",
      sum(1 for e in D.entries() if "หลุดเอง" in e.get("note", "")) == 1,
      [e.get("note") for e in D.entries()])

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL MCP STDIO TESTS PASSED")
