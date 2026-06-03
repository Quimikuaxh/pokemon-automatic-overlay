"""Identificación de especie por TEMPLATE MATCHING ENMASCARADO (sin torch).

Compara solo los píxeles del Pokémon usando la máscara alfa de cada sprite, de modo
que **ignora el fondo del panel del menú** (que es lo que despistaba al comparar la
imagen entera). Métrica ZNCC (invariante a brillo/contraste) con una pequeña búsqueda
de desplazamiento para absorber el bamboleo del icono. Automático para toda la
Pokédex; solo numpy + OpenCV.

La galería es un `templates.npz` con `dex_ids` (int32), `images` (N,S,S,4 uint8 RGBA)
y `size` (S). Se genera con `pvo.tools.build_templates`.
"""

from __future__ import annotations

from typing import Optional

from .profiles.schema import GameProfile

_OFFSETS_Y = (-2, -1, 0, 1, 2)
_OFFSETS_X = (-1, 0, 1)


class SpeciesMatcher:
    def __init__(self, profile: GameProfile):
        import numpy as np

        path = profile.resolve(profile.species.gallery)
        # Auto-curación: perfiles antiguos apuntan a 'embeddings.npz'. Si al lado hay
        # un 'templates.npz' (formato actual), úsalo sin tener que recalibrar.
        alt = path.with_name("templates.npz")
        if path.name != "templates.npz" and alt.exists():
            path = alt
        if not path.exists():
            raise FileNotFoundError(
                f"No existe la galería de plantillas: {path}\n"
                f"Debería venir incluida (gen<N>) o generarse con "
                f"python -m pvo.tools.build_templates."
            )
        data = np.load(str(path))
        if "images" not in data.files:
            raise ValueError(
                f"La galería {path} tiene un formato antiguo (sin 'images'). "
                f"Vuelve a calibrar el perfil con la generación, o regenérala con "
                f"python -m pvo.tools.build_templates."
            )
        self._dex = data["dex_ids"].astype(int)
        imgs = data["images"]  # (N, S, S, 4) uint8 RGBA
        self._size = int(data["size"]) if "size" in data.files else int(imgs.shape[1])

        rgb = imgs[:, :, :, :3].astype(np.float32)
        masks = imgs[:, :, :, 3] > 16
        # Precalcula, por plantilla, el vector de primer plano normalizado (para ZNCC).
        self._masks, self._tv, self._tn = [], [], []
        for i in range(len(self._dex)):
            m = masks[i]
            v = rgb[i][m].ravel()
            v = v - v.mean()
            self._masks.append(m)
            self._tv.append(v)
            self._tn.append(float(np.sqrt((v * v).sum())))

    def match(self, icon_bgr) -> tuple[Optional[int], float]:
        """Devuelve (dex_id, score ZNCC en [-1,1]) del mejor sprite."""
        import cv2
        import numpy as np

        s = self._size
        crop = cv2.cvtColor(icon_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
        crop = cv2.resize(crop, (s, s), interpolation=cv2.INTER_AREA)
        shifted = [np.roll(np.roll(crop, dy, 0), dx, 1)
                   for dy in _OFFSETS_Y for dx in _OFFSETS_X]

        best, best_dex = -2.0, None
        for i in range(len(self._dex)):
            tn = self._tn[i]
            if tn < 1e-6:
                continue
            m, tv = self._masks[i], self._tv[i]
            for c in shifted:
                cm = c[m].ravel()
                cm = cm - cm.mean()
                cn = np.sqrt((cm * cm).sum())
                if cn < 1e-6:
                    continue
                score = float((cm * tv).sum() / (cn * tn))
                if score > best:
                    best, best_dex = score, int(self._dex[i])
        return best_dex, best
