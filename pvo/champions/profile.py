"""Perfil del modo Champions: pantallas (selección/combate) y sus slots de iconos.

Estructura distinta a la del perfil emulador (`profiles.schema.GameProfile`), por eso
vive aparte. Hace *duck-typing* de lo que `SpeciesMatcher` necesita (`.resolve()` y
`.species`), de modo que el matcher de especie se reutiliza sin cambios.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..profiles.schema import CaptureProfile, Region, SpeciesProfile, _as_region


@dataclass(frozen=True)
class ScreenSignature:
    """Firma de una pantalla: template en una región fija + histéresis."""
    template: str
    region: Region
    min_confidence: float
    stable_frames: int


@dataclass(frozen=True)
class ChampionsProfile:
    name: str
    reference_resolution: tuple[int, int]
    capture: CaptureProfile
    species: SpeciesProfile
    mode: str                              # 'Doubles' | 'Singles'
    screens: dict[str, ScreenSignature]    # 'selection', 'battle'
    selection_rival_slots: list[Region]    # iconos del panel rival (hasta 6)
    battle_ally_slots: list[Region]        # iconos activos propios (1-2)
    battle_rival_slots: list[Region]       # iconos activos rivales (1-2)
    base_dir: Path = Path(".")

    def resolve(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else (self.base_dir / p)

    @classmethod
    def from_dict(cls, d: dict, base_dir: Path = Path(".")) -> "ChampionsProfile":
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
            viewport = tuple(float(v) for v in vp_raw)
        else:
            raise ValueError("capture.viewport debe ser 'auto' o [x, y, w, h]")
        aspect = cap.get("aspect_ratio")
        capture = CaptureProfile(
            window_title_match=cap.get("window_title_match"),
            region=_as_region(cap["region"], "capture.region") if cap.get("region") else None,
            fps=float(cap.get("fps", 2)),
            viewport=viewport,
            aspect_ratio=float(aspect) if aspect is not None else None,
            method=str(cap.get("method", "region")),
        )
        if capture.window_title_match is None and capture.region is None:
            raise ValueError("capture: define 'window_title_match' o 'region'")

        sp = d.get("species") or {}
        gallery = sp.get("gallery")
        if not gallery:
            raise ValueError("species: falta 'gallery'")
        species = SpeciesProfile(
            gallery=str(gallery),
            min_similarity=float(sp.get("min_similarity", 0.45)),
        )

        # 'screens' es OPCIONAL: la clasificación de pantalla es por contenido (cuántos
        # iconos se reconocen), no por plantillas. Se conserva el parseo por
        # compatibilidad con perfiles antiguos, pero no es obligatorio.
        screens: dict[str, ScreenSignature] = {}
        for key, s in (d.get("screens") or {}).items():
            if key not in ("selection", "battle") or not s:
                continue
            if "template" not in s or "region" not in s:
                continue
            screens[key] = ScreenSignature(
                template=str(s["template"]),
                region=_as_region(s["region"], f"screens.{key}.region"),
                min_confidence=float(s.get("min_confidence", 0.7)),
                stable_frames=int(s.get("stable_frames", 2)),
            )

        sel = d.get("selection") or {}
        rival_slots = [_as_region(r, f"selection.rival_slots[{i}]")
                       for i, r in enumerate(sel.get("rival_slots") or [])]
        if not rival_slots:
            raise ValueError("selection.rival_slots: define al menos 1 icono rival")

        bat = d.get("battle") or {}
        ally_slots = [_as_region(r, f"battle.ally_slots[{i}]")
                      for i, r in enumerate(bat.get("ally_slots") or [])]
        brival_slots = [_as_region(r, f"battle.rival_slots[{i}]")
                        for i, r in enumerate(bat.get("rival_slots") or [])]
        if not ally_slots or not brival_slots:
            raise ValueError("battle.ally_slots/rival_slots: define los iconos de los activos")

        return cls(
            name=name,
            reference_resolution=(int(rr[0]), int(rr[1])),
            capture=capture,
            species=species,
            mode=str(d.get("mode", "Doubles")),
            screens=screens,
            selection_rival_slots=rival_slots,
            battle_ally_slots=ally_slots,
            battle_rival_slots=brival_slots,
            base_dir=base_dir,
        )


def load_champions_profile(path: str | Path) -> ChampionsProfile:
    import yaml

    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return ChampionsProfile.from_dict(data, base_dir=p.parent)
