# -*- coding: utf-8 -*-
# PyInstaller spec สำหรับ SoonAI CLI
# ใช้: pyinstaller soonai.spec  → ได้ dist/soonai.exe

# === ตั้งชื่อและ version ===
block_cipher = None

a = Analysis(
    ['soonai.py'],
    pathex=[],
    binaries=[],
    datas=[
        # รวม shared/ modules ทั้งหมด
        ('shared/*.py', 'shared'),
        ('shared/core_utils/*.py', 'shared/core_utils'),
        ('shared/core_utils/__init__.py', 'shared/core_utils'),
        ('shared/skills.off/*.md', 'shared/skills.off'),
        ('shared/skills/*.md', 'shared/skills'),
        # config files
        ('shared/config.json', 'shared'),
        ('shared/team.json', 'shared'),
        ('shared/mcp.example.json', 'shared'),
        ('shared/keys.example.json', 'shared'),
    ],
    hiddenimports=[
        'shared.core_utils.model_router',
        'shared.core_utils',
        'shared.skills',
        'shared.providers',
        'shared.runtime',
        'shared.chat',
        'shared.computer',
        'shared.debug',
        'shared.permissions',
        'shared.project',
        'shared.shell',
        'shared.symbols',
        'shared.ui_theme',
        'shared.ui_render',
        'shared.usage',
        'shared.mcp_client',
        'debug',
        'project',
        'shell',
        'symbols',
        'skills',
        'usage',
        'model_selector',
    ],
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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
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

# Collect all data files
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='soonai',
)
