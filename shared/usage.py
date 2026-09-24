# -*- coding: utf-8 -*-
"""usage: นับ token/งบ context/ประเมินค่าใช้จ่าย

ย้ายมาจาก soonai.py (Step 1) — ตั้งแต่รอบ "ลด bind" อ่าน seam ผ่าน runtime
ด้วย attribute access (``R.USAGE``, ``R._kfmt``, ``R.load_config``) โดยไม่ต้อง
พึ่งการ bind ชื่อจาก soonai อีก: ``depgraph.py`` จึงรายงาน bind_refs = 0
"""
import os
import json
import threading as _threading

import runtime as R

_USAGE_LOCK = _threading.Lock()


def est_tokens(content):
    """ประมาณจำนวน token ของข้อความ (หรือของโครงสร้างที่ serialize เป็น JSON ได้)"""
    if content is None:
        return 0
    if isinstance(content, str):
        s = content
    else:
        try:
            s = json.dumps(content, ensure_ascii=False)
        except Exception:
            s = str(content)
    if not s:
        return 0
    ascii_n = 0
    for ch in s:
        if ord(ch) < 128:
            ascii_n += 1
    other = len(s) - ascii_n
    return int(ascii_n / 4 + other / 1.5) + 1
def messages_tokens(messages):
    """ประมาณ token ของทั้งชุดข้อความ (บวก overhead ต่อข้อความ)"""
    total = 0
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        total += 4 + est_tokens(m.get("content"))
        for tc in (m.get("tool_calls") or []):
            total += est_tokens(tc)
    return total
def usage_reset():
    with _USAGE_LOCK:
        R.USAGE.update({"calls": 0, "in": 0, "out": 0, "cost": 0.0})
def _pricing_cached(provider):
    """ราคาจาก cache ในเครื่องเท่านั้น (ไม่ยิงเน็ต)"""
    try:
        hit = R._read_models_cache().get(provider) or {}
        pr = hit.get("pricing")
        return pr if isinstance(pr, dict) else {}
    except Exception:
        return {}
def estimate_cost(provider, model, in_tokens, out_tokens):
    """ค่าใช้จ่ายโดยประมาณ (USD) จากราคาใน cache — ไม่รู้ราคา = 0"""
    pr = _pricing_cached(provider).get(model) or {}
    if not isinstance(pr, dict):
        return 0.0

    def _f(key):
        try:
            return float(pr.get(key) or 0)
        except Exception:
            return 0.0

    in_t, out_t = int(in_tokens or 0), int(out_tokens or 0)
    if pr.get("prompt") is not None:           # openrouter: USD ต่อ 1 token
        return _f("prompt") * in_t + _f("completion") * out_t
    if pr.get("hf_min_in") is not None:        # huggingface: USD ต่อ 1M token
        return (_f("hf_min_in") * in_t + _f("hf_min_out") * out_t) / 1e6
    if pr.get("puter_in") is not None:         # puter: เซนต์ต่อ 1M token
        return (_f("puter_in") * in_t + _f("puter_out") * out_t) / 1e8
    return 0.0
def usage_note(provider, model, in_tokens=0, out_tokens=0):
    """บันทึกการใช้ต่อหนึ่งรอบ + ประเมินค่าใช้จ่าย (ล็อกกันงานทีมขนานนับหาย)"""
    with _USAGE_LOCK:
        R.USAGE["calls"] += 1
        R.USAGE["in"] += int(in_tokens or 0)
        R.USAGE["out"] += int(out_tokens or 0)
        try:
            R.USAGE["cost"] += estimate_cost(provider, model, in_tokens, out_tokens)
        except Exception:
            pass
def _track_usage(provider, model, payload, out_text):
    """นับ token จาก payload ที่ส่งจริง + ข้อความตอบ (ใช้ร่วมทุกเส้นทาง)"""
    try:
        p = payload if isinstance(payload, dict) else {}
        in_t = messages_tokens(p.get("messages")) + est_tokens(p.get("system"))
        usage_note(provider, model, in_t, est_tokens(out_text))
    except Exception:
        pass
def usage_line(prefix="~"):
    """สรุปสั้น: '~12.3k tok เข้า/2.1k ออก · 3 calls · ~$0.0021' (ว่าง = ยังไม่ได้ใช้)"""
    if not R.USAGE["calls"]:
        return ""
    out = (f"{prefix}{R._kfmt(R.USAGE['in'])} tok เข้า/{R._kfmt(R.USAGE['out'])} ออก · "
           f"{R.USAGE['calls']} calls")
    if R.USAGE["cost"] > 0:
        out += f" · ~${R.USAGE['cost']:.4f}"
    return out
def context_budget():
    """งบ context (token) — config context_budget / SOONAI_CONTEXT_BUDGET (ค่าเริ่มต้น 24000)"""
    v = 0
    try:
        v = int(R.load_config().get("context_budget") or 0)
    except Exception:
        v = 0
    try:
        v = int(os.environ.get("SOONAI_CONTEXT_BUDGET") or v or 0)
    except Exception:
        pass
    return v if v > 1000 else 24000
def fit_messages(messages, budget=None):
    """ย่อประวัติให้อยู่ในงบ token — ตัดของเก่าสุดก่อน โดยไม่ตัดคู่ tool_call/tool_result
    คืน (ข้อความชุดใหม่, จำนวนข้อความที่ตัดออก)"""
    budget = int(budget or context_budget())
    msgs = list(messages or [])
    dropped = 0
    if not msgs or messages_tokens(msgs) <= budget:
        return msgs, 0
    while messages_tokens(msgs) > budget and len(msgs) > 2:
        idx = next((i for i, m in enumerate(msgs)
                    if isinstance(m, dict) and m.get("role") != "system"), None)
        if idx is None:
            break
        m = msgs[idx]
        ids = {tc.get("id") for tc in (m.get("tool_calls") or []) if isinstance(tc, dict)}
        had_calls = bool(ids)
        del msgs[idx]
        dropped += 1
        while ids and idx < len(msgs) and msgs[idx].get("role") == "tool" \
                and msgs[idx].get("tool_call_id") in ids:
            del msgs[idx]
            dropped += 1
        while had_calls and idx < len(msgs) and msgs[idx].get("role") == "tool":
            del msgs[idx]          # tool result ที่พ่อหายไปแล้ว = orphan
            dropped += 1
    return msgs, dropped
EFFORT_BUDGET = {"low": 4000, "medium": 10000, "high": 20000}
