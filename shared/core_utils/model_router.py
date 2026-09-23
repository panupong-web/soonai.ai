# -*- coding: utf-8 -*-
"""core_utils/model_router.py — เลือกโมเดล AI อัจฉริยะตามบริบทงาน

ระบบจะวิเคราะห์ prompt และเลือก:
1. โมเดลที่แม่นยำสูง (deepseek-chat, gemini-flash, mistral-large)
2. โมเดล Ollama บนเครื่อง (llama3.1, qwen3, deepseek-r1, ฯลฯ)
3. หรือใช้ default (cohere-north-mini) เมื่องานง่าย/ไม่ซับซ้อน

การวิเคราะห์:
- ความยาว prompt (ตัวอักษร)
- รูปแบบคำถาม (ด้วย regex)
- จำนวนตัวแปร/โครงสร้างซับซ้อน
"""

import re
from typing import Dict, List


def count_thai_chars(text: str) -> int:
    """นับตัวอักษรภาษาไทย"""
    return len(re.findall(r'[\u0E00-\u0E7F]', text))


def analyze_complexity(prompt: str, config: Dict) -> dict:
    """
    วิเคราะห์ความซับซ้อนของ prompt
    Returns: {
        "is_complex": bool,
        "complexity_score": int (0-100),
        "reasoning_needed": bool,
        "code_related": bool,
        "recommend_model": str
    }
    """
    score = 0

    # 1. Length factor (นับทั้งไทยและอังกฤษ)
    total_length = len(prompt)

    if total_length > config.get("model_routing", {}).get("complexity_threshold", 150):
        score += 40

    # 2. Pattern matching (จาก config)
    patterns = config.get("model_routing", {}).get("use_high_accuracy_patterns", [])
    for pattern in patterns:
        if re.search(pattern, prompt, re.IGNORECASE):
            score += 30
            break

    # 3. Code complexity indicators
    code_indicators = [
        r"\bdef\s+\w+", r"class\s+\w+", r"if __name__",
        r"try:\s*$", r"except.*:", r"for.*in.*:",
        r"#.*TODO", r"#.*FIXME", r"debug", r"refactor"
    ]
    for pattern in code_indicators:
        if re.search(pattern, prompt):
            score += 20
            break

    # 4. Thai-specific complexity (การอธิบายแนวคิดลึก)
    deep_thai_patterns = [
        r"\bอธิบาย\b.*\bแนวคิด\b",
        r"\bvision\b.*\barchitecture\b",
        r"\bwriting.*complex.*code\b"
    ]
    for pattern in deep_thai_patterns:
        if re.search(pattern, prompt, re.IGNORECASE):
            score += 20
            break

    # 5. Thai-specific: การวิเคราะห์เชิงลึก
    deep_analysis_keywords = ["วิเคราะห์", "เปรียบเทียบ", "แนวคิดหลัก"]
    if any(kw in prompt for kw in deep_analysis_keywords):
        score += 15

    # 6. Thai-specific: การแก้ปัญหาซับซ้อน
    problem_solving_keywords = ["แก้บั๊ก", "ปรับปรุง", "เพิ่มประสิทธิภาพ"]
    if any(kw in prompt for kw in problem_solving_keywords):
        score += 15

    # Determine if reasoning needed (and thus high-accuracy model)
    is_complex = score >= 40
    code_related = bool(re.search(r"\bโค้ด\b|\bcode\b|\bfunction\b|\bdef\b", prompt, re.IGNORECASE))

    return {
        "is_complex": is_complex,
        "complexity_score": min(score, 100),
        "reasoning_needed": score >= 50 or code_related,
        "code_related": code_related,
        "recommend_model": "deepseek/deepseek-chat:v3" if (score >= 45 and code_related)
                            else "google/gemini-2.0-flash-exp:free" if is_complex
                            else None  # use default
    }


def select_best_model(prompt: str, config: Dict, current_model: str) -> str:
    """
    เลือกโมเดลที่ดีที่สุดสำหรับ prompt
    ถ้าไม่มีอะไรซับซ้อน → ใช้ default model (ประหยัด)

    รองรับ:
    - โมเดล cloud (OpenRouter, OpenAI, Gemini, ฯลฯ)
    - โมเดล Ollama บนเครื่อง
    - โมเดล groq/huggingface ฟรี
    """
    analysis = analyze_complexity(prompt, config)

    # If not complex, use current (default) model
    if not analysis["is_complex"]:
        return current_model

    models = config.get("models_high_accuracy", {})

    # Check if Ollama is available and prefer local for complex tasks
    ollama_models = config.get("ollama_models", {})
    use_ollama = bool(ollama_models) and analysis["code_related"]

    # Priority: Code expert > Reasoning > Multilingual > Fast chat > Ollama
    if analysis["code_related"]:
        return (models.get("code_expert")
                or models.get("code_command_r")
                or models.get("deepseek_coder")
                or models.get("fast_reasoning")
                or models.get("multilingual_pro")
                or (list(ollama_models.values())[0] if use_ollama else None)
                or models.get("groq_fast")
                or current_model)
    elif analysis["reasoning_needed"]:
        return (models.get("reasoning_master")
                or models.get("fast_reasoning")
                or models.get("code_expert")
                or models.get("deepseek_coder")
                or models.get("multilingual_pro")
                or models.get("fast_chat")
                or current_model)
    else:
        # Fallback for general complex tasks
        return (models.get("multilingual_pro")
                or models.get("fast_chat")
                or models.get("gemini_fallback")
                or models.get("huggingface_free")
                or models.get("groq_fast")
                or current_model)


def list_all_models(config: Dict) -> List[str]:
    """รายการโมเดลทั้งหมดที่พร้อมใช้งาน จาก config ทุกหมวด"""
    seen = set()
    result = []

    # models_high_accuracy
    high_acc = config.get("models_high_accuracy", {})
    for name, model_id in high_acc.items():
        if model_id not in seen:
            seen.add(model_id)
            result.append(model_id)

    # ollama_models
    ollama = config.get("ollama_models", {})
    for name, model_id in ollama.items():
        if model_id not in seen:
            seen.add(model_id)
            result.append(model_id)

    # all_models (per provider)
    all_m = config.get("all_models", {})
    for provider, model_list in all_m.items():
        for model_id in model_list:
            if model_id not in seen:
                seen.add(model_id)
                result.append(f"{provider}/{model_id}" if "/" not in model_id else model_id)

    return result


def list_models_by_provider(config: Dict, provider: str) -> List[str]:
    """รายการโมเดลของ provider เฉพาะ"""
    all_m = config.get("all_models", {})
    if provider in all_m:
        return all_m[provider]
    if provider == "ollama":
        return list(config.get("ollama_models", {}).values())
    return []


def get_free_models(config: Dict) -> List[str]:
    """รายการโมเดลฟรี (Ollama + OpenRouter free + HuggingFace)"""
    free = []

    # Ollama models
    ollama = config.get("ollama_models", {})
    free.extend(ollama.values())

    # OpenRouter free models
    or_models = config.get("all_models", {}).get("openrouter", [])
    for m in or_models:
        if ":free" in m:
            free.append(m)

    # HuggingFace free/tier models
    hf_models = config.get("all_models", {}).get("huggingface", [])
    free.extend(hf_models)

    # Groq free
    groq_models = config.get("all_models", {}).get("groq_free", [])
    free.extend(groq_models)

    return free


def get_model_category(model_id: str, config: Dict) -> str:
    """ระบุหมวดหมู่ของโมเดล (cloud, ollama, free, etc.)"""
    ollama_models = config.get("ollama_models", {})
    if model_id in ollama_models.values():
        return "ollama"

    or_models = config.get("all_models", {}).get("openrouter", [])
    if model_id in or_models:
        if ":free" in model_id:
            return "free"
        return "cloud"

    free_models = get_free_models(config)
    if model_id in free_models:
        return "free"

    return "cloud"


def get_prompt_context_summary(prompt: str, max_chars: int = 80) -> str:
    """สรุป prompt เป็นชื่อสั้นๆ (สำหรับ log)"""
    clean = re.sub(r'\s+', ' ', prompt.strip())
    return (clean[:max_chars] + "..." if len(clean) > max_chars else clean)


def get_prompt_summary(prompt: str, max_chars: int = 80) -> str:
    """alias สำหรับโค้ดเก่า — ใช้ get_prompt_context_summary แทน"""
    return get_prompt_context_summary(prompt, max_chars)


# ตัวอย่างการใช้งาน
if __name__ == "__main__":
    test_config = {
        "model_routing": {
            "complexity_threshold": 150,
            "use_high_accuracy_patterns": [
                "^สร้าง.*ระบบ", "^เขียน.*โค้ด.*ซับซ้อน", "^แก้บั๊ก.*ลึก"
            ]
        },
        "models_high_accuracy": {
            "code_expert": "deepseek/deepseek-chat:v3",
            "reasoning_master": "google/gemini-2.0-flash-exp:free"
        },
        "ollama_models": {
            "llama3.1": "llama3.1",
            "qwen3": "qwen3",
            "deepseek-r1": "deepseek-r1"
        },
        "all_models": {
            "openai": ["gpt-5", "gpt-4.1", "o4-mini"],
            "ollama": ["llama3.1", "qwen3", "deepseek-r1"]
        }
    }

    prompts = [
        "สร้างระบบ login ด้วย FastAPI และ JWT",
        "เขียนฟังก์ชันบวกเลข 2 ตัว",
        "วิเคราะห์ architecture ของ microservices",
        "แก้โค้ดนี้ให้เร็วขึ้น"
    ]

    print("=== Model Routing Demo ===")
    for p in prompts:
        result = analyze_complexity(p, test_config)
        best_model = select_best_model(p, test_config, "cohere/north-mini-code:free")
        print(f"Prompt: {get_prompt_context_summary(p)}")
        print(f"  → Complexity: {result['complexity_score']}, Model: {best_model}")
        print()

    print(f"\nAll models ({len(list_all_models(test_config))}):")
    for m in list_all_models(test_config)[:10]:
        print(f"  - {m}")
