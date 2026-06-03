"""Captura de la ventana del emulador a baja frecuencia y normalización.

Único trabajo continuo del pipeline → debe ser barato. Por defecto captura una
región fija de pantalla; opcionalmente localiza la ventana por título (requiere
`pygetwindow`). Las dependencias pesadas se importan de forma perezosa.
"""

from __future__ import annotations

import time
from typing import Optional

from .profiles.schema import CaptureProfile, Region


def _find_window_bbox(title_match: str) -> Optional[Region]:
    """Localiza la ventana cuyo título contenga `title_match`. Devuelve (x,y,w,h)."""
    try:
        import pygetwindow as gw  # type: ignore
    except Exception:
        return None
    for w in gw.getAllWindows():
        if title_match.lower() in (w.title or "").lower() and w.width > 0 and w.height > 0:
            return (int(w.left), int(w.top), int(w.width), int(w.height))
    return None


class Capturer:
    def __init__(self, capture: CaptureProfile, reference_resolution: tuple[int, int]):
        self._cfg = capture
        self._ref = reference_resolution
        self._interval = 1.0 / max(capture.fps, 0.1)
        self._last_ts = 0.0
        self._sct = None  # mss instance (perezoso)

    def _ensure_sct(self):
        if self._sct is None:
            import mss  # import perezoso
            self._sct = mss.mss()
        return self._sct

    def _bbox(self) -> Region:
        if self._cfg.window_title_match:
            bbox = _find_window_bbox(self._cfg.window_title_match)
            if bbox:
                return bbox
        if self._cfg.region:
            return self._cfg.region
        raise RuntimeError(
            "No se pudo determinar la región de captura: ventana no encontrada y "
            "no hay 'region' en el perfil."
        )

    def _grab_window(self):
        """Captura la ventana/región completa (con cromo). Devuelve BGR sin redimensionar."""
        import numpy as np  # imports perezosos

        x, y, w, h = self._bbox()
        sct = self._ensure_sct()
        raw = sct.grab({"left": x, "top": y, "width": w, "height": h})
        return np.asarray(raw)[:, :, :3]  # BGRA -> BGR

    def _viewport(self, window_frame):
        """Devuelve la región (x,y,w,h) del área de juego dentro de `window_frame`."""
        vp = self._cfg.viewport
        if vp == "auto":
            from .viewport import detect_viewport
            return detect_viewport(window_frame, self._cfg.aspect_ratio)
        h, w = window_frame.shape[:2]
        # Fracciones de la ventana (todos 0..1) → robusto a cambios de tamaño;
        # si no, se interpretan como píxeles absolutos.
        if all(0.0 <= float(v) <= 1.0 for v in vp):
            x, y, fw, fh = vp
            return (int(x * w), int(y * h), int(fw * w), int(fh * h))
        return tuple(int(v) for v in vp)

    def grab(self):
        """Captura un frame, recorta el viewport del juego y lo normaliza a
        `reference_resolution`.

        Devuelve un array BGR (numpy) de tamaño (ref_h, ref_w, 3). Bloquea hasta
        respetar el intervalo de fps (captura a baja tasa)."""
        import cv2

        wait = self._interval - (time.monotonic() - self._last_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_ts = time.monotonic()

        window = self._grab_window()
        vx, vy, vw, vh = self._viewport(window)
        viewport = window[vy:vy + vh, vx:vx + vw] if vw > 0 and vh > 0 else window

        ref_w, ref_h = self._ref
        # Normaliza el viewport a la resolución de referencia: así las coordenadas del
        # perfil son estables sin importar tamaño de ventana ni cromo del emulador.
        if (viewport.shape[1], viewport.shape[0]) != (ref_w, ref_h):
            viewport = cv2.resize(viewport, (ref_w, ref_h), interpolation=cv2.INTER_AREA)
        return viewport
