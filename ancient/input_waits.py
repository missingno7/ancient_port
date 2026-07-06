"""Boundary-less input-wait loop registry (see docs/demos_and_snapshots.md).

Shared by ALL drivers.  Canonical head addresses of busy-wait input polls that
produce no frame boundary.  Empty until traced from the oracle — recording any
demo before this registry is populated produces proofs that freeze or lie.
"""
from __future__ import annotations

INPUT_WAIT_HEADS: dict[tuple[int, int], str] = {}


def is_input_wait(addr: tuple[int, int]) -> bool:
    return addr in INPUT_WAIT_HEADS
