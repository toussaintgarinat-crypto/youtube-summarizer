#!/bin/bash

echo "========================================"
echo "  YouTube Summarizer - Launch Script"
echo "========================================"
echo

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "[2/4] Installing dependencies..."
pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "[3/4] Creating configuration file..."
    cp .env.example .env
    echo
    echo "========================================"
    echo "  IMPORTANT: Edit the .env file"
    echo "  and add your OpenRouter API key"
    echo "========================================"
    echo
    open -t .env
    read -p "Press Enter to continue..."
    exit 0
fi

echo "[4/4] Launching interface..."
echo
echo "Open your browser at:"
echo "http://localhost:8501"
echo

streamlit run app.py