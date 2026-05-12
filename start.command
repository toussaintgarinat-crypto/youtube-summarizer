#!/bin/bash
cd "$(dirname "$0")"
echo "========================================="
echo "  YouTube Summarizer"
echo "========================================="
echo ""

# Check if virtualenv exists
if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "[2/4] Installing dependencies..."
pip install -r requirements.txt --quiet

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo "[3/4] Creating configuration..."
    cp .env.example .env
    echo ""
    echo "========================================="
    echo "IMPORTANT: Edit .env and add your"
    echo "OpenRouter API key!"
    echo "========================================="
    echo ""
    open -t .env
    echo "Press Enter when done..."
    read
fi

# Run streamlit
echo "[4/4] Starting interface..."
echo ""
echo "Open your browser at:"
echo "http://localhost:8501"
echo ""
streamlit run app.py