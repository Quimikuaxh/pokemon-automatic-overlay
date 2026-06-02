"""OCR neural del mote (robusto a suavizado/HD).

Se usa EasyOCR (paquete pip, empaquetable con PyInstaller). El motor se carga una
vez (modelos ML) y se reutiliza. Solo se invoca al abrir el menú, sobre recortes
pequeños → coste acotado.
"""

from __future__ import annotations

from typing import Optional

from .profiles.schema import OcrProfile


class NeuralOCR:
    def __init__(self, cfg: OcrProfile):
        self._cfg = cfg
        self._reader = None

    def _ensure_reader(self):
        if self._reader is not None:
            return self._reader
        if self._cfg.engine == "easyocr":
            import easyocr  # import perezoso (arrastra torch)
            self._reader = easyocr.Reader([self._cfg.lang], gpu=False)
        else:
            raise NotImplementedError(f"Motor OCR no soportado: {self._cfg.engine}")
        return self._reader

    def read(self, text_bgr) -> Optional[str]:
        """Lee el texto de un recorte. Devuelve el string más probable o None."""
        reader = self._ensure_reader()
        results = reader.readtext(text_bgr, detail=1, paragraph=False)
        if not results:
            return None
        # results: list[(bbox, text, conf)] — quedarnos con la de mayor confianza.
        best = max(results, key=lambda r: r[2])
        text = (best[1] or "").strip()
        return text or None
