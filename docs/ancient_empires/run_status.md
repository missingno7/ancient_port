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

## 2026-07-07 — scripts/play.py: the owner's interactive entrypoint (OBSERVED)

- `scripts/play.py`: live viewer (VGA 13h, tools/display presenter), boots
  cold / `--boot-intro` (cached canonical snapshot) / `--snapshot DIR`;
  **F12** snapshot, **F11** demo record toggle, `--play-demo DIR` replay;
  `--frames N` headless smoke. Key delivery via the shared
  `ancient.keys.deliver_game_key` (scan + dos_key dual path).
- **Interactive (chunked) demo clock**: one presented frame = fixed
  `--chunk-steps` budget with the frame's IRQ quota (master tick 236.70 Hz /
  present_hz) interleaved at fixed sub-batches; params stored in the demo
  manifest and restored on replay. `run_frame` in play.py is the single
  shared frame-advance (loop + tests use it).
- **Proven**: state digests identical across runs and audio on/off (audio is
  observer-only); CLI record→replay identical (digest + CPU addr + icount);
  committed gate `tests/test_ancient_demo_roundtrip.py` records a demo with
  a real Enter press (exercises both delivery paths, visibly advances the
  intro) and replays bit-identically.
- **Audio**: live sink = Nuked-OPL3 (built: `python -m nuked_opl3._ffi_build`)
  + PC-speaker square wave on a pygame channel with jitter lead. Intro plays
  speaker SFX in the VM (119 speaker events/10 s observed). Game *detected*
  AdLib (active port DS:1830=0x388) but music config **DS:1778=0** (off) —
  KB audio.md: 1=PSG, 2=OPL2, 3=port 0x205. Selection is in-game (Options F3
  / per-player config) — confirm interactively, then trace where DS:1778 is
  written. (KB confirms 1010:C1A0 is the sound tick — CANONICAL there.)
- **Known-open (charter §6)**: play.py's chunked clock and the frame
  verifier's wait-head boundary clock are two different demo-clock
  definitions. Fine while each driver replays its own recordings; must be
  unified before the proof-corpus demos are recorded (porting guide step 6).

## Next

1. Owner playtest via scripts/play.py: enable music in-game (Options F3),
   confirm AdLib path live; then trace the DS:1778 write site.
2. Unify the demo-clock definition across play.py and the frame verifier
   before recording proof-corpus demos.
3. Find the present/blit routine (page-buffer far-ptr table at DS:3924) for
   a present boundary; widen the sample toward full observable state.
4. First lifting targets: the DAT decompressor hot loop at 1010:6E11..6E97
   (boot spends ~40M+ instructions there), per porting guide step 7.

## Blockers

None open — see blockers.md.
