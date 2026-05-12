# YouTube Summarizer

Résumez n'importe quelle vidéo YouTube, Twitch, Vimeo ou fichier audio/vidéo grâce à l'IA.  
Disponible en **deux modes** : application web (navigateur) ou application desktop (locale, sans navigateur).

---

## Deux modes d'utilisation

### 🌐 Mode Web — Streamlit Cloud

L'application est déployée en ligne et accessible depuis n'importe quel navigateur, sans installation.

> L'app Streamlit est redéployée automatiquement à chaque mise à jour du dépôt.

**Prérequis :** une clé API OpenRouter (gratuite sur [openrouter.ai](https://openrouter.ai/keys))

---

### 🖥️ Mode Local — Application Desktop

Une fenêtre native (Tkinter), **sans navigateur**, qui tourne entièrement sur votre machine.

#### Installation

```bash
# 1. Cloner le dépôt
git clone https://github.com/toussaintgarinat-crypto/youtube-summarizer.git
cd youtube-summarizer

# 2. Installer les dépendances Python
pip install -r requirements.txt

# 3. (macOS) Installer les dépendances système
brew install ffmpeg yt-dlp

# 4. Configurer la clé API
cp .env.example .env
# Ouvrir .env et renseigner OPENROUTER_API_KEY=sk-or-v1-...
```

#### Lancement

```bash
python gui.py
```

---

## Architecture du projet

Les deux modes partagent le même code backend :

```
youtube-summarizer/
│
├── app.py          ← Interface web (Streamlit Cloud)
├── gui.py          ← Interface desktop locale (Tkinter)
│
└── src/            ← Code partagé par les deux interfaces
    ├── analyzer.py          Appels LLM (OpenRouter)
    ├── fusion.py            Fusion des analyses multi-chunks
    ├── extractor.py         Extraction des transcripts natifs
    ├── chunker.py           Découpage en chunks
    ├── models.py            Liste dynamique des modèles OpenRouter
    └── whisper_transcriber.py  Transcription audio via Whisper
```

---

## Fonctionnalités

| Fonctionnalité | Web | Desktop |
|---|:---:|:---:|
| YouTube / Twitch / Vimeo / 1000+ plateformes | ✅ | ✅ |
| Fallback Whisper (yt-dlp) si pas de transcript | ✅ | ✅ |
| Fichier audio/vidéo local (mp3, mp4, wav…) | ✅ | ✅ |
| Modèles gratuits dynamiques (OpenRouter) | ✅ | ✅ |
| Fallback automatique si modèle surchargé | ✅ | ✅ |
| Choix de la langue du résumé (FR/EN/ES…) | ✅ | ✅ |
| Export Markdown | ✅ | ✅ |
| Export PDF | ✅ | ✅ |
| Clé API personnalisée | ✅ | ✅ |
| Sans navigateur | ❌ | ✅ |

---

## Clé API OpenRouter

Les deux modes nécessitent une clé API [OpenRouter](https://openrouter.ai/keys).

- **Mode Web** : entrez votre clé dans la barre latérale, ou configurez-la dans les secrets Streamlit (`OPENROUTER_API_KEY`)
- **Mode Local** : renseignez-la dans le fichier `.env` ou directement dans l'interface

Les **modèles gratuits** (suffixe `:free`) ne nécessitent pas de crédits.  
Si un modèle est temporairement surchargé, l'app bascule automatiquement sur un autre modèle gratuit.

---

## Variables d'environnement (`.env`)

```env
OPENROUTER_API_KEY=sk-or-v1-...   # Obligatoire
APP_PASSWORD=                      # Optionnel : protège l'app web par mot de passe
DEFAULT_MODEL=meta-llama/llama-3.3-70b-instruct:free
CHUNK_SIZE_TOKENS=12000
CHUNK_OVERLAP_TOKENS=1200
```
