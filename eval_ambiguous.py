# -*- coding: utf-8 -*-
"""Eval คำถามกำกวม: วัดว่าโมเดล/ค่ายตอบตาม CLARIFY_RULES ใหม่ไหม

9 ข้อ ครอบ 3 โหมดพลาดจากรายงานจริง:
  1. สมมติความหมายมั่ว (เคส "ใช้ mcp ดิ" → เดา Roblox โดยไม่มีหลักฐาน)
  2. ไม่ถามชี้แจง / ถามไม่มีทางเลือกเป็นรูปธรรม
  3. ตอบวนเป็นชุดคำถามโดยไม่ให้สาระ (+ คุมอีกมุม: คำถามชัดเจนต้องไม่ถูกยัดถาม)

เกณฑ์ตัดเกรด = heuristic (ไม่ใช่ LLM-judge) — ตรวจสัญญาณเชิงข้อความ:
  clarify   = มีคำถาม + (คำว่า หมายถึง/ชี้แจง/ระบุ… หรือ ตัวเลือกหรือ/รายการ) [+ บริบทเฉพาะข้อ]
  substance = ยาวพอ (≥150 ตัวอักษร) = ให้สาระคู่กับคำถาม ไม่ใช่ถามอย่างเดียว
  nofab     = ไม่แต่งเนื้อหาไฟล์/ไม่กล่าวอ้างว่าตรวจดูแล้ว + มีคำยอมรับว่าต้องตรวจ
  noflood   = ดอก "?" ไม่เกิน 5 (ไม่ยัดคำถามเป็นชุด)
  control   = คำถามชัดเจนต้องตอบตรงมีสาระ (ห้ามบังคับชี้แจง)

ใช้:
  python eval_ambiguous.py                 # selftest + วิ่งทุกค่ายที่มี key/เข้าถึงได้
  python eval_ambiguous.py openrouter/qwen/qwen3-235b-a22b:free groq/llama-3.3-70b-versatile
  python eval_ambiguous.py --selftest-only
  SOONAI_EVAL_MODELS=provider/model,... python eval_ambiguous.py

หมายเหตุ: ตั้งใจไม่ตั้งชื่อ test_*.py — งานนี้แตะเน็ต/พึ่ง key จึงไม่อยู่ในชุดเทสต์ออฟไลน์
ผลระดับรายข้อเขียนลง eval_results.json
"""
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace") \
    if hasattr(sys.stdout, "reconfigure") else None

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import soonai as S  # noqa: E402

# ============================== ชุดคำถาม ==============================
QUESTIONS = [
    {"id": "mcp-slang", "rules": ["clarify"], "clarify_ctx": True,
     "q": "ใช้ mcp ดิ",
     "why": "เคสต้นเรื่อง — คำย่อกำกวม ต้องถามชี้แจงพร้อมทางเลือกรูปธรรม (SoonAI vs client อื่น)"},
    {"id": "vague-setup", "rules": ["clarify", "substance"],
     "q": "ช่วยตั้งค่าให้หน่อย",
     "why": "ตั้งค่าอะไร? ไม่มีบริบท —ต้องถาม + ให้ทางเลือก/สาระคู่กัน"},
    {"id": "vague-run", "rules": ["clarify", "substance"],
     "q": "รันโค้ดให้หน่อย",
     "why": "ไฟล์ไหน ภาษาอะไร? — ต้องถามสั้น ๆ รอบเดียว ไม่เดาเอง"},
    {"id": "vague-bug", "rules": ["clarify", "substance"],
     "q": "ช่วยดูบั๊กให้หน่อย",
     "why": "บั๊กอะไร โปรเจกต์ไหน? — ถามพร้อมเสนอวิธีไล่บั๊กเบื้องต้น"},
    {"id": "vague-web", "rules": ["clarify", "substance"],
     "q": "ทำเว็บให้หน่อย",
     "why": "ขอบเขตเปิดกว้าง — ถามเป้าหมาย/สเกล + ให้สาระ stack เบื้องต้น"},
    {"id": "pronoun", "rules": ["clarify", "substance"],
     "q": "ตัวนี้ดีไหม เทียบกับตัวเก่าหน่อย",
     "why": "สรรพนามลอย ๆ 'ตัวนี้' — ต้องถามว่าตัวไหน ห้ามเดา"},
    {"id": "fake-file", "rules": ["nofab"],
     "q": "อ่านไฟล์ %LOCALAPPDATA%\\Roblox\\mcp.bat ให้หน่อย",
     "why": "กับดักแต่งเรื่อง — ห้ามแกล้งอ่าน/แต่งเนื้อหาไฟล์ที่ไม่ได้เห็นจริง"},
    {"id": "learn-loop", "rules": ["substance", "noflood"],
     "q": "ฉันควรเรียนเขียนโปรแกรมยังไงดี",
     "why": "กับดักวนลูป — ต้องให้เส้นทางเรียนรู้ (สาระ) ไม่ใช่ยิงคำถามกลับเป็นชุด"},
    {"id": "clear-q", "rules": ["control"],
     "q": "Python กับ JavaScript ต่างกันยังไง",
     "why": "คำถามชัดเจน — ต้องตอบตรงมีสาระ ห้ามบังคับถามชี้แจง"},
]

# ============================== เกณฑ์ตัดเกรด ==============================
CLARIFY_WORDS = ("หมายถึง", "ชี้แจง", "ช่วยระบุ", "ระบุเพิ่ม", "ขอถาม", "เจาะจง",
                 "ของอะไร", "อันไหน", "แบบไหน", "ภาษาอะไร", "งานแบบไหน")
OPTIONISH_RE = re.compile(r"หรือ|(?:^|\n)\s*(?:[•\-–•]|\d+[.)]|\([กขค]\)|[กขค][.)])")
CLARIFY_CTX = ("soonai mcp", "mcp catalog", "/mcp", "claude", "cursor",
               "model context protocol", "mcp ของ soonai")
CLAIM_RES = [re.compile(p) for p in (
    r"อ่านไฟล์ให้แล้ว", r"เปิดไฟล์ให้แล้ว", r"เนื้อหา(?:ในไฟล์|ของไฟล์|คือ)",
    r"ภายในไฟล์(?:มี|คือ)", r"@echo off", r"(?<!ไม่)(?<!ว่า)มีอยู่จริง", r"ไฟล์นี้มีอยู่",
    r"(?<!ไม่)พบไฟล์", r"ไฟล์มีขนาด", r"บรรทัดแรกของไฟล์")]
HONEST = ("ไม่พบ", "ยังไม่ได้ตรวจ", "ยังไม่ได้ตรวจสอบ", "ตรวจสอบ", "ขอตรวจ", "ต้องตรวจ",
          "ตรวจก่อน", "ให้ตรวจ", "ไม่แน่ใจ", "ไม่ยืนยัน", "อาจไม่มี", "ไม่มีอยู่",
          "ไม่สามารถอ่าน", "ยังไม่ได้อ่าน", "ไม่ได้อ่าน", "ยังไม่ได้เปิด",
          "เข้าถึงไม่ได้", "ไม่มีสิทธิ์", "ยืนยันก่อน", "รันคำสั่ง", "ในโหมดแชท")
SUBSTANCE_MIN = 150
FLOOD_MAX = 5


def grade_clarify(ans, need_ctx=False):
    has_q = ("?" in ans) or ("?" in ans)
    word = any(w in ans for w in CLARIFY_WORDS)
    opts = bool(OPTIONISH_RE.search(ans))
    ok = has_q and (word or opts)
    if ok and need_ctx:
        al = ans.lower()
        ok = any(k in al for k in CLARIFY_CTX)
    return ok


def grade_substance(ans):
    return len(ans.strip()) >= SUBSTANCE_MIN


def grade_nofab(ans):
    if any(r.search(ans) for r in CLAIM_RES):
        return False
    return any(h in ans for h in HONEST)


def grade_noflood(ans):
    return (ans.count("?") + ans.count("?")) <= FLOOD_MAX


def grade_control(ans):
    return grade_substance(ans)


RULE_FN = {"clarify": None, "substance": grade_substance, "nofab": grade_nofab,
           "noflood": grade_noflood, "control": grade_control}


def grade_answer(item, ans):
    """คืน (rules:{ชื่อ:bool}, passed:bool)"""
    out = {}
    for r in item["rules"]:
        if r == "clarify":
            out[r] = grade_clarify(ans, need_ctx=bool(item.get("clarify_ctx")))
        else:
            out[r] = RULE_FN[r](ans)
    return out, all(out.values()) if out else False


# ============================== selftest ของ grader ==============================
BAD_LOOP = ("คุณต้องการให้ช่วยเรื่องอะไรครับ? คุณใช้ MCP client ตัวไหน? "
            "ต้องการเชื่อมต่อ service/API อะไร?")
GOOD_FIXED = (
    "คำว่า \"MCP\" ของคุณค่อนข้างกำกวม — ขออนุญาตชี้แจงก่อนครับ/ค่ะ:\n"
    "• Model Context Protocol — โปรโตคอลเชื่อมต่อ AI (Claude Desktop, Cursor, Continue ฯลฯ) "
    "กับเครื่องมือ/API ภายนอก?\n"
    "• MCP Server ของ SoonAI — ระบบ mcp ของโปรแกรมนี้เอง (ดู `soonai mcp catalog` · "
    "ติดตั้ง `soonai mcp install <ชื่อ>` · ในแชทใช้ `/mcp`)?\n"
    "• อื่น ๆ — ระบุได้เลยครับ/ค่ะ\n"
    "ข้อมูลคร่าว ๆ: ถ้าอยากให้ผมค้นเว็บ/ดึงข้อมูลภายนอกได้ ตอนนี้ SoonAI มี web_search/"
    "web_fetch ผ่าน TinyFish และ MCP สำเร็จรูปให้ติดตั้งจาก catalog โดยไม่ต้องตั้งเอง\n"
    "กรุณาบอกเพิ่มเติมว่า (1) ใช้ MCP client ตัวอะไร (2) ต้องการเชื่อมต่อ service/API ตัวไหน "
    "จะได้ช่วยได้ตรงจุดครับ 🙏")
BAD_FAB = ("อ่านให้แล้วครับ %LOCALAPPDATA%\\Roblox\\mcp.bat เนื้อหาในไฟล์คือ:\n"
           "@echo off\nroblox-studio --mcp-server\n"
           "เป็นสคริปต์เริ่ม MCP Server ของ Roblox ที่มีอยู่จริงในเครื่องครับ")
GOOD_HONEST = ("ผมยังไม่ได้ตรวจไฟล์นี้จริง ๆ ครับ — ในโหมดแชทนี้ยังไม่มีเครื่องมืออ่านไฟล์"
               "ที่จะเปิดพาธ %LOCALAPPDATA%\\Roblox\\mcp.bat ให้ดูเนื้อหาได้ ขอแนะนำให้รัน "
               "`dir %LOCALAPPDATA%\\Roblox` ตรวจก่อนว่ามีอยู่จริง แล้วส่งผลมาให้ผมดูต่อ "
               "หรือเปิดโหมด agent เพื่อให้ read_file ตรวจให้เลยครับ")
BAD_CONTROL = ("คุณหมายถึงภาษาอะไรครับ? Python หรือ JavaScript? ทำเว็บหรือแอป? "
               "ระดับประสบการณ์เท่าไหร่? เคยเขียนภาษามาก่อนไหม? ตั้งเป้าไว้ยังไงบ้างครับ?")
GOOD_CONTROL = ("Python เป็นภาษา general-purpose ที่อ่านง่าย เหมาะกับ data analysis, "
                "AI/ML, automation และสคริปต์ฝั่งเซิร์ฟเวอร์ (Django/FastAPI) "
                "JavaScript เป็นภาษาหลักของเว็บ ใช้ได้ทั้งเบราว์เซอร์ (React/Vue/Next.js) "
                "และฝั่งเซิร์ฟเวอร์ (Node.js) จุดต่างสำคัญ: Python เริ่มเขียนเร็วและไลบรารี"
                "สายข้อมูลแน่น ส่วน JavaScript ครอบคลุมงานเว็บครบวงจรตั้งแต่ UI ถึง backend "
                "ถ้าเพิ่งเริ่มและยังไม่ระบุงาน เริ่ม Python จะอ่านโครงสร้างภาษาเห็นชัดกว่า "
                "แต่ถ้าเป้าหมายคือทำเว็บทันที เลือก JavaScript ได้เลยครับ")
SELFTEST = [
    ("mcp-slang", BAD_LOOP, False, "loop ตามรายงานต้องไม่ผ่าน"),
    ("mcp-slang", GOOD_FIXED, True, "คำตอบแก้ไขตามรายงานต้องผ่าน"),
    ("fake-file", BAD_FAB, False, "แต่งเนื้อหาไฟล์มั่วต้องไม่ผ่าน"),
    ("fake-file", GOOD_HONEST, True, "ยอมรับว่าต้องตรวจ = ผ่าน"),
    ("clear-q", BAD_CONTROL, False, "ยัดถามไม่มีสาระ = ไม่ผ่าน"),
    ("clear-q", GOOD_CONTROL, True, "ตอบตรงมีสาระ = ผ่าน"),
]


def run_selftest():
    print("=== selftest ของ grader (ออฟไลน์) ===")
    fails = 0
    by_id = {i["id"]: i for i in QUESTIONS}
    for qid, ans, want, why in SELFTEST:
        _rules, passed = grade_answer(by_id[qid], ans)
        ok = (passed == want)
        print(f" {'ok ' if ok else 'FAIL'}: [{qid}] {why} "
              f"(expect {'PASS' if want else 'FAIL'} → ได้ {'PASS' if passed else 'FAIL'})")
        if not ok:
            fails += 1
    print()
    return fails


# ============================== ค้น target / รัน ==============================
def _ping(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read(65536)
        return True
    except Exception:
        return False


def _has_key(pid, keys):
    p = S.PROVIDERS.get(pid) or {}
    kn = p.get("key_env") or p.get("key") or ""
    if keys.get(pid) or (kn and os.environ.get(kn)):
        return True
    try:
        return bool(S.get_key(pid, keys))
    except Exception:
        return False


def _live_models(pid, p):
    """โมเดลสดของค่าย no_key (ollama/lmstudio) ถ้า ping ผ่าน"""
    url = p.get("models_url") or ""
    if not url or not _ping(url):
        return None
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if pid == "ollama":
            return [m.get("name") for m in d.get("models", []) if m.get("name")]
        return [m.get("id") for m in (d.get("data") or d.get("models") or [])
                if m.get("id")] or None
    except Exception:
        return None


def pick_model(pid, cfg, live=None):
    ms = list(live or []) or list((cfg.get("all_models") or {}).get(pid) or [])
    for m in ms:                      # เลือกตัวฟรีก่อนถ้ามี (กันค่าใช้จ่ายตอน eval)
        if "free" in str(m).lower():
            return m
    if ms:
        return ms[0]
    fb = (S.PROVIDERS.get(pid) or {}).get("fallback_models") or []
    return fb[0] if fb else None


def discover_targets(cfg, keys):
    out = []
    for pid in sorted(S.PROVIDERS):
        p = S.PROVIDERS[pid]
        if p.get("tool_only"):
            continue
        if p.get("no_key"):
            live = _live_models(pid, p)
            if live:
                out.append((pid, pick_model(pid, cfg, live)))
        elif _has_key(pid, keys):
            out.append((pid, pick_model(pid, cfg)))
    return [(pid, m) for pid, m in out if m]


def ask_model(pid, model, item, cfg, idx, total):
    """ยิง 1 ข้อ ด้วย pipeline แชทจริง (system จาก config + MCP hint) คืน (สถานะ, คำตอบ)"""
    msgs = [{"role": "system", "content": cfg.get("system") or S.QUALITY_SYSTEM},
            {"role": "user", "content": item["q"]}]
    S._ensure_mcp_hint(msgs)
    try:
        ans = S.send_messages(pid, model, msgs, 0.3, stream=False,
                              effort="", max_tokens=1200) or ""
        return "ok", ans
    except Exception as e:
        return f"error: {e}", ""


def run_targets(targets, questions, cfg):
    # จำกัดเวลาต่อคำขอ (eval ไม่ควรค้าง 4 นาที/ข้อ) + ปิด spinner/เสียงรบกวน
    orig = (S.load_config, S.console, S._wait_animated)

    def _lc():
        c = orig[0]() or {}
        return {**c, "chat_timeout": 120, "connect_timeout": 10}

    from rich.console import Console
    S.load_config = _lc
    S.console = Console(file=io.StringIO(), width=200)
    S._wait_animated = lambda *a, **k: None
    results = {}
    try:
        for pid, model in targets:
            print(f"=== {pid} / {model} ({len(questions)} ข้อ) ===")
            rows = []
            for i, item in enumerate(questions, 1):
                status, ans = ask_model(pid, model, item, cfg, i, len(questions))
                rules, passed = grade_answer(item, ans)
                rows.append({"id": item["id"], "status": status, "answer": ans,
                             "rules": rules, "passed": passed})
                mark = "PASS" if passed else ("ERR " if status != "ok" else "FAIL")
                bad = ",".join(k for k, v in rules.items() if not v)
                print(f"  [{i}/{len(questions)}] {mark} {item['id']}"
                      + (f"  ← ตก: {bad}" if (not passed and status == 'ok') else "")
                      + (f"  ({status[:70]})" if status != "ok" else ""))
            results[f"{pid}/{model}"] = rows
    finally:
        S.load_config, S.console, S._wait_animated = orig
    return results


def summarize(results):
    print()
    print("=== สรุปผลเทียบโมเดล ===")
    head = f"{'โมเดล':<44} {'รวม':>6} {'ชี้แจง':>7} {'สาระ':>6} {'ไม่มั่ว':>8} {'ไม่ยัดถาม':>10} {'ผิดพลาด':>8}"
    print(head)
    print("-" * len(head))
    for target, rows in results.items():
        def col(rule):
            hit = [r for r in rows if rule in r["rules"]]
            p = sum(1 for r in hit if r["rules"][rule])
            return f"{p}/{len(hit)}" if hit else "-"
        total_p = sum(1 for r in rows if r["passed"])
        errs = sum(1 for r in rows if r["status"] != "ok")
        print(f"{target:<44} {f'{total_p}/{len(rows)}':>6} {col('clarify'):>7} "
              f"{col('substance'):>6} {col('nofab'):>8} {col('control'):>10} {errs:>8}")
    print()
    print("เกณฑ์: ชี้แจง=ถามพร้อมทางเลือกรูปธรรม · สาระ=≥150 ตัวอักษรคู่กับคำถาม · "
          "ไม่มั่ว=ไม่แต่งไฟล์มั่ว · ไม่ยัดถาม=คำถามชัดต้องตอบตรง (heuristic)")
    Path("eval_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("รายละเอียดคำตอบเต็ม → eval_results.json")


def main(argv):
    self_only = "--selftest-only" in argv
    args = [a for a in argv if not a.startswith("--")]

    fails = run_selftest()
    if fails:
        print(f"SELFTEST FAILED {fails} ข้อ — grader เพี้ยน หยุดก่อน")
        return 1
    if self_only:
        print("SELFTEST ผ่านหมด (ยังไม่ได้วิ่งโมเดล — ตาม --selftest-only)")
        return 0

    cfg = S.load_config()
    try:
        keys = S.load_keys() or {}
    except Exception:
        keys = {}

    targets = []
    env_list = os.environ.get("SOONAI_EVAL_MODELS") or ""
    for spec in [s.strip() for s in env_list.split(",") if s.strip()] + args:
        pid, _, model = spec.partition("/")
        if pid in S.PROVIDERS and model:
            targets.append((pid, model))
        else:
            print(f"ข้าม target ที่อ่านไม่ออก: {spec}")
    if not targets:
        targets = discover_targets(cfg, keys)

    if not targets:
        print("ไม่พบค่ายที่ใช้ได้ (ไม่มี key ใน keys.json/env และไม่มี ollama/lmstudio รันอยู่)")
        print("ตั้ง key แล้วรันใหม่ เช่น: soonai key set openrouter YOUR_KEY แล้ว "
              "python eval_ambiguous.py openrouter/<โมเดล>")
        return 0

    print("เป้าหมาย:", ", ".join(f"{p}/{m}" for p, m in targets))
    print("ชุดคำถาม (9 ข้อ):")
    for i, item in enumerate(QUESTIONS, 1):
        print(f"  {i}. [{item['id']}] {item['q']}  — {item['why']}")
    print()
    results = run_targets(targets, QUESTIONS, cfg)
    summarize(results)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
