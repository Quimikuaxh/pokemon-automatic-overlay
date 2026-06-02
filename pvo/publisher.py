"""Publica el equipo al endpoint de ingesta de claude-test.

Solo hace POST cuando el payload cambia respecto al último publicado (evita tráfico
innecesario en cada apertura del menú). El cliente HTTP es inyectable para poder
testear sin red.
"""

from __future__ import annotations

import json
import time
from typing import Callable, Optional

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
        self._url = f"{api_base.rstrip('/')}/api/stream-team/ingest/{ingest_token}"
        self._post = post_fn or _default_post
        self._min_interval = min_interval_s
        self._clock = clock
        self._last_sig: Optional[str] = None
        self._last_ts: float = float("-inf")

    @staticmethod
    def _signature(payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def publish(self, payload: dict, force: bool = False) -> bool:
        """Publica si el payload cambió (o force=True) y respeta el debounce.
        Devuelve True si se hizo POST con éxito (2xx)."""
        sig = self._signature(payload)
        now = self._clock()
        if not force:
            if sig == self._last_sig:
                return False
            if now - self._last_ts < self._min_interval:
                return False

        status = self._post(self._url, payload)
        if 200 <= status < 300:
            self._last_sig = sig
            self._last_ts = now
            return True
        return False
