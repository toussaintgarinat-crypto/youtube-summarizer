"""
YouTube Summarizer — Streamlit Web Interface
Supports: YouTube, Twitch, Vimeo (transcript), any platform via Whisper, local audio/video files.
"""

from __future__ import annotations

import atexit
import os
import queue
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime

import streamlit as st
import config
from src import extractor, chunker, analyzer, fusion
from src import tts_generator, local_llm, drive_exporter
from src.models import fetch_free_models, fetch_all_models, fetch_open_code_go_models
from src.image_generator import generate_image, get_providers_list, get_styles_list, build_image_prompt, enhance_image_prompt
from src.excalidraw_generator import generate_diagram as generate_excalidraw
from src import updater
from src.video_generator import generate_video, get_video_providers_list, build_video_prompt


# ──────────────────────────────────────────────────────────────
# Model caches
# ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_free_models() -> dict:
    return fetch_free_models()


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_all_models() -> dict:
    return fetch_all_models()


# ──────────────────────────────────────────────────────────────
# Transcript cache (avoids re-fetching the same URL)
# ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_transcript(url: str) -> dict | None:
    """Fetch and cache native transcript for 30 min. Returns None on failure."""
    try:
        return extractor.get_transcript(url)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Cookies helpers
# ──────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _server_cookies_path() -> str | None:
    """Return path to cookies file: local file takes priority, then YOUTUBE_COOKIES env/secret."""
    local = os.path.join(os.path.dirname(__file__), ".streamlit", "youtube_cookies.txt")
    if os.path.isfile(local):
        return local

    content = config.YOUTUBE_COOKIES
    if not content or not content.strip():
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    # Clean up on process exit so temp files don't accumulate
    atexit.register(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
    return tmp.name


def resolve_cookies_path(user_upload) -> str | None:
    """User upload takes priority; fall back to server-side cookies from secrets."""
    if user_upload:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb")
        tmp.write(user_upload.read())
        tmp.flush()
        tmp.close()
        return tmp.name
    return _server_cookies_path()


# ──────────────────────────────────────────────────────────────
# Password protection
# ──────────────────────────────────────────────────────────────

def check_password() -> bool:
    return True


# ──────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────

def _save_key_to_env(key_name: str, value: str):
    """Save or update a single key in .env so it persists across refreshes."""
    env_path = config.BASE_DIR / ".env"
    try:
        lines = []
        found = False
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith(f"{key_name}="):
                        lines.append(f"{key_name}={value}\n")
                        found = True
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
        if not found:
            lines.append(f"{key_name}={value}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)
        os.environ[key_name] = value
        if key_name == "OPENROUTER_API_KEY":
            config.OPENROUTER_API_KEY = value
    except Exception:
        pass


def init_session_state():
    defaults = {
        "analysis_result": None,
        "current_title": "",
        "current_transcript": "",
        "is_processing": False,
        "history": [],
        "authenticated": False,
        "chat_history": [],
        "generated_image_url": "",
        "generated_image_provider": "",
        "generated_video_url": "",
        "generated_image_prompt": "",
        "excalidraw_json": "",
        "excalidraw_concepts": [],
        "_last_url": "",
        # Video selection state
        "video_list": None,
        "video_list_title": "",
        "video_list_type": "",
        "video_list_url": "",
        # Background thread state
        "_thread_finished": False,
        "_result_queue": None,
        "_cancel_event": None,
        "_processing_source": "",
        "llm_provider": "openrouter",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def active_api_key() -> str:
    """Return the user's custom key if set, otherwise the default from config/secrets."""
    try:
        custom = st.session_state.get("custom_api_key", "")
        if custom:
            return custom
    except Exception:
        pass
    return config.OPENROUTER_API_KEY


def active_go_api_key() -> str:
    """Return the OpenCode Go key from session, env, or secrets."""
    key = st.session_state.get("custom_go_api_key", "")
    if key:
        return key
    return config.OPENCODE_GO_API_KEY


def active_provider() -> str:
    """Return the active LLM provider name."""
    return st.session_state.get("llm_provider", "openrouter")


def get_provider_api_key(provider_id: str) -> str:
    """Return the API key for a specific provider, if configured."""
    key = st.session_state.get(f"provider_key_{provider_id}", "")
    return key or active_api_key()


# ──────────────────────────────────────────────────────────────
# Pipeline (no direct Streamlit calls — uses on_progress callback)
# ──────────────────────────────────────────────────────────────

def run_pipeline(
    transcript: list,
    video_title: str,
    model: str,
    chunk_size: int,
    overlap: int,
    output_language: str = "Français",
    on_progress=None,
    cancel_event=None,
    api_key: str = "",
    use_local: bool = False,
    local_model: str = "llama3.2",
    fallbacks: list = None,
    provider: str = "openrouter",
) -> str:
    """Chunk → Analyze → Fuse. Reports progress via on_progress(pct: int, msg: str)."""
    api_key = api_key or active_api_key()
    fallbacks = fallbacks or []

    def _progress(pct: int, msg: str):
        if on_progress:
            on_progress(pct, msg)

    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Analyse annulée par l'utilisateur")

    _progress(0, "✂️ Découpage en chunks…")
    chunks = chunker.chunk_transcript(transcript, max_tokens=chunk_size, overlap_tokens=overlap, model=model)
    chunk_info = chunker.get_chunk_count_info(chunks)
    total_chunks = len(chunks)
    _progress(10, f"📊 {chunk_info}")
    time.sleep(2.0)
    _progress(15, f"🤖 Analyse de {total_chunks} lot(s) par l'IA…")
    time.sleep(1.0)

    analyses = []
    for i, chunk in enumerate(chunks):
        _check_cancel()
        pct = 20 + int(70 * (i + 1) / total_chunks) if total_chunks > 0 else 90
        _progress(pct, f"🧠 Chunk {i+1}/{total_chunks} ({chunk.get('tokens', 0)} tokens) — analyse en cours...")
        if use_local:
            analyses.append(local_llm.analyze_chunk_local(
                chunk["text"], video_title, model=local_model, output_language=output_language,
            ))
        else:
            analyses.append(analyzer.analyze_chunk(
                chunk["text"], video_title, model=model, api_key=api_key,
                output_language=output_language, fallback_models=fallbacks,
                provider=provider,
            ))
        if len(chunks) > 1:
            time.sleep(1)

    _check_cancel()
    final_analysis = analyses[0]
    if len(analyses) > 1:
        _progress(95, f"🔗 Fusion des {len(analyses)} analyses…")
        if use_local:
            merged = "\n\n".join(analyses)
            final_analysis = merged
        else:
            final_analysis = fusion.fusion_analyses(
                analyses, video_title, model, api_key=api_key,
                output_language=output_language, fallback_models=fallbacks,
                provider=provider,
            )

    _progress(100, "✅ Terminé !")
    return final_analysis


def _transcript_to_text(transcript_entries: list) -> str:
    """Convert transcript entries (list of {text, start, duration}) to plain text with timestamps."""
    lines = []
    for entry in transcript_entries:
        start = entry.get("start", 0)
        minutes = int(start // 60)
        seconds = int(start % 60)
        timestamp = f"[{minutes}:{seconds:02d}]"
        lines.append(f"{timestamp} {entry.get('text', '')}")
    return "\n".join(lines)


def process_url(
    url: str,
    model: str,
    chunk_size: int,
    overlap: int,
    force_whisper: bool,
    whisper_lang: str,
    whisper_model: str,
    output_language: str = "Français",
    cookies_path: str = None,
    on_progress=None,
    cancel_event=None,
    api_key: str = "",
    provider: str = "openrouter",
    openai_api_key: str = "",
) -> tuple[str, str, list, str]:
    """Fetch transcript (or Whisper fallback) then run pipeline. Returns (result, title, warnings, transcript_text)."""
    warnings: list[str] = []

    def _progress(pct: int, msg: str):
        if on_progress:
            on_progress(pct, msg)

    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Analyse annulée par l'utilisateur")

    transcript_data = None

    if not force_whisper:
        _progress(5, "📥 Extraction du transcript...")
        try:
            data = extractor.get_transcript(url)
        except Exception as e:
            data = None
            warnings.append(f"⚠️ Erreur de transcript ({e}) — passage en mode Whisper...")
        if data and data.get("transcript"):
            transcript_data = data
        elif data:
            warnings.append(f"⚠️ {data.get('warning', 'Aucun transcript disponible')} — passage en mode Whisper...")
        else:
            warnings.append("⚠️ Transcript indisponible — passage en mode Whisper...")

    _check_cancel()

    if transcript_data is None:
        from src.whisper_transcriber import transcribe_url
        _progress(10, "🎙️ Téléchargement audio + transcription Whisper...")
        transcript_data = transcribe_url(
            url,
            language=whisper_lang if whisper_lang != "auto" else None,
            model_size=whisper_model,
            cookies_path=cookies_path,
            openai_api_key=openai_api_key or None,
        )

    transcript = transcript_data["transcript"]
    title = transcript_data.get("title", "Video")
    duration = transcript_data.get("total_duration_minutes", 0)
    method = transcript_data.get("method", "transcript")
    method_label = "Whisper" if "whisper" in method else "transcript"

    _progress(35, f"📺 {title} — {duration:.1f} min — {len(transcript)} segments ({method_label})")
    _check_cancel()

    def _pipeline_progress(pct: int, msg: str):
        on_progress(35 + int(pct * 0.65), msg)

    result = run_pipeline(
        transcript, title, model, chunk_size, overlap,
        output_language=output_language,
        on_progress=_pipeline_progress if on_progress else None,
        cancel_event=cancel_event,
        api_key=api_key,
        provider=provider,
    )
    transcript_text = _transcript_to_text(transcript)
    return result, title, warnings, transcript_text


def process_local_file(
    file_bytes: bytes,
    filename: str,
    model: str,
    chunk_size: int,
    overlap: int,
    whisper_lang: str,
    whisper_model: str,
    output_language: str = "Français",
    on_progress=None,
    cancel_event=None,
    api_key: str = "",
    provider: str = "openrouter",
    openai_api_key: str = "",
) -> tuple[str, str, list, str]:
    """Transcribe local audio/video file then run pipeline. Returns (result, title, warnings, transcript_text)."""
    from src.whisper_transcriber import transcribe_local_file

    warnings: list[str] = []

    def _progress(pct: int, msg: str):
        if on_progress:
            on_progress(pct, msg)

    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Analyse annulée par l'utilisateur")

    _progress(5, f"🎙️ Transcription de {filename} avec Whisper...")

    transcript_data = transcribe_local_file(
        file_bytes, filename,
        language=whisper_lang if whisper_lang != "auto" else None,
        model_size=whisper_model,
        openai_api_key=openai_api_key or None,
    )

    transcript = transcript_data["transcript"]
    title = transcript_data.get("title", filename)
    duration = transcript_data.get("total_duration_minutes", 0)

    _progress(30, f"✅ {title} — {duration:.1f} min — {len(transcript)} segments")
    _check_cancel()

    def _pipeline_progress(pct: int, msg: str):
        on_progress(30 + int(pct * 0.70), msg)

    result = run_pipeline(
        transcript, title, model, chunk_size, overlap,
        output_language=output_language,
        on_progress=_pipeline_progress if on_progress else None,
        cancel_event=cancel_event,
        api_key=api_key,
        provider=provider,
    )
    transcript_text = _transcript_to_text(transcript)
    return result, title, warnings, transcript_text



def process_playlist(
    url: str,
    model: str,
    chunk_size: int,
    overlap: int,
    force_whisper: bool,
    whisper_lang: str,
    whisper_model: str,
    output_language: str = "Français",
    cookies_path: str = None,
    on_progress=None,
    cancel_event=None,
    videos: list[dict] | None = None,
    api_key: str = "",
    provider: str = "openrouter",
    openai_api_key: str = "",
) -> tuple[str, str, list, str]:
    """Process all videos in a YouTube playlist. Returns combined result."""
    warnings: list[str] = []
    all_results = []
    playlist_title = "Playlist"

    def _progress(pct: int, msg: str):
        if on_progress:
            on_progress(pct, msg)

    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Analyse annulée par l'utilisateur")

    if videos is None:
        _progress(2, "📋 Récupération des vidéos de la playlist...")
        videos = extractor.get_playlist_videos(url, cookies_path=cookies_path)
    total = len(videos)
    playlist_id = extractor.extract_playlist_id(url)
    if playlist_id:
        try:
            import subprocess
            yt_bin = shutil.which("yt-dlp") or "yt-dlp"
            result = subprocess.run(
                [yt_bin, "--print", "%(playlist_title)s", "--flat-playlist", url],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                playlist_title = result.stdout.strip()
        except Exception:
            pass

    _progress(5, f"📋 Playlist : {playlist_title} — {total} vidéos trouvées")

    for idx, video in enumerate(videos):
        _check_cancel()
        video_url = video['url']
        video_title = video['title']
        progress_start = 5 + (85 * idx // total)
        progress_end = 5 + (85 * (idx + 1) // total)

        def _video_progress(pct: int, msg: str):
            video_pct = progress_start + int((progress_end - progress_start) * pct / 100)
            _progress(video_pct, f"[{idx+1}/{total}] {msg}")

        _progress(progress_start, f"[{idx+1}/{total}] 📥 Analyse de : {video_title}")
        try:
            result, title, w, _ = process_url(
                video_url, model, chunk_size, overlap,
                force_whisper, whisper_lang, whisper_model,
                output_language, cookies_path,
                on_progress=_video_progress,
                cancel_event=cancel_event,
                api_key=api_key,
                provider=provider,
                openai_api_key=openai_api_key,
            )
            all_results.append(f"## 📺 Vidéo {idx+1} : {title}\n\n{result}\n\n---\n")
            for warn in w:
                warnings.append(f"[{video_title}] {warn}")
        except InterruptedError:
            raise
        except Exception as e:
            error_msg = f"[{video_title}] Erreur : {str(e)}"
            warnings.append(error_msg)
            all_results.append(f"## 📺 Vidéo {idx+1} : {video_title}\n\n⚠️ {error_msg}\n\n---\n")

    _check_cancel()
    _progress(92, "🔗 Génération du rapport consolidé...")

    summary_header = f"# 📋 Rapport de la playlist : {playlist_title}\n"
    summary_header += f"**{total} vidéos analysées**\n\n---\n\n"
    combined = summary_header + "\n".join(all_results)

    _progress(95, "🤖 Génération du résumé global de la playlist...")
    try:
        playlist_summary_prompt = (
            f"Voici les analyses de {total} vidéos d'une playlist intitulée '{playlist_title}'.\n\n"
            f"{' '.join(all_results[:3])}"  # Send first 3 analyses as context
            f"\n\nGénère un résumé global de cette playlist en 3-5 phrases."
        )
        playlist_summary = analyzer.call_llm(
            playlist_summary_prompt, model=model, max_tokens=2000,
            api_key=api_key,
            fallback_models=[],
            provider=provider,
        )
        combined = f"# 📋 Rapport de la playlist : {playlist_title}\n\n"
        combined += f"**{total} vidéos analysées**\n\n"
        combined += f"## 🌟 Résumé global\n\n{playlist_summary}\n\n---\n\n"
        combined += "\n".join(all_results)
    except Exception:
        pass

    _progress(100, "✅ Playlist terminée !")
    return combined, playlist_title, warnings, ""


def process_channel(
    url: str,
    model: str,
    chunk_size: int,
    overlap: int,
    force_whisper: bool,
    whisper_lang: str,
    whisper_model: str,
    output_language: str = "Français",
    cookies_path: str = None,
    max_videos: int = 50,
    on_progress=None,
    cancel_event=None,
    videos: list[dict] | None = None,
    channel_name: str | None = None,
    api_key: str = "",
    provider: str = "openrouter",
    openai_api_key: str = "",
) -> tuple[str, str, list, str]:
    """Process all videos from a YouTube channel. Returns combined result."""
    warnings: list[str] = []
    all_results = []

    def _progress(pct: int, msg: str):
        if on_progress:
            on_progress(pct, msg)

    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Analyse annulée par l'utilisateur")

    if videos is None:
        _progress(2, "📋 Récupération des vidéos de la chaîne...")
        videos, channel_name = extractor.get_channel_videos(url, cookies_path=cookies_path, max_videos=max_videos)
    elif channel_name is None:
        channel_name = "Chaîne YouTube"
    total = len(videos)

    _progress(5, f"📺 Chaîne : {channel_name} — {total} vidéos trouvées")

    for idx, video in enumerate(videos):
        _check_cancel()
        video_url = video['url']
        video_title = video['title']
        progress_start = 5 + (85 * idx // total)
        progress_end = 5 + (85 * (idx + 1) // total)

        def _video_progress(pct: int, msg: str):
            video_pct = progress_start + int((progress_end - progress_start) * pct / 100)
            _progress(video_pct, f"[{idx+1}/{total}] {msg}")

        _progress(progress_start, f"[{idx+1}/{total}] 📥 Analyse de : {video_title}")
        try:
            result, title, w, _ = process_url(
                video_url, model, chunk_size, overlap,
                force_whisper, whisper_lang, whisper_model,
                output_language, cookies_path,
                on_progress=_video_progress,
                cancel_event=cancel_event,
                api_key=api_key,
                provider=provider,
                openai_api_key=openai_api_key,
            )
            all_results.append(f"## 📺 Vidéo {idx+1} : {title}\n\n{result}\n\n---\n")
            for warn in w:
                warnings.append(f"[{video_title}] {warn}")
        except InterruptedError:
            raise
        except Exception as e:
            error_msg = f"[{video_title}] Erreur : {str(e)}"
            warnings.append(error_msg)
            all_results.append(f"## 📺 Vidéo {idx+1} : {video_title}\n\n⚠️ {error_msg}\n\n---\n")

    _check_cancel()
    _progress(92, "🔗 Génération du rapport consolidé...")

    summary_header = f"# 📺 Rapport de la chaîne : {channel_name}\n"
    summary_header += f"**{total} vidéos analysées**\n\n---\n\n"
    combined = summary_header + "\n".join(all_results)

    _progress(95, "🤖 Génération du résumé global de la chaîne...")
    try:
        channel_summary_prompt = (
            f"Voici les analyses de {total} vidéos de la chaîne YouTube '{channel_name}'.\n\n"
            f"{' '.join(all_results[:3])}"
            f"\n\nGénère un résumé global de cette chaîne en 3-5 phrases, "
            f"en mettant en évidence les thèmes principaux abordés."
        )
        channel_summary = analyzer.call_llm(
            channel_summary_prompt, model=model, max_tokens=2000,
            api_key=api_key,
            fallback_models=[],
            provider=provider,
        )
        combined = f"# 📺 Rapport de la chaîne : {channel_name}\n\n"
        combined += f"**{total} vidéos analysées**\n\n"
        combined += f"## 🌟 Résumé global\n\n{channel_summary}\n\n---\n\n"
        combined += "\n".join(all_results)
    except Exception:
        pass

    _progress(100, "✅ Chaîne terminée !")
    return combined, channel_name, warnings, ""


# ──────────────────────────────────────────────────────────────
# Background thread helpers
# ──────────────────────────────────────────────────────────────

# Shared thread-safe progress store (not st.session_state — avoids ScriptRunContext issues)
_thread_progress_store = {"pct": 0, "msg": "Démarrage..."}
_thread_progress_lock = threading.Lock()

def _set_progress(pct: int, msg: str):
    with _thread_progress_lock:
        _thread_progress_store["pct"] = pct
        _thread_progress_store["msg"] = msg

def _get_progress():
    with _thread_progress_lock:
        return _thread_progress_store["pct"], _thread_progress_store["msg"]


def _start_analysis_thread(source: str, fn, *args, **kwargs):
    """Run fn(*args, **kwargs) in a daemon thread. fn must return (result, title, warnings)."""
    cancel_ev = threading.Event()
    result_q: queue.Queue = queue.Queue()

    def _on_progress(pct: int, msg: str):
        _set_progress(min(pct, 100), msg)

    def _body():
        import traceback as _tb
        try:
            _set_progress(2, "🚀 Thread démarré...")
            result, title, w, transcript_text = fn(*args, on_progress=_on_progress, cancel_event=cancel_ev, **kwargs)
            result_q.put(("ok", result, title, w, transcript_text))
        except InterruptedError:
            result_q.put(("cancelled", "", "", "", []))
        except Exception as e:
            _tb.print_exc()
            result_q.put(("error", str(e), "", "", ""))

    _set_progress(0, "Démarrage...")
    st.session_state._cancel_event = cancel_ev
    st.session_state._result_queue = result_q
    st.session_state._processing_source = source
    st.session_state.is_processing = True

    threading.Thread(target=_body, daemon=True).start()


# ──────────────────────────────────────────────────────────────
# History
# ──────────────────────────────────────────────────────────────

def add_to_history(title: str, source: str, result: str):
    st.session_state.history.insert(0, {
        "title": title, "source": source,
        "result": result, "timestamp": datetime.now().strftime("%H:%M:%S"),
    })
    st.session_state.history = st.session_state.history[:10]


# ──────────────────────────────────────────────────────────────
# Chat / Q&A
# ──────────────────────────────────────────────────────────────

QA_PROMPT_TEMPLATE = """Tu es un assistant spécialisé dans l'analyse de contenu vidéo.
Voici le transcript complet d'une vidéo :

{transcript}

Réponds à la question suivante en te basant UNIQUEMENT sur le transcript ci-dessus.
Si la réponse ne se trouve pas dans le transcript, dis-le clairement.
Utilise des timestamps [min:sec] quand tu cites des passages précis.

Question : {question}"""


def run_qa(question: str, transcript_text: str) -> str:
    """Answer a question about the video using the transcript as context."""
    prov = active_provider()
    api_key = active_go_api_key() if prov == "opencode-go" else active_api_key()
    model = st.session_state.get("selected_model", config.DEFAULT_MODEL)
    free_models = list(_cached_free_models().keys())
    fallbacks = [m for m in free_models if m != model] if prov == "openrouter" else []

    prompt = QA_PROMPT_TEMPLATE.format(transcript=transcript_text, question=question)

    if len(prompt) > 120000:
        prompt = prompt[:60000] + "\n...[transcript tronqué]...\n" + prompt[-60000:]

    use_local = st.session_state.get("use_local_llm", False)
    local_model = st.session_state.get("local_llm_model", "llama3.2")
    if use_local:
        return local_llm.call_local_llm(prompt, model=local_model, max_tokens=3000)

    return analyzer.call_llm(
        prompt, model=model, max_tokens=3000,
        api_key=api_key, fallback_models=fallbacks,
        provider=prov,
    )


# ──────────────────────────────────────────────────────────────
# Image generation
# ──────────────────────────────────────────────────────────────

def render_image_generation(result: str, title: str):
    """Render image generation UI after analysis."""
    with st.expander("🎨 Générer une image à partir du résumé", expanded=False):
        st.markdown("Générez une illustration basée sur le contenu de la vidéo.")

        providers = get_providers_list()
        provider_options = {f"{p['icon']} {p['name']}": p['id'] for p in providers}
        selected_provider_label = st.selectbox(
            "Provider d'image",
            options=list(provider_options.keys()),
            index=0,
            key="img_provider",
        )
        selected_provider = provider_options[selected_provider_label]

        styles = get_styles_list()
        style_options = {s['name']: s['id'] for s in styles}
        selected_style_label = st.selectbox(
            "Style d'image",
            options=list(style_options.keys()),
            index=0,
            key="img_style",
        )
        selected_style = style_options[selected_style_label]
        style_obj = next((s for s in styles if s["id"] == selected_style), None)

        # Prompt mode: Auto or Custom
        prompt_mode = st.radio(
            "Source du prompt",
            ["🔧 Auto (généré depuis le résumé)", "✏️ Personnalisé"],
            index=0,
            horizontal=True,
            key="img_prompt_mode",
        )

        custom_prompt = ""
        if "Personnalisé" in prompt_mode:
            custom_prompt = st.text_area(
                "Votre prompt",
                placeholder="Décrivez l'image que vous voulez générer...",
                key="img_custom_prompt",
                height=120,
            )
            col_enhance, _ = st.columns([1, 3])
            with col_enhance:
                enhance_btn = st.button("🤖 Améliorer le prompt (CTLT+)", key="btn_enhance_prompt")
            if enhance_btn and custom_prompt.strip():
                with st.spinner("🧠 Amélioration du prompt..."):
                    enhanced = enhance_image_prompt(custom_prompt.strip(), active_api_key(), image_llm_model, provider="openrouter")
                if enhanced.get("success"):
                    st.session_state["img_custom_prompt"] = enhanced["enhanced"]
                    st.success("✅ Prompt amélioré !")
                    st.rerun()
                else:
                    st.error(f"❌ {enhanced.get('error', 'Erreur')}")

        col_gen, col_dl = st.columns([1, 1])
        with col_gen:
            generate_btn = st.button("🚀 Générer l'image", type="primary", key="btn_gen_img")
        with col_dl:
            if st.session_state.generated_image_url:
                st.markdown(
                    f"[🌐 Ouvrir l'image dans un nouvel onglet]({st.session_state.generated_image_url})",
                    unsafe_allow_html=True,
                )

        if generate_btn:
            with st.spinner("🎨 Génération de l'image..."):
                if "Personnalisé" in prompt_mode and custom_prompt.strip():
                    image_prompt = custom_prompt.strip()
                else:
                    image_prompt = build_image_prompt(result, title, style=selected_style)
                img_result = generate_image(
                    prompt=image_prompt,
                    provider=selected_provider,
                    api_key=get_provider_api_key(selected_provider),
                )

            if img_result.get('success'):
                st.session_state.generated_image_url = img_result['image_url']
                st.session_state.generated_image_provider = selected_provider
                st.session_state.generated_image_prompt = img_result.get('revised_prompt', image_prompt)
                st.image(img_result['image_url'], caption=img_result.get('revised_prompt', image_prompt), use_container_width=True)
            else:
                st.error(f"❌ {img_result.get('error', 'Erreur inconnue')}")

        if st.session_state.generated_image_url and not generate_btn:
            st.image(st.session_state.generated_image_url,
                     caption=st.session_state.generated_image_prompt,
                     use_container_width=True)


def render_video_generation(result: str, title: str):
    """Render video generation UI after analysis."""
    with st.expander("🎬 Générer une vidéo à partir du résumé", expanded=False):
        st.markdown("Générez une courte vidéo basée sur le contenu de la vidéo.")

        vp = get_video_providers_list()
        vp_options = {f"{p['icon']} {p['name']}": p['id'] for p in vp}
        col_vp, col_vm = st.columns(2)
        with col_vp:
            sel_vp_label = st.selectbox(
                "Provider vidéo", options=list(vp_options.keys()),
                key="res_video_provider",
            )
        sel_vp = vp_options[sel_vp_label]
        vp_config = next((p for p in vp if p['id'] == sel_vp), {})
        with col_vm:
            sel_vm = st.selectbox(
                "Modèle", options=vp_config.get("models", []),
                key="res_video_model",
            )

        prompt_mode = st.radio(
            "Source du prompt",
            ["🔧 Auto (généré depuis le résumé)", "✏️ Personnalisé"],
            index=0, horizontal=True, key="video_prompt_mode",
        )

        custom_prompt = ""
        if "Personnalisé" in prompt_mode:
            custom_prompt = st.text_area(
                "Votre prompt vidéo",
                placeholder="Décrivez la vidéo que vous voulez générer...",
                key="video_custom_prompt", height=100,
            )

        if st.button("🎬 Générer la vidéo", type="primary", key="btn_gen_video"):
            video_prompt = custom_prompt.strip() if "Personnalisé" in prompt_mode and custom_prompt.strip() else build_video_prompt(result, title)
            api_key = ""
            for p in vp:
                if p['id'] == sel_vp:
                    env_key_name = {"replicate-video": "REPLICATE_API_KEY", "luma": "REPLICATE_API_KEY", "minimax": "REPLICATE_API_KEY"}.get(sel_vp, "REPLICATE_API_KEY")
                    api_key = os.getenv(env_key_name, "") or st.session_state.get(f"provider_key_replicate", "")
                    break

            if not api_key:
                st.error("⚠️ Configurez une clé Replicate dans la sidebar (🔌 Providers images).")
                st.stop()

            with st.spinner("🎬 Génération vidéo en cours... (cela peut prendre 1-2 minutes)"):
                vid_result = generate_video(
                    prompt=video_prompt,
                    provider=sel_vp,
                    model=sel_vm,
                    api_key=api_key,
                )

            if vid_result.get('success'):
                video_url = vid_result['video_url']
                st.session_state.generated_video_url = video_url
                st.success("✅ Vidéo générée !")
                st.video(video_url)
                st.markdown(f"[🌐 Ouvrir la vidéo]({video_url})")
            else:
                st.error(f"❌ {vid_result.get('error', 'Erreur inconnue')}")

        if st.session_state.get("generated_video_url") and st.session_state.get("generated_video_url") != st.session_state.get("_last_vid_url"):
            st.video(st.session_state.generated_video_url)


def _render_excalidraw_download(title: str):
    st.download_button(
        "💾 Télécharger .excalidraw",
        data=st.session_state.excalidraw_json,
        file_name=_safe_filename(title, "schema.excalidraw"),
        mime="application/json",
        key="dl_excalidraw",
    )


def render_excalidraw_generation(result: str, title: str):
    """Render Excalidraw diagram generation UI after analysis."""
    with st.expander("📐 Générer un schéma conceptuel (Excalidraw)", expanded=False):
        st.markdown("Générez un diagramme arborescent des concepts clés de la vidéo, éditable dans [Excalidraw](https://excalidraw.com).")

        gen_btn = st.button("📐 Générer le schéma", type="primary", key="btn_excalidraw")

        if gen_btn:
            with st.status("🧠 Génération du schéma conceptuel…", expanded=True) as status:
                st.write("🤖 Extraction des concepts via IA…")
                selected = st.session_state.get("selected_model", "")
                use_local = st.session_state.get("use_local_llm", False)
                local_model = st.session_state.get("local_llm_model", "llama3.2")
                diag = generate_excalidraw(result, title, api_key=active_api_key(), model=image_llm_model,
                                            use_local=use_local, local_model=local_model, provider="openrouter")

                if diag.get("success"):
                    st.session_state.excalidraw_json = diag["diagram_json"]
                    st.session_state.excalidraw_concepts = diag.get("concepts", [])
                    n = len(diag.get("concepts", []))
                    st.write(f"✅ {n} concepts extraits")
                    st.write("📐 Génération du diagramme…")
                    status.update(label=f"✅ Schéma généré ({n} concepts)", state="complete")
                    _render_excalidraw_download(title)
                    with st.expander("👁️ Aperçu des concepts extraits", expanded=True):
                        for c in diag.get("concepts", []):
                            parent = next(
                                (x["label"] for x in diag.get("concepts", []) if x["id"] == c.get("parent_id")),
                                "─",
                            )
                            st.markdown(f"- **{c['label']}** → parent : *{parent}*")
                else:
                    status.update(label="❌ Échec", state="error")
                    st.error(f"❌ {diag.get('error', 'Erreur inconnue')}")

        if st.session_state.excalidraw_json and not gen_btn:
            n = len(st.session_state.excalidraw_concepts)
            st.success(f"✅ Schéma prêt ({n} concepts) — téléchargez le fichier ci-dessus")
            _render_excalidraw_download(title)


# ──────────────────────────────────────────────────────────────
# Result display
# ──────────────────────────────────────────────────────────────

def _safe_filename(title: str, suffix: str) -> str:
    safe = re.sub(r'[^\w .-]', '', title)
    safe = re.sub(r'\s+', ' ', safe).strip()[:40] or "export"
    return f"{safe}_{suffix}"


def show_result(result: str, title: str):
    st.markdown("---")
    st.markdown(f"## 📝 {title}")

    col_md, col_pdf, col_obs = st.columns(3)
    with col_md:
        try:
            st.download_button(
                label="💾 Markdown",
                data=result or "",
                file_name=_safe_filename(title, "analyse.md"),
                mime="text/markdown",
                key="dl_md_result",
            )
        except Exception as e:
            st.caption(f"Markdown non disponible : {e}")
    with col_pdf:
        try:
            from src.pdf_exporter import export_to_pdf
            pdf_bytes = export_to_pdf(result or "", title or "export")
            st.download_button(
                label="📄 PDF",
                data=pdf_bytes,
                file_name=_safe_filename(title, "analyse.pdf"),
                mime="application/pdf",
                key="dl_pdf_result",
            )
        except Exception as e:
            st.caption(f"PDF non disponible : {e}")
    with col_obs:
        obs_vault = st.session_state.get("obsidian_vault_path", "").strip()
        if obs_vault:
            if st.button("📓 Obsidian", key="btn_export_obsidian", type="secondary",
                         help="Exporter dans le vault Obsidian"):
                from src.obsidian_exporter import export_to_obsidian
                obs_sub = st.session_state.get("obsidian_subfolder", "YouTube").strip() or "YouTube"
                obs_src = st.session_state.get("_last_url", "")
                res = export_to_obsidian(result or "", title or "export", obs_vault,
                                         source_url=obs_src, subfolder=obs_sub)
                if res["success"]:
                    st.success(f"✅ Exporté dans Obsidian : `{res['file_path']}`")
                else:
                    st.error(f"❌ {res['error']}")
        else:
            st.caption("📓 Configurer vault")

    # ── TTS & Drive export ────────────────────────────────────
    col_tts, col_drive = st.columns(2)
    with col_tts:
        tts_label = f"🔊 Lire le résumé ({st.session_state.get('tts_method', 'gTTS')})"
        if st.button(tts_label, key="btn_tts_summary", type="secondary"):
            tts_methods = {m["name"]: m["id"] for m in tts_generator.get_tts_methods()}
            method_id = tts_methods.get(st.session_state.get("tts_method", "gTTS"), "gtts")
            with st.spinner("🔊 Génération audio..."):
                tts_res = tts_generator.generate_tts(result[:3000], method=method_id)
            if tts_res["success"]:
                with open(tts_res["audio_path"], "rb") as f:
                    audio_bytes = f.read()
                st.session_state.last_audio = audio_bytes
                st.audio(audio_bytes, format="audio/mp3")
            else:
                st.error(f"❌ {tts_res['error']}")
        if st.session_state.get("last_audio") and not st.session_state.get("btn_tts_summary", False):
            st.audio(st.session_state.last_audio, format="audio/mp3")

    with col_drive:
        if st.session_state.get("drive_tokens"):
            if st.button("☁️ Tout exporter sur Drive", type="secondary", key="btn_drive_export"):
                tokens = st.session_state.drive_tokens
                access_token = tokens.get("access_token", "")
                files_to_export = []

                # Summary MD
                with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
                    f.write(result)
                    files_to_export.append((f.name, f"{title[:40]}_analyse.md", "text/markdown"))

                # Excalidraw
                if st.session_state.get("excalidraw_json"):
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".excalidraw", delete=False, encoding="utf-8") as f:
                        f.write(st.session_state.excalidraw_json)
                        files_to_export.append((f.name, f"{title[:40]}_schema.excalidraw", "application/json"))

                progress_bar = st.progress(0)
                status_text = st.empty()
                results = []
                for idx, (path, name, mime) in enumerate(files_to_export):
                    status_text.info(f"☁️ Envoi de {name}...")
                    res = drive_exporter.upload_to_drive(path, name, mime, access_token)
                    results.append(res)
                    progress_bar.progress((idx + 1) / len(files_to_export))
                    os.unlink(path)

                success_count = sum(1 for r in results if r["success"])
                if success_count == len(results):
                    st.success(f"✅ {success_count} fichier(s) exporté(s) sur Google Drive !")
                else:
                    for r in results:
                        if not r["success"]:
                            st.warning(f"⚠️ {r.get('file_name', '?')}: {r.get('error', '?')}")
                    if success_count > 0:
                        st.success(f"✅ {success_count}/{len(results)} exporté(s)")
        else:
            st.info("☁️ Configurez Google Drive dans la sidebar pour exporter")

    st.markdown(result)

    # ── Chat / Q&A section ────────────────────────────────────
    transcript = st.session_state.get("current_transcript", "")
    if transcript:
        st.markdown("---")
        st.markdown("### 💬 Poser une question sur la vidéo")
        st.caption("Posez n'importe quelle question sur le contenu de la vidéo. L'IA répondra en se basant sur le transcript.")

        for qa in st.session_state.chat_history:
            st.markdown(f"**🧑 Vous :** {qa['question']}")
            st.markdown(f"**🤖 Assistant :** {qa['answer']}")
            st.markdown("---")

        with st.form("qa_form", clear_on_submit=True):
            question = st.text_input("Votre question", placeholder="Par exemple : Quel est le sujet principal de la vidéo ?", key="qa_input")
            submitted = st.form_submit_button("💬 Demander", type="primary")
            if submitted and question.strip():
                with st.spinner("🤖 Réflexion..."):
                    try:
                        answer = run_qa(question.strip(), transcript)
                        st.session_state.chat_history.append({
                            "question": question.strip(),
                            "answer": answer,
                        })
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {str(e)}")

        if st.session_state.chat_history:
            if st.button("🗑️ Effacer l'historique", key="clear_chat"):
                st.session_state.chat_history = []
                st.rerun()

    # ── Image generation section ──────────────────────────────
    render_image_generation(result, title)

    # ── Video generation section ──────────────────────────────
    render_video_generation(result, title)

    # ── Excalidraw diagram section ─────────────────────────────
    render_excalidraw_generation(result, title)


# ──────────────────────────────────────────────────────────────
# Video selection UI (before processing)
# ──────────────────────────────────────────────────────────────

def render_video_selection(
    videos, title, vtype, url,
    selected_model, chunk_size, overlap,
    force_whisper, whisper_lang, whisper_model_size,
    output_language, cookies_path, max_channel_videos,
    key_in_use, provider, whisper_openai_key,
):
    """Show checkboxes to select which videos to analyse."""
    if not key_in_use:
        st.error("⚠️ Entrez votre clé OpenRouter dans la barre latérale.")
        return

    icon = "📺" if vtype == "channel" else "📋"
    st.markdown(f"### {icon} {title}")
    st.caption(f"{len(videos)} vidéo(s) trouvée(s) — cochez celles à analyser")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("✅ Tout sélectionner", key="sel_all"):
            for i in range(len(videos)):
                st.session_state[f"sel_v_{i}"] = True
            st.rerun()
    with col2:
        if st.button("❌ Tout désélectionner", key="sel_none"):
            for i in range(len(videos)):
                st.session_state[f"sel_v_{i}"] = False
            st.rerun()

    st.markdown("---")
    selected = []
    for i, v in enumerate(videos):
        key = f"sel_v_{i}"
        if key not in st.session_state:
            st.session_state[key] = True
        checked = st.checkbox(v["title"], key=key)
        if checked:
            selected.append(i)

    st.markdown("---")
    n_sel = len(selected)
    st.markdown(f"**{n_sel}/{len(videos)}** vidéo(s) sélectionnée(s)")

    col_a, col_b, col_c = st.columns([1, 1, 6])
    with col_a:
        if n_sel > 0 and st.button(f"🚀 Analyser {n_sel} vidéo(s)", type="primary", key="btn_analyze_sel"):
            selected_videos = [videos[i] for i in selected]
            for i in range(len(videos)):
                st.session_state.pop(f"sel_v_{i}", None)
            st.session_state.video_list = None

            kwargs = dict(
                url=url, model=selected_model,
                chunk_size=chunk_size, overlap=overlap,
                force_whisper=force_whisper,
                whisper_lang=whisper_lang, whisper_model=whisper_model_size,
                output_language=output_language,
                cookies_path=cookies_path,
                videos=selected_videos,
                api_key=key_in_use,
                provider=provider,
                openai_api_key=whisper_openai_key,
            )
            if vtype == "channel":
                kwargs["max_videos"] = max_channel_videos
                kwargs["channel_name"] = title

            fn = process_channel if vtype == "channel" else process_playlist
            _start_analysis_thread(url, fn, **kwargs)
            st.rerun()
    with col_b:
        if st.button("↩️ Nouvelle URL", key="btn_back_url"):
            st.session_state.video_list = None
            st.session_state.pop("url_input", None)
            for i in range(len(videos)):
                st.session_state.pop(f"sel_v_{i}", None)
            st.rerun()
    with col_c:
        st.caption("Les résultats seront combinés en un rapport unique, exportable sur Drive.")


# ──────────────────────────────────────────────────────────────
# Processing UI — polling loop (replaces tabs while a thread runs)
# ──────────────────────────────────────────────────────────────

def render_processing_ui():
    """Show progress bar + cancel button. Poll the result queue and rerun until done."""
    st.markdown("---")
    prog, msg = _get_progress()

    st.progress(prog / 100)
    st.markdown(f"<h3 style='text-align: center; color: #FF4B4B;'>{msg}</h3>", unsafe_allow_html=True)

    # Show chunk progress if available
    if "chunk" in msg.lower():
        try:
            import re
            match = re.search(r'chunk (\d+)/(\d+)', msg.lower())
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                st.caption(f"Progression des chunks : {current}/{total}")
                st.progress(current / total)
        except Exception:
            pass

    if st.button("🛑 Annuler l'analyse", type="secondary"):
        cancel_ev = st.session_state._cancel_event
        if cancel_ev:
            cancel_ev.set()
        _set_progress(0, "⏳ Annulation en cours (fin de la requête courante)...")

    q: queue.Queue | None = st.session_state._result_queue
    if q is not None:
        try:
            data = q.get_nowait()
            status = data[0]

            st.session_state.is_processing = False
            _set_progress(0, "")

            if status == "ok":
                _, result, title, warnings, transcript_text = data
                for w in warnings:
                    st.warning(w)
                st.session_state.analysis_result = result
                st.session_state.current_title = title
                st.session_state.current_transcript = transcript_text
                st.session_state._last_url = st.session_state._processing_source
                st.session_state.chat_history = []
                st.session_state.generated_image_url = ""
                st.session_state.excalidraw_json = ""
                st.session_state.excalidraw_concepts = []
                add_to_history(title, st.session_state._processing_source, result)
            elif status == "cancelled":
                st.info("ℹ️ Analyse annulée.")
                st.session_state.analysis_result = None
            else:
                _, error_msg, _, _, _ = data
                st.error(f"❌ {error_msg}")
                st.session_state.analysis_result = None

            st.rerun()
            return
        except queue.Empty:
            pass

    # Still running — poll again in 300 ms
    time.sleep(0.3)
    st.rerun()


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def _inject_pwa():
    st.markdown(
        '<script>if("serviceWorker" in navigator){navigator.serviceWorker.register("/pwa/sw.js")}</script>',
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(
        page_title="YouTube Summarizer",
        page_icon="📺",
        layout="wide",
    )

    _inject_pwa()
    init_session_state()

    # ── Client-side key persistence ──
    from src.key_store import inject_persistence_script, handle_loaded_keys, save_keys_to_localstorage, collect_provider_keys
    inject_persistence_script()
    handle_loaded_keys()

    if not check_password():
        return

    st.title("📺 YouTube Summarizer")
    st.markdown("Résumez n'importe quelle vidéo — YouTube, Twitch, Vimeo, ou n'importe quelle source audio/vidéo.")

    # ── Sidebar ──────────────────────────────────────────────
    st.sidebar.header("⚙️ Configuration")

    # ── LLM Provider selector ──
    st.sidebar.markdown("### 🔌 Provider LLM")
    provider_label = st.sidebar.selectbox(
        "Fournisseur LLM",
        options=["OpenRouter", "OpenCode Go"],
        index=0,
        key="llm_provider_label",
        label_visibility="collapsed",
    )
    llm_provider = "opencode-go" if provider_label == "OpenCode Go" else "openrouter"
    st.session_state["llm_provider"] = llm_provider

    # ── Always show both key inputs ──
    # OpenRouter key
    st.sidebar.markdown("### 🔑 Clé OpenRouter")
    col_or_key, col_or_save = st.sidebar.columns([3, 1])
    with col_or_key:
        custom_key = st.text_input(
            "OpenRouter key",
            type="password",
            placeholder="sk-or-v1-...",
            help="Laissez vide pour utiliser la clé par défaut. Obtenez une clé gratuite sur openrouter.ai",
            key="custom_api_key",
            label_visibility="collapsed",
        )
    with col_or_save:
        st.write("")
        if st.button("💾", key="save_openrouter", help="Sauvegarder dans .env"):
            if custom_key:
                _save_key_to_env("OPENROUTER_API_KEY", custom_key)
                st.success("✅", icon="💾")
            else:
                st.error("Entrez une clé")

    # OpenCode Go key
    st.sidebar.markdown("### 🔑 Clé OpenCode Go")
    col_go_key, col_go_save = st.sidebar.columns([3, 1])
    with col_go_key:
        go_key = st.text_input(
            "OpenCode Go key",
            type="password",
            placeholder="opencode-go-...",
            help="Obtenez votre clé sur opencode.ai/auth (Go: $5/mois premier mois à $5).",
            key="custom_go_api_key",
            label_visibility="collapsed",
        )
    with col_go_save:
        st.write("")
        if st.button("💾", key="save_opencode_go", help="Sauvegarder dans .env"):
            if go_key:
                _save_key_to_env("OPENCODE_GO_API_KEY", go_key)
                st.success("✅", icon="💾")
            else:
                st.error("Entrez une clé")

    # ── Active key indicator ──
    if llm_provider == "openrouter":
        key_in_use = custom_key or config.OPENROUTER_API_KEY
        if custom_key:
            st.sidebar.success("✅ OpenRouter actif — votre clé personnelle")
        elif config.OPENROUTER_API_KEY:
            st.sidebar.info("ℹ️ OpenRouter actif — clé .env")
        else:
            st.sidebar.error("⚠️ Aucune clé OpenRouter")
    else:
        key_in_use = go_key or config.OPENCODE_GO_API_KEY
        if go_key:
            st.sidebar.success("✅ OpenCode Go actif — votre clé")
        elif config.OPENCODE_GO_API_KEY:
            st.sidebar.info("ℹ️ OpenCode Go actif — clé .env")
        else:
            st.sidebar.error("⚠️ Aucune clé OpenCode Go")

    # ── Client-side key persistence ──
    with st.sidebar.expander("💾 Persistance locale", expanded=False):
        st.caption("Sauvegardez vos clés API sur cet appareil (navigateur). Elles seront restaurées automatiquement à chaque visite.")
        from src.key_store import save_keys_to_localstorage, collect_provider_keys, export_keys_json, import_keys_from_json, apply_imported_keys
        if st.button("💾 Sauvegarder sur cet appareil", key="btn_save_keys", help="Sauvegarder toutes les clés saisies dans le navigateur"):
            keys = collect_provider_keys()
            if keys:
                save_keys_to_localstorage(keys)
                st.success(f"✅ {len(keys)} clé(s) sauvegardée(s) sur cet appareil", icon="💾")
            else:
                st.warning("Aucune clé à sauvegarder")

        st.markdown("---")
        st.caption("Transférez vos clés entre appareils :")
        col_e, col_i = st.columns(2)
        with col_e:
            keys_json = export_keys_json()
            st.download_button(
                "📤 Exporter",
                data=keys_json,
                file_name="youtube_summarizer_keys.json",
                mime="application/json",
                key="btn_export_keys",
                help="Télécharge un fichier JSON avec vos clés. Gardez-le en lieu sûr.",
            )
        with col_i:
            uploaded = st.file_uploader(
                "📥 Importer",
                type=["json"],
                key="import_keys_file",
                label_visibility="collapsed",
            )
            if uploaded:
                try:
                    imported = import_keys_from_json(uploaded.read().decode("utf-8"))
                    if imported:
                        apply_imported_keys(imported)
                        st.success(f"✅ {len(imported)} clé(s) importée(s) et sauvegardée(s)", icon="📥")
                        st.rerun()
                    else:
                        st.warning("Aucune clé valide dans le fichier")
                except Exception as e:
                    st.error(f"❌ Fichier invalide : {e}")

    with st.sidebar.expander("🔌 Providers images", expanded=False):
        st.caption("Clés API pour les providers d'image externes (optionnel). Laissez vide pour utiliser la clé OpenRouter.")
        for pid in ["stability-ai", "replicate", "pruna"]:
            label = {"stability-ai": "Stability AI", "replicate": "Replicate", "pruna": "Pruna AI"}[pid]
            placeholder = {"stability-ai": "sk-...", "replicate": "r8_...", "pruna": "Clé Pruna"}[pid]
            col_pk, col_ps = st.columns([3, 1])
            with col_pk:
                st.text_input(
                    f"{label}",
                    type="password",
                    placeholder=placeholder,
                    key=f"provider_key_{pid}",
                    label_visibility="collapsed",
                )
            with col_ps:
                st.write("")
                env_key = {"stability-ai": "STABILITY_API_KEY", "replicate": "REPLICATE_API_KEY", "pruna": "PRUNA_API_KEY"}[pid]
                if st.button("💾", key=f"save_{pid}", help="Sauvegarder dans .env"):
                    val = st.session_state.get(f"provider_key_{pid}", "")
                    if val:
                        _save_key_to_env(env_key, val)

    st.sidebar.markdown("---")
    with st.sidebar.expander("🎬 Génération vidéo", expanded=False):
        st.caption("Générez une courte vidéo à partir du résumé. Nécessite une clé Replicate.")
        video_providers = get_video_providers_list()
        vp_options = {f"{p['icon']} {p['name']}": p['id'] for p in video_providers}
        selected_vp_label = st.selectbox(
            "Provider vidéo",
            options=list(vp_options.keys()),
            index=0,
            key="video_provider",
            label_visibility="collapsed",
        )
        st.session_state["selected_video_provider"] = vp_options[selected_vp_label]
        st.session_state["selected_video_model"] = st.selectbox(
            "Modèle",
            options=next(
                (p['models'] for p in video_providers if p['id'] == vp_options[selected_vp_label]),
                [],
            ),
            key="video_model",
            label_visibility="collapsed",
        )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🤖 Modèle")

    if llm_provider == "opencode-go":
        model_map = fetch_open_code_go_models()
        available_models = sorted(model_map.keys())
        st.sidebar.caption(f"⚡ {len(model_map)} modèles OpenCode Go disponibles")
        default_model = "deepseek-v4-flash"
        default_idx = available_models.index(default_model) if default_model in available_models else 0
    else:
        show_all_models = st.sidebar.toggle("Afficher tous les modèles", value=False,
                                            help="Par défaut seuls les modèles gratuits sont affichés.")
        if show_all_models:
            model_map = _cached_all_models()
            st.sidebar.caption(f"{len(model_map)} modèles disponibles (gratuits + payants)")
        else:
            model_map = _cached_free_models()
            st.sidebar.caption(f"✅ {len(model_map)} modèles **gratuits** disponibles")
        available_models = sorted(model_map.keys())
        default_model = config.DEFAULT_MODEL
        default_idx = available_models.index(default_model) if default_model in available_models else 0

    selected_model = st.sidebar.selectbox("Modèle LLM texte", options=available_models, index=default_idx)
    st.session_state["selected_model"] = selected_model

    ctx_limit = model_map.get(selected_model, config.get_model_context_limit(selected_model))
    chunk_size = st.sidebar.number_input(
        "Tokens par chunk",
        min_value=1000, max_value=ctx_limit - 4000,
        value=config.CHUNK_SIZE_TOKENS, step=1000,
    )
    overlap = st.sidebar.number_input(
        "Chevauchement (tokens)",
        min_value=100, max_value=chunk_size // 2,
        value=min(chunk_size // 10, config.CHUNK_OVERLAP_TOKENS), step=100,
    )

    # ── Image/Excalidraw LLM model (always uses OpenRouter) ──
    image_models = _cached_free_models()
    image_model_names = sorted(image_models.keys())
    img_default = "meta-llama/llama-3.3-70b-instruct:free"
    img_default_idx = image_model_names.index(img_default) if img_default in image_model_names else 0
    image_llm_model = st.sidebar.selectbox(
        "Modèle LLM image/excalidraw",
        options=image_model_names,
        index=img_default_idx,
        key="image_llm_model",
        help="Modèle OpenRouter utilisé pour générer les prompts d'image, diagrammes Excalidraw, etc.",
    )

    st.sidebar.markdown("---")
    with st.sidebar.expander("🧠 Local LLM (Ollama)", expanded=False):
        use_local_llm = st.checkbox("Utiliser Ollama", value=False, key="use_local_llm",
                                    help="Utilise un modèle local via Ollama au lieu d'OpenRouter.")
        ollama_status = local_llm.check_ollama()
        if use_local_llm:
            if ollama_status["available"]:
                st.success(f"✅ Ollama connecté — {len(ollama_status['models'])} modèle(s) dispo(s)")
                local_model = st.selectbox("Modèle local", options=ollama_status["models"] or ["llama3.2"],
                                           key="local_llm_model")
            else:
                st.error(f"❌ Ollama: {ollama_status['error']}")
                st.info("💡 Lancez 'ollama serve' dans un terminal après avoir installé Ollama (ollama.com)")
                st.session_state.use_local_llm = False

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🌐 Langue du résumé")
    LANGUAGE_OPTIONS = {
        "🇫🇷 Français": "Français",
        "🇬🇧 English": "English",
        "🇪🇸 Español": "Español",
        "🇩🇪 Deutsch": "Deutsch",
        "🇵🇹 Português": "Português",
        "🇮🇹 Italiano": "Italiano",
    }
    selected_lang_label = st.sidebar.selectbox(
        "Langue de sortie",
        options=list(LANGUAGE_OPTIONS.keys()),
        index=0,
        help="Langue dans laquelle le résumé sera généré (indépendante de la langue de la vidéo).",
    )
    output_language = LANGUAGE_OPTIONS[selected_lang_label]

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🍪 Cookies YouTube")
    server_cookies = _server_cookies_path()
    if server_cookies:
        st.sidebar.success("✅ Cookies configurés (serveur)", icon="🔒")
        st.sidebar.caption("Les cookies du serveur sont utilisés automatiquement.")
    else:
        st.sidebar.caption(
            "Si YouTube bloque (erreur 403), importez votre cookies.txt. "
            "Ou configurez YOUTUBE_COOKIES dans les secrets Streamlit pour tous les utilisateurs."
        )
    cookies_file = st.sidebar.file_uploader(
        "cookies.txt personnel (optionnel)",
        type=["txt"],
        label_visibility="collapsed",
        help="Exportez vos cookies YouTube avec l'extension 'Get cookies.txt LOCALLY' sur Chrome/Firefox.",
    )
    cookies_path = resolve_cookies_path(cookies_file)
    if cookies_file:
        st.sidebar.success("✅ Vos cookies personnels sont utilisés")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎙️ Whisper")

    whisper_openai_key = st.sidebar.text_input(
        "Clé OpenAI (Whisper API)",
        type="password",
        placeholder="sk-... (optionnel)",
        help="Clé OpenAI pour utiliser l'API Whisper (plus rapide). Sans clé, utilise OpenRouter ou Whisper local.",
        key="whisper_openai_key",
        label_visibility="collapsed",
    )
    if whisper_openai_key:
        st.sidebar.caption("✅ Clé OpenAI Whisper configurée")

    force_whisper = st.sidebar.checkbox(
        "Forcer Whisper",
        value=False,
        help="Ignore les sous-titres existants et transcrit l'audio directement.",
    )
    whisper_lang = st.sidebar.selectbox(
        "Langue audio",
        options=["auto", "fr", "en", "es", "de", "it", "pt", "ja", "zh", "ar", "nl", "pl", "ru"],
        index=0,
    )
    whisper_model_size = st.sidebar.selectbox(
        "Modèle Whisper local",
        options=["tiny", "base", "small", "medium", "large"],
        index=1,
        help="tiny = rapide, large = précis.",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📺 Analyse de chaîne")
    max_channel_videos = st.sidebar.number_input(
        "Max vidéos par chaîne",
        min_value=1, max_value=200,
        value=50, step=5,
        help="Nombre maximum de vidéos à analyser lors du scraping d'une chaîne YouTube.",
    )

    free_tag = " 🆓" if selected_model.endswith(":free") else ""
    admin_tag = f" (OpenCode Go)" if llm_provider == "opencode-go" else ""
    st.sidebar.markdown(f"**Contexte :** {ctx_limit:,} tokens{free_tag}{admin_tag}")

    st.sidebar.markdown("---")
    with st.sidebar.expander("☁️ Google Drive", expanded=False):
        st.caption("Sauvegardez vos exports directement sur Google Drive.")
        drive_client_id = st.text_input("Google Client ID", type="password",
                                         placeholder="votre-id.apps.googleusercontent.com",
                                         key="drive_client_id")
        drive_client_secret = st.text_input("Client Secret", type="password",
                                             placeholder="GOCSPX-...",
                                             key="drive_client_secret")
        if st.session_state.get("drive_tokens"):
            st.success("✅ Connecté à Google Drive")
            if st.button("Déconnecter", key="btn_drive_disconnect"):
                st.session_state.drive_tokens = None
                st.session_state.drive_folder_id = None
                st.rerun()
        elif drive_client_id and drive_client_secret:
            auth_url = drive_exporter.get_google_auth_url(
                drive_client_id, "http://localhost:8501"
            )
            st.markdown(f"1. [🔗 Autoriser l'accès Google]({auth_url})")
            st.markdown("2. Collez le code de redirection ci-dessous :")
            auth_code = st.text_input("Code d'autorisation", key="drive_auth_code", label_visibility="collapsed")
            if auth_code:
                result = drive_exporter.exchange_code_for_token(
                    drive_client_id, drive_client_secret, auth_code, "http://localhost:8501"
                )
                if result["success"]:
                    st.session_state.drive_tokens = result["tokens"]
                    st.success("✅ Connecté !")
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")
        else:
            st.info("Entrez votre Google Client ID pour activer Drive.")
            st.caption("Créez un projet sur console.cloud.google.com, activez Drive API, "
                       "créez un OAuth 2.0 Client ID de type 'Web application' "
                       "avec redirect URI http://localhost:8501")

    st.sidebar.markdown("---")
    with st.sidebar.expander("📓 Obsidian", expanded=False):
        st.caption("Exportez vos analyses directement dans votre vault Obsidian en Markdown.")
        from src.obsidian_exporter import find_vaults
        vaults = find_vaults()
        if vaults:
            vault_options = {v["name"]: v["path"] for v in vaults}
            vault_options["— Chemin personnalisé —"] = ""
            sel = st.selectbox("Vault détecté", options=list(vault_options.keys()), key="obsidian_vault_sel")
            if sel != "— Chemin personnalisé —":
                st.session_state.obsidian_vault_path = vault_options[sel]
            else:
                st.session_state.obsidian_vault_path = ""
        else:
            st.caption("Aucun vault détecté automatiquement.")
        st.text_input("Chemin du vault", value=st.session_state.get("obsidian_vault_path", ""),
                       placeholder="/Users/moi/Documents/Obsidian/MonVault",
                       key="obsidian_vault_path", label_visibility="collapsed",
                       help="Chemin absolu vers le dossier racine de votre vault Obsidian.")
        st.text_input("Sous-dossier (optionnel)", value="YouTube", key="obsidian_subfolder",
                       placeholder="YouTube", label_visibility="collapsed",
                       help="Dossier dans le vault où sauvegarder les analyses.")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔊 Synthèse vocale")
    tts_methods = tts_generator.get_tts_methods()
    tts_options = {m["name"]: m["id"] for m in tts_methods}
    st.sidebar.selectbox("Méthode TTS", options=list(tts_options.keys()), index=0,
                          key="tts_method", help="gTTS : cloud gratuit. Moshi : local GPU lourd.")
    if st.sidebar.button("🔊 Tester", key="btn_tts_test", type="secondary"):
        with st.spinner("Génération audio..."):
            method_id = tts_options[st.session_state.tts_method]
            result = tts_generator.generate_tts("Bonjour, ceci est un test de synthèse vocale.", method=method_id)
            if result["success"]:
                with open(result["audio_path"], "rb") as f:
                    st.sidebar.audio(f.read(), format="audio/mp3")
            else:
                st.sidebar.error(result["error"])

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"### 🔄 Mise à jour")
    st.sidebar.caption(f"Version actuelle : **{config.APP_VERSION}**")
    if st.sidebar.button("🔍 Vérifier les mises à jour", key="btn_check_update", use_container_width=True):
        with st.spinner("Vérification..."):
            info = updater.check_update()
        if info.error:
            st.sidebar.error(info.error)
        elif info.available:
            st.sidebar.success(f"Nouvelle version disponible : **{info.latest_version}**")
            with st.sidebar.expander("📝 Notes de version", expanded=False):
                st.text(info.release_notes[:800] + ("..." if len(info.release_notes) > 800 else ""))
            mode = updater.detect_install_mode()
            if mode == "git":
                if st.sidebar.button("⬇️ Mettre à jour (git pull)", key="btn_do_update", use_container_width=True):
                    with st.spinner("Mise à jour en cours..."):
                        ok = updater.perform_git_pull()
                    if ok:
                        st.sidebar.success("✅ Mise à jour terminée ! Redémarrez l'app.")
                        st.cache_data.clear()
                    else:
                        st.sidebar.error("❌ La mise à jour a échoué")
            elif mode == "desktop":
                st.sidebar.info(f"Téléchargez la dernière version :\n{info.release_url}")
            elif mode == "docker":
                if st.sidebar.button("⬇️ Pull Docker", key="btn_docker_update", use_container_width=True):
                    with st.spinner("Pull de l'image Docker..."):
                        ok = updater.perform_docker_pull()
                    if ok:
                        st.sidebar.success("✅ Image mise à jour. Redémarrez : `docker compose up -d`")
                    else:
                        st.sidebar.error("❌ Échec du pull Docker")
            else:
                st.sidebar.markdown(f"Téléchargez la dernière version : [GitHub]({info.release_url})")
        else:
            st.sidebar.info("✅ Vous êtes à jour !")

    if st.session_state.history:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📚 Historique")
        for i, entry in enumerate(st.session_state.history):
            label = f"{entry['timestamp']} — {entry['title'][:22]}"
            with st.sidebar.expander(label):
                st.caption(entry["source"])
                if st.button("Recharger", key=f"reload_{i}"):
                    st.session_state.analysis_result = entry["result"]
                    st.session_state.current_title = entry["title"]
                    st.rerun()

    # ── Processing UI (shown while background thread runs) ───
    if st.session_state.is_processing:
        render_processing_ui()
        return

    # ── Video selection UI ───────────────────────────────────
    if st.session_state.get("video_list"):
        render_video_selection(
            st.session_state.video_list,
            st.session_state.video_list_title,
            st.session_state.video_list_type,
            st.session_state.video_list_url,
            selected_model, chunk_size, overlap,
            force_whisper, whisper_lang, whisper_model_size,
            output_language, cookies_path, max_channel_videos,
            key_in_use, llm_provider, whisper_openai_key,
        )
        return

    # ── Tabs ─────────────────────────────────────────────────
    tab_url, tab_local = st.tabs(["🔗 URL Vidéo", "📁 Fichier Local"])

    # ── Tab 1 : URL ──────────────────────────────────────────
    with tab_url:
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            url_input = st.text_input(
                "URL de la vidéo",
                placeholder="https://www.youtube.com/watch?v=...  |  Chaîne YouTube (@...)  |  Twitch  |  Vimeo  |  ...",
                key="url_input",
            )
        with col_btn:
            st.write("")
            st.write("")
            analyze_url_btn = st.button("🚀 Analyser", type="primary", key="btn_url")

        platforms = extractor.get_supported_platforms()
        native_str = " · ".join(f"{p['icon']} {p['name']}" for p in platforms)
        st.caption(
            f"Transcript natif : {native_str}   |   "
            "Whisper (yt-dlp) : YouTube, Twitch, Vimeo, TikTok, Twitter/X, Instagram, SoundCloud… et 1 000+ autres."
        )

        if analyze_url_btn and url_input:
            if not key_in_use:
                st.error("⚠️ Entrez votre clé OpenRouter dans la barre latérale.")
            elif extractor.detect_channel(url_input):
                with st.spinner("📋 Récupération des vidéos de la chaîne..."):
                    try:
                        videos, channel_name = extractor.get_channel_videos(
                            url_input, cookies_path=cookies_path, max_videos=max_channel_videos,
                        )
                    except Exception as e:
                        st.error(f"❌ {e}")
                        st.stop()
                st.session_state.video_list = videos
                st.session_state.video_list_title = channel_name
                st.session_state.video_list_type = "channel"
                st.session_state.video_list_url = url_input
                st.rerun()
            elif extractor.detect_playlist(url_input):
                with st.spinner("📋 Récupération des vidéos de la playlist..."):
                    try:
                        videos = extractor.get_playlist_videos(url_input, cookies_path=cookies_path)
                    except Exception as e:
                        st.error(f"❌ {e}")
                        st.stop()
                st.session_state.video_list = videos
                st.session_state.video_list_title = "Playlist"
                st.session_state.video_list_type = "playlist"
                st.session_state.video_list_url = url_input
                st.rerun()
            else:
                is_valid, _ = extractor.validate_url(url_input)
                need_whisper = force_whisper or not is_valid

                if not is_valid and not force_whisper:
                    st.info("Plateforme non reconnue pour le transcript natif — tentative via Whisper + yt-dlp...")

                _start_analysis_thread(
                    url_input,
                    process_url,
                    url_input, selected_model, chunk_size, overlap,
                    need_whisper, whisper_lang, whisper_model_size,
                    output_language, cookies_path,
                    api_key=key_in_use,
                    provider=llm_provider,
                    openai_api_key=whisper_openai_key,
                )
                st.rerun()

    # ── Tab 2 : Local File ───────────────────────────────────
    with tab_local:
        st.markdown(
            "Importez un fichier audio ou vidéo depuis votre ordinateur. "
            "Il sera transcrit avec Whisper puis analysé."
        )

        uploaded_file = st.file_uploader(
            "Fichier audio ou vidéo",
            type=["mp3", "mp4", "wav", "m4a", "ogg", "flac", "webm", "mkv", "avi", "mov"],
            label_visibility="collapsed",
        )

        analyze_local_btn = st.button(
            "🚀 Transcrire & Analyser", type="primary", key="btn_local",
            disabled=uploaded_file is None,
        )

        if analyze_local_btn and uploaded_file:
            if not key_in_use:
                st.error("⚠️ Entrez votre clé OpenRouter dans la barre latérale.")
            else:
                file_bytes = uploaded_file.read()
                _start_analysis_thread(
                    uploaded_file.name,
                    process_local_file,
                    file_bytes, uploaded_file.name,
                    selected_model, chunk_size, overlap,
                    whisper_lang, whisper_model_size,
                    output_language,
                    api_key=key_in_use,
                    provider=llm_provider,
                    openai_api_key=whisper_openai_key,
                )
                st.rerun()

    # ── Result ───────────────────────────────────────────────
    if st.session_state.analysis_result:
        show_result(st.session_state.analysis_result, st.session_state.current_title)


if __name__ == "__main__":
    main()
