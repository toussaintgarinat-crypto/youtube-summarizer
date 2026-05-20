"""Multi-Platform Transcript Extractor"""

import re
import time
import requests
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
)

PLATFORMS = {
    'youtube': {
        'domains': ['youtube.com', 'youtu.be', 'youtube-nocookie.com'],
        'icon': '📺',
    },
    'twitch': {
        'domains': ['twitch.tv', 'clips.twitch.tv'],
        'icon': '🟣',
    },
    'vimeo': {
        'domains': ['vimeo.com'],
        'icon': '🎬',
    },
}

def detect_platform(url: str) -> str:
    """Detect video platform from URL."""
    url_lower = url.lower()
    for platform, info in PLATFORMS.items():
        for domain in info['domains']:
            if domain in url_lower:
                return platform
    return 'unknown'

def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_twitch_id(url: str) -> Optional[tuple]:
    """Extract Twitch video/clip ID and type."""
    clip_match = re.search(r'twitch\.tv/\w+/clip/([a-zA-Z0-9_-]+)', url)
    if clip_match:
        return clip_match.group(1), 'clip'
    
    video_match = re.search(r'twitch\.tv/videos/(\d+)', url)
    if video_match:
        return video_match.group(1), 'video'
    
    channel_match = re.search(r'twitch\.tv/([a-zA-Z0-9_]{4,25})/?$', url)
    if channel_match:
        return channel_match.group(1), 'channel'
    
    return None, None

def extract_vimeo_id(url: str) -> Optional[str]:
    """Extract Vimeo video ID."""
    patterns = [
        r'vimeo\.com/(\d+)',
        r'player\.vimeo\.com/video/(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_video_title(video_id: str) -> str:
    """Get video title from YouTube oembed API."""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('title', f"Video {video_id}")
    except:
        pass
    return f"Video {video_id}"

def get_youtube_transcript(url: str, languages: list = None) -> dict:
    """Get transcript from YouTube video."""
    if languages is None:
        languages = ['fr', 'en', 'es', 'de', 'it', 'pt']

    if re.search(r'youtube\.com/(channel|c|user|@)', url):
        raise ValueError(
            "Cette URL est une chaîne YouTube, pas une vidéo.\n"
            "Colle l'URL d'une vidéo spécifique (ex: youtube.com/watch?v=...)"
        )

    if re.search(r'youtube\.com/(playlist|feed)', url):
        raise ValueError(
            "Cette URL est une playlist YouTube, pas une vidéo.\n"
            "Colle l'URL d'une vidéo spécifique (ex: youtube.com/watch?v=...)"
        )

    video_id = extract_youtube_id(url)
    if not video_id:
        raise ValueError("URL YouTube invalide. Format attendu : youtube.com/watch?v=VIDEOID ou youtu.be/VIDEOID")
    
    yt_api = YouTubeTranscriptApi()
    
    try:
        transcript_data = None
        original_lang = None
        
        for lang in languages:
            try:
                transcript = yt_api.fetch(video_id, languages=[lang])
                transcript_data = list(transcript)
                original_lang = lang
                break
            except:
                continue
        
        if not transcript_data:
            transcript = yt_api.fetch(video_id)
            transcript_data = list(transcript)
            try:
                original_lang = transcript.language_code
            except:
                original_lang = 'en'
        
        if not transcript_data:
            transcript = yt_api.fetch(video_id, languages=['fr', 'en'], preserve_ordering=True, offset=0)
            transcript_data = list(transcript)
            original_lang = 'en'
        
        video_title = get_video_title(video_id)
        
        formatted_transcript = []
        for entry in transcript_data:
            formatted_transcript.append({
                'text': entry.text,
                'start': entry.start,
                'duration': entry.duration,
            })
        
        last_entry = formatted_transcript[-1]
        total_duration = last_entry['start'] + last_entry['duration']
        total_minutes = total_duration / 60
        
        return {
            'video_id': video_id,
            'transcript': formatted_transcript,
            'language': original_lang or 'unknown',
            'title': video_title,
            'total_duration_minutes': total_minutes,
            'entries_count': len(formatted_transcript)
        }
        
    except TranscriptsDisabled:
        raise ValueError("Transcript désactivé sur cette vidéo YouTube")
    except NoTranscriptFound:
        raise ValueError("Aucun transcript disponible pour cette vidéo YouTube")
    except CouldNotRetrieveTranscript as e:
        if "403" in str(e):
            try:
                time.sleep(3)
                transcript = yt_api.fetch(video_id, languages=languages)
                transcript_data = list(transcript)
                formatted_transcript = []
                for entry in transcript_data:
                    formatted_transcript.append({
                        'text': entry.text,
                        'start': entry.start,
                        'duration': entry.duration,
                    })
                return {
                    'video_id': video_id,
                    'transcript': formatted_transcript,
                    'language': 'unknown',
                    'title': get_video_title(video_id)
                }
            except:
                pass
        raise ValueError(f"Erreur YouTube 403: vidéo peut-être restreinte. Détail: {str(e)}")
    except Exception as e:
        raise ValueError(f"Erreur lors de la récupération du transcript: {str(e)}")

def get_twitch_transcript(url: str, client_id: str = None) -> dict:
    """Get caption/subtitle from Twitch VOD."""
    if client_id is None:
        client_id = "kimne78kx3ncx6brgo4mv6wki5h1ko"
    
    twitch_id, video_type = extract_twitch_id(url)
    if not twitch_id:
        raise ValueError("URL Twitch invalide")
    
    if video_type == 'channel':
        raise ValueError("Utilisez un lien de VOD ou Clip Twitch, pas un lien de chaîne")
    
    try:
        headers = {
            "Client-ID": client_id,
            "Accept": "application/json"
        }
        
        if video_type == 'video':
            video_url = f"https://api.twitch.tv/helix/videos?id={twitch_id}"
            video_response = requests.get(video_url, headers=headers)
            
            if video_response.status_code != 200:
                raise ValueError("VOD Twitch non accessible ou supprimé")
            
            video_data = video_response.json().get('data', [{}])[0]
            video_title = video_data.get('title', f"Twitch VOD {twitch_id}")
            duration = video_data.get('duration', '0h0m0s')
            
            duration_match = re.search(r'(\d+)h(\d+)m(\d+)s', duration)
            if duration_match:
                total_seconds = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + int(duration_match.group(3))
            else:
                total_seconds = 0
            
            minutes = total_seconds / 60
        else:
            clips_url = f"https://api.twitch.tv/helix/clips?id={twitch_id}"
            clips_response = requests.get(clips_url, headers=headers)
            
            if clips_response.status_code != 200:
                raise ValueError("Clip Twitch non accessible")
            
            clips_data = clips_response.json().get('data', [{}])[0]
            video_title = clips_data.get('title', f"Twitch Clip {twitch_id}")
            minutes = 0
        
        captions_url = f"https://api.twitch.tv/helix/videos/{twitch_id}/subtitles"
        captions_response = requests.get(captions_url, headers=headers)
        
        transcript = []
        
        if captions_response.status_code == 200:
            subtitles = captions_response.json().get('data', [])
            
            if not subtitles:
                return {
                    'video_id': twitch_id,
                    'transcript': [],
                    'language': 'unknown',
                    'title': video_title,
                    'total_duration_minutes': minutes,
                    'entries_count': 0,
                    'platform': 'twitch',
                    'warning': 'Aucun caption disponible sur ce VOD Twitch'
                }
            
            for sub in subtitles:
                sub_url = sub.get('url')
                lang = sub.get('language', 'unknown')
                
                if sub_url:
                    try:
                        vtt_response = requests.get(sub_url, timeout=30)
                        if vtt_response.status_code == 200:
                            lines = vtt_response.text.split('\n')
                            current_start = 0
                            current_text = []
                            
                            for line in lines:
                                line = line.strip()
                                if '-->' in line:
                                    time_match = re.search(r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})', line)
                                    if time_match:
                                        h, m, s, ms = map(int, time_match.groups())
                                        current_start = h * 3600 + m * 60 + s + ms / 1000
                                elif line and not line.startswith('<'):
                                    current_text.append(line)
                                elif line == '' and current_text:
                                    transcript.append({
                                        'text': ' '.join(current_text),
                                        'start': current_start,
                                        'duration': 3.0,
                                    })
                                    current_text = []
                    except:
                        continue
            
            if transcript:
                last_entry = transcript[-1]
                total_duration = last_entry['start'] + last_entry['duration']
                minutes = total_duration / 60
                
                return {
                    'video_id': twitch_id,
                    'transcript': transcript,
                    'language': 'en',
                    'title': video_title,
                    'total_duration_minutes': minutes,
                    'entries_count': len(transcript),
                    'platform': 'twitch'
                }
        
        return {
            'video_id': twitch_id,
            'transcript': [],
            'language': 'unknown',
            'title': video_title,
            'total_duration_minutes': minutes,
            'entries_count': 0,
            'platform': 'twitch',
            'warning': 'Aucun caption disponible sur ce VOD. Seuls les VODs avec sous-titres automatiques sont supportés.'
        }
        
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Erreur Twitch: {str(e)}")

def get_vimeo_transcript(url: str) -> dict:
    """Get caption from Vimeo video."""
    vimeo_id = extract_vimeo_id(url)
    if not vimeo_id:
        raise ValueError("ID Vimeo invalide")
    
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(f"https://vimeo.com/{vimeo_id}", headers=headers, timeout=15)
        
        if response.status_code != 200:
            raise ValueError("Vidéo Vimeo non accessible")
        
        html = response.text
        
        title_match = re.search(r'<title>([^<]+)</title>', html)
        video_title = title_match.group(1) if title_match else f"Vimeo {vimeo_id}"
        
        caption_pattern = r'"captions":\[(.*?)\]'
        caption_match = re.search(caption_pattern, html)
        
        transcript = []
        
        if caption_match:
            import json
            captions_data = caption_match.group(1)
            try:
                captions = json.loads(f'[{captions_data}]')
                
                for caption in captions:
                    caption_url = caption.get('caption_file', {}).get('url')
                    lang = caption.get('language', 'unknown')
                    
                    if caption_url:
                        try:
                            vtt_resp = requests.get(caption_url, timeout=30)
                            if vtt_resp.status_code == 200:
                                lines = vtt_resp.text.split('\n')
                                current_start = 0
                                current_text = []
                                
                                for line in lines:
                                    line = line.strip()
                                    if '-->' in line:
                                        parts = re.split(r'[:\.]', line.replace('-->', '').strip())
                                        if len(parts) >= 3:
                                            h = int(parts[0])
                                            m = int(parts[1])
                                            s = int(parts[2].split('.')[0])
                                            ms = int(parts[2].split('.')[1]) if '.' in parts[2] else 0
                                            current_start = h * 3600 + m * 60 + s + ms / 1000
                                    elif line and not line.startswith('<'):
                                        current_text.append(line)
                                    elif line == '' and current_text:
                                        transcript.append({
                                            'text': ' '.join(current_text),
                                            'start': current_start,
                                            'duration': 3.0,
                                        })
                                        current_text = []
                        except:
                            continue
            except:
                pass
        
        if transcript:
            last_entry = transcript[-1]
            total_duration = last_entry['start'] + last_entry['duration']
            minutes = total_duration / 60
            
            return {
                'video_id': vimeo_id,
                'transcript': transcript,
                'language': 'en',
                'title': video_title,
                'total_duration_minutes': minutes,
                'entries_count': len(transcript),
                'platform': 'vimeo'
            }
        
        return {
            'video_id': vimeo_id,
            'transcript': [],
            'language': 'unknown',
            'title': video_title,
            'total_duration_minutes': 0,
            'entries_count': 0,
            'platform': 'vimeo',
            'warning': 'Aucun caption disponible. Seuls les vidéos Vimeo avec sous-titres sont supportées.'
        }
        
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Erreur Vimeo: {str(e)}")

def get_transcript(url: str, languages: list = None) -> dict:
    """
    Get transcript from any supported platform.
    
    Supported platforms:
    - YouTube (📺) - Automatic transcripts
    - Twitch (🟣) - VODs with captions only
    - Vimeo (🎬) - Videos with captions only
    """
    platform = detect_platform(url)
    
    if platform == 'youtube':
        return get_youtube_transcript(url, languages)
    elif platform == 'twitch':
        return get_twitch_transcript(url)
    elif platform == 'vimeo':
        return get_vimeo_transcript(url)
    else:
        raise ValueError(
            f"Plateforme non supportée. URLs supportées:\n"
            f"📺 YouTube: youtube.com, youtu.be\n"
            f"🟣 Twitch: twitch.tv (VODs avec captions)\n"
            f"🎬 Vimeo: vimeo.com (vidéos avec sous-titres)"
        )

def validate_url(url: str) -> tuple:
    """Validate URL and return platform info."""
    if not url or not url.strip():
        return False, "URL vide"

    url_clean = url.strip()

    if re.search(r'youtube\.com/(channel|c|user|@)', url_clean):
        return False, (
            "Cette URL est une chaîne YouTube, pas une vidéo.\n"
            "Colle l'URL d'une vidéo spécifique (ex: youtube.com/watch?v=...)"
        )

    if re.search(r'youtube\.com/(playlist|feed)', url_clean):
        return False, (
            "Cette URL est une playlist YouTube, pas une vidéo.\n"
            "Colle l'URL d'une vidéo spécifique (ex: youtube.com/watch?v=...)"
        )

    platform = detect_platform(url_clean)

    if platform == 'unknown':
        return False, (
            "URL non supportée. Formats acceptés:\n"
            "• YouTube: youtube.com/watch?v=..., youtu.be/...\n"
            "• Twitch: twitch.tv/videos/... (VOD uniquement)\n"
            "• Vimeo: vimeo.com/..."
        )

    icon = PLATFORMS.get(platform, {}).get('icon', '🔗')
    return True, f"{icon} {platform.capitalize()}"

def get_supported_platforms() -> list:
    """Get list of supported platforms."""
    return [
        {"id": "youtube", "name": "YouTube", "icon": "📺", "description": "Transcripts automatiques"},
        {"id": "twitch", "name": "Twitch", "icon": "🟣", "description": "VODs avec sous-titres"},
        {"id": "vimeo", "name": "Vimeo", "icon": "🎬", "description": "Vidéos avec sous-titres"},
    ]