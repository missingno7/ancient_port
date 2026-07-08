"""Run Ancient Empires inside the dos_re VM — the interactive entrypoint.

A thin :class:`dos_re.player.GameFrontend` over the unified play runner
(``dos_re/dos_re/player.py`` documents the full standard CLI: viewer by
default / ``--headless``; ``--snapshot`` / ``--save-snapshot``;
``--record-demo`` / ``--play-demo`` / ``--demo-continue``; hook-mode flags;
F10 screenshot, F11 demo-record toggle, F12 snapshot).  Bring-up phase: the
ORACLE runs — pure original ASM, no recovered hooks yet, so the
``--safe-hooks``/``--verify-hooks``/``--trace-hooks`` tiers fail loud.

What is Ancient-Empires-specific here:

  - THE CLOCK (``ancient/frame_clock.py``): the game paces itself on its own
    236.69 Hz PIT master tick, so a frame is a fixed ``--chunk-steps`` budget
    with the frame's IRQ quota interleaved at fixed sub-batch points, parking
    at registered tick-wait heads instead of interpreting idle spins.  The
    demo clock is the presented-frame index; {chunk_steps, present_hz} are
    stored in the demo manifest and restored on replay.
  - ``--boot-intro``: start at the intro screen via a cached canonical
    snapshot (built once with the versioned recipe in ancient/runtime.py).
  - Audio defaults ON (``--audio adlib``): the framework's observer-only
    Nuked-OPL3 + PC-speaker sink — this game drives both.

Usage:
  python scripts/play.py                        boot from cold
  python scripts/play.py --boot-intro           skip to the intro screen
  python scripts/play.py --snapshot DIR         resume any saved snapshot
  python scripts/play.py --play-demo DIR        replay a recorded demo
  python scripts/play.py --headless --frames N  headless smoke (SDL dummy ok)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))              # the ancient adapter package
sys.path.insert(0, str(ROOT / "dos_re"))   # the dos_re submodule's repo root

from dos_re import player  # noqa: E402
from dos_re.snapshot import write_snapshot  # noqa: E402

from ancient.frame_clock import master_tick_hz, run_frame, ticks_for_frame  # noqa: E402,F401 — re-exported: tests/probes import these from `play`
from ancient.runtime import DEFAULT_EXE, boot_to_intro, create_game_runtime, load_game_snapshot  # noqa: E402

INTRO_SNAPSHOT = ROOT / "artifacts" / "snap_intro"


class AncientFrontend(player.GameFrontend):
    name = "ancient"
    default_exe = str(DEFAULT_EXE)
    default_steps_per_frame = 40_000   # the --chunk-steps demo-clock unit
    default_present_hz = 60
    default_audio = "adlib"            # AdLib + PC speaker, observer-only

    def add_arguments(self, parser):
        parser.add_argument("--chunk-steps", dest="steps_per_frame", type=int,
                            help="alias for --steps-per-frame (the historical name of "
                                 "this port's demo-clock unit)")
        parser.add_argument("--boot-intro", action="store_true",
                            help="start at the intro screen (cached canonical snapshot)")

    def create_runtime(self, args):
        if args.boot_intro:
            if not (INTRO_SNAPSHOT / "memory_1mb.bin").is_file():
                print("building canonical intro snapshot (one-time, ~4 min)...")
                rt = create_game_runtime(args.exe, install_replacements=False)
                boot_to_intro(rt)
                write_snapshot(rt, INTRO_SNAPSHOT,
                               status="intro screen (canonical boot recipe)",
                               steps=rt.cpu.instruction_count)
            return load_game_snapshot(args.exe, INTRO_SNAPSHOT)
        return create_game_runtime(args.exe, install_replacements=False)

    def load_snapshot_runtime(self, args, snapshot_dir):
        return load_game_snapshot(args.exe, snapshot_dir)

    def advance_frame(self, rt, args, frame):
        ticks_per_frame = master_tick_hz(rt) / max(1, args.present_hz)
        run_frame(rt, frame, chunk_steps=args.steps_per_frame,
                  ticks_per_frame=ticks_per_frame)

    def demo_metadata(self, args):
        # Historical keys — existing recorded demos carry exactly these.
        return {"exe": Path(args.exe).name, "chunk_steps": int(args.steps_per_frame),
                "present_hz": int(args.present_hz)}

    def apply_demo_metadata(self, args, meta):
        args.steps_per_frame = int(meta.get("chunk_steps", args.steps_per_frame))
        args.present_hz = int(meta.get("present_hz", args.present_hz))


def main(argv: list[str] | None = None) -> int:
    return player.main(AncientFrontend(ROOT), argv, description=__doc__)


if __name__ == "__main__":
    raise SystemExit(main())
