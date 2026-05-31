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

### Avec Docker (recommandé)

**Prérequis :** [Docker Desktop](https://docs.docker.com/get-docker/) installé et lancé.

```bash
# 1. Cloner le dépôt
git clone https://github.com/toussaintgarinat-crypto/youtube-summarizer.git
cd youtube-summarizer

# 2. Configurer la clé API
cp .env.example .env
# Éditer .env et renseigner OPENROUTER_API_KEY=sk-or-v1-...

# 3. Lancer l'application
docker compose up -d

# 4. Ouvrir le navigateur
# → http://localhost:8501
```

**📱 Mode PWA (icône sur le téléphone) :**

```bash
docker compose up -d
# Puis ouvrir : http://localhost:8500
# iOS  → Safari > Partager > Sur l'écran d'accueil
# Android → Chrome > Menu > Installer l'application
```

**Autres commandes utiles :**

| Commande | Effet |
|---|---|
| `docker compose up -d` | Lancer en arrière-plan |
| `docker compose logs -f` | Voir les logs en direct |
| `docker compose down` | Arrêter le container |
| `docker compose build --no-cache` | Rebuilder l'image de zéro |

**Détail de ce que fait Docker :**

1. **Build** : construit une image Python 3.11 avec ffmpeg, Node.js et toutes les dépendances
2. **Run** : démarre le container sur le port 8501
3. **Volume** : monte `config.py` pour que les modifs soient prises en compte sans rebuild
4. **.env** : injecté automatiquement → pas de clé API dans l'image

> Sans Docker Compose : `docker run -p 8501:8501 --env-file .env youtube-summarizer`

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

### Avec PyInstaller (build standalone)

```bash
pip install pyinstaller
pyinstaller gui.spec   # Build l'application desktop
# L'executable se trouve dans dist/
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

## Comment ça marche — Guide complet

### Pipeline d'analyse

```
                   ┌─────────────────────────┐
                   │  URL / Playlist / Fichier │
                   └────────┬────────────────┘
                            ↓
                    ┌───────┴───────┐
                    │  Détection    │
                    │  plateforme   │
                    └───────┬───────┘
                            ↓
              ┌─────────────┴─────────────┐
              │                           │
         Transcript natif ?           Whisper
      (YouTube, Twitch, Vimeo)    (yt-dlp + OpenAI API
              │                   ou modèle local)
              │                           │
              └─────────────┬─────────────┘
                            ↓
                   ┌────────────────┐
                   │  Découpage en  │
                   │  chunks        │
                   │  (tiktoken)    │
                   └────────┬───────┘
                            ↓
              ┌─────────────┴─────────────┐
              │                           │
         ┌────┴────┐              ┌───────┴──────┐
         │ Chunk 1 │   ...        │  Chunk N     │
         │ Analyse │              │  Analyse     │
         │   LLM   │              │    LLM       │
         └────┬────┘              └───────┬──────┘
              │                           │
              └─────────────┬─────────────┘
                            ↓
                   ┌────────────────┐
                   │    Fusion      │ (si N > 1)
                   │   des analyses │
                   └────────┬───────┘
                            ↓
                   ┌────────────────┐
                   │  Résumé final  │
                   └────────┬───────┘
                            ↓
              ┌─────────────┼─────────────┐
              │             │             │
         Export MD      Chat Q&A     Image gen
         Export PDF    (transcript   (résumé →
                       → question)   prompt → IA)
```

### Détail de chaque étape

#### 1. Extraction du transcript (`src/extractor.py`)

| Plateforme | Méthode | Source |
|---|---|---|
| **YouTube** | `youtube-transcript-api` | Sous-titres natifs |
| **Twitch** | API Helix + VTT | VODs avec sous-titres |
| **Vimeo** | Scraping HTML + VTT | Vidéos avec sous-titres |
| **Autres** | Whisper (via yt-dlp) | Audio téléchargé puis transcrit |

Pour les **playlists YouTube**, `yt-dlp --flat-playlist` liste toutes les vidéos, puis chacune est analysée individuellement.

#### 2. Transcription Whisper (`src/whisper_transcriber.py`)

Si aucun transcript natif n'est disponible :
1. **yt-dlp** télécharge l'audio (mp3, qualité 5)
2. **ffmpeg** compresse en 16kHz mono 32kbps
3. **Whisper** transcrit (priorité API OpenAI, fallback modèle local)
4. Si le fichier > 24 MB, il est découpé en chunks de 20 min

#### 3. Découpage en chunks (`src/chunker.py`)

- **Tokenisation** via `tiktoken` (cl100k_base)
- **Taille par défaut** : 12 000 tokens
- **Chevauchement** : 10% entre les chunks (conserve le contexte)
- Les chunks respectent les timestamps de la vidéo

#### 4. Analyse LLM (`src/analyzer.py`)

- Appelle l'API **OpenRouter** avec un prompt structuré (XML)
- Si le modèle est saturé (HTTP 429), **bascule automatiquement** sur le prochain modèle gratuit disponible
- Timeout : 180 secondes par requête
- Le prompt demande : résumé exécutif, table des chapitres, points clés, insights

#### 5. Fusion (`src/fusion.py`)

Pour les vidéos longues (multi-chunks) :
- Fusionne les tables de chapitres avec dédup
- Sélectionne les meilleurs insights
- Appelle le LLM une dernière fois pour un rapport cohérent

#### 6. Post-traitement

| Feature | Module | Description |
|---|---|---|
| **📄 PDF** | `src/pdf_exporter.py` | Conversion Markdown → PDF (fpdf2) |
| **💬 Chat Q&A** | Intégré dans l'UI | LLM + transcript complet comme contexte |
| **🖼️ Image** | `src/image_generator.py` | Flux, DALL-E, SD, Midjourney via OpenRouter |

---

## Architecture du projet

```
youtube-summarizer/
│
├── app.py                    # Interface web (Streamlit) — principale
├── gui.py                    # Interface desktop (Tkinter)
├── cli.py                    # Interface en ligne de commande
├── youtube_summarizer_app.py # Version simplifiée (Streamlit, build EXE)
│
├── Dockerfile                # Image Docker (Python 3.11 + ffmpeg + Node.js)
├── docker-compose.yml        # Orchestration Docker (port, volume, env)
├── start.sh                  # Script one-liner : setup + build + run
│
├── config.py                 # Configuration centralisée (env, secrets)
├── requirements.txt          # Dépendances Python
├── packages.txt              # Dépendances système (ffmpeg, nodejs)
│
├── src/
│   ├── extractor.py           # Détection plateforme + extraction transcript
│   ├── whisper_transcriber.py # Téléchargement audio + Whisper
│   ├── chunker.py             # Découpage token-aware du transcript
│   ├── analyzer.py            # Appel LLM OpenRouter avec fallback
│   ├── fusion.py              # Fusion multi-chunks
│   ├── models.py              # Liste dynamique des modèles OpenRouter
│   ├── image_generator.py     # Génération d'images (4 providers)
│   └── pdf_exporter.py        # Export Markdown → PDF
│
├── prompts/
│   ├── analyzer.xml           # Prompt LLM pour un chunk
│   └── fusion.xml             # Prompt LLM pour la fusion
│
├── test_core.py               # Tests unitaires (30+ classes)
│
├── *.spec                     # Build PyInstaller (Mac, Windows, Linux)
├── build_app.sh               # Build script macOS
├── run.sh / run.bat           # Lanceurs (Mac/Windows)
│
└── .streamlit/
    ├── config.toml            # Thème Streamlit (dark, upload 500MB)
    ├── secrets.toml           # Clés API (gitignoré)
    └── secrets.toml.example   # Template pour secrets.toml
```

---

## Détail des interfaces

### Interface web (Streamlit — `app.py`)

| Élément | Description |
|---|---|
| **🔑 Sidebar** | Clé API, modèle LLM, chunk size, langue, cookies Whisper |
| **🔗 Tab URL** | URL vidéo, playlist, ou plateforme tierce |
| **📁 Tab Fichier** | Upload audio/vidéo local |
| **📜 Historique** | 10 dernières analyses sauvegardées en session |
| **🛡️ Password** | Protection optionnelle via `APP_PASSWORD` |

### Interface desktop (Tkinter — `gui.py`)

Mêmes fonctionnalités que la version web, mais en application native :
- Fenêtre redimensionnable (920x780)
- Barre de progression
- Export Markdown / PDF / Copier
- Gestion des clés API en direct

### CLI (`cli.py`)

```bash
python cli.py "URL_VIDEO" --model "modele" --chunk-size 12000 -o resultat.md
```

---

## Variables d'environnement (`.env`)

| Variable | Obligatoire | Défaut | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | ✅ | — | Clé API OpenRouter |
| `OPENAI_API_KEY` | ❌ | — | Clé API OpenAI (Whisper API) |
| `APP_PASSWORD` | ❌ | — | Mot de passe pour l'app web |
| `DEFAULT_MODEL` | ❌ | `meta-llama/llama-3.3-70b-instruct:free` | Modèle LLM par défaut |
| `CHUNK_SIZE_TOKENS` | ❌ | `12000` | Taille des chunks en tokens |
| `CHUNK_OVERLAP_TOKENS` | ❌ | `1200` | Chevauchement entre chunks |
| `WHISPER_MODEL` | ❌ | `base` | Modèle Whisper local |
| `YOUTUBE_COOKIES` | ❌ | — | Cookies YouTube (pour vidéos restreintes) |

---

## CI/CD — Build automatique

| Workflow | Runner | Artifact |
|---|---|---|
| `build-mac.yml` | `macos-latest` | `YouTubeSummarizer-Mac.dmg` |
| `build-windows.yml` | `windows-latest` | `YouTubeSummarizer-Windows.zip` |
| `build-linux.yml` | `ubuntu-latest` | `YouTubeSummarizer-Linux.tar.gz` |

Les builds sont déclenchés automatiquement à chaque push sur `main`, ou manuellement via **Actions → Run workflow**.
