"""Juegos soportados por lectura de memoria: dirección del equipo, generación y
tamaño de cada Pokémon en el equipo.

GBA (gen 3): direcciones bien conocidas (versión inglesa). DS (gen 4/5): direcciones
ORIENTATIVAS (inglesas) — pueden variar por versión/idioma y por cómo mapee la memoria
el core melonDS; si sale el equipo vacío, hay que localizar la dirección correcta.
El descifrado (gen3.py / gen45.py) es común a cada generación.
"""

# name -> {address, gen, mon_size}
GAMES: dict[str, dict] = {
    "GBA — Esmeralda": {"address": "0x020244EC", "gen": 3, "mon_size": 100},
    "GBA — Rojo Fuego / Verde Hoja": {"address": "0x02024284", "gen": 3, "mon_size": 100},
    "GBA — Rubí / Zafiro": {"address": "0x03004360", "gen": 3, "mon_size": 100},
    # DS (direcciones a verificar)
    "DS — Diamante / Perla": {"address": "0x0227061C", "gen": 4, "mon_size": 236},
    "DS — Platino": {"address": "0x02270044", "gen": 4, "mon_size": 236},
    "DS — HeartGold / SoulSilver": {"address": "0x02234804", "gen": 4, "mon_size": 236},
    "DS — Negro / Blanco": {"address": "0x022346FC", "gen": 5, "mon_size": 220},
    "DS — Negro 2 / Blanco 2": {"address": "0x0221E03C", "gen": 5, "mon_size": 220},
}
