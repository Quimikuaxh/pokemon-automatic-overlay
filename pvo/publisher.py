"""Publica el equipo al endpoint de ingesta de claude-test.

Solo hace POST cuando el payload cambia respecto al último publicado (evita tráfico
innecesario en cada apertura del menú). El cliente HTTP es inyectable para poder
testear sin red.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable, Optional

log = logging.getLogger("pvo.publisher")

# (url, json_body) -> status_code
PostFn = Callable[[str, dict], int]


def _default_post(url: str, body: dict) -> int:
    import requests  # import perezoso

    resp = requests.post(url, json=body, timeout=10)
    return resp.status_code


class Publisher:
    def __init__(
        self,
        api_base: str,
        ingest_token: str,
        post_fn: Optional[PostFn] = None,
        min_interval_s: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._base = api_base.rstrip("/")
        self._token = ingest_token
        self._url = f"{self._base}/api/stream-team/ingest/{ingest_token}"
        self._post = post_fn or _default_post
        self._min_interval = min_interval_s
        self._clock = clock
        self._last_sig: Optional[str] = None
        self._last_ts: float = float("-inf")

    @staticmethod
    def _signature(payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _safe_url(self) -> str:
        # No exponer el token en los logs.
        tok = self._token
        masked = (tok[:4] + "…" + tok[-4:]) if len(tok) >= 8 else "****"
        return f"{self._base}/api/stream-team/ingest/{masked}"

    def publish(self, payload: dict, force: bool = False) -> bool:
        """Publica si el payload cambió (o force=True) y respeta el debounce.
        Devuelve True si se hizo POST con éxito (2xx). Nunca lanza: los errores de
        red se registran y devuelven False."""
        sig = self._signature(payload)
        now = self._clock()
        if not force:
            if sig == self._last_sig:
                log.debug("Payload sin cambios; no se reenvía.")
                return False
            if now - self._last_ts < self._min_interval:
                log.info("Cambio detectado pero dentro del debounce (%.1fs); se omite el envío.",
                         self._min_interval)
                return False

        log.info("Enviando equipo a %s …", self._safe_url())
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
            log.error("HTTP 404: el ingest_token no existe en el backend. Revisa el token.")
        elif status in (401, 403):
            log.error("HTTP %s: no autorizado. Revisa el token/permisos.", status)
        else:
            log.error("El endpoint respondió HTTP %s (envío fallido).", status)
        return False
