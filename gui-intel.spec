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
        # HTTP / network
        'requests',
        'urllib3',
        'certifi',
        'charset_normalizer',
        'idna',
        # YouTube transcript
        'youtube_transcript_api',
        'youtube_transcript_api._transcripts',
        'youtube_transcript_api._errors',
        # Tokenizer
        'tiktoken',
        'tiktoken.core',
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
        # yt-dlp
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.postprocessor',
        # PDF
        'fpdf',
        'fpdf2',
        # Env / config
        'dotenv',
        'dotenv.main',
        # OpenAI SDK
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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
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
    target_arch='x86_64',
    codesign_identity=None,
    entitlements_file=None,
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

app = BUNDLE(
    coll,
    name='YouTubeSummarizer.app',
    icon=None,
    bundle_identifier='com.youtubesummarizer.app',
    info_plist={
        'NSHighResolutionCapable': True,
        'LSUIElement': False,
        'CFBundleDisplayName': 'YouTube Summarizer',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSMicrophoneUsageDescription': 'Needed for local audio transcription.',
    },
)
