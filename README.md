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
  (EasyOCR arrastra `torch`/`torchvision`; la primera ejecución descarga modelos.
  Incluye `PyGetWindow` para localizar la ventana del emulador por título.)

## Uso (interfaz gráfica)

Al abrir el `.exe` (o `python -m pvo.main` sin argumentos) se abre una **ventana**:

- Campos **API base** e **Ingest token** (se guardan en `config.yaml`).
- Desplegable **Juego (perfil)** con los perfiles disponibles.
- **Calibrar nuevo juego…**: pide nombre + título de ventana y lanza el asistente.
- **Generar embeddings…**: elige la carpeta de iconos y genera el `.npz`.
- **▶ Arrancar / ■ Parar** y un **panel de log** con lo que va detectando.

Para quien lo prefiera, todo sigue disponible por línea de comandos (secciones de
abajo); la GUI no es más que un envoltorio sobre ellas.

### Dónde se guardan los datos (persisten entre actualizaciones)

Los datos del usuario NO viven dentro de la app, sino en la **carpeta de datos del
sistema**, así que **sobrescribir/actualizar la app no los borra**:

- Windows: `%APPDATA%\poke-overlay\`
- Linux: `~/.local/share/poke-overlay/`
- macOS: `~/Library/Application Support/poke-overlay/`

```
poke-overlay/                 (en %APPDATA%, etc.)
  config.yaml                 ← api_base, token, perfil
  profiles/<juego>.yaml       ← perfiles que calibras
  assets/
    templates/<juego>/party_menu.png
    icons/gen3/ … gen9/       ← galerías de iconos incluidas (+ embeddings.npz)
```

Al primer arranque, la app **siembra** ahí las galerías de iconos y los perfiles de
ejemplo que trae empaquetados (sin pisar lo que ya tengas).

### Galerías de iconos incluidas

La app trae galerías de menu sprites por generación (gen 3–9, fuente Bulbagarden) con
sus `embeddings.npz` ya generados. Al **calibrar**, indica la **generación** del juego
y el perfil usará esa galería directamente: no necesitas reunir iconos ni generar
embeddings a mano. Solo si juegas con un render muy distinto (texturas HD que cambian
los iconos) tendrá sentido rehacer la galería con tus propias capturas.

## Configuración (CLI)

1. Copia `config.example.yaml` a `config.yaml` y rellena:
   - `api_base`: URL del backend de claude-test.
   - `ingest_token`: cópialo desde la pestaña **Stream** de claude-test.
   - `profile`: nombre de un perfil en `pvo/profiles/`.
2. Crea el **perfil de juego** con el asistente de calibración (ver abajo) en vez de
   medir píxeles a mano.

## Calibrar un juego (asistente)

Cada juego/generación necesita su perfil **una vez** (el layout del menú difiere). El
asistente lo genera a base de clics y **detecta solo el área de juego** (recorta el
cromo del emulador); las coordenadas se guardan en resolución de referencia, así que
son **independientes del tamaño de ventana/zoom**.

```bash
# abre el menú de equipo en el emulador, y luego:
python -m pvo.main --calibrate gba_emerald --window "mGBA" --aspect 1.5
```

Se abre una ventana con la captura ya recortada y normalizada. Dibuja un rectángulo
sobre cada **icono** (6), cada **mote** (6, o `n` si el juego no lo muestra) y una
**zona fija del menú** (firma para el detector). El asistente escribe
`pvo/profiles/gba_emerald.yaml` y el template `assets/templates/gba_emerald/party_menu.png`.

Flags útiles: `--region x,y,w,h` (en vez de `--window`), `--res WxH` (resolución de
referencia, por defecto `240x160`), `--viewport x,y,w,h` (si la detección automática
falla), `--lang es`.

Lo único que queda manual es generar los **embeddings** de especie (siguiente paso).

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
pyinstaller --onedir --noconfirm --name poke-overlay \
  --collect-all easyocr --collect-all torch --collect-all torchvision \
  --add-data "pvo/profiles:pvo/profiles" \
  --add-data "assets:assets" \
  run.py
```

> **Usa `--onedir`, no `--onefile`.** Con `--onefile` el ejecutable re-extrae ~1-2 GB
> de torch a una carpeta temporal en **cada arranque**, lo que ralentiza muchísimo el
> PC. `--onedir` genera una carpeta (`dist/poke-overlay/`) que arranca rápido; se
> distribuye comprimida. El punto de entrada debe ser **`run.py`** (no `pvo/main.py`,
> que como script suelto rompe los imports relativos).

La carpeta queda en `dist/poke-overlay/`. Pesa bastante por los modelos ML (trade-off
de usar OCR neural robusto a HD). Pruébala en una máquina sin Python.

### Compilar el .exe de Windows sin tener Windows/Python

PyInstaller **no** hace cross-compile desde Linux. Para obtener el `.exe` sin montar
un entorno Windows propio, usa el workflow `.github/workflows/build-windows.yml`:
compila en un runner `windows-latest` y sube el binario como artefacto.

- Manual: pestaña **Actions → Build Windows executable → Run workflow**.
- Por release: crea un tag `vX.Y.Z` y el `.exe` se adjunta a la release.

Descarga el artefacto `poke-overlay-windows` (un **.zip** con la carpeta de la app:
`poke-overlay.exe`, `_internal/`, `config.example.yaml`). Descomprímela entera y
ejecuta `poke-overlay.exe` desde dentro. El usuario final no necesita Python.

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
