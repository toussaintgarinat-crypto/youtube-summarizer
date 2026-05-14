# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('prompts', 'prompts'),
        ('.env', '.'),
    ],
    hiddenimports=[
        'requests',
        'urllib3',
        'certifi',
        'charset_normalizer',
        'idna',
        'youtube_transcript_api',
        'youtube_transcript_api._transcripts',
        'youtube_transcript_api._errors',
        'tiktoken',
        'tiktoken.core',
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.postprocessor',
        'fpdf',
        'fpdf2',
        'dotenv',
        'dotenv.main',
        'openai',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YouTubeSummarizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YouTubeSummarizer',
)
