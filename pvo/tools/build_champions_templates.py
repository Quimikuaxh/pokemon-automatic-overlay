"""Genera el `templates.npz` de la galería Champions desde los menu sprites descargados.

Lee `Menu_CP_<dex4>[-variante].png` (RGBA), extrae el nº de Pokédex (4 dígitos) y guarda
el mismo formato que la galería del modo emulador (`dex_ids`, `images` N,S,S,4, `size`),
de modo que el `SpeciesMatcher` lo usa sin cambios. Las formas alternativas se mapean a
su dex base (varias plantillas pueden compartir dex; el matcher devuelve la mejor).

Uso:
    python -m pvo.tools.build_champions_templates
    python -m pvo.tools.build_champions_templates --src assets/icons/champions/src \
        --out assets/icons/champions/templates.npz
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SIZE = 32
_NAME_RE = re.compile(r"^Menu_CP_(\d{4})(?:-.*)?\.(png|gif|bmp)$", re.IGNORECASE)


def build(src_dir: Path, out_path: Path, size: int = SIZE) -> int:
    import numpy as np
    from PIL import Image

    dex_ids, images = [], []
    for f in sorted(src_dir.iterdir()):
        m = _NAME_RE.match(f.name)
        if not m:
            continue
        im = Image.open(f).convert("RGBA").resize((size, size), Image.NEAREST)
        arr = np.array(im, dtype=np.uint8)
        if (arr[:, :, 3] > 16).sum() < 20:  # casi vacío → descartar
            continue
        dex_ids.append(int(m.group(1)))
        images.append(arr)

    if not dex_ids:
        raise SystemExit(
            f"No se encontraron sprites válidos (Menu_CP_NNNN.png) en {src_dir}.\n"
            f"Descárgalos antes con: python -m pvo.tools.download_champions_sprites"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        dex_ids=np.asarray(dex_ids, dtype=np.int32),
        images=np.stack(images).astype(np.uint8),
        size=np.int32(size),
    )
    uniq = len(set(dex_ids))
    print(f"Guardadas {len(dex_ids)} plantillas ({uniq} especies) en {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, default=Path("assets/icons/champions/src"))
    p.add_argument("--out", type=Path, default=Path("assets/icons/champions/templates.npz"))
    p.add_argument("--size", type=int, default=SIZE)
    args = p.parse_args(argv)
    return build(args.src, args.out, args.size)


if __name__ == "__main__":
    raise SystemExit(main())
