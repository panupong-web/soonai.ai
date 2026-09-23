# -*- coding: utf-8 -*-
"""Regression: dependency graph (depgraph.py)
- ไม่มี import cycle ระหว่างโมดูล
- ไม่มี bind cycle (โมดูลย่อยพึ่งกันไปมา) — ขอบเขตต้องเป็น DAG
- soonai import โมดูลที่แยกออกครบ + ทิศทางการพึ่งถูก (symbols -> project)
- โหมด --plan: จัดกลุ่ม symbol ตาม cohesion (deterministic · บอก layer · บอกสิ่งที่ต้อง bind)
ใช้ตรวจก่อน/หลังย้ายโค้ดก้อนถัดไป · อ่านไฟล์จริงแต่ไม่แก้ ไม่แตะเน็ต
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import depgraph as D  # noqa: E402 - ต้อง sys.path.insert ก่อน  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


rep = D.build()
mods = rep["modules"]
MIGRATED = {"symbols.py", "project.py", "usage.py", "shell.py", "skills.py",
           "ui_render.py"}

check("วิเคราะห์โมดูลหลักครบ", {"soonai.py"} | MIGRATED <= set(mods), sorted(mods))
check("ไม่มี import cycle", rep["import_cycles"] == [], rep["import_cycles"])
check("ไม่มี bind cycle (ขอบเขตเป็น DAG)", rep["bind_cycles"] == [], rep["bind_cycles"])

check("soonai import โมดูลที่แยกออกครบ",
      MIGRATED <= set(mods.get("soonai.py", {}).get("imports", [])),
      mods.get("soonai.py", {}).get("imports"))

def _t(n):
    return mods.get(n, {})
# ── ขอบเขต "โมดูลฐาน" หลังรอบลด bind: ต้องพ้นจาก facade ของ soonai โดยสิ้นเชิง ──
# เกณฑ์: (1) ไม่ import soonai กลับ (2) bind_refs = 0 → อ่าน seam ผ่าน runtime เอง
BASE = {"runtime.py", "symbols.py", "project.py", "usage.py", "shell.py"}
check("โมดูลฐานไม่ import soonai กลับ (ไม่พึ่ง facade)",
      not any("soonai.py" in _t(n).get("imports", []) for n in BASE),
      {n: _t(n).get("imports") for n in BASE})
check("โมดูลฐาน bind_refs = 0 (ไม่พึ่งชื่อที่ soonai ส่งให้แล้ว)",
      all(_t(n).get("bind_deps") == [] for n in BASE),
      {n: _t(n).get("bind_deps") for n in BASE})
check("runtime เป็นรากของกราฟ (import/bind ว่างเปล่า)",
      _t("runtime.py").get("imports") == [] and _t("runtime.py").get("bind_deps") == [],
      [_t("runtime.py").get("imports"), _t("runtime.py").get("bind_deps")])
check("symbols import โมดูลพี่น้อง + runtime ตรง ๆ (project, runtime)",
      set(_t("symbols.py").get("imports", [])) == {"project.py", "runtime.py"},
      _t("symbols.py").get("imports"))
check("shell/usage อ่าน seam ผ่าน runtime (import runtime + debug ตรง ๆ ไม่ bind)",
      _t("usage.py").get("imports") == ["runtime.py"]
      and set(_t("shell.py").get("imports", [])) == {"debug.py", "runtime.py"},
      {n: _t(n).get("imports") for n in ("shell.py", "usage.py")})

# debug (Step 6): "โมดูลฐาน" ตัวใหม่ — พึ่ง runtime ทางเดียว (ตอนเรียกใช้ ไม่ใช่ตอน import)
check("debug.py เป็นโมดูลฐาน (import เฉพาะ runtime · ไม่ bind)",
      set(_t("debug.py").get("imports", [])) <= {"runtime.py"}
      and _t("debug.py").get("bind_deps") == [],
      [_t("debug.py").get("imports"), _t("debug.py").get("bind_deps")])
check("soonai/chat/permissions import debug (จุดที่กลืน exception สำคัญ)",
      {"debug.py"} <= set(_t("soonai.py").get("imports", []))
      and "debug.py" in _t("chat.py").get("imports", [])
      and "debug.py" in _t("permissions.py").get("imports", []),
      {n: _t(n).get("imports") for n in ("soonai.py", "chat.py", "permissions.py")})
check("project ไม่พึ่ง symbols/shell/usage",
      not ({"symbols.py", "shell.py", "usage.py"} & set(_t("project.py").get("imports", []))),
      _t("project.py").get("imports"))

# ── bind budget = 0: ไม่มีโมดูลไหนต้อง bind อีก (ทุกตัวอ่าน seam ผ่าน runtime) ──
_binders = {n for n, i in mods.items() if i.get("bind_deps")}
check("bind budget: ไม่มีโมดูลใดต้อง bind เลย", _binders == set(), sorted(_binders))
check("bind budget: ขอบ bind ทั้งโปรเจกต์เหลือ 0",
      not any(i.get("bind_deps") for i in mods.values()),
      {n: i.get("bind_deps") for n, i in mods.items() if i.get("bind_deps")})

# skills (Step 2): ต้องเป็น DAG · พึ่งโมดูลที่แยกแล้วเท่านัด (ไม่ bind, ไม่พึ่ง soonai)
_skills_deps = set(_t("skills.py").get("bind_deps", []))
_skills_imports = set(_t("skills.py").get("imports", []))
check("skills ไม่ bind และ import เฉพาะโมดูลที่แยกแล้ว (debug/project/runtime/shell/symbols)",
      _skills_deps == set()
      and _skills_imports <= {"debug.py", "project.py", "runtime.py", "shell.py", "symbols.py"},
      [sorted(_skills_deps), sorted(_skills_imports)])
check("skills import เข้า soonai จริง",
      "skills.py" in mods.get("soonai.py", {}).get("imports", []),
      mods.get("soonai.py", {}).get("imports"))
check("skills ไม่ถูก import กลับจากโมดูลอื่น (ไม่มีวันเกิด cycle)",
      not any("skills.py" in i.get("imports", [])
              for n, i in mods.items() if n != "soonai.py"),
      {n: i.get("imports") for n, i in mods.items() if n != "soonai.py"})

# ui_render (Step 3): เลเยอร์เรนเดอร์ — พึ่งเฉพาะโมดูลฐาน (ไม่ bind, ไม่พึ่ง soonai)
_uir_deps = set(_t("ui_render.py").get("bind_deps", []))
_uir_imports = set(_t("ui_render.py").get("imports", []))
check("ui_render ไม่ bind และ import เฉพาะโมดูลฐาน",
      _uir_deps == set()
      and _uir_imports <= {"runtime.py", "shell.py", "usage.py", "providers.py",
                           "ui_theme.py"},
      [sorted(_uir_deps), sorted(_uir_imports)])
check("ui_render import เข้า soonai จริง",
      "ui_render.py" in mods.get("soonai.py", {}).get("imports", []),
      mods.get("soonai.py", {}).get("imports"))
check("ui_render ไม่ถูก import กลับจากโมดูลอื่น (ไม่มีวันเกิด cycle)",
      not any("ui_render.py" in i.get("imports", [])
              for n, i in mods.items() if n != "soonai.py"),
      {n: i.get("imports") for n, i in mods.items() if n != "soonai.py"})

# gate logic: cycle ใด ๆ = ไม่ผ่าน
_gate_bad = bool(rep["import_cycles"] or rep["bind_cycles"])
check("gate: ไม่มี cycle ให้ผ่าน", _gate_bad is False)


# ---------- 4) โหมด --plan: เสนอการจัดกลุ่มโมดูล ----------
def _graph(edges, nodes):
    w = {}
    for a, b, wt in edges:
        k = (a, b) if a < b else (b, a)
        w[k] = w.get(k, 0.0) + wt
    return {"nodes": list(nodes), "w": w}


# 4.1 cluster() เป็นฟังก์ชันบริสุทธิ์ — ทดสอบด้วยกราฟสมมติ (ไม่พึ่งไฟล์จริง)
_tri = _graph([("a1", "a2", 1), ("a2", "a3", 1), ("a1", "a3", 1),
               ("b1", "b2", 1), ("b2", "b3", 1), ("b1", "b3", 1),
               ("a3", "b1", 0.2)], ["a1", "a2", "a3", "b1", "b2", "b3"])
_c = D.cluster(_tri)
check("cluster: สองสามเหลี่ยมเชื่อมกันด้วยขอบอ่อน → 2 กลุ่ม",
      sorted(map(sorted, _c["groups"])) == [["a1", "a2", "a3"], ["b1", "b2", "b3"]],
      _c["groups"])
check("cluster: modularity > 0 เมื่อมีโครงสร้างจริง", _c["modularity"] > 0.3, _c["modularity"])
check("cluster: ทำซ้ำได้ผลเดิม (deterministic)", D.cluster(_tri) == _c)
check("cluster: ไม่มีขอบเลย → node ละกลุ่ม",
      len(D.cluster(_graph([], ["x", "y"]))["groups"]) == 2)
check("cluster: max_groups=1 → รวมเป็นกลุ่มเดียว",
      len(D.cluster(_tri, max_groups=1)["groups"]) == 1)

# 4.2 plan() กับ symbol จริงในโปรเจกต์
_SYMS = ["record_skill_use", "record_skill_decline", "_skill_state",
         "_skill_state_save", "skill_use_count", "skill_suggestions_for_task"]
_p1 = D.plan(_SYMS)
check("plan: เจอ symbol ครบ ไม่มีตกหล่น", _p1["missing"] == [] and _p1["count"] == len(_SYMS),
      _p1["missing"])
_flat = [n for g in _p1["groups"] for n in g["symbols"]]
check("plan: ทุก symbol อยู่พอดีกลุ่มละครั้ง",
      sorted(_flat) == sorted(_SYMS) and len(_flat) == len(set(_flat)), _flat)
check("plan: symbol ที่เรียกกันตรง ๆ อยู่กลุ่มเดียวกัน",
      any({"record_skill_use", "_skill_state_save"} <= set(g["symbols"])
          for g in _p1["groups"]),
      [g["symbols"] for g in _p1["groups"]])
check("plan: เสนอชื่อไฟล์โมดูลทุกกลุ่ม",
      all(g["file_hint"].startswith("shared/") and g["file_hint"].endswith(".py")
          for g in _p1["groups"]))
# หลังลด bind: ชื่อที่กลุ่มนี้ใช้ผ่าน `R.<ชื่อ>` ต้องไม่ถูกนับเป็น "ต้อง bind จากภายนอก" อีก
check("plan: seam ที่อ่านผ่าน runtime ไม่ถูกนับเป็น bind อีก",
      not any({"save_json", "load_json", "SKILL_STATE_FILE", "load_config",
               "console", "agent_tools"} & set(g["needs"]) for g in _p1["groups"]),
      [g["needs"] for g in _p1["groups"]])
check("plan: ยังรายงานสิ่งที่ต้องเตรียมจริง (เช่น state ของโมดูล)",
      any(g["needs"] for g in _p1["groups"]),
      [g["needs"] for g in _p1["groups"]])
check("plan: modularity อยู่ในช่วง [-1, 1]", -1.0 <= _p1["modularity"] <= 1.0,
      _p1["modularity"])
check("plan: layers ครอบทุกกลุ่ม",
      {i for layer in _p1["layers"] for i in layer} == {g["id"] for g in _p1["groups"]},
      (_p1["layers"], [g["id"] for g in _p1["groups"]]))
check("plan: symbol ที่ไม่มีจริงถูก รายงาน ไม่ทำให้พัง",
      D.plan(["no_such_symbol_xx", "record_skill_use"])["missing"] == ["no_such_symbol_xx"])
check("plan: symbol เดียว → กลุ่มเดียว เตือนว่าไม่มีขอบ",
      D.plan(["record_skill_use"])["warnings"] != [])

# 4.3 CLI: --plan / --plan-all / --max-groups ผ่าน main()

def _run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D.main(argv)
    return rc, buf.getvalue()


_rc, _out = _run_main(["--plan", "search_catalog", "install_skill", "--json"])
check("CLI --plan --json: exit 0 + JSON ที่อ่านได้", _rc == 0 and "groups" in json.loads(_out))
_rc, _out = _run_main(["--plan-all", "shared/skills.py", "--max-groups", "4", "--json"])
_p4 = json.loads(_out)
check("CLI --plan-all --max-groups 4: ได้ไม่เกิน 4 กลุ่ม", _rc == 0 and len(_p4["groups"]) <= 4,
      len(_p4["groups"]))
check("CLI --plan-all: ครอบ symbol ฟังก์ชันทั้งไฟล์",
      _p4["count"] >= 40 and not _p4["missing"], _p4["count"])
_rc, _out = _run_main(["--plan-all", "shared/skills.py"])
_rc2, _out2 = _run_main(["--plan-all", "shared/skills.py", "--max-groups", "4"])
check("CLI: เพดานกลุ่มทำให้ได้กลุ่มหยาบขึ้นจริง",
      len(json.loads(_run_main(["--plan-all", "shared/skills.py", "--json"])[1])["groups"])
      > len(_p4["groups"]))
check("CLI: --plan-all (ข้อความ) พิมพ์ลิสต์กลุ่ม", "symbols:" in _out and "cohesion" in _out2)
_rc, _out = _run_main(["--check"])
check("CLI --check ยังทำงานเหมือนเดิม (exit 0)", _rc == 0 and "import cycles" in _out)

# 4.4 ผลต้องไม่ขึ้นกับว่า fast-path เลือก parse ไฟล์ไหน (บั๊ก coupling ที่เคยเจอ)
_orig_def_index = D.def_index
try:
    D.def_index = lambda path: []          # บังคับเส้นทางสแกนเต็ม
    _p1_full = D.plan(_SYMS)
finally:
    D.def_index = _orig_def_index
check("plan: fast path = สแกนเต็ม (groups + modularity เท่ากัน)",
      _p1_full["groups"] == _p1["groups"]
      and _p1_full["modularity"] == _p1["modularity"],
      (_p1_full["modularity"], _p1["modularity"]))


# ---------- 5) โหมด --graph: ภาพสถาปัตยกรรม (Mermaid / DOT / HTML) ----------
_MODEL = D.module_model(rep)
_md = D.render_mermaid(_MODEL)
_dot = D.render_dot(_MODEL)
_html = D.render_html(_MODEL)

check("mermaid: flowchart + subgraph ชั้น",
      _md.startswith("%%") and "flowchart TB" in _md and "subgraph L" in _md)
check("mermaid: วาดขอบ import เป็นเส้นทึบ",
      "-->" in _md and any(e["kind"] == "import" for e in _MODEL["edges"]))
check("model: ระบบจริงไม่มีขอบ bind เหลือแล้ว (decoupling ครบ)",
      not any(e["kind"] == "bind" for e in _MODEL["edges"]),
      [e for e in _MODEL["edges"] if e["kind"] == "bind"])

# คุมโค้ดเส้นทาง "เส้นประ" ด้วยโมเดลสังเคราะห์ (ของจริงไม่มี bind ให้ทดสอบแล้ว)
import copy as _copy  # noqa: E402 - ต้อง sys.path.insert ก่อน
_syn = _copy.deepcopy(_MODEL)
_bind_edge = dict(_syn["edges"][0])
_bind_edge["kind"], _bind_edge["weight"] = "bind", 1
_syn["edges"] = list(_syn["edges"]) + [_bind_edge]
check("mermaid: ขอบ bind → เส้นประ (โมเดลสังเคราะห์)",
      "-.->" in D.render_mermaid(_syn))
check("dot: ขอบ bind → style=dashed (โมเดลสังเคราะห์)",
      'style="dashed"' in D.render_dot(_syn).split("subgraph")[-1])
check("svg: ขอบ bind → stroke-dasharray (โมเดลสังเคราะห์)",
      "stroke-dasharray" in D.render_svg(_syn))
_decl = set(re.findall(r"^\s*([MG]\d+)\[", _md, re.M))
_used = set(re.findall(r"([MG]\d+)\s+[-.]*->", _md))
check("mermaid: ทุก id ที่อ้างถึงถูกประกาศ", _used <= _decl and bool(_decl), sorted(_used - _decl))
check("dot: digraph + วงเล็บครบ", _dot.startswith("//") and "digraph arch {" in _dot
      and _dot.rstrip().endswith("}") and _dot.count("{") == _dot.count("}"))
_svg = D.render_svg(_MODEL)
check("svg: วาดเองได้ ไม่พึ่ง JS/CDN", _svg.startswith("<svg") and _svg.rstrip().endswith("</svg>")
      and "mermaid" not in _svg.lower())
check("svg: มีกล่องของทุกโมดูล + marker ลูกศร",
      _svg.count("<rect") >= len(_MODEL["nodes"]) and 'marker-end="url(#arw)"' in _svg)
check("html: ฝัง SVG + ซอร์ส Mermaid/DOT (เห็นภาพทันทีแม้ออฟไลน์)",
      "<svg" in _html and "flowchart TB" in _html and "digraph arch" in _html
      and "esm.min.mjs" not in _html)

# 5.1 ชั้นต้องสื่อโครงสร้างจริง: import ทุกเส้นชี้ลงล่าง (บนพึ่งล่าง)
_layer_of = {}
for _i, _layer in enumerate(_MODEL["layers"]):
    for _x in _layer:
        _layer_of[_x] = _i
_name = {n["id"]: n["name"] for n in _MODEL["nodes"]}
_bad = [(_name[e["from"]], _name[e["to"]]) for e in _MODEL["edges"]
        if e["kind"] == "import"
        and _layer_of.get(e["from"], -1) <= _layer_of.get(e["to"], -2)]
check("layer: import ชี้ลงล่างเสมอ (ไม่สลับชั้น)", not _bad, _bad)
check("layer: ทุกโมดูลถูกจัดชั้นครบ", len(_layer_of) == len(_MODEL["nodes"]),
      (len(_layer_of), len(_MODEL["nodes"])))
check("layer: ไม่มีกลุ่ม/โมดูลซ้ำหลายชั้น",
      len({x for lay in _MODEL["layers"] for x in lay}) == sum(len(lay) for lay in _MODEL["layers"]))

# 5.2 ภาพของ --plan
_PMODEL = D.plan_model(_p1)
_pmd = D.render_mermaid(_PMODEL)
check("plan graph: จำนวนโหนด = จำนวนกลุ่ม", len(_PMODEL["nodes"]) == len(_p1["groups"]))
_GIDS = {n["id"] for n in _PMODEL["nodes"]}
check("plan graph: ขอบอ้างถึงโหนดที่มีจริง",
      all(e["from"] in _GIDS and e["to"] in _GIDS for e in _PMODEL["edges"]),
      _PMODEL["edges"])
check("plan graph: วาดได้ทั้ง mermaid/dot + ขอบพึ่งกันเป็นเส้นทึบ",
      "flowchart" in _pmd and "digraph" in D.render_dot(_PMODEL)
      and (not _PMODEL["edges"] or "-->" in _pmd))

# 5.3 CLI --out: เดาชนิดจากนามสกุลไฟล์
_tmpdir = tempfile.mkdtemp(prefix="depgraph_test_")
try:
    _pd = os.path.join(_tmpdir, "arch.dot")
    _rc, _out = _run_main(["--graph", "--out", _pd])
    check("CLI --out .dot: ได้ DOT จริง",
          _rc == 0 and Path(_pd).read_text(encoding="utf-8").startswith("//"))
    _ph = os.path.join(_tmpdir, "arch.html")
    _run_main(["--graph", "--out", _ph])
    check("CLI --out .html: เดาชนิดจากนามสกุล",
          "<!doctype html>" in Path(_ph).read_text(encoding="utf-8").lower())
    _pm = os.path.join(_tmpdir, "plan.mmd")
    _run_main(["--plan-all", "shared/skills.py", "--out", _pm])
    check("CLI --plan --out .mmd: ภาพของข้อเสนอ",
          "flowchart" in Path(_pm).read_text(encoding="utf-8"))
    # ลำดับความสำคัญ: --graph มาก่อน --json (ได้ภาพ ไม่ใช่ JSON)
    check("CLI: --graph --json → ออกเป็นภาพ",
          _run_main(["--graph", "--json"])[1].startswith("%%"))
finally:
    shutil.rmtree(_tmpdir, ignore_errors=True)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL DEPGRAPH TESTS PASSED")
