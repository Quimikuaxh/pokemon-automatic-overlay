"""Extracción del equipo a partir de un frame del menú abierto.

Orquesta los 6 slots: por cada uno recorta el icono (→ especie por embeddings) y, si
el perfil lo define, el recuadro del mote (→ OCR). Trabajo pesado pero PUNTUAL: solo
se llama cuando el detector confirma el menú abierto.
"""

from __future__ import annotations

from .profiles.schema import GameProfile
from .state import SlotReading


def _crop(frame, region):
    x, y, w, h = region
    return frame[y:y + h, x:x + w]


class TeamExtractor:
    def __init__(self, profile: GameProfile, matcher, ocr=None):
        self._profile = profile
        self._matcher = matcher
        self._ocr = ocr

    def extract(self, frame) -> list[SlotReading]:
        readings: list[SlotReading] = []
        for slot in self._profile.slots:
            icon = _crop(frame, slot.icon_region)
            dex_id, score = self._matcher.match(icon)
            if score < self._profile.species.min_similarity:
                # Por debajo del umbral lo tratamos como slot vacío/no fiable.
                readings.append(SlotReading(dex_id=None, species_score=score))
                continue

            nickname = None
            if self._ocr is not None and slot.text_region is not None:
                nickname = self._ocr.read(_crop(frame, slot.text_region))

            readings.append(SlotReading(dex_id=dex_id, species_score=score, nickname=nickname))
        return readings
