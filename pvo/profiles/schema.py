"""Perfil de juego: define todo lo específico de un juego/render concreto.

El pipeline es agnóstico; cambiar de GBA→NDS→3DS = nuevo perfil + nuevos assets,
sin tocar el código. `from_dict` valida y no requiere PyYAML (testeable con stdlib);
`load_profile` lee el YAML.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

Region = tuple[int, int, int, int]  # (x, y, w, h)


def _as_region(value, where: str) -> Region:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{where}: se esperaba [x, y, w, h], got {value!r}")
    x, y, w, h = value
    for n in (x, y, w, h):
        if not isinstance(n, int):
            raise ValueError(f"{where}: las coordenadas deben ser enteros, got {value!r}")
    if w <= 0 or h <= 0:
        raise ValueError(f"{where}: ancho/alto deben ser > 0, got {value!r}")
    return (x, y, w, h)


@dataclass(frozen=True)
class SlotProfile:
    icon_region: Region
    text_region: Optional[Region]  # None si ese juego no muestra mote en el menú


@dataclass(frozen=True)
class MenuDetector:
    template: str
    region: Region
    min_confidence: float
    stable_frames: int


@dataclass(frozen=True)
class CaptureProfile:
    window_title_match: Optional[str]
    region: Optional[Region]
    fps: float
    viewport: object = "auto"          # "auto" (detección) o Region explícita
    aspect_ratio: Optional[float] = None  # ancho/alto del sistema (p. ej. 1.5 GBA)


@dataclass(frozen=True)
class SpeciesProfile:
    gallery: str         # ruta a templates.npz (sprites RGBA de referencia)
    min_similarity: float  # umbral de score ZNCC [-1,1]


@dataclass(frozen=True)
class OcrProfile:
    engine: str          # "easyocr" | "paddleocr"
    lang: str


@dataclass(frozen=True)
class GameProfile:
    name: str
    reference_resolution: tuple[int, int]
    capture: CaptureProfile
    menu_detector: MenuDetector
    slots: list[SlotProfile]
    species: SpeciesProfile
    ocr: OcrProfile
    base_dir: Path = Path(".")

    def resolve(self, relative: str) -> Path:
        """Resuelve una ruta de asset relativa al directorio del perfil."""
        p = Path(relative)
        return p if p.is_absolute() else (self.base_dir / p)

    @classmethod
    def from_dict(cls, d: dict, base_dir: Path = Path(".")) -> "GameProfile":
        if not isinstance(d, dict):
            raise ValueError("el perfil debe ser un mapping")
        name = d.get("profile")
        if not isinstance(name, str) or not name:
            raise ValueError("falta 'profile' (nombre)")

        rr = d.get("reference_resolution")
        if not isinstance(rr, (list, tuple)) or len(rr) != 2 or not all(isinstance(n, int) and n > 0 for n in rr):
            raise ValueError("'reference_resolution' debe ser [w, h] enteros > 0")

        cap = d.get("capture") or {}
        vp_raw = cap.get("viewport", "auto")
        if vp_raw == "auto":
            viewport: object = "auto"
        elif isinstance(vp_raw, (list, tuple)) and len(vp_raw) == 4:
            # 4 números: fracciones de la ventana (0..1) o píxeles absolutos.
            viewport = tuple(float(v) for v in vp_raw)
        else:
            raise ValueError("capture.viewport debe ser 'auto' o [x, y, w, h]")
        aspect = cap.get("aspect_ratio")
        capture = CaptureProfile(
            window_title_match=cap.get("window_title_match"),
            region=_as_region(cap["region"], "capture.region") if cap.get("region") else None,
            fps=float(cap.get("fps", 3)),
            viewport=viewport,
            aspect_ratio=float(aspect) if aspect is not None else None,
        )
        if capture.window_title_match is None and capture.region is None:
            raise ValueError("capture: define 'window_title_match' o 'region'")

        md = d.get("menu_detector") or {}
        for k in ("template", "region"):
            if k not in md:
                raise ValueError(f"menu_detector: falta '{k}'")
        menu = MenuDetector(
            template=str(md["template"]),
            region=_as_region(md["region"], "menu_detector.region"),
            min_confidence=float(md.get("min_confidence", 0.85)),
            stable_frames=int(md.get("stable_frames", 3)),
        )

        raw_slots = d.get("slots")
        if not isinstance(raw_slots, list) or len(raw_slots) != 6:
            raise ValueError("'slots' debe ser una lista de exactamente 6 entradas")
        slots: list[SlotProfile] = []
        for i, s in enumerate(raw_slots):
            if "icon_region" not in s:
                raise ValueError(f"slots[{i}]: falta 'icon_region'")
            text = s.get("text_region")
            slots.append(SlotProfile(
                icon_region=_as_region(s["icon_region"], f"slots[{i}].icon_region"),
                text_region=_as_region(text, f"slots[{i}].text_region") if text else None,
            ))

        sp = d.get("species") or {}
        gallery = sp.get("gallery", sp.get("embeddings"))  # 'embeddings' = alias antiguo
        if not gallery:
            raise ValueError("species: falta 'gallery'")
        species = SpeciesProfile(
            gallery=str(gallery),
            min_similarity=float(sp.get("min_similarity", 0.5)),
        )

        oc = d.get("ocr") or {}
        ocr = OcrProfile(
            engine=str(oc.get("engine", "easyocr")),
            lang=str(oc.get("lang", "es")),
        )

        return cls(
            name=name,
            reference_resolution=(int(rr[0]), int(rr[1])),
            capture=capture,
            menu_detector=menu,
            slots=slots,
            species=species,
            ocr=ocr,
            base_dir=base_dir,
        )


def load_profile(path: str | Path) -> GameProfile:
    """Carga un perfil desde un YAML (requiere PyYAML)."""
    import yaml  # import perezoso

    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return GameProfile.from_dict(data, base_dir=p.parent)
