"""Bridge re-export of dos_re.islands' @oracle_link for ancient/recovered/.

``ancient/recovered/`` may never import ``dos_re`` (tools/audit_layers.py),
but the shared island-manifest generator (``tools/gen_island_manifest.py``)
does an ``isinstance(link, dos_re.islands.OracleLink)`` check, so a duplicate
dataclass in this package would not be discovered -- it must be the real
class. This module is the one place that tension gets resolved: recovered
code imports ``ancient.islands`` (adapter glue, not the pure layer), which
re-exports the genuine ``dos_re.islands`` symbols unchanged.
"""
from __future__ import annotations

from dos_re.islands import OracleLink, oracle_link

__all__ = ["OracleLink", "oracle_link"]
