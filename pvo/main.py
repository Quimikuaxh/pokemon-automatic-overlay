"""Punto de entrada del agente (headless).

Ya no hay ventana: la interfaz vive en la web de claude-test. El agente se conecta a
ella por WebSocket saliente y obedece sus órdenes (arrancar/parar, elegir fuente,
buscar partidas guardadas).

Lo que se elige en la web se **persiste solo** en `config.yaml`, así que al volver a
abrir el ejecutable reanuda con lo último sin tocar el navegador. Si no hay nada
guardado, se queda esperando órdenes.

    poke-overlay                 # arranca el agente (reanuda lo último, si lo hay)
    poke-overlay --detect-saves  # lista las partidas guardadas encontradas
    poke-overlay --read <save>   # lee un fichero de partida y muestra el equipo
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from . import paths
from .appconfig import can_resume, load_app_config, persist_state, save_app_config
from .agent.core import VERSION

log = logging.getLogger("pvo")


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# --------------------------------------------------------------------- utilidades


def cmd_detect_saves() -> int:
    from .sav import locate

    found = locate.find_saves()
    if not found:
        print("No se encontraron partidas guardadas en las rutas habituales.")
        print("Rutas rastreadas:")
        for r in locate.default_roots():
            print(f"  - {r}")
        return 1
    for c in found:
        print(f"{c.path}\n    {c.label} — {c.team_count} Pokémon ({c.size} bytes)")
    return 0


def cmd_read(path: str) -> int:
    from . import sav

    try:
        team = sav.read_team_file(path)
    except (sav.SaveError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"{team.label}")
    for note in team.notes:
        print(f"  ({note})")
    for i, slot in enumerate(team.slots, 1):
        if slot is None:
            print(f"  {i}. —")
        else:
            dex, nick = slot
            print(f"  {i}. #{dex}" + (f' "{nick}"' if nick else ""))
    return 0


# --------------------------------------------------------------------- agente


def run_agent(cfg: dict, config_path: Path) -> int:
    from .agent.bridge import Bridge

    missing = [k for k in ("api_base", "ingest_token") if not cfg.get(k)]
    if missing:
        log.error("Faltan campos en %s: %s. Cópialos de config.example.yaml "
                  "(api_base = backend de claude-test, ingest_token = pestaña Stream).",
                  config_path, ", ".join(missing))
        return 2

    stopped = threading.Event()

    def save_state(updates: dict) -> None:
        persist_state(config_path, cfg, updates)

    bridge = Bridge(cfg["bridge_url"], cfg, save_state=save_state)
    core = bridge.core
    threading.Thread(target=bridge.run_forever, name="bridge", daemon=True).start()

    # Si la última vez se quedó leyendo algo, se reanuda sin esperar a la web.
    if can_resume(cfg):
        log.info("Reanudando la última configuración (%s).", cfg["source"])
        core.start(cfg["source"], cfg)
    elif cfg.get("source"):
        log.info("La última vez lo dejaste parado (%s): esperando a que le des a "
                 "Arrancar en la pestaña Stream de claude-test.", cfg["source"])
    else:
        log.info("Sin configuración previa: elige la fuente en la pestaña Stream "
                 "de claude-test.")

    def _sig(_signum, _frame):
        stopped.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _sig)
        except (ValueError, AttributeError):
            pass

    log.info("Agente poke-overlay %s en marcha. Ctrl+C para salir.", VERSION)
    try:
        while not stopped.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    bridge.stop()
    log.info("Agente detenido.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="poke-overlay",
        description="Agente que lee el equipo Pokémon y lo publica en el overlay de claude-test.",
    )
    parser.add_argument("-c", "--config", default=None, help="Ruta a config.yaml")
    parser.add_argument("--detect-saves", action="store_true",
                        help="Lista las partidas guardadas detectadas y sale")
    parser.add_argument("--read", metavar="FICHERO",
                        help="Lee un fichero de partida, muestra el equipo y sale")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"poke-overlay {VERSION}")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    if args.detect_saves:
        return cmd_detect_saves()
    if args.read:
        return cmd_read(args.read)

    config_path = Path(args.config) if args.config else paths.config_path()
    if not config_path.exists():
        log.warning("No hay config en %s; se crea una vacía a partir de los defaults.",
                    config_path)
        save_app_config(config_path, {})
    cfg = load_app_config(config_path)
    return run_agent(cfg, config_path)


if __name__ == "__main__":
    sys.exit(main())
