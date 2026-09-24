# -*- coding: utf-8 -*-
"""
soonai_custom.py — ตัวช่วยปรับแต่ง SoonAI เพื่อใช้โมเดลแม่นยำสูง

วิธีใช้:
    python soonai_custom.py
"""

import sys
from pathlib import Path


def main():
    # Add shared directory to path
    script_dir = Path(__file__).parent
    shared_dir = script_dir / "shared"

    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))

    try:
        from core_utils.model_router import select_best_model, get_prompt_summary
        print("[OK] Model selector loaded successfully")

        # Load config
        import json
        config_file = shared_dir / "config.json"
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        print("\n[INFO] Config Summary:")
        print(f"  Default model: {config.get('model')}")
        print(f"  High-accuracy models: {list(config.get('models_high_accuracy', {}).keys())}")

        # Test selector
        test_prompts = [
            "สร้างระบบ login ด้วย FastAPI และ JWT",
            "เขียนฟังก์ชันบวกเลข 2 ตัว",
            "วิเคราะห์ architecture ของ microservices",
            "แก้โค้ดนี้ให้เร็วขึ้น"
        ]

        print("\n[TEST] Testing Model Selection:")
        for p in test_prompts:
            best_model = select_best_model(p, config, config.get('model'))
            print(f"  '{get_prompt_summary(p)}' -> {best_model}")

        print("\n[OK] Customization loaded!")
        print("[INFO] Use /smart command to enable high-accuracy mode")
        return 0

    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
