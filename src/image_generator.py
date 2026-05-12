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
        "models": ["flux-1-dev", "flux-1-schnell", "flux-1-pro"],
        "default_model": "flux-1-dev",
        "api_url": "https://openrouter.ai/api/v1/images/generations",
        "icon": "🎨",
        "description": "Qualité haute, rapide"
    },
    "dall-e": {
        "name": "DALL-E",
        "models": ["dall-e-3", "dall-e-2"],
        "default_model": "dall-e-3",
        "api_url": "https://openrouter.ai/api/v1/images/generations",
        "icon": "🖼️",
        "description": "Style naturel"
    },
    "stable-diffusion": {
        "name": "Stable Diffusion",
        "models": ["stable-diffusion-xl-base-1.0", "stable-diffusion-3-medium"],
        "default_model": "stable-diffusion-xl-base-1.0",
        "api_url": "https://openrouter.ai/api/v1/images/generations",
        "icon": "🎭",
        "description": "Style artistique"
    },
    "midjourney": {
        "name": "Midjourney",
        "models": ["midjourney"],
        "default_model": "midjourney",
        "api_url": "https://openrouter.ai/api/v1/images/generations",
        "icon": "✨",
        "description": "Artistique premium"
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

def generate_image(
    prompt: str,
    provider: str = "flux",
    model: str = None,
    size: str = "1024x1024",
    api_key: str = None
) -> dict:
    """
    Generate image using specified provider.
    
    Args:
        prompt: Image generation prompt
        provider: Image provider (flux, dall-e, stable-diffusion, midjourney)
        model: Specific model (uses default if not specified)
        size: Image size (1024x1024, 512x512, etc.)
        api_key: OpenRouter API key
    
    Returns:
        dict: {
            'success': bool,
            'image_url': str,
            'revised_prompt': str,
            'provider': str,
            'model': str,
            'error': str
        }
    """
    if api_key is None:
        from src.analyzer import config
        api_key = getattr(config, 'OPENROUTER_API_KEY', None)
    
    if not api_key:
        return {
            'success': False,
            'error': "API key non configurée. Ajoutez OPENROUTER_API_KEY dans .env"
        }
    
    provider_config = IMAGE_PROVIDERS.get(provider)
    if not provider_config:
        return {
            'success': False,
            'error': f"Provider '{provider}' non supporté. Options: {', '.join(IMAGE_PROVIDERS.keys())}"
        }
    
    model = model or provider_config["default_model"]
    
    try:
        url = provider_config["api_url"]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://youtube-summarizer.local",
            "X-Title": "YouTube Summarizer"
        }
        
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size
        }
        
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=120)
                
                if response.status_code == 429:
                    wait_time = (attempt + 1) * 15
                    time.sleep(wait_time)
                    continue
                
                if response.status_code == 402:
                    return {
                        'success': False,
                        'error': "Crédit API épuisé. Ajoutez des credits sur OpenRouter."
                    }
                
                if response.status_code != 200:
                    return {
                        'success': False,
                        'error': f"Erreur API {response.status_code}: {response.text[:200]}"
                    }
                
                data = response.json()
                
                if 'data' in data and len(data['data']) > 0:
                    image_data = data['data'][0]
                    return {
                        'success': True,
                        'image_url': image_data.get('url', ''),
                        'revised_prompt': image_data.get('revised_prompt', prompt),
                        'provider': provider,
                        'model': model
                    }
                else:
                    return {
                        'success': False,
                        'error': f"Réponse API invalide: {str(data)[:200]}"
                    }
                    
            except requests.exceptions.Timeout:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return {'success': False, 'error': "Timeout - génération d'image trop longue"}
            except Exception as e:
                if attempt < 2:
                    time.sleep(3)
                    continue
                return {'success': False, 'error': f"Erreur: {str(e)}"}
        
        return {'success': False, 'error': "Échec après plusieurs tentatives"}
        
    except Exception as e:
        return {'success': False, 'error': f"Erreur connexion: {str(e)}"}

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
            "description": pconfig["description"]
        }
        for pid, pconfig in IMAGE_PROVIDERS.items()
    ]

def get_styles_list() -> list:
    """Get list of available image styles."""
    return [
        {"id": sid, "name": sconfig["name"], "prompt_hint": sconfig["prompt_suffix"][:50]}
        for sid, sconfig in IMAGE_STYLES.items()
    ]

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