"""Fuentes de equipo del agente: de dónde salen los 6 Pokémon.

Las dos fuentes exponen el mismo contrato (`TeamSource`), así que el agente y la web
las tratan igual:

- **sav**: relee el fichero de partida guardada cuando el emulador lo reescribe
  (es decir, cuando el usuario guarda dentro del juego). Única opción en 3DS.
- **retroarch**: lee la memoria del juego en vivo por los Network Commands de
  RetroArch. Solo para los juegos de `pvo.memory.games`.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from .. import sav
from ..memory.games import GAMES

log = logging.getLogger("pvo.agent.sources")

# (payload, detalle) → lo consume el agente para publicar y para informar a la web.
OnTeam = Callable[[dict, str], None]
OnError = Callable[[Exception], None]


class TeamSource:
    """Interfaz común. `start` es no bloqueante; `stop` es idempotente."""

    key = "?"

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return self.key


class SavSource(TeamSource):
    key = "sav"

    def __init__(self, path: str | Path, on_team: OnTeam, on_error: OnError,
                 poll_interval_s: float = 1.0, stable_for_s: float = 1.5):
        self.path = Path(path)
        self._on_team = on_team
        self._on_error = on_error
        self._watcher = sav.SaveWatcher(
            self.path,
            on_change=self._reload,
            on_error=on_error,
            poll_interval_s=poll_interval_s,
            stable_for_s=stable_for_s,
        )

    def _reload(self, path: Path) -> None:
        team = sav.read_team_file(path)          # lanza SaveError → lo captura el watcher
        log.info("Equipo leído de %s (%s): %s", path.name, team.parser_key,
                 team.payload()["pokemonIds"])
        self._on_team(team.payload(), f"{team.label} — {path.name}")

    def start(self) -> None:
        if not self.path.exists():
            raise sav.SaveError(f"No existe el fichero de partida: {self.path}")
        # Lectura inicial: valida la ruta ya y deja el overlay con el equipo actual.
        self._watcher.start()

    def stop(self) -> None:
        self._watcher.stop()

    def describe(self) -> str:
        return f"partida guardada: {self.path}"


class RetroArchSource(TeamSource):
    key = "retroarch"

    def __init__(self, game: str, on_team: OnTeam, on_error: OnError,
                 host: str = "127.0.0.1", port: int = 55355,
                 poll_interval_s: float = 1.0):
        if game not in GAMES:
            raise KeyError(
                f"Juego desconocido: {game!r}. Disponibles: {', '.join(sorted(GAMES))}"
            )
        self.game = game
        spec = GAMES[game]
        self._addr = int(spec["address"], 0)
        self._gen = int(spec["gen"])
        self._mon_size = int(spec["mon_size"])
        self._host, self._port = host, int(port)
        self._interval = max(0.2, float(poll_interval_s))
        self._on_team = on_team
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _decode(self, raw: bytes) -> list:
        if self._gen == 3:
            from ..memory.gen3 import decode_party
            return decode_party(raw)
        from ..memory.gen45 import decode_party
        return decode_party(raw, self._mon_size)

    def _run(self) -> None:
        from ..memory.retroarch import RetroArchClient

        client = RetroArchClient(self._host, self._port)
        last_err = 0.0
        import time
        while not self._stop.is_set():
            try:
                raw = client.read_memory(self._addr, 6 * self._mon_size)
                party = self._decode(raw)
                payload = {
                    "pokemonIds": [p[0] if p else None for p in party],
                    "nicknames": [p[1] if p else None for p in party],
                }
                self._on_team(payload, f"{self.game} (memoria)")
            except Exception as e:                    # noqa: BLE001
                now = time.monotonic()
                if now - last_err >= 5.0:             # no inundar el log/la web
                    last_err = now
                    self._on_error(e)
            self._stop.wait(self._interval)
        client.close()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="retroarch-source", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def describe(self) -> str:
        return f"RetroArch {self._host}:{self._port} — {self.game} (0x{self._addr:X})"


def build_source(source: str, config: dict, on_team: OnTeam, on_error: OnError) -> TeamSource:
    """Crea la fuente pedida a partir de un dict de configuración."""
    source = (source or "").lower()
    if source == "sav":
        path = config.get("sav_path") or config.get("savPath")
        if not path:
            raise ValueError("Falta la ruta del fichero de partida ('sav_path').")
        return SavSource(
            path, on_team, on_error,
            poll_interval_s=float(config.get("sav_poll_interval_s", 1.0)),
            stable_for_s=float(config.get("sav_stable_for_s", 1.5)),
        )
    if source == "retroarch":
        game = config.get("game")
        if not game:
            raise ValueError("Falta el juego ('game') para la lectura por memoria.")
        return RetroArchSource(
            game, on_team, on_error,
            host=config.get("retroarch_host") or "127.0.0.1",
            port=int(config.get("retroarch_port") or 55355),
            poll_interval_s=float(config.get("retroarch_poll_interval_s", 1.0)),
        )
    raise ValueError(f"Fuente desconocida: {source!r} (usa 'sav' o 'retroarch').")
