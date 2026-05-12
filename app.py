"""
YouTube Summarizer — Streamlit Web Interface
Supports: YouTube, Twitch, Vimeo (transcript), any platform via Whisper, local audio/video files.
"""

import streamlit as st
import config
from src import extractor, chunker, analyzer, fusion
from src.models import fetch_free_models, fetch_all_models
import time
from datetime import datetime


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_free_models() -> dict:
    return fetch_free_models()


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_all_models() -> dict:
    return fetch_all_models()

st.set_page_config(
    page_title="YouTube Summarizer",
    page_icon="📺",
    layout="wide",
)


# ──────────────────────────────────────────────────────────────
# Password protection
# ──────────────────────────────────────────────────────────────

def check_password() -> bool:
    """Show login screen if APP_PASSWORD is set. Returns True when access is granted."""
    app_password = config._get("APP_PASSWORD", "")

    if not app_password:
        return True  # No password configured → open access

    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        "<h1 style='text-align:center;margin-top:80px'>📺 YouTube Summarizer</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;color:gray'>Entrez le mot de passe pour accéder à l'application</p>",
        unsafe_allow_html=True,
    )

    col = st.columns([1, 2, 1])[1]
    with col:
        pwd = st.text_input("Mot de passe", type="password", label_visibility="collapsed",
                            placeholder="Mot de passe...")
        if st.button("Accéder →", type="primary", use_container_width=True):
            if pwd == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")

    return False


# ──────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────

def init_session_state():
    defaults = {
        "analysis_result": None,
        "current_title": "",
        "is_processing": False,
        "history": [],
        "authenticated": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def active_api_key() -> str:
    """Return the user's custom key if set, otherwise the default from config/secrets."""
    return st.session_state.get("custom_api_key", "") or config.OPENROUTER_API_KEY


# ──────────────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────────────

def run_pipeline(transcript: list, video_title: str, model: str, chunk_size: int, overlap: int, output_language: str = "Français") -> str:
    """Chunk → Analyze → Fuse."""
    api_key = active_api_key()
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        status_text.text("✂️ Découpage en chunks...")
        chunks = chunker.chunk_transcript(transcript, max_tokens=chunk_size, overlap_tokens=overlap, model=model)
        status_text.text(chunker.get_chunk_count_info(chunks))
        progress_bar.progress(20)

        analyses = []
        for i, chunk in enumerate(chunks):
            status_text.text(f"🤖 Analyse chunk {i + 1}/{len(chunks)}...")
            progress_bar.progress(20 + 70 * (i + 1) // len(chunks))
            analyses.append(analyzer.analyze_chunk(chunk["text"], video_title, model=model, api_key=api_key, output_language=output_language))
            if len(chunks) > 1:
                time.sleep(1)

        final_analysis = analyses[0]
        if len(analyses) > 1:
            status_text.text("🔗 Fusion des analyses...")
            progress_bar.progress(95)
            final_analysis = fusion.fusion_analyses(analyses, video_title, model, api_key=api_key, output_language=output_language)

        progress_bar.progress(100)
        status_text.text("✅ Terminé !")
        return final_analysis

    except Exception as e:
        progress_bar.progress(0)
        status_text.text(f"❌ Erreur : {e}")
        raise


def process_url(
    url: str, model: str, chunk_size: int, overlap: int,
    force_whisper: bool, whisper_lang: str, whisper_model: str,
    output_language: str = "Français",
) -> tuple[str, str]:
    """Fetch transcript (or Whisper fallback) then run pipeline."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    transcript_data = None

    if not force_whisper:
        try:
            status_text.text("📥 Extraction du transcript...")
            progress_bar.progress(10)
            transcript_data = extractor.get_transcript(url)
            if not transcript_data.get("transcript"):
                warning = transcript_data.get("warning", "Aucun transcript disponible")
                st.warning(f"⚠️ {warning} — passage en mode Whisper...")
                transcript_data = None
        except Exception as e:
            st.warning(f"⚠️ Transcript indisponible ({e}) — passage en mode Whisper...")

    if transcript_data is None:
        from src.whisper_transcriber import transcribe_url
        status_text.text("🎙️ Téléchargement audio + transcription Whisper...")
        progress_bar.progress(10)
        transcript_data = transcribe_url(
            url,
            language=whisper_lang if whisper_lang != "auto" else None,
            model_size=whisper_model,
        )
        progress_bar.progress(28)

    transcript = transcript_data["transcript"]
    title = transcript_data.get("title", "Video")
    duration = transcript_data.get("total_duration_minutes", 0)
    method = transcript_data.get("method", "transcript")
    method_label = "Whisper" if "whisper" in method else "transcript"

    status_text.text(f"📺 {title} — {duration:.1f} min — {len(transcript)} segments ({method_label})")
    progress_bar.progress(30)
    time.sleep(0.4)

    result = run_pipeline(transcript, title, model, chunk_size, overlap, output_language=output_language)
    return result, title


def process_local_file(
    file_bytes: bytes, filename: str, model: str, chunk_size: int, overlap: int,
    whisper_lang: str, whisper_model: str, output_language: str = "Français",
) -> tuple[str, str]:
    """Transcribe local audio/video file then run pipeline."""
    from src.whisper_transcriber import transcribe_local_file

    progress_bar = st.progress(0)
    status_text = st.empty()

    status_text.text(f"🎙️ Transcription de {filename} avec Whisper...")
    progress_bar.progress(10)

    transcript_data = transcribe_local_file(
        file_bytes, filename,
        language=whisper_lang if whisper_lang != "auto" else None,
        model_size=whisper_model,
    )

    transcript = transcript_data["transcript"]
    title = transcript_data.get("title", filename)
    duration = transcript_data.get("total_duration_minutes", 0)

    status_text.text(f"✅ {title} — {duration:.1f} min — {len(transcript)} segments")
    progress_bar.progress(30)
    time.sleep(0.4)

    result = run_pipeline(transcript, title, model, chunk_size, overlap, output_language=output_language)
    return result, title


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
# Result display
# ──────────────────────────────────────────────────────────────

def show_result(result: str, title: str):
    st.markdown("---")
    st.markdown(f"## 📝 {title}")

    col_md, col_pdf = st.columns(2)
    with col_md:
        st.download_button(
            label="💾 Télécharger Markdown",
            data=result,
            file_name=f"{title[:40]}_analyse.md",
            mime="text/markdown",
        )
    with col_pdf:
        try:
            from src.pdf_exporter import export_to_pdf
            pdf_bytes = export_to_pdf(result, title)
            st.download_button(
                label="📄 Télécharger PDF",
                data=pdf_bytes,
                file_name=f"{title[:40]}_analyse.pdf",
                mime="application/pdf",
            )
        except Exception as e:
            st.caption(f"PDF non disponible : {e}")

    st.markdown(result)


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    init_session_state()

    if not check_password():
        return

    st.title("📺 YouTube Summarizer")
    st.markdown("Résumez n'importe quelle vidéo — YouTube, Twitch, Vimeo, ou n'importe quelle source audio/vidéo.")

    # ── Sidebar ──────────────────────────────────────────────
    st.sidebar.header("⚙️ Configuration")

    # Custom OpenRouter API key
    st.sidebar.markdown("### 🔑 Clé API OpenRouter")
    custom_key = st.sidebar.text_input(
        "Votre clé OpenRouter (optionnel)",
        type="password",
        placeholder="sk-or-v1-...",
        help="Laissez vide pour utiliser la clé par défaut. Obtenez une clé gratuite sur openrouter.ai",
        key="custom_api_key",
    )

    key_in_use = custom_key or config.OPENROUTER_API_KEY
    if custom_key:
        st.sidebar.success("Votre clé personnelle est utilisée")
    elif config.OPENROUTER_API_KEY:
        st.sidebar.info("Clé par défaut utilisée")
    else:
        st.sidebar.error("Aucune clé API — entrez la vôtre ci-dessus")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🤖 Modèle")

    show_all_models = st.sidebar.toggle("Afficher tous les modèles", value=False,
                                        help="Par défaut seuls les modèles gratuits sont affichés.")

    if show_all_models:
        model_map = _cached_all_models()
        st.sidebar.caption(f"{len(model_map)} modèles disponibles (gratuits + payants)")
    else:
        model_map = _cached_free_models()
        st.sidebar.caption(f"✅ {len(model_map)} modèles **gratuits** disponibles")

    available_models = sorted(model_map.keys())
    # Prefer llama-3.3-70b:free as default when present
    default_model = config.DEFAULT_MODEL
    default_idx = available_models.index(default_model) if default_model in available_models else 0

    selected_model = st.sidebar.selectbox("Modèle LLM", options=available_models, index=default_idx)

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
    st.sidebar.markdown("### 🎙️ Whisper")

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

    free_tag = " 🆓" if selected_model.endswith(":free") else ""
    st.sidebar.markdown(f"**Contexte :** {ctx_limit:,} tokens{free_tag}")

    # History
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

    # ── Tabs ─────────────────────────────────────────────────
    tab_url, tab_local = st.tabs(["🔗 URL Vidéo", "📁 Fichier Local"])

    # ── Tab 1 : URL ──────────────────────────────────────────
    with tab_url:
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            url_input = st.text_input(
                "URL de la vidéo",
                placeholder="https://www.youtube.com/watch?v=...  |  Twitch  |  Vimeo  |  ...",
                key="url_input",
            )
        with col_btn:
            st.write("")
            st.write("")
            analyze_url_btn = st.button(
                "🚀 Analyser", type="primary", key="btn_url",
                disabled=st.session_state.is_processing,
            )

        platforms = extractor.get_supported_platforms()
        native_str = " · ".join(f"{p['icon']} {p['name']}" for p in platforms)
        st.caption(
            f"Transcript natif : {native_str}   |   "
            "Whisper (yt-dlp) : YouTube, Twitch, Vimeo, TikTok, Twitter/X, Instagram, SoundCloud… et 1 000+ autres."
        )

        if analyze_url_btn and url_input:
            if not key_in_use:
                st.error("⚠️ Entrez votre clé OpenRouter dans la barre latérale.")
            else:
                is_valid, _ = extractor.validate_url(url_input)
                need_whisper = force_whisper or not is_valid

                if not is_valid and not force_whisper:
                    st.info("Plateforme non reconnue pour le transcript natif — tentative via Whisper + yt-dlp...")

                st.session_state.is_processing = True
                try:
                    result, title = process_url(
                        url_input, selected_model, chunk_size, overlap,
                        force_whisper=need_whisper,
                        whisper_lang=whisper_lang, whisper_model=whisper_model_size,
                        output_language=output_language,
                    )
                    st.session_state.analysis_result = result
                    st.session_state.current_title = title
                    add_to_history(title, url_input, result)
                except Exception as e:
                    st.error(f"❌ {e}")
                    st.session_state.analysis_result = None
                finally:
                    st.session_state.is_processing = False

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
            disabled=st.session_state.is_processing or uploaded_file is None,
        )

        if analyze_local_btn and uploaded_file:
            if not key_in_use:
                st.error("⚠️ Entrez votre clé OpenRouter dans la barre latérale.")
            else:
                st.session_state.is_processing = True
                try:
                    file_bytes = uploaded_file.read()
                    result, title = process_local_file(
                        file_bytes, uploaded_file.name, selected_model, chunk_size, overlap,
                        whisper_lang=whisper_lang, whisper_model=whisper_model_size,
                        output_language=output_language,
                    )
                    st.session_state.analysis_result = result
                    st.session_state.current_title = title
                    add_to_history(title, uploaded_file.name, result)
                except Exception as e:
                    st.error(f"❌ {e}")
                    st.session_state.analysis_result = None
                finally:
                    st.session_state.is_processing = False

    # ── Result ───────────────────────────────────────────────
    if st.session_state.analysis_result:
        show_result(st.session_state.analysis_result, st.session_state.current_title)


if __name__ == "__main__":
    main()
