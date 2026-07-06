"""Shared wait-loop registry for Ancient Empires (see docs/demos_and_snapshots.md).

EVERY driver (interactive play, headless verifier, frame verifier) consumes
THIS registry; duplicating detectors per-driver voids the demo proof.

Two families, both detected at their canonical head and checked every step so
reference and candidate stop at the identical instruction:

- ``input_wait``: poll loops that call the key check (1010:6B4A) and the
  non-blocking deadline check (1010:6C87) but never block in a tick wait.
  They double as timed waits (cursor blink, attract-mode timeout), so the
  shared clock rule still applies at their boundary.
- ``timer_wait``: the tick-wait spin heads from ancient.timing, gated on the
  wait condition still holding.

The unified demo clock (one definition for all drivers): **one boundary =
one delivered INT 08h master tick** (plus any due input events), delivered at
the boundary head via ``ancient.timing.deliver_ae_timer_irq0``.
"""
from __future__ import annotations

from dos_re.cpu import CPU8086

from .timing import timer_wait_spinning

Addr = tuple[int, int]

INPUT_WAIT_HEADS: dict[Addr, str] = {
    # TRACED 2026-07-06: call 6B4A / Enter(0D)+Esc(1B) exits / 6C87 timeout.
    (0x1010, 0x5595): "intro screens: wait Enter/Esc with attract timeout",
    # TRACED 2026-07-06: 24-instruction cycle B08A(call 6B4A) -> AFF9(call 6C87).
    (0x1010, 0xB08A): "sign-in/menu: poll key with blink deadline",
}


def is_input_wait(addr: Addr) -> bool:
    return addr in INPUT_WAIT_HEADS


def frame_verify_wait_detector(cpu: CPU8086) -> tuple[str, Addr] | None:
    """Boundary detector shared by all drivers (dos_re InputWaitDetector shape)."""
    addr = cpu.addr()
    if addr in INPUT_WAIT_HEADS:
        return ("input_wait", addr)
    head = timer_wait_spinning(cpu)
    if head is not None:
        return ("timer_wait", head)
    return None
