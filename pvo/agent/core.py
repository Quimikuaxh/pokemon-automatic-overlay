"""Núcleo del agente: ejecuta los comandos que llegan de la web y publica el equipo.

Deliberadamente **sin red**: recibe mensajes ya deserializados y emite mensajes por un
`send` inyectable. Así toda la lógica de control se puede probar sin WebSocket ni
emulador (ver `tests/test_agent_core.py`).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .. import sav
from ..appconfig import STATE_KEYS
from ..memory.games import GAMES
from ..publisher import Publisher
from . import protocol
from .sources import TeamSource, build_source

log = logging.getLogger("pvo.agent")

VERSION = "0.2.0"
SOURCES = ["sav", "retroarch"]

Send = Callable[[dict], None]
# Recibe los campos de estado que han cambiado, para que quien cree el agente los
# persista (normalmente en config.yaml). Ver `pvo.appconfig.persist_state`.
SaveState = Callable[[dict], None]


class AgentCore:
    def __init__(self, cfg: dict, send: Send, publisher: Optional[Publisher] = None,
                 save_state: Optional[SaveState] = None):
        self._cfg = cfg
        self._send = send
        self._save_state = save_state
        self._source: Optional[TeamSource] = None
        self._detail = "parado"
        self._error: Optional[str] = None
        self._publisher = publisher or Publisher(
            api_base=cfg.get("api_base", ""),
            ingest_token=cfg.get("ingest_token", ""),
            min_interval_s=float(cfg.get("publish_min_interval_s", 1.0)),
        )

    # -- estado ------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._source is not None

    def hello(self) -> dict:
        return protocol.hello(
            token=self._cfg.get("ingest_token", ""),
            version=VERSION,
            sources=SOURCES,
            games=sorted(GAMES),
            sav_formats=sav.supported_formats(),
        )

    def _status(self, request_id: str | None = None) -> dict:
        return protocol.status(
            running=self.running,
            source=self._source.key if self._source else None,
            detail=self._detail,
            error=self._error,
            request_id=request_id,
        )

    def push_status(self, request_id: str | None = None) -> None:
        self._send(self._status(request_id))

    # -- callbacks de las fuentes -----------------------------------------
    def _on_team(self, payload: dict, detail: str) -> None:
        self._detail = detail
        self._error = None
        self._publisher.publish(payload)
        self._send(protocol.team(payload, self._source.key if self._source else "?", detail))

    def _on_error(self, exc: Exception) -> None:
        self._error = str(exc)
        log.error("%s", exc)
        self.push_status()

    # -- persistencia ------------------------------------------------------
    def _persist(self, updates: dict) -> None:
        """Guarda el estado elegido desde la web para reanudarlo al reiniciar.

        Un fallo al escribir no debe tumbar al agente: se avisa y se sigue leyendo."""
        if self._save_state is None:
            return
        self._cfg.update({k: v for k, v in updates.items() if k in STATE_KEYS})
        try:
            self._save_state(updates)
        except Exception as e:                        # noqa: BLE001
            log.warning("No se pudo guardar la configuración (%s); "
                        "el agente sigue, pero no reanudará solo al reiniciar.", e)

    # -- comandos ----------------------------------------------------------
    def start(self, source: str, config: dict, request_id: str | None = None) -> None:
        self.stop(notify=False)
        merged = {**self._cfg, **(config or {})}
        try:
            src = build_source(source, merged, self._on_team, self._on_error)
            src.start()
        except Exception as e:                        # noqa: BLE001
            self._error = str(e)
            self._detail = "no se pudo arrancar"
            log.error("Arranque fallido: %s", e)
            self._send(protocol.error(str(e), request_id))
            self.push_status(request_id)
            return
        self._source = src
        self._error = None
        self._detail = src.describe()
        log.info("Fuente activa: %s", self._detail)
        # La web es quien elige la fuente: se guarda para reanudar al reiniciar.
        self._persist({"source": source, "autostart": True,
                       **{k: v for k, v in (config or {}).items() if k in STATE_KEYS}})
        self.push_status(request_id)

    def stop(self, notify: bool = True, request_id: str | None = None) -> None:
        was_running = self._source is not None
        if was_running:
            try:
                self._source.stop()
            except Exception as e:                    # noqa: BLE001
                log.warning("Error al parar la fuente: %s", e)
            self._source = None
            self._detail = "parado"
        if notify:
            # Parar desde la web también se recuerda: al reiniciar no arranca solo.
            if was_running:
                self._persist({"autostart": False})
            self.push_status(request_id)

    def detect_saves(self, request_id: str | None = None) -> None:
        from ..sav import locate

        try:
            found = [c.as_dict() for c in locate.find_saves()]
        except Exception as e:                        # noqa: BLE001
            self._send(protocol.error(f"Fallo buscando partidas: {e}", request_id))
            return
        log.info("Partidas encontradas: %d", len(found))
        self._send(protocol.saves(found, request_id))

    def inspect_save(self, path: str, request_id: str | None = None) -> None:
        from ..sav import locate

        cand = locate.inspect(path)
        if cand is None:
            self._send(protocol.error(
                f"'{path}' no se reconoce como partida guardada soportada.", request_id))
            return
        self._send(protocol.saves([cand.as_dict()], request_id))

    # -- despacho ----------------------------------------------------------
    def handle(self, msg: dict) -> None:
        """Procesa un mensaje del servidor. Nunca lanza."""
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")
        rid = msg.get("requestId")
        try:
            if kind == "start":
                self.start(msg.get("source", ""), msg.get("config") or {}, rid)
            elif kind == "stop":
                self.stop(request_id=rid)
            elif kind == "get_status":
                self.push_status(rid)
            elif kind == "detect_saves":
                self.detect_saves(rid)
            elif kind == "inspect_save":
                self.inspect_save(msg.get("path", ""), rid)
            elif kind == "ping":
                self._send(protocol.pong(rid))
            elif kind in ("welcome", "ack", None):
                pass
            else:
                self._send(protocol.error(f"Comando no soportado: {kind!r}", rid))
        except Exception as e:                        # noqa: BLE001
            log.exception("Fallo procesando %r", kind)
            self._send(protocol.error(str(e), rid))

    def close(self) -> None:
        self.stop(notify=False)
