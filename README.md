# YouTube Summarizer

Résumez n'importe quelle vidéo YouTube, Twitch, Vimeo, TikTok ou fichier audio/vidéo local grâce à l'IA — en français, anglais, espagnol ou autre langue.

Disponible en **trois modes** : application web (Streamlit), application desktop (Tkinter), ou conteneur Docker.

---

## 🚀 Démarrage rapide (Docker — recommandé)

**Une seule commande :**

```bash
OPENROUTER_API_KEY=sk-or-v1-xxx \
  bash -c "$(curl -sSL https://raw.githubusercontent.com/toussaintgarinat-crypto/youtube-summarizer/main/start.sh)"
```

Remplacez `sk-or-v1-xxx` par votre clé OpenRouter (gratuite sur [openrouter.ai/keys](https://openrouter.ai/keys)).

L'app est alors accessible sur **[http://localhost:8501](http://localhost:8501)**.

---

## Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| **📺 Analyse vidéo** | Résumé de YouTube, Twitch, Vimeo, TikTok, Twitter/X, Instagram, 1 000+ plateformes |
| **🎙️ Whisper** | Transcription automatique via Whisper API ou local si pas de sous-titres |
| **📁 Fichiers locaux** | Analyse de mp3, mp4, wav, m4a, ogg, flac, webm, mkv, avi, mov |
| **🎬 Playlists YouTube** | Analyse toutes les vidéos d'une playlist avec un rapport consolidé |
| **💬 Chat / Q&A** | Posez des questions sur le contenu de la vidéo après l'analyse |
| **🖼️ Génération d'images** | Créez une illustration du résumé (Flux, DALL-E, SD, Midjourney) |
| **🌍 Multilingue** | Résumé en français, anglais, espagnol, allemand, portugais, italien |
| **📄 Export** | Markdown, PDF |
| **🔄 Fallback automatique** | Bascule sur un autre modèle LLM gratuit en cas de saturation |

---

## Installation

### Avec Docker

```bash
# 1. Cloner
git clone https://github.com/toussaintgarinat-crypto/youtube-summarizer.git
cd youtube-summarizer

# 2. Configurer la clé API
cp .env.example .env
# Éditer .env et renseigner OPENROUTER_API_KEY

# 3. Lancer
docker compose up -d
# → http://localhost:8501
```

### Sans Docker (code source)

```bash
# 1. Prérequis : Python 3.11, ffmpeg
brew install ffmpeg    # macOS
# apt install ffmpeg   # Linux

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer la clé API
cp .env.example .env
# Éditer .env et renseigner OPENROUTER_API_KEY

# 4. Lancer
streamlit run app.py   # Interface web
# ou
python gui.py          # Interface desktop
```

---

## Utilisation

### 1. Obtenir une clé API OpenRouter (gratuit)

1. Créez un compte sur [openrouter.ai](https://openrouter.ai)
2. Allez dans **Keys** → **Create Key**
3. Copiez la clé (commence par `sk-or-v1-...`)

Les **modèles gratuits** (suffixe `:free`) ne nécessitent aucun crédit.

### 2. Analyser une vidéo

**URL vidéo** : collez un lien YouTube, Twitch, Vimeo, etc. → l'app récupère le transcript natif ou transcrit avec Whisper.

**Playlist YouTube** : collez une URL de playlist (ex: `youtube.com/playlist?list=...`) → l'app détecte automatiquement et analyse toutes les vidéos.

**Fichier local** : importez un fichier audio/vidéo → transcription Whisper + analyse.

### 3. Après l'analyse

- **💬 Poser une question** : interrogez le contenu de la vidéo (ex: "Quel est le sujet principal ?")
- **🎨 Générer une image** : créez une illustration basée sur le résumé (choix du provider et du style)
- **📄 Exporter** : sauvegardez en Markdown ou PDF

---

## Architecture

```
youtube-summarizer/
├── app.py                  Interface web (Streamlit)
├── gui.py                  Interface desktop (Tkinter)
├── cli.py                  Interface en ligne de commande
├── Dockerfile              Conteneurisation Docker
├── docker-compose.yml      Orchestration Docker
├── start.sh                Script de démarrage one-liner
│
├── src/
│   ├── extractor.py           Récupère le transcript natif (YouTube, Twitch, Vimeo)
│   ├── whisper_transcriber.py Transcrit l'audio via Whisper
│   ├── chunker.py             Découpe le transcript en blocs (chunks)
│   ├── analyzer.py            Envoie chaque chunk au LLM (OpenRouter)
│   ├── fusion.py              Fusionne les analyses multi-chunks
│   ├── models.py              Liste dynamique des modèles OpenRouter
│   ├── image_generator.py     Génération d'images (Flux, DALL-E, SD, Midjourney)
│   └── pdf_exporter.py        Export PDF du résumé
│
├── prompts/
│   ├── analyzer.xml           Prompt LLM pour l'analyse d'un chunk
│   └── fusion.xml             Prompt LLM pour la fusion multi-chunks
│
└── .streamlit/
    ├── secrets.toml           Clés API (gitignoré)
    └── secrets.toml.example   Template pour secrets.toml
```

**Pipeline d'analyse :**

```
URL / Fichier local / Playlist
      ↓
Transcript natif ? ──non──→ Whisper (yt-dlp + transcription)
      ↓
Découpage en chunks (≈12 000 tokens)
      ↓
Analyse de chaque chunk via LLM
      ↓
Fusion des analyses → Résumé final
      ↓
         ├─ 💬 Chat / Q&A sur le transcript
         └─ 🎨 Génération d'image
```

Si un modèle LLM est temporairement surchargé, l'app bascule automatiquement sur un autre modèle gratuit disponible.

---

## Variables d'environnement (`.env`)

```env
OPENROUTER_API_KEY=sk-or-v1-...    # Obligatoire
OPENAI_API_KEY=sk-...               # Optionnel : Whisper API
APP_PASSWORD=                       # Optionnel : protège l'app web
DEFAULT_MODEL=meta-llama/llama-3.3-70b-instruct:free
CHUNK_SIZE_TOKENS=12000
CHUNK_OVERLAP_TOKENS=1200
WHISPER_MODEL=base
```
