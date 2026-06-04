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

from . import paths
from .capture import Capturer
from .extractor import TeamExtractor
from .menu_detector import MenuDetector
from .ocr import NeuralOCR
from .profiles.schema import GameProfile, load_profile
from .publisher import Publisher
from .species_matcher import SpeciesMatcher
from .state import TeamState

log = logging.getLogger("pvo")

# Resolución nativa por generación/sistema. El aspecto se deriva (w/h). Elegir la
# generación al calibrar fija estos valores automáticamente.
GEN_PRESETS: dict[int, tuple[int, int]] = {
    3: (240, 160),   # GBA
    4: (256, 192),   # NDS
    5: (256, 192),   # NDS
    6: (400, 240),   # 3DS (pantalla superior)
    7: (400, 240),   # 3DS (pantalla superior)
    8: (480, 270),   # Switch (16:9, resolución de trabajo)
    9: (480, 270),   # Switch
}


def load_config(path: Path) -> dict:
    import yaml
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_profile(name: str) -> GameProfile:
    # Busca primero en los perfiles del usuario (escribibles, junto al .exe) y luego
    # en los ejemplos empaquetados.
    for base in (paths.profiles_dir(), paths.bundled_profiles_dir()):
        candidate = base / f"{name}.yaml"
        if candidate.exists():
            return load_profile(candidate)
    raise FileNotFoundError(
        f"Perfil '{name}' no encontrado en {paths.profiles_dir()} ni en los ejemplos. "
        f"Créalo con el asistente de calibración."
    )


def build_pipeline(profile: GameProfile, cfg: dict):
    # Umbral: override de config si está, si no el del perfil.
    thr = profile.species.min_similarity
    ov = cfg.get("min_similarity")
    if ov not in (None, ""):
        try:
            thr = float(ov)
        except (TypeError, ValueError):
            log.warning("min_similarity de config no es un número: %r (se ignora)", ov)
    log.info("Umbral de similitud: %.2f", thr)

    capturer = Capturer(profile.capture, profile.reference_resolution)
    detector = MenuDetector(profile)
    matcher = SpeciesMatcher(profile)
    ocr = NeuralOCR(profile.ocr)
    extractor = TeamExtractor(profile, matcher, ocr, min_similarity=thr)
    state = TeamState(min_similarity=thr)
    publisher = Publisher(
        api_base=cfg["api_base"],
        ingest_token=cfg["ingest_token"],
        min_interval_s=float(cfg.get("publish_min_interval_s", 1.0)),
    )
    return capturer, detector, extractor, state, publisher


def run_memory_loop(cfg: dict, stop_event=None) -> int:
    """Lee el equipo de la memoria del emulador vía RetroArch y lo publica.

    Mucho más fiable que la visión (sin calibrar ni reconocer iconos). Solo gen 3
    de momento."""
    import json
    import threading

    from .memory.gen3 import decode_party
    from .memory.retroarch import RetroArchClient

    host = cfg.get("retroarch_host") or "127.0.0.1"
    port = int(cfg.get("retroarch_port") or 55355)
    try:
        addr = int(str(cfg.get("party_address") or "0x020244EC"), 0)
    except ValueError:
        log.error("party_address inválida: %r (ej. 0x020244EC)", cfg.get("party_address"))
        return 2

    client = RetroArchClient(host, port)
    publisher = Publisher(
        api_base=cfg["api_base"], ingest_token=cfg["ingest_token"],
        min_interval_s=float(cfg.get("publish_min_interval_s", 1.0)),
    )
    log.info("Fuente: RetroArch (memoria) %s:%s, equipo en 0x%X.", host, port, addr)

    stop = stop_event or threading.Event()
    last_sig = None
    last_err = 0.0
    import time
    while not stop.is_set():
        try:
            raw = client.read_memory(addr, 600)
            party = decode_party(raw)
            ids = [p[0] if p else None for p in party]
            nicks = [p[1] if p else None for p in party]
            payload = {"pokemonIds": ids, "nicknames": nicks}
            sig = json.dumps(payload, sort_keys=True)
            if sig != last_sig:
                last_sig = sig
                log.info("Equipo: %s", ids)
                publisher.publish(payload)
        except Exception as e:  # noqa: BLE001
            now = time.monotonic()
            if now - last_err >= 3.0:
                last_err = now
                log.error("Lectura de memoria falló: %s", e)
        stop.wait(1.0)
    log.info("Detenido.")
    return 0


def run_with_config(cfg: dict, stop_event=None) -> int:
    """Arranca el pipeline con una config ya cargada. Se detiene cuando `stop_event`
    se activa (o con Ctrl+C). Usado tanto por la CLI como por la GUI."""
    import threading

    missing = [k for k in ("api_base", "ingest_token") if not cfg.get(k)]
    if missing:
        log.error("Faltan campos en la config: %s", ", ".join(missing))
        return 2

    if (cfg.get("source") or "vision").lower() == "retroarch":
        return run_memory_loop(cfg, stop_event)

    if not cfg.get("profile"):
        log.error("Falta 'profile' (fuente=visión).")
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
                log.warning("Ningún Pokémon reconocido. Revisa el encuadre de los "
                            "iconos al calibrar (ajustados al sprite) y la generación elegida.")
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
    paths.ensure_seeded()
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

    # La generación fija resolución y aspecto (salvo que se pasen --res/--aspect).
    preset = GEN_PRESETS.get(args.gen) if args.gen else None
    if args.res:
        res = _parse_res(args.res)
    elif preset:
        res = preset
    else:
        res = (240, 160)
    aspect = args.aspect
    if aspect is None and preset:
        aspect = preset[0] / preset[1]
    log.info("Calibrando '%s' (gen %s): resolución %sx%s, aspecto %.3f",
             args.calibrate, args.gen, res[0], res[1], aspect or 0.0)

    capture = CaptureProfile(
        window_title_match=args.window,
        region=_parse_region(args.region) if args.region else None,
        fps=3.0,
        viewport=_parse_region(args.viewport) if args.viewport and args.viewport != "auto" else "auto",
        aspect_ratio=aspect,
    )
    return run_calibration(
        name=args.calibrate,
        capture=capture,
        reference_resolution=res,
        lang=args.lang,
        profiles_dir=paths.profiles_dir(),
        assets_dir=paths.assets_dir(),
        species_gen=args.gen,
    )


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:]) if argv is None else list(argv)

    parser = argparse.ArgumentParser(description="Overlay de equipo Pokémon por visión.")
    parser.add_argument(
        "-c", "--config", default=None,
        help="Ruta al fichero de config (por defecto: config.yaml junto al ejecutable)",
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
    parser.add_argument("--gen", type=int, help="[calibración] generación de sprites (3-9) → usa la galería compartida gen<N>")
    parser.add_argument("--res", default=None, help="[calibración] resolución de referencia 'WxH' (si no, la fija --gen)")
    parser.add_argument("--lang", default="es", help="[calibración] idioma del OCR")
    args = parser.parse_args(argv)

    if args.calibrate:
        return run_calibrate(args)

    # Sin argumentos (p. ej. doble clic en el .exe) → interfaz gráfica.
    if args.gui or (not raw_args and not args.no_gui):
        from .gui import launch
        return launch()

    config_path = Path(args.config) if args.config else paths.config_path()
    return run(config_path)


if __name__ == "__main__":
    sys.exit(main())
