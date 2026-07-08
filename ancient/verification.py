"""Per-hook continuation metadata for the differential verifier.

One GenericHookStop per registered hook address.
"""
from __future__ import annotations

from dos_re.verification import GenericHookStop

DEFAULT_STOPS: dict[tuple[int, int], GenericHookStop] = {
    # Plain near RET (5 argument words left for the caller's own `add sp,0xA`).
    (0x1010, 0x08F2): GenericHookStop("near_ret"),
}
