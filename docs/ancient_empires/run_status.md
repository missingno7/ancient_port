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

## 2026-07-06 (later) — frame verifier standing, boundary clock unified (OBSERVED)

- **Timing architecture traced** (ancient/timing.py): timer ISR 1010:6BCF
  increments 32-bit master tick DS:0B76/0B78, chains saved BIOS INT8
  (DS:0B7A) every 13th tick, calls per-tick service 1010:C1A0 (suspected
  audio — unconfirmed). Wait helpers 6C26 (wait_ticks, spin head **6C40**),
  6C57 (set_deadline DS:C0D0/C0D2), 6C6F (wait_deadline, spin head **6C71**),
  6C87 (non-blocking deadline check).
- **Unified demo clock** (all drivers): one boundary = one delivered real
  INT 08h ISR (never a flag poke). Boundary kinds: `timer_wait` at 6C40/6C71
  (condition-gated) and `input_wait` at poll-loop heads **1010:5595** (intro,
  Enter/Esc + attract timeout) and **1010:B08A** (sign-in menu). Registry:
  ancient/input_waits.py, consumed via frame_verify_wait_detector.
- **Frame verifier** (ancient/frame_verify.py): detector-only boundaries, no
  replacement hooks; sample = A000 VRAM 64000B + 768B DAC palette + RGB.
  Evidence: no-op lockstep 4000 boundaries PASS **across the attract-mode
  screen transition** (both boundary kinds exercised); corrupted-candidate
  control caught at frame 1. Committed gate: tests/test_ancient_frame_verify.py
  (cached canonical intro snapshot via ancient.runtime.boot_to_intro).

## Next

1. Record the first demo (intro → sign-in → into gameplay); verify identical
   replay under every driver. Needs key delivery wired into the demo
   recorder (scan + dos_key dual path per the ISR's BIOS chain).
2. Find the present/blit routine (page-buffer far-ptr table at DS:3924) for
   a present boundary; widen the sample toward full observable state.
3. First lifting targets: the DAT decompressor hot loop at 1010:6E11..6E97
   (boot spends ~40M+ instructions there), per porting guide step 7.
4. Audio: confirm 1010:C1A0 is the sequencer service; map PC-speaker/OPL
   port writes (owner priority: AdLib music + PC-speaker SFX must work).

## Blockers

None open — see blockers.md.
