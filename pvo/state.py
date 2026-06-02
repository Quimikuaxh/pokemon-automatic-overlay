"""Estado del equipo: cachea la última lectura válida y la mantiene estática.

Pura lógica, sin dependencias de visión → testeable con la stdlib. El patrón de uso
es: leer al abrir el menú, validar, y solo sobrescribir el cache si la lectura es
fiable. Mientras se viaja/combate (sin menú), `consider` no se llama y el equipo
permanece igual.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SlotReading:
    """Lectura de un slot del menú de equipo."""
    dex_id: Optional[int]          # None = slot vacío
    species_score: float = 0.0     # similitud del matching de especie [0..1]
    nickname: Optional[str] = None


class TeamState:
    def __init__(self, min_similarity: float = 0.85, slot_count: int = 6):
        self.min_similarity = min_similarity
        self.slot_count = slot_count
        self._pokemon_ids: list[Optional[int]] = [None] * slot_count
        self._nicknames: list[Optional[str]] = [None] * slot_count
        self._has_team = False

    @staticmethod
    def is_valid(readings: list[SlotReading], min_similarity: float, slot_count: int) -> bool:
        """Una lectura es válida si tiene el nº correcto de slots y cada slot
        OCUPADO supera el umbral de similitud. Slots vacíos no exigen score."""
        if len(readings) != slot_count:
            return False
        occupied = 0
        for r in readings:
            if r.dex_id is None:
                continue
            occupied += 1
            if r.species_score < min_similarity:
                return False
        # Al menos un Pokémon identificado para considerarla una lectura real.
        return occupied > 0

    def consider(self, readings: list[SlotReading]) -> bool:
        """Evalúa una nueva lectura. Si es válida y difiere del cache, lo actualiza.
        Devuelve True si el equipo cacheado cambió."""
        if not self.is_valid(readings, self.min_similarity, self.slot_count):
            return False

        new_ids = [r.dex_id for r in readings]
        new_nicks = [r.nickname for r in readings]
        if self._has_team and new_ids == self._pokemon_ids and new_nicks == self._nicknames:
            return False

        self._pokemon_ids = new_ids
        self._nicknames = new_nicks
        self._has_team = True
        return True

    @property
    def has_team(self) -> bool:
        return self._has_team

    def to_payload(self) -> dict:
        """Payload para el endpoint de ingesta de claude-test."""
        return {
            "pokemonIds": list(self._pokemon_ids),
            "nicknames": list(self._nicknames),
        }
