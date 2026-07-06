"""Record/replay determinism for the interactive (chunked) demo clock.

Records a demo from the intro snapshot with a real key event (Enter — which
exercises BOTH delivery paths: the scan event through the game ISR and the
dos_key event through the BIOS queue), then replays it from the demo's start
snapshot and asserts bit-identical final machine state.  Uses scripts/play.py's
run_frame — the same frame-advance the interactive loop runs — so this test
covers the real driver, not a copy.

Skips without assets.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "AEPROG.EXE"
if not EXE.is_file():
    pytest.skip("assets/AEPROG.EXE missing — game asset tests are optional",
                allow_module_level=True)

sys.path.insert(0, str(ROOT / "scripts"))

from dos_re.input_demo import InputDemoPlayback, InputDemoRecorder  # noqa: E402
from dos_re.interrupts import deliver_scancode  # noqa: E402
from dos_re.snapshot import write_snapshot  # noqa: E402

from ancient.keys import deliver_game_key  # noqa: E402
from ancient.runtime import boot_to_intro, create_game_runtime, load_game_snapshot  # noqa: E402
from play import master_tick_hz, run_frame  # noqa: E402

SNAP_DIR = ROOT / "artifacts" / "snap_intro"
CHUNK_STEPS = 40_000
PRESENT_HZ = 60
FRAMES = 160
ENTER = 0x1C


def _digest(rt) -> str:
    return hashlib.sha1(bytes(rt.cpu.mem.data)).hexdigest()


@pytest.fixture(scope="module")
def intro_snapshot() -> Path:
    if not (SNAP_DIR / "memory_1mb.bin").is_file():
        rt = create_game_runtime(EXE, install_replacements=False)
        boot_to_intro(rt)
        write_snapshot(rt, SNAP_DIR, status="intro screen (canonical boot recipe)",
                       steps=rt.cpu.instruction_count)
    return SNAP_DIR


def test_record_then_replay_is_bit_identical(intro_snapshot, tmp_path):
    # --- record ---
    rt = load_game_snapshot(EXE, intro_snapshot)
    tpf = master_tick_hz(rt) / PRESENT_HZ
    rec = InputDemoRecorder(root=tmp_path, name="roundtrip",
                            metadata={"chunk_steps": CHUNK_STEPS, "present_hz": PRESENT_HZ})
    rec.start(rt, boundary=0)
    for frame in range(FRAMES):
        if frame == 30:
            deliver_game_key(rt, ENTER, recorder=rec, boundary=frame)
        if frame == 40:
            deliver_game_key(rt, ENTER | 0x80, recorder=rec, boundary=frame)
        run_frame(rt, frame, chunk_steps=CHUNK_STEPS, ticks_per_frame=tpf)
    demo_dir = rec.stop(boundary=FRAMES)
    recorded_digest = _digest(rt)
    recorded_addr = rt.cpu.addr()

    # The Enter press must have visibly advanced the game (intro -> next screen);
    # otherwise this proves replay of a no-op.
    baseline = load_game_snapshot(EXE, intro_snapshot)
    assert _digest(baseline) != recorded_digest

    # --- replay ---
    playback = InputDemoPlayback.load(demo_dir)
    rt2 = load_game_snapshot(EXE, playback.snapshot_path())
    tpf2 = master_tick_hz(rt2) / PRESENT_HZ
    assert tpf2 == tpf
    for frame in range(FRAMES):
        playback.apply_to_runtimes(frame, [rt2], deliver=deliver_scancode)
        run_frame(rt2, frame, chunk_steps=CHUNK_STEPS, ticks_per_frame=tpf2)

    assert rt2.cpu.addr() == recorded_addr
    assert _digest(rt2) == recorded_digest
