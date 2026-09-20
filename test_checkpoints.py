# -*- coding: utf-8 -*-
"""Regression: checkpoint + undo (ให้ agent แก้ไฟล์แล้วย้อนได้)
- สำเนาไฟล์ก่อน write_file/edit_file (ผ่าน run_tool จริง)
- /undo คืนเนื้อหาเดิม · ไฟล์ที่ไม่เคยมีอยู่ = ลบ
- ไม่เก็บไฟล์ต้องห้าม (keys ฯลฯ) และไม่เก็บไฟล์นอกโฟลเดอร์งาน
- index ถูกตัดเมื่อย้อนแล้ว + ยังไม่มี checkpoint = ข้อความบอก
ทำงานใน temp dir ทั้งหมด ไม่แตะของจริง
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


tmp = tempfile.mkdtemp(prefix="soonai-cp-")
_orig = (S.workspace_root, S.load_config, S.CHECKPOINT_DIR, dict(S._CP))
S.workspace_root = lambda: Path(tmp).resolve()
S.load_config = lambda: {"agent": {"checkpoints": True}}
S.CHECKPOINT_DIR = Path(tmp) / ".cp"
S._CP["bucket"] = None

try:
    # 1) ยังไม่มี checkpoint
    check("undo ไม่มีอะไรให้ย้อน", "ยังไม่มี checkpoint" in S.undo_last())
    check("records ว่างตอนแรก", S.checkpoint_records() == [])

    # 2) เขียนไฟล์ใหม่ผ่าน run_tool → checkpoint บันทึกว่าเดิมไม่มีไฟล์
    f1 = os.path.join(tmp, "note.txt")
    check("run_tool write ครั้งแรก", S.run_tool("write_file", {"path": f1, "content": "v1"}).startswith("OK"))
    recs = S.checkpoint_records()
    check("มี record หลังเขียน", len(recs) == 1, recs)
    check("record บอกว่าเดิมไม่มีไฟล์", recs and recs[0]["had"] is False, recs)
    check("record เก็บ path จริง", recs and Path(recs[0]["path"]) == Path(f1).resolve(), recs)

    # 3) เขียนทับ → checkpoint สำเนาเนื้อหาเดิมไว้
    check("run_tool write ทับ", S.run_tool("write_file", {"path": f1, "content": "v2"}).startswith("OK"))
    recs = S.checkpoint_records()
    check("record เพิ่มเป็น 2", len(recs) == 2, recs)
    check("record ที่สองเก็บสำเนา v1",
          Path(recs[1]["blob"]).read_text(encoding="utf-8") == "v1", recs[1])
    check("ไฟล์ตอนนี้เป็น v2", Path(f1).read_text(encoding="utf-8") == "v2")

    # 4) undo หนึ่งครั้ง → กลับเป็น v1
    msg = S.undo_last(1)
    check("undo คืนค่า v1", Path(f1).read_text(encoding="utf-8") == "v1", msg)
    check("undo รายงานชื่อไฟล์", "note.txt" in msg, msg)
    check("index ถูกตัดเหลือ 1", len(S.checkpoint_records()) == 1, S.checkpoint_records())

    # 5) undo ต่อ → ไฟล์ที่เดิมไม่มี = ถูกลบ
    msg2 = S.undo_last(1)
    check("undo ลบไฟล์ที่เดิมไม่มี", not Path(f1).exists(), msg2)
    check("records ว่างหลังย้อนครบ", S.checkpoint_records() == [], S.checkpoint_records())

    # 6) edit_file ก็ checkpoint
    f2 = os.path.join(tmp, "code.py")
    Path(f2).write_text("a = 1\nb = 2\n", encoding="utf-8")
    out = S.run_tool("edit_file", {"path": f2, "old_string": "a = 1", "new_string": "a = 99"})
    check("edit_file สำเร็จ", out.startswith("OK"), out)
    check("checkpoint ของ edit_file", any(r["tool"] == "edit_file" for r in S.checkpoint_records()))
    S.undo_last(1)
    check("undo คืนค่าไฟล์ที่แก้ด้วย edit_file", "a = 1" in Path(f2).read_text(encoding="utf-8"),
          Path(f2).read_text(encoding="utf-8"))

    # 7) diff ระหว่าง checkpoint กับตอนนี้
    S.run_tool("edit_file", {"path": f2, "old_string": "b = 2", "new_string": "b = 777"})
    d = S.checkpoint_diff()
    check("diff เห็นบรรทัดที่เปลี่ยน", "b = 777" in d and "-b = 2" in d, d[:200])

    # 8) ไม่เก็บไฟล์ต้องห้าม / นอกโฟลเดอร์งาน
    check("ไม่ checkpoint ไฟล์ keys", S.checkpoint_file(S.KEYS_FILE) is None)
    outside = Path(tempfile.mkdtemp(prefix="soonai-out-")) / "x.txt"
    outside.write_text("nope", encoding="utf-8")
    check("ไม่ checkpoint ไฟล์นอกโฟลเดอร์งาน", S.checkpoint_file(outside) is None)

    # 9) ปิดได้ด้วย config
    S.load_config = lambda: {"agent": {"checkpoints": False}}
    f3 = os.path.join(tmp, "off.txt")
    S.run_tool("write_file", {"path": f3, "content": "x"})
    check("ปิด checkpoint ด้วย config ได้",
          not any(Path(r["path"]).name == "off.txt" for r in S.checkpoint_records()),
          S.checkpoint_records())

    # 10) ไฟล์ใหญ่เกินเพดานถูกข้าม
    S.load_config = lambda: {"agent": {"checkpoints": True}}
    big = Path(tmp) / "big.bin"
    big.write_text("x" * (S.CHECKPOINT_MAX_BYTES + 10), encoding="utf-8")
    check("ข้ามไฟล์ใหญ่เกินเพดาน", S.checkpoint_file(big) is None)

    # 11) undo ที่ล้มเหลวต้องค้าง record ไว้กู้ซ้ำได้
    S._CP["bucket"] = None
    f4 = os.path.join(tmp, "fragile.txt")
    S.run_tool("write_file", {"path": f4, "content": "v1"})
    S.run_tool("write_file", {"path": f4, "content": "v2"})
    recs4 = S.checkpoint_records()
    check("มี 2 records", len(recs4) == 2, recs4)
    Path(recs4[1]["blob"]).unlink()  # ทำลายสำเนา → undo ต้องล้มเหลว
    msgf = S.undo_last(1)
    check("undo ล้มเหลวรายงานชัด", "ย้อนไม่ได้" in msgf, msgf)
    check("record ที่ย้อนไม่ได้ยังค้างอยู่", len(S.checkpoint_records()) == 2,
          S.checkpoint_records())
finally:
    S.workspace_root, S.load_config, S.CHECKPOINT_DIR = _orig[0], _orig[1], _orig[2]
    S._CP.clear()
    S._CP.update(_orig[3])

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("ALL CHECKPOINT TESTS PASSED")
