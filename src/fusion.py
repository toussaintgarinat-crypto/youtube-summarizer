"""YouTube Analyzer - Fusion Module"""

import sys
from pathlib import Path
import config

def get_prompts_dir() -> Path:
    """Get prompts directory (handles frozen mode)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "prompts"
    return Path(__file__).parent.parent / "prompts"

def load_fusion_prompt() -> str:
    """Load fusion prompt template."""
    prompt_path = get_prompts_dir() / "fusion.xml"
    return prompt_path.read_text(encoding="utf-8")

def prepare_fusion_prompt(analyses: list, video_title: str, output_language: str = "Français") -> str:
    """Prepare fusion prompt with analyses."""
    prompt_template = load_fusion_prompt()

    analyses_text = "\n\n---\n\n".join(analyses)

    return prompt_template.format(
        video_title=video_title,
        analyses=analyses_text,
        output_language=output_language,
    )

def merge_chapter_tables(chapters_list: list) -> list:
    """Merge multiple chapter tables by timestamp order."""
    all_chapters = []
    
    for chapters in chapters_list:
        all_chapters.extend(chapters)
    
    all_chapters.sort(key=lambda x: x.get('timestamp', ''))
    
    seen_timestamps = set()
    unique_chapters = []
    
    for chapter in all_chapters:
        ts = chapter.get('timestamp', '')
        if ts not in seen_timestamps:
            seen_timestamps.add(ts)
            unique_chapters.append(chapter)
    
    return unique_chapters

def select_top_insights(insights_list: list, max_insights: int = 3) -> list:
    """Select top insights from multiple lists."""
    all_insights = []
    
    for insights in insights_list:
        all_insights.extend(insights)
    
    return all_insights[:max_insights]

def fusion_analyses(analyses: list, video_title: str, model: str = None, api_key: str = None, output_language: str = "Français", fallback_models: list = None) -> str:
    """Fusionne plusieurs analyses en un rapport final."""
    from src.analyzer import call_llm

    if len(analyses) == 1:
        return analyses[0]

    model = model or config.DEFAULT_MODEL
    prompt = prepare_fusion_prompt(analyses, video_title, output_language)
    return call_llm(prompt, model, api_key=api_key, fallback_models=fallback_models)