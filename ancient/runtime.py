"""Adapter runtime wiring for Ancient Empires.

AEPROG.EXE is a plain MZ executable (not packed — no LZEXE bootstrap needed;
see docs/ancient_empires/README.md).  The data archives AE000.DAT/AE001.DAT
must sit next to the EXE (assets/).
"""
from __future__ import annotations

from pathlib import Path

from dos_re.runtime import Runtime, create_runtime
from dos_re.snapshot import load_snapshot

EXE_NAME = "AEPROG.EXE"

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "assets" / EXE_NAME


def create_game_runtime(
    exe_path: str | Path = DEFAULT_EXE,
    *,
    game_root: str | Path | None = None,
    command_tail: bytes | str = b"",
    install_replacements: bool = True,
) -> Runtime:
    """Boot a fresh runtime.  ``install_replacements=False`` is the pure-ASM
    oracle: no recovered hooks, the CPU runs the original code verbatim."""
    if install_replacements:
        from . import hooks  # noqa: F401  (registers @registry.replace handlers)
    return create_runtime(exe_path, game_root=game_root, command_tail=command_tail)


def load_game_snapshot(
    exe_path: str | Path,
    snapshot_dir: str | Path,
    *,
    game_root: str | Path | None = None,
) -> Runtime:
    return load_snapshot(exe_path, snapshot_dir, game_root=game_root)
