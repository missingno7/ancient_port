"""Adapter runtime wiring for Ancient Empires.

AEPROG.EXE is a plain MZ executable (not packed — no LZEXE bootstrap needed;
see docs/ancient_empires/README.md).  The data archives AE000.DAT/AE001.DAT
must sit next to the EXE (assets/).
"""
from __future__ import annotations

from pathlib import Path

from dos_re.runtime import BIOS_INT9_ENTRY, Runtime, create_runtime
from dos_re.snapshot import load_snapshot

EXE_NAME = "AEPROG.EXE"

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "assets" / EXE_NAME

# DGROUP paragraph (load_seg 0x1010 + 0x0FA3); DS:xxxx offsets are DGROUP-relative.
DGROUP_SEG = 0x1FB3
# The game saves the previous INT 9 vector here during install (traced 1010:6B88);
# its ISR chains buffered keys through it.  Snapshots taken before the framework
# grew a native BIOS INT 9 handler saved the old F000:FF53 IRET stub, so their
# menu keyboard input is dead — repoint them at the real handler on load.
SAVED_INT9_VECTOR_OFF = 0xC0CC
_OLD_BIOS_STUB = (0xF000, 0xFF53)


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


def boot_to_intro(rt: Runtime) -> None:
    """Deterministic canonical boot: reach the intro 'press Enter' screen.

    Recipe (versioned — changing it invalidates cached snapshots): 200k free
    steps (init + ISR install), then 25000 batches of 2000 steps + one
    delivered INT 08h master tick.  Ends parked in the intro input-wait loop
    (head 1010:5595) with the screen fully drawn.
    """
    from dos_re.interrupts import deliver_interrupt

    rt.cpu.run(200_000)
    for _ in range(25_000):
        rt.cpu.run(2_000)
        deliver_interrupt(rt, 0x08)


def load_game_snapshot(
    exe_path: str | Path,
    snapshot_dir: str | Path,
    *,
    game_root: str | Path | None = None,
) -> Runtime:
    rt = load_snapshot(exe_path, snapshot_dir, game_root=game_root)
    _repair_saved_int9_vector(rt)
    return rt


def _repair_saved_int9_vector(rt: Runtime) -> None:
    """Migrate a pre-fix snapshot: if the game's saved INT 9 vector still points
    at the old bare IRET stub, repoint it at the native BIOS keyboard handler so
    chained keystrokes reach the type-ahead buffer (menu navigation)."""
    mem = rt.cpu.mem
    off = mem.rw(DGROUP_SEG, SAVED_INT9_VECTOR_OFF)
    seg = mem.rw(DGROUP_SEG, SAVED_INT9_VECTOR_OFF + 2)
    if (seg, off) == _OLD_BIOS_STUB:
        new_seg, new_off = BIOS_INT9_ENTRY
        mem.ww(DGROUP_SEG, SAVED_INT9_VECTOR_OFF, new_off)
        mem.ww(DGROUP_SEG, SAVED_INT9_VECTOR_OFF + 2, new_seg)
