"""Per-hook continuation metadata for the differential verifier.

One GenericHookStop per registered hook address.  Empty until the first
recovered routine lands.
"""
from __future__ import annotations

from dos_re.verification import GenericHookStop

DEFAULT_STOPS: dict[tuple[int, int], GenericHookStop] = {}
