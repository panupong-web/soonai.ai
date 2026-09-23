"""Regression: custom OpenAI-compatible provider registration and routing."""
import sys
import os

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import providers as P  # noqa: E402
import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


before = dict(P.PROVIDERS)
try:
    added = P.apply_custom_providers({"custom_providers": {
        "localtest": {
            "name": "Local Test API",
            "base": "http://127.0.0.1:9999/v1/chat/completions",
            "model": "test-model",
            "models": ["test-model", "second-model"],
            "key_env": "SOONAI_CUSTOM_TEST_KEY",
            "extra_headers": {"X-Client": "soonai", "Authorization": "must-drop"},
        }
    }})
    check("เพิ่ม custom provider ได้", added == ["localtest"])
    spec = P.PROVIDERS.get("localtest", {})
    check("ตัด /chat/completions เหลือ base ที่ถูกต้อง",
          spec.get("base") == "http://127.0.0.1:9999/v1", spec)
    check("เป็น OpenAI-compatible provider", spec.get("type") == "openai")
    os.environ["SOONAI_CUSTOM_TEST_KEY"] = "env-secret"
    check("อ่าน API key จาก environment ได้", P.get_key("localtest", {}) == "env-secret")
    check("รักษา fallback models", spec.get("fallback_models") == ["test-model", "second-model"], spec)
    check("ไม่เก็บ Authorization ใน custom headers",
          "Authorization" not in spec.get("extra_headers", {}), spec)
    check("เก็บ header ที่ไม่ใช่ secret", spec.get("extra_headers", {}).get("X-Client") == "soonai")

    old_keys = S.load_keys
    try:
        S.load_keys = lambda: {"localtest": "secret-token"}
        driver = S._OpenAICompatDriver("localtest", "test-model", 0.2)
        url, headers, payload, _ = driver.request([], False, False)
        check("driver ใช้ custom base + chat endpoint",
              url == "http://127.0.0.1:9999/v1/chat/completions", url)
        check("driver ส่ง API key แบบ Bearer", headers.get("Authorization") == "Bearer secret-token", headers)
        check("driver ส่ง model ที่เลือก", payload.get("model") == "test-model", payload)
        check("driver ยังสร้าง tools payload ได้", isinstance(payload.get("tools"), list), payload)
    finally:
        S.load_keys = old_keys
finally:
    os.environ.pop("SOONAI_CUSTOM_TEST_KEY", None)
    P.PROVIDERS.clear()
    P.PROVIDERS.update(before)
    P._CUSTOM_PROVIDER_IDS.clear()

# ---------- เมนูเปลี่ยนค่าย: มีหัวข้อ "เพิ่มค่ายเอง" + เพิ่มเสร็จเลือกต่อทันที
cfg_store = {"provider": "ollama", "model": "", "custom_providers": {}}
saved = {}
orig = (S.Prompt, S.CONFIG_FILE, S.fuzzy_pick, S.cmd_providers, S.ensure_key,
        S.ensure_local_server, S.pick_model, S.save_json, dict(P.PROVIDERS))

def _tmp_save(path, obj):
    saved["cfg"] = dict(obj)
    saved["path"] = str(path)

try:
    import tempfile
    S.CONFIG_FILE = os.path.join(tempfile.mkdtemp(prefix="soonai-cprov-"), "config.json")
    S.save_json = _tmp_save  # ไม่เขียน config จริงระหว่างเทสต์
    # ลำดับคำตอบ: ชื่อ / URL / โมเดล
    answers = ["demo", "http://127.0.0.1:9/v1", "m-test"]
    S.Prompt = type("P", (), {"ask": staticmethod(lambda *a, **k: answers.pop(0))})
    seen = {}
    def _fp(message, items):
        seen["items"] = list(items)
        return S.ADD_PROVIDER_CHOICE          # ผู้ใช้เลือกหัวข้อ ➕ เพิ่มค่ายเอง
    S.fuzzy_pick = _fp
    S.cmd_providers = lambda *a, **k: 0       # ข้ามการพิมพ์ตารางระหว่างเทสต์
    S.ensure_key = lambda pid, keys: True
    S.ensure_local_server = lambda pid: True
    S.pick_model = lambda pid, keys, **k: "m-test"

    result = S.switch_provider({}, cfg_store)
    check("เมนูเปลี่ยนค่ายมีหัวข้อ เพิ่มค่ายเอง",
          any(v == S.ADD_PROVIDER_CHOICE and "เพิ่มค่ายเอง" in label
              for v, label in seen.get("items", [])),
          seen.get("items"))
    check("เพิ่มเสร็จ = สลับไปค่ายใหม่ทันที",
          result == ("demo", "m-test"), result)
    check("ค่ายใหม่เข้าตาราง PROVIDERS แล้ว",
          P.PROVIDERS.get("demo", {}).get("base") == "http://127.0.0.1:9/v1",
          P.PROVIDERS.get("demo"))
    check("cfg ถูกตั้งเป็นค่ายใหม่",
          cfg_store.get("provider") == "demo" and cfg_store.get("model") == "m-test",
          cfg_store)
    check("บันทึกลง config (custom_providers ใหม่)",
          "cfg" in saved and "demo" in saved["cfg"].get("custom_providers", {}),
          saved.get("cfg"))

    # URL ผิด → เพิ่มไม่สำเร็จ ต้องคืน None แล้ววนกลับเมนู (ไม่ใช่เลือกค่ายหัวดำ)
    answers[:] = ["bad", "ftp://ไม่ใช่ http", "m1"]
    bad = S.add_custom_provider_flow({}, cfg_store)
    check("URL ผิด → เพิ่มไม่สำเร็จคืน None", bad is None, bad)
    check("ค่ายที่ URL ผิดไม่เข้าตาราง", "bad" not in P.PROVIDERS)

    # ยกเลิกกลางคัน (พิมพ์ว่าง) → None ไม่พัง
    answers[:] = ["", "", ""]
    check("พิมพ์ว่าง = ยกเลิก คืน None",
          S.add_custom_provider_flow({}, cfg_store) is None)
finally:
    (S.Prompt, S.CONFIG_FILE, S.fuzzy_pick, S.cmd_providers, S.ensure_key,
     S.ensure_local_server, S.pick_model, S.save_json) = orig[:8]
    P.PROVIDERS.clear()
    P.PROVIDERS.update(orig[8])
    P._CUSTOM_PROVIDER_IDS.clear()

# ---------- soonai setup: มีหัวข้อเพิ่มค่ายเองเหมือนเมนู /provider

def _run_setup(answers, fp_result, tag):
    """รัน cmd_setup จนจบในสภาพจำลอง — คืน (rc, cfg, saved, seen_items)"""
    cfg2 = {"provider": "ollama", "model": "", "custom_providers": {}}
    saved2, seen2 = {}, {}
    o = (S.Prompt, S.CONFIG_FILE, S.fuzzy_pick, S.cmd_providers, S.ensure_key,
         S.pick_model, S.setup_timeouts, S.scan_skills, S.save_json)
    seq = list(answers)
    try:
        S.CONFIG_FILE = os.path.join(
            tempfile.mkdtemp(prefix="soonai-setup-"), "config.json")
        S.save_json = lambda path, obj: saved2.update(
            {"cfg": dict(obj), "path": str(path)})
        S.Prompt = type("P", (), {"ask": staticmethod(lambda *a, **k: seq.pop(0))})
        def _fp(message, items):
            seen2["items"] = list(items)
            return fp_result
        S.fuzzy_pick = _fp
        S.cmd_providers = lambda *a, **k: 0
        S.ensure_key = lambda pid, keys: True
        S.pick_model = lambda pid, keys, **k: f"{pid}-model"
        S.setup_timeouts = lambda cfg=None: None
        S.scan_skills = lambda: True       # ข้ามขั้นติดตั้ง skill
        rc = S.cmd_setup(None, {}, cfg2)
        return rc, cfg2, saved2, seen2.get("items", [])
    finally:
        (S.Prompt, S.CONFIG_FILE, S.fuzzy_pick, S.cmd_providers, S.ensure_key,
         S.pick_model, S.setup_timeouts, S.scan_skills, S.save_json) = o

try:
    # A) tty: เลือกหัวข้อ ➕ ใน fuzzy (เหมือนเมนู /provider เป๊ะ)
    rc, cfg2, saved2, items = _run_setup(
        ["demo-a", "http://127.0.0.1:9/v1", "mA", "n", ""],
        S.ADD_PROVIDER_CHOICE, "A")
    check("setup (fuzzy): มีหัวข้อ เพิ่มค่ายเอง เหมือน /provider",
          any(v == S.ADD_PROVIDER_CHOICE and "เพิ่มค่ายเอง" in label
              for v, label in items), items)
    check("setup (fuzzy): เพิ่มเสร็จ + ตั้งค่าเสร็จ exit 0", rc == 0, rc)
    check("setup (fuzzy): ค่ายใหม่ถูกเลือก + โมเดลจาก pick_model",
          cfg2.get("provider") == "demo-a" and cfg2.get("model") == "demo-a-model",
          cfg2)
    check("setup (fuzzy): custom_providers ถูกบันทึก",
          "demo-a" in saved2.get("cfg", {}).get("custom_providers", {}),
          saved2.get("cfg"))

    # B) pipe: พิมพ์ "add" ในช่องเลือกค่าย (fuzzy ใช้ไม่ได้ = return None)
    rc, cfg2, saved2, _ = _run_setup(
        ["add", "demo-b", "http://127.0.0.1:9/v1", "mB", "n", ""],
        None, "B")
    check("setup (pipe): พิมพ์ add = เพิ่มค่ายเอง แล้วจบ setup exit 0",
          rc == 0, rc)
    check("setup (pipe): ค่ายใหม่ถูกเลือกถูกต้อง (ชื่อถูกย่อเป็น lower-case ให้)",
          cfg2.get("provider") == "demo-b" and cfg2.get("model") == "demo-b-model",
          cfg2)
    check("setup (pipe): demo-b เข้าตาราง PROVIDERS",
          P.PROVIDERS.get("demo-b", {}).get("base") == "http://127.0.0.1:9/v1",
          P.PROVIDERS.get("demo-b"))

    # C) guard เดิม: พิมพ์ค่ายไม่รู้จัก = exit 1 เหมือนเดิม
    rc, *_ = _run_setup(["nope-not-real"], None, "C")
    check("setup: พิมพ์ค่ายไม่รู้จักยัง exit 1 เหมือนเดิม", rc == 1, rc)
finally:
    P.PROVIDERS.clear()
    P.PROVIDERS.update(orig[8])
    P._CUSTOM_PROVIDER_IDS.clear()

# ---------- /connect: เลือก/เพิ่มค่าย + key + โมเดล + ทดสอบยิงจริง 1 รอบ
# ลงทะเบียนครบ 3 จุด: autocomplete · เมนูเลข · dispatch+help ในแชท
_ui_src = open("shared/ui_render.py", encoding="utf-8").read()
_chat_src = open("shared/chat.py", encoding="utf-8").read()
check("/connect อยู่ใน autocomplete + เมนูเลข (/) ครบ 2 จุด",
      _ui_src.count('"/connect"') >= 2, _ui_src.count('"/connect"'))
check("แชทมี dispatch /connect + บรรทัด help",
      "R.connect_provider" in _chat_src and "/connect เชื่อมต่อค่าย" in _chat_src)

cfg_c = {"provider": "openrouter", "model": "old-model", "custom_providers": {}}
o3 = (S.ensure_key, S.pick_model, S.save_json, S._connect_ping, S.fuzzy_pick,
      S.cmd_providers, S.ensure_local_server, S.Prompt, S.CONFIG_FILE)
cap = {}
try:
    S.CONFIG_FILE = "unused-config.json"   # save ถูก patch แล้ว ไม่เขียน config จริง
    S.save_json = lambda p, o: cap.update({"cfg": dict(o)})
    S.ensure_key = lambda p, k: True
    S.ensure_local_server = lambda p: True
    S.pick_model = lambda p, k, **kw: "m1"

    # เคส 1: /connect <ค่าย> — ping ผ่าน → ตั้งเป็นค่ายหลัก
    S._connect_ping = lambda pid, model: (True, "ok")
    r1 = S.connect_provider({}, cfg_c, "groq")
    check("/connect <ค่าย>: ping ผ่าน = ตั้งเป็นค่ายหลักทันที",
          r1 == ("groq", "m1") and cfg_c["provider"] == "groq"
          and cfg_c["model"] == "m1", (r1, cfg_c))
    check("/connect: save ค่ายหลักถูกบันทึก",
          cap.get("cfg", {}).get("provider") == "groq", cap.get("cfg"))

    # เคส 2: ค่ายไม่รู้จัก → None (ไม่เงียบ ขึ้นแดง + วิธีแก้)
    check("/connect ค่ายไม่รู้จัก → None",
          S.connect_provider({}, cfg_c, "nope-xyz") is None)

    # เคส 3: ping ไม่ผ่าน (ยังไม่ได้แตะค่ายหลัก) → None + คงค่ายเดิม
    cfg_c["provider"], cfg_c["model"] = "openrouter", "old-model"
    S._connect_ping = lambda pid, model: (False, "401: key ใช้ไม่ได้")
    check("/connect ping ไม่ผ่าน → None + คงค่ายเดิมไว้",
          S.connect_provider({}, cfg_c, "groq") is None
          and cfg_c["provider"] == "openrouter" and cfg_c["model"] == "old-model", cfg_c)

    # เคส 4: ไม่ใส่ arg = เมนู ➕เพิ่มค่ายเอง (switch) + ping fail
    #        → switch บันทึกไปแล้ว → ต้องย้อนกลับเป็นค่ายเดิม (atomic)
    seq4 = ["zz", "http://127.0.0.1:9/v1", "mz"]
    S.Prompt = type("P", (), {"ask": staticmethod(lambda *a, **k: seq4.pop(0))})
    S.fuzzy_pick = lambda *a, **k: S.ADD_PROVIDER_CHOICE
    S.cmd_providers = lambda *a, **k: 0
    S.pick_model = lambda p, k, **kw: "mz-model"
    r4 = S.connect_provider({}, cfg_c, "")
    check("/connect ไม่มี arg: ping fail → ย้อนกลับเป็นค่ายเดิม (ไม่ค้างค่ายพัง)",
          r4 is None and cfg_c["provider"] == "openrouter"
          and cfg_c["model"] == "old-model", (r4, cfg_c))
finally:
    (S.ensure_key, S.pick_model, S.save_json, S._connect_ping, S.fuzzy_pick,
     S.cmd_providers, S.ensure_local_server, S.Prompt, S.CONFIG_FILE) = o3
    P.PROVIDERS.clear()
    P.PROVIDERS.update(orig[8])
    P._CUSTOM_PROVIDER_IDS.clear()

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL CUSTOM PROVIDER TESTS PASSED")
