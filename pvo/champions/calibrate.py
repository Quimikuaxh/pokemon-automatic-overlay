"""Asistente de calibración del modo Champions.

Dos capturas: la pantalla de SELECCIÓN (para la firma de pantalla + los 6 iconos
rivales) y la de COMBATE (firma + 2 iconos propios + 2 rivales). Reutiliza el
`_RectPicker` y el flujo de viewport de `pvo.calibrate`. Escribe `champions.yaml` y los
dos templates de pantalla.

Controles: arrastra para dibujar; ENTER acepta; 'r' repite; ESC aborta.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..calibrate import _AUTO, _RectPicker, _draw_text, _fit_scale
from ..capture import Capturer
from ..geometry import Region, clamp_region
from ..profiles.schema import CaptureProfile


def _wait_for_frame(cap: Capturer, prompt: str, win: str):
    """Muestra la ventana en vivo; devuelve el frame crudo al pulsar ESPACIO, o None."""
    import cv2

    while True:
        raw = cap._grab_window()
        s = _fit_scale(raw.shape[1], raw.shape[0])
        disp = cv2.resize(raw, (int(raw.shape[1] * s), int(raw.shape[0] * s)), interpolation=cv2.INTER_AREA)
        _draw_text(disp, prompt, (8, 24), (0, 255, 255), 0.6)
        _draw_text(disp, "ESPACIO=capturar   ESC=abortar", (8, 46), (255, 255, 255), 0.5)
        cv2.imshow(win, disp)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            return None
        if key == 32:
            return raw


def _pick_viewport(raw, win: str) -> Optional[tuple[float, float, float, float]]:
    import cv2

    H, W = raw.shape[:2]
    s = _fit_scale(W, H)
    canvas = cv2.resize(raw, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    picker = _RectPicker(canvas, win)
    r = picker.pick("Dibuja el AREA DE JUEGO (16:9). 'a'=auto", s, allow_none=False, allow_auto=True)
    if r is _AUTO:
        return None
    x, y, w, h = r
    return (x / W, y / H, w / W, h / H)


def _normalize(raw, vp_frac, ref_w, ref_h, aspect):
    import cv2

    H, W = raw.shape[:2]
    if vp_frac:
        fx, fy, fw, fh = vp_frac
        vx, vy, vw, vh = int(fx * W), int(fy * H), int(fw * W), int(fh * H)
    else:
        from ..viewport import detect_viewport
        vx, vy, vw, vh = detect_viewport(raw, aspect)
    crop = raw[vy:vy + vh, vx:vx + vw]
    return cv2.resize(crop, (ref_w, ref_h), interpolation=cv2.INTER_AREA)


def _pick_on_frame(frame, ref_w, ref_h, win, labels):
    """Devuelve la lista de regiones (en coords de ref) para cada label."""
    import cv2

    s = _fit_scale(ref_w, ref_h)
    canvas = cv2.resize(frame, (int(ref_w * s), int(ref_h * s)), interpolation=cv2.INTER_AREA)
    picker = _RectPicker(canvas, win)
    out: list[Region] = []
    for label in labels:
        r = picker.pick(label, s, allow_none=False)
        out.append(clamp_region(r, ref_w, ref_h))
    return out


def run_champions_calibration(
    name: str,
    capture: CaptureProfile,
    reference_resolution: tuple[int, int],
    profiles_dir: Path,
    assets_dir: Path,
    mode: str = "Doubles",
) -> int:
    import cv2
    import yaml

    cap = Capturer(capture, reference_resolution)
    ref_w, ref_h = reference_resolution
    aspect = capture.aspect_ratio
    win = "Calibración Champions — pokemon-vision-overlay"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    try:
        # 1) Pantalla de SELECCIÓN
        raw = _wait_for_frame(cap, "Pon la pantalla de SELECCION de equipo", win)
        if raw is None:
            raise KeyboardInterrupt
        vp_frac = _pick_viewport(raw, win)
        sel_frame = _normalize(raw, vp_frac, ref_w, ref_h, aspect)
        sel_sig = _pick_on_frame(sel_frame, ref_w, ref_h, win,
                                 ["FIRMA selección: algo FIJO y UNICO de esta pantalla "
                                  "(texto 'Selecciona 4 Pokemon' o barra 'Todo listo', NO el fondo)"])[0]
        rival_slots = _pick_on_frame(sel_frame, ref_w, ref_h, win,
                                     [f"ICONO rival {i + 1}/6" for i in range(6)])

        # 2) Pantalla de COMBATE (mismo viewport)
        raw2 = _wait_for_frame(cap, "Pon la pantalla de COMBATE (dobles)", win)
        if raw2 is None:
            raise KeyboardInterrupt
        bat_frame = _normalize(raw2, vp_frac, ref_w, ref_h, aspect)
        bat_sig = _pick_on_frame(bat_frame, ref_w, ref_h, win,
                                 ["FIRMA combate: algo FIJO y UNICO de esta pantalla "
                                  "(botones 'Luchar'/'Pokemon' abajo-dcha, NO el fondo ni las barras de HP)"])[0]
        ally_slots = _pick_on_frame(bat_frame, ref_w, ref_h, win,
                                    [f"ICONO activo PROPIO {i + 1}/2" for i in range(2)])
        brival_slots = _pick_on_frame(bat_frame, ref_w, ref_h, win,
                                      [f"ICONO activo RIVAL {i + 1}/2" for i in range(2)])
    except KeyboardInterrupt:
        cv2.destroyAllWindows()
        print("Calibración abortada; no se ha escrito nada.")
        return 1

    # Templates de pantalla (recortes de la firma elegida).
    tpl_dir = assets_dir / "templates" / "champions"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    sx, sy, sw, sh = sel_sig
    bx, by, bw, bh = bat_sig
    sel_tpl = tpl_dir / "selection.png"
    bat_tpl = tpl_dir / "battle.png"
    cv2.imwrite(str(sel_tpl), sel_frame[sy:sy + sh, sx:sx + sw])
    cv2.imwrite(str(bat_tpl), bat_frame[by:by + bh, bx:bx + bw])
    cv2.destroyAllWindows()

    def rel(p: Path) -> str:
        return os.path.relpath(p, profiles_dir).replace("\\", "/")

    gallery_path = assets_dir / "icons" / "champions" / "templates.npz"

    cap_dict: dict = {"fps": capture.fps}
    if capture.window_title_match:
        cap_dict["window_title_match"] = capture.window_title_match
    cap_dict["viewport"] = [round(v, 4) for v in vp_frac] if vp_frac else "auto"
    if aspect is not None:
        cap_dict["aspect_ratio"] = aspect

    data = {
        "profile": name,
        "reference_resolution": [ref_w, ref_h],
        "mode": mode,
        "capture": cap_dict,
        "species": {"gallery": rel(gallery_path), "min_similarity": 0.45},
        "screens": {
            "selection": {"template": rel(sel_tpl), "region": [0, 0, ref_w, ref_h],
                          "min_confidence": 0.7, "stable_frames": 2},
            "battle": {"template": rel(bat_tpl), "region": [0, 0, ref_w, ref_h],
                       "min_confidence": 0.7, "stable_frames": 2},
        },
        "selection": {"rival_slots": [list(r) for r in rival_slots]},
        "battle": {
            "ally_slots": [list(r) for r in ally_slots],
            "rival_slots": [list(r) for r in brival_slots],
        },
    }

    profiles_dir.mkdir(parents=True, exist_ok=True)
    out = profiles_dir / f"{name}.yaml"
    with out.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)

    print(f"Perfil escrito: {out}")
    print(f"Templates de pantalla: {sel_tpl}, {bat_tpl}")
    if not gallery_path.exists():
        print(f"Aviso: falta la galería {gallery_path}. Genérala con:\n"
              f"  python -m pvo.tools.download_champions_sprites\n"
              f"  python -m pvo.tools.build_champions_templates")
    return 0
