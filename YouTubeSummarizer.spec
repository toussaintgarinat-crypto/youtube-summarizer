# -*- mode: python ; coding: utf-8 -*-
import os

# Include .env only if it exists (contains API keys)
datas = [('prompts', 'prompts')]
if os.path.isfile('.env'):
    datas.append(('.env', '.'))

hiddenimports = [
    # YouTube transcript
    'youtube_transcript_api',
    'youtube_transcript_api._errors',
    'youtube_transcript_api.formatters',
    # HTTP / config
    'requests',
    'requests.adapters',
    'requests.auth',
    'dotenv',
    # Tokenizer
    'tiktoken',
    'tiktoken.core',
    'tiktoken.model',
    'tiktoken.registry',
    'tiktoken.load',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    # PDF export
    'fpdf',
    'fpdf.enums',
    'fpdf.errors',
    # yt-dlp
    'yt_dlp',
    'yt_dlp.extractor',
    'yt_dlp.downloader',
    'yt_dlp.postprocessor',
    # OpenRouter / models
    'src.models',
    'src.analyzer',
    'src.fusion',
    'src.extractor',
    'src.chunker',
    'src.whisper_transcriber',
    'src.pdf_exporter',
]

a = Analysis(
    ['gui.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclure les gros paquets inutiles en desktop
        'streamlit',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'cv2',
    ],
    noarchive=False,
    optimize=1,
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='YouTubeSummarizer',
)

app = BUNDLE(
    coll,
    name='YouTubeSummarizer.app',
    icon=None,
    bundle_identifier='com.youtubesummarizer.app',
    info_dict={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '2.0.0',
        'CFBundleName': 'YouTube Summarizer',
        'NSHumanReadableCopyright': 'YouTube Summarizer',
    },
)
