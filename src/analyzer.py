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

def prepare_analyzer_prompt(transcript: str, video_title: str, output_language: str = "Français") -> str:
    """Prepare analyzer prompt with transcript."""
    prompt_template = load_analyzer_prompt()
    return prompt_template.format(
        video_title=video_title,
        transcript=transcript,
        output_language=output_language,
    )

def call_llm(
    prompt: str,
    model: str = None,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    api_key: str = None,
) -> str:
    """
    Call OpenRouter LLM API.
    
    Args:
        prompt: Complete prompt to send
        model: Model name (default from config)
        max_tokens: Max response tokens
        temperature: Temperature for generation
    
    Returns:
        LLM response text
    """
    model = model or config.DEFAULT_MODEL
    active_key = api_key or config.OPENROUTER_API_KEY

    if not active_key:
        raise ValueError("Clé OpenRouter manquante. Entrez votre clé dans la barre latérale ou configurez OPENROUTER_API_KEY.")

    # OpenRouter API
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {active_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://youtube-summarizer.local",
        "X-Title": "YouTube Summarizer"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=180
            )

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
                # Respect retry_after from OpenRouter metadata if present
                try:
                    retry_after = int(response.json()["error"]["metadata"].get("retry_after_seconds", 0))
                except Exception:
                    retry_after = 0
                wait_time = max(retry_after + 2, (attempt + 1) * 15)
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            data = response.json()

            # OpenRouter sometimes returns HTTP 200 with an error body
            if "error" in data:
                err = data["error"]
                code = err.get("code", 0)
                msg = err.get("message", str(err))
                if code == 429:
                    wait_time = max(
                        int(err.get("metadata", {}).get("retry_after_seconds", 0)) + 2,
                        (attempt + 1) * 15,
                    )
                    time.sleep(wait_time)
                    continue
                raise ValueError(f"Erreur modèle ({code}) : {msg}")

            return data['choices'][0]['message']['content']

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise ValueError(f"Erreur réseau : {str(e)}")

    raise ValueError(
        "Le modèle est temporairement surchargé (rate limit).\n"
        "Essayez un autre modèle gratuit dans la liste ou réessayez dans quelques secondes."
    )

def analyze_chunk(
    transcript_chunk: str,
    video_title: str,
    model: str = None,
    max_tokens: int = 4000,
    api_key: str = None,
    output_language: str = "Français",
) -> str:
    prompt = prepare_analyzer_prompt(transcript_chunk, video_title, output_language)
    return call_llm(prompt, model, max_tokens, api_key=api_key)

def extract_title_from_analysis(analysis: str) -> str:
    """Extract video title from analysis if present."""
    import re
    match = re.search(r'# 📺 ANALYSE VIDÉO : (.+)', analysis)
    if match:
        return match.group(1).strip()
    return "Video"