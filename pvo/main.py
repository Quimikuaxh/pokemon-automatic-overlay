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


def run_with_config(cfg: dict, stop_event=None) -> int:
    """Arranca el pipeline con una config ya cargada. Se detiene cuando `stop_event`
    se activa (o con Ctrl+C). Usado tanto por la CLI como por la GUI."""
    import threading

    missing = [k for k in ("api_base", "ingest_token", "profile") if not cfg.get(k)]
    if missing:
        log.error("Faltan campos en la config: %s", ", ".join(missing))
        return 2

    profile = resolve_profile(cfg["profile"])
    log.info("Perfil cargado: %s (%sx%s)", profile.name, *profile.reference_resolution)

    capturer, detector, extractor, state, publisher = build_pipeline(profile, cfg)
    log.info("Pipeline listo. Vigilando el menú de equipo…")

    stop = stop_event or threading.Event()
    import time
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
                stop.wait(0.5)  # no martillear si la ventana no está
                continue

            if first:
                first = False
                log.info("Captura OK: %sx%s px. Abre el menú de equipo en el emulador.",
                         frame.shape[1], frame.shape[0])

            opened = detector.update(frame)
            now = time.monotonic()
            if now - last_beat >= 2.0:
                last_beat = now
                log.info("vigilando… menú=%s (confianza %.2f / umbral %.2f)",
                         "SÍ" if detector.is_open else "no",
                         detector.last_confidence, detector.min_confidence)

            if not opened:
                continue

            # Flanco de apertura del menú: extraer una vez.
            log.info("Menú detectado — leyendo equipo:")
            readings = extractor.extract(frame)
            recognised = sum(1 for r in readings if r.dex_id)
            log.info("Reconocidos %d/6: %s", recognised, [r.dex_id for r in readings])
            if recognised == 0:
                log.warning("Ningún Pokémon reconocido. ¿Generaste embeddings.npz y "
                            "calibraste bien las regiones de los iconos?")
                continue
            if state.consider(readings):
                publisher.publish(state.to_payload())
            else:
                log.info("Equipo igual que la última lectura; no se reenvía.")
    except KeyboardInterrupt:
        pass
    log.info("Detenido.")
    return 0


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
    return run_with_config(cfg)


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


def run_build_embeddings(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.icons or not args.out:
        log.error("--build-embeddings requiere --icons <carpeta> y --out <fichero.npz>")
        return 2
    from .tools.build_embeddings import build
    return build(Path(args.icons), Path(args.out))


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:]) if argv is None else list(argv)

    parser = argparse.ArgumentParser(description="Overlay de equipo Pokémon por visión.")
    parser.add_argument(
        "-c", "--config", default="config.yaml",
        help="Ruta al fichero de config (por defecto: config.yaml)",
    )
    parser.add_argument("--gui", action="store_true", help="Abre la interfaz gráfica.")
    parser.add_argument("--no-gui", action="store_true", help="Fuerza el modo headless (sin GUI).")
    parser.add_argument(
        "--calibrate", metavar="NAME",
        help="Lanza el asistente de calibración y genera el perfil NAME.",
    )
    parser.add_argument("--window", help="[calibración] subcadena del título de la ventana del emulador")
    parser.add_argument("--region", help="[calibración] región de captura 'x,y,w,h' (alternativa a --window)")
    parser.add_argument("--viewport", default="auto", help="[calibración] 'auto' o 'x,y,w,h' del área de juego")
    parser.add_argument("--aspect", type=float, help="[calibración] relación de aspecto del sistema (p. ej. 1.5)")
    parser.add_argument("--res", default="240x160", help="[calibración] resolución de referencia 'WxH'")
    parser.add_argument("--lang", default="es", help="[calibración/embeddings] idioma del OCR")
    parser.add_argument("--build-embeddings", action="store_true", help="Genera embeddings.npz")
    parser.add_argument("--icons", help="[embeddings] carpeta con iconos NNN.png")
    parser.add_argument("--out", help="[embeddings] ruta de salida del .npz")
    args = parser.parse_args(argv)

    if args.calibrate:
        return run_calibrate(args)
    if args.build_embeddings:
        return run_build_embeddings(args)

    # Sin argumentos (p. ej. doble clic en el .exe) → interfaz gráfica.
    if args.gui or (not raw_args and not args.no_gui):
        from .gui import launch
        return launch()

    return run(Path(args.config))


if __name__ == "__main__":
    sys.exit(main())
