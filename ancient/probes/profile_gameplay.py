"""Throwaway: profile CS:IP frequency across real advancing gameplay frames.

tools/profile_hotspots.py samples raw interpreted steps but never pumps timer
IRQs, so from a gameplay snapshot it just samples the tick-wait spin forever.
This drives the exact same frame-advance play.py uses (run_frame: real INT 08h
ISR delivery, chunked demo clock) so the profile reflects actual per-frame
rendering/game-logic work.

Usage: python -m ancient.probes.profile_gameplay <snapshot_dir> [frames] [chunk_steps]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ancient.runtime import load_game_snapshot  # noqa: E402
from play import master_tick_hz, run_frame  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    snap = argv[0]
    frames = int(argv[1]) if len(argv) > 1 else 120
    chunk_steps = int(argv[2]) if len(argv) > 2 else 40_000
    present_hz = 60

    rt = load_game_snapshot(str(ROOT / "assets" / "AEPROG.EXE"), snap)
    cpu = rt.cpu
    cpu.trace_enabled = False
    tpf = master_tick_hz(rt) / present_hz

    addr_counts: Counter[tuple[int, int]] = Counter()
    backward_edges: Counter[tuple[tuple[int, int], tuple[int, int]]] = Counter()
    call_targets: Counter[tuple[int, int]] = Counter()

    orig_step = cpu.step
    prev = [None]

    def counting_step():
        a = cpu.addr()
        addr_counts[a] += 1
        orig_step()
        b = cpu.addr()
        if b[0] == a[0] and b[1] <= a[1]:
            backward_edges[(a, b)] += 1
        prev[0] = a

    cpu.step = counting_step

    import time
    t0 = time.perf_counter()
    total_steps_before = cpu.instruction_count
    for f in range(frames):
        run_frame(rt, f, chunk_steps=chunk_steps, ticks_per_frame=tpf)
    wall = time.perf_counter() - t0
    executed = cpu.instruction_count - total_steps_before

    print(f"profiled {frames} frames, {executed:,} steps, {wall:.2f}s "
          f"({executed / wall:,.0f} steps/sec)")
    print(f"final CS:IP = {cpu.s.cs:04X}:{cpu.s.ip:04X}")
    print("-" * 64)
    print("Top 40 executed CS:IP:")
    for (cs, ip), count in addr_counts.most_common(40):
        pct = 100 * count / executed
        print(f"  {cs:04X}:{ip:04X}  {count:9,}  {pct:5.2f}%")
    print("-" * 64)
    print("Top 20 backward edges (tight loops):")
    for (src, dst), count in backward_edges.most_common(20):
        print(f"  {src[0]:04X}:{src[1]:04X} -> {dst[0]:04X}:{dst[1]:04X}  {count:9,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
