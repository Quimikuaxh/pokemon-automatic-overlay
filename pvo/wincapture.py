"""Captura del contenido de una ventana en Windows aunque esté tapada (PrintWindow).

A diferencia de `mss` (que copia la región de pantalla, y por tanto lo que haya delante),
`PrintWindow` con `PW_RENDERFULLCONTENT` pide a la propia ventana que se renderice en un
DC en memoria, así que funciona aunque el proyector de OBS no esté en primer plano.

Solo Windows; usa `ctypes` (sin dependencias extra). Si algo falla o no es Windows,
las funciones devuelven None y el llamador cae al método `mss`.
"""

from __future__ import annotations

import sys
from typing import Optional

PW_RENDERFULLCONTENT = 0x00000002
_BI_RGB = 0
_DIB_RGB_COLORS = 0


def available() -> bool:
    return sys.platform == "win32"


def _find_hwnd(title_match: str):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if title_match.lower() in buf.value.lower():
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(_cb, 0)
    return found[0] if found else None


def grab_window_by_title(title_match: str):
    """Devuelve un array BGR (h, w, 3) del contenido de la ventana, o None si falla."""
    if not available():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        import numpy as np

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        hwnd = _find_hwnd(title_match)
        if not hwnd:
            return None

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None

        hdc = user32.GetWindowDC(hwnd)
        memdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        old = gdi32.SelectObject(memdc, bmp)
        try:
            ok = user32.PrintWindow(hwnd, memdc, PW_RENDERFULLCONTENT)
            if not ok:
                return None

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h  # top-down
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = _BI_RGB

            buf = ctypes.create_string_buffer(w * h * 4)
            scanned = gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bmi), _DIB_RGB_COLORS)
            if scanned == 0:
                return None
            arr = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
            return arr[:, :, :3].copy()  # BGRA -> BGR
        finally:
            gdi32.SelectObject(memdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(memdc)
            user32.ReleaseDC(hwnd, hdc)
    except Exception:  # noqa: BLE001
        return None
