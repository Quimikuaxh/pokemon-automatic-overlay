"""Carga/guardado de la config de la app (config.yaml) y listado de perfiles.

La normalización es pura (sin PyYAML) → testeable con la stdlib; load/save añaden el
I/O con YAML.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_CONFIG = {
    "api_base": "",
    "ingest_token": "",
    "profile": "",
    "publish_min_interval_s": 1.0,
    "min_similarity": "",  # vacío = usar el del perfil; si no, override (0–1)
    # Fuente del equipo: "vision" (visión sobre la pantalla) o "retroarch" (memoria).
    "source": "vision",
    "retroarch_host": "127.0.0.1",
    "retroarch_port": 55355,
    "party_address": "0x020244EC",  # gPlayerParty en Pokémon Esmeralda (GBA)
}


def normalize_config(raw: dict | None) -> dict:
    """Devuelve un dict con todas las claves esperadas, aplicando defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        for k in DEFAULT_CONFIG:
            if raw.get(k) is not None:
                cfg[k] = raw[k]
    try:
        cfg["publish_min_interval_s"] = float(cfg["publish_min_interval_s"])
    except (TypeError, ValueError):
        cfg["publish_min_interval_s"] = DEFAULT_CONFIG["publish_min_interval_s"]
    return cfg


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
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def list_profiles(profiles_dir: str | Path) -> list[str]:
    """Nombres (sin extensión) de los perfiles YAML disponibles, ordenados."""
    p = Path(profiles_dir)
    if not p.exists():
        return []
    return sorted(f.stem for f in p.glob("*.yaml"))
