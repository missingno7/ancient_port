"""Replacement hooks: thin VM adapters over pure recovered rules.

Every hook: read VM state -> call a pure rule from ancient/recovered/ -> write
back -> exact return mechanics, with a HookStop entry in verification.py.
"""
from __future__ import annotations

from dos_re.cpu import CPU8086
from dos_re.hooks import registry

from .recovered.blit import blit_masked_bitmap

CODE_SEG = 0x1010

# Physical row-address table: DS:3924 + row*4 = a segment:0 far pointer to
# that scanline's start (a back-buffer, NOT the VGA A000 aperture directly --
# a later present step copies it to A000; see run_status.md 2026-07-08).
_ROW_TABLE_OFF = 0x3924
_CLIP_TOP, _CLIP_BOTTOM, _CLIP_LEFT, _CLIP_RIGHT = 0x0094, 0x0096, 0x0098, 0x009A
_RECORD_FLAG_OFF = 0x00BC
_SILHOUETTE_PTR_OFF = 0x40C4


@registry.replace(0x1010, 0x08F2, "blit_masked_bitmap_08F2")  # CODE_SEG, inlined:
# tools/audit_hook_oracle.py's INT_CONSTANTS resolver is unpopulated upstream
# (dead code, resolves no names), so a variable here would make the audit
# silently see 0 registered hooks instead of covering this one.
def blit_masked_bitmap_08F2(cpu: CPU8086) -> None:
    mem = cpu.mem
    ss, sp = cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF
    # Called-but-not-yet-entered: SP points at the return address, caller args
    # sit above it (matches the routine's own bp+4.. offsets, bp = sp+2 after
    # `push bp`).
    ret_ip = mem.rw(ss, sp)
    x = mem.rw(ss, (sp + 2) & 0xFFFF)
    y = mem.rw(ss, (sp + 4) & 0xFFFF)
    far_off = mem.rw(ss, (sp + 6) & 0xFFFF)
    far_seg = mem.rw(ss, (sp + 8) & 0xFFFF)
    mirror = mem.rw(ss, (sp + 10) & 0xFFFF) != 0

    row_bytes = mem.rb(far_seg, (far_off + 0x20) & 0xFFFF)
    height = mem.rb(far_seg, (far_off + 0x21) & 0xFFFF)
    vga_table = bytes(mem.block(far_seg, (far_off + 0x10) & 0xFFFF, 16))
    pixel_data = bytes(mem.block(far_seg, (far_off + 0x22) & 0xFFFF, row_bytes * height))

    ds = cpu.s.ds & 0xFFFF
    clip_top = mem.rw(ds, _CLIP_TOP)
    clip_bottom = mem.rw(ds, _CLIP_BOTTOM)
    clip_left = mem.rw(ds, _CLIP_LEFT)
    clip_right = mem.rw(ds, _CLIP_RIGHT)
    record_silhouette = mem.rb(ds, _RECORD_FLAG_OFF) == 1

    result = blit_masked_bitmap(
        row_bytes=row_bytes, height=height, pixel_data=pixel_data, vga_table=vga_table,
        x=x, y=y, mirror=mirror,
        clip_top=clip_top, clip_bottom=clip_bottom, clip_left=clip_left, clip_right=clip_right,
        record_silhouette=record_silhouette, entry_bx=cpu.s.bx & 0xFFFF,
    )

    if result.silhouette is not None:
        sil_off = mem.rw(ds, _SILHOUETTE_PTR_OFF)
        sil_seg = mem.rw(ds, (_SILHOUETTE_PTR_OFF + 2) & 0xFFFF)
        x_half_lo, y_lo, width_bytes, height_val = result.silhouette
        mem.wb(sil_seg, sil_off, x_half_lo)
        mem.wb(sil_seg, (sil_off + 1) & 0xFFFF, y_lo)
        mem.wb(sil_seg, (sil_off + 2) & 0xFFFF, width_bytes)
        mem.wb(sil_seg, (sil_off + 3) & 0xFFFF, height_val)
        mem.ww(ds, _SILHOUETTE_PTR_OFF, (sil_off + 4) & 0xFFFF)

    if result.reached_pixel_phase:
        row_off = mem.rw(ds, (_ROW_TABLE_OFF + result.clipped_y * 4) & 0xFFFF)
        row_seg = mem.rw(ds, (_ROW_TABLE_OFF + result.clipped_y * 4 + 2) & 0xFFFF)
        base = (row_off + result.bx) & 0xFFFF
        for row, col, value in result.writes:
            off = (base + row * 0x140 + col) & 0xFFFF
            mem.wb(row_seg, off, value & 0xFF)
        # BX/ES get reused past this point: BX becomes the colour-table byte
        # offset (popped back off the stack at 099B), ES the resolved
        # row/back-buffer segment (from the row-pointer table lookup at 0992)
        # -- neither still holds the clip-derived DI-base value used above.
        final_bx = (far_off + 0x10) & 0xFFFF
        final_es = row_seg
    else:
        final_bx = result.bx & 0xFFFF
        final_es = far_seg  # set once by `les si,[bp+8]` and never touched again

    cpu.s.ax = result.ax & 0xFFFF
    cpu.s.bx = final_bx
    cpu.s.cx = result.cx & 0xFFFF
    cpu.s.dx = result.dx & 0xFFFF
    cpu.s.es = final_es
    # Only CF/PF/AF/ZF/SF/OF are ever set by this routine's arithmetic; DF is
    # always cleared (the shared epilogue always CLDs). IF/TF and reserved
    # bits are untouched by any instruction here -- preserve them exactly,
    # never blanket-overwrite the low 12 bits.
    _STATUS_MASK = 0x0001 | 0x0004 | 0x0010 | 0x0040 | 0x0080 | 0x0800  # CF PF AF ZF SF OF
    cpu.s.flags = (cpu.s.flags & ~(_STATUS_MASK | 0x0400)) | (result.flags12 & _STATUS_MASK) | 0x0002

    # Exact near-RET mechanics: only the return address is caller-owned; the
    # five argument words remain for the caller's own `add sp,0x0A`.
    cpu.s.ip = ret_ip
    cpu.s.sp = (sp + 2) & 0xFFFF
