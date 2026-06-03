"""Interfaz gráfica (Tkinter) de la app local.

Junta todo lo que antes era CLI: configurar api_base/token, elegir el perfil del
juego, calibrar uno nuevo, generar embeddings, y arrancar/parar el overlay con un
panel de log. Tkinter va en la stdlib y se empaqueta con PyInstaller sin peso extra.

Acciones que abren ventanas de OpenCV pesadas o cargan torch (calibrar, embeddings)
se lanzan como subproceso del propio ejecutable, para no bloquear la GUI.
"""

from __future__ import annotations

import logging
import queue
import subprocess
import sys
import threading
from pathlib import Path

from . import paths
from .appconfig import list_profiles, load_app_config, save_app_config
from .main import run_with_config

CONFIG_PATH = paths.config_path()
log = logging.getLogger("pvo")


def _available_profiles() -> list[str]:
    """Perfiles del usuario (escribibles) + ejemplos empaquetados, sin duplicados."""
    names = set(list_profiles(paths.profiles_dir())) | set(list_profiles(paths.bundled_profiles_dir()))
    return sorted(names)


class _QueueLogHandler(logging.Handler):
    def __init__(self, q: "queue.Queue[str]"):
        super().__init__()
        self._q = q

    def emit(self, record):
        self._q.put(self.format(record))


def _self_command(*extra: str) -> list[str]:
    """Comando para re-invocar esta misma app (exe congelado o `python -m pvo.main`)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *extra]
    return [sys.executable, "-m", "pvo.main", *extra]


class App:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        root.title("Poke Overlay")
        root.geometry("560x520")

        self.cfg = load_app_config(CONFIG_PATH)
        self.log_q: "queue.Queue[str]" = queue.Queue()
        self.stop_event: threading.Event | None = None
        self.worker: threading.Thread | None = None

        self.api_var = tk.StringVar(value=self.cfg.get("api_base", ""))
        self.token_var = tk.StringVar(value=self.cfg.get("ingest_token", ""))
        self.profile_var = tk.StringVar(value=self.cfg.get("profile", ""))

        self._build_ui()
        self._attach_logging()
        self.root.after(150, self._drain_log)

    # --- UI ---
    def _build_ui(self):
        tk, ttk = self.tk, self.ttk
        pad = {"padx": 8, "pady": 4}

        frm = ttk.Frame(self.root)
        frm.pack(fill="x", **pad)

        ttk.Label(frm, text="API base (claude-test):").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.api_var, width=48).grid(row=0, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="Ingest token:").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.token_var, width=48, show="•").grid(row=1, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="Juego (perfil):").grid(row=2, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(frm, textvariable=self.profile_var, state="readonly",
                                           values=_available_profiles(), width=30)
        self.profile_combo.grid(row=2, column=1, sticky="we")
        ttk.Button(frm, text="↻", width=3, command=self._refresh_profiles).grid(row=2, column=2, sticky="w")
        frm.columnconfigure(1, weight=1)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad)
        ttk.Button(btns, text="Guardar config", command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="Calibrar nuevo juego…", command=self._calibrate).pack(side="left", padx=4)
        ttk.Button(btns, text="Generar embeddings…", command=self._build_embeddings).pack(side="left", padx=4)

        run = ttk.Frame(self.root)
        run.pack(fill="x", **pad)
        self.start_btn = ttk.Button(run, text="▶ Arrancar", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(run, text="■ Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        self.status_var = tk.StringVar(value="parado")
        ttk.Label(run, textvariable=self.status_var).pack(side="left", padx=8)

        from tkinter import scrolledtext
        ttk.Label(self.root, text="Log:").pack(anchor="w", padx=8)
        self.log_text = scrolledtext.ScrolledText(self.root, height=16, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _attach_logging(self):
        handler = _QueueLogHandler(self.log_q)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)

    # --- helpers ---
    def _refresh_profiles(self):
        self.profile_combo["values"] = _available_profiles()

    def _collect_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg["api_base"] = self.api_var.get().strip()
        cfg["ingest_token"] = self.token_var.get().strip()
        cfg["profile"] = self.profile_var.get().strip()
        return cfg

    def _save(self):
        self.cfg = self._collect_cfg()
        save_app_config(CONFIG_PATH, self.cfg)
        log.info("Config guardada en %s", CONFIG_PATH)

    def _append_log(self, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_log(self):
        try:
            while True:
                self._append_log(self.log_q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(150, self._drain_log)

    # --- subprocesos (calibrar / embeddings) ---
    def _run_subprocess(self, cmd: list[str], on_done=None):
        def worker():
            log.info("Ejecutando: %s", " ".join(cmd))
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.log_q.put(line.rstrip())
                proc.wait()
                log.info("Proceso terminado (código %s)", proc.returncode)
            except Exception as e:  # noqa: BLE001
                log.error("Fallo al ejecutar el proceso: %s", e)
            if on_done:
                self.root.after(0, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _calibrate(self):
        from tkinter import simpledialog, messagebox

        name = simpledialog.askstring("Calibrar", "Nombre del perfil (p. ej. gba_emerald):", parent=self.root)
        if not name:
            return
        window = simpledialog.askstring("Calibrar", "Título de la ventana del emulador (p. ej. mGBA):", parent=self.root)
        if not window:
            messagebox.showinfo("Calibrar", "Necesito el título de la ventana para localizar el emulador.")
            return
        gen = simpledialog.askstring(
            "Calibrar — generación del juego",
            "¿De qué generación es el juego? Escribe el número:\n\n"
            "  3 = GBA (Rubí/Zafiro/Esmeralda/Rojo Fuego/Verde Hoja)\n"
            "  4 = NDS (Diamante/Perla/Platino/HG/SS)\n"
            "  5 = NDS (Negro/Blanco 1 y 2)\n"
            "  6 = 3DS (X/Y/Rubí Omega/Zafiro Alfa)\n"
            "  7 = 3DS (Sol/Luna/Ultra)\n"
            "  8 = Switch (Espada/Escudo)\n"
            "  9 = Switch (Escarlata/Púrpura)\n\n"
            "Esto fija la galería de iconos y la resolución/aspecto correctos.",
            parent=self.root,
        )
        if not (gen and gen.strip().isdigit()):
            messagebox.showinfo("Calibrar", "Necesito la generación (un número del 3 al 9).")
            return
        cmd = _self_command("--calibrate", name, "--window", window, "--gen", gen.strip())
        self._run_subprocess(cmd, on_done=self._refresh_profiles)

    def _build_embeddings(self):
        from tkinter import filedialog
        icons_base = str(paths.assets_dir() / "icons")
        icons = filedialog.askdirectory(title="Carpeta con iconos NNN.png", initialdir=icons_base)
        if not icons:
            return
        # Por defecto, guarda dentro de la propia carpeta de iconos (que es donde el
        # perfil calibrado espera el embeddings.npz).
        out = filedialog.asksaveasfilename(title="Guardar embeddings", defaultextension=".npz",
                                           initialdir=icons, initialfile="embeddings.npz")
        if not out:
            return
        self._run_subprocess(_self_command("--build-embeddings", "--icons", icons, "--out", out))

    # --- arrancar / parar ---
    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        self._save()
        if not self.cfg.get("profile"):
            log.error("Elige un perfil antes de arrancar.")
            return
        self.stop_event = threading.Event()
        cfg = self.cfg

        def target():
            try:
                run_with_config(cfg, self.stop_event)
            except Exception:  # noqa: BLE001
                log.exception("El pipeline se detuvo por un error")
            finally:
                # Garantiza que los botones vuelvan a su sitio aunque el hilo falle.
                self.root.after(0, self._on_stopped)

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set("ejecutando")

    def _stop(self):
        if self.stop_event:
            self.stop_event.set()
        self.status_var.set("parando…")

    def _on_stopped(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_var.set("parado")


def launch() -> int:
    import tkinter as tk

    paths.ensure_seeded()  # copia galerías/ejemplos a la carpeta del usuario (1ª vez)
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
