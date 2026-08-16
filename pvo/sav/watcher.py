"""Vigilancia del fichero de partida guardada (disparo automático al guardar).

Cuando el jugador guarda dentro del juego, el emulador **reescribe** el fichero de
partida. El watcher lo detecta y relee el equipo, sin que el usuario tenga que tocar
nada.

Escrituras parciales: un emulador puede escribir el fichero en varias pasadas (o
truncarlo y rellenarlo). Por eso no se lee en cuanto cambia el mtime, sino cuando el
fichero lleva `stable_for_s` segundos **sin cambiar de tamaño ni de contenido**
(huella SHA-1). Así nunca se parsea un save a medio escribir.

Sin dependencias externas (polling con `os.stat`): funciona igual en Windows, Linux y
macOS, y mantiene la app en unos pocos MB.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("pvo.sav.watcher")


@dataclass
class _Snapshot:
    size: int
    mtime: float
    digest: str


def _fingerprint(path: Path) -> Optional[_Snapshot]:
    try:
        st = path.stat()
        data = path.read_bytes()
    except (OSError, ValueError):
        return None
    return _Snapshot(size=st.st_size, mtime=st.st_mtime,
                     digest=hashlib.sha1(data).hexdigest())


class SaveWatcher:
    """Vigila un fichero y llama a `on_change(path)` cuando queda escrito del todo.

    `on_error(exc)` recibe los fallos de lectura/parseo (p. ej. savestate no
    soportado) para que la capa de arriba pueda avisar al usuario.
    """

    def __init__(
        self,
        path: str | Path,
        on_change: Callable[[Path], None],
        on_error: Optional[Callable[[Exception], None]] = None,
        poll_interval_s: float = 1.0,
        stable_for_s: float = 1.5,
        emit_initial: bool = True,
    ):
        self.path = Path(path)
        self._on_change = on_change
        self._on_error = on_error or (lambda e: log.error("%s", e))
        self._poll = max(0.1, float(poll_interval_s))
        self._stable = max(0.0, float(stable_for_s))
        self._emit_initial = emit_initial
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_emitted: Optional[str] = None

    # -- ciclo de vida -----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, name="sav-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._poll * 3)

    # -- bucle -------------------------------------------------------------
    def run(self) -> None:
        log.info("Vigilando la partida guardada: %s", self.path)
        pending: Optional[_Snapshot] = None
        stable_polls = 0
        needed = max(1, int(round(self._stable / self._poll)))
        first = True

        while not self._stop.is_set():
            snap = _fingerprint(self.path)
            if snap is None:
                pending, stable_polls = None, 0
                self._stop.wait(self._poll)
                continue

            if pending is None or snap.digest != pending.digest or snap.size != pending.size:
                pending, stable_polls = snap, 0
            else:
                stable_polls += 1

            if stable_polls >= needed and snap.digest != self._last_emitted:
                self._last_emitted = snap.digest
                if first and not self._emit_initial:
                    first = False
                else:
                    first = False
                    self._emit(snap)

            self._stop.wait(self._poll)
        log.info("Watcher detenido.")

    def _emit(self, snap: _Snapshot) -> None:
        log.info("Partida guardada actualizada (%d bytes) — releyendo el equipo.", snap.size)
        try:
            self._on_change(self.path)
        except Exception as e:                       # noqa: BLE001
            self._on_error(e)

    # -- utilidad para tests ----------------------------------------------
    def poll_once(self) -> bool:
        """Comprueba el fichero una vez (sin esperar estabilidad). True si emitió."""
        snap = _fingerprint(self.path)
        if snap is None or snap.digest == self._last_emitted:
            return False
        self._last_emitted = snap.digest
        self._emit(snap)
        return True
