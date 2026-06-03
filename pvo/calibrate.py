"""Asistente de calibración: genera un perfil de juego a base de clics.

En vez de medir píxeles a mano: abres el menú de equipo en el emulador, lanzas el
asistente, y vas dibujando un rectángulo sobre cada icono y cada mote. El asistente
detecta el viewport automáticamente, normaliza a la resolución de referencia, recoge
las regiones (en esa resolución, por tanto independientes del tamaño de ventana) y
escribe el YAML del perfil + el template del detector de menú.

Controles (ventana de OpenCV):
  - arrastra con el ratón para dibujar el rectángulo
  - ENTER  acepta la región actual y pasa a la siguiente
  - 'n'    marca la región como inexistente (p. ej. un juego sin mote)
  - 'r'    repite (borra el rectángulo en curso)
  - ESC    aborta la calibración
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .capture import Capturer
from .geometry import Region, clamp_region, unscale_region
from .profiles.schema import CaptureProfile


def _draw_text(img, text, org, color, scale=0.6):
    """Texto con grueso contorno negro para que sea legible sobre cualquier fondo."""
    import cv2
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


class _RectPicker:
    def __init__(self, canvas, window_name: str):
        self._base = canvas
        self._win = window_name
        self._start: Optional[tuple[int, int]] = None
        self._cur: Optional[Region] = None  # en coords de display

    def _on_mouse(self, event, x, y, flags, param):
        import cv2
        if event == cv2.EVENT_LBUTTONDOWN:
            self._start = (x, y)
            self._cur = None
        elif event == cv2.EVENT_MOUSEMOVE and self._start is not None:
            self._cur = self._rect_from(self._start, (x, y))
        elif event == cv2.EVENT_LBUTTONUP and self._start is not None:
            self._cur = self._rect_from(self._start, (x, y))
            self._start = None

    @staticmethod
    def _rect_from(a, b) -> Region:
        x0, y0 = a
        x1, y1 = b
        return (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))

    def pick(self, label: str, scale: float, allow_none: bool) -> Optional[Region]:
        """Devuelve la región elegida en coords de la resolución de referencia, o
        None si se marca como inexistente. Lanza KeyboardInterrupt si se aborta."""
        import cv2

        cv2.setMouseCallback(self._win, self._on_mouse)
        hint = "ENTER=ok  'r'=repetir  ESC=abortar" + ("  'n'=ninguno" if allow_none else "")
        while True:
            img = self._base.copy()
            _draw_text(img, label, (8, 24), (0, 255, 255), 0.6)   # amarillo
            _draw_text(img, hint, (8, 46), (255, 255, 255), 0.5)  # blanco
            if self._cur:
                x, y, w, h = self._cur
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 1)
            cv2.imshow(self._win, img)
            key = cv2.waitKey(20) & 0xFF
            if key == 27:  # ESC
                raise KeyboardInterrupt("calibración abortada")
            if key in (ord("r"), ord("R")):
                self._cur = None
            if allow_none and key in (ord("n"), ord("N")):
                return None
            if key in (13, 10):  # ENTER
                if self._cur and self._cur[2] > 1 and self._cur[3] > 1:
                    return unscale_region(self._cur, scale)


def _wait_for_capture(cap, win: str, ref_w: int, ref_h: int, scale: float):
    """Muestra la captura en vivo. Devuelve el frame congelado al pulsar ESPACIO,
    o None si se pulsa ESC."""
    import cv2

    while True:
        frame = cap.grab()
        disp = cv2.resize(frame, (ref_w * scale, ref_h * scale), interpolation=cv2.INTER_NEAREST)
        _draw_text(disp, "Abre el MENU de equipo", (8, 24), (0, 255, 255), 0.6)
        _draw_text(disp, "ESPACIO=capturar   ESC=abortar", (8, 46), (255, 255, 255), 0.5)
        cv2.imshow(win, disp)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:       # ESC
            return None
        if key == 32:       # ESPACIO
            return frame


def run_calibration(
    name: str,
    capture: CaptureProfile,
    reference_resolution: tuple[int, int],
    lang: str,
    profiles_dir: Path,
    assets_dir: Path,
    species_gen: int | None = None,
) -> int:
    import cv2
    import yaml

    cap = Capturer(capture, reference_resolution)
    ref_w, ref_h = reference_resolution
    scale = max(1, 720 // ref_h)

    win = "Calibración — pokemon-vision-overlay"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    # Vista en vivo hasta que el usuario congela el frame con ESPACIO.
    frame = _wait_for_capture(cap, win, ref_w, ref_h, scale)
    if frame is None:
        cv2.destroyAllWindows()
        print("Calibración abortada; no se ha escrito nada.")
        return 1
    canvas = cv2.resize(frame, (ref_w * scale, ref_h * scale), interpolation=cv2.INTER_NEAREST)
    picker = _RectPicker(canvas, win)

    try:
        icons: list[Region] = []
        texts: list[Optional[Region]] = []
        for i in range(6):
            r = picker.pick(f"ICONO del slot {i + 1}/6", scale, allow_none=False)
            icons.append(clamp_region(r, ref_w, ref_h))
        for i in range(6):
            r = picker.pick(f"MOTE del slot {i + 1}/6 (o 'n' si no hay)", scale, allow_none=True)
            texts.append(clamp_region(r, ref_w, ref_h) if r else None)
        menu_rect = picker.pick("FIRMA del menú (zona fija característica)", scale, allow_none=False)
        menu_rect = clamp_region(menu_rect, ref_w, ref_h)
    except KeyboardInterrupt:
        cv2.destroyAllWindows()
        print("Calibración abortada; no se ha escrito nada.")
        return 1
    cv2.destroyAllWindows()

    # Guardar template del detector de menú a partir de la firma elegida.
    tpl_dir = assets_dir / "templates" / name
    tpl_dir.mkdir(parents=True, exist_ok=True)
    mx, my, mw, mh = menu_rect
    tpl_path = tpl_dir / "party_menu.png"
    cv2.imwrite(str(tpl_path), frame[my:my + mh, mx:mx + mw])

    # Rutas relativas al directorio del perfil (pvo/profiles).
    def rel(p: Path) -> str:
        import os
        return os.path.relpath(p, profiles_dir).replace("\\", "/")

    # Si se indica generación, se reutiliza la galería compartida gen<N> (con sus
    # embeddings ya incluidos); si no, una carpeta propia por nombre de perfil.
    icons_key = f"gen{species_gen}" if species_gen else name
    emb_path = assets_dir / "icons" / icons_key / "embeddings.npz"

    data = {
        "profile": name,
        "reference_resolution": [ref_w, ref_h],
        "capture": _capture_to_dict(capture),
        "menu_detector": {
            "template": rel(tpl_path),
            "region": [0, 0, ref_w, ref_h],
            "min_confidence": 0.85,
            "stable_frames": 3,
        },
        "slots": [
            {"icon_region": list(icons[i]), **({"text_region": list(texts[i])} if texts[i] else {})}
            for i in range(6)
        ],
        "species": {"embeddings": rel(emb_path), "min_similarity": 0.85},
        "ocr": {"engine": "easyocr", "lang": lang},
    }

    profiles_dir.mkdir(parents=True, exist_ok=True)
    out = profiles_dir / f"{name}.yaml"
    with out.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)

    print(f"Perfil escrito: {out}")
    print(f"Template del menú: {tpl_path}")
    print(f"Falta generar los embeddings de especie en: {emb_path}")
    print("  (reúne iconos NNN.png de tu render y usa: python -m pvo.tools.build_embeddings)")
    return 0


def _capture_to_dict(capture: CaptureProfile) -> dict:
    d: dict = {"fps": capture.fps}
    if capture.window_title_match:
        d["window_title_match"] = capture.window_title_match
    if capture.region:
        d["region"] = list(capture.region)
    if capture.viewport != "auto":
        d["viewport"] = list(capture.viewport)  # type: ignore[arg-type]
    else:
        d["viewport"] = "auto"
    if capture.aspect_ratio is not None:
        d["aspect_ratio"] = capture.aspect_ratio
    return d
