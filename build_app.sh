#!/bin/bash
# Build YouTubeSummarizer.app (macOS)
set -e

echo "=== YouTube Summarizer — Build ==="

# Check Python
PYTHON=/usr/bin/python3
if ! $PYTHON -m PyInstaller --version &>/dev/null; then
    echo "Installation de PyInstaller..."
    $PYTHON -m pip install pyinstaller
fi

# Clean previous build
echo "Nettoyage..."
rm -rf build/YouTubeSummarizer dist/YouTubeSummarizer dist/YouTubeSummarizer.app

# Build
echo "Build en cours..."
$PYTHON -m PyInstaller YouTubeSummarizer.spec --noconfirm

echo ""
echo "=== Terminé ==="
echo "App : dist/YouTubeSummarizer.app"
echo "Pour lancer : open dist/YouTubeSummarizer.app"
