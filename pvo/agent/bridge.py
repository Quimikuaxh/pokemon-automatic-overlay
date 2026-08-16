"""Transporte del canal de control: WebSocket **saliente** con reconexión.

El agente es siempre quien inicia la conexión (`wss://<backend>/api/stream-team/agent/
<ingest_token>`), así que no hay que abrir puertos en el PC del usuario y funciona
igual con la web publicada en https.

Si la conexión se cae, se reintenta con espera exponencial (1s → 30s) sin parar la
fuente activa: el equipo se sigue publicando por HTTP mientras tanto.
"""

from __future__ import annotations

import json
import logging
import threading

from .core import AgentCore

log = logging.getLogger("pvo.agent.bridge")

_BACKOFF_START = 1.0
_BACKOFF_MAX = 30.0


class Bridge:
    def __init__(self, url: str, cfg: dict, ping_interval_s: float = 25.0,
                 save_state=None):
        self.url = url
        self._cfg = cfg
        self._ping = ping_interval_s
        self._ws = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.core = AgentCore(cfg, send=self.send, save_state=save_state)

    # -- envío -------------------------------------------------------------
    def send(self, msg: dict) -> None:
        with self._lock:
            ws = self._ws
        if ws is None:
            log.debug("Sin canal de control; mensaje descartado: %s", msg.get("type"))
            return
        try:
            ws.send(json.dumps(msg, ensure_ascii=False))
        except Exception as e:                        # noqa: BLE001
            log.warning("No se pudo enviar %s: %s", msg.get("type"), e)

    # -- bucle -------------------------------------------------------------
    def run_forever(self) -> None:
        try:
            import websocket                          # websocket-client
        except ImportError:
            log.error("Falta la dependencia 'websocket-client' "
                      "(pip install -r requirements.txt). Sin ella el agente no puede "
                      "hablar con la web, que es de donde recibe las órdenes.")
            self._stop.wait()
            return

        backoff = _BACKOFF_START
        while not self._stop.is_set():
            try:
                log.info("Conectando al canal de control: %s", _safe(self.url))
                ws = websocket.create_connection(self.url, timeout=10)
                ws.settimeout(self._ping + 10)
                with self._lock:
                    self._ws = ws
                backoff = _BACKOFF_START
                log.info("Canal de control conectado.")
                self.send(self.core.hello())
                self.core.push_status()
                self._pump(ws)
            except Exception as e:                    # noqa: BLE001
                log.warning("Canal de control caído (%s). Reintento en %.0fs.", e, backoff)
            finally:
                with self._lock:
                    self._ws = None
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, _BACKOFF_MAX)
        log.info("Canal de control detenido.")

    def _pump(self, ws) -> None:
        import websocket

        while not self._stop.is_set():
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                ws.ping()
                continue
            if raw is None or raw == "":
                raise ConnectionError("el servidor cerró la conexión")
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                log.warning("Mensaje no-JSON descartado.")
                continue
            self.core.handle(msg)

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:                         # noqa: BLE001
                pass
        self.core.close()


def _safe(url: str) -> str:
    """Oculta el token del final de la URL en los logs."""
    head, _, tail = url.rpartition("/")
    if len(tail) >= 8:
        tail = tail[:4] + "…" + tail[-4:]
    return f"{head}/{tail}"
