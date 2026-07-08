"""Key delivery for Ancient Empires — the ONE path every driver uses.

TRACED 2026-07-06/07 (kbd ISR 1010:699E): the game's INT 09h handler consumes
15 special scancodes in-ISR (word table at cs:6A0B, held-state at DS:0B68/6A/6C)
and, for the keys it wants buffered, **chains to the previous BIOS INT 9**
(far ptr DS:C0CC).  Non-special keys always chain; special keys chain only when
the game's DS:0B72 "route to buffer" flag is set (menus on, gameplay off).

The framework's native BIOS INT 9 handler (dos_re: DOSMachine.bios_int9_keyboard,
installed at runtime.BIOS_INT9_ENTRY) does the real scancode->type-ahead-buffer
translation when the game chains, exactly like a PC BIOS.  So delivery here is
just ``deliver_scancode`` (which runs the game ISR, which chains) — every driver
that delivers scancodes gets consistent buffered input, no per-driver hacks.
"""
from __future__ import annotations

from dos_re.input_demo import InputDemoRecorder
from dos_re.interrupts import deliver_scancode
from dos_re.runtime import Runtime

# The ISR's in-ISR scancode set (word table at cs:6A0B, 15 entries).
SPECIAL_SCANCODES: frozenset[int] = frozenset(
    (0x1D, 0x1F, 0x29, 0x2B, 0x46, 0x47, 0x48, 0x49,
     0x4A, 0x4B, 0x4D, 0x4E, 0x50, 0x54, 0x58)
)


def deliver_game_key(
    rt: Runtime,
    scancode: int,
    *,
    recorder: InputDemoRecorder | None = None,
    boundary: int = 0,
) -> None:
    """Deliver one XT scancode (make, or make|0x80 break) through the game's own
    INT 9 ISR (which updates its key-state table and chains to the BIOS handler),
    optionally recording it as a demo scan event."""
    scancode &= 0xFF
    deliver_scancode(rt, scancode)
    if recorder is not None and recorder.active:
        recorder.record_scan(boundary=boundary, scancode=scancode)
