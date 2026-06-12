"""
YouTube Summarizer — Desktop GUI (Tkinter)
Lance avec : python gui.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from src import extractor, chunker, analyzer, fusion
from src.models import fetch_free_models, fetch_all_models, fetch_open_code_go_models
from src.image_generator import generate_image, get_providers_list, get_styles_list, build_image_prompt
from src.excalidraw_generator import generate_diagram as generate_excalidraw
from src.video_generator import generate_video, get_video_providers_list, build_video_prompt
from src import updater

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

LANGUAGES = {
    "🇫🇷 Français":   "Français",
    "🇬🇧 English":    "English",
    "🇪🇸 Español":    "Español",
    "🇩🇪 Deutsch":    "Deutsch",
    "🇵🇹 Português":  "Português",
    "🇮🇹 Italiano":   "Italiano",
}

WHISPER_LANGS  = ["auto", "fr", "en", "es", "de", "it", "pt", "ja", "zh", "ar"]
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]

AUDIO_EXTS = [
    ("Audio/Vidéo", "*.mp3 *.mp4 *.wav *.m4a *.ogg *.flac *.webm *.mkv *.avi *.mov"),
    ("Tous les fichiers", "*.*"),
]


# ──────────────────────────────────────────────────────────────
# Main application
# ──────────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube Summarizer")
        self.root.geometry("920x780")
        self.root.resizable(True, True)

        self.is_processing = False
        self.current_result = ""
        self.current_title = ""
        self.current_transcript = ""
        self.chat_history = []
        self._local_file_bytes = None
        self._local_filename = ""

        # Model cache (loaded in background)
        self._free_models: dict = {}
        self._all_models: dict  = {}
        self._go_models: dict = {}
        self.provider = "openrouter"

        self._build_ui()
        self._center()
        self._load_models_async()

    # ── UI construction ────────────────────────────────────────

    def _build_ui(self):
        root = self.root
        pad = dict(padx=12, pady=6)

        # ── Top bar: API key ──────────────────────────────────
        key_bar = ttk.Frame(root)
        key_bar.pack(fill=tk.X, **pad)

        ttk.Label(key_bar, text="Provider :").pack(side=tk.LEFT)
        self.provider_var = tk.StringVar(value="OpenRouter")
        self._provider_combo = ttk.Combobox(key_bar, textvariable=self.provider_var,
                                            width=13, state="readonly",
                                            values=["OpenRouter", "OpenCode Go"])
        self._provider_combo.pack(side=tk.LEFT, padx=4)
        self._provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        ttk.Label(key_bar, text="Clé OpenRouter :").pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar(value=config.OPENROUTER_API_KEY or "")
        self._key_entry = ttk.Entry(key_bar, textvariable=self.api_key_var,
                                    width=40, show="*")
        self._key_entry.pack(side=tk.LEFT, padx=6)
        ttk.Button(key_bar, text="👁", width=3,
                   command=self._toggle_key).pack(side=tk.LEFT)
        self._key_status = ttk.Label(key_bar, text="")
        self._key_status.pack(side=tk.LEFT, padx=8)
        self.api_key_var.trace_add("write", lambda *_: self._refresh_key_status())
        self._refresh_key_status()

        key_bar2 = ttk.Frame(root)
        key_bar2.pack(fill=tk.X, **{"padx": 12, "pady": (0, 6)})
        ttk.Label(key_bar2, text="Clé OpenCode Go :").pack(side=tk.LEFT)
        self.go_key_var = tk.StringVar(value=config.OPENCODE_GO_API_KEY or "")
        self._go_key_entry = ttk.Entry(key_bar2, textvariable=self.go_key_var,
                                        width=40, show="*")
        self._go_key_entry.pack(side=tk.LEFT, padx=6)
        ttk.Button(key_bar2, text="👁", width=3,
                   command=self._toggle_go_key).pack(side=tk.LEFT)
        self._go_key_status = ttk.Label(key_bar2, text="")
        self._go_key_status.pack(side=tk.LEFT, padx=4)
        self.go_key_var.trace_add("write", lambda *_: self._refresh_go_key_status())
        self._refresh_go_key_status()
        self._go_key_bar = key_bar2  # reference for show/hide

        ttk.Label(key_bar, text="  Clé OpenAI (Whisper) :").pack(side=tk.LEFT)
        self.openai_key_var = tk.StringVar(value=config.OPENAI_API_KEY or "")
        self._openai_entry = ttk.Entry(key_bar, textvariable=self.openai_key_var,
                                       width=30, show="*")
        self._openai_entry.pack(side=tk.LEFT, padx=6)
        ttk.Button(key_bar, text="👁", width=3,
                   command=self._toggle_openai_key).pack(side=tk.LEFT)
        self._openai_status = ttk.Label(key_bar, text="")
        self._openai_status.pack(side=tk.LEFT, padx=4)
        self.openai_key_var.trace_add("write", lambda *_: self._refresh_openai_status())
        self._refresh_openai_status()

        ttk.Separator(root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12)

        # ── Settings row ──────────────────────────────────────
        cfg = ttk.LabelFrame(root, text="Configuration", padding=8)
        cfg.pack(fill=tk.X, **pad)

        # Row 1 : model + language
        row1 = ttk.Frame(cfg)
        row1.pack(fill=tk.X, pady=3)

        ttk.Label(row1, text="Modèle :").pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value=config.DEFAULT_MODEL)
        self._model_combo = ttk.Combobox(row1, textvariable=self.model_var,
                                          width=42, state="readonly")
        self._model_combo.pack(side=tk.LEFT, padx=6)

        self.show_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="Tous les modèles",
                        variable=self.show_all_var,
                        command=self._refresh_model_list).pack(side=tk.LEFT, padx=4)

        self._model_info = ttk.Label(row1, text="", foreground="gray")
        self._model_info.pack(side=tk.LEFT, padx=6)

        ttk.Label(row1, text="  Langue sortie :").pack(side=tk.LEFT)
        self.lang_var = tk.StringVar(value="🇫🇷 Français")
        ttk.Combobox(row1, textvariable=self.lang_var,
                     values=list(LANGUAGES.keys()), width=14,
                     state="readonly").pack(side=tk.LEFT, padx=4)

        # Row 2 : chunk + whisper
        row2 = ttk.Frame(cfg)
        row2.pack(fill=tk.X, pady=3)

        ttk.Label(row2, text="Tokens/chunk :").pack(side=tk.LEFT)
        self.chunk_var = tk.IntVar(value=config.CHUNK_SIZE_TOKENS)
        ttk.Spinbox(row2, from_=1000, to=200000, increment=1000,
                    textvariable=self.chunk_var, width=8).pack(side=tk.LEFT, padx=6)

        self.force_whisper_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Forcer Whisper",
                        variable=self.force_whisper_var).pack(side=tk.LEFT, padx=12)

        ttk.Label(row2, text="Langue audio :").pack(side=tk.LEFT)
        self.whisper_lang_var = tk.StringVar(value="auto")
        ttk.Combobox(row2, textvariable=self.whisper_lang_var,
                     values=WHISPER_LANGS, width=6,
                     state="readonly").pack(side=tk.LEFT, padx=4)

        ttk.Label(row2, text="  Modèle Whisper :").pack(side=tk.LEFT)
        self.whisper_model_var = tk.StringVar(value="base")
        ttk.Combobox(row2, textvariable=self.whisper_model_var,
                     values=WHISPER_MODELS, width=8,
                     state="readonly").pack(side=tk.LEFT, padx=4)

        # Row 3 : channel scraping
        row3 = ttk.Frame(cfg)
        row3.pack(fill=tk.X, pady=3)

        ttk.Label(row3, text="📺  Max vidéos/chaîne :").pack(side=tk.LEFT)
        self.max_channel_var = tk.IntVar(value=50)
        ttk.Spinbox(row3, from_=1, to=200, increment=5,
                    textvariable=self.max_channel_var, width=6).pack(side=tk.LEFT, padx=6)

        ttk.Separator(root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12)

        # ── Input tabs ────────────────────────────────────────
        nb = ttk.Notebook(root)
        nb.pack(fill=tk.X, **pad)

        # Tab 1 — URL
        tab_url = ttk.Frame(nb, padding=8)
        nb.add(tab_url, text="🔗  URL vidéo")

        url_row = ttk.Frame(tab_url)
        url_row.pack(fill=tk.X)
        self.url_var = tk.StringVar()
        ttk.Entry(url_row, textvariable=self.url_var,
                  font=("TkDefaultFont", 11)).pack(side=tk.LEFT, fill=tk.X,
                                                    expand=True, padx=(0, 8))
        self._btn_url = ttk.Button(url_row, text="🚀 Analyser",
                                    command=self._start_url)
        self._btn_url.pack(side=tk.LEFT)

        ttk.Label(tab_url,
                  text="YouTube · Twitch · Vimeo · TikTok · Twitter/X · Instagram · 1 000+ autres",
                  foreground="gray").pack(anchor=tk.W, pady=(4, 0))

        # Tab 2 — Local file
        tab_local = ttk.Frame(nb, padding=8)
        nb.add(tab_local, text="📁  Fichier local")

        file_row = ttk.Frame(tab_local)
        file_row.pack(fill=tk.X)
        ttk.Button(file_row, text="📂 Choisir fichier…",
                   command=self._pick_file).pack(side=tk.LEFT)
        self._file_label = ttk.Label(file_row, text="Aucun fichier sélectionné",
                                      foreground="gray")
        self._file_label.pack(side=tk.LEFT, padx=10)
        self._btn_local = ttk.Button(file_row, text="🚀 Transcrire & Analyser",
                                      command=self._start_local, state=tk.DISABLED)
        self._btn_local.pack(side=tk.RIGHT)

        ttk.Label(tab_local,
                  text="mp3 · mp4 · wav · m4a · ogg · flac · webm · mkv · avi · mov",
                  foreground="gray").pack(anchor=tk.W, pady=(4, 0))

        # ── Progress ──────────────────────────────────────────
        prog_frame = ttk.Frame(root)
        prog_frame.pack(fill=tk.X, padx=12)

        self._progress = ttk.Progressbar(prog_frame, mode="indeterminate", length=200)
        self._progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self._status_lbl = ttk.Label(prog_frame, text="Prêt",
                                      font=("TkDefaultFont", 9))
        self._status_lbl.pack(side=tk.LEFT)

        # ── Result ────────────────────────────────────────────
        res_frame = ttk.LabelFrame(root, text="Résultat", padding=8)
        res_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self._result_text = tk.Text(res_frame, wrap=tk.WORD,
                                     font=("TkDefaultFont", 10))
        sb = ttk.Scrollbar(res_frame, command=self._result_text.yview)
        self._result_text.configure(yscrollcommand=sb.set)
        self._result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Export buttons ────────────────────────────────────
        exp_frame = ttk.Frame(root)
        exp_frame.pack(fill=tk.X, padx=12, pady=(0, 5))

        ttk.Button(exp_frame, text="💾 Sauvegarder Markdown",
                   command=self._save_md).pack(side=tk.LEFT, padx=4)
        ttk.Button(exp_frame, text="📄 Exporter PDF",
                   command=self._save_pdf).pack(side=tk.LEFT, padx=4)
        ttk.Button(exp_frame, text="📋 Copier",
                   command=self._copy).pack(side=tk.LEFT, padx=4)
        ttk.Button(exp_frame, text="🗑️ Effacer",
                   command=self._clear).pack(side=tk.RIGHT, padx=4)
        ttk.Button(exp_frame, text="🔍 Mettre à jour",
                   command=self._check_update).pack(side=tk.RIGHT, padx=4)

        # ── Q&A Section ───────────────────────────────────────
        qa_frame = ttk.LabelFrame(root, text="💬 Poser une question sur la vidéo", padding=6)
        qa_frame.pack(fill=tk.X, padx=12, pady=(0, 5))

        qa_row = ttk.Frame(qa_frame)
        qa_row.pack(fill=tk.X)
        self._qa_entry = ttk.Entry(qa_row, font=("TkDefaultFont", 10))
        self._qa_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self._qa_entry.bind("<Return>", lambda e: self._ask_qa())
        ttk.Button(qa_row, text="💬 Demander", command=self._ask_qa).pack(side=tk.LEFT)

        self._qa_history = tk.Text(qa_frame, height=4, wrap=tk.WORD,
                                    font=("TkDefaultFont", 9), state=tk.DISABLED,
                                    foreground="gray20")
        self._qa_history.pack(fill=tk.X, pady=(4, 0))

        # ── Image Generation Section ──────────────────────────
        img_frame = ttk.LabelFrame(root, text="🎨 Générer une image", padding=6)
        img_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        img_row = ttk.Frame(img_frame)
        img_row.pack(fill=tk.X)

        ttk.Label(img_row, text="Provider :").pack(side=tk.LEFT)
        providers = get_providers_list()
        provider_names = [f"{p['icon']} {p['name']}" for p in providers]
        self._img_provider_var = tk.StringVar(value=provider_names[0] if provider_names else "")
        ttk.Combobox(img_row, textvariable=self._img_provider_var,
                     values=provider_names, width=18, state="readonly").pack(side=tk.LEFT, padx=4)

        ttk.Label(img_row, text="Style :").pack(side=tk.LEFT, padx=(8, 0))
        styles = get_styles_list()
        style_names = [s['name'] for s in styles]
        self._img_style_var = tk.StringVar(value=style_names[0] if style_names else "")
        ttk.Combobox(img_row, textvariable=self._img_style_var,
                     values=style_names, width=14, state="readonly").pack(side=tk.LEFT, padx=4)

        ttk.Button(img_row, text="🚀 Générer", command=self._generate_image).pack(side=tk.LEFT, padx=8)

        self._img_url_var = tk.StringVar(value="")
        self._img_link_lbl = ttk.Label(img_frame, text="", foreground="blue",
                                        font=("TkDefaultFont", 9))
        self._img_link_lbl.pack(anchor=tk.W, pady=(2, 0))

        # ── Excalidraw Section ────────────────────────────────
        exc_frame = ttk.LabelFrame(root, text="📐 Schéma Excalidraw", padding=6)
        exc_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        exc_row = ttk.Frame(exc_frame)
        exc_row.pack(fill=tk.X)

        ttk.Button(exc_row, text="📐 Générer le schéma", command=self._generate_excalidraw).pack(side=tk.LEFT, padx=4)

        self._excalidraw_status = tk.StringVar(value="")
        ttk.Label(exc_frame, textvariable=self._excalidraw_status,
                  foreground="gray20", font=("TkDefaultFont", 9)).pack(anchor=tk.W, pady=(2, 0))

        # ── Video Generation Section ──────────────────────────────
        vid_frame = ttk.LabelFrame(root, text="🎬 Générer une vidéo", padding=6)
        vid_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        vid_row = ttk.Frame(vid_frame)
        vid_row.pack(fill=tk.X)

        ttk.Label(vid_row, text="Provider :").pack(side=tk.LEFT)
        vp_list = get_video_providers_list()
        vp_names = [f"{p['icon']} {p['name']}" for p in vp_list]
        self._vid_provider_var = tk.StringVar(value=vp_names[0] if vp_names else "")
        ttk.Combobox(vid_row, textvariable=self._vid_provider_var,
                     values=vp_names, width=20, state="readonly").pack(side=tk.LEFT, padx=4)

        self._vid_provider_var.trace_add("write", lambda *_: self._refresh_vid_models())

        ttk.Label(vid_row, text="Modèle :").pack(side=tk.LEFT, padx=(8, 0))
        self._vid_model_var = tk.StringVar()
        self._vid_model_combo = ttk.Combobox(vid_row, textvariable=self._vid_model_var,
                                              width=30, state="readonly")
        self._vid_model_combo.pack(side=tk.LEFT, padx=4)
        self._refresh_vid_models()

        ttk.Button(vid_row, text="🎬 Générer", command=self._generate_video).pack(side=tk.LEFT, padx=8)

        self._vid_url_var = tk.StringVar(value="")
        self._vid_link_lbl = ttk.Label(vid_frame, text="", foreground="blue",
                                        font=("TkDefaultFont", 9))
        self._vid_link_lbl.pack(anchor=tk.W, pady=(2, 0))

    # ── Helpers ───────────────────────────────────────────────

    def _center(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _set_status(self, text: str):
        self._status_lbl.config(text=text)
        self.root.update_idletasks()

    def _toggle_key(self):
        show = "" if self._key_entry.cget("show") == "*" else "*"
        self._key_entry.config(show=show)

    def _toggle_openai_key(self):
        show = "" if self._openai_entry.cget("show") == "*" else "*"
        self._openai_entry.config(show=show)

    def _refresh_openai_status(self):
        key = self.openai_key_var.get().strip()
        if key:
            self._openai_status.config(text="✅", foreground="green")
        elif config.OPENAI_API_KEY:
            self._openai_status.config(text="ℹ️.env", foreground="blue")
        else:
            self._openai_status.config(text="—", foreground="gray")

    def _active_openai_key(self) -> str:
        return self.openai_key_var.get().strip() or config.OPENAI_API_KEY

    def _refresh_key_status(self):
        key = self.api_key_var.get().strip()
        if key:
            self._key_status.config(text="✅ Clé saisie", foreground="green")
        elif config.OPENROUTER_API_KEY:
            self._key_status.config(text="ℹ️ Clé .env", foreground="blue")
        else:
            self._key_status.config(text="⚠️ Aucune clé", foreground="red")

    def _active_key(self) -> str:
        return self.api_key_var.get().strip() or config.OPENROUTER_API_KEY

    def _toggle_go_key(self):
        show = "" if self._go_key_entry.cget("show") == "*" else "*"
        self._go_key_entry.config(show=show)

    def _refresh_go_key_status(self):
        key = self.go_key_var.get().strip()
        if key:
            self._go_key_status.config(text="✅", foreground="green")
        elif config.OPENCODE_GO_API_KEY:
            self._go_key_status.config(text="ℹ️.env", foreground="blue")
        else:
            self._go_key_status.config(text="—", foreground="gray")

    def _active_go_key(self) -> str:
        return self.go_key_var.get().strip() or config.OPENCODE_GO_API_KEY

    def _active_api_key(self) -> str:
        return self._active_go_key() if self.provider == "opencode-go" else self._active_api_key()

    def _on_provider_change(self, event=None):
        sel = self.provider_var.get()
        old = self.provider
        self.provider = "opencode-go" if sel == "OpenCode Go" else "openrouter"
        if self.provider != old:
            self._refresh_model_list()
            if self.provider == "opencode-go":
                self._go_key_bar.pack(fill=tk.X, **{"padx": 12, "pady": (0, 6)})
            else:
                self._go_key_bar.pack_forget()

    def _output_language(self) -> str:
        return LANGUAGES.get(self.lang_var.get(), "Français")

    # ── Dynamic model loading ──────────────────────────────────

    def _load_models_async(self):
        self._set_status("⏳ Chargement des modèles…")
        threading.Thread(target=self._fetch_models, daemon=True).start()

    def _fetch_models(self):
        self._free_models = fetch_free_models()
        self._all_models  = fetch_all_models()
        from src.models import fetch_open_code_go_models
        self._go_models = fetch_open_code_go_models()
        self.root.after(0, self._refresh_model_list)

    def _refresh_model_list(self):
        if self.provider == "opencode-go":
            models = self._go_models
            names = sorted(models.keys())
        else:
            models = self._all_models if self.show_all_var.get() else self._free_models
            names = sorted(models.keys())

        if not names:
            return

        self._model_combo.config(values=names)

        current = self.model_var.get()
        if current not in names:
            if self.provider == "opencode-go":
                preferred = "deepseek-v4-flash"
            else:
                preferred = "meta-llama/llama-3.3-70b-instruct:free"
            self.model_var.set(preferred if preferred in names else names[0])

        if self.provider == "opencode-go":
            tag = f"⚡ {len(self._go_models)} modèles Go"
        else:
            tag = "" if self.show_all_var.get() else f"✅ {len(self._free_models)} gratuits"
        self._model_info.config(text=tag)
        self._set_status("Prêt")

    # ── File picker ───────────────────────────────────────────

    def _pick_file(self):
        path = filedialog.askopenfilename(filetypes=AUDIO_EXTS)
        if not path:
            return
        with open(path, "rb") as f:
            self._local_file_bytes = f.read()
        self._local_filename = os.path.basename(path)
        self._file_label.config(text=self._local_filename, foreground="black")
        self._btn_local.config(state=tk.NORMAL)

    # ── Guards ────────────────────────────────────────────────

    def _check_ready(self) -> bool:
        if self.is_processing:
            return False
        if not self._active_api_key():
            who = "OpenCode Go" if self.provider == "opencode-go" else "OpenRouter"
            messagebox.showerror("Clé manquante",
                                 f"Entrez votre clé {who} en haut de la fenêtre.")
            return False
        return True

    def _lock(self, btn):
        self.is_processing = True
        btn.config(state=tk.DISABLED)
        self._progress.start(12)
        self._result_text.delete("1.0", tk.END)
        self.current_result = ""
        self.current_title  = ""

    def _unlock(self, btn):
        self.is_processing = False
        btn.config(state=tk.NORMAL)
        self._progress.stop()

    # ── Analysis launchers ────────────────────────────────────

    def _start_url(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("URL manquante", "Entrez une URL.")
            return
        if not self._check_ready():
            return
        if extractor.detect_channel(url) or extractor.detect_playlist(url):
            self._set_status("📋 Récupération des vidéos...")
            threading.Thread(target=self._fetch_and_show_selection, args=(url,), daemon=True).start()
        else:
            self._lock(self._btn_url)
            threading.Thread(target=self._run_url, args=(url,), daemon=True).start()

    def _fetch_and_show_selection(self, url):
        """Fetch videos and display selection dialog."""
        try:
            is_channel = extractor.detect_channel(url)
            if is_channel:
                videos, channel_name = extractor.get_channel_videos(
                    url, max_videos=self.max_channel_var.get())
                vtype = "channel"
                list_title = channel_name
            else:
                videos = extractor.get_playlist_videos(url)
                vtype = "playlist"
                list_title = "Playlist"
            self.root.after(0, self._show_selection_dialog, url, videos, vtype, list_title)
        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    def _show_selection_dialog(self, url, videos, vtype, list_title):
        """Display a dialog with a video selection listbox."""
        win = tk.Toplevel(self.root)
        win.title(f"Sélection — {list_title[:50]}")
        win.geometry("620x520")
        win.transient(self.root)
        win.grab_set()

        icon = "📺" if vtype == "channel" else "📋"
        ttk.Label(win, text=f"{icon} {list_title}",
                  font=("TkDefaultFont", 12, "bold")).pack(pady=(10, 2))
        ttk.Label(win, text=f"{len(videos)} vidéo(s) trouvée(s) — Sélectionnez celles à analyser").pack(pady=(0, 6))

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        lb = tk.Listbox(frame, selectmode=tk.MULTIPLE, font=("TkDefaultFont", 10))
        sb = ttk.Scrollbar(frame, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for v in videos:
            lb.insert(tk.END, v["title"])
        lb.selection_set(0, tk.END)

        btn_row = ttk.Frame(win)
        btn_row.pack(fill=tk.X, padx=10, pady=4)

        ttk.Button(btn_row, text="✅ Tout", command=lambda: lb.selection_set(0, tk.END)).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="❌ Rien", command=lambda: lb.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=3)

        count_lbl = ttk.Label(btn_row, text=f"{lb.size()} sélectionnée(s)")
        count_lbl.pack(side=tk.RIGHT, padx=6)

        def on_select(_=None):
            n = len(lb.curselection())
            count_lbl.config(text=f"{n} sélectionnée(s)")
        lb.bind("<<ListboxSelect>>", on_select)

        def analyze():
            indices = lb.curselection()
            if not indices:
                messagebox.showwarning("Sélection vide", "Sélectionnez au moins une vidéo.")
                return
            selected = [videos[i] for i in indices]
            win.destroy()
            if vtype == "channel":
                threading.Thread(target=self._run_channel, args=(url, selected), daemon=True).start()
            else:
                threading.Thread(target=self._run_playlist, args=(url, selected), daemon=True).start()

        bot_row = ttk.Frame(win)
        bot_row.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(bot_row, text="🚀 Analyser la sélection", command=analyze).pack(side=tk.LEFT, padx=4)
        ttk.Button(bot_row, text="↩ Annuler", command=win.destroy).pack(side=tk.RIGHT, padx=4)

    def _start_local(self):
        if not self._local_file_bytes:
            return
        if not self._check_ready():
            return
        self._lock(self._btn_local)
        threading.Thread(target=self._run_local, daemon=True).start()

    # ── Pipeline ──────────────────────────────────────────────

    def _run_url(self, url: str):
        try:
            model        = self.model_var.get()
            chunk_size   = self.chunk_var.get()
            overlap      = max(100, chunk_size // 10)
            force_w      = self.force_whisper_var.get()
            w_lang       = self.whisper_lang_var.get()
            w_model      = self.whisper_model_var.get()
            lang_out     = self._output_language()
            api_key      = self._active_api_key()

            transcript_data = None

            if not force_w:
                try:
                    self._status("📥 Extraction du transcript…")
                    transcript_data = extractor.get_transcript(url)
                    if not transcript_data.get("transcript"):
                        transcript_data = None
                except Exception:
                    transcript_data = None

            if transcript_data is None:
                from src.whisper_transcriber import transcribe_url
                self._status("🎙️ Téléchargement + transcription Whisper…")
                transcript_data = transcribe_url(
                    url,
                    language=w_lang if w_lang != "auto" else None,
                    model_size=w_model,
                    openai_api_key=self._active_openai_key(),
                )

            transcript = transcript_data["transcript"]
            title      = transcript_data.get("title", "Video")
            duration   = transcript_data.get("total_duration_minutes", 0)
            self._status(f"📺 {title} — {duration:.1f} min — {len(transcript)} segments")

            self.current_transcript = "\n".join(
                f"[{int(e['start']//60)}:{int(e['start']%60):02d}] {e.get('text', '')}"
                for e in transcript
            )

            result = self._pipeline(transcript, title, model, chunk_size, overlap,
                                    api_key, lang_out)
            self.root.after(0, self._show_result, result, title)

        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    def _run_local(self):
        try:
            from src.whisper_transcriber import transcribe_local_file
            model      = self.model_var.get()
            chunk_size = self.chunk_var.get()
            overlap    = max(100, chunk_size // 10)
            w_lang     = self.whisper_lang_var.get()
            w_model    = self.whisper_model_var.get()
            lang_out   = self._output_language()
            api_key    = self._active_api_key()

            self._status(f"🎙️ Transcription de {self._local_filename}…")
            transcript_data = transcribe_local_file(
                self._local_file_bytes,
                self._local_filename,
                language=w_lang if w_lang != "auto" else None,
                model_size=w_model,
                openai_api_key=self._active_openai_key(),
            )

            transcript = transcript_data["transcript"]
            title      = transcript_data.get("title", self._local_filename)
            duration   = transcript_data.get("total_duration_minutes", 0)
            self._status(f"✅ {title} — {duration:.1f} min — {len(transcript)} segments")

            self.current_transcript = "\n".join(
                f"[{int(e['start']//60)}:{int(e['start']%60):02d}] {e.get('text', '')}"
                for e in transcript
            )

            result = self._pipeline(transcript, title, model, chunk_size, overlap,
                                    api_key, lang_out)
            self.root.after(0, self._show_result, result, title)

        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    # ── Q&A ───────────────────────────────────────────────────

    def _ask_qa(self):
        question = self._qa_entry.get().strip()
        if not question or not self.current_transcript:
            return
        api_key = self._active_api_key()
        model = self.model_var.get()
        if self.provider == "opencode-go":
            fallbacks = []
        else:
            free_models = list(self._free_models.keys())
            fallbacks = [m for m in free_models if m != model]

        prompt = (
            "Tu es un assistant spécialisé dans l'analyse de contenu vidéo.\n"
            "Voici le transcript complet d'une vidéo :\n\n"
            f"{self.current_transcript}\n\n"
            "Réponds à la question suivante en te basant UNIQUEMENT sur le transcript ci-dessus.\n"
            "Si la réponse ne se trouve pas dans le transcript, dis-le clairement.\n"
            "Utilise des timestamps [min:sec] quand tu cites des passages précis.\n\n"
            f"Question : {question}"
        )

        if len(prompt) > 120000:
            prompt = prompt[:60000] + "\n...[transcript tronqué]...\n" + prompt[-60000:]

        def _body():
            try:
                answer = analyzer.call_llm(
                    prompt, model=model, max_tokens=3000,
                    api_key=api_key, fallback_models=fallbacks,
                    provider=self.provider,
                )
                self.root.after(0, self._show_qa_answer, question, answer)
            except Exception as e:
                self.root.after(0, self._show_qa_error, str(e))

        self._set_status("🤖 Réflexion...")
        threading.Thread(target=_body, daemon=True).start()

    def _show_qa_answer(self, question: str, answer: str):
        self.chat_history.append({"question": question, "answer": answer})
        self._qa_entry.delete(0, tk.END)
        self._refresh_qa_display()
        self._set_status("✅ Question répondue")

    def _show_qa_error(self, error: str):
        self._refresh_qa_display()
        self._set_status("❌ Erreur Q&A")

    def _refresh_qa_display(self):
        self._qa_history.config(state=tk.NORMAL)
        self._qa_history.delete("1.0", tk.END)
        for qa in self.chat_history[-5:]:  # Show last 5 exchanges
            self._qa_history.insert(tk.END, f"🧑 Vous : {qa['question']}\n")
            self._qa_history.insert(tk.END, f"🤖 {qa['answer'][:200]}{'...' if len(qa['answer']) > 200 else ''}\n")
            self._qa_history.insert(tk.END, "-" * 40 + "\n")
        self._qa_history.config(state=tk.DISABLED)

    # ── Excalidraw Generation ─────────────────────────────────

    def _generate_excalidraw(self):
        if not self.current_result:
            messagebox.showwarning("Aucun résultat", "Analysez d'abord une vidéo.")
            return
        api_key = self._active_api_key()

        def _body():
            try:
                self._set_status("📐 Génération du schéma Excalidraw...")
                result = generate_excalidraw(self.current_result, self.current_title, api_key=api_key)
                self.root.after(0, self._show_excalidraw_result, result)
            except Exception as e:
                self.root.after(0, self._show_excalidraw_error, str(e))

        threading.Thread(target=_body, daemon=True).start()

    def _show_excalidraw_result(self, result: dict):
        if result.get('success'):
            json_str = result['diagram_json']
            fname = f"{self.current_title[:40]}_schema.excalidraw"
            path = filedialog.asksaveasfilename(
                defaultextension=".excalidraw",
                initialfile=fname,
                filetypes=[("Excalidraw", "*.excalidraw"), ("JSON", "*.json")],
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(json_str)
                n = len(result.get("concepts", []))
                self._excalidraw_status.set(f"✅ Schéma sauvegardé ({n} concepts)")
                self._set_status(f"✅ Schéma Excalidraw sauvegardé")
            else:
                self._excalidraw_status.set("⚠️ Sauvegarde annulée")
                self._set_status("Prêt")
        else:
            self._excalidraw_status.set(f"❌ {result.get('error', 'Erreur inconnue')}")
            self._set_status("❌ Erreur génération schéma")

    def _show_excalidraw_error(self, msg: str):
        self._excalidraw_status.set(f"❌ {msg}")
        self._set_status("❌ Erreur génération schéma")

    # ── Video Generation Helpers ──────────────────────────────

    def _refresh_vid_models(self):
        label = self._vid_provider_var.get()
        vp_list = get_video_providers_list()
        provider_id = None
        for p in vp_list:
            if f"{p['icon']} {p['name']}" == label:
                provider_id = p['id']
                break
        if provider_id:
            models = next((p['models'] for p in vp_list if p['id'] == provider_id), [])
            self._vid_model_combo.config(values=models)
            if models:
                self._vid_model_var.set(models[0])

    def _generate_video(self):
        if not self.current_result:
            messagebox.showwarning("Aucun résultat", "Analysez d'abord une vidéo.")
            return

        provider_label = self._vid_provider_var.get()
        vp_list = get_video_providers_list()
        provider_id = None
        for p in vp_list:
            if f"{p['icon']} {p['name']}" == provider_label:
                provider_id = p['id']
                break
        if not provider_id:
            provider_id = "replicate-video"

        model = self._vid_model_var.get()
        api_key = self._active_api_key()
        rep_key = os.getenv("REPLICATE_API_KEY", "") or os.getenv("STABILITY_API_KEY", "")
        api_key = rep_key or api_key

        if not api_key:
            messagebox.showerror("Clé manquante", "Configurez une clé Replicate dans le .env")
            return

        def _body():
            try:
                self._set_status("🎬 Génération vidéo... (1-2 min)")
                prompt = build_video_prompt(self.current_result, self.current_title)
                result = generate_video(prompt, provider=provider_id, model=model, api_key=api_key)
                self.root.after(0, self._show_video_result, result)
            except Exception as e:
                self.root.after(0, self._show_video_error, str(e))

        threading.Thread(target=_body, daemon=True).start()

    def _show_video_result(self, result: dict):
        if result.get('success'):
            url = result['video_url']
            self._vid_url_var.set(url)
            self._vid_link_lbl.config(
                text=f"✅ Vidéo générée ! Ouvrir le lien :\n{url}",
                cursor="hand2",
            )
            self._set_status("✅ Vidéo générée !")
            import webbrowser
            webbrowser.open(url)
        else:
            self._vid_link_lbl.config(
                text=f"❌ {result.get('error', 'Erreur inconnue')}",
                foreground="red",
            )
            self._set_status("❌ Erreur génération vidéo")

    def _show_video_error(self, msg: str):
        self._vid_link_lbl.config(text=f"❌ {msg}", foreground="red")
        self._set_status("❌ Erreur génération vidéo")

    # ── Image Generation ──────────────────────────────────────

    def _generate_image(self):
        if not self.current_result:
            messagebox.showwarning("Aucun résultat", "Analysez d'abord une vidéo.")
            return
        api_key = self._active_api_key()
        provider_label = self._img_provider_var.get()
        providers = get_providers_list()
        provider_id = None
        for p in providers:
            if f"{p['icon']} {p['name']}" == provider_label:
                provider_id = p['id']
                break
        if not provider_id:
            provider_id = "flux"

        style_id = self._img_style_var.get().lower()
        style_map = {s['name']: s['id'] for s in get_styles_list()}
        style_id = style_map.get(style_id, "realistic")

        def _body():
            try:
                self._set_status("🎨 Génération de l'image...")
                prompt = build_image_prompt(self.current_result, self.current_title, style=style_id)
                result = generate_image(prompt, provider=provider_id, api_key=api_key)
                self.root.after(0, self._show_image_result, result)
            except Exception as e:
                self.root.after(0, self._show_qa_error, f"Erreur image: {str(e)}")

        threading.Thread(target=_body, daemon=True).start()

    def _show_image_result(self, result: dict):
        if result.get('success'):
            url = result['image_url']
            self._img_url_var.set(url)
            self._img_link_lbl.config(
                text=f"✅ Image générée ! Ouvrir le lien :\n{url}",
                cursor="hand2",
            )
            self._set_status("✅ Image générée !")
        else:
            self._img_link_lbl.config(
                text=f"❌ {result.get('error', 'Erreur inconnue')}",
                foreground="red",
            )
            self._set_status("❌ Erreur génération image")

    # ── Playlist ──────────────────────────────────────────────

    def _run_playlist(self, url: str, videos=None):
        try:
            model      = self.model_var.get()
            chunk_size = self.chunk_var.get()
            overlap    = max(100, chunk_size // 10)
            force_w    = self.force_whisper_var.get()
            w_lang     = self.whisper_lang_var.get()
            w_model    = self.whisper_model_var.get()
            lang_out   = self._output_language()
            api_key    = self._active_api_key()

            if videos is None:
                self._status("📋 Récupération des vidéos de la playlist...")
                videos = extractor.get_playlist_videos(url)
            total = len(videos)
            playlist_title = f"Playlist ({total} vidéos)"
            all_results = []
            warnings = []

            for idx, video in enumerate(videos):
                video_url = video['url']
                video_title = video['title']
                self._status(f"[{idx+1}/{total}] 📥 {video_title}")
                try:
                    result, title, w, _ = self._run_single_video(
                        video_url, model, chunk_size, overlap,
                        force_w, w_lang, w_model, lang_out, api_key,
                    )
                    all_results.append(f"## 📺 Vidéo {idx+1} : {title}\n\n{result}\n\n---\n")
                    for warn in w:
                        warnings.append(f"[{video_title}] {warn}")
                except Exception as e:
                    warnings.append(f"[{video_title}] Erreur : {str(e)}")
                    all_results.append(f"## 📺 Vidéo {idx+1} : {video_title}\n\n⚠️ Erreur\n\n---\n")

            combined = f"# 📋 Rapport de la playlist : {playlist_title}\n\n" + "\n".join(all_results)
            self.root.after(0, self._show_result, combined, playlist_title)

        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    def _run_channel(self, url: str, videos=None):
        try:
            model      = self.model_var.get()
            chunk_size = self.chunk_var.get()
            overlap    = max(100, chunk_size // 10)
            force_w    = self.force_whisper_var.get()
            w_lang     = self.whisper_lang_var.get()
            w_model    = self.whisper_model_var.get()
            lang_out   = self._output_language()
            api_key    = self._active_api_key()
            max_videos = self.max_channel_var.get()

            if videos is None:
                self._status("📋 Récupération des vidéos de la chaîne...")
                videos, channel_name = extractor.get_channel_videos(url, max_videos=max_videos)
            else:
                channel_name = f"Chaîne ({len(videos)} vidéos sélectionnées)"
            total = len(videos)
            all_results = []
            warnings = []

            for idx, video in enumerate(videos):
                video_url = video['url']
                video_title = video['title']
                self._status(f"[{idx+1}/{total}] 📥 {video_title}")
                try:
                    result, title, w, _ = self._run_single_video(
                        video_url, model, chunk_size, overlap,
                        force_w, w_lang, w_model, lang_out, api_key,
                    )
                    all_results.append(f"## 📺 Vidéo {idx+1} : {title}\n\n{result}\n\n---\n")
                    for warn in w:
                        warnings.append(f"[{video_title}] {warn}")
                except Exception as e:
                    warnings.append(f"[{video_title}] Erreur : {str(e)}")
                    all_results.append(f"## 📺 Vidéo {idx+1} : {video_title}\n\n⚠️ Erreur\n\n---\n")

            combined = f"# 📺 Rapport de la chaîne : {channel_name}\n\n" + "\n".join(all_results)
            self.root.after(0, self._show_result, combined, channel_name)

        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    def _run_single_video(self, url, model, chunk_size, overlap, force_w,
                          w_lang, w_model, lang_out, api_key):
        """Analyze a single video. Returns (result, title, warnings, transcript_text)."""
        warnings = []
        transcript_data = None

        if not force_w:
            try:
                transcript_data = extractor.get_transcript(url)
                if not transcript_data.get("transcript"):
                    transcript_data = None
            except Exception:
                transcript_data = None

        if transcript_data is None:
            from src.whisper_transcriber import transcribe_url
            transcript_data = transcribe_url(
                url,
                language=w_lang if w_lang != "auto" else None,
                model_size=w_model,
                openai_api_key=self._active_openai_key(),
            )

        transcript = transcript_data["transcript"]
        title = transcript_data.get("title", "Video")
        duration = transcript_data.get("total_duration_minutes", 0)

        result = self._pipeline(transcript, title, model, chunk_size, overlap, api_key, lang_out)

        transcript_text = "\n".join(
            f"[{int(e['start']//60)}:{int(e['start']%60):02d}] {e.get('text', '')}"
            for e in transcript
        )
        return result, title, warnings, transcript_text

    def _pipeline(self, transcript, title, model, chunk_size, overlap,
                  api_key, lang_out) -> str:
        # Build fallback list from free models (excluding the selected one)
        if self.provider == "opencode-go":
            fallbacks = []
        else:
            free_models = list(self._free_models.keys())
            fallbacks = [m for m in free_models if m != model]

        self._status("✂️ Découpage en chunks…")
        chunks = chunker.chunk_transcript(transcript, max_tokens=chunk_size,
                                          overlap_tokens=overlap, model=model)
        self._status(chunker.get_chunk_count_info(chunks))

        analyses = []
        for i, chunk in enumerate(chunks):
            self._status(f"🤖 Analyse chunk {i+1}/{len(chunks)}…")
            analyses.append(
                analyzer.analyze_chunk(chunk["text"], title, model=model,
                                       api_key=api_key, output_language=lang_out,
                                       fallback_models=fallbacks,
                                       provider=self.provider)
            )
            if len(chunks) > 1:
                time.sleep(1)

        if len(analyses) > 1:
            self._status("🔗 Fusion des analyses…")
            return fusion.fusion_analyses(analyses, title, model, api_key=api_key,
                                          output_language=lang_out, fallback_models=fallbacks,
                                          provider=self.provider)
        return analyses[0]

    def _status(self, text: str):
        self.root.after(0, self._set_status, text)

    # ── Result / error display ────────────────────────────────

    def _show_result(self, result: str, title: str):
        self._unlock(self._btn_url)
        self._unlock(self._btn_local)
        self._set_status("✅ Terminé !")
        self.current_result = result
        self.current_title  = title
        self._result_text.delete("1.0", tk.END)
        self._result_text.insert("1.0", result)

        # Reset Q&A
        self.chat_history = []
        self._qa_history.config(state=tk.NORMAL)
        self._qa_history.delete("1.0", tk.END)
        self._qa_history.config(state=tk.DISABLED)
        self._qa_entry.delete(0, tk.END)

        # Reset image
        self._img_url_var.set("")
        self._img_link_lbl.config(text="")

        # Reset excalidraw
        self._excalidraw_status.set("")

        # Reset video
        self._vid_url_var.set("")
        self._vid_link_lbl.config(text="")

    def _show_error(self, msg: str):
        self._unlock(self._btn_url)
        self._unlock(self._btn_local)
        self._set_status("❌ Erreur")
        messagebox.showerror("Erreur", msg)

    # ── Export ────────────────────────────────────────────────

    def _save_md(self):
        content = self._result_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Vide", "Aucun résultat à sauvegarder.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=f"{self.current_title[:40]}_analyse.md",
            filetypes=[("Markdown", "*.md"), ("Texte", "*.txt")],
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._set_status(f"💾 Sauvegardé : {os.path.basename(path)}")

    def _save_pdf(self):
        content = self._result_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Vide", "Aucun résultat à exporter.")
            return
        try:
            from src.pdf_exporter import export_to_pdf
            pdf_bytes = export_to_pdf(content, self.current_title)
        except Exception as e:
            messagebox.showerror("PDF", f"Export PDF impossible : {e}")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=f"{self.current_title[:40]}_analyse.pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if path:
            with open(path, "wb") as f:
                f.write(pdf_bytes)
            self._set_status(f"📄 PDF exporté : {os.path.basename(path)}")

    def _copy(self):
        content = self._result_text.get("1.0", tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self._set_status("📋 Copié dans le presse-papier")

    def _clear(self):
        self._result_text.delete("1.0", tk.END)
        self.current_result = ""
        self.current_title  = ""
        self.current_transcript = ""
        self.chat_history = []
        self._qa_history.config(state=tk.NORMAL)
        self._qa_history.delete("1.0", tk.END)
        self._qa_history.config(state=tk.DISABLED)
        self._qa_entry.delete(0, tk.END)
        self._img_url_var.set("")
        self._img_link_lbl.config(text="")
        self._excalidraw_status.set("")
        self._vid_url_var.set("")
        self._vid_link_lbl.config(text="")
        self.url_var.set("")
        self._set_status("Prêt")

    # ── Update ─────────────────────────────────────────────────

    def _check_update(self):
        def _body():
            self._set_status("🔍 Vérification des mises à jour...")
            info = updater.check_update()
            self.root.after(0, self._show_update_result, info)

        threading.Thread(target=_body, daemon=True).start()

    def _show_update_result(self, info: updater.UpdateInfo):
        if info.error:
            messagebox.showerror("Mise à jour", info.error)
            self._set_status("❌ Échec vérification mise à jour")
            return

        if info.available:
            msg = (
                f"Version actuelle : {info.current_version}\n"
                f"Nouvelle version : {info.latest_version}\n\n"
                f"Notes de version :\n{info.release_notes[:600]}"
            )
            answer = messagebox.askyesno(
                "Mise à jour disponible",
                msg + "\n\nSouhaitez-vous mettre à jour ?",
            )
            if answer:
                self._perform_update(info)
            else:
                self._set_status("Mise à jour ignorée")
        else:
            messagebox.showinfo("Mise à jour", f"✅ Vous êtes à jour !\n\nVersion : {info.current_version}")
            self._set_status("✅ À jour")

    def _perform_update(self, info: updater.UpdateInfo):
        mode = updater.detect_install_mode()

        if mode == "git":
            self._set_status("⬇️ Mise à jour via git...")
            def _git():
                ok = updater.perform_git_pull()
                self.root.after(0, lambda: self._update_done(ok, "git pull terminé" if ok else "Échec git pull"))
            threading.Thread(target=_git, daemon=True).start()

        elif mode == "desktop":
            self._set_status("🔗 Ouverture de la page de téléchargement...")
            import webbrowser
            webbrowser.open(info.release_url)
            self._set_status("Prêt")

        elif mode == "docker":
            self._set_status("⬇️ Pull de l'image Docker...")
            def _docker():
                ok = updater.perform_docker_pull()
                self.root.after(0, lambda: self._update_done(ok, "Image Docker mise à jour" if ok else "Échec pull Docker"))
            threading.Thread(target=_docker, daemon=True).start()

        else:
            import webbrowser
            webbrowser.open(info.release_url)
            self._set_status("Prêt")

    def _update_done(self, ok: bool, msg: str):
        if ok:
            messagebox.showinfo("Mise à jour", f"✅ {msg}\n\nRedémarrez l'application.")
            self._set_status(f"✅ {msg}")
        else:
            messagebox.showerror("Mise à jour", f"❌ {msg}")
            self._set_status(f"❌ {msg}")


# ──────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
