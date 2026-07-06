"""Key delivery for Ancient Empires — the ONE path every driver uses.

TRACED 2026-07-06 (kbd ISR 1010:699E): the game's INT 09h handler consumes 15
special scancodes in-ISR (word table at cs:6A0B) and chains everything else to
the previous BIOS INT 9 (far ptr DS:C0CC), reading those keys back later via
INT 16h from the BIOS keyboard buffer.  The VM's BIOS INT 9 is an IRET stub,
so the BIOS-buffer half is modelled by pushing the translated key word into
``dos.key_queue`` (the same store the framework's INT 16h serves) — exactly
what a real BIOS ISR would have produced.

Drivers must not hand-roll this: recording and replay both go through
:func:`deliver_game_key` so demo events cover both delivery paths.
"""
from __future__ import annotations

from dos_re.input_demo import InputDemoRecorder, bios_key_value_from_scancode
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
    """Deliver one XT scancode (make, or make|0x80 break) the way the game's
    ISR + BIOS chain would see it, optionally recording the demo events."""
    scancode &= 0xFF
    deliver_scancode(rt, scancode)
    if recorder is not None and recorder.active:
        recorder.record_scan(boundary=boundary, scancode=scancode)
    make = scancode & 0x7F
    if scancode & 0x80 or make in SPECIAL_SCANCODES:
        return
    value = bios_key_value_from_scancode(make, "")
    if value is None:
        return
    rt.dos.key_queue.append(value & 0xFFFF)
    if recorder is not None and recorder.active:
        recorder.record_dos_key(boundary=boundary, scancode=make,
                                text=chr(value & 0xFF), value=value)
