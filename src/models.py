"""Fetch and filter available models from OpenRouter API + OpenCode Go."""

import requests
from typing import Optional
import config

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Fallback list if the API is unreachable
FALLBACK_FREE_MODELS = {
    "meta-llama/llama-3.3-70b-instruct:free": 128000,
    "meta-llama/llama-3.1-8b-instruct:free": 128000,
    "google/gemma-3-12b-it:free": 96000,
    "mistralai/mistral-7b-instruct:free": 32000,
    "deepseek/deepseek-r1:free": 64000,
}

FALLBACK_PAID_MODELS = {
    "meta-llama/llama-3.3-70b-instruct": 128000,
    "anthropic/claude-3.5-sonnet": 200000,
    "google/gemini-2.0-flash-exp": 1000000,
    "openai/gpt-4o-mini": 128000,
    "mistralai/mistral-large": 32000,
}

# Models known to produce poor results (OCR-only, multimodal-only, etc.)
_BLOCKLIST_KEYWORDS = ("ocr", "vision", "image", "audio", "owl-alpha", "cobuddy", "laguna")


def _is_text_model(model: dict) -> bool:
    arch = model.get("architecture", {})
    inputs = arch.get("input_modalities", [])
    outputs = arch.get("output_modalities", [])
    model_id = model.get("id", "").lower()
    if any(kw in model_id for kw in _BLOCKLIST_KEYWORDS):
        return False
    # Must accept text input, produce text output, and NOT produce audio/image
    return (
        "text" in inputs
        and "text" in outputs
        and "audio" not in outputs
        and outputs != ["image"]
    )


def fetch_free_models(timeout: int = 5) -> dict[str, int]:
    """
    Return {model_id: context_length} for all free text→text models on OpenRouter.
    Falls back to FALLBACK_FREE_MODELS if the API is unreachable.
    """
    try:
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("data", [])

        free = {
            m["id"]: int(m.get("context_length") or m.get("top_provider", {}).get("context_length") or 32000)
            for m in models
            if m.get("pricing", {}).get("prompt") == "0"
            and m.get("pricing", {}).get("completion") == "0"
            and _is_text_model(m)
        }

        return free if free else FALLBACK_FREE_MODELS

    except Exception:
        return FALLBACK_FREE_MODELS


def fetch_all_models(timeout: int = 5) -> dict[str, int]:
    """Return {model_id: context_length} for ALL text→text models (free + paid)."""
    try:
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("data", [])

        all_models = {
            m["id"]: int(m.get("context_length") or m.get("top_provider", {}).get("context_length") or 32000)
            for m in models
            if _is_text_model(m)
        }

        return all_models if all_models else {**FALLBACK_FREE_MODELS, **FALLBACK_PAID_MODELS}

    except Exception:
        return {**FALLBACK_FREE_MODELS, **FALLBACK_PAID_MODELS}


def fetch_open_code_go_models(timeout: int = 5) -> dict[str, int]:
    """Return {model_id: context_length} for all OpenCode Go models."""
    try:
        resp = requests.get(f"{config.OPENCODE_GO_BASE_URL}/models", timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        result = {}
        for m in models:
            model_id = m["id"]
            result[model_id] = config.OPENCODE_GO_MODELS.get(model_id, 131072)
        return result if result else config.OPENCODE_GO_MODELS
    except Exception:
        return config.OPENCODE_GO_MODELS
