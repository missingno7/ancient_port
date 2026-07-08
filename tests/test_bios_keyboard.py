"""BIOS INT 09h keyboard handler: scancode -> type-ahead buffer translation.

A DOS game that installs its own INT 9 ISR and chains to the previous (BIOS)
handler relies on it filling the buffer INT 16h reads.  These are framework
unit tests (no game assets needed)."""
from __future__ import annotations

from pathlib import Path

from dos_re.cpu import CPU8086, CPUState
from dos_re.dos import DOSMachine
from dos_re.memory import Memory
from dos_re.runtime import BIOS_INT9_ENTRY


def _machine():
    cpu = CPU8086(Memory(), CPUState(cs=0x1000, ds=0x1000, es=0x1000, ss=0x1000, sp=0xFFF0))
    dos = DOSMachine(root=Path("."))
    cpu.port_writer = dos.port_write
    return cpu, dos


def _deliver(cpu, dos, scancode):
    """Enter the handler like the game's chain does: pushf; (far) push cs; push ip."""
    dos.current_scancode = scancode & 0xFF
    ret_ip, ret_cs = 0x1234, 0x1000
    cpu.push(cpu.s.flags)
    cpu.push(ret_cs)
    cpu.push(ret_ip)
    dos.bios_int9_keyboard(cpu)
    assert (cpu.s.cs, cpu.s.ip) == (ret_cs, ret_ip)   # IRET returned cleanly


def test_extended_keys_buffer_as_scancode_high_byte():
    cpu, dos = _machine()
    for sc, word in [(0x50, 0x5000), (0x48, 0x4800), (0x4B, 0x4B00), (0x4D, 0x4D00),
                     (0x3B, 0x3B00)]:  # down, up, left, right, F1
        dos.key_queue.clear()
        _deliver(cpu, dos, sc)
        assert dos.key_queue == [word]


def test_ascii_keys_buffer_scancode_and_ascii():
    cpu, dos = _machine()
    _deliver(cpu, dos, 0x1C)                 # Enter
    assert dos.key_queue[-1] == 0x1C0D
    _deliver(cpu, dos, 0x01)                 # Esc
    assert dos.key_queue[-1] == 0x011B
    _deliver(cpu, dos, 0x1E)                 # 'a'
    assert dos.key_queue[-1] == 0x1E61


def test_shift_state_produces_capitals():
    cpu, dos = _machine()
    _deliver(cpu, dos, 0x2A)                 # shift down (make)
    _deliver(cpu, dos, 0x1E)                 # 'A'
    assert dos.key_queue[-1] == 0x1E41
    _deliver(cpu, dos, 0xAA)                 # shift up (break)
    _deliver(cpu, dos, 0x1E)                 # back to 'a'
    assert dos.key_queue[-1] == 0x1E61


def test_break_codes_and_modifiers_do_not_buffer():
    cpu, dos = _machine()
    _deliver(cpu, dos, 0x9C)                 # Enter release
    _deliver(cpu, dos, 0x1D)                 # Ctrl make (modifier)
    assert dos.key_queue == []


def test_buffer_is_bounded():
    cpu, dos = _machine()
    for _ in range(40):
        _deliver(cpu, dos, 0x1E)
    assert len(dos.key_queue) <= 16


def test_bios_int9_entry_installed_on_fresh_runtime():
    # A fresh runtime installs the native handler and points IVT[9] at it.
    exe = Path(__file__).resolve().parents[1] / "assets" / "AEPROG.EXE"
    if not exe.is_file():
        import pytest
        pytest.skip("assets/AEPROG.EXE missing")
    from ancient.runtime import create_game_runtime
    rt = create_game_runtime(exe, install_replacements=False)
    assert BIOS_INT9_ENTRY in rt.cpu.replacement_hooks
    seg, off = BIOS_INT9_ENTRY
    assert (rt.cpu.mem.rw(0, 9 * 4 + 2), rt.cpu.mem.rw(0, 9 * 4)) == (seg, off)
