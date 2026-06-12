"""Interfaz gráfica (Tkinter) de la app local.

Junta todo lo que antes era CLI: configurar api_base/token, elegir el perfil del
juego, calibrar uno nuevo, probar el envío, y arrancar/parar el overlay con un panel
de log. Tkinter va en la stdlib y se empaqueta con PyInstaller sin peso extra.

La calibración (ventana de OpenCV) se lanza como subproceso del propio ejecutable,
para no bloquear la GUI.
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
from .memory.games import GAMES

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
        root.geometry("560x580")

        self.cfg = load_app_config(CONFIG_PATH)
        self.log_q: "queue.Queue[str]" = queue.Queue()
        self.stop_event: threading.Event | None = None
        self.worker: threading.Thread | None = None

        self.api_var = tk.StringVar(value=self.cfg.get("api_base", ""))
        self.token_var = tk.StringVar(value=self.cfg.get("ingest_token", ""))
        self.profile_var = tk.StringVar(value=self.cfg.get("profile", ""))
        self.thr_var = tk.StringVar(value=str(self.cfg.get("min_similarity", "") or ""))
        self.source_var = tk.StringVar(value=self.cfg.get("source", "vision") or "vision")
        self.addr_var = tk.StringVar(value=str(self.cfg.get("party_address", "0x020244EC")))
        self.game_var = tk.StringVar(value="")

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

        ttk.Label(frm, text="Umbral (vacío=perfil):").grid(row=3, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.thr_var, width=8).grid(row=3, column=1, sticky="w")

        ttk.Label(frm, text="Fuente:").grid(row=4, column=0, sticky="w")
        ttk.Combobox(frm, textvariable=self.source_var, state="readonly",
                     values=["vision", "retroarch", "champions"], width=12).grid(row=4, column=1, sticky="w")

        ttk.Label(frm, text="Juego (memoria):").grid(row=5, column=0, sticky="w")
        game_combo = ttk.Combobox(frm, textvariable=self.game_var, state="readonly",
                                  values=list(GAMES), width=26)
        game_combo.grid(row=5, column=1, sticky="w")
        game_combo.bind("<<ComboboxSelected>>", self._on_game_selected)

        ttk.Label(frm, text="Dirección equipo (RetroArch):").grid(row=6, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.addr_var, width=14).grid(row=6, column=1, sticky="w")
        frm.columnconfigure(1, weight=1)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad)
        ttk.Button(btns, text="Guardar config", command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="Calibrar nuevo juego…", command=self._calibrate).pack(side="left", padx=4)
        ttk.Button(btns, text="Calibrar Champions…", command=self._calibrate_champions).pack(side="left", padx=4)
        ttk.Button(btns, text="Auto-localizar equipo…", command=self._autolocate).pack(side="left", padx=4)
        ttk.Button(btns, text="Guardar captura", command=self._save_capture).pack(side="left", padx=4)

        run = ttk.Frame(self.root)
        run.pack(fill="x", **pad)
        self.start_btn = ttk.Button(run, text="▶ Arrancar", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(run, text="■ Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(run, text="Probar envío", command=self._test_send).pack(side="left", padx=4)
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

    def _on_game_selected(self, _evt=None):
        info = GAMES.get(self.game_var.get())
        if info:
            self.addr_var.set(info["address"])
            self.source_var.set("retroarch")
            self.cfg["gen"] = info["gen"]
            self.cfg["mon_size"] = info["mon_size"]

    def _collect_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg["api_base"] = self.api_var.get().strip()
        cfg["ingest_token"] = self.token_var.get().strip()
        cfg["profile"] = self.profile_var.get().strip()
        cfg["min_similarity"] = self.thr_var.get().strip()
        cfg["source"] = self.source_var.get().strip() or "vision"
        cfg["party_address"] = self.addr_var.get().strip() or "0x020244EC"
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

    def _autolocate(self):
        """Localiza los 6 iconos a partir de los nombres del equipo (sin calibrar)."""
        from tkinter import messagebox
        cfg = self._collect_cfg()
        self.cfg = cfg
        if not cfg.get("profile"):
            messagebox.showinfo("Auto-localizar", "Elige antes un perfil (con su ventana/viewport).")
            return
        try:
            from .main import resolve_profile
            profile = resolve_profile(cfg["profile"])
        except Exception as e:  # noqa: BLE001
            log.error("No se pudo cargar el perfil '%s': %s", cfg["profile"], e)
            return

        tk, ttk = self.tk, self.ttk
        top = tk.Toplevel(self.root)
        top.title("Auto-localizar equipo")
        ttk.Label(top, justify="left", text=(
            "Con el menú de equipo abierto, escribe el Pokémon de cada slot (en inglés),\n"
            "en orden. La app encontrará la posición de cada icono sola.")).pack(padx=10, pady=8)
        rows = ttk.Frame(top); rows.pack(padx=10, pady=4)
        entries = {}
        for i in range(6):
            fr = ttk.Frame(rows); fr.grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(fr, text=f"Slot {i + 1}:", width=8).pack(side="left")
            var = tk.StringVar(); ttk.Entry(fr, textvariable=var, width=22).pack(side="left", padx=6)
            entries[i] = var

        def run():
            names = [entries[i].get() for i in range(6)]
            top.destroy()

            def work():
                try:
                    import cv2  # noqa: F401
                    from . import autolocate
                    from .capture import Capturer
                    frame = Capturer(profile.capture, profile.reference_resolution).grab()
                    nmap = autolocate.load_name_map()
                    dex_list = [autolocate.name_to_dex(n, nmap) for n in names]
                    gallery = profile.resolve(profile.species.gallery)
                    alt = gallery.with_name("templates.npz")
                    if gallery.name != "templates.npz" and alt.exists():
                        gallery = alt
                    results = autolocate.locate_team(frame, dex_list, gallery)
                    regions = []
                    for i, r in enumerate(results):
                        if r is None:
                            regions.append(None)
                            log.warning("Slot %d: '%s' no reconocido como Pokémon; se omite.", i + 1, names[i])
                        else:
                            reg, score = r
                            regions.append(reg)
                            log.info("Slot %d (%s, dex %s): pos %s score %.2f", i + 1, names[i], dex_list[i], reg[:2], score)
                    path = autolocate.write_slots(profile.name, regions)
                    log.info("Recuadros actualizados en %s. Pulsa ▶ Arrancar.", path)
                    self.root.after(0, self._refresh_profiles)
                except Exception:  # noqa: BLE001
                    log.exception("Fallo al auto-localizar el equipo")

            threading.Thread(target=work, daemon=True).start()

        bf = ttk.Frame(top); bf.pack(pady=8)
        ttk.Button(bf, text="Localizar", command=run).pack(side="left", padx=6)
        ttk.Button(bf, text="Cancelar", command=top.destroy).pack(side="left", padx=6)

    def _save_capture(self):
        """Guarda el frame normalizado (240x160) + los recortes por slot, para poder
        revisar/medir el encuadre."""
        from tkinter import messagebox
        cfg = self._collect_cfg()
        self.cfg = cfg
        if not cfg.get("profile"):
            messagebox.showinfo("Guardar captura", "Elige antes un perfil.")
            return
        try:
            import cv2
            from .capture import Capturer
            from .main import resolve_profile
            profile = resolve_profile(cfg["profile"])
            frame = Capturer(profile.capture, profile.reference_resolution).grab()
        except Exception as e:  # noqa: BLE001
            log.error("No se pudo capturar (¿emulador y menú abiertos?): %s", e)
            return
        out_dir = paths.data_dir() / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / "captura.png"), frame)
        # Versión ampliada 4x para verla mejor.
        big = cv2.resize(frame, (frame.shape[1] * 4, frame.shape[0] * 4), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(str(out_dir / "captura_x4.png"), big)
        for i, slot in enumerate(profile.slots):
            x, y, w, h = slot.icon_region
            cv2.imwrite(str(out_dir / f"slot{i + 1}.png"), frame[y:y + h, x:x + w])
        log.info("Captura guardada en: %s", out_dir)
        log.info("  (captura.png = 240x160; captura_x4.png = ampliada; slotN.png = recortes)")

    # --- subproceso (calibrar) ---
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

    def _calibrate_champions(self):
        from tkinter import simpledialog, messagebox

        window = simpledialog.askstring(
            "Calibrar Champions",
            "Título de la ventana de OBS a capturar.\n"
            "En OBS: clic derecho en la fuente → 'Proyector en ventana (Fuente)'.",
            initialvalue="Windowed Projector", parent=self.root,
        )
        if not window:
            messagebox.showinfo("Calibrar Champions", "Necesito el título de la ventana del proyector de OBS.")
            return

        def on_done():
            self._refresh_profiles()
            self.profile_var.set("champions")
            self.source_var.set("champions")

        cmd = _self_command("--calibrate-champions", "--window", window)
        self._run_subprocess(cmd, on_done=on_done)

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

    def _test_send(self):
        """Envía un equipo de prueba (un Pikachu) al endpoint para verificar la web."""
        self._save()
        cfg = self.cfg
        if not cfg.get("api_base") or not cfg.get("ingest_token"):
            log.error("Rellena 'API base' e 'Ingest token' antes de probar el envío.")
            return
        from .publisher import Publisher
        pub = Publisher(cfg["api_base"], cfg["ingest_token"], min_interval_s=0.0)

        def work():
            log.info("Probando envío a la web (equipo de prueba: un Pikachu)…")
            ok = pub.publish({"pokemonIds": [25, None, None, None, None, None],
                              "nicknames": [None] * 6}, force=True)
            log.info("Resultado de la prueba: %s", "OK ✓ (mira tu overlay)" if ok else "FALLÓ ✗ (ver arriba)")

        threading.Thread(target=work, daemon=True).start()

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
