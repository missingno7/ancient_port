"""Hook-oracle verification for the masked-bitmap blitter at 1010:08F2.

Strict/auto-continuation mode: every real invocation during a real gameplay
session is diffed full-register + full-memory against the interpreted ASM.
Uses a locally-captured gameplay snapshot (NOT committed -- game memory
dumps embed original asset data; see docs/demos_and_snapshots.md "Where
evidence lives"). Skips without assets or that snapshot; CI never has either.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "AEPROG.EXE"
GAMEPLAY_SNAPSHOT = ROOT / "artifacts" / "snapshot_ae_20260708_164943"
if not EXE.is_file() or not (GAMEPLAY_SNAPSHOT / "memory_1mb.bin").is_file():
    pytest.skip("assets/AEPROG.EXE or the local gameplay snapshot is missing",
                allow_module_level=True)

import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))

from dos_re.verification import (  # noqa: E402
    HookVerifierConfig,
    HookVerifyDivergence,
    HookVerifyLimitReached,
    install_hook_verifier,
)

from ancient.runtime import load_game_snapshot  # noqa: E402
from play import master_tick_hz, run_frame  # noqa: E402

TARGET = (0x1010, 0x08F2)


def test_blit_08f2_matches_asm_oracle_across_gameplay():
    rt = load_game_snapshot(str(EXE), GAMEPLAY_SNAPSHOT)
    rt.cpu.trace_enabled = False
    tpf = master_tick_hz(rt) / 60

    verifier = install_hook_verifier(
        rt, HookVerifierConfig.strict(hooks={TARGET}), stops={},
    )

    try:
        for frame in range(60):
            run_frame(rt, frame, chunk_steps=40_000, ticks_per_frame=tpf)
    except HookVerifyLimitReached:
        pass
    except HookVerifyDivergence as exc:
        pytest.fail(str(exc))

    assert verifier.total_verified > 0, "the hook never fired -- test proves nothing"


def test_blit_08f2_frame_oracle_equivalence():
    """Semantic proof: hooked candidate reproduces the exact framebuffer the
    ASM oracle produces, paced by real wait boundaries (not raw step counts,
    which a hook that saves thousands of interpreted steps per call would
    otherwise make an unfair/meaningless comparison)."""
    from ancient.frame_verify import run_ae_frame_verifier

    ref = load_game_snapshot(str(EXE), GAMEPLAY_SNAPSHOT, install_replacements=False)
    cand = load_game_snapshot(str(EXE), GAMEPLAY_SNAPSHOT, install_replacements=True)
    assert run_ae_frame_verifier(reference=ref, candidate=cand, max_frames=100,
                                 log_every=0) == 0
