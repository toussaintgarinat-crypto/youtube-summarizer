"""
YouTube Summarizer - Standalone EXE Version
Simplified interface for PyInstaller compilation.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import config
from src import extractor, chunker, analyzer, fusion
import time

st.set_page_config(
    page_title="YouTube Summarizer",
    page_icon="📺",
    layout="wide"
)

def init_session_state():
    if 'analysis_result' not in st.session_state:
        st.session_state.analysis_result = None
    if 'video_url' not in st.session_state:
        st.session_state.video_url = ""
    if 'is_processing' not in st.session_state:
        st.session_state.is_processing = False
    if 'progress' not in st.session_state:
        st.session_state.progress = 0

def process_video(url, model, chunk_size, overlap):
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("📥 Extraction du transcript...")
        progress_bar.progress(10)
        
        result = extractor.get_transcript(url)
        transcript = result['transcript']
        video_title = result.get('title', f"Video {result['video_id']}")
        
        st.session_state.progress = 20
        
        status_text.text("✂️ Découpage en chunks...")
        chunks = chunker.chunk_transcript(
            transcript,
            max_tokens=chunk_size,
            overlap_tokens=overlap,
            model=model
        )
        
        chunk_info = chunker.get_chunk_count_info(chunks)
        status_text.text(f"{chunk_info}")
        
        progress_bar.progress(30)
        
        analyses = []
        for i, chunk in enumerate(chunks):
            status_text.text(f"🤖 Analyse chunk {i+1}/{len(chunks)}...")
            progress_bar.progress(30 + (60 * (i + 1) // len(chunks)))
            
            analysis = analyzer.analyze_chunk(
                chunk['text'],
                video_title,
                model=model
            )
            analyses.append(analysis)
            time.sleep(1)
        
        final_analysis = analyses[0]
        if len(analyses) > 1:
            status_text.text("🔗 Fusion des analyses...")
            progress_bar.progress(95)
            final_analysis = fusion.fusion_analyses(analyses, video_title, model)
        
        progress_bar.progress(100)
        status_text.text("✅ Terminé!")
        
        return final_analysis
        
    except Exception as e:
        progress_bar.progress(0)
        status_text.text(f"❌ Erreur: {str(e)}")
        raise

def main():
    init_session_state()
    
    st.title("📺 YouTube Summarizer")
    st.markdown("Transformez vos vidéos YouTube en rapports structurés")
    
    st.sidebar.header("⚙️ Configuration")
    
    available_models = list(config.MODEL_CONTEXTS.keys())
    selected_model = st.sidebar.selectbox(
        "Modèle LLM",
        options=available_models,
        index=available_models.index(config.DEFAULT_MODEL)
        if config.DEFAULT_MODEL in available_models else 0
    )
    
    st.sidebar.markdown("### Limites")
    
    ctx_limit = config.get_model_context_limit(selected_model)
    chunk_size = st.sidebar.number_input(
        "Tokens par chunk",
        min_value=1000,
        max_value=ctx_limit - 4000,
        value=config.CHUNK_SIZE_TOKENS,
        step=1000
    )
    
    overlap = st.sidebar.number_input(
        "Chevauchement (tokens)",
        min_value=100,
        max_value=chunk_size // 2,
        value=min(chunk_size // 10, config.CHUNK_OVERLAP_TOKENS),
        step=100
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Limite contexte:** {ctx_limit} tokens")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        url_input = st.text_input(
            "URL YouTube",
            placeholder="https://www.youtube.com/watch?v=...",
            key="url_input"
        )
    
    with col2:
        st.write("")
        st.write("")
        analyze_btn = st.button(
            "🚀 Analyser",
            type="primary",
            disabled=st.session_state.is_processing
        )
    
    st.markdown("### 📁 Ou importez un fichier")
    uploaded_file = st.file_uploader(
        "Déposez un fichier .txt contenant l'URL",
        type=['txt'],
        label_visibility="collapsed"
    )
    
    if uploaded_file is not None:
        url_from_file = uploaded_file.getvalue().decode("utf-8").strip()
        if url_from_file and url_from_file != st.session_state.video_url:
            st.session_state.video_url = url_from_file
            if not st.session_state.is_processing:
                url_input = url_from_file
    
    if analyze_btn and url_input:
        if not config.OPENROUTER_API_KEY:
            st.error("⚠️ Configurez OPENROUTER_API_KEY dans le fichier .env")
            return
            
        is_valid, error = extractor.validate_youtube_url(url_input)
        if not is_valid:
            st.error(f"❌ {error}")
            return
        
        st.session_state.is_processing = True
        st.session_state.video_url = url_input
        
        try:
            result = process_video(
                url_input,
                selected_model,
                chunk_size,
                overlap
            )
            st.session_state.analysis_result = result
            
        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")
            st.session_state.analysis_result = None
        
        finally:
            st.session_state.is_processing = False
    
    if st.session_state.analysis_result:
        st.markdown("---")
        st.markdown("## 📝 Résultat")
        
        st.download_button(
            label="💾 Télécharger Markdown",
            data=st.session_state.analysis_result,
            file_name="youtube_analysis.md",
            mime="text/markdown"
        )
        
        st.markdown(st.session_state.analysis_result)

if __name__ == "__main__":
    main()