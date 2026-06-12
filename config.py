import os
import sys
from pathlib import Path
from dotenv import load_dotenv

APP_VERSION = "1.0.0"
REPO_OWNER = "toussaintgarinat-crypto"
REPO_NAME = "youtube-summarizer"

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

load_dotenv(BASE_DIR / ".env", override=True)

def _get(key: str, default: str = "") -> str:
    """Read from env, then fall back to Streamlit secrets if available."""
    value = os.getenv(key, "")
    if not value:
        try:
            import streamlit as st
            value = st.secrets.get(key, default)
        except Exception:
            value = default
    return value

OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY")
OPENCODE_GO_API_KEY = _get("OPENCODE_GO_API_KEY")
OPENAI_API_KEY = _get("OPENAI_API_KEY")
YOUTUBE_COOKIES = _get("YOUTUBE_COOKIES")  # Netscape cookies.txt content (optional)
DEFAULT_MODEL = _get("DEFAULT_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
CHUNK_SIZE_TOKENS = int(_get("CHUNK_SIZE_TOKENS", "12000"))
CHUNK_OVERLAP_TOKENS = int(_get("CHUNK_OVERLAP_TOKENS", "1200"))
WHISPER_MODEL = _get("WHISPER_MODEL", "base")
MAX_CHUNK_OUTPUT_TOKENS = int(_get("MAX_CHUNK_OUTPUT_TOKENS", "6000"))
MAX_FUSION_OUTPUT_TOKENS = int(_get("MAX_FUSION_OUTPUT_TOKENS", "32000"))

MODEL_CONTEXTS = {
    # ── Gratuits (suffixe :free) ──────────────────────────────
    "meta-llama/llama-3.1-8b-instruct:free": 128000,
    "meta-llama/llama-3.3-70b-instruct:free": 128000,
    "google/gemma-3-12b-it:free": 96000,
    "mistralai/mistral-7b-instruct:free": 32000,
    "deepseek/deepseek-r1:free": 64000,
    # ── Payants ──────────────────────────────────────────────
    "meta-llama/llama-3.3-70b-instruct": 128000,
    "meta-llama/llama-3.1-70b-instruct": 128000,
    "meta-llama/llama-3.1-8b-instruct": 128000,
    "mistralai/mistral-large": 32000,
    "mistralai/mistral-small": 32000,
    "mistralai/mistral-medium": 32000,
    "anthropic/claude-3.5-sonnet": 200000,
    "anthropic/claude-3-opus": 200000,
    "google/gemini-2.0-flash-exp": 1000000,
    "openai/gpt-4o-mini": 128000,
}

OPENCODE_GO_MODELS = {
    "deepseek-v4-pro": 1048576,
    "deepseek-v4-flash": 1048576,
    "kimi-k2.5": 131072,
    "kimi-k2.6": 131072,
    "glm-5": 131072,
    "glm-5.1": 131072,
    "mimo-v2.5": 131072,
    "mimo-v2.5-pro": 131072,
    "mimo-v2-pro": 131072,
    "mimo-v2-omni": 131072,
    "minimax-m2.5": 131072,
    "minimax-m2.7": 131072,
    "minimax-m3": 131072,
    "qwen3.5-plus": 131072,
    "qwen3.6-plus": 131072,
    "qwen3.7-plus": 131072,
    "qwen3.7-max": 131072,
    "hy3-preview": 131072,
}

OPENCODE_GO_ANTHROPIC_MODELS = {"minimax-m2.5", "minimax-m2.7", "minimax-m3",
                                 "qwen3.5-plus", "qwen3.6-plus", "qwen3.7-plus", "qwen3.7-max"}

OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"

def get_model_context_limit(model: str) -> int:
    if model in OPENCODE_GO_MODELS:
        return OPENCODE_GO_MODELS[model]
    for key, limit in MODEL_CONTEXTS.items():
        if key in model:
            return limit
    return 32000

def prepare_chunk_size(model: str, custom_size: int = None) -> int:
    if custom_size:
        return custom_size
    ctx_limit = get_model_context_limit(model)
    return min(ctx_limit - 4000, CHUNK_SIZE_TOKENS)

def prepare_overlap(model: str) -> int:
    ctx_limit = get_model_context_limit(model)
    return min(ctx_limit // 10, CHUNK_OVERLAP_TOKENS)