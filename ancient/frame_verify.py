"""Frame-verify adapter for Ancient Empires (VGA mode 13h primary).

Bring-up configuration: NO boundary replacement hooks — every boundary comes
from the shared wait detector (ancient.input_waits), and ``pump_inputs``
delivers exactly one real INT 08h master tick per boundary to each runtime
(the unified demo clock; see input_waits.py).  Both runtimes execute 100%%
original bytes, so a no-op candidate must match the oracle exactly.

The sample is the visible VGA mode 13h frame: 64000 bytes at A000:0000 plus
the 256-entry DAC palette (the game uploads a custom palette via INT 10h
AX=1012h; palette divergence must not hide).  Widen this sample as recovery
proceeds (charter §5.3).
"""
from __future__ import annotations

from pathlib import Path

from dos_re.frame_verify import (
    Addr,
    FrameSample,
    FrameVerifyConfig,
    make_frame_sample,
    run_frame_verifier as run_generic_frame_verifier,
)
from dos_re.runtime import Runtime

from .input_waits import frame_verify_wait_detector
from .timing import deliver_ae_timer_irq0

WIDTH, HEIGHT = 320, 200
VRAM_BASE = 0xA0000
VRAM_SIZE = WIDTH * HEIGHT

# No replacement-hook boundaries during bring-up; detector-only.
BOUNDARY_HOOKS: tuple[tuple[Addr, str], ...] = ()
REFERENCE_ENV_HOOKS: set[Addr] = set()


def pump_tick(reference: Runtime, candidate: Runtime) -> None:
    """The shared clock rule: one boundary = one delivered master tick."""
    for rt in (reference, candidate):
        if not deliver_ae_timer_irq0(rt.cpu):
            raise RuntimeError(
                "AE timer ISR not installed at 1010:6BCF; cannot advance the "
                "demo clock (no synthetic timer fallback is allowed)"
            )


def visible_vram(rt: Runtime) -> bytes:
    return bytes(rt.program.memory.data[VRAM_BASE:VRAM_BASE + VRAM_SIZE])


def palette_bytes(rt: Runtime) -> bytes:
    pal = rt.dos.vga_palette
    out = bytearray(768)
    for i, (r, g, b) in enumerate(pal[:256]):
        out[i * 3:i * 3 + 3] = bytes((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(out)


def render_rgb(rt: Runtime) -> bytes:
    vram = visible_vram(rt)
    pal = palette_bytes(rt)
    out = bytearray(VRAM_SIZE * 3)
    for i, px in enumerate(vram):
        out[i * 3:i * 3 + 3] = pal[px * 3:px * 3 + 3]
    return bytes(out)


def sample_builder(
    rt: Runtime,
    side: str,
    frame_no: int,
    kind: str,
    hook: Addr,
    boundary_steps: int,
    start_count: int,
    recent_hooks: tuple[str, ...],
    recent_sample_changes: tuple[str, ...] = (),
) -> FrameSample:
    return make_frame_sample(
        rt=rt,
        side=side,
        frame_no=frame_no,
        kind=kind,
        hook=hook,
        boundary_steps=boundary_steps,
        start_count=start_count,
        recent_hooks=recent_hooks,
        recent_sample_changes=recent_sample_changes,
        raw=visible_vram(rt) + palette_bytes(rt),
        rgb=render_rgb(rt),
        display_start=0,
        width=WIDTH,
        height=HEIGHT,
        context="vga13h",
    )


def run_ae_frame_verifier(
    *,
    reference: Runtime,
    candidate: Runtime,
    max_frames: int = 60,
    frame_budget: int = 2_000_000,
    dump_dir: Path = Path("artifacts/evidence/frame_verify"),
    log_every: int = 10,
) -> int:
    config = FrameVerifyConfig(
        max_frames=max_frames,
        frame_budget=frame_budget,
        source="both",
        dump_dir=dump_dir,
        log_every=log_every,
    )
    return run_generic_frame_verifier(
        reference=reference,
        candidate=candidate,
        config=config,
        boundary_hooks=BOUNDARY_HOOKS,
        sample_builder=sample_builder,
        reference_env_hooks=REFERENCE_ENV_HOOKS,
        pump_inputs=pump_tick,
        input_wait_detector=frame_verify_wait_detector,
        label="AE FRAME VERIFY",
    )
