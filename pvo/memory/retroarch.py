"""Cliente de la interfaz de comandos por red de RetroArch (UDP).

Requiere activar en RetroArch: Settings → Network → "Network Commands" (puerto 55355
por defecto). Lee memoria del core con `READ_CORE_MEMORY <dirección hex> <bytes>`.
"""

from __future__ import annotations

import socket

_CHUNK = 256  # bytes por petición (evita respuestas UDP enormes)


def parse_read_response(resp: str) -> bytes:
    """Parsea 'READ_CORE_MEMORY <addr> <hex bytes...>' → bytes. Lanza si error."""
    parts = resp.strip().split()
    if len(parts) < 3 or parts[0] != "READ_CORE_MEMORY":
        raise IOError(f"Respuesta inesperada de RetroArch: {resp!r}")
    tokens = parts[2:]
    if tokens[0] == "-1" or tokens[0].lower() == "error":
        raise IOError(
            "RetroArch rechazó la lectura (-1). ¿'Network Commands' activado y un core "
            "con mapa de memoria (mGBA)? ¿Dirección correcta?"
        )
    return bytes(int(h, 16) for h in tokens)


class RetroArchClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 55355, timeout: float = 1.0):
        self._addr = (host, int(port))
        self._timeout = timeout
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(timeout)

    def _read_chunk(self, address: int, size: int) -> bytes:
        cmd = f"READ_CORE_MEMORY {address:x} {size}"
        self._sock.sendto(cmd.encode(), self._addr)
        data, _ = self._sock.recvfrom(65536)
        return parse_read_response(data.decode(errors="replace"))

    def read_memory(self, address: int, size: int) -> bytes:
        """Lee `size` bytes desde `address` (troceando en peticiones pequeñas)."""
        out = bytearray()
        offset = 0
        while offset < size:
            n = min(_CHUNK, size - offset)
            chunk = self._read_chunk(address + offset, n)
            if not chunk:
                raise IOError("RetroArch devolvió una lectura vacía.")
            out += chunk
            offset += len(chunk)
        return bytes(out)

    def close(self) -> None:
        self._sock.close()
