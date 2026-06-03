"""Aprender el equipo actual: galería de iconos a partir de TUS propias capturas.

Los sprites genéricos fallan porque su fondo no es el del menú del juego. Aquí se
capturan los iconos tal cual se ven en tu emulador (mismo fondo, mismo render, mismo
bamboleo), se etiquetan con el Pokémon, y se construye/actualiza una galería personal
para ese perfil. El reconocimiento de tu equipo sube muchísimo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths


def load_name_map() -> dict[str, int]:
    """nombre (inglés, minúsculas) → nº de Pokédex nacional."""
    for base in (paths.assets_dir(), paths.bundled_assets_dir()):
        p = base / "pokedex_names.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.strip().lower())


def name_to_dex(name: str, names: dict[str, int]) -> int | None:
    """Resuelve un nombre escrito por el usuario a su dex (tolerante a mayúsculas,
    espacios, guiones y signos)."""
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


def upsert_gallery(npz_path: Path, entries: list[tuple[int, object]]) -> int:
    """Inserta/actualiza (dex → vector) en la galería personal. Devuelve el total."""
    import numpy as np

    npz_path.parent.mkdir(parents=True, exist_ok=True)
    if npz_path.exists():
        data = np.load(str(npz_path))
        dex = list(int(d) for d in data["dex_ids"])
        vecs = list(data["vectors"].astype("float32"))
    else:
        dex, vecs = [], []
    index = {d: i for i, d in enumerate(dex)}
    for d, v in entries:
        if d in index:
            vecs[index[d]] = v
        else:
            index[d] = len(dex)
            dex.append(d)
            vecs.append(v)
    np.savez_compressed(str(npz_path),
                        dex_ids=np.asarray(dex, dtype=np.int32),
                        vectors=np.asarray(vecs, dtype="float32"))
    return len(dex)


def _rewrite_profile_embeddings(profile_yaml: Path, rel_embeddings: str) -> None:
    import yaml
    data = yaml.safe_load(profile_yaml.read_text(encoding="utf-8"))
    data.setdefault("species", {})["embeddings"] = rel_embeddings
    profile_yaml.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def learn_from_crops(profile_name: str, slot_names: dict[int, str], crops: dict[int, object]) -> str:
    """Etiqueta los iconos capturados, calcula embeddings y los guarda en la galería
    personal del perfil; ajusta el perfil para usarla. Devuelve un resumen."""
    from .species_matcher import build_embedder

    names = load_name_map()
    embed, _ = build_embedder()

    entries: list[tuple[int, object]] = []
    learned: list[str] = []
    unknown: list[str] = []
    for slot, raw_name in slot_names.items():
        if not raw_name.strip():
            continue
        dex = name_to_dex(raw_name, names)
        if dex is None:
            unknown.append(raw_name)
            continue
        entries.append((dex, embed(crops[slot])))
        learned.append(f"slot {slot + 1}={raw_name} (dex {dex})")

    if not entries:
        return "No se aprendió nada (¿nombres vacíos o no reconocidos?)."

    gallery = paths.assets_dir() / "icons" / profile_name / "embeddings.npz"
    total = upsert_gallery(gallery, entries)

    # Asegura que el perfil del usuario apunte a la galería personal.
    profile_yaml = paths.profiles_dir() / f"{profile_name}.yaml"
    if not profile_yaml.exists():
        bundled = paths.bundled_profiles_dir() / f"{profile_name}.yaml"
        if bundled.exists():
            profile_yaml.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
    if profile_yaml.exists():
        import os
        rel = os.path.relpath(gallery, paths.profiles_dir()).replace("\\", "/")
        _rewrite_profile_embeddings(profile_yaml, rel)

    msg = f"Aprendidos {len(entries)} ({', '.join(learned)}). Galería personal: {total} Pokémon."
    if unknown:
        msg += f" No reconocidos: {', '.join(unknown)}."
    return msg
