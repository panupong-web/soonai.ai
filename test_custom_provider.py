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

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL CUSTOM PROVIDER TESTS PASSED")
