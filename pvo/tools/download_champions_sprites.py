"""Descarga los menu sprites de Pokémon Champions desde Bulbagarden Archives.

Usa la API de MediaWiki (no scraping de HTML): un generator de categoría que devuelve
directamente la URL de cada archivo, con paginación por 'continue'. Los nombres siguen
el patrón `Menu_CP_<dex4>[-variante].png`.

Uso:
    python -m pvo.tools.download_champions_sprites
    python -m pvo.tools.download_champions_sprites --out assets/icons/champions/src
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

API = "https://archives.bulbagarden.net/w/api.php"
CATEGORY = "Category:Champions_menu_sprites"
UA = "pokemon-vision-overlay/1.0 (gallery builder; contact: local use)"


def _iter_files(session):
    """Genera (filename, url) de todos los archivos de la categoría."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "categorymembers",
        "gcmtitle": CATEGORY,
        "gcmtype": "file",
        "gcmlimit": "500",
        "prop": "imageinfo",
        "iiprop": "url",
    }
    while True:
        resp = session.get(API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            title = page.get("title", "")
            info = page.get("imageinfo") or []
            if not info:
                continue
            url = info[0].get("url")
            if not url:
                continue
            filename = title.split(":", 1)[-1]  # quita el prefijo "File:"
            yield filename, url
        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)


def download(out_dir: Path) -> int:
    import requests

    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    count, skipped = 0, 0
    for filename, url in _iter_files(session):
        dest = out_dir / filename
        if dest.exists() and dest.stat().st_size > 0:
            skipped += 1
            continue
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            dest.write_bytes(r.content)
            count += 1
            if count % 25 == 0:
                print(f"  …{count} descargados")
            time.sleep(0.05)  # cortesía con el servidor
        except Exception as e:  # noqa: BLE001
            print(f"  ! fallo con {filename}: {e}")
    print(f"Descargados {count} sprites nuevos ({skipped} ya existían) en {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("assets/icons/champions/src"))
    args = p.parse_args(argv)
    return download(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
