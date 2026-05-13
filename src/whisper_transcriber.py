"""Audio transcription using Whisper (local model or OpenAI API) + yt-dlp download"""

import os
import json
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import config

WHISPER_API_MAX_BYTES = 24 * 1024 * 1024  # 24 MB hard limit for Whisper API
WHISPER_CHUNK_DURATION = 1200             # 20-minute chunks when splitting


def _find_yt_dlp() -> Optional[str]:
    """Return path to yt-dlp binary, checking PATH and common user-install locations."""
    import shutil

    if (path := shutil.which("yt-dlp")):
        return path

    candidates = [
        os.path.expanduser("~/Library/Python/3.9/bin/yt-dlp"),
        os.path.expanduser("~/Library/Python/3.10/bin/yt-dlp"),
        os.path.expanduser("~/Library/Python/3.11/bin/yt-dlp"),
        os.path.expanduser("~/.local/bin/yt-dlp"),
        "/usr/local/bin/yt-dlp",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def _find_node() -> Optional[str]:
    """Return path to Node.js binary (macOS + Linux)."""
    import shutil, glob

    if (path := shutil.which("node")):
        return path

    candidates = [
        # macOS
        "/usr/local/bin/node",
        "/opt/homebrew/bin/node",
        # Linux (Streamlit Cloud / Debian)
        "/usr/bin/node",
        "/usr/bin/nodejs",
        "/usr/local/lib/nodejs/bin/node",
        # nvm (any version)
        *glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")),
        *glob.glob("/usr/local/nvm/versions/node/*/bin/node"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def _subprocess_env() -> dict:
    """Build env dict that guarantees /usr/local/bin is in PATH for subprocess calls."""
    env = os.environ.copy()
    extra = "/usr/local/bin:/opt/homebrew/bin"
    if extra not in env.get("PATH", ""):
        env["PATH"] = extra + ":" + env.get("PATH", "")
    return env


def _js_runtime_flags() -> list:
    """Return --js-runtimes flag if a JS runtime is available, otherwise empty list."""
    node = _find_node()
    if node:
        return ["--js-runtimes", f"node:{node}"]
    return []


def check_yt_dlp() -> bool:
    return _find_yt_dlp() is not None


def _cookies_flags(cookies_path: Optional[str]) -> list:
    """Return --cookies flag if a cookies file path is provided and exists."""
    if cookies_path and os.path.isfile(cookies_path):
        return ["--cookies", cookies_path]
    return []


def download_audio(url: str, output_dir: str, cookies_path: Optional[str] = None) -> str:
    """Download audio from any video URL using yt-dlp. Returns path to audio file."""
    yt_dlp_bin = _find_yt_dlp()
    if not yt_dlp_bin:
        raise ValueError(
            "yt-dlp non installé.\n"
            "Installez-le avec: pip install yt-dlp\n"
            "ou: brew install yt-dlp"
        )

    output_template = os.path.join(output_dir, "audio.%(ext)s")

    cmd = [
        yt_dlp_bin,
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "--no-playlist",
        *_js_runtime_flags(),
        *_cookies_flags(cookies_path),
        "-o", output_template,
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=_subprocess_env())

    if result.returncode != 0:
        stderr = result.stderr[-800:] if result.stderr else "Erreur inconnue"
        raise ValueError(f"Erreur yt-dlp:\n{stderr}")

    for f in os.listdir(output_dir):
        if f.startswith("audio"):
            return os.path.join(output_dir, f)

    raise ValueError("Fichier audio introuvable après téléchargement")


def get_video_title_ytdlp(url: str, cookies_path: Optional[str] = None) -> str:
    """Get video title using yt-dlp."""
    yt_dlp_bin = _find_yt_dlp() or "yt-dlp"
    try:
        result = subprocess.run(
            [yt_dlp_bin, "--get-title", "--no-playlist",
             *_js_runtime_flags(), *_cookies_flags(cookies_path), url],
            capture_output=True, text=True, timeout=30, env=_subprocess_env(),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "Video"


def _compress_for_whisper(src: str, dst: str) -> bool:
    """Re-encode to 16 kHz mono 32 kbps — enough for speech, ~13 MB/h."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-b:a", "32k", dst],
            capture_output=True, timeout=300,
        )
        return r.returncode == 0 and os.path.exists(dst)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _get_audio_duration_sec(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        pass
    return 0.0


def _split_audio_chunk(src: str, dst: str, start: float, duration: float) -> bool:
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", src,
             "-ss", str(start), "-t", str(duration),
             "-ar", "16000", "-ac", "1", "-b:a", "32k", dst],
            capture_output=True, timeout=300,
        )
        return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 500
    except Exception:
        return False


def _transcribe_chunked(audio_path: str, language: Optional[str], client) -> list:
    """Split oversized audio into 20-min chunks and transcribe each, stitching timestamps."""
    total = _get_audio_duration_sec(audio_path)
    if total <= 0:
        raise ValueError("Impossible de lire la durée de l'audio pour le découpage en chunks")

    tmp_dir = tempfile.mkdtemp()
    try:
        all_segments = []
        start = 0.0
        idx = 0
        while start < total:
            chunk_path = os.path.join(tmp_dir, f"chunk_{idx:04d}.mp3")
            if not _split_audio_chunk(audio_path, chunk_path, start, WHISPER_CHUNK_DURATION):
                break
            with open(chunk_path, "rb") as f:
                kwargs = {
                    "model": "whisper-1",
                    "file": f,
                    "response_format": "verbose_json",
                    "timestamp_granularities": ["segment"],
                }
                if language:
                    kwargs["language"] = language
                result = client.audio.transcriptions.create(**kwargs)
            for seg in result.segments:
                all_segments.append({
                    "text": seg.text,
                    "start": float(seg.start) + start,
                    "duration": float(seg.end) - float(seg.start),
                })
            start += WHISPER_CHUNK_DURATION
            idx += 1
        return all_segments
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def transcribe_with_whisper_api(
    audio_path: str, language: Optional[str] = None, api_key: Optional[str] = None
) -> list:
    """Transcribe using OpenAI Whisper API."""
    try:
        import openai
    except ImportError:
        raise ValueError("Package 'openai' non installé: pip install openai")

    api_key = api_key or getattr(config, "OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY non configurée")

    client = openai.OpenAI(api_key=api_key)

    if os.path.getsize(audio_path) > WHISPER_API_MAX_BYTES:
        return _transcribe_chunked(audio_path, language, client)

    with open(audio_path, "rb") as f:
        kwargs = {
            "model": "whisper-1",
            "file": f,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment"],
        }
        if language:
            kwargs["language"] = language

        transcript = client.audio.transcriptions.create(**kwargs)

    return [
        {
            "text": seg.text,
            "start": float(seg.start),
            "duration": float(seg.end) - float(seg.start),
        }
        for seg in transcript.segments
    ]


def transcribe_with_local_whisper(
    audio_path: str, model_size: str = "base", language: Optional[str] = None
) -> list:
    """Transcribe using local Whisper model."""
    try:
        import whisper
    except ImportError:
        raise ValueError(
            "Whisper local non disponible dans cette version de l'application.\n"
            "Solution : entrez une clé OpenAI dans le champ dédié pour utiliser l'API Whisper."
        )

    model = whisper.load_model(model_size)
    kwargs = {"verbose": False}
    if language:
        kwargs["language"] = language

    result = model.transcribe(audio_path, **kwargs)

    return [
        {
            "text": seg["text"],
            "start": float(seg["start"]),
            "duration": float(seg["end"]) - float(seg["start"]),
        }
        for seg in result.get("segments", [])
    ]


def transcribe_audio(
    audio_path: str, language: Optional[str] = None, model_size: str = "base",
    openai_api_key: Optional[str] = None,
) -> list:
    """
    Transcribe audio using best available method.
    Priority: OpenAI Whisper API (if key available) → local Whisper model.
    """
    effective_key = openai_api_key or getattr(config, "OPENAI_API_KEY", "")

    if effective_key:
        try:
            return transcribe_with_whisper_api(audio_path, language, api_key=effective_key)
        except Exception:
            pass  # fall through to local whisper

    return transcribe_with_local_whisper(audio_path, model_size=model_size, language=language)


def transcribe_url(
    url: str, language: Optional[str] = None, model_size: str = "base",
    cookies_path: Optional[str] = None, openai_api_key: Optional[str] = None,
) -> dict:
    """Download audio from any video URL and transcribe with Whisper."""
    tmp_dir = tempfile.mkdtemp()
    try:
        audio_path = download_audio(url, tmp_dir, cookies_path=cookies_path)
        title = get_video_title_ytdlp(url, cookies_path=cookies_path)

        # Compress to 16kHz mono 32kbps — reduces size ~2× and keeps Whisper API well under 25 MB/h
        compressed_path = os.path.join(tmp_dir, "audio_compressed.mp3")
        if _compress_for_whisper(audio_path, compressed_path):
            audio_path = compressed_path

        segments = transcribe_audio(
            audio_path, language=language, model_size=model_size,
            openai_api_key=openai_api_key,
        )

        if not segments:
            raise ValueError("Aucun segment audio transcrit")

        last = segments[-1]
        total_duration = last["start"] + last["duration"]

        return {
            "transcript": segments,
            "language": language or "auto",
            "title": title,
            "total_duration_minutes": total_duration / 60,
            "entries_count": len(segments),
            "method": "whisper",
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def transcribe_local_file(
    file_bytes: bytes, filename: str, language: Optional[str] = None, model_size: str = "base",
    openai_api_key: Optional[str] = None,
) -> dict:
    """Transcribe an uploaded local audio/video file with Whisper."""
    title = Path(filename).stem
    suffix = Path(filename).suffix.lower()

    tmp_dir = tempfile.mkdtemp()
    try:
        audio_path = os.path.join(tmp_dir, f"upload{suffix}")
        with open(audio_path, "wb") as f:
            f.write(file_bytes)

        # Extract audio from video files using ffmpeg
        video_exts = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v"}
        if suffix in video_exts:
            mp3_path = os.path.join(tmp_dir, "audio.mp3")
            try:
                cmd = [
                    "ffmpeg", "-i", audio_path,
                    "-vn", "-ar", "16000", "-ac", "1", "-b:a", "32k",
                    mp3_path, "-y"
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                if result.returncode == 0:
                    audio_path = mp3_path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass  # Try with original file; Whisper can handle many formats

        segments = transcribe_audio(
            audio_path, language=language, model_size=model_size,
            openai_api_key=openai_api_key,
        )

        if not segments:
            raise ValueError("Aucun segment audio transcrit")

        last = segments[-1]
        total_duration = last["start"] + last["duration"]

        return {
            "transcript": segments,
            "language": language or "auto",
            "title": title,
            "total_duration_minutes": total_duration / 60,
            "entries_count": len(segments),
            "method": "whisper_local_file",
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
