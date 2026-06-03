"""Genera el `templates.npz` de una galería a partir de iconos PNG con transparencia.

Toma una carpeta de iconos nombrados por nº de Pokédex (`25.png`, …), los lee en RGBA
(respetando la transparencia) y guarda un `templates.npz` con `dex_ids`, `images`
(N,S,S,4 uint8) y `size`. Es lo que usa el matcher enmascarado.

Uso:
    python -m pvo.tools.build_templates --icons assets/icons/gen3 --out assets/icons/gen3/templates.npz
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SIZE = 32
_NAME_RE = re.compile(r"^(\d+)\.(png|gif|bmp)$", re.IGNORECASE)


def build(icons_dir: Path, out_path: Path, size: int = SIZE) -> int:
    import numpy as np
    from PIL import Image  # solo en build-time

    dex_ids, images = [], []
    for f in sorted(icons_dir.iterdir()):
        m = _NAME_RE.match(f.name)
        if not m:
            continue
        im = Image.open(f).convert("RGBA").resize((size, size), Image.NEAREST)
        arr = np.array(im, dtype=np.uint8)
        if (arr[:, :, 3] > 16).sum() < 20:
            continue
        dex_ids.append(int(m.group(1)))
        images.append(arr)

    if not dex_ids:
        raise SystemExit(f"No se encontraron iconos válidos (NNN.png) en {icons_dir}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        dex_ids=np.asarray(dex_ids, dtype=np.int32),
        images=np.stack(images).astype(np.uint8),
        size=np.int32(size),
    )
    print(f"Guardadas {len(dex_ids)} plantillas en {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--icons", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--size", type=int, default=SIZE)
    args = p.parse_args(argv)
    return build(args.icons, args.out, args.size)


if __name__ == "__main__":
    raise SystemExit(main())
