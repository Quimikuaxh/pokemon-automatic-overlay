"""Estado de combate: cachea la última lectura por pantalla y decide cuándo publicar.

Pura lógica, sin dependencias de visión → testeable con la stdlib. Construye el payload
para `POST /api/stream-team/battle/:token` y mantiene un contador de turno que avanza en
cada cambio (marcador monótono para la web).
"""

from __future__ import annotations


class BattleState:
    def __init__(self, mode: str = "Doubles"):
        self.mode = mode
        self._rivals: list[int] = []          # equipo rival detectado en selección
        self._active_allies: list[int] = []   # activos propios (combate)
        self._active_rivals: list[int] = []   # activos rivales (combate)
        self._turn = 0

    def consider_selection(self, rival_dexes: list[int]) -> dict | None:
        """Lectura de la pantalla de selección. Devuelve payload si cambió, si no None."""
        rivals = list(rival_dexes)
        if rivals == self._rivals:
            return None
        self._rivals = rivals
        return self._payload(phase=1)

    def consider_battle(self, ally_dexes: list[int], rival_dexes: list[int]) -> dict | None:
        """Lectura de la pantalla de combate. Devuelve payload si cambió, si no None."""
        allies = list(ally_dexes)
        rivals = list(rival_dexes)
        if allies == self._active_allies and rivals == self._active_rivals:
            return None
        self._active_allies = allies
        self._active_rivals = rivals
        return self._payload(phase=2)

    def _payload(self, phase: int) -> dict:
        self._turn += 1
        return {
            "phase": phase,
            "mode": self.mode,
            "rivals": list(self._rivals),
            "activeAllies": list(self._active_allies) if phase == 2 else [],
            "activeRivals": list(self._active_rivals) if phase == 2 else [],
            "turn": self._turn,
        }

    @property
    def turn(self) -> int:
        return self._turn

    @property
    def rivals(self) -> list[int]:
        """Equipo rival detectado en la fase de selección (para acotar los activos)."""
        return list(self._rivals)
