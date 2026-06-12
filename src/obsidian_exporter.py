"""Obsidian Exporter — save analysis results directly to an Obsidian vault."""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def _safe_filename(title: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    safe = re.sub(r'\s+', ' ', safe).strip()
    if not safe:
        safe = "untitled"
    return safe


def export_to_obsidian(
    content: str,
    title: str,
    vault_path: str,
    source_url: str = "",
    tags: list = None,
    subfolder: str = "YouTube",
) -> dict:
    """
    Save analysis result as a markdown file in an Obsidian vault.

    Args:
        content: The analysis markdown content
        title: Video/topic title
        vault_path: Absolute path to the Obsidian vault root
        source_url: Original video URL (for metadata)
        tags: List of tags (e.g. ["youtube", "summary"])
        subfolder: Subfolder inside the vault (default "YouTube")

    Returns:
        dict with "success", "file_path", "error"
    """
    vault = Path(vault_path).expanduser().resolve()
    if not vault.is_dir():
        return {"success": False, "error": f"Le dossier du vault n'existe pas : {vault}"}

    target_dir = vault / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_title = _safe_filename(title)
    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"{timestamp} - {safe_title}.md"
    filepath = target_dir / filename

    tags_list = tags or ["youtube-summary"]
    if source_url:
        tags_list.append("video")

    frontmatter = f"""---
date: {timestamp}
tags: [{', '.join(tags_list)}]
source: {source_url}
title: "{title}"
---

"""

    full_content = frontmatter + content

    try:
        filepath.write_text(full_content, encoding="utf-8")
        return {"success": True, "file_path": str(filepath)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_vaults() -> list[dict]:
    """Auto-detect Obsidian vaults on the system."""
    vaults = []
    home = Path.home()

    candidates = [
        home / "Documents" / "Obsidian",
        home / "Documents" / "obsidian",
        home / "Obsidian",
        home / "obsidian",
        home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
    ]

    for base in candidates:
        if base.is_dir():
            for entry in base.iterdir():
                if entry.is_dir() and (entry / ".obsidian").is_dir():
                    vaults.append({"name": entry.name, "path": str(entry)})

    return vaults
