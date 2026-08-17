"""Lanzador de nivel superior (punto de entrada del ejecutable).

Importa el paquete `pvo` de forma ABSOLUTA para que los imports relativos internos
funcionen. PyInstaller debe empaquetar este fichero, no `pvo/main.py` directamente
(que como `__main__` rompería los imports relativos).
"""

from pvo.main import main

if __name__ == "__main__":
    raise SystemExit(main())
