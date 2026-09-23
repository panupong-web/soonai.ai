# -*- coding: utf-8 -*-
"""Regression: MCP ผ่าน Streamable HTTP + auto-include ใน payload ทุกเทิร์น

พิสูจน์ว่าระบบ MCP "ใช้ได้จริงทุก session":
- MCPHttpClient คุยกับ HTTP server จริงบนเครื่อง (ในเทสต์ = mock server ใน thread)
  ครอบทั้งสองแบบที่ streamable HTTP ตอบได้: application/json และ text/event-stream (SSE)
- initialize → เก็บ Mcp-Session-Id → ส่งกลับทุก request → close() = DELETE
- custom headers (Authorization) ส่งถึง server จริง · error ทั้ง HTTP/JSON-RPC อ่านออก
- client_for_spec เลือก transport ถูก (url = HTTP, command = stdio)
- expand_mcp_spec ขยาย placeholder ใน headers (${cwd}) ได้เหมือน args/env
- MCPHub.add_server_spec บันทึก url+headers ลง mcp.json แล้วต่อ/เรียก tool ได้จริง
- agent_tools ส่ง MCP tools เข้า payload ตั้งแต่รอบแรกของทุกเทิร์นเมื่อมี server
  เปิดอยู่ (ไม่ต้องรอโมเดลเรียก mcp_tools ก่อน) — และหยุดรวมเมื่อไม่มี/บังคับปิด
- mcp_catalog.json มี tinyfish (stdio ผ่าน mcp-remote) + entry แบบ url (HTTP ตรง)

ไม่แตะเน็ต (mock เป็น 127.0.0.1) · ไม่แตะ mcp.json จริง (ใช้ temp path)
"""
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import mcp_client as MC  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="soonai-mcphttp-"))
FAILS = []

class OversizedResponse:
    """Minimal urlopen response used to verify the HTTP body limit."""
    headers = {"Content-Length": str(MC.MAX_HTTP_RESPONSE_BYTES + 1),
               "Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return b"{}"


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


def hget(d, k):
    """ดึง header แบบไม่สนตัวพิมพ์ (http.client บางเวอร์ชัน normalize ต่างกัน)"""
    for kk, vv in (d or {}).items():
        if kk.lower() == k.lower():
            return vv
    return None




raw_defs = [{"type": "function", "function": {"name": "mcp__x__read",
    "description": "D" * 1000, "parameters": {"type": "object", "title": "drop",
    "properties": {"path": {"type": "string", "description": "P" * 500,
                              "default": "drop"}}, "required": ["path"]}}}]
compact_defs = MC.compact_tool_defs(raw_defs)
check("compact MCP schema รักษาชื่อและ required",
      compact_defs[0]["function"]["name"] == "mcp__x__read"
      and compact_defs[0]["function"]["parameters"]["required"] == ["path"])
check("compact MCP schema ลด metadata/description",
      len(json.dumps(compact_defs, ensure_ascii=False)) < len(json.dumps(raw_defs, ensure_ascii=False))
      and "title" not in json.dumps(compact_defs, ensure_ascii=False)
      and "default" not in json.dumps(compact_defs, ensure_ascii=False))
check("MCP ${env:NAME} ขยายตอน runtime",
    "${env:SOONAI_TEST_SECRET}" not in MC.expand_mcp_value(
        "token=${env:SOONAI_TEST_SECRET}")
    and MC.expand_mcp_value("token=${env:SOONAI_TEST_SECRET}").startswith("token="))


# ---------- mock MCP server แบบ streamable HTTP (ใน thread) ----------
class MockMCPHandler(BaseHTTPRequestHandler):
    methods = []        # ลำดับ method ที่ได้รับ
    headers_seen = {}    # method -> headers ของ request สุดท้าย
    deletes = []         # headers ของ DELETE ทุกครั้ง

    def log_message(self, *a):
        pass

    def _send(self, obj, sse=False, sid=None, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        if sid:
            self.send_header("Mcp-Session-Id", sid)
        if sse:
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"event: message\ndata: " + body + b"\n\n")
        else:
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/mcp", "/sse"):
            self.send_error(404, "not an mcp endpoint")
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads((self.rfile.read(n) if n else b"{}").decode("utf-8"))
        except Exception:
            req = {}
        m = req.get("method", "")
        type(self).methods.append(m)
        type(self).headers_seen[m] = dict(self.headers)
        sse = self.path == "/sse"
        if "id" not in req:                      # notification (notifications/initialized)
            self.send_response(202)
            self.end_headers()
            return
        rid = req.get("id")
        if m == "initialize":
            self._send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                "serverInfo": {"name": "mockhttp", "version": "1.0"}}},
                sse=sse, sid="sess-1")
        elif m == "tools/list":
            self._send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                {"name": "echo", "description": "echo กลับ",
                 "inputSchema": {"type": "object", "properties": {}}}]}}, sse=sse)
        elif m == "tools/call":
            args = (req.get("params") or {}).get("arguments") or {}
            self._send({"jsonrpc": "2.0", "id": rid, "result": {"content": [
                {"type": "text", "text": f"echo:{args.get('x', '')}"}]}}, sse=sse)
        else:
            self._send({"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32601, "message": "ไม่รู้จัก method"}},
                       sse=sse)

    def do_DELETE(self):
        type(self).deletes.append(dict(self.headers))
        self.send_response(204)
        self.end_headers()


srv = ThreadingHTTPServer(("127.0.0.1", 0), MockMCPHandler)
PORT = srv.server_address[1]
BASE = f"http://127.0.0.1:{PORT}"
threading.Thread(target=srv.serve_forever, daemon=True).start()

try:
    # ---------- 0) oversized HTTP response is rejected before body processing ----------
    original_urlopen = MC.urllib.request.urlopen
    try:
        MC.urllib.request.urlopen = lambda *args, **kwargs: OversizedResponse()
        try:
            MC.MCPHttpClient("http://oversized.invalid/mcp").request("tools/list", {})
            check("HTTP response ใหญ่เกิน limit = MCPError", False)
        except MC.MCPError as e:
            check("HTTP response ใหญ่เกิน limit = MCPError",
                  "ใหญ่เกินขนาด" in str(e), str(e))
    finally:
        MC.urllib.request.urlopen = original_urlopen

    # ---------- 1) client ตรง: JSON mode ----------
    c = MC.MCPHttpClient(BASE + "/mcp", {"Authorization": "Bearer t1"},
                         label="web")
    info = c.connect(timeout=10)
    check("connect ผ่าน streamable HTTP จริง (JSON mode)",
          info.get("name") == "mockhttp", info)
    hi = MockMCPHandler.headers_seen.get("initialize", {})
    check("ส่ง Accept = application/json, text/event-stream",
          "application/json" in (hget(hi, "Accept") or "") and
          "text/event-stream" in (hget(hi, "Accept") or ""), hget(hi, "Accept"))
    check("ส่ง Content-Type = application/json",
          "application/json" in (hget(hi, "Content-Type") or ""),
          hget(hi, "Content-Type"))
    check("ส่ง custom headers (Authorization) ถึง server",
          hget(hi, "Authorization") == "Bearer t1", hget(hi, "Authorization"))
    tools = c.list_tools(timeout=10)
    check("list_tools ได้เครื่องมือจาก server จริง",
          [t.get("name") for t in tools] == ["echo"], tools)
    check("ส่ง Mcp-Session-Id กลับทุก request หลัง initialize",
          hget(MockMCPHandler.headers_seen.get("tools/list"), "Mcp-Session-Id")
          == "sess-1", MockMCPHandler.headers_seen.get("tools/list"))
    out = c.call_tool("echo", {"x": "1"}, timeout=10)
    check("call_tool คืนผลจริง", "echo:1" in str(out), out)
    try:
        c.request("bogus/method", {}, timeout=5)
        check("JSON-RPC error โยน MCPError", False)
    except MC.MCPError as e:
        check("JSON-RPC error อ่านออก (ข้อความไทยจาก server ผ่านถึง)",
              "ไม่รู้จัก method" in str(e), str(e))
    c.close()
    check("close() = DELETE + Mcp-Session-Id ถึง server",
          len(MockMCPHandler.deletes) == 1 and
          hget(MockMCPHandler.deletes[0], "Mcp-Session-Id") == "sess-1",
          MockMCPHandler.deletes[:1])

    # ---------- 2) SSE mode (server ตอบ text/event-stream) ----------
    cs = MC.MCPHttpClient(BASE + "/sse")
    infos = cs.connect(timeout=10)
    toolss = cs.list_tools(timeout=10)
    check("รองรับ server ที่ตอบเป็น SSE (text/event-stream)",
          infos.get("name") == "mockhttp" and
          [t.get("name") for t in toolss] == ["echo"], (infos, toolss))
    cs.close()

    # ---------- 3) HTTP ผิด endpoint = ข้อความชี้สาเหตุ ----------
    c4 = MC.MCPHttpClient(BASE + "/nope")
    try:
        c4.connect(timeout=5)
        check("404 = MCPError ที่บอกว่าไม่ใช่ MCP endpoint", False)
    except MC.MCPError as e:
        check("404 = MCPError ที่บอกว่าไม่ใช่ MCP endpoint",
              "404" in str(e), str(e))

    # ---------- 4) client_for_spec เลือก transport ถูก ----------
    check("client_for_spec: url = MCPHttpClient",
          isinstance(MC.client_for_spec({"url": BASE + "/mcp"}), MC.MCPHttpClient))
    check("client_for_spec: command = MCPClient (stdio เดิม)",
          isinstance(MC.client_for_spec({"command": "python"}), MC.MCPClient))

    # ---------- 5) expand_mcp_spec: headers + placeholder ----------
    ex = MC.expand_mcp_spec({"url": "http://x/mcp",
                             "headers": {"X-Base": "p=${cwd}"},
                             "args": ["${cwd}"], "env": {"E": "e-${cwd}"}})
    check("ขยาย ${cwd} ใน headers ได้เหมือน args/env",
          "${cwd}" not in ex["headers"]["X-Base"] and
          "${cwd}" not in ex["args"][0] and "${cwd}" not in ex["env"]["E"],
          ex)

    # ---------- 6) ระดับ hub: add_server_spec (url) + เรียก tool จริง ----------
    hub_path = TMP / "mcp_http.json"
    h = MC.MCPHub(path=hub_path)
    msg = h.add_server_spec("web", {"url": BASE + "/mcp",
                                    "headers": {"Authorization": "Bearer t1"}})
    check("add_server_spec (url/headers) = OK", str(msg).startswith("OK"), msg)
    disk = json.loads(hub_path.read_text(encoding="utf-8"))
    sp = disk.get("servers", {}).get("web", {})
    check("บันทึก url + headers ลง mcp.json จริง",
          sp.get("url") == BASE + "/mcp" and
          sp.get("headers", {}).get("Authorization") == "Bearer t1", sp)
    st = h.status()
    check("hub ต่อ HTTP server + นับ tools ได้",
          st.get("web", {}).get("connected") and st["web"].get("tools") == 1, st)
    dnames = sorted(d["function"]["name"] for d in h.tools())
    check("defs ชื่อ mcp__web__echo", dnames == ["mcp__web__echo"], dnames)
    out2 = h.call("mcp__web__echo", {"x": "42"})
    check("เรียก tool ผ่าน hub ได้จริง", "echo:42" in str(out2), out2)
    h.close_all()

    # ---------- 7) catalog: มีทั้ง stdio และ url entries ----------
    import soonai as S  # noqa: E402
    cat = S.mcp_catalog_load()
    check("catalog อ่านได้ + มี tinyfish (mcp-remote/stdio)", "tinyfish" in cat,
          list(cat)[:8])
    check("มี entry แบบ url (streamable HTTP ตรง ไม่ต้อง node/npx)",
          any(isinstance(v, dict) and v.get("url") for v in cat.values()))
    check("ไม่มี key ซ้ำใน catalog (json โหลดแล้วได้ครบ)",
          len(cat) >= 10)

    # ---------- 8) auto-include: MCP tools เข้า payload ทุกเทิร์น ----------
    fake = {"type": "function", "function": {
        "name": "mcp__srv__echo", "description": "",
        "parameters": {"type": "object", "properties": {}}}}
    old = (S._MCP_DEFS_CACHE["defs"], S._MCP_ON["names"],
           S._MCP_LAZY["loaded"], S.mcp_hub_for_tools)
    try:
        S.mcp_hub_for_tools = lambda: [fake]
        S._MCP_ON["names"] = ["srv"]
        S._MCP_LAZY["loaded"] = False
        S._MCP_DEFS_CACHE["defs"] = None
        names = {d["function"]["name"] for d in S.agent_tools()}
        check("payload รอบแรกมี MCP tools เมื่อมี server เปิดอยู่ (ไม่ต้องรอ mcp_tools)",
              "mcp__srv__echo" in names)
        check("tools ในเครื่องยังอยู่ครบ + MCP ต่อท้าย",
              len(names) == len(S.AGENT_TOOLS) + 1, len(names))
        S._MCP_DEFS_CACHE["defs"] = None
        n2 = {d["function"]["name"] for d in S.agent_tools(include_mcp=False)}
        check("include_mcp=False = ไม่รวม MCP (ใช้บังคับในหน้าจอ)",
              "mcp__srv__echo" not in n2)
        S._MCP_DEFS_CACHE["defs"] = None
        S._MCP_ON["names"] = []
        n3 = {d["function"]["name"] for d in S.agent_tools()}
        check("ไม่มี server เปิด = ไม่ต่อ MCP ไม่เปลือง token",
              "mcp__srv__echo" not in n3)
    finally:
        (S._MCP_DEFS_CACHE["defs"], S._MCP_ON["names"],
         S._MCP_LAZY["loaded"], S.mcp_hub_for_tools) = old

    # ---------- 9) _mcp_servers_on: กรอง enabled + cache ต่อ process ----------
    class FakeHub:
        def servers(self):
            return {"a": {"enabled": True}, "b": {"enabled": False}}

    old2 = (S._MCP_OK, S._MCP_HUB, S._MCP_ON["names"])
    try:
        S._MCP_OK = True
        S._MCP_HUB = FakeHub()
        S._MCP_ON["names"] = None
        check("_mcp_servers_on เห็น server ที่เปิดอยู่", S._mcp_servers_on() is True)
        check("กรองเฉพาะ enabled + cache ไว้ไม่ยิงไฟล์ซ้ำ",
              S._MCP_ON["names"] == ["a"], S._MCP_ON["names"])
        S._MCP_ON["names"] = []
        check("cache ว่าง = ไม่มี server → False",
              S._mcp_servers_on() is False)
    finally:
        S._MCP_OK, S._MCP_HUB, S._MCP_ON["names"] = old2
finally:
    srv.shutdown()
    srv.server_close()

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL MCP HTTP TESTS PASSED")
