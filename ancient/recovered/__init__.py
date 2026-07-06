"""Pure recovered game logic — NEVER imports dos_re/cpu/memory/hooks/offsets.

Every function carries @oracle_link metadata (dos_re.islands is the one
allowed dos_re import, it is VM-free metadata only if the audit permits;
otherwise tag via the manifest generator).  Enforced by tools/audit_layers.py.
"""
