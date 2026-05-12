#!/bin/bash
# YouTube Summarizer - Lanceur simple

cd "$(dirname "$0")"

echo "📺 YouTube Summarizer"
echo "===================="

# Launch Streamlit
python3 -m streamlit run app.py --server.port 8501

echo ""
echo "Ouvrez votre navigateur: http://localhost:8501"