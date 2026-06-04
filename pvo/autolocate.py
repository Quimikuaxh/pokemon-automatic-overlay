"""Auto-localización de los iconos del menú a partir del equipo conocido.

En vez de dibujar los 6 recuadros a mano, el usuario escribe qué Pokémon hay en cada
slot; la app desliza el sprite de referencia de cada uno por el frame
(`cv2.matchTemplate` enmascarado) y encuentra su posición exacta. Coordenadas
pixel-perfectas sin medir nada.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths


def load_name_map() -> dict[str, int]:
    for base in (paths.assets_dir(), paths.bundled_assets_dir()):
        p = base / "pokedex_names.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.strip().lower())


def name_to_dex(name: str, names: dict[str, int]) -> int | None:
    if not name.strip():
        return None
    key = name.strip().lower().replace(" ", "-")
    if key in names:
        return names[key]
    target = _norm(name)
    if target.isdigit():
        n = int(target)
        return n if 1 <= n <= 1025 else None
    for k, v in names.items():
        if _norm(k) == target:
            return v
    return None


def locate_team(frame_bgr, dex_list: list[int | None], gallery_npz: Path):
    """Para cada dex, devuelve ([x, y, S, S], score) de la mejor posición en el frame,
    o None si no hay dex o plantilla. `gallery_npz` es el templates.npz de referencia."""
    import cv2
    import numpy as np

    data = np.load(str(gallery_npz))
    dex = data["dex_ids"].astype(int)
    imgs = data["images"]
    size = int(data["size"]) if "size" in data.files else int(imgs.shape[1])
    by_dex = {int(dex[i]): imgs[i] for i in range(len(dex))}

    frame = frame_bgr.astype(np.float32)
    out: list[tuple[list[int], float] | None] = []
    for dn in dex_list:
        if dn is None or dn not in by_dex:
            out.append(None)
            continue
        a = by_dex[dn]
        tmpl = cv2.cvtColor(a[:, :, :3], cv2.COLOR_RGB2BGR).astype(np.float32)
        mask = ((a[:, :, 3] > 16).astype(np.uint8) * 255).astype(np.float32)
        res = cv2.matchTemplate(frame, tmpl, cv2.TM_CCORR_NORMED, mask=mask)
        res[~np.isfinite(res)] = -1.0
        _, score, _, loc = cv2.minMaxLoc(res)
        out.append(([int(loc[0]), int(loc[1]), size, size], float(score)))
    return out


def write_slots(profile_name: str, regions: list[list[int] | None]) -> Path:
    """Actualiza los icon_region del perfil del usuario con las regiones localizadas.

    Mantiene un text_region estimado a la derecha del icono (para el mote)."""
    import yaml

    profile_yaml = paths.profiles_dir() / f"{profile_name}.yaml"
    if not profile_yaml.exists():
        bundled = paths.bundled_profiles_dir() / f"{profile_name}.yaml"
        if bundled.exists():
            profile_yaml.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            raise FileNotFoundError(f"No existe el perfil {profile_yaml}")

    data = yaml.safe_load(profile_yaml.read_text(encoding="utf-8"))
    slots = data.get("slots") or [{} for _ in range(6)]
    for i, region in enumerate(regions):
        if i >= len(slots):
            break
        if region is None:
            continue
        x, y, w, h = region
        slots[i]["icon_region"] = [x, y, w, h]
        slots[i]["text_region"] = [x + w + 2, y + 6, 70, 12]  # estimación del mote
    data["slots"] = slots
    profile_yaml.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return profile_yaml
