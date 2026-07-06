"""No-op frame verification for the Ancient Empires adapter (bring-up gate).

Both runtimes execute 100% original bytes; boundaries come from the shared
wait detector and the pump delivers one real INT 08h tick per boundary.  A
no-op candidate must match the oracle at every boundary; a corrupted
candidate must be caught at the first one.

Skips without assets.  The intro snapshot is built once per checkout via the
canonical deterministic recipe (ancient.runtime.boot_to_intro) and cached in
artifacts/ (gitignored scratch — evidence, not a runtime dependency).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "AEPROG.EXE"
if not EXE.is_file():
    pytest.skip("assets/AEPROG.EXE missing — game asset tests are optional",
                allow_module_level=True)

from ancient.frame_verify import run_ae_frame_verifier  # noqa: E402
from ancient.runtime import boot_to_intro, create_game_runtime, load_game_snapshot  # noqa: E402

SNAP_DIR = ROOT / "artifacts" / "snap_intro"


@pytest.fixture(scope="module")
def intro_snapshot() -> Path:
    if not (SNAP_DIR / "memory_1mb.bin").is_file():
        from dos_re.snapshot import write_snapshot

        rt = create_game_runtime(EXE, install_replacements=False)
        boot_to_intro(rt)
        write_snapshot(rt, SNAP_DIR, status="intro screen (canonical boot recipe)",
                       steps=rt.cpu.instruction_count)
    return SNAP_DIR


def test_noop_candidate_matches_oracle(intro_snapshot, tmp_path):
    ref = load_game_snapshot(EXE, intro_snapshot)
    cand = load_game_snapshot(EXE, intro_snapshot)
    assert run_ae_frame_verifier(reference=ref, candidate=cand, max_frames=60,
                                 dump_dir=tmp_path, log_every=0) == 0


def test_corrupted_candidate_is_caught(intro_snapshot, tmp_path):
    ref = load_game_snapshot(EXE, intro_snapshot)
    cand = load_game_snapshot(EXE, intro_snapshot)
    cand.cpu.mem.data[0xA0000 + 160 + 100 * 320] ^= 0x3F
    assert run_ae_frame_verifier(reference=ref, candidate=cand, max_frames=10,
                                 dump_dir=tmp_path, log_every=0) == 1
