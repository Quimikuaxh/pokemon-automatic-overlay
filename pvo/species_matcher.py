"""Identificación de especie por embeddings de imagen (robusto a render HD).

En vez de correlación de píxeles (frágil con filtros/texturas HD), se calcula el
embedding del recorte del icono con un CNN preentrenado y se compara por similitud de
coseno contra los vectores de referencia (`embeddings.npz`, dexId -> vector). Tolera
escalado, anti-aliasing y variación visual moderada.

El set de referencia debe generarse a partir del MISMO render del usuario (ver
`pvo/tools/build_embeddings.py`).
"""

from __future__ import annotations

from typing import Optional

from .profiles.schema import GameProfile, SpeciesProfile


def build_embedder():
    """Crea el extractor de features (MobileNetV3 sin la capa de clasificación).

    Devuelve `(embed_fn, device)` donde `embed_fn(bgr_image) -> np.ndarray` (vector
    L2-normalizado). Imports perezosos para no exigir torch en módulos puros."""
    import numpy as np
    import cv2
    import torch
    from torchvision import models, transforms

    device = "cuda" if torch.cuda.is_available() else "cpu"
    weights = models.MobileNet_V3_Small_Weights.DEFAULT
    net = models.mobilenet_v3_small(weights=weights)
    net.classifier = torch.nn.Identity()  # nos quedamos con el embedding
    net.eval().to(device)

    preprocess = transforms.Compose([
        transforms.ToTensor(),
        transforms.Resize((96, 96), antialias=True),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    @torch.no_grad()
    def embed_fn(bgr):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        t = preprocess(rgb).unsqueeze(0).to(device)
        vec = net(t).squeeze(0).cpu().numpy().astype("float32")
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    return embed_fn, device


class SpeciesMatcher:
    def __init__(self, profile: GameProfile, embed_fn=None):
        import numpy as np

        self._cfg: SpeciesProfile = profile.species
        emb_path = profile.resolve(self._cfg.embeddings)
        if not emb_path.exists():
            raise FileNotFoundError(
                f"No existe el fichero de embeddings: {emb_path}\n"
                f"Genéralo con el botón 'Generar embeddings…' (o "
                f"python -m pvo.tools.build_embeddings) apuntando a la carpeta de iconos."
            )
        data = np.load(str(emb_path))
        # npz con 'dex_ids' (int) y 'vectors' (float32, ya L2-normalizados).
        self._dex_ids = data["dex_ids"].astype(int)
        self._matrix = data["vectors"].astype("float32")  # (N, D)
        self._embed = embed_fn or build_embedder()[0]

    def match(self, icon_bgr) -> tuple[Optional[int], float]:
        """Devuelve (dex_id, similitud) del mejor candidato. Si el recorte parece
        vacío, devuelve (None, 0.0)."""
        import numpy as np

        vec = self._embed(icon_bgr)  # (D,) L2-normalizado
        sims = self._matrix @ vec    # coseno (ambos normalizados)
        idx = int(np.argmax(sims))
        return int(self._dex_ids[idx]), float(sims[idx])
