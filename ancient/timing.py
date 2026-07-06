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


def tick32(cpu: CPU8086) -> int:
    ds = cpu.s.ds & 0xFFFF
    return (cpu.mem.rw(ds, TICK_HI) << 16) | cpu.mem.rw(ds, TICK_LO)


def timer_wait_spinning(cpu: CPU8086) -> Addr | None:
    """Return the wait head if the CPU sits at a tick-wait spin head whose
    condition still holds (the loop would iterate again), else None."""
    addr = cpu.addr()
    if addr == WAIT_DEADLINE_HEAD:
        ds = cpu.s.ds & 0xFFFF
        deadline = (cpu.mem.rw(ds, DEADLINE_HI) << 16) | cpu.mem.rw(ds, DEADLINE_LO)
        return addr if tick32(cpu) < deadline else None
    if addr == WAIT_REL_HEAD:
        ss, bp = cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF
        target = (cpu.mem.rw(ss, (bp - 2) & 0xFFFF) << 16) | cpu.mem.rw(ss, (bp - 4) & 0xFFFF)
        return addr if tick32(cpu) < target else None
    return None


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
