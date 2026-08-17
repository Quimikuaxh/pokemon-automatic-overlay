"""Agente headless: lee el equipo y lo publica; la interfaz vive en claude-test."""

from .core import SOURCES, VERSION, AgentCore

__all__ = ["AgentCore", "SOURCES", "VERSION"]
