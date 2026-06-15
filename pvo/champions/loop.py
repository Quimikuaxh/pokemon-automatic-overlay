"""Bucle del modo Champions: captura → clasifica pantalla → extrae → publica.

- Pantalla de SELECCIÓN: lee el equipo rival (iconos del panel) → publica fase 1.
- Pantalla de COMBATE: relee los activos cada intervalo (turnos) → publica fase 2.

La extracción (ZNCC sobre la galería) es lo caro, así que se limita por intervalo. El
clasificador y la captura son baratos y corren en cada frame.
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
import threading
import time
from pathlib import Path

from .. import paths
from ..capture import Capturer
from ..species_matcher import SpeciesMatcher
from .extractor import BattleExtractor
from .profile import ChampionsProfile, load_champions_profile
from .publisher import BattlePublisher
from .state import BattleState

log = logging.getLogger("pvo.champions")

READ_INTERVAL_S = 1.5  # cada cuánto reextraer especies (turnos / panel rival)


def resolve_champions_profile(name: str) -> ChampionsProfile:
    for base in (paths.profiles_dir(), paths.bundled_profiles_dir()):
        candidate = base / f"{name}.yaml"
        if candidate.exists():
            return load_champions_profile(candidate)
    raise FileNotFoundError(
        f"Perfil Champions '{name}' no encontrado en {paths.profiles_dir()} ni en los "
        f"ejemplos. Genéralo con: python -m pvo.main --calibrate-champions"
    )


def _with_gallery(profile: ChampionsProfile) -> ChampionsProfile:
    """Resuelve la galería Champions a la ruta CANÓNICA del usuario y la siembra ahí si
    falta (desde la ruta del perfil o desde la empaquetada). Devuelve el perfil con esa
    ruta absoluta, evitando depender de la ruta relativa del YAML (que al sembrarse podía
    quedar mal)."""
    canonical = paths.assets_dir() / "icons" / "champions" / "templates.npz"
    if not canonical.exists():
        for src in (profile.resolve(profile.species.gallery),
                    paths.bundled_assets_dir() / "icons" / "champions" / "templates.npz"):
            if src.exists() and src.resolve() != canonical.resolve():
                canonical.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, canonical)
                log.info("Galería Champions disponible en %s", canonical)
                break
    species = dataclasses.replace(profile.species, gallery=str(canonical))
    return dataclasses.replace(profile, species=species)


def _recognized(readings) -> list[int]:
    return [r.dex_id for r in readings if r.dex_id is not None]


def _fmt_scores(readings) -> list[tuple[int | None, float]]:
    return [(r.dex_id, round(r.score, 2)) for r in readings]


def run_champions_loop(cfg: dict, stop_event=None) -> int:
    missing = [k for k in ("api_base", "ingest_token") if not cfg.get(k)]
    if missing:
        log.error("Faltan campos en la config: %s", ", ".join(missing))
        return 2

    name = cfg.get("profile") or "champions"
    profile = resolve_champions_profile(name)
    log.info("Perfil Champions cargado: %s (%sx%s, modo %s)",
             profile.name, *profile.reference_resolution, profile.mode)

    thr = profile.species.min_similarity
    ov = cfg.get("min_similarity")
    if ov not in (None, ""):
        try:
            thr = float(ov)
        except (TypeError, ValueError):
            log.warning("min_similarity de config no es un número: %r (se ignora)", ov)
    log.info("Umbral de similitud: %.2f", thr)

    rival_thr = thr
    ov_r = cfg.get("rival_min_similarity")
    if ov_r not in (None, ""):
        try:
            rival_thr = float(ov_r)
        except (TypeError, ValueError):
            rival_thr = 0.25
    else:
        rival_thr = 0.25  # restringido al equipo rival → umbral más permisivo
    log.info("Umbral activos rivales (restringido al equipo): %.2f", rival_thr)

    profile = _with_gallery(profile)
    capturer = Capturer(profile.capture, profile.reference_resolution)
    matcher = SpeciesMatcher(profile)  # duck-typing: usa profile.resolve()/profile.species
    extractor = BattleExtractor(profile, matcher, min_similarity=thr, rival_min_similarity=rival_thr)
    state = BattleState(mode=profile.mode)
    publisher = BattlePublisher(
        api_base=cfg["api_base"],
        token=cfg["ingest_token"],
        min_interval_s=float(cfg.get("publish_min_interval_s", 0.5)),
    )
    log.info("Pipeline Champions listo. Captura la pantalla del juego en OBS (Proyector "
             "en ventana → Fuente).")

    stop = stop_event or threading.Event()
    last_read = 0.0
    last_beat = 0.0
    last_err = 0.0
    last_diag = 0.0
    # Anti-transitorio: una lectura solo se publica si se repite (estable) en 2 ciclos,
    # para que un frame malo de transición no pise el equipo/activos ya detectados.
    pending_sel: list[int] | None = None
    pending_bat: tuple[list[int], list[int]] | None = None
    first = True
    try:
        while not stop.is_set():
            try:
                frame = capturer.grab()
            except Exception as e:  # noqa: BLE001
                now = time.monotonic()
                if now - last_err >= 2.0:
                    last_err = now
                    log.error("No se pudo capturar la pantalla: %s", e)
                stop.wait(0.5)
                continue

            if first:
                first = False
                log.info("Captura OK: %sx%s px.", frame.shape[1], frame.shape[0])

            now = time.monotonic()
            if (now - last_read) < READ_INTERVAL_S:
                continue
            last_read = now

            # Clasificación por CONTENIDO (sin plantillas de pantalla): se leen los iconos
            # de ambas pantallas y gana la que reconozca más Pokémon. Robusto al fondo
            # compartido del estadio y sin depender de firmas calibradas.
            sel_readings = extractor.extract_selection(frame)
            sel_rivals = _recognized(sel_readings)
            allies_r, rivals_r = extractor.extract_battle(frame, rival_candidates=state.rivals)
            allies = _recognized(allies_r)
            rivals = _recognized(rivals_r)
            n_sel = len(sel_rivals)
            n_bat = len(allies) + len(rivals)

            if n_bat >= 2 and n_bat >= n_sel:
                screen = "battle"
            elif n_sel >= 3 and n_sel > n_bat:
                screen = "selection"
            else:
                screen = None

            if now - last_beat >= 4.0:
                last_beat = now
                log.info("vigilando… pantalla=%s (rivales_sel=%d, activos=%d)",
                         screen or "—", n_sel, n_bat)

            if screen == "selection":
                if sel_rivals != pending_sel:
                    pending_sel = sel_rivals  # esperar confirmación antes de publicar
                    continue
                payload = state.consider_selection(sel_rivals)
                if payload:
                    log.info("Selección — rivales: %s", sel_rivals)
                    log.info("  scores por slot: %s (umbral %.2f)", _fmt_scores(sel_readings), thr)
                    publisher.publish(payload)
            elif screen == "battle":
                if (len(allies) + len(rivals)) < (len(allies_r) + len(rivals_r)) and (now - last_diag) >= 5.0:
                    last_diag = now
                    log.info("slots combate — propios=%s rivales=%s (umbral %.2f / rival %.2f)",
                             _fmt_scores(allies_r), _fmt_scores(rivals_r), thr, rival_thr)
                cur = (allies, rivals)
                if cur != pending_bat:
                    pending_bat = cur  # esperar confirmación (filtra activos de transición)
                    continue
                payload = state.consider_battle(allies, rivals)
                if payload:
                    log.info("Combate — propios: %s | rivales: %s", allies, rivals)
                    publisher.publish(payload)
            elif (now - last_diag) >= 6.0:
                last_diag = now
                log.info("sin pantalla — sel=%s | combate propios=%s rivales=%s",
                         _fmt_scores(sel_readings), _fmt_scores(allies_r), _fmt_scores(rivals_r))
    except KeyboardInterrupt:
        pass
    log.info("Detenido.")
    return 0
