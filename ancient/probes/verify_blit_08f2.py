"""Throwaway: strict-mode hook-oracle verification for the 1010:08F2 blitter.

Runs the gameplay snapshot forward with the hook installed and strict
auto-continuation verification active, so every real invocation during
normal play is diffed full-register+full-memory against the ASM oracle.

Usage: python -m ancient.probes.verify_blit_08f2 <snapshot_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dos_re.verification import HookVerifierConfig, HookVerifyDivergence, HookVerifyLimitReached, install_hook_verifier  # noqa: E402

from ancient.runtime import load_game_snapshot  # noqa: E402
from play import master_tick_hz, run_frame  # noqa: E402

TARGET = (0x1010, 0x08F2)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    snap = argv[0]
    frames = int(argv[1]) if len(argv) > 1 else 60

    rt = load_game_snapshot(str(ROOT / "assets" / "AEPROG.EXE"), snap)
    rt.cpu.trace_enabled = False
    tpf = master_tick_hz(rt) / 60

    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig.strict(hooks={TARGET}, max_verified=None,
                                  progress_callback=None),
        stops={},
    )

    try:
        for f in range(frames):
            run_frame(rt, f, chunk_steps=40_000, ticks_per_frame=tpf)
    except HookVerifyDivergence as exc:
        print("DIVERGENCE:")
        print(exc)
        return 1
    except HookVerifyLimitReached:
        pass

    print(f"OK: {verifier.total_verified} verified calls to {TARGET[0]:04X}:{TARGET[1]:04X}, "
          f"no divergence, {frames} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
