# pokemon-vision-overlay

Lee **el equipo Pokémon** de un emulador (GBA/NDS/3DS) **por visión sobre la
interfaz** (sin leer memoria) y lo publica en el **overlay público** de `claude-test`
(la misma vista `/stream/:token` que se usa en OBS y se puede compartir por URL).

Patrón: lee el equipo **al abrir el menú de equipo**, lo **cachea** y lo mantiene
estático mientras viajas/combates; solo lo refresca en la siguiente apertura.

- **Especie** → identificada por el **icono** del menú con *template matching
  enmascarado* (compara solo los píxeles del Pokémon usando la máscara del sprite, así
  ignora el fondo del panel; ZNCC + búsqueda de bamboleo). Automático para toda la
  Pokédex y sin torch.
- **Mote** → leído por **OCR neural** (EasyOCR).

## Fuente: RetroArch (memoria) — recomendado para GBA/DS

Si juegas en **RetroArch** (o corres DS en su core melonDS), puedes leer el equipo
**directo de la memoria del juego** en vez de por visión: sin calibrar, sin reconocer
iconos, **100% fiable** y con motes reales.

1. En RetroArch: **Settings → Network → Network Commands = ON** (puerto 55355).
2. En la app: **Fuente = `retroarch`**, y **Dirección equipo** = `0x020244EC`
   (gPlayerParty en Pokémon Esmeralda). Pulsa **▶ Arrancar**.

Lee los 6 Pokémon (especie, + mote en gen 3) y los publica igual que la visión.

**Juegos** (desplegable "Juego (memoria)", rellena dirección/generación):
- **GBA (gen 3)**: Esmeralda, Rojo Fuego/Verde Hoja, Rubí/Zafiro. Direcciones fiables.
- **DS (gen 4/5)**: Diamante/Perla, Platino, HG/SS, Negro/Blanco, N2/B2. Corre el juego
  en RetroArch con el core **melonDS DS**. Las direcciones DS son **orientativas**
  (versión inglesa): si sale el equipo vacío, hay que localizar la dirección de tu
  versión.
- **3DS (Azahar)**: no hay API de memoria → ahí se usa la visión.

> La dirección `party_address` y la generación dependen del juego; el desplegable las
> pone por ti. Para versiones en otros idiomas puede haber que ajustar la dirección.

## Modo Pokémon Champions (Switch vía OBS) → pestaña Combate

Modo aparte para **Pokémon Champions** capturado con **OBS**. En vez de publicar un
equipo al overlay de stream, alimenta la pestaña **Combate** de claude-test:

- **Fase 1 (pantalla de selección):** detecta el **equipo rival** (los menu-sprites del
  panel rival; tu equipo lo eliges tú a mano en la web).
- **Fase 2 (combate dobles):** cada turno relee los **4 activos** (2 propios + 2 rivales)
  y los marca como seleccionados.

Ambas fases identifican por **icono/menu-sprite** (mismo matcher ZNCC), así que envían
**dex IDs** y son independientes del idioma del juego. El modo automático **no pisa** el
manual: con el toggle "Visión" apagado en la web, todo funciona como siempre.

**Token:** se reutiliza el **mismo `share_token`** de la pestaña Stream (lo muestra el
panel "Visión" de la pestaña Combate). No hay token nuevo.

**Puesta en marcha:**

1. **Galería Champions** (una vez): descarga los menu sprites de Bulbagarden y construye
   la galería:
   ```bash
   python -m pvo.tools.download_champions_sprites
   python -m pvo.tools.build_champions_templates
   ```
2. **OBS:** clic derecho en la fuente del juego → **Proyector en ventana (Fuente)**.
3. **Calibra** las pantallas (selección y combate) recortando, a clics, la firma de cada
   pantalla y los iconos rivales/activos:
   ```bash
   python -m pvo.main --calibrate-champions --window "Windowed Projector"
   ```
   (o el botón **Calibrar Champions…** de la GUI).
4. En la app: **Fuente = `champions`**, **perfil = `champions`**, rellena
   `api_base`/token y **▶ Arrancar**.
5. En la web (pestaña **Combate**): activa **Visión** y pega el token en el overlay.

```
OBS (Proyector en ventana) → captura → clasifica pantalla (selección/combate)
   selección → iconos rival → dexIds → POST /api/stream-team/battle/:token (fase 1)
   combate   → 4 iconos activos → dexIds → POST … (fase 2, cada turno)
```

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
- **Calibrar nuevo juego…**: pide nombre + título de ventana + generación.
- **Probar envío**: manda un equipo de prueba para verificar la web.
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
    icons/gen3/ … gen9/       ← galerías incluidas (templates.npz)
```

Al primer arranque, la app **siembra** ahí las galerías y los perfiles de ejemplo que
trae empaquetados (sin pisar lo que ya tengas).

### Galerías de iconos incluidas

La app trae galerías de menu sprites por generación (gen 3–9, fuente Bulbagarden) ya
convertidas a `templates.npz`. Al **calibrar**, indica la **generación** del juego y el
perfil usa esa galería directamente: **no hay que generar ni etiquetar nada**.

El reconocimiento compara solo los **píxeles del Pokémon** (máscara del sprite),
ignorando el fondo del panel del menú, así que funciona con los sprites estándar para
toda la Pokédex. (Si tu render reemplaza por completo los iconos, regenera la galería
con `pvo.tools.build_templates` a partir de tus capturas.)

> **Probar envío.** El botón homónimo manda un equipo de prueba al endpoint para
> verificar `api_base`/token/red sin depender del reconocimiento.

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
# abre el menú de equipo en el emulador, y luego (gen 3 = GBA):
python -m pvo.main --calibrate esmeralda --window "mGBA" --gen 3
```

La **generación** (`--gen 3..9`, o el desplegable en la GUI) fija a la vez la galería
de iconos y la **resolución/aspecto** del sistema (GBA 240×160, NDS 256×192, 3DS
400×240, Switch 480×270). No necesitas saber resoluciones.

Se abre una ventana con la captura ya recortada y normalizada. Dibuja un rectángulo
sobre cada **icono** (6), cada **mote** (6, o `n` si el juego no lo muestra) y una
**zona fija del menú** (firma para el detector).

Flags de override (avanzado): `--region x,y,w,h` (en vez de `--window`), `--res WxH`,
`--aspect`, `--viewport x,y,w,h` (si la detección automática del área falla), `--lang`.

> En NDS/3DS (doble pantalla) configura el emulador para mostrar **solo la pantalla
> del menú**, o usa `--region`/`--viewport` para acotarla.

Con la generación indicada, el perfil ya apunta a la galería incluida: **no hay paso
manual de referencia**. (Para regenerar plantillas desde tus propias capturas:
`python -m pvo.tools.build_templates --icons <carpeta> --out <carpeta>/templates.npz`.)

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
