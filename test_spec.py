# -*- coding: utf-8 -*-
"""Regression: soonai.spec ต้องอ้างอิงของที่มีอยู่จริง และใช้ API ของ PyInstaller 6

spec เคยพังเงียบ ๆ เพราะไม่มีอะไรตรวจ:
- datas ชี้ไปที่ shared/skills.off/*.md กับ shared/core_utils/* ซึ่งไม่มี(แล้ว)
- hiddenimports มี 'model_selector' ที่ไม่มีอยู่จริง และชื่อ shared.X ที่ pathex หาไม่เจอ
- ใช้ PYZ(a.pure, a.zipped_data, cipher=block_cipher) = API ของ PyInstaller 5
  (รุ่น 6 ตัด cipher/zipped_data/win_no_prefer_redirects/win_private_assemblies ออก)
- ใส่ a.binaries/a.datas เข้าทั้ง EXE และ COLLECT พร้อมกัน (onefile ปน onedir)

การรัน PyInstaller จริงหนักเกินสำหรับเทสต์ จึง exec spec ด้วย stub ที่ดักจับ
kwargs/args ไว้ตรวจแทน — จับ bug ทุกข้อข้างบนได้โดยไม่ต้อง build
"""
import os
from pathlib import Path

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "soonai.spec"
SPEC_TEXT = SPEC.read_text(encoding="utf-8")


class _Node:
    """ตัวแทน a/pyz/exe ใน spec — เข้า attribute ไหนก็ได้แล้วจำชื่อไว้ให้อ้างตอนตรวจ"""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, item):
        return _Node(f"{self._name}.{item}")


captured = {}


def _stub(kind, node_name=None):
    def fn(*args, **kwargs):
        captured[kind] = {"args": args, "kwargs": kwargs}
        return _Node(node_name or kind.lower())
    return fn


namespace = {
    "__file__": str(SPEC),
    "__name__": "soonai_spec",
    "Analysis": _stub("Analysis", "a"),
    "PYZ": _stub("PYZ", "pyz"),
    "EXE": _stub("EXE", "exe"),
    "COLLECT": _stub("COLLECT", "coll"),
}
# spec เขียน Path('shared/...') แบบ relative — ต้องรันจาก ROOT จริง
_cwd = os.getcwd()
os.chdir(ROOT)
try:
    exec(compile(SPEC_TEXT, str(SPEC), "exec"), namespace)   # spec คือโค้ดของเราเอง
finally:
    os.chdir(_cwd)

for kind in ("Analysis", "PYZ", "EXE"):
    check(f"spec เรียก {kind}()", kind in captured)
if FAILS:
    print(f"\n{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)

analysis = captured["Analysis"]["kwargs"]
pyz_args = captured["PYZ"]["args"]
pyz_kwargs = captured["PYZ"]["kwargs"]


def _node_names(args):
    return [getattr(a, "_name", None) or repr(a) for a in args]


# ── 1) ต้องเป็น API ของ PyInstaller 6 ────────────────────────────────────────
for key in ("cipher", "win_no_prefer_redirects", "win_private_assemblies"):
    check(f"Analysis ไม่มี kwarg ของ PyInstaller 5: {key}", key not in analysis)
check("PYZ รับแค่ a.pure (ไม่มี a.zipped_data)",
      _node_names(pyz_args) == ["a.pure"], _node_names(pyz_args))
check("PYZ ไม่ส่ง cipher", "cipher" not in pyz_kwargs, sorted(pyz_kwargs))
check("spec ไม่ประกาศ block_cipher", "block_cipher" not in namespace)

# onefile กับ onedir ต้องเลือกทางเดียว: onefile ใส่ a.binaries/a.datas ใน EXE,
# onedir ใส่ใน COLLECT — ประกาศทั้งคู่จะทำให้ของถูกบรรจุซ้ำ/บิลด์พัง
exe_nodes = set(_node_names(captured["EXE"]["args"]))
coll_nodes = set(_node_names(captured.get("COLLECT", {}).get("args", ())))
onefile = {"a.binaries", "a.datas"} <= exe_nodes
onedir = "COLLECT" in captured and {"a.binaries", "a.datas"} <= coll_nodes
check("เป็น onefile หรือ onedir ทางเดียว (ไม่ปนกัน)", onefile != onedir,
      f"EXE={sorted(exe_nodes)} COLLECT={sorted(coll_nodes)}")
if onedir:
    check("onedir: EXE ต้องไม่รับ a.binaries/a.datas",
          not ({"a.binaries", "a.datas"} & exe_nodes), sorted(exe_nodes))

# ── 2) entrypoint + pathex ──────────────────────────────────────────────────
check("entrypoint คือ soonai.py", captured["Analysis"]["args"][:1] == (["soonai.py"],),
      captured["Analysis"]["args"][:1])
# soonai.py ทำ sys.path.insert(shared/) ตอนรัน ซึ่ง PyInstaller มองไม่เห็น
# ถ้าไม่ใส่ pathex โมดูลใน shared/ จะหาไม่เจอเลย
check("pathex มี shared", "shared" in (analysis.get("pathex") or []), analysis.get("pathex"))

# ── 3) datas ทุกตัวต้องมีอยู่จริง ────────────────────────────────────────────
datas = analysis.get("datas") or []
check("datas ไม่ว่าง (ต้องมีข้อมูลตอนรัน)", bool(datas))
for source, dest in datas:
    check(f"datas: มี {source}", Path(source).exists(), source)
    check(f"datas: dest อยู่ใน bundle: {dest}",
          not Path(dest).is_absolute() and ".." not in Path(dest).parts, dest)

# ── 4) hiddenimports ต้องชี้ที่ไฟล์จริง ─────────────────────────────────────
hidden = analysis.get("hiddenimports") or []
check("hiddenimports ไม่ว่าง", bool(hidden))
for name in hidden:
    check(f"hiddenimport {name} ไม่ใช้ prefix shared. (pathex ชี้ shared/ แล้ว)",
          not name.startswith("shared."), name)
    check(f"hiddenimport {name} มีไฟล์รองรับ",
          (ROOT / "shared" / f"{name}.py").is_file()
          or (ROOT / "shared" / name / "__init__.py").is_file(), name)

# โมดูลที่ soonai.py กับ shared/*.py import จริงต้องประกาศครบ — ขาดแล้ว exe จะ ImportError
EXPECTED = {"chat", "computer", "debug", "mcp_client", "permissions", "project",
            "providers", "runtime", "shell", "skills", "symbols", "ui_render",
            "ui_theme", "usage"}
check("hiddenimports ครบทุกโมดูลใน shared/", EXPECTED <= set(hidden),
      f"ขาด {sorted(EXPECTED - set(hidden))}")
check("hiddenimports ไม่มีชื่อเกินไฟล์ใน shared/",
      set(hidden) <= {p.stem for p in (ROOT / "shared").glob("*.py")},
      sorted(set(hidden) - {p.stem for p in (ROOT / "shared").glob("*.py")}))

# ── 5) ของที่ลบไปแล้วต้องไม่โผล่ใน spec ─────────────────────────────────────
for dead in ("core_utils", "cli_smooth", "skills.off", "soonai_custom",
             "model_selector", "apps", "packages", "eval_ambiguous"):
    check(f"spec ไม่อ้างของตาย: {dead}", dead not in SPEC_TEXT)

# ── 6) ต้องไม่แพ็กความลับ/ค่าส่วนตัวของผู้ใช้ลง bundle ───────────────────────
sources = [str(s).replace("\\", "/") for s, _ in datas]
for secret in ("keys.json", "shared/config.json", "shared/team.json", "mcp.json"):
    check(f"datas ไม่แพ็ก {secret}",
          not any(s == secret or s.endswith("/" + secret) for s in sources), sources)
# แต่ต้องมี *.default.json เพราะ runtime.ensure_user_files() ใช้เป็นต้นแบบตอนรันครั้งแรก
names = {Path(s).name for s in sources}
for needed in ("config.default.json", "team.default.json", "mcp_catalog.json"):
    check(f"datas มี {needed}", needed in names, sorted(names))

# ── 7) โครง skills ต้องคงชื่อโฟลเดอร์ ────────────────────────────────────────
# skills.py อ่าน SHARED_DIR/skills/<ชื่อสกิล>/SKILL.md — datas แบบ glob จะแบนโฟลเดอร์
# ทำให้ทุกสกิลกลายเป็น SKILL.md ก้อนเดียวทับกัน
skill_dests = [d for s, d in datas if "SKILL.md" in str(s).replace("\\", "/")]
check("มี SKILL.md ถูกแพ็ก", bool(skill_dests), datas)
on_disk = {p.parent.name for p in (ROOT / "shared" / "skills").glob("*/SKILL.md")}
bundled = {Path(d).name for d in skill_dests}
check("ทุกสกิลบนดิสก์ถูกแพ็กเป็นโฟลเดอร์ของตัวเอง", on_disk == bundled,
      f"ขาด {sorted(on_disk - bundled)} เกิน {sorted(bundled - on_disk)}")
check("dest ของสกิลอยู่ใต้ shared/skills/<ชื่อ>",
      all(Path(d).as_posix().startswith("shared/skills/") and len(Path(d).parts) == 3
          for d in skill_dests), skill_dests)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
    raise SystemExit(1)
print("ALL SPEC TESTS PASSED")
