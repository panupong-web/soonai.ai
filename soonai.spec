# -*- coding: utf-8 -*-
# PyInstaller spec สำหรับ SoonAI CLI (PyInstaller >= 6)
# ใช้: pyinstaller soonai.spec  → ได้ dist/soonai.exe (onefile)
#
# หมายเหตุ: ไฟล์ config/keys/team ของผู้ใช้ไม่อยู่ใน bundle — ตอนรันจริง
# runtime.ensure_user_files() จะสร้าง/ย้ายไปที่ DATA_DIR
# (%LOCALAPPDATA%\SoonAI · ~/.soonai) จาก *.default.json ที่แนบมาข้างล่าง

# soonai.py ทำ sys.path.insert(shared/) ตอนรัน ซึ่ง PyInstaller มองไม่เห็น
# จึงต้องบอก pathex เอง แล้วอ้างโมดูลใน shared/ ด้วยชื่อชั้นบนสุด (ไม่ใช่ shared.X)
_SHARED_MODULES = [
    'chat',
    'computer',
    'debug',
    'mcp_client',
    'permissions',
    'project',
    'providers',
    'runtime',
    'shell',
    'skills',
    'symbols',
    'ui_render',
    'ui_theme',
    'usage',
]

# skills.py อ่าน shared/skills/<ชื่อสกิล>/SKILL.md — datas แบบ glob จะแบนโฟลเดอร์
# จึงไล่จับคู่ทีละสกิลเองเพื่อคงโครงโฟลเดอร์ไว้
from pathlib import Path  # noqa: E402

_SKILL_DATAS = [(str(p), str(Path('shared/skills') / p.parent.name))
                for p in Path('shared/skills').glob('*/SKILL.md')]

a = Analysis(
    ['soonai.py'],
    pathex=['shared'],
    binaries=[],
    datas=_SKILL_DATAS + [
        # ข้อมูลที่อ่านตอนรัน (ไม่ใช่โค้ด) — ต้องอยู่ใต้ shared/ ใน bundle
        # เพราะ runtime.SHARED_DIR ชี้ที่นั่น
        ('shared/mcp_catalog.json', 'shared'),
        ('shared/config.default.json', 'shared'),
        ('shared/team.default.json', 'shared'),
    ],
    hiddenimports=_SHARED_MODULES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'pytest',
        'ruff',
        'pyinstaller',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='soonai',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
