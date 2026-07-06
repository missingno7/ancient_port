"""Frame-verify adapter: boundaries + sample builder + reference env hooks.

Candidates from docs/ancient_empires/README.md (to be re-derived against this
oracle before use): timer ISR at code offset 0x6BCF; the player loop
reschedules every 24 master ticks (~9.862 Hz gameplay tick).  Video is EGA
planar.  All values below are placeholders until traced in this VM.
"""
from __future__ import annotations

WIDTH, HEIGHT = 320, 200

BOUNDARY_HOOKS: tuple[tuple[tuple[int, int], str], ...] = ()

REFERENCE_ENV_HOOKS: set[tuple[int, int]] = set()
