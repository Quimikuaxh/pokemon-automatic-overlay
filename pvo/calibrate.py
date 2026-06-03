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


_AUTO = object()  # centinela: "detectar el área de juego automáticamente"


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

    def pick(self, label: str, scale: float, allow_none: bool, allow_auto: bool = False):
        """Devuelve la región elegida (en coords reales, deshecho el `scale`), `None`
        si se marca como inexistente, o `_AUTO` si se elige automático. Lanza
        KeyboardInterrupt si se aborta."""
        import cv2

        cv2.setMouseCallback(self._win, self._on_mouse)
        extra = ("  'n'=ninguno" if allow_none else "") + ("  'a'=auto" if allow_auto else "")
        hint = "ENTER=ok  'r'=repetir  ESC=abortar" + extra
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
            if allow_auto and key in (ord("a"), ord("A")):
                return _AUTO
            if key in (13, 10):  # ENTER
                if self._cur and self._cur[2] > 1 and self._cur[3] > 1:
                    return unscale_region(self._cur, scale)


def _fit_scale(w: int, h: int, max_w: int = 1000, max_h: int = 700) -> float:
    """Escala para que (w,h) quepa en (max_w,max_h) sin pasarse de 1x."""
    return min(1.0, max_w / w, max_h / h)


def _wait_for_raw(cap, win: str):  # noqa: D401
    """Muestra la VENTANA completa del emulador en vivo (ambas pantallas si las hay).
    Devuelve el frame crudo congelado al pulsar ESPACIO, o None si ESC."""
    import cv2

    while True:
        raw = cap._grab_window()  # ventana entera, sin recortar viewport
        s = _fit_scale(raw.shape[1], raw.shape[0])
        disp = cv2.resize(raw, (int(raw.shape[1] * s), int(raw.shape[0] * s)), interpolation=cv2.INTER_AREA)
        _draw_text(disp, "Abre el MENU de equipo", (8, 24), (0, 255, 255), 0.6)
        _draw_text(disp, "ESPACIO=capturar   ESC=abortar", (8, 46), (255, 255, 255), 0.5)
        cv2.imshow(win, disp)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            return None
        if key == 32:
            return raw


def _pick_viewport(raw, win: str):
    """Deja dibujar la PANTALLA del juego que contiene el menú (en doble pantalla,
    p. ej. NDS/3DS). Devuelve fracciones (fx,fy,fw,fh) de la ventana, o None si se
    elige 'a' (auto-detección)."""
    import cv2

    H, W = raw.shape[:2]
    s = _fit_scale(W, H)
    canvas = cv2.resize(raw, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    picker = _RectPicker(canvas, win)
    r = picker.pick("Dibuja la PANTALLA del menú de equipo", s, allow_none=False, allow_auto=True)
    if r is _AUTO:
        return None
    x, y, w, h = r  # en píxeles de la ventana (deshecho el escalado de display)
    return (x / W, y / H, w / W, h / H)


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

    # 1) Captura la VENTANA completa (ambas pantallas si las hay) y, si es doble
    #    pantalla, deja elegir cuál contiene el menú; si no, 'a' = auto.
    raw = _wait_for_raw(cap, win)
    if raw is None:
        cv2.destroyAllWindows()
        print("Calibración abortada; no se ha escrito nada.")
        return 1
    try:
        vp_frac = _pick_viewport(raw, win)
    except KeyboardInterrupt:
        cv2.destroyAllWindows()
        print("Calibración abortada; no se ha escrito nada.")
        return 1

    # 2) Construye el frame de trabajo: recorta el viewport y normaliza a ref-res.
    H, W = raw.shape[:2]
    if vp_frac:
        fx, fy, fw, fh = vp_frac
        vx, vy, vw, vh = int(fx * W), int(fy * H), int(fw * W), int(fh * H)
    else:
        from .viewport import detect_viewport
        vx, vy, vw, vh = detect_viewport(raw, capture.aspect_ratio)
    crop = raw[vy:vy + vh, vx:vx + vw]
    frame = cv2.resize(crop, (ref_w, ref_h), interpolation=cv2.INTER_AREA)
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
    # plantillas ya incluidas); si no, una carpeta propia por nombre de perfil.
    icons_key = f"gen{species_gen}" if species_gen else name
    gallery_path = assets_dir / "icons" / icons_key / "templates.npz"

    cap_dict = _capture_to_dict(capture)
    cap_dict["viewport"] = [round(v, 4) for v in vp_frac] if vp_frac else "auto"

    data = {
        "profile": name,
        "reference_resolution": [ref_w, ref_h],
        "capture": cap_dict,
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
        "species": {"gallery": rel(gallery_path), "min_similarity": 0.6},
        "ocr": {"engine": "easyocr", "lang": lang},
    }

    profiles_dir.mkdir(parents=True, exist_ok=True)
    out = profiles_dir / f"{name}.yaml"
    with out.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)

    print(f"Perfil escrito: {out}")
    print(f"Template del menú: {tpl_path}")
    if not gallery_path.exists():
        print(f"Aviso: no encuentro la galería {gallery_path}. Indica la generación "
              f"(--gen N) para usar una incluida.")
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
