"""Modo visión para Pokémon Champions (Switch capturado vía OBS).

Detecta el equipo rival en la pantalla de selección (Fase 1) y los Pokémon activos en
combate (Fase 2) por matching de sprite (ZNCC, mismo `SpeciesMatcher` que el modo
emulador) y los publica al backend de claude-test para la pestaña Combate.

Es un flujo independiente del modo emulador/stream: no comparte estado ni rompe nada.
"""
