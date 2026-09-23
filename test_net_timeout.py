# -*- coding: utf-8 -*-
"""Regression: timeout/conn error ทุกค่าย ต้องไม่โผล่ string ดิบ + failover ต่อได้

เคสจริงที่พบ: HTTPSConnectionPool(host='generativelanguage.googleapis.com'...):
Read timed out. (read timeout=120) — เกิดกับเกือบทุกโมเดล/ทุกค่าย เพราะ
- read timeout hard-code 120s ทั้งที่ non-stream ต้องรอทั้งคำตอบ
- timeout ไม่มี status code → ไม่เคยเข้า failover → ผู้ใช้เห็น exc ดิบของ urllib3

สิ่งที่เทสต์:
- _is_timeout_error/_is_read_timeout จับทั้ง exc ชนิด requests และ string ดิบ
- _chat_timeout: (connect, read) จาก config · non-stream ได้เวลานานกว่า stream
- _post_chat: read timeout = ไม่ retry (ช้าซ้ำ) → NetTimeoutError ข้อความไทย
             conn blip = retry ตามเดิม
- send_messages: timeout → _failover_free(504) สลับโมเดล / _failover_provider
  สลับค่าย (เหตุผล 'อ่านคำตอบเกินเวลา') → ได้คำตอบจริง ไม่ใช่ error
- สตรีมขาดกลาง = คืนคำตอบบางส่วน · error ผู้ให้บริการยัง raise ตามเดิม
- หน้าตั้งค่า timeout ใน soonai setup: ถามค่า/validate/บันทึกลง config (ไม่ต้องแก้มือ)
- timeout ถูกบันทึกเป็น health "slow" ให้ statusline โชว์ ⚠ (การแสดงผลตรวจใน test_statusline)
- config key แยก: connect_timeout / chat_timeout (ไม่สตรีม) / chat_timeout_stream

ไม่แตะ network จริง · ไม่แตะ config/keys จริง (patch ทุกจุดที่มีผลข้างเคียง)
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import requests  # noqa: E402
import soonai as S  # noqa: E402

FAILS = []
RAW = ("HTTPSConnectionPool(host='generativelanguage.googleapis.com', port=443): "
       "Read timed out. (read timeout=120)")


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


# ---------- 1) จำแนก error ----------
check("string ดิบของ urllib3 (เคสจริง) = ถูกจับว่าเป็น timeout",
      S._is_timeout_error(RuntimeError(RAW)))
check("requests.ReadTimeout = timeout", S._is_timeout_error(requests.exceptions.ReadTimeout(RAW)))
check("NetTimeoutError = timeout", S._is_timeout_error(S.NetTimeoutError("x")))
check("ConnectionError = timeout/conn",
      S._is_timeout_error(requests.exceptions.ConnectionError("connection reset by peer")))
check("error ปกติของโค้ด = ไม่ใช่ timeout (ไม่โดนกลืน)",
      not S._is_timeout_error(RuntimeError("สตรีมว่างเปล่า (ลองเปลี่ยนโมเดล หรือรันอีกครั้ง)")))
check("ValueError = ไม่ใช่ timeout", not S._is_timeout_error(ValueError("boom")))
check("_is_read_timeout แยก read-timeout ออก",
      S._is_read_timeout(requests.exceptions.ReadTimeout(RAW))
      and not S._is_read_timeout(requests.exceptions.ConnectionError("connection reset")))
ft = S._friendly_timeout(RuntimeError(RAW))
check("_friendly_timeout = ข้อความไทย ไม่โชว์ string ดิบ",
      "HTTPSConnectionPool" not in ft and "เกินเวลา" in ft, ft)

# ---------- 2) _chat_timeout จาก config ----------
_orig_cfg = S.load_config
try:
    S.load_config = lambda: {}
    check("non-stream ได้ read เยอะกว่า stream (คำตอบมาทีเดียว)",
          S._chat_timeout(False) == (15, 240) and S._chat_timeout(True) == (15, 180),
          (S._chat_timeout(False), S._chat_timeout(True)))
    S.load_config = lambda: {"chat_timeout": 45, "connect_timeout": 9}
    check("config chat_timeout/connect_timeout ทับได้",
          S._chat_timeout(False) == (9, 45), S._chat_timeout(False))
    S.load_config = lambda: {"chat_timeout": 5}
    check("ค่าต่ำผิดปกติถูก clamp ไม่ให้สั้นเกินไป",
          S._chat_timeout(True)[1] >= 30, S._chat_timeout(True))
finally:
    S.load_config = _orig_cfg

# ---------- 3) _post_chat: wrap + retry policy ----------
class BoomSession:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def post(self, *a, **k):
        self.calls += 1
        raise self.exc


_orig_sess, _orig_wait = S._http_session, S._wait_animated
S._wait_animated = lambda *a, **k: None
try:
    boom = BoomSession(requests.exceptions.ReadTimeout(RAW))
    S._http_session = lambda: boom
    try:
        S._post_chat("https://x/y", {}, {}, timeout=(15, 120), stream=False, tag="t")
        check("read timeout โยน exception", False)
    except S.NetTimeoutError as e:
        check("read timeout → NetTimeoutError ข้อความไทย",
              "เกินเวลา" in str(e) and "HTTPSConnectionPool" not in str(e), str(e))
        check("read timeout ไม่ retry (server ช้า ลองซ้ำก็ช้า — ให้ failover จัดการ)",
              boom.calls == 1, boom.calls)

    boom2 = BoomSession(requests.exceptions.ConnectionError("connection reset by peer"))
    S._http_session = lambda: boom2
    try:
        S._post_chat("https://x/y", {}, {}, timeout=(15, 120), stream=False, tag="t")
        check("conn blip โยน exception", False)
    except Exception as e:
        check("conn blip = retry ครบตาม retries แล้วค่อยยอม",
              boom2.calls == 3, boom2.calls)
        check("conn blip สุดท้ายยังเป็น NetTimeoutError ข้อความไทย",
              isinstance(e, S.NetTimeoutError) and "เกินเวลา" in str(e), str(e))
finally:
    S._http_session, S._wait_animated = _orig_sess, _orig_wait

# ---------- 4) send_messages: timeout → failover โมเดลเดิมค่าย ----------
class FakeResp:
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content": "ok-thai"},
                             "finish_reason": "stop"}]}


_orig_post, _orig_ff = S._post_chat, S._failover_free
_orig_track, _orig_health = S._track_usage, S._health_note_ok
_orig_slow = S._health_note_slow
seen_slow = []
S._track_usage = lambda *a, **k: None
S._health_note_ok = lambda *a, **k: None
calls = {"n": 0}
seen_ff = {}


def fake_post_a(url, **kw):
    calls["n"] += 1
    if calls["n"] == 1:
        raise S.NetTimeoutError(S._friendly_timeout(RuntimeError(RAW)))
    return FakeResp()


def fake_ff(provider, model, status, body, switches, *a, **k):
    seen_ff.update(status=status, body=body)
    return "model-b"


try:
    S._post_chat = fake_post_a
    S._failover_free = fake_ff
    S._health_note_slow = lambda p: seen_slow.append(p)
    out = S.send_messages("openrouter", "model-a",
                          [{"role": "user", "content": "hi"}], 0, stream=False)
    check("timeout แล้วระบบสลับโมเดล/ลองใหม่ → ได้คำตอบ (ไม่ใช่ error)",
          out.strip() == "ok-thai", out)
    check("failover ถูกเรียกด้วยสถานะ 504 (reuse ทาง HTTP ชั่วคราวเดิม)",
          seen_ff.get("status") == 504, seen_ff)
    check("ลองใหม่จริงหลังสลับ", calls["n"] >= 2, calls["n"])
    check("timeout ถูกบันทึกเป็นสัญญาณ ⚠ ให้ statusline เห็น",
          seen_slow == ["openrouter"], seen_slow)

    # ---------- 5) send_messages: timeout → failover ข้ามค่าย ----------
    class FakeDriver:
        provider_key = "groq"
        model = "gm"
        supports_switch = True
        max_rounds = 1
        emit_per_round = True
        stream = False
        supports_stream = False

        def spec(self):
            return "u", {}, {}

        def send(self, *a):
            return FakeResp()

        def read(self, r, emit):
            emit("มาจากค่ายใหม่")
            return "มาจากค่ายใหม่", ""

        def should_continue(self, *a):
            return False

    def always_timeout(url, **kw):
        raise S.NetTimeoutError(S._friendly_timeout(RuntimeError(RAW)))

    _orig_fp, _orig_csd, _orig_ap = (S._failover_provider, S._chat_switch_driver,
                                     S._apply_provider_switch)
    seen_sw = {}
    S._post_chat = always_timeout
    S._failover_free = lambda *a, **k: ""
    S._failover_provider = lambda p, m, ttl=0: (seen_sw.update(ttl=ttl) or ("groq", "gm"))
    S._chat_switch_driver = lambda *a, **k: FakeDriver()
    S._apply_provider_switch = lambda p, m, reason: seen_sw.update(reason=reason)
    try:
        out2 = S.send_messages("openrouter", "model-a",
                               [{"role": "user", "content": "hi"}], 0, stream=False)
        check("ค่ายเดิมตายหมด → สลับค่ายแล้วได้คำตอบจริง",
              out2.strip() == "มาจากค่ายใหม่", out2)
        check("เหตุผลสลับค่ายสื่อว่าเป็นเรื่องเกินเวลา",
              "เกินเวลา" in str(seen_sw.get("reason", "")), seen_sw)
        check("เรียก failover_provider แบบจำสั้น (ttl=1800)",
              seen_sw.get("ttl") == 1800, seen_sw)
    finally:
        S._failover_provider, S._chat_switch_driver, S._apply_provider_switch = (
            _orig_fp, _orig_csd, _orig_ap)

    # ---------- 6) timeout ทุกอย่างล้ม = error ไทย (ไม่ใช่ exc ดิบ) ----------
    S._post_chat = always_timeout
    S._failover_free = lambda *a, **k: ""
    S._failover_provider = lambda *a, **k: ("", "")
    try:
        S.send_messages("openrouter", "model-a",
                        [{"role": "user", "content": "hi"}], 0, stream=False)
        check("หมดหนทาง = โยน error", False)
    except S.NetTimeoutError as e:
        check("หมดหนทาง = NetTimeoutError ข้อความไทย ไม่มี string ดิบ",
              "HTTPSConnectionPool" not in str(e) and "เกินเวลา" in str(e), str(e))
    except Exception as e:
        check("หมดหนทาง = NetTimeoutError ข้อความไทย", False, str(e))
finally:
    S._post_chat, S._failover_free = _orig_post, _orig_ff
    S._track_usage, S._health_note_ok = _orig_track, _orig_health
    S._health_note_slow = _orig_slow

# ---------- 7) สตรีมขาดกลาง = คืนคำตอบบางส่วน ----------
class PartialResp:
    def iter_lines(self, decode_unicode=True):
        yield 'data: {"choices":[{"delta":{"content":"หวัดดี"}}]}'
        yield ""
        raise requests.exceptions.ConnectionError("Connection broken: IncompleteRead(10, 20)")


class ErrResp:
    def iter_lines(self, decode_unicode=True):
        yield 'data: {"error": {"message": "boom"}}'


drv = S._OpenAIChatDriver("openrouter", "m",
                          [{"role": "user", "content": "x"}], 0, True, "", None)
got = []
text, finish = drv.read(PartialResp(), got.append)
check("สตรีมขาดกลาง = คืนคำตอบบางส่วนที่อ่านได้", text == "หวัดดี", text)
check("emit ออกจริงทุกชิ้นที่ได้มา", got == ["หวัดดี"], got)
try:
    drv.read(ErrResp(), lambda t: None)
    check("error จากผู้ให้บริการกลางสตรีม = raise ตามเดิม", False)
except RuntimeError as e:
    check("error จากผู้ให้บริการกลางสตรีม = raise ตามเดิม", "boom" in str(e), str(e))

# ---------- 8) หน้าตั้งค่า timeout ใน soonai setup ----------
class FakePrompt:
    def __init__(self, answers):
        self.answers = list(answers)

    def ask(self, *a, **k):
        return self.answers.pop(0)


_orig_prompt, _orig_save = S.Prompt, S.save_json
saved = {}


def fake_save(fn, data):
    saved["file"] = str(fn)
    saved["data"] = dict(data)


S.save_json = fake_save
try:
    # 8a) ตอบ n = คงค่าเดิม ไม่แตะ config
    S.Prompt = FakePrompt(["n"])
    tcfg = {"provider": "openrouter"}
    r1 = S.setup_timeouts(tcfg)
    check("setup timeout: ตอบ n = คงค่าเดิม ไม่เขียน config",
          r1 is False and not saved, (r1, saved))

    # 8b) กรอกค่า = บันทึกเฉพาะค่าที่ถูก (Enter = คง · เกินช่วง = ไม่เอา)
    S.Prompt = FakePrompt(["y", "", "600", "9999"])
    tcfg = {"provider": "openrouter"}
    r2 = S.setup_timeouts(tcfg)
    check("setup timeout: บันทึกเฉพาะค่าที่กรอกถูก (Enter/เกินช่วง = ไม่เอา)",
          r2 is True and tcfg.get("chat_timeout_stream") == 600
          and "chat_timeout" not in tcfg and "connect_timeout" not in tcfg, tcfg)
    check("setup timeout: save_json ถูกเรียกพร้อมค่าใหม่",
          saved.get("data", {}).get("chat_timeout_stream") == 600, saved)
    check("setup timeout: cfg ที่ส่งเข้าไปถูก update ด้วย (ใช้ต่อได้)",
          tcfg.get("chat_timeout_stream") == 600, tcfg)

    # 8c) ค่าไม่ใช่ตัวเลข = คงเดิม ไม่บันทึก
    saved.clear()
    S.Prompt = FakePrompt(["y", "abc", "", ""])
    r3 = S.setup_timeouts({})
    check("setup timeout: ค่าไม่ใช่ตัวเลข = ไม่บันทึก",
          r3 is False and not saved, (r3, saved))

    # 8d) EOF (โหมด pipe) = จบเงียบ ไม่พัง
    class EofPrompt:
        @staticmethod
        def ask(*a, **k):
            raise EOFError

    S.Prompt = EofPrompt
    r4 = S.setup_timeouts({})
    check("setup timeout: EOF (โหมด pipe) = จบเงียบ ไม่แตะ config",
          r4 is False and not saved, (r4, saved))
finally:
    S.Prompt, S.save_json = _orig_prompt, _orig_save

# ---------- 9) config key แยก: connect / non-stream / stream ----------
_orig_cfg2 = S.load_config
try:
    S.load_config = lambda: {"chat_timeout_stream": 77}
    check("chat_timeout_stream อ่านแยกสำหรับสตรีม",
          S._chat_timeout(True) == (15, 77), S._chat_timeout(True))
    S.load_config = lambda: {"chat_timeout": 45}
    check("ไม่มี chat_timeout_stream = ใช้ chat_timeout (legacy)",
          S._chat_timeout(True)[1] == 45, S._chat_timeout(True))
    S.load_config = lambda: {"chat_timeout_stream": 77, "chat_timeout": 300,
                             "connect_timeout": 8}
    check("สองค่าอ่านแยกกัน + connect ใช้ร่วมกัน",
          S._chat_timeout(True) == (8, 77) and S._chat_timeout(False) == (8, 300),
          (S._chat_timeout(True), S._chat_timeout(False)))
finally:
    S.load_config = _orig_cfg2

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL NET TIMEOUT TESTS PASSED")
