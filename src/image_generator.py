"""Image Generator - Multi-Provider Support"""

import base64
import os
import re
import time
import requests
from pathlib import Path
from typing import Optional

IMAGE_PROVIDERS = {
    "flux": {
        "name": "Flux",
        "models": ["black-forest-labs/flux.2-klein-4b", "black-forest-labs/flux.2-max", "black-forest-labs/flux.2-pro", "black-forest-labs/flux.2-flex"],
        "default_model": "black-forest-labs/flux.2-klein-4b",
        "icon": "🎨",
        "description": "Rapide et économique (OpenRouter)"
    },
    "recraft": {
        "name": "Recraft",
        "models": ["recraft/recraft-v4.1", "recraft/recraft-v4.1-pro", "recraft/recraft-v4.1-vector", "recraft/recraft-v4.1-pro-vector"],
        "default_model": "recraft/recraft-v4.1",
        "icon": "🎭",
        "description": "Design vectoriel et créatif (OpenRouter)"
    },
    "gemini-image": {
        "name": "Gemini Image",
        "models": ["google/gemini-3.1-flash-image-preview", "google/gemini-2.5-flash-image", "google/gemini-3-pro-image-preview"],
        "default_model": "google/gemini-3.1-flash-image-preview",
        "icon": "💎",
        "description": "Google Gemini (OpenRouter)"
    },
    "openai-image": {
        "name": "OpenAI Image",
        "models": ["openai/gpt-5.4-image-2", "openai/gpt-5-image", "openai/gpt-5-image-mini"],
        "default_model": "openai/gpt-5.4-image-2",
        "icon": "🖼️",
        "description": "GPT-5 Image via OpenAI (OpenRouter)"
    },
    "seedream": {
        "name": "Seedream",
        "models": ["bytedance-seed/seedream-4.5"],
        "default_model": "bytedance-seed/seedream-4.5",
        "icon": "🌱",
        "description": "ByteDance Seed (OpenRouter)"
    },
    "riverflow": {
        "name": "Riverflow",
        "models": ["sourceful/riverflow-v2-pro", "sourceful/riverflow-v2-fast", "sourceful/riverflow-v2-standard-preview"],
        "default_model": "sourceful/riverflow-v2-pro",
        "icon": "🌊",
        "description": "Sourceful Riverflow (OpenRouter)"
    },
    "mai-image": {
        "name": "MAI Image",
        "models": ["microsoft/mai-image-2.5"],
        "default_model": "microsoft/mai-image-2.5",
        "icon": "🔬",
        "description": "Microsoft MAI-Image (OpenRouter)"
    },
    "grok-imagine": {
        "name": "Grok Imagine",
        "models": ["x-ai/grok-imagine-image-quality"],
        "default_model": "x-ai/grok-imagine-image-quality",
        "icon": "🤖",
        "description": "xAI Grok Imagine (OpenRouter)"
    },
    "stability-ai": {
        "name": "Stability AI (direct)",
        "models": ["stable-diffusion-v3-5-large", "stable-diffusion-v3-5-medium", "stable-diffusion-xl-1024-v1-0"],
        "default_model": "stable-diffusion-v3-5-large",
        "icon": "🔮",
        "description": "Via API Stability AI directe",
        "api_key_label": "Clé API Stability AI (sk-...)"
    },
    "replicate": {
        "name": "Replicate (direct)",
        "models": ["black-forest-labs/flux-schnell", "stability-ai/stable-diffusion-3.5-large", "recraft-ai/recraft-v3"],
        "default_model": "black-forest-labs/flux-schnell",
        "icon": "🔄",
        "description": "Via API Replicate directe",
        "api_key_label": "Clé API Replicate (r8_...)"
    },
    "pruna": {
        "name": "Pruna AI (direct)",
        "models": ["p-image"],
        "default_model": "p-image",
        "icon": "⚡",
        "description": "P-Image : ultra-rapide (<1s), $0.005/image",
        "api_key_label": "Clé API Pruna (contacter Pruna)"
    }
}

IMAGE_STYLES = {
    "realistic": {
        "name": "Réaliste",
        "prompt_suffix": "photorealistic, high detail, 4K, natural lighting, professional photography"
    },
    "cartoon": {
        "name": "Dessin Animé",
        "prompt_suffix": "cartoon style, animated, colorful, fun, character illustration"
    },
    "minimalist": {
        "name": "Minimaliste",
        "prompt_suffix": "minimalist, clean design, flat illustration, simple, modern"
    },
    "abstract": {
        "name": "Abstrait",
        "prompt_suffix": "abstract art, geometric shapes, artistic, creative composition"
    },
    "infographic": {
        "name": "Infographie",
        "prompt_suffix": "infographic style, diagram, data visualization, clean layout"
    }
}

def extract_video_title_from_insight(insight_text: str) -> str:
    """Extract a short title from insight text."""
    lines = insight_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and len(line) > 5:
            title = re.sub(r'^\d+[.\)]\s*', '', line)
            title = re.sub(r'\[?\d{1,2}:\d{2}\]?\s*:?\s*', '', title)
            title = title[:60].strip()
            if title:
                return title
    return "Moment fort"

def build_image_prompt(insight_text: str, video_title: str, style: str = "realistic") -> str:
    """
    Build optimized image prompt from insight text.
    
    Args:
        insight_text: The insight description
        video_title: Original video title
        style: Image style preset
    
    Returns:
        Optimized prompt for image generation
    """
    title = extract_video_title_from_insight(insight_text)
    
    insight_clean = re.sub(r'\[?\d{1,2}:\d{2}\]?\s*:?\s*', '', insight_text)
    insight_clean = re.sub(r'[#*_`]', '', insight_clean)
    insight_clean = insight_clean[:200].strip()
    
    style_config = IMAGE_STYLES.get(style, IMAGE_STYLES["realistic"])
    style_suffix = style_config["prompt_suffix"]
    
    prompt = f"'{title}' - {insight_clean}. {style_suffix}. Topic: {video_title}"
    
    prompt = re.sub(r'\s+', ' ', prompt).strip()
    
    if len(prompt) > 400:
        prompt = prompt[:400] + "..."
    
    return prompt

def _call_openrouter(prompt: str, model: str, api_key: str, size: str) -> dict:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://youtube-summarizer.local",
        "X-Title": "YouTube Summarizer",
    }
    payload = {
        "model": model,
        "modalities": ["image"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 5000,
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 429:
                time.sleep((attempt + 1) * 15)
                continue
            if resp.status_code == 402:
                return {"error": "Crédit API épuisé sur OpenRouter."}
            if resp.status_code != 200:
                return {"error": f"OpenRouter {resp.status_code}: {resp.text[:200]}"}
            data = resp.json()
            if data.get("error"):
                return {"error": data["error"]}
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            # OpenRouter returns images in the "images" array
            images = msg.get("images", [])
            for img in images:
                if img.get("type") == "image_url":
                    url = img.get("image_url", {}).get("url", "")
                    if url:
                        return {"url": url, "revised": prompt}
            # Fallback: check content for markdown image syntax
            content = msg.get("content", "")
            if content and ("data:image" in content or "http" in content):
                m = re.search(r'!\[.*?\]\((https?://[^\s)]+)\)', content)
                if m:
                    return {"url": m.group(1), "revised": prompt}
                m2 = re.search(r'(https?://[^\s)]+)', content)
                if m2:
                    return {"url": m2.group(1), "revised": prompt}
                return {"url": content.strip(), "revised": prompt}
            # Also check finish_reason for errors
            if choice.get("finish_reason") == "error":
                return {"error": "Le modèle n'a pas généré d'image"}
            return {"error": "Aucune image dans la réponse"}
        except requests.exceptions.Timeout:
            if attempt < 2:
                time.sleep(5)
                continue
            return {"error": "Timeout OpenRouter"}
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            return {"error": str(e)}
    return {"error": "Échec après tentatives"}


def _call_stability_ai(prompt: str, model: str, api_key: str, size: str) -> dict:
    url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    size_map = {"1024x1024": "1024x1024", "512x512": "512x512", "1024x768": "1024x768", "768x1024": "768x1024"}
    aspect = size_map.get(size, "1024x1024")
    try:
        resp = requests.post(
            url, headers=headers,
            data={"model": model, "prompt": prompt, "aspect_ratio": aspect, "output_format": "png"},
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            image_data = data.get("image", b"")
            if isinstance(image_data, str):
                image_bytes = image_data.encode() if isinstance(image_data, str) else image_data
                import base64 as b64
                b64_bytes = b64.b64encode(image_bytes)
                image_url = f"data:image/png;base64,{b64_bytes.decode()}"
            else:
                image_url = "data:image/png;base64," + base64.b64encode(image_data).decode()
            return {"url": image_url, "revised": prompt}
        if resp.status_code == 402:
            return {"error": "Crédit Stability AI épuisé."}
        return {"error": f"Stability AI {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": f"Stability AI: {str(e)}"}


def _call_replicate(prompt: str, model: str, api_key: str, size: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    model_url = f"https://api.replicate.com/v1/models/{model}/predictions"
    payload = {"input": {"prompt": prompt, "num_outputs": 1, "aspect_ratio": "1:1"}}
    try:
        resp = requests.post(model_url, headers=headers, json=payload, timeout=120)
        if resp.status_code == 201:
            data = resp.json()
            output = data.get("output", [])
            if output and isinstance(output, list) and len(output) > 0:
                return {"url": output[0], "revised": prompt}
            if data.get("status") == "processing":
                get_url = data.get("urls", {}).get("get", "")
                for _ in range(30):
                    time.sleep(2)
                    poll = requests.get(get_url, headers=headers, timeout=30)
                    if poll.status_code != 200:
                        continue
                    poll_data = poll.json()
                    if poll_data.get("status") == "succeeded":
                        out = poll_data.get("output", [])
                        if out and len(out) > 0:
                            return {"url": out[0], "revised": prompt}
                        break
                    if poll_data.get("status") == "failed":
                        return {"error": f"Replicate: {poll_data.get('error', 'échec')}"}
                    time.sleep(2)
            return {"error": f"Réponse Replicate: {str(data)[:200]}"}
        if resp.status_code == 402:
            return {"error": "Crédit Replicate épuisé."}
        return {"error": f"Replicate {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": f"Replicate: {str(e)}"}


def _call_pruna(prompt: str, model: str, api_key: str, size: str) -> dict:
    url = "https://api.pruna.ai/v1/predictions"
    aspect_map = {"1024x1024": "1:1", "512x512": "1:1", "1024x768": "4:3", "768x1024": "3:4", "1920x1080": "16:9", "1080x1920": "9:16"}
    aspect = aspect_map.get(size, "1:1")
    headers = {"apikey": api_key, "Model": model, "Try-Sync": "true", "Content-Type": "application/json"}
    payload = {"input": {"prompt": prompt, "aspect_ratio": aspect}}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            gen_url = data.get("generation_url", "")
            if gen_url:
                img_resp = requests.get(gen_url, headers={"apikey": api_key}, timeout=30)
                if img_resp.status_code == 200:
                    import base64 as b64
                    img_b64 = b64.b64encode(img_resp.content).decode()
                    return {"url": f"data:image/jpeg;base64,{img_b64}", "revised": prompt}
                return {"url": gen_url, "revised": prompt}
            status = data.get("status", "")
            if status == "succeeded" and data.get("generation_url"):
                return {"url": data["generation_url"], "revised": prompt}
            if "error" in data:
                return {"error": data["error"]}
            return {"error": f"Réponse Pruna: {str(data)[:200]}"}
        if resp.status_code == 402:
            return {"error": "Crédit Pruna AI épuisé."}
        return {"error": f"Pruna AI {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": f"Pruna AI: {str(e)}"}


def generate_image(
    prompt: str,
    provider: str = "flux",
    model: str = None,
    size: str = "1024x1024",
    api_key: str = None
) -> dict:
    if api_key is None:
        from src.analyzer import config
        api_key = getattr(config, 'OPENROUTER_API_KEY', None)

    if not api_key:
        return {"success": False, "error": "API key non configurée."}

    provider_config = IMAGE_PROVIDERS.get(provider)
    if not provider_config:
        return {"success": False, "error": f"Provider '{provider}' non supporté."}

    model = model or provider_config["default_model"]

    if provider == "stability-ai":
        result = _call_stability_ai(prompt, model, api_key, size)
    elif provider == "replicate":
        result = _call_replicate(prompt, model, api_key, size)
    elif provider == "pruna":
        result = _call_pruna(prompt, model, api_key, size)
    else:
        result = _call_openrouter(prompt, model, api_key, size)

    if "error" in result:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "image_url": result["url"],
        "revised_prompt": result.get("revised", prompt),
        "provider": provider,
        "model": model,
    }

def download_image(url: str, output_path: str) -> bool:
    """Download image from URL to local path."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        return True
    except Exception as e:
        print(f"Erreur download: {e}")
        return False

def get_providers_list() -> list:
    """Get list of available image providers."""
    return [
        {
            "id": pid,
            "name": pconfig["name"],
            "icon": pconfig["icon"],
            "models": pconfig["models"],
            "description": pconfig["description"],
            "api_key_label": pconfig.get("api_key_label", ""),
        }
        for pid, pconfig in IMAGE_PROVIDERS.items()
    ]

def get_styles_list() -> list:
    """Get list of available image styles."""
    return [
        {"id": sid, "name": sconfig["name"], "prompt_hint": sconfig["prompt_suffix"][:50]}
        for sid, sconfig in IMAGE_STYLES.items()
    ]

CTLT_PROMPT = """Tu es un expert en ingénierie de prompt visuel, spécialisé dans la création et la reformulation de prompts pour les IA d'images.

Objectif : Transformer une idée simple ou un prompt existant en un prompt ultra descriptif, cohérent et prêt à coller.

Méthode CTLT+ :
1. Interpréter l'idée / analyser le prompt fourni pour en extraire le concept visuel.
2. Composer ou reformuler un prompt intégrant :
- C – Camera & Composition : angle, plan, focale, profondeur de champ
- T – Tonality & Style : ambiance, palette de couleurs, références esthétiques
- L – Light : type, direction, intensité, température
- T – Texture & Details : grain, matériaux, surfaces, micro-détails

Format de sortie (strict) :
1. Un bloc de texte unique et continu EN ANGLAIS contenant le prompt seulement.
2. Puis sur une nouvelle ligne : "Artistic Explanation: " suivi de 2-3 phrases en français sur l'intention.
3. Puis sur une nouvelle ligne : "Format: Portrait/Landscape" + brève raison.

Idée ou prompt à transformer : {prompt}"""


def enhance_image_prompt(user_prompt: str, api_key: str, model: str = None) -> dict:
    """Enhance an image prompt using CTLT+ methodology via LLM."""
    from src.analyzer import call_llm
    try:
        full_prompt = CTLT_PROMPT.format(prompt=user_prompt)
        result = call_llm(full_prompt, model=model or "meta-llama/llama-3.3-70b-instruct:free", max_tokens=1000, temperature=0.5, api_key=api_key)
        return {"success": True, "enhanced": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_insights_images(
    insights: list,
    video_title: str,
    provider: str = "flux",
    style: str = "realistic",
    output_dir: str = None,
    api_key: str = None
) -> list:
    """
    Generate images for multiple insights.
    
    Args:
        insights: List of insight texts
        video_title: Video title for context
        provider: Image provider to use
        style: Image style preset
        output_dir: Directory to save images (optional)
        api_key: API key override
    
    Returns:
        List of dicts with image_url, prompt, success status
    """
    results = []
    
    if output_dir is None:
        output_dir = os.path.expanduser("~/Documents/YouTubeSummarizer/images")
    
    for i, insight in enumerate(insights, 1):
        prompt = build_image_prompt(insight, video_title, style)
        
        result = generate_image(prompt, provider=provider, api_key=api_key)
        
        result_item = {
            'insight_number': i,
            'insight_text': insight[:100] + "..." if len(insight) > 100 else insight,
            'prompt': prompt,
            'success': result.get('success', False),
            'image_url': result.get('image_url', ''),
            'revised_prompt': result.get('revised_prompt', ''),
            'provider': provider,
            'model': result.get('model', ''),
            'error': result.get('error', ''),
            'local_path': ''
        }
        
        if result.get('success') and output_dir:
            ext = 'png'
            filename = f"insight_{i}_{int(time.time())}.{ext}"
            local_path = os.path.join(output_dir, filename)
            
            if download_image(result['image_url'], local_path):
                result_item['local_path'] = local_path
        
        results.append(result_item)
        
        if i < len(insights):
            time.sleep(2)
    
    return results