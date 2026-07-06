# Ancient Empires port — run status

Current phase: **bring-up (porting guide steps 0–6, lifecycle Stage 0)**.
Owner priorities: VGA is the primary video mode; AdLib/OPL music and
PC-speaker SFX must work; CGA/EGA stay isolated and never block VGA.

## 2026-07-06 — boot + video + input proven (OBSERVED)

- Adapter package `ancient/` created from the skeleton; lint + layer audit
  wired (`tools/lint.py` PACKAGE_ROOTS, `tools/audit_layers.py
  ancient/recovered`). `tests/test_ancient_boot.py` skips without assets.
- **Framework extensions this game proved it needs** (all with focused tests
  in `tests/test_core.py`):
  - CPU opcode `0x99` CWD (hit at 1010:02A6, icount ~97k).
  - INT 10h AH=1Ah read display combination → AL=1Ah, BL=08h (VGA). This is
    the game's VGA probe; with it the game selects **mode 13h**.
  - INT 15h AH=C0h → CF=1, AH=86h (8086-class machine, no config table).
  - INT 21h AX=4400h IOCTL get device info (probed on an opened .DAT handle).
- Boot: `create_game_runtime()` runs clean past init. Game installs INT 08
  ISR at **1010:6BCF**, INT 09 ISR at **1010:699E**, PIT ch0 reload
  **0x13B1** (5041 → 236.69 Hz) — all matching docs/ancient_empires/README.md.
  DGROUP DS = **0x1FB3** (load seg 0x1010 + 0xFA3), so doc flat offsets map
  1:1 to cs=1010 offsets.
- Timer IRQs are front-end pumped (`deliver_interrupt(rt, 0x08)` between run
  batches); without them the game parks in a tick-wait (observed at
  1010:5557, a `ret` inside a poll helper).
- Video: intro screen renders pixel-correct via `tools/render_frame.py`
  (VGA mode 13h). Evidence: `artifacts/snap_timer_pump/frame.png`.
- Input: the game's INT 09 ISR reads port 60h; **special keys** (15-entry
  scancode word table at cs:6A0B: 1D,1F,29,2B,46,47,48,49,4A,4B,4D,4E,50,54,
  58) are handled in-ISR (writes DS:0B68/0B6C observed); **all other keys
  chain to the previous BIOS INT 9** (far ptr at DS:C0CC) and are consumed
  later via INT 16h. Delivery recipe: `deliver_scancode` + push
  `bios_key_value_from_scancode(sc)` into `dos.key_queue`. Enter delivered
  this way advances intro → Player Sign-In menu. Evidence:
  `artifacts/snap_after_enter/frame.png`.

## Next

1. Find frame boundaries (timer wait / retrace wait / present) —
   profile_hotspots + lindis; stand up frame verifier with no-op candidate.
2. Input-wait registry (the intro "press Enter" poll is the first entry —
   canonical head TBD).
3. First demo recording once boundaries + waits are unified.

## Blockers

None open — see blockers.md.
