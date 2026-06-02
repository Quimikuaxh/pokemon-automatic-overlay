"""Detección automática del área de juego (viewport) dentro de la ventana capturada.

El emulador suele rodear la pantalla del juego con cromo (barras de menú, bordes) y
franjas negras (letterbox) para respetar la relación de aspecto. Aquí se recorta ese
margen para quedarnos solo con la pantalla del juego, de modo que las coordenadas del
perfil (en resolución de referencia) sean estables sin importar el tamaño de ventana.
"""

from __future__ import annotations

from .geometry import Region, center_box, fit_aspect


def content_bbox(gray, tol: int = 8) -> Region:
    """Recorta los márgenes de color uniforme (bordes/letterbox sólidos).

    Una fila/columna se considera 'borde' si su rango (max-min) <= tol (casi
    constante). Devuelve (x, y, w, h) del contenido no uniforme."""
    import numpy as np

    h, w = gray.shape[:2]
    g = gray.astype(np.int16)
    col_range = g.max(axis=0) - g.min(axis=0)   # (w,)
    row_range = g.max(axis=1) - g.min(axis=1)   # (h,)
    cols = np.where(col_range > tol)[0]
    rows = np.where(row_range > tol)[0]
    if cols.size == 0 or rows.size == 0:
        return (0, 0, w, h)
    x0, x1 = int(cols[0]), int(cols[-1])
    y0, y1 = int(rows[0]), int(rows[-1])
    return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def detect_viewport(frame_bgr, aspect: float | None = None, tol: int = 8) -> Region:
    """Detecta el viewport del juego en un frame BGR.

    1) recorta márgenes uniformes; 2) si se da `aspect` (=ancho/alto del sistema, p.
    ej. 1.5 para GBA), encaja y centra la mayor caja con esa relación para eliminar
    letterbox residual."""
    import cv2

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    x, y, w, h = content_bbox(gray, tol)
    if aspect:
        nw, nh = fit_aspect(w, h, aspect)
        if nw > 0 and nh > 0:
            return center_box((x, y, w, h), (nw, nh))
    return (x, y, w, h)
