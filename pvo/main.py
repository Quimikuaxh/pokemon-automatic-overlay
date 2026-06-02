"""Loop de orquestación: captura → detecta menú → extrae → cachea → publica.

El trabajo continuo es barato (captura a baja fps + detector ligero). La extracción
(embeddings + OCR) solo se dispara en el flanco de apertura del menú; entre medias el
equipo cacheado se mantiene estático y se republica si cambió.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .capture import Capturer
from .extractor import TeamExtractor
from .menu_detector import MenuDetector
from .ocr import NeuralOCR
from .profiles.schema import GameProfile, load_profile
from .publisher import Publisher
from .species_matcher import SpeciesMatcher
from .state import TeamState

log = logging.getLogger("pvo")

PROFILES_DIR = Path(__file__).parent / "profiles"


def load_config(path: Path) -> dict:
    import yaml
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_profile(name: str) -> GameProfile:
    candidate = PROFILES_DIR / f"{name}.yaml"
    if not candidate.exists():
        raise FileNotFoundError(f"Perfil no encontrado: {candidate}")
    return load_profile(candidate)


def build_pipeline(profile: GameProfile, cfg: dict):
    capturer = Capturer(profile.capture, profile.reference_resolution)
    detector = MenuDetector(profile)
    matcher = SpeciesMatcher(profile)
    ocr = NeuralOCR(profile.ocr)
    extractor = TeamExtractor(profile, matcher, ocr)
    state = TeamState(min_similarity=profile.species.min_similarity)
    publisher = Publisher(
        api_base=cfg["api_base"],
        ingest_token=cfg["ingest_token"],
        min_interval_s=float(cfg.get("publish_min_interval_s", 1.0)),
    )
    return capturer, detector, extractor, state, publisher


def run(config_path: Path) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(config_path)
    for key in ("api_base", "ingest_token", "profile"):
        if not cfg.get(key):
            log.error("Falta '%s' en %s", key, config_path)
            return 2

    profile = resolve_profile(cfg["profile"])
    log.info("Perfil cargado: %s (%sx%s)", profile.name, *profile.reference_resolution)

    capturer, detector, extractor, state, publisher = build_pipeline(profile, cfg)
    log.info("Pipeline listo. Vigilando el menú de equipo… (Ctrl+C para salir)")

    try:
        while True:
            frame = capturer.grab()
            opened = detector.update(frame)
            if not opened:
                continue
            # Flanco de apertura del menú: extraer una vez.
            readings = extractor.extract(frame)
            if state.consider(readings):
                payload = state.to_payload()
                ok = publisher.publish(payload)
                log.info("Equipo actualizado %s -> publicado=%s", payload["pokemonIds"], ok)
            else:
                log.debug("Lectura no válida o sin cambios; se mantiene el cache.")
    except KeyboardInterrupt:
        log.info("Saliendo.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Overlay de equipo Pokémon por visión.")
    parser.add_argument(
        "-c", "--config", default="config.yaml",
        help="Ruta al fichero de config (por defecto: config.yaml)",
    )
    args = parser.parse_args(argv)
    return run(Path(args.config))


if __name__ == "__main__":
    sys.exit(main())
