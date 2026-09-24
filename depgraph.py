# -*- coding: utf-8 -*-
"""dependency graph ของ soonai.py + shared/*.py (ตรวจ cycle + ยืนยันขอบเขตโมดูล)

ใช้เป็นเครื่องมือ (CLI) และเป็นไลบรารี (ให้เทสต์เรียก):
  python depgraph.py            รายงานทั้งหมด
  python depgraph.py --json     ออก JSON
  python depgraph.py --check    exit 1 ถ้าเจอ cycle ที่เป็นปัญหา (ใช้เป็น CI gate)
  python depgraph.py --plan SYMBOL [SYMBOL ...]
                                เสนอการจัดกลุ่มโมดูลจากรายชื่อ symbol (cohesion สูงสุด)
  python depgraph.py --plan-file symbols.txt     (บรรทัดละชื่อ · # = คอมเมนต์)
  python depgraph.py --plan-all [ไฟล์]           ทุก symbol ระดับบนของไฟล์ (ดีฟอลต์ soonai.py)
        ตัวเลือก: --max-groups N · --no-cocite · --json

โหมด --plan ใช้เฉพาะ symbol ที่เป็นฟังก์ชัน/คลาสระดับบน (ค่าคงที่/ตัวแปรระดับโมดูล
ไม่มีขอบอ้างอิงให้จับ) และเสนอชื่อ/ไฟล์โมดูล, ลำดับการย้าย (leaf-first) และรายการ
ชื่อที่กลุ่มนั้นต้องพึ่งจากภายนอกให้ด้วย

สามชั้นที่วิเคราะห์:
  1) import graph     : ไฟล์ -> ไฟล์ที่ import (โมดูลต้องเป็น DAG)
  2) bind graph       : โมดูลย่อย -> โมดูลที่ "นิยาม" ชื่อที่มันอ้างแต่ไม่ได้ import เอง
                        (ชื่อเหล่านี้ส่งมาจาก soonai ตอน import ผ่าน runtime.bind_module)
  3) symbol graph     : ชื่อ -> ชื่อที่อ้างในไฟล์เดียวกัน (mutual recursion = ข้อมูล)
"""
import ast
import builtins
import heapq
import json as _json
import sys
from pathlib import Path

BUILTINS = set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__builtins__", "self", "cls"}


def _local_bound(node):
    bound = set()
    for n in ast.walk(node):
        if isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not node:
            bound.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.Global):
            bound.update(n.names)
    return bound


def _loads(node):
    return {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _scan_imports(stmts, deps, names):
    for node in stmts:
        if isinstance(node, ast.Import):
            for a in node.names:
                deps.add(a.name.split(".")[0])
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                deps.add(node.module.split(".")[0])
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, ast.Try):
            _scan_imports(node.body, deps, names)
            for h in node.handlers:
                _scan_imports(h.body, deps, names)
            _scan_imports(node.orelse, deps, names)
            _scan_imports(node.finalbody, deps, names)
        elif isinstance(node, ast.If):
            _scan_imports(node.body, deps, names)
            _scan_imports(node.orelse, deps, names)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            _scan_imports(node.body, deps, names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _scan_imports(node.body, deps, names)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            _scan_imports(node.body, deps, names)
            _scan_imports(node.orelse, deps, names)
        elif hasattr(ast, "TryStar") and isinstance(node, ast.TryStar):
            _scan_imports(node.body, deps, names)
            for h in node.handlers:
                _scan_imports(h.body, deps, names)
            _scan_imports(node.orelse, deps, names)
            _scan_imports(node.finalbody, deps, names)


def analyze_file(path):
    src = Path(path).read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    defs, deps, imported = set(), set(), set()
    refs_by_def, module_refs = {}, set()

    def _targets(t, acc):
        if isinstance(t, ast.Name):
            acc.add(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                _targets(e, acc)

    _scan_imports(tree.body, deps, imported)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                _targets(t, defs)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defs.add(node.target.id)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            refs_by_def[node.name] = _loads(node) - _local_bound(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            module_refs |= _loads(node) - _local_bound(node)
    refs_by_def["<module>"] = module_refs
    return {"file": str(path), "defs": defs, "deps": deps, "imported": imported,
            "refs_by_def": refs_by_def}


def symbol_edges(info):
    defs = info["defs"]
    return {src: set(refs & defs) for src, refs in info["refs_by_def"].items()}


def external_refs(info):
    """ชื่อที่อ้างแต่ไม่ได้นิยาม/import เอง = พึ่ง bind จาก soonai"""
    out = {}
    for src, refs in info["refs_by_def"].items():
        miss = refs - info["defs"] - info["imported"] - BUILTINS
        if miss:
            out[src] = miss
    return out


def tarjan_scc(graph):
    index, low, on_stack, stack, out = {}, {}, set(), [], []
    counter = [0]

    def strong(v):
        work = [(v, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = low[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            recurse = False
            succs = list(graph.get(node, ()))
            for i in range(pi, len(succs)):
                w = succs[i]
                if w not in index:
                    work[-1] = (node, i + 1)
                    work.append((w, 0))
                    recurse = True
                    break
                if w in on_stack:
                    low[node] = min(low[node], index[w])
            if recurse:
                continue
            if low[node] == index[node]:
                comp = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.add(w)
                    if w == node:
                        break
                out.append(comp)
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])

    for v in graph:
        if v not in index:
            strong(v)
    return out


def mutual_cycles(graph):
    """SCC ขนาด >1 = พึ่งกันไปมา (ไม่นับ self-recursion ซึ่งปกติ)"""
    return [c for c in tarjan_scc(graph) if len(c) > 1]


def module_graphs(targets):
    files = [str(p) for p in targets]
    infos = {f: analyze_file(f) for f in files}
    stem2file = {Path(f).stem: f for f in files}

    import_g = {f: set() for f in files}
    for f, info in infos.items():
        for d in info["deps"]:
            if d in stem2file and stem2file[d] != f:
                import_g[f].add(stem2file[d])

    # ชื่อ -> ไฟล์ที่นิยาม (สำหรับ bind graph)
    owner = {}
    for f, info in sorted(infos.items(), key=lambda kv: kv[0].count("/")):
        for name in info["defs"]:
            owner.setdefault(name, f)

    bind_g = {f: set() for f in files}
    bind_missing = {f: {} for f in files}
    for f, info in infos.items():
        ext = external_refs(info)
        allmiss = sorted({n for s in ext.values() for n in s})
        bind_missing[f] = allmiss
        for n in allmiss:
            o = owner.get(n)
            if o and o != f:
                bind_g[f].add(o)
    return infos, import_g, bind_g, bind_missing


def build(targets=None):
    if targets is None:
        targets = ["soonai.py"] + sorted(str(p) for p in Path("shared").glob("*.py"))
    infos, import_g, bind_g, bind_missing = module_graphs(targets)
    name = {f: Path(f).name for f, _ in infos.items()}
    return {
        "modules": {name[f]: {"defs": len(infos[f]["defs"]),
                              "imports": sorted(name[g] for g in import_g[f]),
                              "bind_deps": sorted(name[g] for g in bind_g[f]),
                              "bind_refs": bind_missing[f]}
                    for f in infos},
        "import_cycles": [[name[x] for x in c] for c in mutual_cycles(import_g)],
        "bind_cycles": [[name[x] for x in c] for c in mutual_cycles(bind_g)],
        "self_recursion": {name[f]: len([1 for s, t in symbol_edges(infos[f]).items()
                                         if s in t])
                           for f in infos},
}


# ── โหมด --plan: เสนอการจัดกลุ่มโมดูลจากรายชื่อ symbol ──────────────────────
# หลักการ: จัดกลุ่มให้ modularity สูงสุด (Newman greedy) บนกราฟน้ำหนัก 2 ชนิด
#   1) ref : symbol A อ้าง symbol B จริงกี่ครั้ง (ทิศทาง = ผู้เรียก → ผู้ถูกเรียก)
#   2) co  : co-citation — A กับ B อ้าง "ชื่อภายนอก" ชุดเดียวกันมากแค่ไหน (jaccard)
#    (--plan ใช้เฉพาะ symbol ที่เป็นฟังก์ชัน/คลาสระดับบน — ค่าคงที่/ตัวแปรระดับโมดูลไม่มูขอบให้จับ)
# เป้าหมายคือคำตอบที่อธิบายได้: ทุกกลุ่มบอกได้ว่าอะไรดึงสมาชิกเข้าหากัน และ
# ต้อง bind อะไรจากภายนอกอีก (ต่อยอดตรงกับขั้นตอนย้ายโค้ดจริง)
CITE_WEIGHT = 0.5      # น้ำหนักต่อ jaccard 1.0 (ขอบอ้างอิงจริงนับ 1.0 ต่อครั้ง)
CITE_MIN = 0.25        # สร้างขอบ co-citation ก็ต่อเมื่อคล้ายกันตั้งแต่เท่านี้


_DEF_LINE = None
_ASSIGN_LINE = None


def target_files(targets=None):
    if targets is None:
        return ["soonai.py"] + sorted(str(p) for p in Path("shared").glob("*.py"))
    return [str(p) for p in targets]


def def_index(path):
    """ชื่อ symbol ระดับบนของไฟล์ (def/class/ตัวแปรระดับโมดูล) — สแกนเร็ว ๆ ด้วย regex

    ยอมรับ false positive ได้ (แค่ parse เพิ่มหนึ่งไฟล์) ส่วน false negative มี
    ทางกันไว้ใน plan(): ถ้าหา symbol ไม่เจอในไฟล์ที่เลือก จะสแกนเต็มทั้งหมดอีกรอบ
    """
    global _DEF_LINE, _ASSIGN_LINE
    if _DEF_LINE is None:
        import re as _re
        _DEF_LINE = _re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)")
        _ASSIGN_LINE = _re.compile(r"^([A-Za-z_]\w*)\s*(?::[^=]*)?=(?!=)")
    names = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line[0] in " \t#":        # ต้องเริ่มที่คอลัมน์ 0 = ระดับโมดูล
            continue
        m = _DEF_LINE.match(line) or _ASSIGN_LINE.match(line)
        if m:
            names.append(m.group(1))
    return names


def ref_counts(path):
    """ชื่อ symbol ระดับบน -> Counter ของชื่อที่เนื้อในอ้างถึง

    ตัดชื่อที่เป็นของในฟังก์ชันเอง (พารามิเตอร์/ตัวแปร/ชื่อที่ประกาศ) ออก เพื่อไม่ให้
    ตัวแปรชั่วคราวกลายเป็น "การพึ่งพา"
    """
    tree = ast.parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    out = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        local = _local_bound(node)
        counter = {}
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in local:
                counter[n.id] = counter.get(n.id, 0) + 1
        out[node.name] = counter
    return out


def cluster(dep, max_groups=None, min_gain=1e-12):
    """จัดกลุ่ม node ให้ modularity สูงสุด — greedy merging (Newman)

    dep = {"nodes": [...], "w": {(a, b): น้ำหนัก}} โดย a < b และน้ำหนักสมมาตร
    merge คู่ที่ ΔQ มากสุดไปเรื่อย ๆ จน ΔQ ≤ 0 (หรือจนถึงโควตา max_groups ถ้าระบุ
    โควตาจะรวมต่อแน้ง ΔQ ไม่เพิ่ม — ใช้ดูภาพหยาบ ๆ) และหยุดไม่ได้ถ้ากลุ่มที่เหลือ
    ไม่มีขอบเชื่อมกันเลย
    คืน {"groups": [[node, ...], ...], "modularity": float, "merges": [[...], ...]}
    """
    nodes = sorted(dep["nodes"])
    w = dict(dep["w"])
    twom = 2.0 * sum(w.values())
    if twom <= 0:
        return {"groups": [[n] for n in nodes], "modularity": 0.0, "merges": []}
    m = twom / 2.0
    idx = {n: k for k, n in enumerate(nodes)}
    # น้ำหนักข้างในกราฟ (ต่อ node) + สะสมแบบ cluster (cadj) สำหรับ ΔQ
    ndeg = {k: 0.0 for k in idx.values()}
    cadj = {k: {} for k in idx.values()}
    for (a, b), wt in w.items():
        ia, ib = idx[a], idx[b]
        cadj[ia][ib] = cadj[ia].get(ib, 0.0) + wt
        cadj[ib][ia] = cadj[ib].get(ia, 0.0) + wt
        ndeg[ia] += wt
        ndeg[ib] += wt
    members = {k: [nodes[k]] for k in idx.values()}
    deg = dict(ndeg)
    heap = []

    def push(i, j, wt):
        a, b = (i, j) if i < j else (j, i)
        dq = wt / m - (deg[a] * deg[b]) / (2.0 * m * m)
        heapq.heappush(heap, (-dq, a, b, wt))

    for k, nb in cadj.items():
        for j, wt in nb.items():
            if k < j:
                push(k, j, wt)

    merges, nxt = [], max(idx.values()) + 1 if idx else 0
    while heap and (max_groups is None or len(members) > max_groups):
        negdq, i, j, wt = heapq.heappop(heap)
        if i not in members or j not in members:
            continue
        if abs(cadj[i].get(j, 0.0) - wt) > 1e-9:
            continue                     # ขอบนี้เก่า (กลุ่มถูก merge ไปแล้ว)
        # หยุดเมื่อไม่มีคู่ไหนเพิ่ม modularity อีก แต่ถ้าผู้ใช้ขอเพดานจำนวนกลุ่มไว้
        # (--max-groups) ยังต้องรวมต่อจนถึงเพดาน แม้ ΔQ จะไม่เพิ่ม
        if -negdq <= min_gain and (max_groups is None or len(members) <= max_groups):
            break
        merged_names = sorted(members.pop(i) + members.pop(j))
        merged_deg = deg.pop(i) + deg.pop(j)
        ci, cj = cadj.pop(i), cadj.pop(j)
        merged = {}
        for src in (ci, cj):
            for k, wt2 in src.items():
                if k == i or k == j:
                    continue             # ขอบภายในกลุ่ม — หายจาก boundary
                merged[k] = merged.get(k, 0.0) + wt2
        for k, wt2 in merged.items():
            cadj[k].pop(i, None)
            cadj[k].pop(j, None)
            cadj[k][nxt] = wt2
        cadj[nxt] = merged
        members[nxt] = merged_names
        deg[nxt] = merged_deg
        merges.append([merged_names, round(-negdq, 6), round(wt, 6)])
        for k, wt2 in merged.items():
            push(nxt, k, wt2)
        nxt += 1

    groups = sorted((sorted(v) for v in members.values()),
                    key=lambda g: (-len(g), g[0]))
    q = 0.0
    for g in groups:
        internal = 0.0
        for x in range(len(g)):
            for y in range(x + 1, len(g)):
                a, b = (g[x], g[y]) if g[x] < g[y] else (g[y], g[x])
                internal += w.get((a, b), 0.0)
        dsum = sum(ndeg[idx[n]] for n in g)
        q += internal / m - (dsum / twom) ** 2
    return {"groups": groups, "modularity": q, "merges": merges}


def name_tokens(name):
    return [t for t in str(name).strip("_").split("_") if len(t) >= 3 and not t.isdigit()]


def group_name_hint(members, ref_dir, wide_tokens=frozenset()):
    """ชื่อโมดูลที่เสนอจากชื่อสมาชิก

    - รวม token ของทุกชื่อ (ตัด _ หน้า/หลัง) แล้วใช้ 1-2 token ที่พบบ่อยสุด
      เช่น {_skill_state, skill_use_count} → "state-use"
    - ตัด token ที่โผล่เกือบทั้งชุด (wide_tokens เช่น "skill" ในโมดูล skills) ออก
      เพื่อให้ชื่อบอกความต่างของกลุ่ม ไม่ใช่ชื่อโมดูลร่ม
    - ถ้าไม่มี token ซ้ำเลย ใช้สมาชิกที่ถูกเพื่อนในกลุ่มเรียกมากสุด (ศูนย์กลาง)
    """
    toks = {}
    for name in members:
        for tok in name_tokens(name):
            if tok in wide_tokens:
                continue
            toks[tok] = toks.get(tok, 0) + 1
    shared = sorted((t for t in toks.items() if t[1] >= 2),
                    key=lambda kv: (-kv[1], kv[0]))[:2]
    if shared:
        return "-".join(t for t, _ in shared)
    score = {name: 0.0 for name in members}
    for (a, b), wt in ref_dir.items():
        if a in score and b in score:
            score[b] += wt
    return sorted(members, key=lambda name: (-score[name], name))[0].lstrip("_")


def _scc(graph):
    return tarjan_scc({k: set(v) for k, v in graph.items()})


def layer_groups(raw_groups, ref_dir):
    """เรียงกลุ่มแบบ leaf-first จากทิศทางการพึ่งพา (น้ำหนักขอบมากกว่าชนะ)

    คืน (layers, cycles) — cycles = กลุ่มที่พึ่งกันไปมาซึ่งการแยกตรง ๆ ไม่ได้
    """
    memb = {n: i for i, g in enumerate(raw_groups) for n in g}
    deps = {}
    for (a, b), wt in ref_dir.items():
        ia, ib = memb[a], memb[b]
        if ia != ib:
            deps[(ia, ib)] = deps.get((ia, ib), 0) + wt
    dom = {i: set() for i in range(len(raw_groups))}
    for (ia, ib), wt in deps.items():
        if wt > deps.get((ib, ia), 0):
            dom[ia].add(ib)
    comps = _scc(dom)
    comp = {n: c for c, grp in enumerate(comps) for n in grp}
    # หมายเหตุสำคัญ: ดัชนีของ component ไม่เท่ากับดัชนีของกลุ่ม → ต้องแมปกลับ
    # ไม่งั้น layer จะสลับกลุ่มกัน (บั๊กที่เคยทำให้ ui_theme ไปอยู่ชั้นบนสุด)
    nodes_of = {}
    for node, c in comp.items():
        nodes_of.setdefault(c, []).append(node)
    cedges = {c: set() for c in nodes_of}
    for i, dd in dom.items():
        for j in dd:
            if comp[i] != comp[j]:
                cedges[comp[i]].add(comp[j])
    order, remaining = [], set(nodes_of)
    while remaining:
        leaf = sorted(c for c in remaining if not (cedges[c] & remaining))
        if not leaf:
            break
        order.append(leaf)
        remaining -= set(leaf)
    layers = []
    for layer in order:
        idxs = sorted(i for c in layer for i in nodes_of[c])
        layers.append([sorted(raw_groups[i]) for i in idxs])
    cycles = [sorted(raw_groups[i] for i in sorted(nodes_of[c]))
              for c in nodes_of if len(nodes_of[c]) > 1]
    return layers, cycles


def plan(symbols, targets=None, max_groups=None, cocite=CITE_WEIGHT, cite_min=CITE_MIN):
    """เสนอการจัดกลุ่มโมดูลจากรายชื่อ symbol — คืนรายงานที่อธิบายได้ (JSON-friendly)

    symbols = ชื่อ symbol (จากไฟล์ที่วิเคราะห์) · symbol ที่หาไม่เจอจะถูกรายงาน ไม่ทำให้พัง
    """
    files = target_files(targets)
    requested, seen = [], set()
    for raw in symbols:
        name = str(raw).strip()
        if name and name not in seen:
            seen.add(name)
            requested.append(name)

    def _scan(selected):
        """คืน counts, owner และ imported ของ "ไฟล์เจ้าของ" แต่ละ symbol

        ใช้ imported รายไฟล์ (ไม่ใช่ union ของทุกไฟล์) เพื่อให้ผลไม่ขึ้นกับว่า
        fast-path เลือก parse ไฟล์ไหน — co-citation จะเสถียรและทำซ้ำได้เสมอ
        """
        counts, owner, fimports = {}, {}, {}
        for f in selected:
            try:
                rc = ref_counts(f)
            except Exception:
                continue
            fimports[f] = analyze_file(f)["imported"]
            for name, counter in rc.items():
                if name not in counts:
                    counts[name] = counter
                    owner[name] = f
        return counts, owner, fimports

    # เลือก parse เฉพาะไฟล์ที่นิยาม symbol ที่ขอ (เร็ว) — ถ้ายังหาไม่เจอค่อยสแกนเต็ม
    want_set = set(requested)
    selected = [f for f in files if want_set & set(def_index(f))]
    counts, owner, fimports = _scan(selected)
    if any(n not in counts for n in requested):
        counts, owner, fimports = _scan(files)
    def _own_imports(name):
        """ชื่อที่ "ไฟล์เจ้าของ symbol นั้น" import เองแล้ว — ตัดออกได้ว่าไม่ใช่บริบทภายนอก

        ตั้งใจใช้รายไฟล์ ไม่ใช้ union ของทุกไฟล์: ชื่ออย่าง console/neo_table/Prompt
        ถูก import เฉพาะใน soonai.py แต่โมดูลอื่นเรียกใช้ผ่าน bind — จึงต้องค้างอยู่ใน
        รายการ "ต้อง bind" และผลการจัดกลุ่มต้องไม่เปลี่ยนไปตามว่า parse ไฟล์ไหน
        """
        return fimports.get(owner.get(name, ""), set())

    wanted = [n for n in requested if n in counts]
    missing = [n for n in requested if n not in counts]
    inside = set(wanted)
    ext = {n: {k for k in counts[n]
               if k not in BUILTINS and k not in _own_imports(n) and k not in inside}
           for n in wanted}

    w, ref_dir, kinds = {}, {}, {}

    def add_edge(a, b, weight, kind):
        k = (a, b) if a < b else (b, a)
        w[k] = w.get(k, 0.0) + weight
        kinds.setdefault(k, set()).add(kind)

    for a in wanted:
        for b in wanted:
            if a != b and counts[a].get(b):
                ref_dir[(a, b)] = counts[a][b]
                add_edge(a, b, float(counts[a][b]), "ref")
    if cocite > 0:
        for pos, a in enumerate(wanted):
            for b in wanted[pos + 1:]:
                ea, eb = ext[a], ext[b]
                if not ea or not eb:
                    continue
                inter = len(ea & eb)
                if not inter:
                    continue
                jac = inter / len(ea | eb)
                if jac >= cite_min:
                    add_edge(a, b, cocite * jac, "co")

    cl = cluster({"nodes": wanted, "w": w}, max_groups=max_groups)
    raw_groups = cl["groups"]
    # token ที่โผล่เกือบทั้งชุด (เช่น "skill" ของโมดูล skills) ไม่ช่วยแยกกลุ่ม → ตัดออก
    df = {}
    for name in wanted:
        for tok in set(name_tokens(name)):
            df[tok] = df.get(tok, 0) + 1
    wide = frozenset(t for t, c in df.items() if len(wanted) >= 4 and c >= 0.6 * len(wanted))
    gid_of, used_ids, groups = {}, set(), []
    for i, members in enumerate(raw_groups):
        hint = group_name_hint(members, ref_dir, wide)
        gid, n = hint, 2
        while gid in used_ids:
            gid = f"{hint}{n}"
            n += 1
        used_ids.add(gid)
        gid_of[i] = gid
    for i, members in enumerate(raw_groups):
        mset = set(members)
        internal = sum(wt for (a, b), wt in w.items() if a in mset and b in mset)
        external = sum(wt for (a, b), wt in w.items() if (a in mset) != (b in mset))
        total = internal + external
        needs = sorted({k for a in members for k in counts[a]
                        if k not in inside and k not in BUILTINS
                        and k not in _own_imports(a) and k != a})
        top = sorted(((a, b, wt, "+".join(sorted(kinds.get((a, b), {"?"}))))
                      for (a, b), wt in w.items() if a in mset and b in mset),
                     key=lambda r: (-r[2], r[0], r[1]))[:4]
        groups.append({
            "id": gid_of[i],
            "name_hint": gid_of[i],
            "file_hint": "shared/%s.py" % gid_of[i].replace("-", "_"),
            "symbols": members,
            "internal_weight": round(internal, 3),
            "external_weight": round(external, 3),
            "cohesion": round(internal / total, 3) if total else None,
            "sources": sorted({owner[n] for n in members}),
            "needs": needs,
            "top_edges": [[a, b, round(wt, 3), kind] for a, b, wt, kind in top],
        })

    memb_of = {n: i for i, g in enumerate(raw_groups) for n in g}
    gdep = {}
    for (a, b), wt in ref_dir.items():
        ia, ib = memb_of[a], memb_of[b]
        if ia != ib:
            gdep[(ia, ib)] = gdep.get((ia, ib), 0) + wt
    for i, g in enumerate(groups):
        out, inc = [], []
        for (ia, ib), wt in gdep.items():
            if ia == i and ib != i:
                out.append({"to": gid_of[ib], "weight": round(wt, 2)})
            elif ib == i and ia != i:
                inc.append({"from": gid_of[ia], "weight": round(wt, 2)})
        g["depends_on"] = sorted(out, key=lambda d: (-d["weight"], d["to"]))
        g["depended_by"] = sorted(inc, key=lambda d: (-d["weight"], d["from"]))

    layers, cycles = layer_groups(raw_groups, ref_dir)
    gindex = {tuple(g): i for i, g in enumerate(raw_groups)}
    layers_out = [[gid_of[gindex[tuple(g)]] for g in layer] for layer in layers]
    cycles_out = [[gid_of[gindex[tuple(g)]] for g in cyc] for cyc in cycles]
    isolated = sorted(n for n in wanted if not any(n in edge for edge in w))
    warnings = []
    if not w:
        warnings.append("ไม่พบขอบอ้างอิง/co-citation ระหว่าง symbol เหล่านี้ — แยกกลุ่มไม่ได้")
    if max_groups and len(groups) > max_groups:
        warnings.append(f"ขอไม่เกิน {max_groups} กลุ่ม แต่ได้ {len(groups)} — ที่เหลือเป็น "
                        "กลุ่มโดดเดี่ยวที่ไม่มีขอบเชื่อมกับกลุ่มอื่น (ดู isolated)")
    if missing:
        warnings.append(f"ไม่พบ symbol: {', '.join(missing)}")
    if cycles_out:
        warnings.append("มีกลุ่มที่พึ่งกันไปมา (ต้องใช้ facade/bind): "
                        + "; ".join(" ↔ ".join(c) for c in cycles_out))
    return {
        "mode": "plan", "files": files, "count": len(wanted),
        "missing": missing, "modularity": round(cl["modularity"], 4),
        "groups": sorted(groups, key=lambda g: (-len(g["symbols"]), g["id"])),
        "layers": layers_out, "cycles": cycles_out, "isolated": isolated,
        "merges": cl["merges"], "warnings": warnings,
    }


def print_plan(rep):
    print(f"=== symbol plan: {rep['count']} symbol → {len(rep['groups'])} กลุ่ม "
          f"(modularity {rep['modularity']:.3f}) ===")
    for wmsg in rep["warnings"]:
        print(f"  [!] {wmsg}")
    for g in rep["groups"]:
        dep = ", ".join(f"→[{d['to']}] {d['weight']:.1f}" for d in g["depends_on"]) or "-"
        coh = f"{g['cohesion']:.2f}" if g["cohesion"] is not None else "-"
        print(f"\n  [{g['id']}] {len(g['symbols'])} symbol · cohesion {coh} · "
              f"ขอบใน {g['internal_weight']:.1f} / ตัดออก {g['external_weight']:.1f}")
        print(f"      ไฟล์ที่เสนอ: {g['file_hint']}")
        print(f"      symbols: {' '.join(g['symbols'])}")
        print(f"      พึ่ง: {dep}")
        if g["needs"]:
            print(f"      ต้อง bind จากภายนอก: {', '.join(g['needs'])}")
        if g["top_edges"]:
            print("      ขอบแน่นสุด: " + ", ".join(
                f"{a}—{b} ({wt:g} {kind})" for a, b, wt, kind in g["top_edges"]))
    print("\n=== ลำดับการย้าย (leaf-first: กลุ่มที่ไม่พึ่งใครก่อน) ===")
    for i, layer in enumerate(rep["layers"], 1):
        print(f"  {i}) " + ", ".join(layer))
    if rep["isolated"]:
        print(f"  [!] symbol ที่ไม่เกี่ยวกับใครในชุดนี้: {', '.join(rep['isolated'])}")
    if rep["merges"]:
        print(f"\n=== ลำดับการรวม ({len(rep['merges'])} ครั้ง — ΔQ มากสุดก่อน) ===")
        for names, gain, wt in rep["merges"][:12]:
            print(f"  ΔQ {gain:+.3f} (ขอบ {wt:g}) ← {' '.join(names)}")
        if len(rep["merges"]) > 12:
            print(f"  … อีก {len(rep['merges']) - 12} ครั้ง (ดูทั้งหมดด้วย --json)")


# ── โหมด --graph: วาดสถาปัตยกรรมเป็นภาพ (Mermaid / DOT / HTML) ──────────────
# ภาพเดียวบอกได้: ชั้นการพึ่งพา (leaf-first) · import (เส้นทึบ) vs bind (เส้นประ
# = พึ่งชื่อจาก soonai อยู่ — หนี้เชิงสถาปัตยกรรม) และโมดูลที่พึ่งกันไปมา

def _file_sizes(targets=None):
    sizes = {}
    for f in target_files(targets):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                sizes[Path(f).name] = sum(1 for _ in fh)
        except Exception:
            pass
    return sizes


def _owners(targets=None):
    """ชื่อ symbol -> ชื่อไฟล์ที่เป็นเจ้าของ (ใช้คำนวณน้ำหนักขอบ bind)"""
    out = {}
    for f in target_files(targets):
        for n in def_index(f):
            out.setdefault(n, Path(f).name)
    return out


def _layers_for(names, ref_dir):
    """layer (leaf-first) + cycles ของกลุ่มเดี่ยว ๆ — คืนเป็นชื่อโหนด (ไม่ซ้อนลิสต์)"""
    layers, cycles = layer_groups([[n] for n in names], ref_dir)
    return ([[g[0] for g in layer] for layer in layers],
            [[g[0] for g in cyc] for cyc in cycles])


def module_model(rep, targets=None):
    """แบบจำลองภาพสถาปัตยกรรมโมดูล: โหนด = ไฟล์ · ขอบ = import (ทึบ) / bind (ประ)"""
    names = sorted(rep["modules"])
    mid = {n: f"M{i}" for i, n in enumerate(names)}
    sizes = _file_sizes(targets)
    owners = _owners(targets)
    # น้ำหนักสำหรับเรียงชั้น: import = 1.0 (โครงสร้างจริง) · bind = 0.5
    # (bind ทำให้โมดูลถูกเรียงได้ แต่จะไม่พลิกทิศของ import — ดูรูปคือเส้นประที่พุ่งขึ้น)
    layer_w = {}
    nodes = []
    for n in names:
        info = rep["modules"][n]
        lines = sizes.get(n)
        nodes.append({
            "id": mid[n], "name": n,
            "label": n,
            "sub": " · ".join(x for x in (
                f"{info['defs']} defs",
                f"{lines:,} บรรทัด" if lines else "",
                f"bind {len(info['bind_refs'])}" if info["bind_refs"] else "") if x),
            "external": len(info["bind_refs"]),
        })
    edges = []
    for n in names:
        info = rep["modules"][n]
        for other in info["imports"]:
            if other in mid:
                layer_w[(n, other)] = layer_w.get((n, other), 0.0) + 1.0
                edges.append({"from": mid[n], "to": mid[other], "kind": "import",
                              "weight": 1, "label": "import"})
        for other in info["bind_deps"]:
            if other not in mid:
                continue
            w = sum(1 for nm in info["bind_refs"] if owners.get(nm) == other)
            layer_w[(n, other)] = layer_w.get((n, other), 0.0) + 0.5
            edges.append({"from": mid[n], "to": mid[other], "kind": "bind",
                          "weight": w, "label": f"bind ({w} ชื่อ)" if w else "bind"})
    layers, cycles = _layers_for(names, layer_w)
    to_id = [[mid[x] for x in layer] for layer in layers]
    placed = {x for layer in to_id for x in layer}
    notes = [f"{len(names)} โมดูล · ขอบ import {sum(1 for e in edges if e['kind'] == 'import')}"
             f" · ขอบ bind {sum(1 for e in edges if e['kind'] == 'bind')}",
             "เส้นประ (bind) = โมดูลเรียกชื่อจาก namespace ของ soonai ตอนรัน = จุดที่ยัง coupling"]
    if len(placed) < len(names):
        notes.append("โมดูลที่เรียงชั้นไม่ได้: " +
                     ", ".join(n["name"] for n in nodes if n["id"] not in placed))
    return {
        "kind": "modules",
        "title": "สถาปัตยกรรมโมดูล soonai (เส้นทึบ = import · เส้นประ = bind จาก soonai)",
        "nodes": nodes, "edges": edges, "layers": to_id,
        "cycles": [[mid[x] for x in c] for c in cycles],
        "notes": notes,
    }


def plan_model(plan_rep):
    """แบบจำลองภาพของข้อเสนอจาก --plan: โหนด = กลุ่มที่เสนอ · ขอบ = พึ่งกัน (มีทิศทาง)"""
    groups = plan_rep["groups"]
    gid = {g["id"]: f"G{i}" for i, g in enumerate(groups)}
    isolated = set(plan_rep["isolated"])
    nodes = []
    for g in groups:
        tail = ""
        if g["cohesion"] is not None:
            tail = f" · cohesion {g['cohesion']:.2f}"
        nodes.append({
            "id": gid[g["id"]], "name": g["id"], "label": g["id"],
            "sub": f"{len(g['symbols'])} symbol{tail}\n→ {g['file_hint']}",
            "solo": len(g["symbols"]) == 1,
            "all_isolated": all(x in isolated for x in g["symbols"]),
            "external": len(g["needs"]),
        })
    ref_dir = {}
    edges = []
    for g in groups:
        for d in g["depends_on"]:
            ref_dir[(g["id"], d["to"])] = d["weight"]
            edges.append({"from": gid[g["id"]], "to": gid[d["to"]], "kind": "dep",
                          "weight": d["weight"], "label": f"{d['weight']:g}"})
    layers = [[gid[x] for x in layer] for layer in plan_rep["layers"]]
    cycles = [[gid[x] for x in c] for c in plan_rep["cycles"]]
    return {
        "kind": "plan",
        "title": f"ข้อเสนอการแยกโมดูลจาก {plan_rep['count']} symbol "
                 f"(modularity {plan_rep['modularity']:.3f}) — ลูกศร = พึ่งกลุ่มอื่น",
        "nodes": nodes, "edges": edges, "layers": layers, "cycles": cycles,
        "notes": plan_rep["warnings"],
    }


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _node_by_id(model):
    return {n["id"]: n for n in model["nodes"]}


def _layer_order(model):
    """เรียงชั้นจาก root → leaf (บนลงล่าง) พร้อมหมายเลขชั้นให้อ่านง่าย"""
    layers = [lay for lay in model["layers"] if lay]
    total = len(layers)
    return [(total - i, layer) for i, layer in enumerate(reversed(layers))]


def _mermaid_label(node):
    """ป้ายโหนด Mermaid: ชื่อตัวหนา + บรรทัดย่อย (escape + แปลง \n เป็น <br/>)"""
    sub = _esc(node["sub"]).replace("\n", "<br/>")
    name = _esc(node["label"])
    return f'"{name}<br/><small>{sub}</small>"'


def render_mermaid(model, title=None):
    """Mermaid flowchart (วางใน Markdown/GitHub/```mermaid ได้เลย)"""
    by_id = _node_by_id(model)
    out = [f"%% {title or model['title']}", "%% (สร้างด้วย depgraph.py --graph)", "flowchart TB"]
    placed = set()
    for depth, layer in _layer_order(model):
        out.append(f'  subgraph L{depth}["ชั้น {depth}"]')
        for x in layer:
            if x in by_id:
                out.append(f'    {x}[{_mermaid_label(by_id[x])}]')
                placed.add(x)
        out.append("  end")
    for n in model["nodes"]:
        if n["id"] not in placed:
            out.append(f'  {n["id"]}[{_mermaid_label(n)}]')
    for e in model["edges"]:
        arrow = "-.->" if e["kind"] == "bind" else "-->"   # bind = เส้นประ (seam)
        out.append(f'  {e["from"]} {arrow}|{e["label"]}| {e["to"]}')
    cyc = sorted({x for c in model["cycles"] for x in c})
    if cyc:
        out.append("  classDef cyc fill:#ffe3e3,stroke:#c0392b,stroke-width:2px;")
        out.append("  class " + ",".join(cyc) + " cyc;")
    if model["cycles"]:
        out.append("  %% [!] กลุ่มที่พึ่งกันไปมา: " +
                   "; ".join(" ↔ ".join(by_id[x]["name"] for x in c if x in by_id)
                             for c in model["cycles"]))
    for note in model.get("notes", []):
        out.append(f"  %% {note}")
    return "\n".join(out) + "\n"


def render_dot(model, title=None):
    """Graphviz DOT (dot -Tsvg arch.dot > arch.svg)"""
    by_id = _node_by_id(model)
    t = _esc(title or model["title"])
    out = [f"// {title or model['title']}", "digraph arch {", "  rankdir=TB;",
           f'  graph [label="{t}", labelloc=t, fontsize=14];',
           '  node [shape=box, style="rounded,filled", fillcolor="#f7f7f7", '
           'fontname="Helvetica"];',
           '  edge [fontname="Helvetica"];']
    placed = set()
    for depth, layer in _layer_order(model):
        out.append(f"  subgraph cluster_{depth} {{")
        out.append(f'    label="ชั้น {depth}";')
        out.append('    style="rounded,dashed"; color="#bbbbbb";')
        for x in layer:
            if x in by_id:
                n = by_id[x]
                lab = "%s\\n%s" % (n["label"], n["sub"].replace("\n", " · "))
                out.append(f'    {n["id"]} [label="{_esc(lab).replace(chr(34), "'")}"];')
                placed.add(x)
        out.append("  }")
    for n in model["nodes"]:
        if n["id"] not in placed:
            lab = "%s\\n%s" % (n["label"], n["sub"].replace("\n", " · "))
            out.append(f'  {n["id"]} [label="{_esc(lab).replace(chr(34), "'")}"];')
    cyc = sorted({x for c in model["cycles"] for x in c})
    for e in model["edges"]:
        style = 'style="dashed", color="#777777", ' if e["kind"] == "bind" else ""
        out.append(f'  {e["from"]} -> {e["to"]} [{style}label="{e["label"]}", fontsize=10];')
    for x in cyc:
        out.append(f'  {x} [fillcolor="#ffe3e3", color="#c0392b", penwidth=2];')
    for note in model.get("notes", []):
        out.append(f"  // {note}")
    if model["cycles"]:
        out.append("  // [!] กลุ่มที่พึ่งกันไปมา: " + "; ".join(
            " ↔ ".join(by_id[x]["name"] for x in c if x in by_id) for c in model["cycles"]))
    out.append("}")
    return "\n".join(out) + "\n"


def render_svg(model, title=None):
    """SVG ที่วาดเอง (ไม่พึ่ง JS/CDN) — ชั้นบนลงล่าง · import เส้นทึบ · bind เส้นประ

    เหตุผลที่วาดเอง: Mermaid ต้องโหลดจาก CDN ถ้าเครื่องออฟไลน์จะเห็นเพียงซอร์ส
    """
    t = title or model["title"]
    by_id = _node_by_id(model)
    # เรียงบนลงล่างแบบสถาปัตยกรรมปกติ: ชั้นบน = โมดูลที่พึ่งคนอื่น (root) · ล่าง = ฐาน
    rows = []
    for layer in reversed([lay for lay in model["layers"] if lay]):
        ids = [x for x in layer if x in by_id]
        if ids:
            rows.append(ids)
    placed = {x for row in rows for x in row}
    rest = [n["id"] for n in model["nodes"] if n["id"] not in placed]
    if rest:
        rows.append(rest)

    def lines_of(node):
        out = [node["label"]] + [s for s in str(node["sub"]).split("\n") if s]
        return out[:3]

    def width_of(node):
        return max(96.0, max(len(x) for x in lines_of(node)) * 6.6 + 26)

    gap_x, gap_y, row_gap, margin, head = 30.0, 60.0, 26.0, 22.0, 34.0
    max_row_w = 720.0
    # 1) ตัดชั้นที่กว้างเกินเป็นหลายแถว (ให้ภาพไม่ยืดออกด้านข้างจนอ่านไม่ได้)
    plan_rows = []
    for row in rows:
        chunk, cur = [], 0.0
        for nid in row:
            w = width_of(by_id[nid])
            add = w + (gap_x if chunk else 0)
            if chunk and cur + add > max_row_w:
                plan_rows.append((chunk, False))
                chunk, cur = [], 0.0
                add = w
            chunk.append(nid)
            cur += add
        if chunk:
            plan_rows.append((chunk, True))
    # 2) เรียงในแถวตาม barycenter ของเพื่อนบ้านที่วางแล้ว (ลดเส้นตัดกัน)
    nbrs = {}
    for e in model["edges"]:
        nbrs.setdefault(e["from"], set()).add(e["to"])
        nbrs.setdefault(e["to"], set()).add(e["from"])
    pos, ordered = {}, []
    for ri, (row, _new) in enumerate(plan_rows):
        if ri == 0:
            ordered.append(list(row))
            for ci, nid in enumerate(row):
                pos[nid] = ci
            continue
        scored = []
        for ci, nid in enumerate(row):
            seen = [pos[x] for x in nbrs.get(nid, ()) if x in pos]
            scored.append((sum(seen) / len(seen) if seen else float("inf"), ci, nid))
        scored.sort()
        ordered.append([nid for _s, _c, nid in scored])
        for ci, (_s, _c, nid) in enumerate(scored):
            pos[nid] = ci
    # 3) วางกล่อง
    heights = [14.0 + 13.0 * max(len(lines_of(by_id[n])) for n in row) + 12
               for row in ordered]
    row_w = [sum(width_of(by_id[x]) for x in row) + gap_x * (len(row) - 1) for row in ordered]
    width = max(row_w + [240.0]) + 2 * margin
    boxes, y = {}, head + margin
    for row, rw, h, (_ids, new_layer) in zip(ordered, row_w, heights, plan_rows):
        x = (width - rw) / 2
        for nid in row:
            w = width_of(by_id[nid])
            boxes[nid] = (x, y, w, h)
            x += w + gap_x
        y += h + (gap_y if new_layer else row_gap)
    height = y - row_gap + margin
    cyc = {x for c in model["cycles"] for x in c}

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
           f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
           'font-family="Segoe UI, system-ui, sans-serif">',
           '<defs>'
           '<marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
           'markerHeight="7" orient="auto-start-reverse">'
           '<path d="M 0 0 L 10 5 L 0 10 z" fill="#5f6368"/></marker>'
           '<marker id="arwb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
           'markerHeight="7" orient="auto-start-reverse">'
           '<path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa0a6"/></marker>'
           '</defs>',
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           f'<text x="{margin:.0f}" y="22" font-size="14" font-weight="600" '
           f'fill="#202124">{_esc(t)}</text>']

    # ขอบก่อน เพื่อให้กล่องทับเส้น
    for e in model["edges"]:
        a, b = boxes.get(e["from"]), boxes.get(e["to"])
        if not a or not b:
            continue
        x1, y1 = a[0] + a[2] / 2, a[1] + a[3]
        x2, y2 = b[0] + b[2] / 2, b[1]
        bind = e["kind"] == "bind"
        dash = ' stroke-dasharray="5 4"' if bind else ""
        col = "#9aa0a6" if bind else "#5f6368"
        mark = "arwb" if bind else "arw"
        mid_y = (y1 + y2) / 2
        out.append(f'<path d="M {x1:.0f} {y1:.0f} C {x1:.0f} {mid_y:.0f} '
                   f'{x2:.0f} {mid_y:.0f} {x2:.0f} {y2:.0f}" fill="none" '
                   f'stroke="{col}"{dash} stroke-width="1.3" marker-end="url(#{mark})"/>')
        out.append(f'<text x="{(x1 + x2) / 2:.0f}" y="{mid_y - 3:.0f}" font-size="9.5" '
                   f'fill="{col}" text-anchor="middle" paint-order="stroke" '
                   f'stroke="#ffffff" stroke-width="3">{_esc(e["label"])}</text>')

    for nid, (x, y0, w, h) in boxes.items():
        node = by_id[nid]
        edge_col = "#c0392b" if nid in cyc else "#b8b8b8"
        fill = "#ffe3e3" if nid in cyc else "#f7f7f7"
        out.append(f'<rect x="{x:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" '
                   f'rx="8" fill="{fill}" stroke="{edge_col}" stroke-width="1.4"/>')
        lines = lines_of(node)
        out.append(f'<text x="{x + 11:.0f}" y="{y0 + 20:.0f}" font-size="12" '
                   f'font-weight="600" fill="#202124">{_esc(lines[0])}</text>')
        for i, line in enumerate(lines[1:]):
            out.append(f'<text x="{x + 11:.0f}" y="{y0 + 34 + i * 13:.0f}" font-size="10" '
                       f'fill="#5f6368">{_esc(line)}</text>')

    legend = "เส้นทึบ = import · เส้นประ = bind (พึ่งชื่อจาก soonai)" \
        if model["kind"] == "modules" else "ลูกศร = กลุ่มต้นทางพึ่งกลุ่มปลายทาง"
    notes = ([legend] + list(model.get("notes", [])))[:3]
    ly = height - 8 - 12 * (len(notes) - 1)
    for i, note in enumerate(notes):
        out.append(f'<text x="{margin:.0f}" y="{ly + i * 12:.0f}" font-size="10" '
                   f'fill="#5f6368">{_esc(note)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def render_html(model, title=None):
    """HTML หน้าตียว: ฝัง SVG ที่วาดเอง (เห็นภาพทันทีแม้ออฟไลน์) + ซอร์สให้คัดลอก"""
    t = title or model["title"]
    svg = render_svg(model, title)
    msrc = _esc(render_mermaid(model, title))
    dsrc = _esc(render_dot(model, title))
    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(t)}</title>
<style>
 body {{ font-family: system-ui, "Segoe UI", sans-serif; margin: 24px; color: #202124; }}
 h1 {{ font-size: 17px; font-weight: 600; }}
 .diagram {{ background: #fff; border: 1px solid #e5e5e5; border-radius: 10px; padding: 8px;
            overflow: auto; }}
 .diagram svg {{ display: block; max-width: 100%; height: auto; }}
 pre.src {{ background: #f6f6f6; padding: 12px; overflow: auto; font-size: 12px; }}
 details {{ margin-top: 14px; }}
 summary {{ cursor: pointer; font-size: 13px; }}
</style></head>
<body>
<h1>{_esc(t)}</h1>
<div class="diagram">
{svg}</div>
<details><summary>ซอร์ส Mermaid (วางใน Markdown/```mermaid ได้)</summary>
<pre class="src">{msrc}</pre></details>
<details><summary>ซอร์ส Graphviz DOT (dot -Tsvg)</summary>
<pre class="src">{dsrc}</pre></details>
</body></html>
"""


def _infer_format(path, given):
    if given:
        return "mermaid" if given in ("mmd", "mermaid") else given
    suf = Path(path).suffix.lower()
    if suf in (".dot", ".gv"):
        return "dot"
    if suf == ".svg":
        return "svg"
    if suf in (".html", ".htm"):
        return "html"
    return "mermaid"


def render_model(model, fmt="mermaid", title=None):
    if fmt == "dot":
        return render_dot(model, title)
    if fmt == "svg":
        return render_svg(model, title)
    if fmt == "html":
        return render_html(model, title)
    return render_mermaid(model, title)


def _parser():
    import argparse
    ap = argparse.ArgumentParser(
        prog="depgraph",
        description="dependency graph + ข้อเสนอการแยกโมดูลของ soonai.py / shared/*.py")
    ap.add_argument("--json", action="store_true", help="ออก JSON")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 ถ้าเจอ cycle ที่เป็นปัญหา (ใช้เป็น CI gate)")
    ap.add_argument("--plan", nargs="+", metavar="SYMBOL",
                    help="เสนอการจัดกลุ่มโมดูลจากรายชื่อ symbol (cohesion สูงสุด)")
    ap.add_argument("--plan-file", metavar="PATH",
                    help="อ่านรายชื่อ symbol จากไฟล์ (บรรทัดละชื่อ · # = คอมเมนต์)")
    ap.add_argument("--plan-all", nargs="?", const="soonai.py", metavar="FILE",
                    help="ใช้ทุก symbol ระดับบนของไฟล์ (ดีฟอลต์ soonai.py)")
    ap.add_argument("--max-groups", type=int, default=None,
                    help="เพดานจำนวนกลุ่มที่โหมด plan จะรวมถึง")
    ap.add_argument("--no-cocite", action="store_true",
                    help="โหมด plan: ใช้แค่ขอบอ้างอิงจริง ไม่ใช้ co-citation")
    ap.add_argument("--graph", action="store_true",
                    help="ออกเป็นภาพ (Mermaid/DOT/HTML) — ใช้กับ --plan ก็ได้")
    ap.add_argument("--format", choices=["mermaid", "mmd", "dot", "svg", "html"], default=None,
                    help="รูปแบบภาพ (ดีฟอลต์ mermaid · เดาจากนามสกุล --out) — svg/html ไม่พึ่ง CDN")
    ap.add_argument("--out", metavar="PATH", default=None,
                    help="เขียนภาพลงไฟล์ (ไม่ระบุ = ออกทาง stdout)")
    ap.add_argument("--title", default=None, help="ชื่อเรื่องของภาพ")
    return ap


def _read_symbols_file(path):
    names = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def _print_modules(rep):
    print("=== modules (import / bind deps) ===")
    for p, i in sorted(rep["modules"].items()):
        print(f"  {p:18s} defs={i['defs']:4d}  imports={i['imports']}  "
              f"bind_deps={i['bind_deps']}")
    print("\n=== import cycles ===")
    print("  " + ("(none)" if not rep["import_cycles"] else str(rep["import_cycles"])))
    print("=== bind (cross-module) cycles ===")
    print("  " + ("(none)" if not rep["bind_cycles"] else str(rep["bind_cycles"])))
    print("\n=== external (bind-provided) refs per module ===")
    for p, i in sorted(rep["modules"].items()):
        if p == "soonai.py":
            continue
        refs = i["bind_refs"]
        print(f"  {p:18s} {len(refs):3d} names e.g. {sorted(refs)[:10]}")


def _gate_code(rep):
    """exit code ของ CI gate — 1 เมื่อมี cycle (import หรือ bind) ที่เป็นปัญหา"""
    return 1 if (rep["import_cycles"] or rep["bind_cycles"]) else 0


def main(argv=None):
    args = _parser().parse_args(sys.argv[1:] if argv is None else list(argv))
    wants_plan = bool(args.plan or args.plan_file or args.plan_all)
    wants_graph = bool(args.graph or args.out)

    if wants_plan:
        # โหมด plan ไม่ต้องใช้ import/bind graph — ยกเว้นเมื่อขอ --check ด้วย
        code = _gate_code(build()) if args.check else 0
        symbols = list(args.plan or [])
        if args.plan_file:
            symbols += _read_symbols_file(args.plan_file)
        if args.plan_all:
            want = sorted(ref_counts(args.plan_all))
            symbols = want if not symbols else symbols + [n for n in want if n not in set(symbols)]
        data = plan(symbols, max_groups=args.max_groups,
                    cocite=0.0 if args.no_cocite else CITE_WEIGHT)
        if wants_graph:
            return _emit_graph(plan_model(data), args, code)
        if args.json:
            print(_json.dumps(data, ensure_ascii=False, indent=1))
        else:
            print_plan(data)
        return code

    rep = build()
    code = _gate_code(rep) if args.check else 0
    if wants_graph:
        return _emit_graph(module_model(rep), args, code)
    if args.json:
        print(_json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        _print_modules(rep)
    return code


def _emit_graph(model, args, code=0):
    """ออกภาพ: stdout หรือ --out (เดาชนิดจากนามสกุลไฟล์ถ้าไม่ระบุ --format)"""
    fmt = _infer_format(args.out or "", args.format)
    text = render_model(model, fmt, args.title)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"เขียนภาพ {fmt} ไปที่ {args.out}")
    else:
        print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
