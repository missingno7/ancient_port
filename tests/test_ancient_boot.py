"""Bring-up tests for the Ancient Empires adapter.

Skip when assets/ has no game files (CI has none — original game files are
never committed; see START_HERE.md step 2).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "AEPROG.EXE"
if not EXE.is_file():
    pytest.skip("assets/AEPROG.EXE missing — game asset tests are optional",
                allow_module_level=True)

from ancient.runtime import create_game_runtime  # noqa: E402


def test_exe_loads_and_boots():
    rt = create_game_runtime(EXE, install_replacements=False)
    rt.cpu.run(100_000)
    # The run must have proceeded (no crash/loud fail before 100k steps).
    assert rt.cpu.instruction_count >= 100_000
