"""Audio transcription using Whisper (local model or OpenAI API) + yt-dlp download"""

import os
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import config


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
    """Return path to Node.js binary."""
    import shutil

    if (path := shutil.which("node")):
        return path

    candidates = [
        "/usr/local/bin/node",
        "/opt/homebrew/bin/node",
        os.path.expanduser("~/.nvm/versions/node/*/bin/node"),
    ]
    for path in candidates:
        if "*" not in path and os.path.isfile(path):
            return path

    # nvm glob fallback
    import glob
    for path in glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")):
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


def download_audio(url: str, output_dir: str) -> str:
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


def get_video_title_ytdlp(url: str) -> str:
    """Get video title using yt-dlp."""
    yt_dlp_bin = _find_yt_dlp() or "yt-dlp"
    try:
        result = subprocess.run(
            [yt_dlp_bin, "--get-title", "--no-playlist", *_js_runtime_flags(), url],
            capture_output=True, text=True, timeout=30, env=_subprocess_env(),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "Video"


def transcribe_with_whisper_api(audio_path: str, language: Optional[str] = None) -> list:
    """Transcribe using OpenAI Whisper API."""
    try:
        import openai
    except ImportError:
        raise ValueError("Package 'openai' non installé: pip install openai")

    api_key = getattr(config, "OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY non configurée dans .env")

    client = openai.OpenAI(api_key=api_key)

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
            "openai-whisper non installé.\n"
            "Installez-le avec: pip install openai-whisper\n"
            "(Nécessite ffmpeg: brew install ffmpeg)"
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
    audio_path: str, language: Optional[str] = None, model_size: str = "base"
) -> list:
    """
    Transcribe audio using best available method.
    Priority: OpenAI Whisper API (if OPENAI_API_KEY set) → local Whisper model.
    """
    openai_key = getattr(config, "OPENAI_API_KEY", "")

    if openai_key:
        try:
            return transcribe_with_whisper_api(audio_path, language)
        except Exception:
            pass  # fall through to local whisper

    return transcribe_with_local_whisper(audio_path, model_size=model_size, language=language)


def transcribe_url(
    url: str, language: Optional[str] = None, model_size: str = "base"
) -> dict:
    """Download audio from any video URL and transcribe with Whisper."""
    tmp_dir = tempfile.mkdtemp()
    try:
        audio_path = download_audio(url, tmp_dir)
        title = get_video_title_ytdlp(url)
        segments = transcribe_audio(audio_path, language=language, model_size=model_size)

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
    file_bytes: bytes, filename: str, language: Optional[str] = None, model_size: str = "base"
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
                    "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
                    mp3_path, "-y"
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                if result.returncode == 0:
                    audio_path = mp3_path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass  # Try with original file; Whisper can handle many formats

        segments = transcribe_audio(audio_path, language=language, model_size=model_size)

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
