"""Geometría pura (sin numpy/cv2) para encaje de viewport y mapeo de coordenadas.

Se mantiene libre de dependencias para poder testearla con la stdlib.
"""

from __future__ import annotations

Region = tuple[int, int, int, int]  # (x, y, w, h)


def fit_aspect(w: int, h: int, aspect: float) -> tuple[int, int]:
    """Mayor sub-tamaño con relación de aspecto `aspect` (=ancho/alto) que cabe en
    (w, h). Devuelve (nw, nh) <= (w, h)."""
    if w <= 0 or h <= 0:
        return (0, 0)
    if w / h > aspect:
        nh = h
        nw = round(h * aspect)
    else:
        nw = w
        nh = round(w / aspect)
    return (int(nw), int(nh))


def center_box(outer: Region, inner: tuple[int, int]) -> Region:
    """Centra una caja de tamaño `inner` dentro de `outer`. Devuelve (x, y, w, h)."""
    ox, oy, ow, oh = outer
    iw, ih = inner
    x = ox + (ow - iw) // 2
    y = oy + (oh - ih) // 2
    return (x, y, iw, ih)


def scale_region(region: Region, scale: float) -> Region:
    """Escala una región por un factor (p. ej. para mostrarla ampliada)."""
    x, y, w, h = region
    return (round(x * scale), round(y * scale), round(w * scale), round(h * scale))


def unscale_region(region: Region, scale: float) -> Region:
    """Inversa de `scale_region`: de coordenadas de display a las reales."""
    if scale == 0:
        raise ValueError("scale no puede ser 0")
    x, y, w, h = region
    return (round(x / scale), round(y / scale), round(w / scale), round(h / scale))


def clamp_region(region: Region, width: int, height: int) -> Region:
    """Recorta la región para que quede dentro de (0,0,width,height)."""
    x, y, w, h = region
    x0 = max(0, min(x, width))
    y0 = max(0, min(y, height))
    x1 = max(0, min(x + w, width))
    y1 = max(0, min(y + h, height))
    return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))
