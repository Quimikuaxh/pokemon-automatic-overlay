# poke-overlay (pokemon-vision-overlay)

Lee **tu equipo Pokémon** del emulador y lo publica en el **overlay público** de
`claude-test` (la vista `/stream/:shareToken` que se usa en OBS).

Es un **agente sin ventana**: se arranca y se olvida. Toda la interfaz vive en la web
de claude-test, en la pestaña **Stream**, y se comunica con el agente por un canal
seguro. Así se maneja igual desde el móvil o desde otro PC.

> El nombre del repo es histórico: el modo de **visión/OCR** ya no existe. Ahora el
> equipo se lee de la **partida guardada** o de la **memoria del emulador**, que son
> fiables al 100% y no requieren calibrar nada.

## Cómo funciona

```
   TU PC (donde juegas)                        claude-test (en la nube)
┌─────────────────────────┐                 ┌───────────────────────────┐
│  emulador               │                 │  backend                  │
│    │                    │                 │    ├── /api/stream-team/  │
│    ├── partida.srm ─────┼── watcher ──┐   │    │   ingest/:token      │
│    └── memoria ─────────┼── RetroArch ┤   │    └── /api/stream-team/  │
│                         │             │   │        agent/:token (ws)  │
│  agente poke-overlay ◀──┴─────────────┘   │                           │
│         │                                 │  navegador (pestaña       │
│         ├── POST equipo ──────────────────▶─── Stream) ◀── ws ────────│
│         └── ws saliente ──────────────────▶                           │
└─────────────────────────┘                 └───────────────────────────┘
                                                        │
                                            vista pública /stream/:token → OBS
```

El agente **abre él la conexión** hacia el backend (WebSocket saliente, autenticado
con tu `ingest_token`). No hay que abrir puertos ni tocar el router, y funciona con la
web en https sin problemas de *mixed content*.

## Las dos formas de leer el equipo

### 1. Partida guardada (modo SAV) — recomendado

Se vigila el **fichero de partida** del emulador. Cuando guardas dentro del juego, el
emulador reescribe ese fichero, el agente lo detecta y publica el equipo. No hay que
hacer nada más.

| Plataforma | Juegos | Emuladores |
|---|---|---|
| GBA (gen 3) | Rubí/Zafiro, Esmeralda, Rojo Fuego/Verde Hoja | mGBA, VBA-M, RetroArch |
| NDS (gen 4/5) | Diamante/Perla, Platino, HG/SS, Negro/Blanco, N2/B2 | DeSmuME, melonDS, RetroArch |
| 3DS (gen 6/7) | X/Y, Rubí Omega/Zafiro Alfa, Sol/Luna, Ultra Sol/Ultra Luna | Citra, Azahar |

**La extensión da igual.** Cada emulador usa la suya (`.sav`, `.srm`, `.fla`, `.flash`,
`.sa1`, `.sgm`, `.dsv`, `.duc`, o el fichero `main` de 3DS), así que el reconocimiento
es **por contenido**: se quitan los envoltorios conocidos (el footer `|-DESMUME SAVE-|`
de los `.dsv`, la cabecera de los `.duc`) y se busca el equipo validando los checksums
de las propias estructuras Pokémon. Por eso funciona sin depender de la versión ni del
idioma del juego.

**Los savestates no valen.** Un `.state` / `.ss0` / `.st0` es un volcado del emulador,
no una partida. Si seleccionas uno, el agente te lo dice claramente en vez de fallar en
silencio: **guarda dentro del juego** para que se escriba la partida de verdad.

> **Switch (gen 8/9)** — Espada/Escudo, BDSP, Leyendas Arceus, Escarlata/Púrpura — aún
> **no** está soportado. La arquitectura ya está preparada: añadir una plataforma es
> añadir una entrada a `PARSERS` en `pvo/sav/parsers.py`.
>
> **Fangames de RPG Maker / Pokémon Essentials** (tipo Pokémon Añil) quedan **fuera de
> alcance**: guardan en `Game.rxdata` (Ruby Marshal con clases propias de cada fangame)
> y no hay un formato común que parsear.

### 2. Memoria en vivo (RetroArch)

Si juegas en **RetroArch**, se puede leer la memoria del juego mientras juegas, así que
el equipo se actualiza al instante en vez de al guardar.

1. En RetroArch: **Ajustes → Red → Comandos de red = ON** (puerto 55355).
2. En la pestaña Stream de la web: fuente **Memoria (RetroArch)** y elige el juego.

Juegos disponibles en `pvo/memory/games.py` (GBA gen 3 y NDS gen 4/5). Las direcciones
de NDS son orientativas de la versión inglesa: si sale el equipo vacío, usa el modo SAV.

## Instalación y arranque

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml    # rellena api_base e ingest_token
python -m pvo.main
```

El `ingest_token` se copia de la pestaña **Stream** de claude-test.

### El `config.yaml` son dos campos

Solo hay que rellenar **`api_base`** e **`ingest_token`**. Nada más. Todo lo demás — si
lees de la partida guardada o de la memoria, qué fichero, qué juego, cada cuánto se
comprueba — se elige **desde la pestaña Stream**, en el navegador.

Y no hay que reelegirlo cada vez: el agente **guarda solo** en `config.yaml` lo que
configures desde la web, así que al volver a abrir el ejecutable **reanuda con lo
último** sin tocar nada. Si lo paraste desde la web, arranca parado. Si nunca has
configurado nada, se queda esperando órdenes.

> Esos campos son estado interno del agente: no hace falta editarlos a mano (y si lo
> haces, la web los sobrescribirá la próxima vez que cambies algo).

### Comandos

```bash
poke-overlay                 # arranca el agente (reanuda lo último, si lo hay)
poke-overlay --detect-saves  # lista las partidas guardadas que encuentra
poke-overlay --read <save>   # lee un fichero de partida y muestra el equipo
poke-overlay -v              # log detallado
```

`--detect-saves` y `--read` son la vía rápida para comprobar que tu partida se lee bien
antes de montar nada.

### Dónde vive la config

En la carpeta de datos del sistema, para que **sobreviva a las actualizaciones**:

- Windows: `%APPDATA%\poke-overlay\config.yaml`
- Linux: `~/.local/share/poke-overlay/config.yaml`
- macOS: `~/Library/Application Support/poke-overlay/config.yaml`

En desarrollo (ejecutando desde el repo) se usa `config.yaml` en la raíz del proyecto.

## Uso desde la web

En claude-test → pestaña **Stream** → panel **Agente local**:

- **Buscar partidas guardadas**: el agente rastrea las carpetas habituales de los
  emuladores y devuelve solo las que **de verdad se leen** (con cuántos Pokémon tiene
  cada una). También puedes pegar una ruta a mano y comprobarla.
- **Arrancar / Parar**, el estado en vivo, el último equipo recibido y un registro de
  lo que va pasando.

Si el agente no está arrancado, el panel lo dice y los botones quedan deshabilitados.

## El ejecutable (.exe)

### Descargarlo y usarlo

El `.exe` se compila en GitHub Actions, así que no hace falta tener Windows ni Python
para generarlo:

1. **Actions → Build Windows executable → Run workflow** (o publica un tag `vX.Y.Z` y
   el `.exe` se adjunta a la release).
2. Descarga el artefacto **`poke-overlay-windows`**: un zip con `poke-overlay.exe`,
   `config.example.yaml` y este README.
3. Descomprime donde quieras, renombra `config.example.yaml` a `config.yaml` y rellena
   `api_base` e `ingest_token`.
4. Ejecuta `poke-overlay.exe`. Es una **aplicación de consola**: se queda abierta
   mostrando el log mientras el agente trabaja, y se cierra con Ctrl+C o cerrando la
   ventana. Si prefieres pasarle opciones, ábrelo desde `cmd`:

```
poke-overlay.exe --detect-saves
poke-overlay.exe --read "C:\ruta\a\tu\partida.srm"
```

> El `config.yaml` que uses realmente vive en `%APPDATA%\poke-overlay\`. Si arrancas el
> `.exe` sin config, se crea ahí uno con los valores por defecto y la ruta sale en el
> log; edítalo y vuelve a arrancar.

### Compilarlo a mano

```bash
pip install pyinstaller
pyinstaller --onefile --noconfirm --name poke-overlay run.py
```

Queda en `dist/poke-overlay`. Se usa `--onefile` (un único binario de unos pocos MB) y
el punto de entrada es **`run.py`**, no `pvo/main.py`: como script suelto rompería los
imports relativos del paquete. No hay que empaquetar assets ni perfiles: la app ya no
usa ninguno.

## Tests

```bash
python -m unittest discover -s tests -v
```

Cubren el descifrado de las estructuras Pokémon, la localización del equipo dentro del
fichero de partida, los contenedores de cada emulador, el watcher y el control del
agente. Las partidas de prueba se **generan sintéticamente** (`tests/savefixtures.py`),
así que no hace falta ningún fichero real ni se versionan datos personales.

Para contrastar contra partidas reales, apunta a una carpeta con las tuyas:

```bash
PVO_REAL_SAVES=/ruta/con/mis/saves python -m unittest discover -s tests -v
```

## Estructura

```
pvo/
  main.py            punto de entrada (CLI del agente)
  appconfig.py       config.yaml
  paths.py           dónde viven config y log
  publisher.py       POST del equipo al endpoint de ingesta
  pkm.py             descifrado común de gen 4-7 (bloques barajados + LCG)
  agent/
    core.py          lógica de control (sin red → testeable)
    protocol.py      mensajes del canal de control
    bridge.py        WebSocket saliente con reconexión
    sources.py       fuentes: partida guardada / RetroArch
  sav/
    container.py     envoltorios por emulador y detección de savestates
    scan.py          localización del equipo por checksum
    gba.py           partidas de GBA (sectores de flash)
    parsers.py       registro de plataformas ← punto de extensión
    locate.py        búsqueda de partidas en el PC
    watcher.py       vigilancia del fichero
  memory/            lectura en vivo por RetroArch
```
