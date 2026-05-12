"""Utility functions for YouTube Summarizer"""

import re
from typing import Optional, Tuple, List

def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def validate_youtube_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate YouTube URL.
    
    Returns:
        (is_valid, video_id or error_message)
    """
    if not url or not url.strip():
        return False, "URL empty"
    
    video_id = extract_video_id(url.strip())
    if video_id:
        return True, video_id
    return False, "Invalid YouTube URL format"

def parse_markdown_sections(markdown: str) -> dict:
    """Parse markdown into sections."""
    sections = {}
    current_section = None
    current_content = []
    
    for line in markdown.split('\n'):
        if line.startswith('## ') or line.startswith('### '):
            if current_section:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = line.lstrip('#').strip()
            current_content = []
        else:
            current_content.append(line)
    
    if current_section:
        sections[current_section] = '\n'.join(current_content).strip()
    
    return sections

def format_duration(seconds: float) -> str:
    """Format seconds to human readable duration."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"

def clean_text(text: str) -> str:
    """Clean text for processing."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove common artifacts
    text = text.replace('[Music]', '')
    text = text.replace('[Applause]', '')
    text = text.replace('[Laughter]', '')
    return text.strip()

def get_available_models() -> List[str]:
    """Get list of available models from config."""
    return list(config.MODEL_CONTEXTS.keys())

def format_model_choice(model: str) -> str:
    """Format model name for display."""
    model_names = {
        "meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B",
        "meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B",
        "meta-llama/llama-3.1-8b-instruct": "Llama 3.1 8B",
        "mistralai/mistral-large": "Mistral Large",
        "mistralai/mistral-small": "Mistral Small",
        "mistralai/mistral-medium": "Mistral Medium",
        "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet",
        "anthropic/claude-3-opus": "Claude 3 Opus",
        "google/gemini-2.0-flash-exp": "Gemini 2.0 Flash",
        "openai/gpt-4o-mini": "GPT-4o Mini",
    }
    return model_names.get(model, model)