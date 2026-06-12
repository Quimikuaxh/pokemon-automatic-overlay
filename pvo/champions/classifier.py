"""Clasificador de pantalla: ¿selección de equipo o combate?

Mismo principio que `menu_detector`: un template match barato sobre una región fija por
pantalla, con histéresis (N frames estables) para no conmutar durante transiciones.
Devuelve la pantalla actualmente estable: 'selection', 'battle' o None.
"""

from __future__ import annotations

from .profile import ChampionsProfile, ScreenSignature


def _crop(frame, region):
    x, y, w, h = region
    return frame[y:y + h, x:x + w]


class ScreenClassifier:
    def __init__(self, profile: ChampionsProfile):
        import cv2

        self._screens = profile.screens
        self._templates = {}
        for key, sig in self._screens.items():
            tpl_path = str(profile.resolve(sig.template))
            tpl = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
            if tpl is None:
                raise FileNotFoundError(
                    f"No se pudo cargar el template de pantalla '{key}': {tpl_path}\n"
                    f"Calíbralo con: python -m pvo.main --calibrate-champions"
                )
            self._templates[key] = tpl
        self._streak: dict[str, int] = {k: 0 for k in self._screens}
        self._current: str | None = None
        self._conf: dict[str, float] = {k: 0.0 for k in self._screens}

    def _confidence(self, frame, key: str, sig: ScreenSignature) -> float:
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        region = _crop(gray, sig.region)
        tpl = self._templates[key]
        if region.shape[0] < tpl.shape[0] or region.shape[1] < tpl.shape[1]:
            return 0.0
        res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return float(max_val)

    def update(self, frame) -> str | None:
        """Devuelve la pantalla actualmente estable ('selection'|'battle') o None."""
        best_key, best_conf = None, -1.0
        for key, sig in self._screens.items():
            c = self._confidence(frame, key, sig)
            self._conf[key] = c
            above = c >= sig.min_confidence
            self._streak[key] = self._streak[key] + 1 if above else 0
            if above and c > best_conf:
                best_key, best_conf = key, c

        # La pantalla candidata es la que supera su umbral con racha suficiente.
        if best_key is not None and self._streak[best_key] >= self._screens[best_key].stable_frames:
            self._current = best_key
        elif all(self._streak[k] == 0 for k in self._screens):
            self._current = None
        return self._current

    @property
    def current(self) -> str | None:
        return self._current

    @property
    def confidences(self) -> dict[str, float]:
        return dict(self._conf)
