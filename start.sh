#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# YouTube Summarizer — démarrage one-liner
# Utilisation : bash start.sh
# ──────────────────────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "📺 YouTube Summarizer — Installation & Démarrage"
echo "================================================"

# ── Vérifier Docker ─────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "❌ Docker n'est pas installé."
    echo "   → https://docs.docker.com/get-docker/"
    exit 1
fi

# ── Créer .env si nécessaire ────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "🔑 Fichier .env créé."
    echo "   Tu dois y mettre ta clé OpenRouter."
    echo "   Obtiens-en une gratuitement sur https://openrouter.ai/keys"
    echo ""
    read -rp "   Colle ta clé OpenRouter (sk-or-v1-...) : " api_key
    if [ -n "$api_key" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|sk-or-votre-cle-api-ici|$api_key|" .env
        else
            sed -i "s|sk-or-votre-cle-api-ici|$api_key|" .env
        fi
        echo "   ✅ Clé enregistrée dans .env"
    fi
fi

# ── Builder & lancer ────────────────────────────────────────
echo ""
echo "🐳 Construction de l'image Docker..."
docker compose build --quiet 2>/dev/null || docker build -t youtube-summarizer .

echo "🚀 Lancement du container..."
docker compose up -d 2>/dev/null || docker run -d --name youtube-summarizer \
    -p 8501:8501 --env-file .env --restart unless-stopped youtube-summarizer

echo ""
echo "✅ L'app est prête !"
echo "   → http://localhost:8501"
echo ""

# ── Ouvrir le navigateur ────────────────────────────────────
case "$OSTYPE" in
    darwin*)  open "http://localhost:8501" ;;
    linux*)   xdg-open "http://localhost:8501" 2>/dev/null || true ;;
    msys|cygwin) start "http://localhost:8501" ;;
esac
