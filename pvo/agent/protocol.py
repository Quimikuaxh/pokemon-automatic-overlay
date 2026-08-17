"""Protocolo del canal de control agente ↔ claude-test.

El agente abre un **WebSocket saliente** hacia el backend y se autentica con el
`ingest_token`. Es saliente a propósito: así funciona con la web en producción (https)
sin abrir puertos en el PC del usuario ni chocar con el bloqueo de *mixed content*.

Mensajes (JSON, campo `type`):

    agente → servidor
      hello    {token, agent, version, capabilities:{sources, games, savFormats}}
      status   {running, source, detail, error}
      team     {pokemonIds, nicknames, source, detail}
      saves    {requestId, candidates:[{path, size, parserKey, label, teamCount}]}
      error    {requestId, message}
      pong     {requestId}

    servidor → agente
      start        {source: "sav"|"retroarch", config:{...}}
      stop         {}
      get_status   {}
      detect_saves {}
      inspect_save {path}
      ping         {}

Todo mensaje del servidor puede traer `requestId`; el agente lo devuelve en su
respuesta para que la web case pregunta y respuesta.
"""

from __future__ import annotations

PROTOCOL_VERSION = 1

# --- agente → servidor -----------------------------------------------------


def hello(token: str, version: str, sources: list[str], games: list[str],
          sav_formats: list[tuple[str, str]]) -> dict:
    return {
        "type": "hello",
        "protocol": PROTOCOL_VERSION,
        "token": token,
        "agent": "poke-overlay",
        "version": version,
        "capabilities": {
            "sources": sources,
            "games": games,
            "savFormats": [{"key": k, "label": lbl} for k, lbl in sav_formats],
        },
    }


def status(running: bool, source: str | None, detail: str, error: str | None = None,
           request_id: str | None = None) -> dict:
    return _rid({
        "type": "status", "running": running, "source": source,
        "detail": detail, "error": error,
    }, request_id)


def team(payload: dict, source: str, detail: str) -> dict:
    return {
        "type": "team",
        "pokemonIds": payload.get("pokemonIds", []),
        "nicknames": payload.get("nicknames", []),
        "source": source,
        "detail": detail,
    }


def saves(candidates: list[dict], request_id: str | None = None) -> dict:
    return _rid({"type": "saves", "candidates": candidates}, request_id)


def error(message: str, request_id: str | None = None) -> dict:
    return _rid({"type": "error", "message": message}, request_id)


def pong(request_id: str | None = None) -> dict:
    return _rid({"type": "pong"}, request_id)


def _rid(msg: dict, request_id: str | None) -> dict:
    if request_id is not None:
        msg["requestId"] = request_id
    return msg
