# YouTube Summarizer

Résumez n'importe quelle vidéo YouTube, Twitch, Vimeo, TikTok ou fichier audio/vidéo local grâce à l'IA — en français, anglais, espagnol ou autre langue.

Disponible en **deux modes** : application desktop (Mac / Windows) ou application web (navigateur).

---

## Télécharger l'application desktop

Pas besoin de Python ni de terminal. Téléchargez directement l'app compilée :

1. Allez dans l'onglet **Actions** de ce dépôt GitHub
2. Cliquez sur le dernier workflow **Build Mac DMG** ou **Build Windows EXE**
3. En bas de la page du workflow, téléchargez l'artifact :
   - **Mac** → `YouTubeSummarizer-Mac` → extrayez le `.dmg`, ouvrez-le et glissez l'app dans Applications
   - **Windows** → `YouTubeSummarizer-Windows` → extrayez le `.zip`, lancez `YouTubeSummarizer.exe`

> Sur Mac, si macOS bloque l'app au premier lancement : clic droit → **Ouvrir** → confirmer.

---

## Utilisation — pas à pas

### 1. Obtenir une clé API OpenRouter (gratuit)

L'app utilise [OpenRouter](https://openrouter.ai/keys) pour accéder aux modèles IA.

1. Créez un compte sur [openrouter.ai](https://openrouter.ai)
2. Allez dans **Keys** → **Create Key**
3. Copiez la clé (commence par `sk-or-v1-...`)

Les **modèles gratuits** (suffixe `:free`) ne nécessitent aucun crédit.

---

### 2. Lancer l'application

Ouvrez `YouTubeSummarizer.app` (Mac) ou `YouTubeSummarizer.exe` (Windows).

---

### 3. Entrer votre clé API

En haut de la fenêtre, collez votre clé OpenRouter dans le champ **Clé OpenRouter**.  
Un ✅ apparaît quand la clé est reconnue.

> La clé OpenAI (champ à droite) est optionnelle — elle est uniquement nécessaire si vous utilisez Whisper via l'API OpenAI au lieu de Whisper local.

---

### 4. Choisir le modèle et la langue

- **Modèle** : par défaut `meta-llama/llama-3.3-70b-instruct:free` (gratuit, recommandé). Cochez "Tous les modèles" pour accéder aux modèles payants.
- **Langue sortie** : la langue dans laquelle le résumé sera rédigé (FR, EN, ES…).

---

### 5. Analyser une vidéo en ligne

Onglet **🔗 URL vidéo** :

1. Collez l'URL de la vidéo (YouTube, Twitch, Vimeo, TikTok, Twitter/X, Instagram, 1 000+ plateformes)
2. Cliquez **🚀 Analyser**
3. L'app récupère d'abord le transcript natif de la plateforme. Si aucun n'est disponible, elle télécharge l'audio et le transcrit avec Whisper automatiquement.

---

### 6. Analyser un fichier local

Onglet **📁 Fichier local** :

1. Cliquez **📂 Choisir fichier…** et sélectionnez votre fichier (mp3, mp4, wav, m4a, ogg, flac, webm, mkv, avi, mov)
2. Cliquez **🚀 Transcrire & Analyser**
3. L'app transcrit le fichier avec Whisper et génère le résumé.

---

### 7. Lire et exporter le résultat

Le résumé apparaît dans la zone **Résultat**. Vous pouvez ensuite :

- **💾 Sauvegarder Markdown** — enregistre le résumé en `.md`
- **📄 Exporter PDF** — génère un fichier `.pdf`
- **📋 Copier** — copie le texte dans le presse-papier
- **🗑️ Effacer** — réinitialise l'interface

---

## Options avancées

| Option | Description |
|---|---|
| **Tokens/chunk** | Taille des blocs d'analyse. Augmenter si la vidéo est très longue. |
| **Forcer Whisper** | Ignore le transcript natif et transcrit l'audio même si un transcript existe. |
| **Langue audio** | Langue parlée dans la vidéo (pour Whisper). `auto` = détection automatique. |
| **Modèle Whisper** | `tiny` = rapide, `base` = équilibré, `large` = précis mais lent. |

---

## Mode Web — Streamlit Cloud

L'application est aussi disponible en ligne, sans installation, depuis n'importe quel navigateur.

> L'app web est redéployée automatiquement à chaque mise à jour du dépôt.

**Configuration de la clé API :**
- Entrez votre clé dans la barre latérale, ou
- Configurez-la dans les secrets Streamlit (`OPENROUTER_API_KEY`)

---

## Lancer depuis le code source

```bash
# 1. Cloner le dépôt
git clone https://github.com/toussaintgarinat-crypto/youtube-summarizer.git
cd youtube-summarizer

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. (macOS) Installer ffmpeg
brew install ffmpeg

# 4. Configurer la clé API
cp .env.example .env
# Ouvrir .env et renseigner OPENROUTER_API_KEY=sk-or-v1-...

# 5. Lancer l'interface desktop
python gui.py

# ou lancer l'interface web
streamlit run app.py
```

---

## Comment ça fonctionne (architecture)

```
youtube-summarizer/
│
├── app.py          ← Interface web (Streamlit)
├── gui.py          ← Interface desktop (Tkinter)
│
└── src/
    ├── extractor.py           Récupère le transcript natif (YouTube, etc.)
    ├── whisper_transcriber.py Transcrit l'audio via Whisper si pas de transcript
    ├── chunker.py             Découpe le transcript en blocs (chunks)
    ├── analyzer.py            Envoie chaque chunk au LLM (OpenRouter)
    ├── fusion.py              Fusionne les analyses multi-chunks en un résumé final
    └── models.py              Récupère dynamiquement la liste des modèles OpenRouter
```

**Pipeline d'analyse :**

```
URL / Fichier local
      ↓
Transcript natif ? ──non──→ Whisper (yt-dlp + transcription)
      ↓
Découpage en chunks (≈12 000 tokens)
      ↓
Analyse de chaque chunk via LLM
      ↓
Fusion des analyses → Résumé final
```

Si un modèle LLM est temporairement surchargé, l'app bascule automatiquement sur un autre modèle gratuit disponible.

---

## CI/CD — Build automatique

| Workflow | Runner | Artifact |
|---|---|---|
| `build-mac.yml` | `macos-latest` | `YouTubeSummarizer-Mac.dmg` |
| `build-windows.yml` | `windows-latest` | `YouTubeSummarizer-Windows.zip` |

Les builds sont déclenchés automatiquement à chaque push sur `main`, ou manuellement via **Actions → Run workflow**.

---

## Variables d'environnement (`.env`)

```env
OPENROUTER_API_KEY=sk-or-v1-...   # Obligatoire
OPENAI_API_KEY=sk-...              # Optionnel : Whisper via API OpenAI
APP_PASSWORD=                      # Optionnel : protège l'app web par mot de passe
DEFAULT_MODEL=meta-llama/llama-3.3-70b-instruct:free
CHUNK_SIZE_TOKENS=12000
CHUNK_OVERLAP_TOKENS=1200
```
