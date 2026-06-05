"""
YouTube Summarizer — Update checker
Checks GitHub releases for newer versions and provides update instructions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

import config


@dataclass
class UpdateInfo:
    available: bool
    latest_version: str
    current_version: str
    release_url: str
    release_notes: str = ""
    error: str = ""


def _parse_version(v: str) -> tuple[int, ...]:
    cleaned = v.lstrip("vV")
    parts = []
    for p in cleaned.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def get_latest_release() -> dict | None:
    url = f"https://api.github.com/repos/{config.REPO_OWNER}/{config.REPO_NAME}/releases/latest"
    try:
        req = Request(url, headers={"User-Agent": "youtube-summarizer/1.0", "Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def check_update() -> UpdateInfo:
    current = config.APP_VERSION
    release = get_latest_release()
    if release is None:
        return UpdateInfo(
            available=False,
            latest_version=current,
            current_version=current,
            release_url="",
            error="Impossible de contacter GitHub.",
        )

    latest_tag = release.get("tag_name", "")
    latest_ver = latest_tag.lstrip("vV") or current
    release_url = release.get("html_url", "")
    body = release.get("body", "")

    available = _parse_version(latest_ver) > _parse_version(current)

    return UpdateInfo(
        available=available,
        latest_version=latest_tag,
        current_version=current,
        release_url=release_url,
        release_notes=body[:2000] if body else "",
    )


def perform_git_pull(callback: Callable[[str], None] | None = None) -> bool:
    """Run git pull in the project directory. Works only for git-based installs."""
    def _log(msg: str):
        if callback:
            callback(msg)

    try:
        repo_dir = Path(__file__).resolve().parent.parent
        _log("Exécution de git pull...")
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            _log(f"Mise à jour terminée : {result.stdout.strip()}")
            return True
        else:
            _log(f"Erreur git pull : {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        _log("Git n'est pas installé ou n'est pas dans le PATH.")
        return False
    except subprocess.TimeoutExpired:
        _log("La commande git pull a expiré.")
        return False
    except Exception as e:
        _log(f"Erreur inattendue : {e}")
        return False


def perform_docker_pull(callback: Callable[[str], None] | None = None) -> bool:
    """Pull the latest Docker image."""
    def _log(msg: str):
        if callback:
            callback(msg)

    try:
        _log("Téléchargement de la dernière image Docker...")
        result = subprocess.run(
            ["docker", "pull", f"ghcr.io/{config.REPO_OWNER}/{config.REPO_NAME}:latest"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            _log("Image Docker mise à jour.")
            _log("Redémarrez le conteneur : docker compose up -d")
            return True
        else:
            _log(f"Erreur : {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        _log("Docker n'est pas installé.")
        return False
    except Exception as e:
        _log(f"Erreur : {e}")
        return False


def detect_install_mode() -> str:
    """Detect how the app was installed."""
    if getattr(sys, 'frozen', False):
        return "desktop"
    if Path("/.dockerenv").exists() or os.environ.get("DOCKER"):
        return "docker"
    if Path(__file__).resolve().parent.parent.joinpath(".git").is_dir():
        return "git"
    return "unknown"
