"""Bucle del modo Champions: captura → clasifica pantalla → extrae → publica.

- Pantalla de SELECCIÓN: lee el equipo rival (iconos del panel) → publica fase 1.
- Pantalla de COMBATE: relee los activos cada intervalo (turnos) → publica fase 2.

La extracción (ZNCC sobre la galería) es lo caro, así que se limita por intervalo. El
clasificador y la captura son baratos y corren en cada frame.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .. import paths
from ..capture import Capturer
from ..species_matcher import SpeciesMatcher
from .classifier import ScreenClassifier
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


def _recognized(readings) -> list[int]:
    return [r.dex_id for r in readings if r.dex_id is not None]


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

    capturer = Capturer(profile.capture, profile.reference_resolution)
    matcher = SpeciesMatcher(profile)  # duck-typing: usa profile.resolve()/profile.species
    classifier = ScreenClassifier(profile)
    extractor = BattleExtractor(profile, matcher, min_similarity=thr)
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

            screen = classifier.update(frame)
            now = time.monotonic()
            if now - last_beat >= 2.0:
                last_beat = now
                confs = ", ".join(f"{k}={v:.2f}" for k, v in classifier.confidences.items())
                log.info("vigilando… pantalla=%s (%s)", screen or "—", confs)

            if screen is None or (now - last_read) < READ_INTERVAL_S:
                continue
            last_read = now

            if screen == "selection":
                readings = extractor.extract_selection(frame)
                rivals = _recognized(readings)
                if not rivals:
                    continue
                payload = state.consider_selection(rivals)
                if payload:
                    log.info("Selección — rivales: %s", rivals)
                    publisher.publish(payload)
            elif screen == "battle":
                allies_r, rivals_r = extractor.extract_battle(frame)
                allies = _recognized(allies_r)
                rivals = _recognized(rivals_r)
                if not allies and not rivals:
                    continue
                payload = state.consider_battle(allies, rivals)
                if payload:
                    log.info("Combate — propios: %s | rivales: %s", allies, rivals)
                    publisher.publish(payload)
    except KeyboardInterrupt:
        pass
    log.info("Detenido.")
    return 0
