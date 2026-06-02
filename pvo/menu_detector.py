"""Detector del menú de equipo: el "gatillo" ligero del pipeline.

Corre en cada frame capturado y decide CUÁNDO extraer. Hace un único template match
sobre una región fija (barato) e implementa histéresis: exige N frames seguidos por
encima del umbral antes de declarar el menú abierto, evitando leer durante la
animación de apertura.
"""

from __future__ import annotations

from .profiles.schema import MenuDetector as MenuDetectorProfile
from .profiles.schema import GameProfile


def _crop(frame, region):
    x, y, w, h = region
    return frame[y:y + h, x:x + w]


class MenuDetector:
    def __init__(self, profile: GameProfile):
        import cv2  # imports perezosos

        self._cfg: MenuDetectorProfile = profile.menu_detector
        tpl_path = str(profile.resolve(self._cfg.template))
        tpl = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
        if tpl is None:
            raise FileNotFoundError(f"No se pudo cargar el template del menú: {tpl_path}")
        self._template = tpl
        self._streak = 0
        self._open = False

    def confidence(self, frame) -> float:
        """Confianza de que el menú está abierto en este frame [0..1]."""
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        region = _crop(gray, self._cfg.region)
        res = cv2.matchTemplate(region, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return float(max_val)

    def update(self, frame) -> bool:
        """Actualiza la histéresis con un nuevo frame. Devuelve True solo en el
        frame en que el menú PASA a estar establemente abierto (flanco de subida),
        para disparar la extracción una vez por apertura."""
        above = self.confidence(frame) >= self._cfg.min_confidence
        if above:
            self._streak += 1
        else:
            self._streak = 0
            self._open = False
            return False

        if not self._open and self._streak >= self._cfg.stable_frames:
            self._open = True
            return True
        return False

    @property
    def is_open(self) -> bool:
        return self._open
