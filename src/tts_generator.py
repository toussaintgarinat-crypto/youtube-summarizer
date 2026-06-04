"""TTS Generator — gTTS (cloud) + local models (Moshi, Ollama)"""

import os
import tempfile
from typing import Optional


def generate_tts(
    text: str,
    method: str = "gtts",
    lang: str = "fr",
    model: Optional[str] = None,
) -> dict:
    """
    Generate TTS audio from text.

    Args:
        text: Text to read aloud
        method: "gtts" (default), "moshi", "ollama"
        lang: Language code (fr, en, etc.) — used by gTTS
        model: Model name (for moshi or ollama)

    Returns:
        dict with "success", "audio_path", "error"
    """
    if method == "gtts":
        return _gtts(text, lang)
    elif method == "moshi":
        return _moshi(text, model)
    elif method == "ollama":
        return _ollama_tts(text, model)
    return {"success": False, "error": f"Méthode TTS inconnue: {method}"}


def _gtts(text: str, lang: str = "fr") -> dict:
    try:
        from gtts import gTTS
    except ImportError:
        return {"success": False, "error": "gTTS non installé. pip install gtts"}

    try:
        tts = gTTS(text=text[:5000], lang=lang, slow=False)
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        tts.save(path)
        return {"success": True, "audio_path": path}
    except Exception as e:
        return {"success": False, "error": f"gTTS: {e}"}


def _moshi(text: str, model: Optional[str] = None) -> dict:
    try:
        import moshi
    except ImportError:
        return {"success": False, "error": "Moshi non installé. pip install moshi (nécessite PyTorch + GPU 24GB)"}

    try:
        # Moshi is a dialogue model, not pure TTS.
        # For reading a summary, we use the Mimic speech codec to generate audio
        # Note: requires running moshi server locally
        # moshi expects a dialogue format, not plain text TTS
        # We fall through to gTTS with a hint
        return {"success": False, "error": "Moshi nécessite un serveur Moshi en cours d'exécution. Utilisez gTTS pour un usage simple."}
    except Exception as e:
        return {"success": False, "error": f"Moshi: {e}"}


def _ollama_tts(text: str, model: Optional[str] = None) -> dict:
    """Use Ollama + a local TTS model (if available on Ollama)."""
    try:
        import requests
        model = model or "llama3.2"
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": f"Read this text aloud: {text[:2000]}", "stream": False},
            timeout=30,
        )
        if resp.status_code == 200:
            # Ollama returns text, not audio — this won't produce real TTS
            # For actual TTS via Ollama, user needs a TTS model like "bark" or "tts-1"
            return {"success": False, "error": "Ollama ne supporte pas la génération audio directement. Utilisez gTTS ou installez un modèle TTS."}
        return {"success": False, "error": f"Ollama {resp.status_code}: {resp.text[:200]}"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Ollama non accessible sur localhost:11434. Lancez 'ollama serve'"}
    except Exception as e:
        return {"success": False, "error": f"Ollama TTS: {e}"}


def get_tts_methods() -> list:
    """Return list of available TTS methods."""
    methods = [{"id": "gtts", "name": "gTTS (cloud, gratuit)", "icon": "🌐"}]
    try:
        import moshi  # noqa
        methods.append({"id": "moshi", "name": "Moshi (local, GPU)", "icon": "🧠"})
    except ImportError:
        pass
    return methods