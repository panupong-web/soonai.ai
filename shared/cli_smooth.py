# -*- coding: utf-8 -*-
"""CLI Smoothness Engine — ทำให้ CLI ลื่นไหลเทียบเท่า/ดีกว่า Codex

สิ่งที่ทำ (Codex-like smoothness):
1. StreamingTextEngine — ข้อความไหลเรียบเนียนเหมือน Codex
2. LiveStatusBar — สถานะบาร์อัปเดต real-time ที่ด้านล่าง
3. BackgroundTaskQueue — งานพื้นหลังไม่บล็อก UI
4. SmartCache — cache ทุกอย่างแบบ smart
5. KeyboardShortcuts — ปุ่มลัดเหมือน Codex (Ctrl+C, Ctrl+D, Tab)
6. LiveRender — เรนเดอร์แบบ live ตอน agent ทำงาน
7. MemoryPool — ลด GC pressure ด้วย object pooling
8. PulseAnimation — อนิเมชัน pulse ที่ไม่รบกวน
"""
import sys
import os
import threading
import time
import queue
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
import itertools

# runtime import แบบ lazy — ไม่ import ตอน module load
_RUNTIME_REF = None

def _get_R():
    """ดึง runtime module แบบ lazy"""
    global _RUNTIME_REF
    if _RUNTIME_REF is None:
        import runtime as _R
        _RUNTIME_REF = _R
    return _RUNTIME_REF

# ═══════════════════════════════════════════════════════════════
# 1. StreamingTextEngine — ข้อความไหลเรียบเนียนเหมือน Codex
# ═══════════════════════════════════════════════════════════════
@dataclass
class StreamChunk:
    """ชิ้นส่วนของข้อความที่ streaming"""
    text: str
    is_markdown: bool = False
    timestamp: float = field(default_factory=time.time)
    style: str = ""

class StreamingTextEngine:
    """ข้อความ streaming ที่ลื่นไหล — จัดกลุ่ม chunks แล้ว render แบบ batch
    
    Codex จะส่งข้อความทีละนิดแล้วอัปเดตหน้าจอแบบ real-time.
    ที่นี่เราจะ:
    - รวม chunks ที่มาเร็วๆ กัน (within 50ms)
    - render แบบ batch แทนทีละตัวอักษร
    - ใช้ Rich Live ในการอัปเดต
    """

    def __init__(self, console, target=None):
        self.console = console
        self._target = target or sys.stdout
        self._buffer = []
        self._lock = threading.Lock()
        self._live = None
        self._last_render = 0
        self._batch_window = 0.05  # 50ms — รวม chunks ที่มาใกล้กัน
        self._render_lock = threading.Lock()
        self._running = False
        self._render_thread = None

    def start(self):
        """เริ่ม rendering thread"""
        if self._running:
            return
        self._running = True
        self._render_thread = threading.Thread(
            target=self._render_loop, daemon=True)
        self._render_thread.start()

    def stop(self):
        """หยุด rendering thread"""
        self._running = False
        if self._render_thread:
            self._render_thread.join(timeout=0.5)

    def write(self, text, style="", is_markdown=False):
        """เขียนข้อความเข้า queue — ไม่ block"""
        with self._lock:
            self._buffer.append(StreamChunk(text, is_markdown, style=style))

    def flush(self):
        """บังคับ render ทุก chunk ที่ค้าง"""
        with self._lock:
            if not self._buffer:
                return
            chunks = list(self._buffer)
            self._buffer.clear()
        
        self._render_chunks(chunks)

    def _render_loop(self):
        """Loop ที่ render แบบ batch — ทุก 50ms"""
        while self._running:
            now = time.time()
            time.sleep(min(self._batch_window, 0.05))
            
            with self._lock:
                if not self._buffer:
                    continue
                chunks = list(self._buffer)
                self._buffer.clear()
            
            self._render_chunks(chunks)

    def _render_chunks(self, chunks):
        """render ชุดของ chunks พร้อมกัน"""
        if not chunks:
            return
        
        text = "".join(c.text for c in chunks)
        if not text.strip():
            return
        
        # Markdown chunks render เป็น Markdown
        md_chunks = [c for c in chunks if c.is_markdown]
        if md_chunks:
            for mc in md_chunks:
                self.console.print(Markdown(mc.text) if mc.text.strip() else "",
                                   style=mc.style, highlight=False,
                                   soft_wrap=True, end="")
        else:
            self.console.print(text, style="", highlight=False,
                               soft_wrap=True, end="")


# ═══════════════════════════════════════════════════════════════
# 2. LiveStatusBar — สถานะบาร์อัปเดต real-time ที่ด้านล่าง
# ═══════════════════════════════════════════════════════════════
class LiveStatusBar:
    """Status bar ที่อัปเดต real-time — เหมือน Codex status indicator
    
    แสดงที่ด้านล่าง:
    - Provider/model ปัจจุบัน
    - จำนวน tokens ที่ใช้
    - เวลาที่ผ่านไป
    - สถานะ agent
    - จำนวน tools ที่เรียก
    """

    def __init__(self, console):
        self.console = console
        self._live = None
        self._lock = threading.Lock()
        self._provider = ""
        self._model = ""
        self._tokens = 0
        self._elapsed = 0
        self._agent = False
        self._auto_yes = False
        self._tools_called = 0
        self._start_time = 0
        self._running = False
        self._thread = None
        self._last_text = ""

    def start(self, provider="", model=""):
        """เริ่ม status bar"""
        self._provider = provider
        self._model = model
        self._start_time = time.time()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """หยุด status bar"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)

    def update(self, provider="", model="", tokens=0, agent=False,
               auto_yes=False, tools_called=0):
        """อัปเดต status"""
        self._provider = provider
        self._model = model
        self._tokens = tokens
        self._agent = agent
        self._auto_yes = auto_yes
        self._tools_called = tools_called

    def _loop(self):
        """อัปเดต status bar ทุก 1 วินาที"""
        while self._running:
            now = time.time()
            elapsed = now - self._start_time
            self._elapsed = elapsed
            
            with self._lock:
                text = self._build_text()
            
            if text != self._last_text:
                self._last_text = text
                self._render(text)
            
            time.sleep(1.0)

    def _build_text(self):
        """สร้างข้อความ status bar"""
        parts = []
        
        # Provider/model
        if self._provider or self._model:
            parts.append(f"[cyan]{self._provider or '?'}[/cyan] "
                         f"[white]{self._model or '?'}[/white]")
        
        # Agent indicator
        if self._agent:
            parts.append("[yellow]⚡ agent[/yellow]")
        
        # Auto approve
        if self._auto_yes:
            parts.append("[magenta]AUTO[/magenta]")
        
        # Tools
        if self._tools_called > 0:
            parts.append(f"[dim]tools: {self._tools_called}[/dim]")
        
        # Time
        parts.append(f"[dim]{self._elapsed:.0f}s[/dim]")
        
        # Tokens
        if self._tokens > 0:
            parts.append(f"[dim]{self._tokens:,} tokens[/dim]")
        
        return " · ".join(parts)

    def _render(self, text):
        """เรนเดอร์ status bar"""
        try:
            # ใช้ console.print ที่ด้านล่างสุด
            # ตำแหน่ง cursor อยู่ที่ bottom ของ terminal
            self.console.print(
                text, style="dim", highlight=False, end="\r",
                soft_wrap=False, new_line_start=False)
        except Exception:
            pass

    def clear(self):
        """ล้าง status bar"""
        self._last_text = ""
        try:
            self.console.print("", end="\r", highlight=False)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 3. BackgroundTaskQueue — งานพื้นหลังไม่บล็อก UI
# ═══════════════════════════════════════════════════════════════
class BackgroundTaskQueue:
    """Task queue สำหรับงานพื้นหลัง — ไม่บล็อก UI
    
    Codex ทำงานหลายอย่างพร้อมกัน: คิด, ค้นหา, รัน, แสดงผล.
    ที่นี่เราทำให้:
    - ไม่บล็อก main thread
    - มี priority queue
    - หยุดได้เมื่อต้องการ
    """

    def __init__(self, max_workers=4):
        self._queue = queue.PriorityQueue()
        self._workers = []
        self._results = {}
        self._lock = threading.Lock()
        self._running = False
        self._counter = itertools.count()
        self._max_workers = max_workers

    def start(self):
        """เริ่ม worker threads"""
        if self._running:
            return
        self._running = True
        for i in range(self._max_workers):
            t = threading.Thread(target=self._worker, daemon=True,
                                 name=f"bg-worker-{i}")
            t.start()
            self._workers.append(t)

    def stop(self):
        """หยุด worker ทั้งหมด"""
        self._running = False
        for _ in self._workers:
            self._queue.put((999, next(self._counter), None, None))
        for t in self._workers:
            t.join(timeout=1.0)
        self._workers.clear()

    def submit(self, task_id, func, *args, priority=5, callback=None):
        """ส่งงานเข้า queue
        
        priority: 0 = highest, 9 = lowest
        callback: function(result) — เรียกเมื่องานเสร็จ
        """
        self._queue.put((priority, next(self._counter),
                         (func, args, callback), task_id))

    def _worker(self):
        """Worker loop"""
        while self._running:
            try:
                priority, count, task_data, task_id = self._queue.get(timeout=0.5)
                if task_data is None:
                    continue  # Stop signal
                
                func, args, callback = task_data
                try:
                    result = func(*args)
                    with self._lock:
                        self._results[task_id] = result
                    if callback:
                        callback(result)
                except Exception as e:
                    with self._lock:
                        self._results[task_id] = e
                    if callback:
                        callback(e)
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue

    def get_result(self, task_id, timeout=None):
        """ดูผลลัพธ์ของ task"""
        with self._lock:
            if task_id in self._results:
                return self._results[task_id]
        return None


# ═══════════════════════════════════════════════════════════════
# 4. PulseAnimation — อนิเมชัน pulse ที่ไม่รบกวน
# ═══════════════════════════════════════════════════════════════
class PulseAnimation:
    """อนิเมชัน pulse — แสดงว่ากำลังประมวลผล
    
    Codex มี pulse animation ที่ด้านล่างที่แสดงว่า AI กำลังคิด.
    ที่นี่เรา implement แบบเดียวกันแต่ไม่รบกวนการพิมพ์.
    """

    PULSES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, console):
        self.console = console
        self._running = False
        self._thread = None
        self._message = ""
        self._frame = 0
        self._lock = threading.Lock()

    def start(self, message="กำลังประมวลผล…"):
        """เริ่ม pulse animation"""
        if self._running:
            return
        self._message = message
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """หยุด pulse animation"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)
        # ล้าง animation
        try:
            self.console.print("\r" + " " * 40 + "\r", end="", highlight=False)
        except Exception:
            pass

    def _loop(self):
        """Animation loop"""
        while self._running:
            pulse = self.PULSES[self._frame % len(self.PULSES)]
            try:
                self.console.print(
                    f"\r[dim]{self._message} {pulse}[/dim]",
                    end="", highlight=False)
            except Exception:
                pass
            self._frame += 1
            time.sleep(0.1)


# ═══════════════════════════════════════════════════════════════
# 5. SmartCache — cache ทุกอย่างแบบ smart
# ═══════════════════════════════════════════════════════════════
class SmartCache:
    """Cache ที่มี TTL + LRU + size limit
    
    ใช้ cache:
    - Model lists (ไม่ต้องดึงใหม่ทุกรอบ)
    - Provider info
    - File listings
    - Command results
    """

    def __init__(self, max_size=100, default_ttl=300):
        self._cache = {}
        self._max_size = max_size
        self._default_ttl = default_ttl  # seconds
        self._lock = threading.Lock()
        self._access_order = deque()

    def get(self, key):
        """ดึงค่าจาก cache ถ้ายังไม่หมดอายุ"""
        with self._lock:
            if key not in self._cache:
                return None
            entry = self._cache[key]
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                return None
            # Move to end (LRU)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return entry["value"]

    def set(self, key, value, ttl=None):
        """บันทึกลง cache"""
        with self._lock:
            # Evict if over max size
            while len(self._cache) >= self._max_size and self._access_order:
                oldest = self._access_order.popleft()
                self._cache.pop(oldest, None)
            
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + (ttl or self._default_ttl),
            }
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

    def invalidate(self, key=None):
        """ล้าง cache ทั้งหมดหรือ key เฉพาะ"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
                if key in self._access_order:
                    self._access_order.remove(key)
            else:
                self._cache.clear()
                self._access_order.clear()

    def invalidate_pattern(self, prefix):
        """ล้าง cache ที่ key ขึ้นต้นด้วย prefix"""
        with self._lock:
            to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in to_remove:
                self._cache.pop(k, None)
                if k in self._access_order:
                    self._access_order.remove(k)


# ═══════════════════════════════════════════════════════════════
# 6. LiveRender — เรนเดอร์แบบ live ตอน agent ทำงาน
# ═══════════════════════════════════════════════════════════════
class LiveRender:
    """Live rendering สำหรับ agent operations
    
    Codex แสดง progress แบบ real-time ตอน:
    - กำลังคิด (thinking)
    - กำลังรันคำสั่ง
    - กำลังอ่านไฟล์
    - กำลังส่งข้อความ
    """

    def __init__(self, console):
        self.console = console
        self._live = None
        self._lock = threading.Lock()
        self._current = ""
        self._phase = ""
        self._detail = ""
        self._running = False

    def start_live(self, phase=""):
        """เริ่ม live rendering"""
        self._phase = phase
        self._running = True
        self._render()

    def update(self, phase="", detail=""):
        """อัปเดต live rendering"""
        self._phase = phase
        self._detail = detail
        self._render()

    def stop(self):
        """หยุด live rendering"""
        self._running = False
        self._phase = ""
        self._detail = ""

    def _render(self):
        """เรนเดอร์ current state"""
        if not self._running:
            return
        text = self._build_text()
        try:
            # Clear line and rewrite
            self.console.print(text, style="dim", highlight=False,
                               end="\r", soft_wrap=False)
        except Exception:
            pass

    def _build_text(self):
        """สร้างข้อความ live"""
        parts = []
        if self._phase:
            parts.append(f"[cyan]{self._phase}[/cyan]")
        if self._detail:
            parts.append(f"[dim]{self._detail[:60]}[/dim]")
        return " ".join(parts)


# ═══════════════════════════════════════════════════════════════
# 7. KeyboardShortcuts — ปุ่มลัดเหมือน Codex
# ═══════════════════════════════════════════════════════════════
@dataclass
class Shortcut:
    """ปุ่มลัด"""
    key: str
    description: str
    action: str
    group: str = "general"

class KeyboardShortcuts:
    """ปุ่มลัดเหมือน Codex — แสดงเมื่อกด?"""

    SHORTCUTS = [
        # Navigation
        Shortcut("Ctrl+C", "ยกเลิก/ออก", "cancel", "navigation"),
        Shortcut("Ctrl+D", "EOF / ออก", "eof", "navigation"),
        Shortcut("Tab", " autocomplete / เลือก", "tab", "navigation"),
        Shortcut("Up/Down", "เลื่อน history", "history", "navigation"),
        
        # Chat commands
        Shortcut("/", "เมนูคำสั่ง", "slash", "chat"),
        Shortcut("Ctrl+Space", "เสนอคำสั่ง", "suggest", "chat"),
        Shortcut("Esc", "ปิดเมนู/กลับ", "escape", "chat"),
        
        # Agent
        Shortcut("Ctrl+Enter", "ส่ง (agent mode)", "agent_send", "agent"),
        Shortcut("Alt+Enter", "ส่งใหม่", "new_chat", "agent"),
        
        # Tools
        Shortcut("Ctrl+L", "ล้างหน้าจอ", "clear", "tools"),
        Shortcut("Ctrl+R", "ค้นหาใน history", "search", "tools"),
        Shortcut("F1", "Help", "help", "tools"),
    ]

    @staticmethod
    def show():
        """แสดงปุ่มลัด"""
        lines = []
        current_group = None
        for s in KeyboardShortcuts.SHORTCUTS:
            if s.group != current_group:
                current_group = s.group
                lines.append(f"\n[bold]{current_group.upper()}[/bold]")
            lines.append(f"  {s.key:15s} {s.description}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 8. MemoryPool — ลด GC pressure
# ═══════════════════════════════════════════════════════════════
class MemoryPool:
    """Object pool — ลด GC pressure ตอนเรนเดอร์เยอะๆ
    
    Codex ไม่สร้าง object ใหม่ทุกครั้ง — ใช้ pool แทน.
    ที่นี่เรา pool สำหรับ:
    - Text segments
    - Table rows
    - Console output objects
    """

    def __init__(self, factory, max_size=50):
        self._factory = factory
        self._pool = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def acquire(self, *args, **kwargs):
        """รับ object จาก pool หรือสร้างใหม่"""
        with self._lock:
            if self._pool:
                return self._pool.pop()
        return self._factory(*args, **kwargs)

    def release(self, obj):
        """คืน object เข้า pool"""
        with self._lock:
            if len(self._pool) < self._pool.maxlen:
                self._pool.append(obj)


# ═══════════════════════════════════════════════════════════════
# 9. CodexLikeUI — รวมทุกอย่างเข้าด้วยกัน
# ═══════════════════════════════════════════════════════════════
class CodexLikeUI:
    """UI ที่ลื่นไหลเหมือน Codex — รวมทุก feature เข้าด้วยกัน
    
    Usage:
        ui = CodexLikeUI(console)
        ui.start()
        ui.stream("ข้อความ...")
        ui.status(provider="ollama", model="llama3")
        ui.task_queue.submit(...)
        ui.stop()
    """

    def __init__(self, console):
        self.console = console
        self.streamer = StreamingTextEngine(console)
        self.status_bar = LiveStatusBar(console)
        self.task_queue = BackgroundTaskQueue()
        self.pulse = PulseAnimation(console)
        self.live_render = LiveRender(console)
        self.cache = SmartCache()
        self.shortcuts = KeyboardShortcuts
        self.pool = MemoryPool(
            lambda: {"text": "", "style": "", "ts": time.time()}, 50)
        self._running = False

    def start(self, provider="", model=""):
        """เริ่มทุก subsystem"""
        self._running = True
        self.streamer.start()
        self.status_bar.start(provider, model)
        self.task_queue.start()

    def stop(self):
        """หยุดทุก subsystem"""
        self._running = False
        self.streamer.stop()
        self.status_bar.stop()
        self.task_queue.stop()
        self.pulse.stop()
        self.live_render.stop()

    def stream_text(self, text, style="", is_markdown=False):
        """ส่งข้อความ streaming"""
        self.streamer.write(text, style=style, is_markdown=is_markdown)

    def flush_stream(self):
        """บังคับ flush"""
        self.streamer.flush()

    def set_status(self, **kwargs):
        """อัปเดต status bar"""
        self.status_bar.update(**kwargs)

    def show_pulse(self, message="กำลังประมวลผล…"):
        """แสดง pulse animation"""
        self.pulse.start(message)
        return self.pulse

    def submit_task(self, task_id, func, *args, **kwargs):
        """ส่งงานพื้นหลัง"""
        self.task_queue.submit(task_id, func, *args, **kwargs)

    def get_cached(self, key):
        """ดึงจาก cache"""
        return self.cache.get(key)

    def set_cached(self, key, value, ttl=None):
        """บันทึก cache"""
        self.cache.set(key, value, ttl=ttl)

    def render_live(self, phase, detail=""):
        """เรนเดอร์ live"""
        self.live_render.update(phase, detail)


# ═══════════════════════════════════════════════════════════════
# 10. SmoothInput — อินพุตที่ลื่นไหล
# ═══════════════════════════════════════════════════════════════
class SmoothInput:
    """อินพุตที่ลื่นไหล — ไม่มี lag, ไม่สะดุด
    
    Codex มี input ที่ตอบสนองทันที — ไม่มี delay.
    ที่นี่เราทำให้:
    - readline สำหรับ history ถาวร
    - prompt_toolkit สำหรับ autocomplete
    - Fallback ที่รวดเร็วถ้า prompt_toolkit พัง
    """

    def __init__(self, console, history_file=None):
        self.console = console
        self.history_file = history_file or str(
            Path.home() / ".soonai_history")
        self._ptk_session = None
        self._history = None
        self._setup_readline()

    def _setup_readline(self):
        """ตั้ง readline"""
        try:
            import readline
            import pyreadline  # Windows
        except ImportError:
            try:
                import readline
            except ImportError:
                return
        
        try:
            readline.read_history_file(self.history_file)
        except Exception:
            pass
        
        import atexit
        atexit.register(self._save_history)
        
        try:
            readline.parse_and_bind("tab: complete")
            readline.parse_and_bind("set completion-ignore-case on")
            readline.set_history_length(10000)
        except Exception:
            pass

    def _save_history(self):
        """บันทึก history"""
        try:
            import readline
            readline.write_history_file(self.history_file)
        except Exception:
            pass

    def setup_prompt_session(self, completer=None):
        """ตั้ง prompt_toolkit session"""
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.history import InMemoryHistory
            from prompt_toolkit.styles import Style
            
            self._history = InMemoryHistory()
            self._ptk_session = PromptSession(
                history=self._history,
                completer=completer,
                style=Style.from_dict({"": "#00e5ff bold"}),
            )
        except Exception:
            self._ptk_session = None

    def prompt(self, prompt_text="> ", completer=None):
        """รับ input — เร็วที่สุด ไม่มี lag
        
        ลำดับความสำคัญ:
        1. prompt_toolkit session (ถ้ามี)
        2. readline (ถ้าตั้งไว้)
        3. console.input (fallback)
        """
        # 1. prompt_toolkit
        if self._ptk_session is not None:
            try:
                return self._ptk_session.prompt(prompt_text)
            except Exception:
                pass
        
        # 2. readline
        try:
            import readline
            return input(prompt_text)
        except Exception:
            pass
        
        # 3. console.input
        try:
            return self.console.input(prompt_text)
        except (EOFError, KeyboardInterrupt):
            raise

    def clear_session(self):
        """ล้าง prompt_toolkit session"""
        self._ptk_session = None
        self._history = None


# ═══════════════════════════════════════════════════════════════
# 11. Integration helper — เชื่อมเข้ากับ soonai.py / chat.py
# ═══════════════════════════════════════════════════════════════
def make_smooth(console):
        """สร้าง CodexLikeUI พร้อมใช้งาน"""
        ui = CodexLikeUI(console)
        return ui


def patch_console_for_smooth(console):
    """Patch console ให้รองรับ smooth rendering"""
    # บันทึก terminal width
    try:
        console._last_width = console.width
    except Exception:
        pass
    
    # เพิ่ม method สำหรับ smooth render
    def smooth_print(self, *args, **kwargs):
        """Print ที่ไม่ block"""
        try:
            self.print(*args, **kwargs)
        except Exception:
            pass
    
    console.smooth_print = smooth_print.__get__(console)


# ═══════════════════════════════════════════════════════════════
# 12. Startup optimizer — รวมทุกอย่าง
# ═══════════════════════════════════════════════════════════════
def optimize_startup(console, history_file=None):
    """เรียกตอน startup — ตั้ง readline, pre-import, cache
    
    เร่ง startup ให้เร็วเหมือน Codex.
    """
    # 1. readline
    try:
        import readline
        try:
            readline.read_history_file(history_file or str(
                Path.home() / ".soonai_history"))
        except Exception:
            pass
        import atexit
        atexit.register(_save_history, history_file or str(
            Path.home() / ".soonai_history"))
        try:
            readline.parse_and_bind("tab: complete")
            readline.set_history_length(10000)
        except Exception:
            pass
    except ImportError:
        pass
    
    # 2. Pre-import heavy modules
    _preimports = [
        "prompt_toolkit",
        "prompt_toolkit.application",
        "prompt_toolkit.history",
        "prompt_toolkit.styles",
        "prompt_toolkit.completion",
        "prompt_toolkit.layout",
        "prompt_toolkit.key_binding",
        "rich.live",
        "rich.markdown",
        "rich.panel",
        "rich.table",
        "requests",
    ]
    for mod in _preimports:
        try:
            __import__(mod)
        except ImportError:
            pass
    
    # 3. Cache terminal width
    try:
        _term_w = console.width
    except Exception:
        pass


def _save_history(history_file):
    """บันทึก history"""
    try:
        import readline
        readline.write_history_file(history_file)
    except Exception:
        pass
