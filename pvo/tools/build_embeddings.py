"""Genera el `embeddings.npz` de referencia para un perfil.

Toma una carpeta de iconos de referencia nombrados por nº de Pokédex
(`25.png`, `131.png`, …) — capturados/extraídos del MISMO render del usuario, para
que el matching tolere sus filtros/texturas HD — y guarda sus embeddings L2.

Uso:
    python -m pvo.tools.build_embeddings --icons assets/icons/gba_emerald --out assets/icons/gba_emerald/embeddings.npz
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from ..species_matcher import build_embedder

_NAME_RE = re.compile(r"^(\d+)\.(png|jpg|jpeg|bmp|gif)$", re.IGNORECASE)


def build(icons_dir: Path, out_path: Path) -> int:
    import cv2
    import numpy as np

    embed_fn, device = build_embedder()
    print(f"Extractor en {device}")

    dex_ids: list[int] = []
    vectors: list = []
    for f in sorted(icons_dir.iterdir()):
        m = _NAME_RE.match(f.name)
        if not m:
            continue
        img = cv2.imread(str(f), cv2.IMREAD_COLOR)
        if img is None:
            print(f"  aviso: no se pudo leer {f.name}, se omite")
            continue
        dex_ids.append(int(m.group(1)))
        vectors.append(embed_fn(img))

    if not dex_ids:
        raise SystemExit(f"No se encontraron iconos válidos (NNN.png) en {icons_dir}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        dex_ids=np.asarray(dex_ids, dtype=np.int32),
        vectors=np.asarray(vectors, dtype=np.float32),
    )
    print(f"Guardados {len(dex_ids)} embeddings en {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--icons", required=True, type=Path, help="Carpeta con NNN.png")
    p.add_argument("--out", required=True, type=Path, help="Ruta de salida del .npz")
    args = p.parse_args(argv)
    return build(args.icons, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
