"""YouTube Analyzer - Fusion Module"""

import re
import sys
from pathlib import Path
import config


def get_prompts_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "prompts"
    return Path(__file__).parent.parent / "prompts"


def load_fusion_prompt() -> str:
    prompt_path = get_prompts_dir() / "fusion.xml"
    return prompt_path.read_text(encoding="utf-8")


def _safe_format(template: str, **kwargs) -> str:
    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def prepare_fusion_prompt(analyses: list, video_title: str, output_language: str = "Français") -> str:
    prompt_template = load_fusion_prompt()
    analyses_text = "\n\n---\n\n".join(a for a in analyses if a)
    return _safe_format(
        prompt_template,
        video_title=video_title,
        analyses=analyses_text,
        output_language=output_language,
    )


# ─────────────────────────────────────────────────────────
# Chapter & insight extraction from LLM markdown output
# ─────────────────────────────────────────────────────────

def _extract_chapters(analysis: str) -> list[dict]:
    """Extract chapter entries from a ``## 📍 Chapitrage Temporel`` markdown table."""
    chapters = []
    if not analysis:
        return chapters

    # Find the chapter section
    pattern = r'##\s*📍\s*Chapitrage\s*Temporel\s*\n(.*?)(?=\n##\s|\Z)'
    match = re.search(pattern, analysis, re.DOTALL | re.IGNORECASE)
    if not match:
        return chapters

    section = match.group(1)
    # Extract table rows: | [MM:SS] | *Title* | Description |
    row_pattern = r'\|\s*\[?(\d{1,3}:\d{2})\]?\s*\|\s*\*?(.+?)\*?\s*\|\s*(.+?)\s*\|'
    for m in re.finditer(row_pattern, section):
        ts_raw = m.group(1)
        subject = m.group(2).strip().rstrip('*').lstrip('*')
        desc = m.group(3).strip()

        # Exclude separator rows like | :--- | :--- | :--- |
        if subject.startswith(':') and desc.startswith(':'):
            continue

        # Convert timestamp to seconds for sorting
        parts = ts_raw.split(':')
        ts_seconds = int(parts[0]) * 60 + int(parts[1])

        chapters.append({
            'timestamp': ts_raw,
            'ts_seconds': ts_seconds,
            'subject': subject,
            'description': desc,
        })

    return chapters


def _extract_insights(analysis: str) -> list[dict]:
    """Extract insight entries from ``## 💡 Top 3 Moments Forts`` section."""
    insights = []
    if not analysis:
        return insights

    pattern = r'##\s*💡\s*Top\s*\d*\s*Moments\s*Forts.*?\n(.*?)(?=\n##\s|\Z)'
    match = re.search(pattern, analysis, re.DOTALL | re.IGNORECASE)
    if not match:
        return insights

    section = match.group(1)
    # Extract numbered items: 1. *Title* [MM:SS] : Description
    item_pattern = r'\d+\.\s*\*?(.+?)\*?\s*\[?(\d{1,3}:\d{2})\]?\s*:\s*(.+)'
    for m in re.finditer(item_pattern, section):
        title = m.group(1).strip().rstrip('*').lstrip('*')
        ts = m.group(2)
        desc = m.group(3).strip()
        insights.append({
            'title': title,
            'timestamp': ts,
            'description': desc,
        })

    return insights


def _extract_summary_body(analysis: str) -> str:
    """Extract everything after ``## 📝 Résumé Détaillé`` heading."""
    pattern = r'##\s*📝\s*Résumé\s*Détaillé\s*\n(.*)'
    match = re.search(pattern, analysis, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _extract_executive_summary(analysis: str) -> str:
    """Extract the TL;DR block from ``## 🚀 Résumé Exécutif``."""
    pattern = r'##\s*🚀\s*Résumé\s*Exécutif.*?\n>\s*(.*?)(?=\n##\s|\n\*\*|\Z)'
    match = re.search(pattern, analysis, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


# ─────────────────────────────────────────────────────────
# Programmatic merge helpers
# ─────────────────────────────────────────────────────────

def merge_chapter_tables(chapters_lists: list[list[dict]]) -> list[dict]:
    """Merge multiple chapter lists by timestamp, deduplicate."""
    all_chapters = []
    for cl in chapters_lists:
        all_chapters.extend(cl)

    all_chapters.sort(key=lambda x: x.get('ts_seconds', 0))

    seen_ts = set()
    unique = []
    for c in all_chapters:
        ts = c.get('ts_seconds', 0)
        if ts not in seen_ts:
            seen_ts.add(ts)
            unique.append(c)

    return unique


def select_top_insights(insights_lists: list[list[dict]], max_insights: int = 3) -> list[dict]:
    """Select top insights from multiple lists, deduplicate by title."""
    all_insights = []
    seen = set()
    for il in insights_lists:
        for ins in il:
            key = ins.get('title', '').lower()
            if key and key not in seen:
                seen.add(key)
                all_insights.append(ins)

    return all_insights[:max_insights]


def _build_chapter_table(chapters: list[dict]) -> str:
    """Build a markdown chapter table from a list of chapter dicts."""
    if not chapters:
        return ""
    lines = [
        "## 📍 Chapitrage Temporel",
        "| Time | Sujet | Description |",
        "| :--- | :--- | :--- |",
    ]
    for c in chapters:
        ts = c.get('timestamp', '')
        subject = c.get('subject', '')
        desc = c.get('description', '')
        lines.append(f"| {ts} | *{subject}* | {desc} |")
    return "\n".join(lines)


def _build_insights_list(insights: list[dict]) -> str:
    """Build a markdown insights section."""
    if not insights:
        return ""
    lines = ["## 💡 Top 3 Moments Forts (Insights)"]
    for i, ins in enumerate(insights, 1):
        title = ins.get('title', '')
        ts = ins.get('timestamp', '')
        desc = ins.get('description', '')
        lines.append(f"{i}. *{title}* [{ts}] : {desc}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# Simple fusem prompt (LLM only for coherent summary)
# ─────────────────────────────────────────────────────────

_FUSEM_PROMPT = """Tu es un Expert en Synthèse de Contenu.

Voici {count} analyses partielles d'une même vidéo ({video_title}).
Fusionne-les en UN SEUL résumé cohérent et fluide.

Consignes :
- Produis un unique bloc `## 📝 Résumé Détaillé` (pas de chapitrage ni insights — déjà fait).
- Élimine les répétitions.
- Couvre l'intégralité du contenu du début à la fin.
- Langue : {output_language}.
- Ne dépasse pas 2000 mots.

Format requis :
## 📝 Résumé Détaillé
### 🔹 Contexte et Enjeux
...
### 🔹 Points Techniques / Arguments
...

--- ANALYSES ---
{analyses}
"""


# ─────────────────────────────────────────────────────────
# Main fusion function
# ─────────────────────────────────────────────────────────

def fusion_analyses(
    analyses: list,
    video_title: str,
    model: str = None,
    api_key: str = None,
    output_language: str = "Français",
    fallback_models: list = None,
    provider: str = "openrouter",
) -> str:
    """Fusionne plusieurs analyses en un rapport final.

    Chapters and insights are merged programmatically.
    Only the detailed summary is fused via LLM.
    """
    from src.analyzer import call_llm

    if len(analyses) == 1:
        return analyses[0]

    model = model or config.DEFAULT_MODEL

    # ── 1. Extract chapters from each analysis ──────────────
    all_chapter_lists = []
    all_insight_lists = []
    all_summaries = []
    all_execs = []

    for a in analyses:
        if not a:
            continue
        all_chapter_lists.append(_extract_chapters(a))
        all_insight_lists.append(_extract_insights(a))
        body = _extract_summary_body(a)
        if body:
            all_summaries.append(body)
        exec_s = _extract_executive_summary(a)
        if exec_s:
            all_execs.append(exec_s)

    # ── 2. Programmatic merge ────────────────────────────────
    merged_chapters = merge_chapter_tables(all_chapter_lists)
    selected_insights = select_top_insights(all_insight_lists, max_insights=3)

    # ── 3. LLM-based summary fusion ─────────────────────────
    exec_summary = " ".join(all_execs) if all_execs else "Analyse de la vidéo."

    if all_summaries and len(analyses) > 1:
        merged_text = "\n\n---\n\n".join(all_summaries)
        fusem_prompt = _FUSEM_PROMPT.format(
            count=len(analyses),
            video_title=video_title,
            output_language=output_language,
            analyses=merged_text,
        )
        try:
            detailed_summary = call_llm(
                fusem_prompt,
                model=model,
                max_tokens=config.MAX_FUSION_OUTPUT_TOKENS,
                api_key=api_key,
                fallback_models=fallback_models,
                temperature=0.7,
                provider=provider,
            )
        except Exception:
            detailed_summary = merged_text
    else:
        detailed_summary = "\n\n".join(all_summaries) if all_summaries else analyses[0]

    # ── 4. Assemble final report ─────────────────────────────
    lang_line = f"*Langue Source :* {output_language}"

    # Strip duplicate "## 📝 Résumé Détaillé" header if the LLM already generated it
    body = detailed_summary.strip()
    for prefix in ["## 📝 Résumé Détaillé", "## 📝 Résumé Détaille"]:
        if body.startswith(prefix):
            body = body[len(prefix):].strip()

    report_parts = [
        f"# 📺 ANALYSE VIDÉO : {video_title}",
        lang_line + "\n",
        f"## 🚀 Résumé Exécutif (TL;DR)",
        f"> {exec_summary.strip()}\n",
        _build_chapter_table(merged_chapters),
        "",
        _build_insights_list(selected_insights),
        "",
        f"## 📝 Résumé Détaillé",
        body,
    ]

    return "\n\n".join(p for p in report_parts if p)
