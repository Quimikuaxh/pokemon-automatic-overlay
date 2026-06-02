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
    if not config_path.exists():
        log.error(
            "No se encontró el fichero de config: %s\n"
            "Copia 'config.example.yaml' a '%s' y rellena api_base/ingest_token/profile.",
            config_path, config_path.name,
        )
        return 2
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


def _parse_region(text: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("región debe ser 'x,y,w,h'")
    return tuple(parts)  # type: ignore[return-value]


def _parse_res(text: str) -> tuple[int, int]:
    w, h = text.lower().split("x")
    return (int(w), int(h))


def run_calibrate(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from .calibrate import run_calibration
    from .profiles.schema import CaptureProfile

    if not args.window and not args.region:
        log.error("Calibración: indica --window \"<título>\" o --region x,y,w,h")
        return 2
    capture = CaptureProfile(
        window_title_match=args.window,
        region=_parse_region(args.region) if args.region else None,
        fps=3.0,
        viewport=_parse_region(args.viewport) if args.viewport and args.viewport != "auto" else "auto",
        aspect_ratio=args.aspect,
    )
    assets_dir = Path(__file__).parent.parent / "assets"
    return run_calibration(
        name=args.calibrate,
        capture=capture,
        reference_resolution=_parse_res(args.res),
        lang=args.lang,
        profiles_dir=PROFILES_DIR,
        assets_dir=assets_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Overlay de equipo Pokémon por visión.")
    parser.add_argument(
        "-c", "--config", default="config.yaml",
        help="Ruta al fichero de config (por defecto: config.yaml)",
    )
    parser.add_argument(
        "--calibrate", metavar="NAME",
        help="Lanza el asistente de calibración y genera el perfil NAME.",
    )
    parser.add_argument("--window", help="[calibración] subcadena del título de la ventana del emulador")
    parser.add_argument("--region", help="[calibración] región de captura 'x,y,w,h' (alternativa a --window)")
    parser.add_argument("--viewport", default="auto", help="[calibración] 'auto' o 'x,y,w,h' del área de juego")
    parser.add_argument("--aspect", type=float, help="[calibración] relación de aspecto del sistema (p. ej. 1.5)")
    parser.add_argument("--res", default="240x160", help="[calibración] resolución de referencia 'WxH'")
    parser.add_argument("--lang", default="es", help="[calibración] idioma del OCR")
    args = parser.parse_args(argv)

    if args.calibrate:
        return run_calibrate(args)
    return run(Path(args.config))


if __name__ == "__main__":
    sys.exit(main())
