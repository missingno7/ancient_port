"""Replacement hooks: thin VM adapters over pure recovered rules.

No hooks yet — bring-up phase (porting guide steps 0-6).  Every future hook:
read VM state -> call a pure rule from ancient/recovered/ -> write back ->
exact return mechanics, with a HookStop entry in verification.py.
"""
from __future__ import annotations
