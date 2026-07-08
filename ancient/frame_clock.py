"""The interactive driver's chunked demo clock — Ancient Empires' pacing model.

One presented frame = a fixed ``chunk_steps`` instruction budget with the
frame's IRQ quota (from the game's own 236.69 Hz master tick) interleaved at
fixed sub-batch points.  The frame VERIFIER counts wait-head boundaries
instead (ancient/input_waits.py).  Demos recorded under this clock replay
identically under the same {chunk_steps, present_hz} (stored in the demo
manifest); unifying the two clock definitions is the open porting-guide
step-6 item tracked in docs/ancient_empires/run_status.md.

``run_frame`` is the single shared frame-advance for the interactive loop
(scripts/play.py's frontend) AND the headless record/replay tests — never
duplicate this loop (drifting copies void demo proofs).

Lived inline in scripts/play.py until the play-runner unification
(dos_re.player) made the runner a thin frontend; the clock is the
game-specific part, so it moved into the package.
"""
from __future__ import annotations

from dos_re.interrupts import deliver_interrupt


def ticks_for_frame(frame: int, ticks_per_frame: float) -> int:
    """IRQ quota for presented frame ``frame`` — a pure function of the frame
    index, so recordings replay identically."""
    return int((frame + 1) * ticks_per_frame) - int(frame * ticks_per_frame)


def master_tick_hz(rt) -> float:
    reload = rt.dos.pit_channel0_reload or 0x10000
    return rt.dos.PIT_INPUT_HZ / reload


_PARK_PROBE_BATCH = 512  # steps between parked-in-wait probes (any value gives
                         # identical machine state; it only tunes probe overhead)


def _run_budget_or_park(rt, budget: int) -> None:
    """Step up to ``budget`` instructions, stopping early -- parked at the
    spin's canonical head -- once the game enters a registered tick-wait whose
    condition cannot change until the next delivered IRQ.

    This is the cookbook's deterministic timing fast-forward: idle spin
    iterations are provably identical (the loop only re-reads the tick counter
    and its target, and only our IRQ delivery advances the tick), so skipping
    them changes nothing the game can observe.  Parking exactly at the head
    (ancient.timing.park_at_wait_head) makes the stop point -- and therefore
    the IRQ delivery point -- a pure function of machine state, independent of
    the probe batch size.  No state is faked and no IRQ is skipped: the budget
    is simply not burned interpreting a busy-wait (pitfalls #12/#13)."""
    from ancient.timing import park_at_wait_head

    cpu = rt.cpu
    remaining = budget
    while remaining > 0:
        if park_at_wait_head(cpu) is not None:
            return
        batch = _PARK_PROBE_BATCH if remaining > _PARK_PROBE_BATCH else remaining
        cpu.run(batch)
        remaining -= batch
    park_at_wait_head(cpu)  # budget spent mid-iteration: still park canonically


def run_frame(rt, frame: int, *, chunk_steps: int, ticks_per_frame: float) -> None:
    """Advance one presented frame of the chunked demo clock.

    A frame is UP TO ``chunk_steps`` instructions: each of the frame's
    IRQ-quota sub-budgets ends early (parked at the wait head) when the game
    is idling in a tick wait, so the budget is spent on real work, never on
    interpreting spin iterations.  Recordings replay identically under the
    same {chunk_steps, present_hz} (both stored in the manifest; demos
    recorded under the pre-parking clock are not replay-compatible — none
    were promoted)."""
    ticks = ticks_for_frame(frame, ticks_per_frame)
    sub = chunk_steps // (ticks + 1)
    for _ in range(ticks):
        _run_budget_or_park(rt, sub)
        deliver_interrupt(rt, 0x08)
    _run_budget_or_park(rt, chunk_steps - sub * ticks)
