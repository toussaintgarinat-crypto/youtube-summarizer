#!/bin/bash
# Build YouTubeSummarizer.dmg (Intel x86_64) depuis gui.py
set -e

echo "=== YouTube Summarizer — Build Intel ==="

# Python 3.11 en priorité, sinon 3.14
if command -v /usr/local/bin/python3.11 &>/dev/null; then
    PYTHON=/usr/local/bin/python3.11
elif command -v /usr/local/bin/python3.14 &>/dev/null; then
    PYTHON=/usr/local/bin/python3.14
elif command -v python3 &>/dev/null; then
    PYTHON=python3
else
    echo "Erreur : Python 3 introuvable."
    echo "Installer avec : brew install python@3.11"
    exit 1
fi

echo "Python : $($PYTHON --version)"

if ! $PYTHON -m PyInstaller --version &>/dev/null; then
    echo "Installation de PyInstaller..."
    $PYTHON -m pip install pyinstaller
fi

# Dépendances
echo "Installation des dépendances..."
$PYTHON -m pip install --quiet youtube-transcript-api tiktoken python-dotenv requests fpdf2 openai yt-dlp

# Clean
echo "Nettoyage..."
rm -rf build/YouTubeSummarizer dist/YouTubeSummarizer dist/YouTubeSummarizer.app dist/YouTubeSummarizer-Intel.dmg

# Build
echo "Build en cours..."
$PYTHON -m PyInstaller gui.spec --noconfirm

# DMG
echo "Création du DMG..."
hdiutil create \
    -volname "YouTubeSummarizer" \
    -srcfolder dist/YouTubeSummarizer.app \
    -ov -format UDZO \
    dist/YouTubeSummarizer-Intel.dmg

echo ""
echo "=== Terminé ==="
echo "DMG Intel : dist/YouTubeSummarizer-Intel.dmg"
