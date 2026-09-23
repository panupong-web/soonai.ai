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

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL CUSTOM PROVIDER TESTS PASSED")
