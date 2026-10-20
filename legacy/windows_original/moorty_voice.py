import asyncio
import queue
import threading
import time
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import edge_tts
import pygame
import tempfile
import os
import webbrowser
import inspect

APP_TITLE = "Moorty Voice | YouTube + TikTok"
SUBSCRIBER_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
DEFAULT_VOICE = "es-MX-DaliaNeural"
VOICES = {
    "Español México — femenina": "es-MX-DaliaNeural",
    "Español México — masculina": "es-MX-JorgeNeural",
    "Español España — femenina": "es-ES-ElviraNeural",
    "Español España — masculina": "es-ES-AlvaroNeural",
}

class YouTubeChatReader:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("920x980")
        self.root.minsize(760, 800)

        self.stop_event = threading.Event()
        self.worker = None
        self.speech_queue = queue.Queue()
        self.latest_only_var = tk.BooleanVar(value=True)
        # Activado por defecto: si la voz se atrasa, se prioriza el aviso más reciente.
        self.recent_messages_only_var = tk.BooleanVar(value=True)
        self.voice_muted_var = tk.BooleanVar(value=False)
        self.speech_worker = None
        self.active_video_id = None
        self.active_chat_id = None
        self.last_message_ids = set()
        # Evita que eventos retransmitidos por reconexiones generen voz duplicada.
        self.recent_event_times = {}
        self.recent_speech_times = {}
        self.dedupe_lock = threading.Lock()
        self.api = None
        self.subscriber_api = None
        self.oauth_client_file = None
        self.subscriber_worker = None
        self.subscriber_stop_event = threading.Event()
        self.tiktok_client = None
        self.platform_var = tk.StringVar(value="TikTok")
        self.tiktok_account_var = tk.StringVar(value="@moorty_yt")
        # Sonidos de entrada exclusivos de TikTok; no se conectan al flujo de YouTube.
        self.tiktok_join_sound_general = tk.StringVar(value="")
        self.tiktok_join_sound_subscriber = tk.StringVar(value="")
        self.tiktok_join_sound_volume = tk.DoubleVar(value=70)
        # Eventos configurables de TikTok LIVE (por defecto todos activados).
        self.tiktok_event_vars = {
            "comments": tk.BooleanVar(value=True),
            "gifts": tk.BooleanVar(value=True),
            "likes": tk.BooleanVar(value=True),
            "follows": tk.BooleanVar(value=True),
            "shares": tk.BooleanVar(value=True),
            "joins": tk.BooleanVar(value=True),
        }

        self.api_key_var = tk.StringVar()
        self.channel_var = tk.StringVar()
        self.voice_var = tk.StringVar(value="Español México — femenina")
        self.rate_var = tk.StringVar(value="+0%")
        self.volume_var = tk.StringVar(value="+0%")
        self.status_var = tk.StringVar(value="Listo. Introduce tu API key y el ID del canal.")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        # Dark gaming-inspired UI (Tkinter/ttk; no extra UI dependency required).
        self.bg = "#0b0b0f"
        self.panel = "#15151c"
        self.panel2 = "#1d1d26"
        self.red = "#e11d36"
        self.red_hover = "#ff334d"
        self.fg = "#f4f4f5"
        self.muted = "#a1a1aa"
        self.root.configure(bg=self.bg)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=self.bg, foreground=self.fg, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.bg)
        style.configure("Panel.TFrame", background=self.panel)
        style.configure("TLabel", background=self.bg, foreground=self.fg)
        style.configure("Muted.TLabel", background=self.bg, foreground=self.muted)
        style.configure("Panel.TLabel", background=self.panel, foreground=self.fg)
        style.configure("Title.TLabel", background=self.bg, foreground="#ffffff", font=("Segoe UI", 23, "bold"))
        style.configure("Subtitle.TLabel", background=self.bg, foreground=self.muted, font=("Segoe UI", 9, "bold"))
        style.configure("Section.TLabel", background=self.panel, foreground="#ffffff", font=("Segoe UI", 11, "bold"))
        style.configure("TEntry", fieldbackground="#0f0f14", foreground=self.fg, insertcolor=self.fg,
                        bordercolor="#343440", lightcolor="#343440", darkcolor="#343440", padding=8)
        style.configure("TCombobox", fieldbackground="#0f0f14", background=self.panel2,
                        foreground=self.fg, arrowcolor=self.red, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", "#0f0f14")],
                  foreground=[("readonly", self.fg)], selectbackground=[("readonly", self.red)],
                  selectforeground=[("readonly", "#ffffff")])
        style.configure("TButton", background=self.panel2, foreground=self.fg, padding=(13, 9),
                        borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("TButton", background=[("active", "#30303b"), ("disabled", "#25252d")],
                  foreground=[("disabled", "#777780")])
        style.configure("Accent.TButton", background=self.red, foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", self.red_hover), ("disabled", "#64232d")],
                  foreground=[("disabled", "#c7aeb1")])

        # Contenedor desplazable para poder recorrer toda la configuración con la rueda.
        scroll_host = tk.Frame(self.root, bg=self.bg)
        scroll_host.pack(fill="both", expand=True)
        self.main_canvas = tk.Canvas(scroll_host, bg=self.bg, highlightthickness=0, bd=0)
        self.main_scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=self.main_canvas.yview)
        self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)
        self.main_scrollbar.pack(side="right", fill="y")
        self.main_canvas.pack(side="left", fill="both", expand=True)
        outer = ttk.Frame(self.main_canvas, padding=(22, 18, 22, 14))
        self._outer_window = self.main_canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>", lambda _e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all")))
        self.main_canvas.bind("<Configure>", lambda e: self.main_canvas.itemconfigure(self._outer_window, width=e.width))
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_mousewheel_linux, add="+")
        self.root.bind_all("<Button-5>", self._on_mousewheel_linux, add="+")

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 16))
        logo = tk.Canvas(header, width=54, height=54, bg=self.bg, highlightthickness=0)
        logo.pack(side="left", padx=(0, 13))
        logo.create_rectangle(3, 3, 51, 51, fill=self.red, outline=self.red)
        logo.create_text(27, 27, text="TV", fill="white", font=("Segoe UI", 17, "bold"))
        titlebox = ttk.Frame(header)
        titlebox.pack(side="left", fill="x", expand=True)
        ttk.Label(titlebox, text="MOORTY VOICE", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titlebox, text="YOUTUBE + TIKTOK LIVE  •  WINDOWS / OBS", style="Subtitle.TLabel").pack(anchor="w", pady=(1, 0))
        self.status_pill = tk.Label(header, text="● OFFLINE", bg="#32151b", fg="#ff6577",
                                    font=("Segoe UI", 9, "bold"), padx=12, pady=7)
        self.status_pill.pack(side="right", anchor="n")

        ttk.Label(outer, text="Elige plataforma y cuenta; Moorty Voice leerá eventos en voz alta.", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))

        # Platform/account selector
        selector = tk.Frame(outer, bg=self.panel, highlightbackground="#2c2c36", highlightthickness=1)
        selector.pack(fill="x", pady=(0, 12))
        tk.Label(selector, text="PLATAFORMA", bg=self.panel, fg=self.muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", padx=(13, 8), pady=(10, 3))
        tk.Label(selector, text="CUENTA TIKTOK", bg=self.panel, fg=self.muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w", padx=8, pady=(10, 3))
        platform_box = ttk.Combobox(selector, textvariable=self.platform_var, values=["TikTok", "YouTube"], state="readonly", width=18)
        platform_box.grid(row=1, column=0, sticky="ew", padx=(13, 8), pady=(0, 10))
        account_box = ttk.Combobox(selector, textvariable=self.tiktok_account_var, values=["@moorty_yt", "@tocolita"], state="readonly", width=24)
        account_box.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 10))
        selector.columnconfigure(0, weight=1)
        selector.columnconfigure(1, weight=2)

        # TikTok event toggles
        event_card = tk.Frame(outer, bg=self.panel, highlightbackground="#2c2c36", highlightthickness=1)
        event_card.pack(fill="x", pady=(0, 12))
        tk.Label(event_card, text="  EVENTOS DE TIKTOK LIVE", bg=self.panel, fg=self.fg,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(event_card, text="Activa los avisos que quieres escuchar. TikTok solo puede entregar los eventos que expone en ese directo.",
                 bg=self.panel, fg=self.muted, font=("Segoe UI", 8), anchor="w", wraplength=850,
                 justify="left").pack(fill="x", padx=14, pady=(0, 5))
        event_row = tk.Frame(event_card, bg=self.panel)
        event_row.pack(fill="x", padx=10, pady=(0, 10))
        event_labels = [("comments", "Comentarios"), ("gifts", "Regalos"), ("likes", "Likes"),
                        ("follows", "Nuevos seguidores"), ("shares", "Compartidos"), ("joins", "Entradas")]
        for key, label in event_labels:
            tk.Checkbutton(event_row, text=label, variable=self.tiktok_event_vars[key],
                           bg=self.panel, fg=self.fg, activebackground=self.panel, activeforeground="#ffffff",
                           selectcolor="#30303b", font=("Segoe UI", 9), relief="flat", bd=0,
                           highlightthickness=0).pack(side="left", padx=(4, 10), pady=2)

        # Custom join sounds: TikTok only. YouTube event/voice paths remain untouched.
        join_sound_card = tk.Frame(outer, bg=self.panel, highlightbackground="#2c2c36", highlightthickness=1)
        join_sound_card.pack(fill="x", pady=(0, 12))
        tk.Label(join_sound_card, text="  SONIDOS DE ENTRADA — SOLO TIKTOK", bg=self.panel, fg=self.fg,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(join_sound_card,
                 text="Elige un archivo de audio para entradas normales y otro para suscriptores. Si TikTokLive no informa de forma fiable la suscripción, no se asumirá ninguna categoría.",
                 bg=self.panel, fg=self.muted, font=("Segoe UI", 8), anchor="w", wraplength=850,
                 justify="left").pack(fill="x", padx=14, pady=(0, 8))
        for label, var, kind in (
            ("Entrada normal / no suscriptor", self.tiktok_join_sound_general, "general"),
            ("Suscriptor", self.tiktok_join_sound_subscriber, "subscriber"),
        ):
            sound_row = tk.Frame(join_sound_card, bg=self.panel)
            sound_row.pack(fill="x", padx=14, pady=3)
            tk.Label(sound_row, text=label, bg=self.panel, fg=self.fg, width=27, anchor="w").pack(side="left")
            ttk.Entry(sound_row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
            ttk.Button(sound_row, text="Elegir archivo", command=lambda v=var: self.choose_tiktok_join_sound(v)).pack(side="left", padx=3)
            ttk.Button(sound_row, text="Probar", command=lambda v=var: self.test_tiktok_join_sound(v)).pack(side="left", padx=3)
        volume_row = tk.Frame(join_sound_card, bg=self.panel)
        volume_row.pack(fill="x", padx=14, pady=(7, 10))
        tk.Label(volume_row, text="Volumen de sonidos TikTok", bg=self.panel, fg=self.muted).pack(side="left")
        tk.Scale(volume_row, from_=0, to=100, orient="horizontal", variable=self.tiktok_join_sound_volume,
                 bg=self.panel, fg=self.fg, troughcolor="#30303b", highlightthickness=0,
                 activebackground=self.red, length=220).pack(side="left", padx=10)
        tk.Label(volume_row, text="Solo afecta estos sonidos; no cambia el volumen de voz ni YouTube.",
                 bg=self.panel, fg=self.muted, font=("Segoe UI", 8)).pack(side="left", padx=5)

        # Connection card
        conn = tk.Frame(outer, bg=self.panel, highlightbackground="#2c2c36", highlightthickness=1)
        conn.pack(fill="x", pady=(0, 12))
        tk.Label(conn, text="  CONEXIÓN CON YOUTUBE", bg=self.panel, fg=self.fg,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(12, 2))
        tk.Label(conn, text="Introduce las credenciales de tu canal para detectar el directo activo.",
                 bg=self.panel, fg=self.muted, font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=14, pady=(0, 8))
        form = tk.Frame(conn, bg=self.panel)
        form.pack(fill="x", padx=14, pady=(0, 13))
        tk.Label(form, text="YOUTUBE DATA API KEY", bg=self.panel, fg=self.muted,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        tk.Label(form, text="ID DEL CANAL (UC…)", bg=self.panel, fg=self.muted,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 4))
        ttk.Entry(form, textvariable=self.api_key_var, show="*").grid(row=1, column=0, sticky="ew")
        ttk.Entry(form, textvariable=self.channel_var).grid(row=1, column=1, sticky="ew", padx=(12, 0))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        subrow = tk.Frame(conn, bg=self.panel)
        subrow.pack(fill="x", padx=14, pady=(0, 13))
        ttk.Button(subrow, text="♙  ACTIVAR ALERTAS DE SUSCRIPTORES", command=self.connect_subscribers).pack(side="left")
        tk.Label(subrow, text="Requiere OAuth de Google; solo puede anunciar nombres de suscriptores públicos.",
                 bg=self.panel, fg=self.muted, font=("Segoe UI", 8), anchor="w", wraplength=410, justify="left").pack(side="left", padx=(10, 0))

        # Voice settings card
        voice_card = tk.Frame(outer, bg=self.panel, highlightbackground="#2c2c36", highlightthickness=1)
        voice_card.pack(fill="x", pady=(0, 12))
        tk.Label(voice_card, text="  CONFIGURACIÓN DE VOZ", bg=self.panel, fg=self.fg,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(12, 9))
        opts = tk.Frame(voice_card, bg=self.panel)
        opts.pack(fill="x", padx=14, pady=(0, 13))
        fields = [
            ("VOZ", ttk.Combobox(opts, textvariable=self.voice_var, values=list(VOICES.keys()), state="readonly")),
            ("VELOCIDAD", ttk.Combobox(opts, textvariable=self.rate_var, values=["-20%", "-10%", "+0%", "+10%", "+20%"], state="readonly")),
            ("VOLUMEN", ttk.Combobox(opts, textvariable=self.volume_var, values=["-20%", "-10%", "+0%", "+10%", "+20%"], state="readonly")),
        ]
        for col, (label, widget) in enumerate(fields):
            tk.Label(opts, text=label, bg=self.panel, fg=self.muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=col, sticky="w", padx=(0 if col == 0 else 12, 0), pady=(0, 4))
            widget.grid(row=1, column=col, sticky="ew", padx=(0 if col == 0 else 12, 0))
            opts.columnconfigure(col, weight=2 if col == 0 else 1)

        speech_controls = tk.Frame(voice_card, bg=self.panel)
        speech_controls.pack(fill="x", padx=14, pady=(0, 12))
        tk.Checkbutton(
            speech_controls, text="Priorizar SOLO los mensajes más recientes (descartar avisos atrasados)",
            variable=self.recent_messages_only_var, bg=self.panel, fg=self.fg,
            activebackground=self.panel, activeforeground="#ffffff",
            selectcolor="#30303b", font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
            highlightthickness=0
        ).pack(anchor="w", pady=(0, 5))
        tk.Checkbutton(
            speech_controls, text="Agrupar avisos simultáneos en una sola locución (recomendado)",
            variable=self.latest_only_var, bg=self.panel, fg=self.fg,
            activebackground=self.panel, activeforeground="#ffffff",
            selectcolor="#30303b", font=("Segoe UI", 9), relief="flat", bd=0,
            highlightthickness=0
        ).pack(anchor="w", pady=(0, 5))
        tk.Checkbutton(
            speech_controls, text="Silenciar nuevos avisos de voz (seguir detectando eventos)",
            variable=self.voice_muted_var, bg=self.panel, fg=self.fg,
            activebackground=self.panel, activeforeground="#ffffff",
            selectcolor="#30303b", font=("Segoe UI", 9), relief="flat", bd=0,
            highlightthickness=0
        ).pack(anchor="w", pady=(0, 7))
        ttk.Button(speech_controls, text="🧹  VACIAR AVISOS PENDIENTES",
                   command=self.clear_speech_queue).pack(anchor="w")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        self.start_button = ttk.Button(actions, text="▶  CONECTAR CHAT", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(actions, text="■  DETENER", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="♫  PROBAR VOZ", command=self.test_voice).pack(side="left")

        status_card = tk.Frame(outer, bg="#17171e", highlightbackground="#34303a", highlightthickness=1)
        status_card.pack(fill="x", pady=(0, 12))
        tk.Label(status_card, text="ESTADO DEL LECTOR", bg="#17171e", fg=self.red_hover,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        self.status_label = tk.Label(status_card, textvariable=self.status_var, bg="#17171e", fg="#dedee4",
                                     font=("Segoe UI", 9), anchor="w", justify="left", wraplength=820)
        self.status_label.pack(fill="x", padx=12, pady=(0, 9))

        chat_card = tk.Frame(outer, bg=self.panel, highlightbackground="#2c2c36", highlightthickness=1)
        chat_card.pack(fill="both", expand=True)
        chat_head = tk.Frame(chat_card, bg=self.panel)
        chat_head.pack(fill="x", padx=12, pady=(10, 7))
        tk.Label(chat_head, text="MENSAJES DEL CHAT", bg=self.panel, fg=self.fg,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(chat_head, text="EN VIVO", bg="#32151b", fg="#ff6577",
                 font=("Segoe UI", 8, "bold"), padx=8, pady=3).pack(side="right")
        self.log = ScrolledText(chat_card, height=10, wrap="word", state="disabled",
                                font=("Cascadia Mono", 9), bg="#0f0f14", fg="#e4e4e7",
                                insertbackground="#ffffff", selectbackground=self.red,
                                relief="flat", borderwidth=0, padx=12, pady=10)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        footer = tk.Frame(outer, bg=self.bg)
        footer.pack(fill="x", pady=(9, 0))
        tk.Label(footer, text="SALIDA DE AUDIO PARA OBS  •  Captura el audio de Windows en OBS",
                 bg=self.bg, fg=self.muted, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(footer, text="MOORTY VOICE  /  V1.1", bg=self.bg, fg="#656570",
                 font=("Segoe UI", 8, "bold")).pack(side="right")

    def _on_mousewheel(self, event):
        """Rueda del ratón: desplaza la página; el registro conserva su propio scroll."""
        widget = event.widget
        current = widget
        while current is not None:
            if current is getattr(self, "log", None):
                try:
                    self.log.yview_scroll(int(-1 * (event.delta / 120)), "units")
                except Exception:
                    pass
                return
            current = getattr(current, "master", None)
        if hasattr(self, "main_canvas"):
            self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event):
        if hasattr(self, "main_canvas"):
            direction = -1 if event.num == 4 else 1
            self.main_canvas.yview_scroll(direction * 3, "units")

    def log_line(self, text):
        def update():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, update)

    def set_status(self, text):
        def update():
            self.status_var.set(text)
            if hasattr(self, "status_pill"):
                connected = "Conectado al directo" in text
                self.status_pill.configure(
                    text="● ONLINE" if connected else ("● CONECTANDO" if "Buscando" in text else "● OFFLINE"),
                    bg="#123126" if connected else ("#342815" if "Buscando" in text else "#32151b"),
                    fg="#69e3a5" if connected else ("#ffd166" if "Buscando" in text else "#ff6577"))
        self.root.after(0, update)

    def selected_voice(self):
        return VOICES.get(self.voice_var.get(), DEFAULT_VOICE)

    def start(self):
        # Nunca reproducir avisos que quedaron pendientes de una conexión anterior.
        self.clear_speech_queue()
        if self.recent_messages_only_var.get():
            self.log_line("Prioridad de mensajes recientes ACTIVADA: al iniciar se descarta la cola anterior y, si la voz se atrasa, se conserva el aviso más reciente.")
        platform = self.platform_var.get().strip()
        if platform == "TikTok":
            account = self.tiktok_account_var.get().strip().lstrip("@")
            if not account:
                messagebox.showwarning("Falta la cuenta", "Selecciona una cuenta de TikTok.")
                return
            self.stop_event.clear()
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            if self.speech_worker is None or not self.speech_worker.is_alive():
                self.speech_worker = threading.Thread(target=self.speech_loop, daemon=True)
                self.speech_worker.start()
            self.worker = threading.Thread(target=self.tiktok_loop, args=(account,), daemon=True)
            self.worker.start()
            self.set_status(f"Conectando con TikTok @{account}…")
            self.log_line(f"Iniciando lector TikTok LIVE para @{account}. La cuenta debe estar transmitiendo en un directo público.")
            return

        key = self.api_key_var.get().strip()
        channel = self.channel_var.get().strip()
        if not key or not channel:
            messagebox.showwarning("Faltan datos", "Introduce la YouTube Data API key y el ID del canal.")
            return
        if not channel.startswith("UC"):
            if not messagebox.askyesno("Confirmar ID", "El ID de canal de YouTube normalmente empieza por UC. ¿Quieres continuar de todos modos?"):
                return
        self.stop_event.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.worker = threading.Thread(target=self.monitor_loop, args=(key, channel), daemon=True)
        self.worker.start()
        if self.speech_worker is None or not self.speech_worker.is_alive():
            self.speech_worker = threading.Thread(target=self.speech_loop, daemon=True)
            self.speech_worker.start()
        self.set_status("Buscando tu directo activo…")
        self.log_line("Lector iniciado. Se leerán mensajes nuevos y se revisará el contador de espectadores aproximadamente cada 60 segundos.")

    def stop(self):
        self.stop_event.set()
        self.subscriber_stop_event.set()
        # Evita que al volver a conectar se lea una cola antigua desde el principio.
        self.clear_speech_queue()
        client = self.tiktok_client
        if client is not None:
            try:
                result = client.stop()
                if inspect.isawaitable(result) and getattr(client, "loop", None):
                    asyncio.run_coroutine_threadsafe(result, client.loop)
            except Exception as e:
                self.log_line(f"Aviso al detener TikTok: {e}")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.set_status("Lector detenido.")
        self.log_line("Lector detenido.")

    def choose_tiktok_join_sound(self, variable):
        path = filedialog.askopenfilename(
            title="Seleccionar sonido de entrada de TikTok",
            filetypes=[("Archivos de audio", "*.wav *.ogg *.mp3"), ("Todos los archivos", "*.*")]
        )
        if path:
            variable.set(path)

    def test_tiktok_join_sound(self, variable):
        path = variable.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Falta el sonido", "Elige primero un archivo de audio válido.")
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            sound = pygame.mixer.Sound(path)
            sound.set_volume(max(0.0, min(1.0, self.tiktok_join_sound_volume.get() / 100.0)))
            sound.play()
        except Exception as e:
            messagebox.showerror("No se pudo reproducir", f"Prueba con un archivo WAV u OGG compatible.\\n\\nDetalle: {e}")

    def play_tiktok_join_sound(self, subscriber_state):
        """Reproduce el sonido de suscriptor solo con señal explícita; si es desconocido, usa el sonido general."""
        # TikTokLive no siempre expone el estado de suscripción en JoinEvent.
        # Para que la entrada no quede muda, los estados False/None usan el sonido general.
        # Solo se usa el sonido de suscriptor cuando el evento indica True explícitamente.
        variable = self.tiktok_join_sound_subscriber if subscriber_state is True else self.tiktok_join_sound_general
        if not variable.get().strip():
            self.log_line("Entrada de TikTok detectada, pero no hay sonido seleccionado para esta categoría.")
            return
        path = variable.get().strip()
        if not path or not os.path.isfile(path):
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            sound = pygame.mixer.Sound(path)
            sound.set_volume(max(0.0, min(1.0, self.tiktok_join_sound_volume.get() / 100.0)))
            sound.play()
        except Exception as e:
            self.log_line(f"No se pudo reproducir el sonido de entrada de TikTok: {e}")

    @staticmethod
    def tiktok_subscriber_state(user, event):
        """Solo acepta indicadores booleanos explícitos; nunca infiere por insignias/nombre."""
        for obj in (user, event):
            if obj is None:
                continue
            for attr in ("is_subscriber", "is_sub", "subscriber"):
                try:
                    value = getattr(obj, attr, None)
                except Exception:
                    value = None
                if isinstance(value, bool):
                    return value
        return None

    def tiktok_loop(self, account):
        """Conecta a un LIVE público mediante la biblioteca comunitaria TikTokLive."""
        try:
            from TikTokLive import TikTokLiveClient
            from TikTokLive.events import CommentEvent, ConnectEvent, GiftEvent, LikeEvent, FollowEvent, ShareEvent, JoinEvent
        except Exception as e:
            self.log_line(f"No se pudo cargar TikTokLive: {e}")
            self.log_line("Cierra la aplicación y ejecuta INSTALAR_Y_ABRIR.bat para instalar las dependencias actualizadas.")
            self.root.after(0, self.reset_buttons)
            self.set_status("Falta instalar el componente de TikTok.")
            return

        client = None
        try:
            client = TikTokLiveClient(unique_id="@" + account)
            self.tiktok_client = client

            # Durante los primeros segundos TikTokLive puede emitir eventos de presencia
            # de usuarios que ya estaban en el directo. No anunciarlos como si acabaran
            # de entrar: solo anunciar nuevas entradas después de estabilizar la conexión.
            tiktok_connected_at = [None]

            @client.on(ConnectEvent)
            async def on_connect(event):
                tiktok_connected_at[0] = time.monotonic()
                self.log_line(f"Conectado al TikTok LIVE de @{account}.")
                self.log_line("Filtro de conexión activo durante 3 segundos; después se anuncian nuevas entradas.")
                self.set_status(f"Conectado al directo de @{account}. Leyendo eventos nuevos…")

            @client.on(CommentEvent)
            async def on_comment(event):
                author = getattr(getattr(event, "user", None), "nickname", None) or getattr(getattr(event, "user", None), "unique_id", None) or "Alguien"
                comment = str(getattr(event, "comment", "")).strip()
                if comment and self.accept_event("comment", f"{author}:{comment}", cooldown=4):
                    self.log_line(f"@{author} dice: {comment}")
                    if self.tiktok_event_vars["comments"].get():
                        self.enqueue_speech((f"{author} dice: {comment[:250]}", self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

            @client.on(GiftEvent)
            async def on_gift(event):
                if not self.tiktok_event_vars["gifts"].get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or getattr(user, "unique_id", None) or "Alguien"
                gift = getattr(event, "gift", None)
                gift_name = getattr(gift, "name", None) or "un regalo"
                # Evita anunciar cada actualización intermedia de regalos en racha.
                if gift is not None and getattr(gift, "streakable", False) and getattr(event, "streaking", False):
                    return
                count = getattr(event, "repeat_count", 1) or 1
                if not self.accept_event("gift", f"{author}:{gift_name}:{count}", cooldown=4):
                    return
                phrase = f"¡{author} envió {gift_name}" + (f", cantidad {count}" if count > 1 else "") + "! ¡Gracias por el apoyo!"
                self.log_line(phrase)
                self.enqueue_speech((phrase, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

            @client.on(LikeEvent)
            async def on_like(event):
                if not self.tiktok_event_vars["likes"].get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or "Alguien"
                count = getattr(event, "count", 1) or 1
                if not self.accept_event("like", author, cooldown=5):
                    return
                phrase = f"¡Gracias {author} por los likes!" if count < 2 else f"¡Gracias {author} por enviar {count} likes!"
                self.log_line(phrase)
                self.enqueue_speech((phrase, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

            @client.on(FollowEvent)
            async def on_follow(event):
                if not self.tiktok_event_vars["follows"].get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or getattr(user, "unique_id", None) or "Alguien"
                if not self.accept_event("follow", author, cooldown=120):
                    return
                phrase = f"¡{author} empezó a seguir el canal! ¡Muchas gracias!"
                self.log_line(phrase)
                self.enqueue_speech((phrase, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

            @client.on(ShareEvent)
            async def on_share(event):
                if not self.tiktok_event_vars["shares"].get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or getattr(user, "unique_id", None) or "Alguien"
                if not self.accept_event("share", author, cooldown=15):
                    return
                phrase = f"¡Gracias {author} por compartir el directo!"
                self.log_line(phrase)
                self.enqueue_speech((phrase, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

            @client.on(JoinEvent)
            async def on_join(event):
                if not self.tiktok_event_vars["joins"].get():
                    return
                connected_at = tiktok_connected_at[0]
                if connected_at is None or time.monotonic() - connected_at < 3:
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or getattr(user, "unique_id", None)
                if author and self.accept_event("join", author, cooldown=45):
                    subscriber_state = self.tiktok_subscriber_state(user, event)
                    self.play_tiktok_join_sound(subscriber_state)
                    phrase = f"¡{author} se unió al directo!"
                    self.log_line(phrase)
                    self.enqueue_speech((phrase, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

            client.run()
        except Exception as e:
            if not self.stop_event.is_set():
                self.log_line(f"Error de conexión con TikTok @{account}: {e}")
                self.log_line("Comprueba que la cuenta esté en directo público y que TikTokLive esté actualizado.")
        finally:
            self.tiktok_client = None
            self.root.after(0, self.reset_buttons)
            if not self.stop_event.is_set():
                self.set_status("TikTok desconectado. Revisa el registro para ver el motivo.")

    def test_voice(self):
        if self.speech_worker is None or not self.speech_worker.is_alive():
            self.speech_worker = threading.Thread(target=self.speech_loop, daemon=True)
            self.speech_worker.start()
        self.enqueue_speech(("Prueba de voz. Moorty Voice está listo para tu directo.", self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

    def connect_subscribers(self):
        path = filedialog.askopenfilename(
            title="Selecciona el archivo OAuth de Google",
            filetypes=[("Archivo JSON", "*.json"), ("Todos los archivos", "*.*")])
        if not path:
            return
        self.oauth_client_file = path
        self.subscriber_stop_event.clear()
        self.log_line("Configurando alertas de suscriptores. Se abrirá el navegador para autorizar tu cuenta.")
        self.subscriber_worker = threading.Thread(target=self.subscriber_loop, args=(path,), daemon=True)
        self.subscriber_worker.start()

    def subscriber_loop(self, client_file):
        """Consulta los suscriptores recientes públicos autorizados por OAuth."""
        try:
            creds = None
            token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token_subscribers.json")
            if os.path.exists(token_path):
                try:
                    creds = Credentials.from_authorized_user_file(token_path, SUBSCRIBER_SCOPES)
                except Exception:
                    creds = None
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(client_file, SUBSCRIBER_SCOPES)
                    creds = flow.run_local_server(port=0, open_browser=True)
                with open(token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
            self.subscriber_api = build("youtube", "v3", credentials=creds, cache_discovery=False)
            self.log_line("Cuenta autorizada para alertas de suscriptores.")
            self.log_line("YouTube solo muestra nombres de suscriptores recientes que mantienen sus suscripciones públicas.")
            seen = set()
            baseline = True
            while not self.subscriber_stop_event.is_set():
                try:
                    response = self.subscriber_api.subscriptions().list(
                        part="snippet,subscriberSnippet", myRecentSubscribers=True, maxResults=50
                    ).execute()
                    current = []
                    for item in response.get("items", []):
                        sid = item.get("id")
                        title = item.get("subscriberSnippet", {}).get("title") or "Alguien"
                        if sid:
                            current.append((sid, title))
                    if baseline:
                        seen.update(sid for sid, _ in current)
                        baseline = False
                        self.log_line("Lista inicial cargada; avisaré de nuevos suscriptores públicos visibles desde ahora.")
                    else:
                        new_items = [(sid, title) for sid, title in current if sid not in seen]
                        for sid, title in reversed(new_items):
                            phrase = f"¡{title} se acaba de suscribir al canal Moorty! ¡Muchas gracias por el apoyo!"
                            self.log_line(phrase)
                            self.enqueue_speech((phrase, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))
                        seen.update(sid for sid, _ in current)
                except HttpError as e:
                    self.log_line(f"Error consultando suscriptores: {e}")
                    if "insufficientPermissions" in str(e) or "forbidden" in str(e).lower():
                        self.log_line("Verifica que autorizaste el canal correcto y que el proyecto OAuth esté configurado.")
                except Exception as e:
                    self.log_line(f"No se pudo revisar suscriptores: {e}")
                self.subscriber_stop_event.wait(60)
        except Exception as e:
            self.log_line(f"No se pudieron activar alertas de suscriptores: {e}")
            self.log_line("En Google Cloud crea un ID de cliente OAuth tipo Aplicación de escritorio y selecciona su archivo JSON.")

    def monitor_loop(self, key, channel):
        try:
            self.api = build("youtube", "v3", developerKey=key, cache_discovery=False)
        except Exception as e:
            self.set_status("No se pudo iniciar la API. Revisa la clave y la conexión.")
            self.log_line(f"Error al crear cliente de YouTube: {e}")
            self.root.after(0, self.reset_buttons)
            return

        while not self.stop_event.is_set():
            try:
                live = self.find_live_stream(channel)
                if not live:
                    self.active_video_id = None
                    self.active_chat_id = None
                    self.set_status("No encuentro un directo público activo en ese canal. Reintentando en 30 s…")
                    self.stop_event.wait(30)
                    continue

                video_id, chat_id, title = live
                if video_id != self.active_video_id or chat_id != self.active_chat_id:
                    self.active_video_id = video_id
                    self.active_chat_id = chat_id
                    self.log_line(f"Conectado al directo: {title}")
                    self.log_line(f"Video ID: {video_id}")
                    self.set_status("Conectado al directo. Esperando mensajes nuevos…")
                    self.read_chat(chat_id)
                else:
                    self.stop_event.wait(5)
            except HttpError as e:
                self.log_line(f"Error de YouTube API: {e}")
                self.set_status("Error de API. Revisa la clave, cuota y permisos.")
                self.stop_event.wait(20)
            except Exception as e:
                self.log_line(f"Error: {e}")
                self.set_status("Problema de conexión; reintentando…")
                self.stop_event.wait(15)

        self.root.after(0, self.reset_buttons)

    def reset_buttons(self):
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def find_live_stream(self, channel_id):
        # Busca un directo público activo. Requiere YouTube Data API v3.
        result = self.api.search().list(
            part="id,snippet", channelId=channel_id, eventType="live",
            type="video", maxResults=5
        ).execute()
        for item in result.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            video = self.api.videos().list(
                part="snippet,liveStreamingDetails", id=video_id
            ).execute()
            for v in video.get("items", []):
                chat_id = v.get("liveStreamingDetails", {}).get("activeLiveChatId")
                if chat_id:
                    return video_id, chat_id, v.get("snippet", {}).get("title", "Directo de YouTube")
        return None

    def read_chat(self, chat_id):
        page_token = None
        first_response = True
        last_viewer_count = None
        next_viewer_check = 0.0
        while not self.stop_event.is_set() and self.active_chat_id == chat_id:
            # Consulta el contador con poca frecuencia para limitar el uso de cuota.
            now = time.monotonic()
            if now >= next_viewer_check:
                current_count = self.get_concurrent_viewers(self.active_video_id)
                if current_count is not None:
                    if last_viewer_count is not None and current_count > last_viewer_count:
                        increase = current_count - last_viewer_count
                        if increase == 1:
                            spoken = (f"¡El contador de espectadores subió de {last_viewer_count} "
                                      f"a {current_count} en Moorty!")
                        else:
                            spoken = (f"¡El contador de espectadores subió de {last_viewer_count} "
                                      f"a {current_count} en Moorty, un aumento de {increase}!")
                        self.log_line(spoken)
                        self.enqueue_speech((spoken, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))
                    last_viewer_count = current_count
                next_viewer_check = now + 60.0

            response = self.api.liveChatMessages().list(
                liveChatId=chat_id,
                part="id,snippet,authorDetails",
                pageToken=page_token,
                maxResults=200
            ).execute()
            page_token = response.get("nextPageToken")
            items = response.get("items", [])

            # La primera respuesta sirve únicamente como punto de partida.
            # No anunciar ninguno de esos mensajes: pueden ser mensajes anteriores
            # al momento de conexión (incluidos los últimos mensajes que devuelve la API).
            if first_response:
                for item in items:
                    msg_id = item.get("id")
                    if msg_id:
                        self.last_message_ids.add(msg_id)
                first_response = False
                self.log_line(f"Historial inicial de YouTube ignorado ({len(items)} mensaje(s)); esperando mensajes nuevos.")
            else:
                for item in items:
                    msg_id = item.get("id")
                    if msg_id in self.last_message_ids:
                        continue
                    self.last_message_ids.add(msg_id)
                    if len(self.last_message_ids) > 5000:
                        self.last_message_ids.clear()
                        self.last_message_ids.add(msg_id)

                    snippet = item.get("snippet", {})
                    author = item.get("authorDetails", {}).get("displayName", "Alguien")
                    msg_type = snippet.get("type", "")
                    spoken = self.format_chat_event(author, msg_type, snippet)
                    if not spoken:
                        continue
                    self.log_line(spoken)
                    self.enqueue_speech((spoken, self.selected_voice(), self.rate_var.get(), self.volume_var.get()))

            wait_ms = response.get("pollingIntervalMillis", 5000)
            self.stop_event.wait(max(1.0, wait_ms / 1000.0))

    def get_concurrent_viewers(self, video_id):
        """Devuelve el contador público de espectadores simultáneos, si YouTube lo expone."""
        if not video_id:
            return None
        try:
            response = self.api.videos().list(
                part="liveStreamingDetails", id=video_id
            ).execute()
            items = response.get("items", [])
            if not items:
                return None
            value = items[0].get("liveStreamingDetails", {}).get("concurrentViewers")
            return int(value) if value is not None else None
        except Exception as e:
            # No detener el lector del chat si el contador no está disponible.
            self.log_line(f"No pude consultar el contador de espectadores: {e}")
            return None

    def format_chat_event(self, author, msg_type, snippet):
        """Convierte mensajes y eventos que YouTube sí expone en el chat en frases para voz."""
        if msg_type == "textMessageEvent":
            text = snippet.get("displayMessage", "").strip()
            if not text:
                return None
            # Limita longitud y evita leer enlaces o caracteres de control en exceso.
            text = re.sub(r"https?://\S+", " enlace ", text)
            text = re.sub(r"[\r\n\t]+", " ", text)
            text = text[:280]
            return f"{author} dice: {text}"

        if msg_type == "newSponsorEvent":
            details = snippet.get("newSponsorDetails", {})
            level = details.get("memberLevelName", "")
            if level:
                return f"¡{author} se ha unido como miembro del canal, nivel {level}! ¡Gracias por apoyar!"
            return f"¡{author} se ha unido como miembro del canal! ¡Gracias por apoyar!"

        if msg_type == "memberMilestoneChatEvent":
            details = snippet.get("memberMilestoneChatDetails", {})
            months = details.get("memberMonth")
            level = details.get("memberLevelName", "")
            try:
                months_text = f" por {int(months)} meses" if months is not None else ""
            except (TypeError, ValueError):
                months_text = ""
            level_text = f", nivel {level}" if level else ""
            comment = details.get("userComment", "").strip()
            result = f"¡{author} celebra su membresía{months_text}{level_text}!"
            if comment:
                result += f" Dice: {comment[:180]}"
            return result

        if msg_type == "membershipGiftingEvent":
            details = snippet.get("membershipGiftingDetails", {})
            count = details.get("giftMembershipsCount", 1)
            level = details.get("giftMembershipsLevelName", "")
            level_text = f", nivel {level}" if level else ""
            return f"¡{author} regaló {count} membresía(s){level_text}! ¡Muchas gracias!"

        if msg_type == "giftMembershipReceivedEvent":
            details = snippet.get("giftMembershipReceivedDetails", {})
            level = details.get("memberLevelName", "")
            level_text = f", nivel {level}" if level else ""
            return f"¡{author} recibió una membresía regalada{level_text}! ¡Felicidades!"

        if msg_type == "superChatEvent":
            details = snippet.get("superChatDetails", {})
            amount = details.get("amountDisplayString", "")
            comment = details.get("userComment", "").strip()
            result = f"¡Super Chat de {author} por {amount}!" if amount else f"¡{author} envió un Super Chat!"
            if comment:
                result += f" Mensaje: {comment[:180]}"
            return result

        if msg_type == "superStickerEvent":
            details = snippet.get("superStickerDetails", {})
            amount = details.get("amountDisplayString", "")
            if amount:
                return f"¡{author} envió un Super Sticker de {amount}!"
            return f"¡{author} envió un Super Sticker!"

        # YouTube no entrega por la API pública un evento fiable por cada espectador
        # que entra al directo ni por cada suscripción normal al canal.
        return None

    def accept_event(self, event_type, identity, cooldown=5):
        """Devuelve False si TikTok retransmite el mismo evento dentro del periodo indicado."""
        now = time.monotonic()
        key = (event_type, str(identity).strip().casefold())
        with self.dedupe_lock:
            previous = self.recent_event_times.get(key, 0)
            if now - previous < cooldown:
                return False
            self.recent_event_times[key] = now
            # Limita el tamaño de la memoria de deduplicación.
            if len(self.recent_event_times) > 3000:
                self.recent_event_times = {
                    k: stamp for k, stamp in self.recent_event_times.items()
                    if now - stamp < 300
                }
            return True

    def clear_speech_queue(self):
        """Descarta avisos pendientes para que no se reproduzcan mensajes viejos."""
        removed = 0
        while True:
            try:
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
                removed += 1
            except queue.Empty:
                break
        self.log_line(f"Cola de voz vaciada: {removed} aviso(s) pendiente(s) descartado(s).")

    def enqueue_speech(self, item):
        """Encola eventos sin descartar mensajes que llegan casi al mismo tiempo."""
        if self.voice_muted_var.get():
            return
        self.speech_queue.put(item)

    def clear_queue_silently(self):
        while True:
            try:
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
            except queue.Empty:
                break

    def speech_loop(self):
        try:
            pygame.mixer.init()
        except Exception as e:
            self.log_line(f"No se pudo iniciar el audio: {e}")
            return
        while True:
            try:
                item = self.speech_queue.get(timeout=0.5)
            except queue.Empty:
                if self.stop_event.is_set():
                    continue
                else:
                    continue
            # Si la voz va atrasada, conserva el aviso más nuevo y descarta los antiguos.
            # Se aplica a TikTok y YouTube sin alterar cómo se reciben sus eventos.
            if self.recent_messages_only_var.get():
                queued = []
                while True:
                    try:
                        queued.append(self.speech_queue.get_nowait())
                    except queue.Empty:
                        break
                if queued:
                    # El elemento actual y los elementos intermedios se descartan; el último queda pendiente.
                    self.speech_queue.task_done()
                    for _ in queued[:-1]:
                        self.speech_queue.task_done()
                    item = queued[-1]
                    self.log_line(f"Prioridad reciente: se descartaron {len(queued)} aviso(s) atrasado(s).")
            text, voice, rate, volume = item
            # Da una pequeña ventana para que lleguen juntos los eventos simultáneos.
            # Se agrupan en una sola frase en vez de perder avisos.
            batch = [item]
            if self.latest_only_var.get():
                deadline = time.monotonic() + 0.75
                while len(batch) < 5:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        batch.append(self.speech_queue.get(timeout=remaining))
                    except queue.Empty:
                        break
                if len(batch) > 1:
                    texts = []
                    seen_batch = set()
                    for entry in batch:
                        phrase = entry[0].strip()
                        normalized = re.sub(r"\\s+", " ", phrase).casefold()
                        if phrase and normalized not in seen_batch:
                            texts.append(phrase)
                            seen_batch.add(normalized)
                    if not texts:
                        for _ in batch:
                            self.speech_queue.task_done()
                        self.speech_queue.task_done()
                        continue
                    text = " Atención al directo: " + ". Además, ".join(texts)
                    voice, rate, volume = batch[0][1], batch[0][2], batch[0][3]
                    for _ in batch[1:]:
                        self.speech_queue.task_done()
            path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    path = tmp.name
                async def create_audio():
                    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
                    await communicate.save(path)
                asyncio.run(create_audio())
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            except Exception as e:
                self.log_line(f"Error de voz (comprueba internet): {e}")
            finally:
                try:
                    pygame.mixer.music.stop()
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
                self.speech_queue.task_done()

    def close(self):
        self.stop_event.set()
        self.subscriber_stop_event.set()
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    app = YouTubeChatReader(root)
    root.mainloop()
