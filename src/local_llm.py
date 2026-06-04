"""Local LLM — Ollama integration"""

import requests
from typing import Optional


def check_ollama() -> dict:
    """Check if Ollama is running and return available models."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code != 200:
            return {"available": False, "error": f"Ollama {resp.status_code}"}
        models = resp.json().get("models", [])
        return {
            "available": True,
            "models": [m["name"] for m in models],
            "error": None,
        }
    except requests.exceptions.ConnectionError:
        return {"available": False, "error": "Ollama non accessible. Lancez 'ollama serve'"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def call_local_llm(
    prompt: str,
    model: str = "llama3.2",
    max_tokens: int = 6000,
    temperature: float = 0.7,
) -> str:
    """Call Ollama for local LLM inference."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        },
    }
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            timeout=300,
        )
        if resp.status_code != 200:
            raise ValueError(f"Ollama {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return data.get("response", "")
    except requests.exceptions.ConnectionError:
        raise ConnectionError("Ollama non accessible sur localhost:11434")
    except Exception as e:
        raise ValueError(f"Erreur Ollama: {e}")


def analyze_chunk_local(
    text: str,
    title: str,
    model: str,
    output_language: str = "Français",
) -> str:
    """Analyze a transcript chunk using local Ollama."""
    prompt = f"""Tu es un assistant spécialisé dans l'analyse de contenu vidéo.

Analyse cet extrait de la vidéo "{title}" et fournis :
1. Un résumé exécutif (2-3 phrases)
2. Les points clés (liste)
3. Les concepts importants
4. Les moments forts avec timestamps si présents

Réponds en {output_language}.

Extrait :
{text}"""
    return call_local_llm(prompt, model=model)