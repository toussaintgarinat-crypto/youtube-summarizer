"""Video Generator - Multi-Provider Support"""

import json
import os
import re
import time

import requests

VIDEO_PROVIDERS = {
    "replicate-video": {
        "name": "Replicate Video",
        "models": ["stability-ai/stable-video-diffusion",
                    "lucataco/stable-video-diffusion",
                    "cjwbw/stable-video-diffusion2"],
        "default_model": "stability-ai/stable-video-diffusion",
        "icon": "🎬",
        "description": "Stable Video Diffusion via Replicate",
        "api_key_label": "Clé API Replicate (r8_...)"
    },
    "luma": {
        "name": "Luma Dream Machine",
        "models": ["luma-ai/dream-machine"],
        "default_model": "luma-ai/dream-machine",
        "icon": "🌟",
        "description": "Dream Machine via Replicate",
        "api_key_label": "Clé API Replicate (r8_...)"
    },
    "minimax": {
        "name": "MiniMax Video",
        "models": ["minimax/video-01"],
        "default_model": "minimax/video-01",
        "icon": "🎥",
        "description": "MiniMax Video Generation via Replicate",
        "api_key_label": "Clé API Replicate (r8_...)"
    },
}


def build_video_prompt(insight_text: str, video_title: str) -> str:
    title = re.sub(r'[#*_`]', '', video_title)[:80]
    clean = re.sub(r'\[?\d{1,2}:\d{2}\]?\s*:?\s*', '', insight_text)
    clean = re.sub(r'[#*_`]', '', clean)[:300].strip()
    prompt = f"{clean}. Cinematic video, smooth motion, high quality, 4K, professional lighting."
    if len(prompt) > 400:
        prompt = prompt[:400]
    return prompt


def _call_replicate_video(prompt: str, model: str, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    model_url = f"https://api.replicate.com/v1/models/{model}/predictions"
    payload = {"input": {"prompt": prompt, "num_frames": 25, "fps": 8}}
    try:
        resp = requests.post(model_url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 201:
            data = resp.json()
            output = data.get("output", "")
            if output:
                if isinstance(output, str):
                    return {"url": output}
                if isinstance(output, list) and len(output) > 0:
                    return {"url": output[0]}
            if data.get("status") == "processing":
                get_url = data.get("urls", {}).get("get", "")
                for _ in range(60):
                    time.sleep(3)
                    poll = requests.get(get_url, headers=headers, timeout=30)
                    if poll.status_code != 200:
                        continue
                    poll_data = poll.json()
                    if poll_data.get("status") == "succeeded":
                        out = poll_data.get("output", "")
                        if isinstance(out, str) and out:
                            return {"url": out}
                        if isinstance(out, list) and len(out) > 0:
                            return {"url": out[0]}
                        break
                    if poll_data.get("status") == "failed":
                        return {"error": f"Replicate: {poll_data.get('error', 'échec')}"}
            if data.get("status") == "succeeded":
                out = data.get("output", "")
                if isinstance(out, str) and out:
                    return {"url": out}
                if isinstance(out, list) and len(out) > 0:
                    return {"url": out[0]}
            return {"error": f"Réponse Replicate: {str(data)[:200]}"}
        if resp.status_code == 402:
            return {"error": "Crédit Replicate épuisé."}
        return {"error": f"Replicate {resp.status_code}: {resp.text[:200]}"}
    except requests.exceptions.Timeout:
        return {"error": "Timeout Replicate (la génération vidéo est lente)"}
    except Exception as e:
        return {"error": f"Replicate: {str(e)}"}


def generate_video(
    prompt: str,
    provider: str = "replicate-video",
    model: str = None,
    api_key: str = None,
) -> dict:
    if api_key is None:
        api_key = os.getenv("REPLICATE_API_KEY", "")

    if not api_key:
        return {"success": False, "error": "Clé API Replicate non configurée."}

    provider_config = VIDEO_PROVIDERS.get(provider)
    if not provider_config:
        return {"success": False, "error": f"Provider '{provider}' non supporté."}

    model = model or provider_config["default_model"]

    result = _call_replicate_video(prompt, model, api_key)

    if "error" in result:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "video_url": result["url"],
        "provider": provider,
        "model": model,
    }


def get_video_providers_list() -> list:
    return [
        {
            "id": pid,
            "name": pconfig["name"],
            "icon": pconfig["icon"],
            "models": pconfig["models"],
            "description": pconfig["description"],
            "api_key_label": pconfig.get("api_key_label", ""),
        }
        for pid, pconfig in VIDEO_PROVIDERS.items()
    ]
