"""Extracción del equipo a partir de un frame del menú abierto.

Orquesta los 6 slots: por cada uno recorta el icono (→ especie por embeddings) y, si
el perfil lo define, el recuadro del mote (→ OCR). Trabajo pesado pero PUNTUAL: solo
se llama cuando el detector confirma el menú abierto.
"""

from __future__ import annotations

import logging

from .profiles.schema import GameProfile
from .state import SlotReading

log = logging.getLogger("pvo.extractor")


def _crop(frame, region):
    x, y, w, h = region
    return frame[y:y + h, x:x + w]


class TeamExtractor:
    def __init__(self, profile: GameProfile, matcher, ocr=None):
        self._profile = profile
        self._matcher = matcher
        self._ocr = ocr

    def extract(self, frame) -> list[SlotReading]:
        thr = self._profile.species.min_similarity
        readings: list[SlotReading] = []
        for i, slot in enumerate(self._profile.slots):
            icon = _crop(frame, slot.icon_region)
            dex_id, score = self._matcher.match(icon)
            ok = score >= thr

            nickname = None
            if ok and self._ocr is not None and slot.text_region is not None:
                nickname = self._ocr.read(_crop(frame, slot.text_region))

            if ok:
                log.info("  slot %d: dex=%s (sim %.2f) ✓%s",
                         i + 1, dex_id, score, f" mote='{nickname}'" if nickname else "")
                readings.append(SlotReading(dex_id=dex_id, species_score=score, nickname=nickname))
            else:
                # Mejor candidato por debajo del umbral → se trata como no fiable/vacío.
                log.info("  slot %d: mejor candidato dex=%s (sim %.2f) ✗ descartado < %.2f",
                         i + 1, dex_id, score, thr)
                readings.append(SlotReading(dex_id=None, species_score=score))
        return readings
