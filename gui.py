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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from src import extractor, chunker, analyzer, fusion
from src.models import fetch_free_models, fetch_all_models
from src.image_generator import generate_image, get_providers_list, get_styles_list, build_image_prompt
from src.excalidraw_generator import generate_diagram as generate_excalidraw

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

    def _output_language(self) -> str:
        return LANGUAGES.get(self.lang_var.get(), "Français")

    # ── Dynamic model loading ──────────────────────────────────

    def _load_models_async(self):
        self._set_status("⏳ Chargement des modèles…")
        threading.Thread(target=self._fetch_models, daemon=True).start()

    def _fetch_models(self):
        self._free_models = fetch_free_models()
        self._all_models  = fetch_all_models()
        self.root.after(0, self._refresh_model_list)

    def _refresh_model_list(self):
        models = self._all_models if self.show_all_var.get() else self._free_models
        if not models:
            return

        names = sorted(models.keys())
        self._model_combo.config(values=names)

        current = self.model_var.get()
        if current not in names:
            # Pick best default: prefer llama-3.3-70b:free
            preferred = "meta-llama/llama-3.3-70b-instruct:free"
            self.model_var.set(preferred if preferred in names else names[0])

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
        if not self._active_key():
            messagebox.showerror("Clé manquante",
                                 "Entrez votre clé OpenRouter en haut de la fenêtre.")
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
        self._lock(self._btn_url)
        if extractor.detect_playlist(url):
            threading.Thread(target=self._run_playlist, args=(url,), daemon=True).start()
        else:
            threading.Thread(target=self._run_url, args=(url,), daemon=True).start()

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
            api_key      = self._active_key()

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
            api_key    = self._active_key()

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
        api_key = self._active_key()
        model = self.model_var.get()
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
        api_key = self._active_key()

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

    # ── Image Generation ──────────────────────────────────────

    def _generate_image(self):
        if not self.current_result:
            messagebox.showwarning("Aucun résultat", "Analysez d'abord une vidéo.")
            return
        api_key = self._active_key()
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

    def _run_playlist(self, url: str):
        try:
            model      = self.model_var.get()
            chunk_size = self.chunk_var.get()
            overlap    = max(100, chunk_size // 10)
            force_w    = self.force_whisper_var.get()
            w_lang     = self.whisper_lang_var.get()
            w_model    = self.whisper_model_var.get()
            lang_out   = self._output_language()
            api_key    = self._active_key()

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
                                       fallback_models=fallbacks)
            )
            if len(chunks) > 1:
                time.sleep(1)

        if len(analyses) > 1:
            self._status("🔗 Fusion des analyses…")
            return fusion.fusion_analyses(analyses, title, model, api_key=api_key,
                                          output_language=lang_out, fallback_models=fallbacks)
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
        self.url_var.set("")
        self._set_status("Prêt")


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
