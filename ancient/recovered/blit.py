"""Pure recovered logic for the masked-bitmap blitter at 1010:08F2.

Structural evidence (2026-07-08): dispatched via the low jump-table thunk at
1010:03CC (`jmp 08F2`), called from the actor-draw dispatcher (1010:4DB2,
inside the region docs/ancient_empires/exe_map.md calls the "Actor draw
loop"). Its pixel format matches docs/ancient_empires/graphics.md exactly:
two 4-bit logical colours per source byte (high nibble first), each mapped
through a 16-entry colour table, logical colour 0 = transparent (no write).
Profiled (ancient/probes/profile_gameplay.py) as the single hottest
non-pacing loop in live gameplay: backward edges 099E<-09E9/09B4 and
0A66<-0A7F/0AB2 dominate all other executed code.

This is a byte-exact mechanical transcription of the ASM (not a "clean"
reimplementation) because the hook oracle diffs full registers + flags, and
this leaf's clobbered scratch registers (AX/BX/CX/DX) and flags at RET are
part of its observable contract under that oracle. AL/AH are tracked
explicitly through the pixel loop rather than reconstructed after the fact.
See docs/ancient_empires/run_status.md for the full derivation (clip rect,
row-pointer-table lookup, mirror path, and the "silhouette" side record
appended to a DS:40C4-anchored list when the game's DS:00BC flag is set).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ancient.islands import oracle_link

CF, PF, AF, ZF, SF, OF = 0x0001, 0x0004, 0x0010, 0x0040, 0x0080, 0x0800
_PARITY = [bin(i).count("1") % 2 == 0 for i in range(256)]


def _sub16(a: int, b: int) -> tuple[int, int]:
    """8086 SUB/CMP, 16-bit: returns (result, flags12) -- mirrors CPU8086.set_sub_flags."""
    a &= 0xFFFF
    b &= 0xFFFF
    raw = a - b
    r = raw & 0xFFFF
    f = 0
    if raw < 0:
        f |= CF
    if r == 0:
        f |= ZF
    if r & 0x8000:
        f |= SF
    if _PARITY[r & 0xFF]:
        f |= PF
    if ((a & 0xF) - (b & 0xF)) < 0:
        f |= AF
    if ((a ^ b) & (a ^ r)) & 0x8000:
        f |= OF
    return r, f


def _add16(a: int, b: int) -> tuple[int, int]:
    a &= 0xFFFF
    b &= 0xFFFF
    raw = a + b
    r = raw & 0xFFFF
    f = 0
    if raw > 0xFFFF:
        f |= CF
    if r == 0:
        f |= ZF
    if r & 0x8000:
        f |= SF
    if _PARITY[r & 0xFF]:
        f |= PF
    if ((a & 0xF) + (b & 0xF)) > 0xF:
        f |= AF
    if (~(a ^ b) & (a ^ r)) & 0x8000:
        f |= OF
    return r, f


def _dec16_preserve_cf(a: int, prior_cf: int) -> tuple[int, int]:
    """8086 DEC (16-bit): SUB-shaped ZF/SF/PF/AF/OF, CF preserved (DEC never touches CF)."""
    r, f = _sub16(a, 1)
    f = (f & ~CF) | (prior_cf & CF)
    return r, f


def _js(flags: int) -> bool:
    return bool(flags & SF)


def _jle(flags: int) -> bool:
    return bool(flags & ZF) or (bool(flags & SF) != bool(flags & OF))


def _jbe(flags: int) -> bool:
    return bool(flags & CF) or bool(flags & ZF)


def _ja(flags: int) -> bool:
    return not (flags & CF) and not (flags & ZF)


@dataclass
class BlitResult:
    """Everything the thin VM adapter needs to apply this hook's effects."""

    # (row_index, col_byte_offset, value) writes, row_index 0-based among the
    # rows actually processed (post vertical clip), col_byte_offset 0-based
    # from that row's resolved base address (adapter adds row*0x140, 16-bit
    # wraparound, to the once-resolved first visible row's base).
    writes: list[tuple[int, int, int]] = field(default_factory=list)
    # (x_half_lo, y_lo, width_bytes, height) to append to the silhouette list,
    # or None if DS:00BC was clear or the clipped Y was out of [0, 0xC8).
    silhouette: tuple[int, int, int, int] | None = None
    reached_pixel_phase: bool = False
    clipped_y: int = 0              # for the adapter's row-pointer-table lookup
    ax: int = 0
    bx: int = 0
    cx: int = 0
    dx: int = 0
    flags12: int = 0                # DF already cleared (epilogue always CLDs)


@oracle_link(
    "1010:08F2",
    contract="full register(AX/BX/CX/DX/ES)+flags+full-memory equivalence at RET "
             "(masked sprite blit: clip, optional horizontal mirror, transparent "
             "colour 0, DS:40C4 silhouette record)",
    status="ASM_MATCHED",
    merge_target="ancient.recovered.render",
)
def blit_masked_bitmap(
    *,
    row_bytes: int,
    height: int,
    pixel_data: bytes,
    vga_table: bytes,
    x: int,
    y: int,
    mirror: bool,
    clip_top: int,
    clip_bottom: int,
    clip_left: int,
    clip_right: int,
    record_silhouette: bool,
    entry_bx: int,
) -> BlitResult:
    cx = row_bytes & 0xFF
    dx = height & 0xFF
    di = y & 0xFFFF
    src_pos = 0  # offset into pixel_data, mirrors SI advancing past the record header

    # --- vertical (Y) clip ---
    ax, f = _sub16(clip_bottom, di)
    if _js(f):
        return BlitResult(ax=ax, bx=entry_bx, cx=cx, dx=dx, flags12=f)
    ax = (ax + 1) & 0xFFFF
    _, fcmp = _sub16(dx, ax)
    if not _jbe(fcmp):
        dx = ax

    ax, f = _sub16(clip_top, di)
    if not _jle(f):
        dx, f = _sub16(dx, ax)
        if _jbe(f):
            return BlitResult(ax=ax, bx=entry_bx, cx=cx, dx=dx, flags12=f)
        di = (di + ax) & 0xFFFF
        src_pos = (ax & 0xFF) * cx  # MUL CL uses AL only

    bx = x & 0xFFFF
    if not mirror:
        return _blit_normal(cx, dx, di, src_pos, pixel_data, vga_table,
                            bx, clip_left, clip_right, record_silhouette)
    return _blit_mirror(cx, dx, di, src_pos, pixel_data, vga_table,
                        bx, clip_left, clip_right, record_silhouette)


def _blit_normal(cx, dx, di, src_pos, pixel_data, vga_table, bx,
                 clip_left, clip_right, record_silhouette) -> BlitResult:
    bx = (bx >> 1) & 0xFFFF  # SAR bx,1 (arithmetic; bx is a non-negative screen X)
    bp = 0

    ax, f = _sub16(clip_right, bx)
    if _js(f):
        return BlitResult(ax=ax, bx=bx, cx=cx, dx=dx, flags12=f)
    ax = (ax + 1) & 0xFFFF
    _, fcmp = _sub16(cx, ax)
    if not _jbe(fcmp):
        bp = (cx - ax) & 0xFFFF
        cx = ax

    ax, f = _sub16(clip_left, bx)
    if not _jle(f):
        cx, f = _sub16(cx, ax)
        if not _ja(f):
            return BlitResult(ax=ax, bx=bx, cx=cx, dx=dx, flags12=f)
        bx = (bx + ax) & 0xFFFF
        bp = (bp + ax) & 0xFFFF
        src_pos += ax

    silhouette = None
    if record_silhouette and di < 0xC8:
        silhouette = (bx & 0xFF, di & 0xFF, cx & 0xFF, dx & 0xFF)

    bx_di_base = (bx << 1) & 0xFFFF  # SHL bx,1: half-x -> byte offset, added to row base for DI

    writes: list[tuple[int, int, int]] = []
    al = ah = 0
    for row in range(dx):
        col = 0
        for _ in range(cx):
            raw = pixel_data[src_pos] if src_pos < len(pixel_data) else 0
            src_pos += 1
            ah = raw
            al = raw & 0x0F
            if al == 0:                          # low nibble transparent
                ah = (ah >> 4) & 0x0F             # ah = high nibble
                if ah != 0:                       # 09D6..09E3: mov es:[di],al (NOT di+1)
                    al = ah
                    al = vga_table[al]
                    writes.append((row, col, al))
                # else: nothing drawn; al stays 0 (from the earlier AND)
            else:
                al = vga_table[al]                # al = color(low)
                ah = (ah >> 4) & 0x0F              # ah = high nibble
                if ah == 0:                        # 09C4/09C5: inc di; stosb -> di+1
                    writes.append((row, col + 1, al))
                else:
                    al, ah = ah, al                # xchg: al=high_raw, ah=color(low)
                    al = vga_table[al]             # al = color(high)
                    writes.append((row, col, al))
                    writes.append((row, col + 1, ah))
            col += 2
        src_pos += bp
    _, fadd = _add16(0, bp)
    _, fdec = _dec16_preserve_cf(1, fadd & CF)
    return BlitResult(writes=writes, silhouette=silhouette,
                      reached_pixel_phase=True, clipped_y=di,
                      ax=((ah & 0xFF) << 8) | (al & 0xFF), bx=bx_di_base, cx=cx, dx=0,
                      flags12=fdec)


def _blit_mirror(cx, dx, di, src_pos, pixel_data, vga_table, bx,
                 clip_left, clip_right, record_silhouette) -> BlitResult:
    bp = 0
    bx = (bx + cx + cx) & 0xFFFF
    bx = (bx >> 1) & 0xFFFF  # SAR by 1
    bx = (bx - 1) & 0xFFFF

    ax, f = _sub16(bx, clip_left)
    if _js(f):
        return BlitResult(ax=ax, bx=bx, cx=cx, dx=dx, flags12=f)
    ax = (ax + 1) & 0xFFFF
    _, fcmp = _sub16(cx, ax)
    if not _jbe(fcmp):
        bp = (cx - ax) & 0xFFFF
        cx = ax

    ax, f = _sub16(bx, clip_right)
    if not _jbe(f):
        cx, f = _sub16(cx, ax)
        if not _ja(f):
            return BlitResult(ax=ax, bx=bx, cx=cx, dx=dx, flags12=f)
        bx = (bx - ax) & 0xFFFF
        bp = (bp + ax) & 0xFFFF
        src_pos += ax

    silhouette = None
    if record_silhouette and di < 0xC8:
        left_x = (bx - cx + 1) & 0xFF
        silhouette = (left_x, di & 0xFF, cx & 0xFF, dx & 0xFF)

    bx_di_base = (bx << 1) & 0xFFFF  # SHL bx,1: half-x -> byte offset, added to row base for DI

    # Within one source byte's pair-slot the write offsets are always (col,
    # col+1) -- [col]=low-nibble colour, [col+1]=high-nibble colour -- exactly
    # like the normal path.  Only COL's per-byte step differs (-2 here, since
    # DF=1 makes DI walk the row right-to-left); high is tested before low
    # (mirrored nibble priority), and the recorded silhouette X is the sprite's
    # left edge regardless of draw direction (see left_x above).
    writes: list[tuple[int, int, int]] = []
    al = ah = 0
    for row in range(dx):
        col = 0
        for _ in range(cx):
            raw = pixel_data[src_pos] if src_pos < len(pixel_data) else 0
            src_pos += 1
            ah = raw
            al = (raw >> 4) & 0x0F               # high nibble checked FIRST (mirror)
            if al == 0:
                ah &= 0x0F                        # low nibble
                if ah != 0:                       # 0AA4..0AAC: mov es:[di],al (NOT di+1)
                    al = ah
                    al = vga_table[al]
                    writes.append((row, col, al))
                else:
                    al = 0
            else:
                al = vga_table[al]                # al = color(high)
                ah &= 0x0F                        # ah = low nibble
                if ah == 0:                        # 0A8E: mov es:[di+1],al
                    writes.append((row, col + 1, al))
                else:
                    al, ah = ah, al                # xchg: al=low_raw, ah=color(high)
                    al = vga_table[al]             # al = color(low)
                    writes.append((row, col, al))
                    writes.append((row, col + 1, ah))
            col -= 2
        src_pos += bp
    _, fadd = _add16(0, bp)
    _, fdec = _dec16_preserve_cf(1, fadd & CF)
    return BlitResult(writes=writes, silhouette=silhouette,
                      reached_pixel_phase=True, clipped_y=di,
                      ax=((ah & 0xFF) << 8) | (al & 0xFF), bx=bx_di_base, cx=cx, dx=0,
                      flags12=fdec)
