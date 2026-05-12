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

def prepare_analyzer_prompt(transcript: str, video_title: str) -> str:
    """Prepare analyzer prompt with transcript."""
    prompt_template = load_analyzer_prompt()
    return prompt_template.format(
        video_title=video_title,
        transcript=transcript
    )

def call_llm(
    prompt: str,
    model: str = None,
    max_tokens: int = 4000,
    temperature: float = 0.7
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
    
    if not config.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY non configurée dans .env")
    
    # OpenRouter API
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
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
    
    # Retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=180
            )
            
            if response.status_code == 429:
                # Rate limit - wait and retry
                wait_time = (attempt + 1) * 10
                time.sleep(wait_time)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            return data['choices'][0]['message']['content']
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise ValueError(f"Erreur API: {str(e)}")
    
    raise ValueError("Échec après plusieurs tentatives")

def analyze_chunk(
    transcript_chunk: str,
    video_title: str,
    model: str = None,
    max_tokens: int = 4000
) -> str:
    """
    Analyse un chunk de transcript.
    
    Args:
        transcript_chunk: Transcript text for this chunk
        video_title: Video title
        model: LLM model to use
        max_tokens: Max tokens for response
    
    Returns:
        Markdown analysis
    """
    prompt = prepare_analyzer_prompt(transcript_chunk, video_title)
    return call_llm(prompt, model, max_tokens)

def extract_title_from_analysis(analysis: str) -> str:
    """Extract video title from analysis if present."""
    import re
    match = re.search(r'# 📺 ANALYSE VIDÉO : (.+)', analysis)
    if match:
        return match.group(1).strip()
    return "Video"