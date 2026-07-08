"""Timer/tick machinery for Ancient Empires (all addresses TRACED 2026-07-06).

The game reprograms PIT ch0 to reload 0x13B1 (5041 -> 236.69 Hz) and installs
its INT 08h ISR at 1010:6BCF (installer at 1010:6B7A).  The ISR maintains a
32-bit master tick counter at DS:0B76/0B78, chains the saved BIOS INT 08h
(far ptr at DS:0B7A) every 13th tick, and calls the per-tick service routine
at 1010:C1A0.

Wait helpers (traced at 1010:6C26..6C9E):
- 6C26  wait_ticks(AX=delta): target = tick + delta, spin head 6C40 reads the
        target dword from SS:BP-4/BP-2.
- 6C57  set_deadline(AX=delta): DS:C0D0/C0D2 = tick + delta.
- 6C6F  wait_deadline: spin head 6C71, spins while tick32 < deadline32.
- 6C87  deadline_elapsed?: non-blocking check (used by menu/intro poll loops).

The VM delivers no asynchronous IRQs: every driver advances time by delivering
the REAL installed ISR between instruction batches (never by poking the tick
counter -- pitfall #12).  One delivered ISR = one master tick.
"""
from __future__ import annotations

from dos_re.cpu import CPU8086, IF, TF

Addr = tuple[int, int]

CODE_SEG = 0x1010
TIMER_ISR: Addr = (CODE_SEG, 0x6BCF)

TICK_LO = 0x0B76          # DS-relative; DS is the game's DGROUP (0x1FB3)
TICK_HI = 0x0B78
DEADLINE_LO = 0xC0D0
DEADLINE_HI = 0xC0D2

WAIT_REL_HEAD: Addr = (CODE_SEG, 0x6C40)       # spin of wait_ticks (6C26)
WAIT_DEADLINE_HEAD: Addr = (CODE_SEG, 0x6C71)  # spin of wait_deadline (6C6F)

# Full in-loop instruction ranges of the two spins (head..last byte of the
# back-branch), for batched drivers that land mid-iteration and need to know
# "parked in this wait" without checking every step:
#   6C40: mov dx,[0B78]/mov ax,[0B76]/cmp dx,[bp-2]/jb/jnz/cmp ax,[bp-4]/jb
#   6C71: mov dx,[0B78]/mov ax,[0B76]/cmp dx,[C0D2]/jb/jnz/cmp ax,[C0D0]/jb
_WAIT_REL_RANGE = (0x6C40, 0x6C52)
_WAIT_DEADLINE_RANGE = (0x6C71, 0x6C85)


def tick32(cpu: CPU8086) -> int:
    ds = cpu.s.ds & 0xFFFF
    return (cpu.mem.rw(ds, TICK_HI) << 16) | cpu.mem.rw(ds, TICK_LO)


def _wait_target(cpu: CPU8086, head: Addr) -> int:
    if head == WAIT_DEADLINE_HEAD:
        ds = cpu.s.ds & 0xFFFF
        return (cpu.mem.rw(ds, DEADLINE_HI) << 16) | cpu.mem.rw(ds, DEADLINE_LO)
    ss, bp = cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF
    return (cpu.mem.rw(ss, (bp - 2) & 0xFFFF) << 16) | cpu.mem.rw(ss, (bp - 4) & 0xFFFF)


def timer_wait_spinning(cpu: CPU8086) -> Addr | None:
    """Return the wait head if the CPU sits exactly at a tick-wait spin head
    whose condition still holds (the loop would iterate again), else None.
    Per-step detector: the frame verifier checks this after every step so the
    reference and candidate stop at the identical instruction."""
    addr = cpu.addr()
    if addr not in (WAIT_DEADLINE_HEAD, WAIT_REL_HEAD):
        return None
    return addr if tick32(cpu) < _wait_target(cpu, addr) else None


def timer_wait_parked(cpu: CPU8086) -> Addr | None:
    """Return the wait head if the CPU is anywhere INSIDE a tick-wait spin
    whose condition still holds, else None.  For batched drivers (the
    interactive loop) that step in chunks and land mid-iteration."""
    if cpu.s.cs & 0xFFFF != CODE_SEG:
        return None
    ip = cpu.s.ip & 0xFFFF
    if _WAIT_DEADLINE_RANGE[0] <= ip <= _WAIT_DEADLINE_RANGE[1]:
        head = WAIT_DEADLINE_HEAD
    elif _WAIT_REL_RANGE[0] <= ip <= _WAIT_REL_RANGE[1]:
        head = WAIT_REL_HEAD
    else:
        return None
    return head if tick32(cpu) < _wait_target(cpu, head) else None


def park_at_wait_head(cpu: CPU8086, *, max_steps: int = 16) -> Addr | None:
    """If the CPU is inside a still-waiting tick spin, step it forward to the
    spin's canonical head and return the head; else return None.

    The head is the deterministic parking point: while the wait condition
    holds, every loop iteration recomputes the same register state, so the
    machine state at the head is identical no matter where in the iteration
    the caller's batch boundary happened to land.  This is what lets a batched
    driver skip interpreting idle spin iterations (the cookbook's timing
    fast-forward) without perturbing anything the game can observe."""
    head = timer_wait_parked(cpu)
    if head is None:
        return None
    for _ in range(max_steps):
        if cpu.addr() == head:
            return head
        cpu.step()
    # A still-true wait condition cannot take more than one iteration (~8
    # steps) to revisit the head; anything else means the detector's model of
    # this loop is wrong -- fail loud, never park somewhere undefined.
    raise RuntimeError(
        f"park_at_wait_head: did not reach {head[0]:04X}:{head[1]:04X} within "
        f"{max_steps} steps (at {cpu.s.cs:04X}:{cpu.s.ip:04X})"
    )


def deliver_ae_timer_irq0(cpu: CPU8086, *, max_steps: int = 200_000) -> bool:
    """Deliver the game's installed INT 08h ISR exactly like hardware would.

    Returns False (no-op) if the game's ISR is not installed at 1010:6BCF —
    callers must fail loud rather than fake a tick.  The ISR's every-13th-tick
    BIOS chain (far call through DS:0B7A) lands on the framework's F000:FF53
    IRET stub and returns naturally, so no chain-point surgery is needed.
    """
    mem = cpu.mem
    off, seg = mem.rw(0, 0x08 * 4), mem.rw(0, 0x08 * 4 + 2)
    if (seg & 0xFFFF, off & 0xFFFF) != TIMER_ISR:
        return False

    ret_cs, ret_ip = cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF
    sp0 = cpu.s.sp & 0xFFFF
    cpu.push(cpu.s.flags)
    cpu.push(ret_cs)
    cpu.push(ret_ip)
    cpu.set_flag(IF, False)
    cpu.set_flag(TF, False)
    cpu.s.cs, cpu.s.ip = seg & 0xFFFF, off & 0xFFFF
    for _ in range(max_steps):
        if cpu.s.sp == sp0 and cpu.addr() == (ret_cs, ret_ip):
            return True
        cpu.step()
    raise RuntimeError(
        f"AE INT 08h ISR did not return within {max_steps} steps "
        f"(cs:ip={cpu.s.cs:04X}:{cpu.s.ip:04X})"
    )
