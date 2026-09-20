# -*- coding: utf-8 -*-
"""Regression: แผนที่สัญลักษณ์ (M5) + การจัดอันดับผล grep
- file_symbols: Python ใช้ ast · js/ts/go ใช้ regex · ไฟล์พัง = [] · ภาษาอื่น = []
- outline_text: รูปแบบ 'path: บรรทัด: สัญลักษณ์' + ตัดตาม budget + ไฟล์เดียวได้
- _attach_symbol_map: ใส่ครั้งเดียว ไม่ซ้ำ + ปิดได้ด้วย env
- grep: มีหัวสรุปจำนวนจุด/ไฟล์ · จัดอันดับไฟล์ที่เจอหลายจุดก่อน · regex พัง = ERROR
ไม่แตะเน็ต
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "shared")

import soonai as S  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print(f"ok: {name}")
    else:
        print(f"FAIL: {name} {extra}")
        FAILS.append(name)


tmp = Path(tempfile.mkdtemp(prefix="soonai-sym-"))
_orig = (S.workspace_root, S.load_config)
S.workspace_root = lambda: tmp.resolve()
S.load_config = lambda: {"agent": {"symbol_map": True}}

try:
    (tmp / "pkg").mkdir()
    (tmp / "pkg" / "mod.py").write_text(
        "import os\n\nMAX_N = 5\n\n\nclass Store:\n    def get(self):\n        return 1\n\n\n"
        "def main():\n    return 2\n\n\nasync def fetch():\n    return 3\n", encoding="utf-8")
    (tmp / "app.js").write_text(
        "export function boot() {}\nclass Widget {}\nconst CONFIG = {};\n", encoding="utf-8")
    (tmp / "main.go").write_text(
        "package main\n\nfunc main() {\n}\n\ntype Server struct{}\n", encoding="utf-8")
    (tmp / "broken.py").write_text("def (:\n", encoding="utf-8")
    (tmp / "data.txt").write_text("hello\n", encoding="utf-8")

    py = S.file_symbols(tmp / "pkg" / "mod.py")
    labels = [lbl for _ln, lbl in py]
    check("py: เจอ class", any("class Store" in x for x in labels), labels)
    check("py: เจอเมธอดในคลาส", any("Store.get" in x for x in labels), labels)
    check("py: เจอ def ระดับบน", "def main" in labels and "def fetch" in labels, labels)
    check("py: เจอค่าคงที่ตัวใหญ่", any("MAX_N" in x for x in labels), labels)
    check("py: เลขบรรทัดถูก", dict((lbl, ln) for ln, lbl in py).get("def main") == 11, py)

    js = [lbl for _ln, lbl in S.file_symbols(tmp / "app.js")]
    check("js: เจอ function/class/const",
          any("boot" in x for x in js) and any("Widget" in x for x in js)
          and any("CONFIG" in x for x in js), js)
    go = [lbl for _ln, lbl in S.file_symbols(tmp / "main.go")]
    check("go: เจอ func/type", any("main" in x for x in go) and any("Server" in x for x in go), go)
    check("py พัง = []", S.file_symbols(tmp / "broken.py") == [])
    check("ไฟล์ไม่ใช่โค้ด = []", S.file_symbols(tmp / "data.txt") == [])
    check("ไฟล์ไม่มี = []", S.file_symbols(tmp / "nope.py") == [])

    out = S.outline_text(tmp)
    check("outline: มีชื่อไฟล์", "pkg/mod.py" in out.replace("\\", "/"), out[:200])
    check("outline: มีบรรทัด: สัญลักษณ์", ": def main" in out, out[:200])
    check("outline ไฟล์เดียว", S.outline_text(tmp / "pkg" / "mod.py").startswith("mod.py"),
          S.outline_text(tmp / "pkg" / "mod.py")[:60])
    check("outline: ไฟล์พังไม่ทำให้พัง", "broken.py" not in out, out[:200])
    small = S.outline_text(tmp, budget=40)
    check("outline: ตัดตาม budget", len(small) <= 40, len(small))
    check("outline: โฟลเดอร์ว่างบอกตรง ๆ",
          S.outline_text(tmp / "ไม่มีจริง").startswith("(ไม่พบไฟล์"), S.outline_text(tmp / "x")[:40])

    # แนบเข้า system prompt ครั้งเดียว
    msgs = [{"role": "system", "content": "sys"}]
    S._attach_symbol_map(msgs, budget=400)
    check("attach: ใส่แผนที่สัญลักษณ์", "แผนที่สัญลักษณ์" in msgs[0]["content"])
    before = msgs[0]["content"]
    S._attach_symbol_map(msgs, budget=400)
    check("attach: ไม่ใส่ซ้ำ", msgs[0]["content"] == before)
    msgs2 = [{"role": "user", "content": "hi"}]
    check("attach: ไม่แตะถ้าไม่มี system", S._attach_symbol_map(msgs2)[0]["role"] == "user")
    os.environ["SOONAI_NO_SYMBOL_MAP"] = "1"
    m3 = [{"role": "system", "content": "sys"}]
    check("attach: ปิดด้วย env ได้", S._attach_symbol_map(m3)[0]["content"] == "sys")
    os.environ.pop("SOONAI_NO_SYMBOL_MAP", None)
    S.load_config = lambda: {"agent": {"symbol_map": False}}
    m4 = [{"role": "system", "content": "sys"}]
    check("attach: ปิดด้วย config ได้", S._attach_symbol_map(m4)[0]["content"] == "sys")
    S.load_config = lambda: {"agent": {"symbol_map": True}}

    # grep: หัวสรุป + จัดอันดับ
    (tmp / "many.py").write_text("TAG = 1\nTAG = 2\nTAG = 3\n", encoding="utf-8")
    (tmp / "one.py").write_text("x = 1\nTAG = 9\n", encoding="utf-8")
    g = S.run_tool("grep", {"pattern": "TAG", "path": str(tmp)})
    check("grep: มีหัวสรุป", g.startswith("(เจอ ") and "ไฟล์" in g.splitlines()[0], g[:120])
    body = g.splitlines()[1:]
    check("grep: ไฟล์ที่เจอหลายจุดมาก่อน", "many.py" in body[0] and len(body) >= 4, body[:4])
    check("grep: มีเลขบรรทัด", ":1: TAG = 1" in g, g[:200])
    g2 = S.run_tool("grep", {"pattern": "ไม่มีอยู่นะ", "path": str(tmp)})
    check("grep: ไม่พบ = (ไม่พบ)", g2 == "(ไม่พบ)", g2)
    g3 = S.run_tool("grep", {"pattern": "TAG[", "path": str(tmp)})
    check("grep: regex พัง = ERROR", g3.startswith("ERROR:"), g3[:80])
    g4 = S.run_tool("grep", {"pattern": "TAG = 1", "path": str(tmp / "many.py")})
    check("grep ไฟล์เดียว: ยังทำงาน", "many.py:1:" in g4, g4[:120])
finally:
    S.workspace_root, S.load_config = _orig
    os.environ.pop("SOONAI_NO_SYMBOL_MAP", None)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL SYMBOL TESTS PASSED")
