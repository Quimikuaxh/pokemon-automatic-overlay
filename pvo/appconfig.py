"""Config del agente (`config.yaml`).

El fichero tiene dos mitades muy distintas:

1. **Lo que rellena el usuario** (`USER_KEYS`): `api_base` e `ingest_token`, y nada más.
   Sin eso el agente no sabe con qué backend hablar.
2. **El estado que gestiona el agente** (`STATE_KEYS`): la fuente activa, la ruta de la
   partida, el juego, los intervalos… Eso se elige **desde el panel web**, y el agente
   lo persiste solo cada vez que cambia, para que al reiniciar el ejecutable reanude
   con lo último sin tener que volver a tocar el navegador.

La normalización es pura (sin PyYAML) → testeable con la stdlib; load/save añaden el I/O.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# --- lo que rellena el usuario ---
USER_KEYS = ("api_base", "ingest_token", "bridge_url")

# --- estado que el agente escribe solo cuando la web cambia algo ---
STATE_KEYS = (
    "source", "autostart",
    "sav_path", "sav_poll_interval_s", "sav_stable_for_s",
    "game", "retroarch_host", "retroarch_port", "retroarch_poll_interval_s",
    "publish_min_interval_s",
)

DEFAULT_CONFIG = {
    # Backend de claude-test (sin barra final) y token de ingesta de la máquina.
    "api_base": "",
    "ingest_token": "",
    # Override avanzado del WebSocket de control; vacío = derivado de api_base.
    "bridge_url": "",

    # --- Estado gestionado por el agente (no editar a mano) ---
    # Fuente activa: "" (nada elegido todavía), "sav" o "retroarch".
    "source": "",
    # ¿Estaba leyendo cuando se cerró? Si sí, al arrancar reanuda solo.
    "autostart": False,
    "sav_path": "",
    "sav_poll_interval_s": 1.0,
    "sav_stable_for_s": 1.5,
    "game": "",
    "retroarch_host": "127.0.0.1",
    "retroarch_port": 55355,
    "retroarch_poll_interval_s": 1.0,
    "publish_min_interval_s": 1.0,
}

_FLOATS = ("publish_min_interval_s", "sav_poll_interval_s", "sav_stable_for_s",
           "retroarch_poll_interval_s")
SOURCES = ("sav", "retroarch")


def bridge_url_for(api_base: str, token: str) -> str:
    """URL del WebSocket de control derivada del backend: https→wss, http→ws."""
    if not api_base:
        return ""
    parts = urlsplit(api_base.rstrip("/"))
    scheme = "wss" if parts.scheme == "https" else "ws"
    path = parts.path.rstrip("/") + "/api/stream-team/agent"
    if token:
        path += f"/{token}"
    return urlunsplit((scheme, parts.netloc, path, "", ""))


def normalize_config(raw: dict | None) -> dict:
    """Devuelve un dict con todas las claves esperadas, aplicando defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        for k in DEFAULT_CONFIG:
            if raw.get(k) is not None:
                cfg[k] = raw[k]

    for k in _FLOATS:
        try:
            cfg[k] = float(cfg[k])
        except (TypeError, ValueError):
            cfg[k] = DEFAULT_CONFIG[k]
    try:
        cfg["retroarch_port"] = int(cfg["retroarch_port"])
    except (TypeError, ValueError):
        cfg["retroarch_port"] = DEFAULT_CONFIG["retroarch_port"]

    source = str(cfg["source"] or "").lower()
    cfg["source"] = source if source in SOURCES else ""
    cfg["autostart"] = bool(cfg["autostart"])
    cfg["api_base"] = str(cfg["api_base"] or "").rstrip("/")
    if not cfg["bridge_url"]:
        cfg["bridge_url"] = bridge_url_for(cfg["api_base"], str(cfg["ingest_token"] or ""))
    return cfg


def can_resume(cfg: dict) -> bool:
    """¿Hay estado persistido suficiente para reanudar sin esperar a la web?"""
    if not cfg.get("autostart"):
        return False
    if cfg.get("source") == "sav":
        return bool(cfg.get("sav_path"))
    if cfg.get("source") == "retroarch":
        return bool(cfg.get("game"))
    return False


def load_app_config(path: str | Path) -> dict:
    import yaml

    p = Path(path)
    raw = None
    if p.exists():
        with p.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    return normalize_config(raw)


def save_app_config(path: str | Path, cfg: dict) -> None:
    import yaml

    data = normalize_config(cfg)
    with Path(path).open("w", encoding="utf-8") as fh:
        fh.write("# Config del agente poke-overlay.\n"
                 "# Solo api_base e ingest_token son tuyos: el resto lo gestiona el\n"
                 "# agente segun lo que elijas en la pestana Stream de claude-test.\n")
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def merge_state(cfg: dict, updates: dict) -> dict:
    """Aplica sobre `cfg` solo las claves de estado presentes en `updates`."""
    merged = dict(cfg)
    for k, v in updates.items():
        if k in STATE_KEYS and v is not None:
            merged[k] = v
    return normalize_config(merged)


def persist_state(path: str | Path, cfg: dict, updates: dict) -> dict:
    """Guarda el estado nuevo en disco y devuelve la config resultante.

    Se llama cuando la web cambia la fuente o la para, para que el siguiente arranque
    del ejecutable reanude sin intervención."""
    merged = merge_state(cfg, updates)
    save_app_config(path, merged)
    return merged
