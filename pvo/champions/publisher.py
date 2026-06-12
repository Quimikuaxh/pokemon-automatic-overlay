"""Publica el estado de combate al endpoint de claude-test.

`POST {api_base}/api/stream-team/battle/{token}` (token = ingest_token del usuario, el
mismo del modo stream/ingesta). Solo hace POST si el contenido cambió (ignorando 'turn')
y respeta el debounce. Cliente HTTP inyectable para testear sin red.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable, Optional

log = logging.getLogger("pvo.champions.publisher")

PostFn = Callable[[str, dict], int]


def _default_post(url: str, body: dict) -> int:
    import requests

    resp = requests.post(url, json=body, timeout=10)
    return resp.status_code


class BattlePublisher:
    def __init__(
        self,
        api_base: str,
        token: str,
        post_fn: Optional[PostFn] = None,
        min_interval_s: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._base = api_base.rstrip("/")
        self._token = token
        self._url = f"{self._base}/api/stream-team/battle/{token}"
        self._post = post_fn or _default_post
        self._min_interval = min_interval_s
        self._clock = clock
        self._last_sig: Optional[str] = None
        self._last_ts: float = float("-inf")

    @staticmethod
    def _signature(payload: dict) -> str:
        # 'turn' avanza en cada cambio; no debe contar para la igualdad de contenido.
        body = {k: v for k, v in payload.items() if k != "turn"}
        return json.dumps(body, sort_keys=True, ensure_ascii=False)

    def _safe_url(self) -> str:
        tok = self._token
        masked = (tok[:4] + "…" + tok[-4:]) if len(tok) >= 8 else "****"
        return f"{self._base}/api/stream-team/battle/{masked}"

    def publish(self, payload: dict, force: bool = False) -> bool:
        sig = self._signature(payload)
        now = self._clock()
        if not force:
            if sig == self._last_sig:
                return False
            if now - self._last_ts < self._min_interval:
                log.info("Cambio dentro del debounce (%.1fs); se omite.", self._min_interval)
                return False

        log.info("Enviando combate a %s … (fase %s, turno %s)",
                 self._safe_url(), payload.get("phase"), payload.get("turn"))
        try:
            status = self._post(self._url, payload)
        except Exception as e:  # noqa: BLE001
            log.error("No se pudo contactar con el endpoint (%s): %s", self._safe_url(), e)
            return False

        if 200 <= status < 300:
            log.info("Enviado OK (HTTP %s).", status)
            self._last_sig = sig
            self._last_ts = now
            return True
        if status == 404:
            log.error("HTTP 404: el token no existe en el backend. Revisa el token (ingest_token).")
        elif status == 400:
            log.error("HTTP 400: payload inválido.")
        else:
            log.error("El endpoint respondió HTTP %s (envío fallido).", status)
        return False
