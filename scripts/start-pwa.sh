#!/usr/bin/env bash
# Démarrage du mode PWA (hors Docker, nécessite Node.js)
# Utilisation : bash scripts/start-pwa.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# Générer les icônes si absentes
if [ ! -f pwa/icon-192.png ]; then
  echo "📦 Génération des icônes PWA..."
  python3 pwa/generate_icons.py
fi

# Lancer Streamlit en arrière-plan
echo "🚀 Démarrage de Streamlit sur le port 8501..."
streamlit run app.py --server.port=8501 --server.headless=true &
STREAMLIT_PID=$!

# Attendre que Streamlit soit prêt
echo "⏳ Attente de Streamlit..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8501 > /dev/null 2>&1; then
    echo "   ✅ Streamlit prêt"
    break
  fi
  sleep 1
done

# Nettoyer à la sortie
cleanup() {
  echo ""
  echo "🛑 Arrêt..."
  kill $STREAMLIT_PID 2>/dev/null || true
  kill $PROXY_PID 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

# Lancer le proxy Node.js
echo "🌐 Démarrage du proxy PWA sur le port 8500..."
node scripts/pwa-proxy.js &
PROXY_PID=$!

sleep 1

echo ""
echo "📺 YouTube Summarizer — Mode PWA"
echo "=================================="
echo "   → http://localhost:8500"
echo ""
echo "   Sur votre téléphone (même réseau) :"
echo "   http://$(ipconfig getifaddr en0 2>/dev/null || echo "<votre-ip>"):8500"
echo ""

# Ouvrir le navigateur
case "$OSTYPE" in
  darwin*)  open "http://localhost:8500" ;;
  linux*)   xdg-open "http://localhost:8500" 2>/dev/null || true ;;
  msys|cygwin) start "http://localhost:8500" ;;
esac

# Attendre que les processus se terminent
wait $PROXY_PID
