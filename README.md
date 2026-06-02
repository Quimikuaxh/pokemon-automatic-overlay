# pokemon-vision-overlay

Lee **el equipo Pokémon** de un emulador (GBA/NDS/3DS) **por visión sobre la
interfaz** (sin leer memoria) y lo publica en el **overlay público** de `claude-test`
(la misma vista `/stream/:token` que se usa en OBS y se puede compartir por URL).

Patrón: lee el equipo **al abrir el menú de equipo**, lo **cachea** y lo mantiene
estático mientras viajas/combates; solo lo refresca en la siguiente apertura.

- **Especie** → identificada por el **icono** del menú (embeddings de imagen, robusto
  a filtros/texturas HD).
- **Mote** → leído por **OCR neural** (EasyOCR).

## Arquitectura

```
Emulador → captura 2-3 fps → detector de menú (gatillo ligero)
        → al abrir el menú: extrae 6 slots (icono→dexId, texto→mote)
        → cachea/valida → POST /api/stream-team/ingest/:ingestToken (claude-test)
        → la vista pública /stream/:shareToken pinta sprite (por dexId) + mote
```

Dos conjuntos de sprites distintos:
- **Matching** (identificar): iconos de TU render → `assets/icons/<perfil>/`.
- **Display** (pintar en la web): los resuelve `claude-test` por nº de Pokédex.

## Requisitos

- Python 3.10+
- Dependencias: `pip install -r requirements.txt`
  (EasyOCR arrastra `torch`/`torchvision`; la primera ejecución descarga modelos).
- Para captura por título de ventana (opcional): `pip install pygetwindow`.

## Configuración

1. Copia `config.example.yaml` a `config.yaml` y rellena:
   - `api_base`: URL del backend de claude-test.
   - `ingest_token`: cópialo desde la pestaña **Stream** de claude-test.
   - `profile`: nombre de un perfil en `pvo/profiles/`.
2. Crea/ajusta el **perfil de juego** (`pvo/profiles/<nombre>.yaml`): regiones de los
   6 slots, template del menú, idioma OCR. Usa `gba_emerald.yaml` como plantilla.
   **Las coordenadas son específicas de tu ventana/render** y hay que calibrarlas.

## Generar el set de referencia de especies

El matching compara contra iconos de **tu** render. Reúne iconos nombrados por nº de
Pokédex (`25.png`, `131.png`, …) en `assets/icons/<perfil>/` y genera los embeddings:

```bash
python -m pvo.tools.build_embeddings \
  --icons assets/icons/gba_emerald \
  --out   assets/icons/gba_emerald/embeddings.npz
```

> Con texturas HD que **reemplazan** los iconos, captura las referencias con ese mismo
> pack; si no, el matching no coincidirá.

## Ejecutar

```bash
python -m pvo.main -c config.yaml
```

Abre el menú de equipo en el emulador: en los logs verás la detección del menú, las 6
especies (con su similitud), los motes y si se publicó. Al cerrar el menú el equipo se
mantiene estático.

## Empaquetar (sin Python en destino)

```bash
pip install pyinstaller
pyinstaller --onefile --name poke-overlay \
  --collect-all easyocr --collect-all torch --collect-all torchvision \
  --add-data "pvo/profiles:pvo/profiles" \
  --add-data "assets:assets" \
  pvo/main.py
```

El binario queda en `dist/`. Pesa bastante por los modelos ML (trade-off de usar OCR
neural robusto a HD). Pruébalo en una máquina sin Python.

### Compilar el .exe de Windows sin tener Windows/Python

PyInstaller **no** hace cross-compile desde Linux. Para obtener el `.exe` sin montar
un entorno Windows propio, usa el workflow `.github/workflows/build-windows.yml`:
compila en un runner `windows-latest` y sube el binario como artefacto.

- Manual: pestaña **Actions → Build Windows executable → Run workflow**.
- Por release: crea un tag `vX.Y.Z` y el `.exe` se adjunta a la release.

Descarga el artefacto `poke-overlay-windows` (incluye `poke-overlay.exe` +
`config.example.yaml`). El usuario final no necesita Python.

> Los `assets/` (templates/embeddings) son específicos de tu render y **no** están en
> el repo, así que el `.exe` de CI se construye sin ellos: colócalos junto al binario
> y apunta tu perfil a esas rutas.

## Tests

```bash
python -m unittest discover -s tests -v
```

Cubren la lógica pura (estado/cache, validación de perfil, publicación). Los módulos
de visión (`capture`, `menu_detector`, `species_matcher`, `ocr`) requieren las
dependencias instaladas y un emulador real para probarse end-to-end.
```
