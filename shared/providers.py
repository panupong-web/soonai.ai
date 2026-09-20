# -*- coding: utf-8 -*-
"""
ศูนย์รวม Provider AI ทั้งตลาดโลก (2026)
- ใช้มาตรฐาน OpenAI-compatible เป็นหลัก เพราะทุกเจ้าทำตามแล้ว
- ยกเว้น Anthropic ใช้ native API, Gemini รองรับทั้ง 2 แบบ
- Ollama / LM Studio = รันบนเครื่อง 100% ฟรี ไม่ต้องใช้ key
"""
import os

PROVIDERS = {
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "base": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "key_url": "https://platform.openai.com/api-keys",
        "models_url": "https://api.openai.com/v1/models",
        "type": "openai",
        "fallback_models": ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4.1-mini", "o4-mini"],
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "base": "https://api.anthropic.com/v1",
        "key_env": "ANTHROPIC_API_KEY",
        "key_url": "https://console.anthropic.com/settings/keys",
        "models_url": "https://api.anthropic.com/v1/models",
        "type": "anthropic",
        "fallback_models": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1", "claude-3-7-sonnet-latest"],
    },
    "gemini": {
        "name": "Google (Gemini)",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "key_url": "https://aistudio.google.com/apikey",
        "models_url": "native:gemini",
        "type": "openai",
        "tier_models": ["flash", "gemma", "lite"],
        "fallback_models": ["gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"],
    },
    "xai": {
        "name": "xAI (Grok)",
        "base": "https://api.x.ai/v1",
        "key_env": "XAI_API_KEY",
        "key_url": "https://console.x.ai/",
        "models_url": "https://api.x.ai/v1/models",
        "type": "openai",
        "fallback_models": ["grok-4", "grok-4-fast-non-reasoning", "grok-code-fast-1", "grok-3-mini"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "base": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "key_url": "https://platform.deepseek.com/api_keys",
        "models_url": "https://api.deepseek.com/v1/models",
        "type": "openai",
        "fallback_models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "mistral": {
        "name": "Mistral AI",
        "base": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
        "key_url": "https://console.mistral.ai/api-keys",
        "models_url": "https://api.mistral.ai/v1/models",
        "type": "openai",
        "fallback_models": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "open-mistral-nemo", "codestral-latest"],
    },
    "groq": {
        "name": "Groq (เร็ว+ฟรีเยอะ)",
        "base": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "key_url": "https://console.groq.com/keys",
        "models_url": "https://api.groq.com/openai/v1/models",
        "type": "openai",
        "is_free_tier": True,
        "pricing": "tier",
        "fallback_models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen-qwq-32b", "deepseek-r1-distill-llama-70b"],
    },
    "together": {
        "name": "Together AI",
        "base": "https://api.together.xyz/v1",
        "key_env": "TOGETHER_API_KEY",
        "key_url": "https://api.together.xyz/settings/api-keys",
        "models_url": "https://api.together.xyz/v1/models",
        "type": "openai",
        "fallback_models": ["meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8", "Qwen/Qwen3-235B-A22B-fp8-tput", "deepseek-ai/DeepSeek-R1", "mistralai/Mistral-Small-24B-Instruct-2501"],
    },
    "openrouter": {
        "name": "OpenRouter (รวม 300+ โมเดล, ฟรีเยอะสุด)",
        "base": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "key_url": "https://openrouter.ai/keys",
        "models_url": "https://openrouter.ai/api/v1/models",
        "type": "openai",
        "extra_headers": {"HTTP-Referer": "http://localhost:5000", "X-Title": "SoonAI-Universal-Chatbot"},
        "fallback_models": [
            "deepseek/deepseek-r1:free", "qwen/qwen3-235b-a22b:free",
            "meta-llama/llama-3.3-70b-instruct:free", "google/gemma-3-27b-it:free",
            "mistralai/mistral-small-3.1-24b-instruct:free", "x-ai/grok-4-fast:free",
            "z-ai/glm-4.5-air:free", "nvidia/nemotron-nano-9b-v2:free",
            "meta/muse-spark-1.3-contributor", "meta/muse-spark-1.2-contributor",
        ],
    },
    "cohere": {
        "name": "Cohere (Command R)",
        "base": "https://api.cohere.com/compatibility/v1",
        "key_env": "COHERE_API_KEY",
        "key_url": "https://dashboard.cohere.com/api-keys",
        "models_url": "https://api.cohere.com/v1/models",
        "type": "openai",
        "fallback_models": ["command-r-plus", "command-r", "command-a-03-2025"],
    },
    "perplexity": {
        "name": "Perplexity (ค้นเว็บ+ตอบ)",
        "base": "https://api.perplexity.ai",
        "key_env": "PERPLEXITY_API_KEY",
        "key_url": "https://www.perplexity.ai/settings/api",
        "models_url": "https://api.perplexity.ai/models",
        "type": "openai",
        "fallback_models": ["sonar-pro", "sonar", "sonar-reasoning-pro"],
    },
    "qwen": {
        "name": "Alibaba (Qwen)",
        "base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_env": "QWEN_API_KEY",
        "key_url": "https://bailian.console.aliyun.com/?apiKey=1#/api-key",
        "models_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models",
        "type": "openai",
        "fallback_models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen3-235b-a22b", "qwq-32b"],
    },
    "zhipu": {
        "name": "Zhipu (GLM)",
        "base": "https://open.bigmodel.cn/api/paas/v4",
        "key_env": "ZHIPU_API_KEY",
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "models_url": "https://open.bigmodel.cn/api/paas/v4/models",
        "type": "openai",
        "fallback_models": ["glm-4.6", "glm-4.5", "glm-4.5-air", "glm-4.5-flash"],
    },
    "moonshot": {
        "name": "Moonshot (Kimi)",
        "base": "https://api.moonshot.ai/v1",
        "key_env": "MOONSHOT_API_KEY",
        "key_url": "https://platform.moonshot.ai/console/api-keys",
        "models_url": "https://api.moonshot.ai/v1/models",
        "type": "openai",
        "fallback_models": ["kimi-k2-0905-preview", "kimi-k2-turbo-preview", "moonshot-v1-128k"],
    },
    "fireworks": {
        "name": "Fireworks AI",
        "base": "https://api.fireworks.ai/inference/v1",
        "key_env": "FIREWORKS_API_KEY",
        "key_url": "https://fireworks.ai/api-keys",
        "models_url": "https://api.fireworks.ai/inference/v1/models",
        "type": "openai",
        "fallback_models": ["accounts/fireworks/models/llama-v3p3-70b-instruct", "accounts/fireworks/models/qwen3-235b-a22b", "accounts/fireworks/models/deepseek-r1"],
    },
    "huggingface": {
        "name": "HuggingFace (ฟรี)",
        "base": "https://router.huggingface.co/v1",
        "key_env": "HF_TOKEN",
        "key_url": "https://huggingface.co/settings/tokens",
        "models_url": "https://router.huggingface.co/v1/models",
        "type": "openai",
        "is_free_tier": True,
        "pricing": "tier",
        "fallback_models": ["meta-llama/Llama-3.3-70B-Instruct", "Qwen/Qwen3-32B", "deepseek-ai/DeepSeek-R1", "google/gemma-3-27b-it", "mistralai/Mistral-Small-24B-Instruct-2501"],
    },
    "puter": {
        "name": "Puter (API ต้องมี subscription · ฟรีใช้บนเว็บ)",
        "base": "https://api.puter.com/puterai/openai/v1",
        "key_env": "PUTER_AUTH_TOKEN",
        "key_url": "https://puter.com/dashboard#account",
        "models_url": "https://api.puter.com/puterai/chat/models/details",
        "type": "openai",
        "is_free_tier": True,
        "pricing": "tier",
        "fallback_models": ["gpt-5-nano", "gpt-6-astra", "gpt-5.4-nano", "gpt-4o-mini", "gpt-4.1-mini", "o4-mini", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-3.1-flash-lite", "claude-opus-5", "claude-sonnet-5", "claude-fable-5-1", "claude-fable-5", "claude-opus-4-8", "claude-haiku-4-5-20251001", "grok-4.6", "grok-4.5", "deepseek-v4-pro-0813", "deepseek-v4-flash-0731", "qwen3.8-27b", "qwen3.8-max", "qwen3-235b-a22b", "zai-glm-5-2", "kimi-k2.7-code", "mistral-medium-2604"],
    },
    "ollama": {
        "name": "Ollama (รันบนเครื่อง 100% ฟรี)",
        "base": "http://localhost:11434/v1",
        "key_env": None,
        "key_url": "https://ollama.com/download",
        "models_url": "http://localhost:11434/api/tags",
        "type": "openai",
        "no_key": True,
        "is_free_tier": True,
        "fallback_models": ["llama3.1", "qwen3", "deepseek-r1", "gemma3", "mistral"],
    },
    "lmstudio": {
        "name": "LM Studio (รันบนเครื่อง)",
        "base": "http://localhost:1234/v1",
        "key_env": None,
        "key_url": "https://lmstudio.ai/",
        "models_url": "http://localhost:1234/v1/models",
        "type": "openai",
        "no_key": True,
        "is_free_tier": True,
        "fallback_models": ["local-model"],
    },
}

# ระดับราคา (ความจริง ไม่ใช่การเดา):
#   free = $0 แน่นอน (รันบนเครื่อง / OpenRouter pricing = 0)
#   tier = ใช้ฟรีได้ในโควต้า (Groq/Gemini-flash/HF/Puter ส่วนใหญ่มีลิมิต)
#   paid = เสียเงิน (ทุกค่ายที่เหลือ — ไม่แน่ใจให้ถือว่า paid ไว้ก่อน)
def price_tier(model_id: str, provider: str = "", pricing: dict = None) -> str:
    mid = (model_id or "").lower()
    cfg = PROVIDERS.get(provider, {})
    if provider in ("ollama", "lmstudio"):
        return "free"
    if provider == "openrouter":
        pr = (pricing or {}).get(model_id or "")
        if isinstance(pr, dict) and pr:
            try:
                if float(pr.get("prompt", 1)) == 0 and float(pr.get("completion", 1)) == 0:
                    return "free"
            except Exception:
                pass
            return "paid"
        return "free" if mid.endswith(":free") else "paid"
    if provider == "huggingface":
        pr = (pricing or {}).get(model_id or "")
        if isinstance(pr, dict) and "hf_free" in pr:
            return "free" if pr["hf_free"] else "tier"
        return "tier"
    if provider == "puter":
        pr = (pricing or {}).get(model_id or "")
        if isinstance(pr, dict) and ("puter_in" in pr or "puter_out" in pr):
            try:
                pin = float(pr.get("puter_in") or 0)
                pout = float(pr.get("puter_out") or 0)
            except Exception:
                return "tier"
            return "free" if (pin == 0 and pout == 0) else "tier"
        return "tier"
    mode = cfg.get("pricing", "paid")
    if mode == "free":
        return "free"
    if mode == "tier":
        return "tier"
    for k in cfg.get("free_models", []):
        if k in mid:
            return "free"
    for k in cfg.get("tier_models", []):
        if k in mid:
            return "tier"
    return "paid"


def is_free_model(model_id: str, provider: str = "", pricing: dict = None) -> bool:
    """ใช้ฟรีได้ (ฟรีจริง + tier) — ใช้กับตัวกรอง --free-only"""
    return price_tier(model_id, provider, pricing) in ("free", "tier")


def price_str(provider: str, model_id: str, pricing: dict = None) -> str:
    """ราคาจริงจาก API เป็นข้อความสั้น ('$1.25/M', '$0/M', '' ถ้าไม่มีข้อมูล)"""
    try:
        pr = (pricing or {}).get(model_id or "")
        if not isinstance(pr, dict):
            return ""
        if provider == "openrouter" and "prompt" in pr:
            return f"${float(pr['prompt']) * 1e6:g}/M"
        if provider == "huggingface" and pr.get("hf_min_in") is not None:
            return f"${float(pr['hf_min_in']):g}/M"
        if provider == "puter" and pr.get("puter_in") is not None:
            return f"${float(pr['puter_in']) / 100:g}/M"
    except Exception:
        pass
    return ""


def model_label(model_id: str, provider: str = "", pricing: dict = None) -> str:
    """ป้ายโมเดลพร้อมราคา: 'name  [Free $0/M]' / '[tier]' / '[paid $3/M]'"""
    tier = price_tier(model_id, provider, pricing)
    tag = {"free": "Free", "tier": "tier"}.get(tier, "paid")
    p = price_str(provider, model_id, pricing)
    return f"{model_id}  [{tag}{(' ' + p) if p else ''}]"


def get_key(provider_key: str, runtime_keys: dict) -> str:
    """ดึง key จาก: 1) ที่ผู้ใช้กรอกใน UI 2) environment/.env"""
    if provider_key in runtime_keys and runtime_keys[provider_key]:
        return runtime_keys[provider_key]
    cfg = PROVIDERS.get(provider_key, {})
    env_name = cfg.get("key_env")
    if env_name:
        return os.environ.get(env_name, "")
    return ""
