# -*- coding: utf-8 -*-
"""MCP client ขั้นต่ำคุยผ่าน stdio (JSON-RPC 2.0) — ใช้ stdlib ล้วน ไม่ต้องลงแพ็กเกจเพิ่ม.

รองรับ MCP servers ทั่วไป (npx / node / python): initialize → tools/list → tools/call
"""
import itertools
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
MCP_FILE = Path(__file__).resolve().parent / "mcp.json"
DOWN_RETRY_SECS = 60


class MCPError(Exception):
    pass


def sanitize(name):
    """ทำชื่อให้ใช้เป็น function name ได้ (เหลือ A-Za-z0-9_)"""
    return re.sub(r"[^A-Za-z0-9_]", "_", str(name or "")) or "tool"


def mcp_tool_name(server, tool):
    return f"mcp__{sanitize(server)}__{sanitize(tool)}"


def split_mcp_name(qual):
    """แยก 'mcp__<server>__<tool>' → (server, tool)"""
    if not str(qual or "").startswith("mcp__"):
        return None, None
    rest = qual[len("mcp__"):]
    if "__" not in rest:
        return None, None
    server, tool = rest.split("__", 1)
    return server or None, tool or None


def expand_mcp_value(text, cwd=None):
    """ขยาย placeholder ในค่า config MCP (เหลืออย่างอื่นไว้เหมือนเดิม):
    ${cwd} = โฟลเดอร์ปัจจุบันตอน spawn (ตามโปรเจคที่เปิดอยู่)
    ${home} / ~/ = โฟลเดอร์ผู้ใช้"""
    s = str(text or "")
    if "${cwd}" in s:
        try:
            base = cwd or os.getcwd()
        except Exception:
            base = ""
        s = s.replace("${cwd}", base)
    if "${home}" in s:
        s = s.replace("${home}", str(Path.home()))
    if s == "~" or s.startswith("~/") or s.startswith("~\\"):
        s = str(Path.home()) + s[1:]
    return s


def expand_mcp_spec(spec, cwd=None):
    """ขยาย placeholders ทั้ง command/args/env/cwd ของ server spec 1 ตัว
    เรียกตอน spawn ทุกครั้ง = server ได้ฐานตามโฟลเดอร์ที่รันอยู่ (ไม่ล็อกตาย)"""
    try:
        out = dict(spec or {})
    except Exception:
        return spec
    try:
        base = cwd or os.getcwd()
    except Exception:
        base = ""
    if out.get("command"):
        out["command"] = expand_mcp_value(out["command"], base)
    if isinstance(out.get("args"), list):
        out["args"] = [expand_mcp_value(a, base) if isinstance(a, str) else a
                       for a in out["args"]]
    if isinstance(out.get("env"), dict):
        out["env"] = {k: (expand_mcp_value(v, base) if isinstance(v, str) else v)
                      for k, v in out["env"].items()}
    if isinstance(out.get("cwd"), str) and out["cwd"]:
        out["cwd"] = expand_mcp_value(out["cwd"], base)
    return out


def _spawn_argv(command, args):
    """ประกอบ argv ให้รัน .cmd/.bat/.ps1 บน Windows ได้"""
    exe = shutil.which(command) or command
    argv = [exe] + list(args or [])
    if os.name == "nt":
        low = exe.lower()
        if low.endswith((".cmd", ".bat")):
            return ["cmd", "/d", "/s", "/c", subprocess.list2cmdline(argv)]
        if low.endswith(".ps1"):
            return ["powershell", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File"] + argv
    return argv


class MCPClient:
    """คุยกับ MCP server 1 ตัวผ่าน stdio (persistent, มี reader thread)"""

    def __init__(self, command, args=(), env=None, cwd=None):
        self.command, self.args = command, list(args or [])
        self.env, self.cwd = dict(env or {}), cwd
        self.proc = None
        self._ids = itertools.count(1)
        self._pending = {}
        self._lock = threading.Lock()
        self._stderr_log = deque(maxlen=30)
        self.server_info = {}

    def _reply_error(self, rid, code=-32601, message="Method not found"):
        try:
            self.proc.stdin.write(json.dumps(
                {"jsonrpc": "2.0", "id": rid,
                 "error": {"code": code, "message": message}}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except Exception:
            pass

    def _reader(self):
        try:
            for line in self.proc.stdout:
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                if not isinstance(msg, dict):
                    continue
                if "id" in msg and ("result" in msg or "error" in msg):
                    with self._lock:
                        ev = self._pending.pop(msg["id"], None)
                    if ev is not None:
                        ev["msg"] = msg
                        ev["event"].set()
                elif msg.get("method", "").startswith("notifications/"):
                    continue
                elif "method" in msg and "id" in msg:
                    self._reply_error(msg["id"])
        except Exception:
            pass
        finally:
            with self._lock:
                for ev in self._pending.values():
                    ev["event"].set()
                self._pending.clear()

    def _drain_stderr(self):
        try:
            for line in self.proc.stderr:
                self._stderr_log.append(line.rstrip())
        except Exception:
            pass

    def connect(self, timeout=25):
        if self.proc and self.proc.poll() is None:
            return self.server_info
        # MCP servers are separate, potentially third-party processes.  Do not
        # inherit API keys and unrelated user environment variables by default.
        safe_env_names = ("PATH", "PATHEXT", "SystemRoot", "WINDIR", "ComSpec",
                          "TEMP", "TMP", "USERPROFILE", "HOME", "APPDATA",
                          "LOCALAPPDATA", "LANG", "LC_ALL")
        env = {key: os.environ[key] for key in safe_env_names if key in os.environ}
        env.update(self.env)
        # บังคับลูกฝั่ง python พูด UTF-8 (กัน cp1252 บน Windows)
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            self.proc = subprocess.Popen(
                _spawn_argv(self.command, self.args),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", bufsize=1, cwd=self.cwd, env=env)
        except Exception as e:
            raise MCPError(f"สตาร์ทไม่ติด ({self.command}): {e}")
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        try:
            res = self.request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"roots": {"listChanged": False}},
                "clientInfo": {"name": "soonai", "version": "1.0"}}, timeout=timeout)
        except MCPError as e:
            tail = " | ".join(self._stderr_log)[:500]
            self.close()
            raise MCPError(f"{e}" + (f" — log: {tail}" if tail else ""))
        self.server_info = res.get("serverInfo", {}) if isinstance(res, dict) else {}
        try:
            self.proc.stdin.write(json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except Exception:
            pass
        return self.server_info

    def request(self, method, params=None, timeout=30):
        if not self.proc or self.proc.poll() is not None:
            raise MCPError("โปรเซส server ดับไปแล้ว")
        rid = next(self._ids)
        ev = {"event": threading.Event(), "msg": None}
        with self._lock:
            self._pending[rid] = ev
        payload = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except Exception as e:
            with self._lock:
                self._pending.pop(rid, None)
            raise MCPError(f"เขียน stdin ไม่ได้: {e}")
        if not ev["event"].wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise MCPError(f"หมดเวลา {timeout}s ({method})")
        msg = ev["msg"] or {}
        if "error" in msg:
            err = msg["error"]
            raise MCPError(f"{method}: {err.get('message', err)}")
        return msg.get("result", {})

    def list_tools(self, timeout=20):
        res = self.request("tools/list", {}, timeout=timeout)
        tools = res.get("tools", []) if isinstance(res, dict) else []
        return [t for t in tools if isinstance(t, dict) and t.get("name")]

    @staticmethod
    def flatten_content(result):
        """แปลง content blocks ของ tools/call เป็นข้อความ"""
        parts = []
        blocks = (result.get("content", []) if isinstance(result, dict) else []) or []
        for b in blocks:
            if not isinstance(b, dict):
                parts.append(str(b))
                continue
            t = b.get("type")
            if t == "text":
                parts.append(b.get("text", ""))
            elif t == "image":
                parts.append(f"[image {b.get('mimeType', '')} {len(b.get('data', ''))} chars]")
            elif t == "resource":
                r = b.get("resource", {})
                parts.append(f"[resource {r.get('uri', '')}]\n{r.get('text', '')}")
            else:
                parts.append(json.dumps(b, ensure_ascii=False))
        text = "\n".join(p for p in parts if p).strip()
        if isinstance(result, dict) and result.get("isError"):
            text = "ERROR: " + text
        return text or "(ว่าง)"

    def call_tool(self, name, arguments=None, timeout=120):
        res = self.request("tools/call", {"name": name, "arguments": arguments or {}},
                           timeout=timeout)
        return self.flatten_content(res)

    def close(self):
        try:
            p, self.proc = self.proc, None
            if p is None:
                return
            for fh in (p.stdin, p.stdout, p.stderr):
                try:
                    if fh:
                        fh.close()
                except Exception:
                    pass
            try:
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass


def load_mcp_config(path=None):
    try:
        d = json.loads(Path(path or MCP_FILE).read_text(encoding="utf-8"))
        servers = d.get("servers", {}) if isinstance(d, dict) else {}
        return {k: v for k, v in servers.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _atomic_write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(".%s.%s.%s.tmp" % (target.name, os.getpid(), threading.get_ident()))
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, target)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def save_mcp_config(servers, path=None):
    _atomic_write_text(path or MCP_FILE,
                       json.dumps({"servers": servers}, ensure_ascii=False, indent=2))


class MCPHub:
    """รวม MCP servers หลายตัว + cache รายชื่อ tools"""

    def __init__(self, path=None):
        self.path = Path(path or MCP_FILE)
        self._clients = {}
        self._lock = threading.Lock()
        self._defs = None      # [openai tool defs]
        self._meta = {}        # qualname -> {server, tool, description, readonly}
        self._status = {}      # server -> {enabled, connected, tools, error}
        self._down = {}        # server -> timestamp ที่พังล่าสุด

    # ---- config ----
    def servers(self):
        return load_mcp_config(self.path)

    def add_server(self, name, command, args=(), env=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name or ""):
            return "ERROR: ชื่อ server ใช้ได้แค่ A-Za-z0-9_-"
        if not command:
            return "ERROR: ต้องระบุ command"
        cfg = self.servers()
        cfg[name] = {"command": command, "args": list(args or []),
                     "env": dict(env or {}), "enabled": True}
        save_mcp_config(cfg, self.path)
        self.refresh(force=True)
        return f"OK: เพิ่ม MCP server '{name}' แล้ว"

    def remove_server(self, name):
        cfg = self.servers()
        if name not in cfg:
            return f"ERROR: ไม่มี server '{name}'"
        del cfg[name]
        save_mcp_config(cfg, self.path)
        with self._lock:
            c = self._clients.pop(name, None)
        if c:
            c.close()
        self.refresh(force=True)
        return f"OK: ลบ MCP server '{name}' แล้ว"

    def set_enabled(self, name, enabled):
        cfg = self.servers()
        if name not in cfg:
            return f"ERROR: ไม่มี server '{name}'"
        cfg[name]["enabled"] = bool(enabled)
        save_mcp_config(cfg, self.path)
        if not enabled:
            with self._lock:
                c = self._clients.pop(name, None)
            if c:
                c.close()
        self.refresh(force=True)
        return f"OK: {'เปิด' if enabled else 'ปิด'} MCP server '{name}' แล้ว"

    # ---- runtime ----
    def _client(self, server, spec, timeout=25):
        with self._lock:
            c = self._clients.get(server)
        if c and c.proc and c.proc.poll() is None:
            return c
        spec = expand_mcp_spec(spec)  # ${cwd} = โปรเจคที่เปิดอยู่ตอนนี้
        c = MCPClient(spec.get("command", ""), spec.get("args", []),
                      spec.get("env", {}), spec.get("cwd"))
        c.connect(timeout=timeout)
        with self._lock:
            self._clients[server] = c
        return c

    def _load_one(self, item):
        server, spec = item
        try:
            c = self._client(server, spec)
            tools = c.list_tools()
            return server, c.server_info, tools, ""
        except Exception as e:
            with self._lock:
                old = self._clients.pop(server, None)
            if old:
                old.close()
            self._down[server] = time.time()
            return server, {}, [], str(e)

    def refresh(self, force=False, budget=25):
        """ต่อ servers ที่เปิดอยู่แบบขนาน + cache tools คืน (defs, status)"""
        if self._defs is not None and not force:
            return self._defs
        cfg = self.servers()
        enabled = {k: v for k, v in cfg.items() if v.get("enabled", True)}
        now = time.time()
        todo = [(k, v) for k, v in enabled.items()
                if force or now - self._down.get(k, 0) > DOWN_RETRY_SECS]
        defs, meta, status = [], {}, {}
        for k, v in cfg.items():
            en = bool(v.get("enabled", True))
            st = {"enabled": en, "connected": False, "tools": 0, "error": ""}
            if not en:
                st["error"] = "ปิดอยู่"
            elif (k, v) not in todo:
                st["error"] = "ต่อไม่ติด (ข้ามชั่วคราว 60s)"
            status[k] = st
        if todo:
            with ThreadPoolExecutor(max_workers=max(1, len(todo))) as ex:
                for server, info, tools, err in ex.map(self._load_one, todo):
                    st = status[server]
                    if err:
                        st["error"] = err[:200]
                        continue
                    st["connected"] = True
                    st["tools"] = len(tools)
                    if info.get("name"):
                        st["server"] = f"{info.get('name', '')} {info.get('version', '')}".strip()
                    for t in tools:
                        qn = mcp_tool_name(server, t.get("name", ""))
                        if qn in meta:
                            continue
                        schema = t.get("inputSchema") or {"type": "object", "properties": {}}
                        if not isinstance(schema, dict):
                            schema = {"type": "object", "properties": {}}
                        desc = str(t.get("description", "") or "")[:500]
                        readonly = bool((t.get("annotations") or {}).get("readOnlyHint", False))
                        meta[qn] = {"server": server, "tool": t.get("name", ""),
                                    "description": desc, "readonly": readonly}
                        defs.append({"type": "function", "function": {
                            "name": qn,
                            "description": f"[MCP {server}] {desc or t.get('name', '')}",
                            "parameters": schema}})
        with self._lock:
            self._defs, self._meta, self._status = defs, meta, status
        return defs

    def tools(self):
        try:
            return self.refresh()
        except Exception:
            return []

    def meta(self, qualname):
        if self._meta is None:
            self.refresh()
        return (self._meta or {}).get(qualname, {})

    def call(self, qualname, args, timeout=120):
        server, tool = split_mcp_name(qualname)
        if not server:
            return f"ERROR: ชื่อ MCP tool ไม่ถูก ({qualname})"
        cfg = self.servers()
        spec = cfg.get(server)
        if not spec:
            return f"ERROR: ไม่มี MCP server '{server}'"
        if not spec.get("enabled", True):
            return f"ERROR: MCP server '{server}' ถูกปิดอยู่"
        try:
            c = self._client(server, spec, timeout=25)
            return c.call_tool(tool, args if isinstance(args, dict) else {}, timeout=timeout)
        except Exception as e:
            with self._lock:
                old = self._clients.pop(server, None)
            if old:
                old.close()
            self._down[server] = time.time()
            return f"ERROR: MCP {server}/{tool}: {e}"

    def status(self):
        self.refresh()
        return dict(self._status)

    def close_all(self):
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
            self._defs, self._meta = None, {}
        for c in clients:
            c.close()


hub = MCPHub()


def agent_mcp_tools():
    """รายชื่อ MCP tools ในรูป OpenAI defs (ล้มเหลว = [] ไม่พัง agent)"""
    try:
        return hub.tools()
    except Exception:
        return []


def call_mcp_tool(qualname, args):
    try:
        return hub.call(qualname, args)
    except Exception as e:
        return f"ERROR: MCP: {e}"
