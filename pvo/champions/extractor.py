"""Extracción de especies por slot mediante el matcher de sprite (ZNCC).

Recorta cada región de icono y la identifica contra la galería Champions. Devuelve dex
IDs (o None si el score no supera el umbral). Mismo `SpeciesMatcher` que el modo
emulador, así que ambas fases comparten la galería y la métrica.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..species_matcher import SpeciesMatcher
from .profile import ChampionsProfile


@dataclass(frozen=True)
class IconReading:
    dex_id: int | None
    score: float


def _crop(frame, region):
    x, y, w, h = region
    return frame[y:y + h, x:x + w]


class BattleExtractor:
    def __init__(self, profile: ChampionsProfile, matcher: SpeciesMatcher, min_similarity: float):
        self._profile = profile
        self._matcher = matcher
        self._thr = min_similarity

    def _read(self, frame, region) -> IconReading:
        crop = _crop(frame, region)
        if crop.size == 0:
            return IconReading(None, 0.0)
        dex, score = self._matcher.match(crop)
        if dex is None or score < self._thr:
            return IconReading(None, score)
        return IconReading(dex, score)

    def extract_selection(self, frame) -> list[IconReading]:
        """Lee los iconos del panel rival en la pantalla de selección."""
        return [self._read(frame, r) for r in self._profile.selection_rival_slots]

    def extract_battle(self, frame) -> tuple[list[IconReading], list[IconReading]]:
        """Lee los iconos de los activos: (propios, rivales)."""
        allies = [self._read(frame, r) for r in self._profile.battle_ally_slots]
        rivals = [self._read(frame, r) for r in self._profile.battle_rival_slots]
        return allies, rivals
