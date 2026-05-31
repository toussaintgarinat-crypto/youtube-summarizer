"""YouTube Analyzer - OpenRouter LLM Integration"""

import json
import sys
import time
import requests
from typing import Optional
from pathlib import Path
import config

def get_prompts_dir() -> Path:
    """Get prompts directory (handles frozen mode)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "prompts"
    return Path(__file__).parent.parent / "prompts"

def load_analyzer_prompt() -> str:
    """Load analyzer prompt template."""
    prompt_path = get_prompts_dir() / "analyzer.xml"
    return prompt_path.read_text(encoding="utf-8")

def _safe_format(template: str, **kwargs) -> str:
    """Replace {key} placeholders without tripping on literal braces in transcript content."""
    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def prepare_analyzer_prompt(transcript: str, video_title: str, output_language: str = "Français") -> str:
    """Prepare analyzer prompt with transcript."""
    prompt_template = load_analyzer_prompt()
    return _safe_format(
        prompt_template,
        video_title=video_title,
        transcript=transcript,
        output_language=output_language,
    )

class RateLimitError(Exception):
    """Raised when a model is rate-limited and all retries are exhausted."""
    pass


def _call_single_model(
    prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> str:
    """Try one model, raise RateLimitError if rate-limited after retries."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://youtube-summarizer.local",
        "X-Title": "YouTube Summarizer",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)

            if response.status_code == 401:
                raise ValueError(
                    "Clé API OpenRouter non reconnue (401).\n"
                    "Vérifiez que votre clé commence bien par 'sk-or-v1-'."
                )
            if response.status_code == 403:
                raise ValueError(
                    "Accès refusé (403). Vérifiez votre clé sur openrouter.ai/keys\n"
                    "et choisissez un modèle gratuit (suffixe ':free')."
                )
            if response.status_code == 429:
                try:
                    retry_after = int(response.json()["error"]["metadata"].get("retry_after_seconds", 0))
                except Exception:
                    retry_after = 0
                wait_time = max(retry_after + 2, (attempt + 1) * 10)
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            data = response.json()

            if "error" in data:
                err = data["error"]
                code = err.get("code", 0)
                if code == 429:
                    wait_time = max(
                        int(err.get("metadata", {}).get("retry_after_seconds", 0)) + 2,
                        (attempt + 1) * 10,
                    )
                    time.sleep(wait_time)
                    continue
                raise ValueError(f"Erreur modèle ({code}) : {err.get('message', str(err))}")

            content = data["choices"][0]["message"]["content"]
            if content is None:
                raise ValueError(
                    "Le modèle a retourné une réponse vide. "
                    "Essayez un autre modèle ou réessayez."
                )
            return content

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise ValueError(f"Erreur réseau : {str(e)}")

    raise RateLimitError(model)


def call_llm(
    prompt: str,
    model: str = None,
    max_tokens: int = 6000,
    temperature: float = 0.7,
    api_key: str = None,
    fallback_models: list = None,
) -> str:
    """Call OpenRouter. If model is rate-limited, auto-fallback to next free model."""
    model = model or config.DEFAULT_MODEL
    active_key = api_key or config.OPENROUTER_API_KEY

    if not active_key:
        raise ValueError("Clé OpenRouter manquante. Entrez votre clé dans la barre latérale.")

    models_to_try = [model] + [m for m in (fallback_models or []) if m != model]

    last_err = None
    for m in models_to_try:
        try:
            return _call_single_model(prompt, m, max_tokens, temperature, active_key)
        except RateLimitError:
            last_err = m
            continue  # try next model

    tried = ", ".join(models_to_try)
    raise ValueError(
        f"Tous les modèles sont surchargés ({tried}).\n"
        "Réessayez dans quelques minutes ou ajoutez des crédits sur openrouter.ai."
    )


def analyze_chunk(
    transcript_chunk: str,
    video_title: str,
    model: str = None,
    max_tokens: int = None,
    api_key: str = None,
    output_language: str = "Français",
    fallback_models: list = None,
) -> str:
    if max_tokens is None:
        max_tokens = config.MAX_CHUNK_OUTPUT_TOKENS
    prompt = prepare_analyzer_prompt(transcript_chunk, video_title, output_language)
    return call_llm(prompt, model, max_tokens, api_key=api_key, fallback_models=fallback_models)

def extract_title_from_analysis(analysis: str) -> str:
    """Extract video title from analysis if present."""
    import re
    match = re.search(r'# 📺 ANALYSE VIDÉO : (.+)', analysis)
    if match:
        return match.group(1).strip()
    return "Video"