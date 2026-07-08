# Ancient Empires port — run status

Current phase: **lifecycle Stage 1 (first islands) started 2026-07-08** —
bring-up (Stage 0) is complete; gameplay is reachable and the first hot leaf
routine is recovered and hook-oracle verified. Owner priorities: VGA is the
primary video mode; AdLib/OPL music and PC-speaker SFX must work; CGA/EGA
stay isolated and never block VGA.

## 2026-07-08 — play.py rebased onto the unified dos_re.player runner (VERIFIED)

- `scripts/play.py` is now a thin `AncientFrontend` over `dos_re.player` (the
  standard CLI: viewer by default / `--headless`; `--play-demo` +
  `--demo-continue`; F10 screenshot joins F11/F12). The game-specific chunked
  demo clock moved intact to **`ancient/frame_clock.py`** (`run_frame`,
  `master_tick_hz`, `ticks_for_frame` — play.py re-exports them, so
  `from play import run_frame` consumers are unchanged). The AudioSink was
  promoted verbatim into the framework (`dos_re/audio_sink.py`, wired as
  `--audio adlib`, this port's default; `--no-audio` became `--audio off`).
  Demo manifests keep the historical `{chunk_steps, present_hz}` keys —
  existing demos replay unchanged (`--chunk-steps` stays as an alias).
  Suite green (127), boot-intro viewer smoke green.

## 2026-07-08 — first recovered island: the sprite blitter at 1010:08F2 (ASM_MATCHED)

- **Evidence for the target**: `ancient/probes/profile_gameplay.py` (drives
  real frames via play.py's `run_frame`, not raw steps) showed the pixel
  loops at 099E/0A66 as the dominant non-pacing backward edges in real
  gameplay — by a wide margin over every other executed address. Traced the
  entry (`push bp` prologue) back to **1010:08F2**, reached from the actor
  draw dispatcher (1010:4DB2) via the low jump-table thunk **1010:03CC**
  (`jmp 08F2`) — matches exe_map.md's "Actor draw loop" region.
- **What it does** (docs/ancient_empires/graphics.md's Type 0x47 bitmap
  format, confirmed structurally): a masked sprite blit — clips against a
  playfield rect (DS:0094/96/98/9A), optionally mirrors horizontally, maps
  each 4-bit logical-colour nibble (high nibble first; 0 = transparent,
  skipped) through the sprite's own 16-entry VGA colour table, and writes
  through a per-scanline pointer table at **DS:3924** (200×4-byte
  segment:0-style far pointers — NOT the VGA A000 aperture directly; it
  targets a **back-buffer** that a separate present step later copies to
  A000, confirmed byte-identical to A000 in a live snapshot). When the
  game's **DS:00BC** flag is set (true throughout normal play) it also
  appends a 4-byte `{x_half, y, width_bytes, height}` record to a growing
  list anchored at **DS:40C4** — purpose not yet confirmed (dirty-rect list
  or hitbox cache; logged as open in the symbol ledger).
- **Recovery method**: because the hook oracle diffs full registers + flags
  + memory, this leaf's clobbered scratch registers (AX/BX/CX/DX/ES) and
  flags at RET are part of its verified contract — so
  `ancient/recovered/blit.py` is a byte-exact mechanical transcription of
  the ASM (not a "clean" reimplementation), using hand-ported 8086
  SUB/ADD/DEC flag formulas (recovered/ cannot import dos_re, so these are
  duplicated locally, matching `CPU8086.set_sub_flags` etc.). Two real bugs
  were caught and fixed by the oracle during this process (worth recording
  as the concrete value of full-diff verification, pitfall #7):
  1. **Register reuse mis-modeled**: BX is the X/clip-math register through
     0x0996, then gets `pop`ped at 0x099B to become the colour-table byte
     offset for the rest of the routine — an entirely different value. My
     first draft kept using the clip-derived BX throughout.
  2. **One write-offset transcription error**: the "low nibble transparent,
     high nibble opaque" case writes to `[DI]` directly (`09E0..09E3`), not
     `[DI+1]` as the symmetric-looking "high transparent" case does
     (`09C4/09C5`) — caught via a 26-byte pixel-level memory diff.
- **Proven**: `tests/test_blit_08f2.py` — (a) strict/auto-continuation hook
  oracle, full register+flags+full-memory diff, across 60 real gameplay
  frames (both the normal and mirrored draw paths exercised, ~100/300
  mirrored in a longer manual run); (b) frame-oracle equivalence (ASM
  reference vs hooked candidate) over 100 wait-paced boundaries, pixel- and
  VRAM-exact. Both require a **local, uncommitted** gameplay snapshot
  (`artifacts/snapshot_ae_20260708_164943` — game memory dumps embed
  original asset data, kept out of git per demos_and_snapshots.md) and skip
  without it. Full suite 125 green; lint + both layer/hook-oracle audits
  clean. First island manifest entry generated
  (`docs/ancient_empires/recovered_islands.md`).
- **Framework addition**: `ancient/islands.py` — a thin re-export of
  `dos_re.islands.oracle_link`/`OracleLink`. `tools/gen_island_manifest.py`
  does `isinstance(link, dos_re.islands.OracleLink)`, so a duplicate
  dataclass (the pre2_port precedent, which has its own self-contained
  `gen_island_manifest.py`) would not be discovered by *this* repo's shared
  tool; recovered code imports the adapter-level bridge instead of `dos_re`
  directly, satisfying both the discovery mechanism and the layer audit.
- **Also fixed in passing**: `ancient/runtime.py`'s `load_game_snapshot`
  never imported `ancient.hooks`, so replacement hooks silently never
  installed on any snapshot-resumed runtime (only fresh boots via
  `create_game_runtime` got them) — a real gap since scripts/play.py's
  `--snapshot`/`--play-demo` paths, and every test using `load_game_snapshot`,
  were all running pure-ASM without noticing. Now takes the same
  `install_replacements` flag as `create_game_runtime` (default True).

## Performance signal

One hook: ~300 calls in a 300-frame gameplay sample, each replacing ~3300
interpreted steps with one native step — roughly **8% of the interpreted
instruction budget in this scene**, from a single leaf. Confirms the charter's
guidance that blitters are the right first targets both for game speed and
for system observability.

## 2026-07-08 (later) — VM efficiency: wait-parking + interpreter micro-opts

Owner asked for the game to run better even at pure ASM. Profiling showed the
real sink: **~86% of interpreted gameplay steps were the 7-instruction
deadline-wait spin at 6C71** — the game busy-waiting for the next master tick
that only our own IRQ delivery can provide. Two slices:

1. **Deterministic wait-parking in the interactive clock** (the cookbook's
   timing fast-forward; pitfalls #12–14 respected — no state faked, every
   IRQ delivered at its scheduled point, wall-clock pacing untouched).
   `ancient/timing.py` grew `timer_wait_parked` (in-loop range detection,
   6C40..6C52 / 6C71..6C85, condition-gated) and `park_at_wait_head` (step
   to the canonical head — while the wait condition holds every iteration
   recomputes identical register state, so the head is a batch-size-
   independent, deterministic parking point; fails loud if the loop model is
   ever wrong). `scripts/play.py run_frame` now runs each IRQ sub-budget as
   "up to N steps, stop early parked at the head". Equivalence evidence:
   over 300 gameplay frames old-clock vs parked-clock, VRAM + back-buffer
   are byte-identical and DGROUP differs in exactly 3 bytes, all of which
   map into SS below SP (dead-stack IRQ-frame residue — the same class the
   hook verifier exempts). Demos recorded under the pre-parking clock are
   not replay-compatible (none were promoted; documented in run_frame).
2. **Game-agnostic interpreter micro-opts** (`dos_re/cpu.py`): inline
   non-planar code-fetch fast path in `fetch8`/`fetch16` (was two function
   calls per code byte), and `condition()` now tests only the asked flag
   combination (was: build a 16-element list evaluating every condition,
   5 `get_flag` calls, per branch instruction). **Bit-exact**: fixed
   300-frame run digest unchanged (3c16e9eb…); full suite green.

Measured on the gameplay snapshot (300 frames, chunk 40k, 60 Hz schedule):
| configuration | fps-equivalent | notes |
|---|---|---|
| before (pure ASM) | **11.0** | unplayably slow, 86% of steps in the spin |
| + wait-parking | **75.3** | 12.1M → 1.67M interpreted instr per 300 frames |
| + micro-opts | **79.1** | raw interpreter 280k → 481k steps/s (decompress path 1.7x) |

Pure-ASM gameplay is now above the 60 fps real-time target on this machine;
recovered hooks stack on top. Remaining known interpreter cost (future,
larger refactor, not this slice): `execute_opcode` builds disassembly
f-strings on every instruction even with trace off, and dispatches through a
long if-chain — a dispatch-table + lazy-trace refactor is the next big lever
if heavy scenes (level load ~50M steps) ever need it. PyPy is another
untested option (framework is stdlib-only by design).

## Next

1. Continue the lifting loop on the next hot leaf (profile_gameplay.py
   again from a fresh gameplay sample once more islands land — the DAT
   decompressor hot loop at 1010:6E11..6E97 during boot is still
   unrecovered and dominates cold-start time).
2. Confirm the DS:40C4 silhouette-list purpose (watch for a consumer read).
3. Record a first gameplay demo once the demo-clock unification (below) is
   done, so this island gets demo-corpus coverage, not just live-snapshot
   coverage (pitfall #6: a hook only counts as verified once a real demo
   exercises it).

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

## 2026-07-07 — framework grew a BIOS INT 09h keyboard handler (menu input fix)

- **Bug (owner-reported):** arrow keys dead in menus; Enter accepted but
  navigation didn't move. **Root cause:** the game's INT 9 ISR (1010:699E)
  keeps its own held-key table for gameplay but, for buffered input, **chains
  to the previous BIOS INT 9** (saved at DS:C0CC). Menus poll INT 16h, so
  arrows must arrive as BIOS extended codes (AL=0, AH=scancode). Our power-on
  INT 9 vector was a bare IRET stub → chained keys never entered the type-ahead
  buffer. (Non-special keys always chain; special keys chain only when the
  game's DS:0B72 buffer-route flag is set — menus on, gameplay off. So the fix
  needs no game knowledge: a real BIOS handler at the chain target.)
- **Fix (framework, game-agnostic):** `dos_re` now installs a native BIOS
  INT 09h keyboard handler (`DOSMachine.bios_int9_keyboard`) at
  `runtime.BIOS_INT9_ENTRY` (F000:E987); IVT[9] points there at power-on so the
  game saves & chains to it. It does standard set-1 scancode→buffer translation
  (shift/caps, extended nav/F-keys as scancode<<8) into `key_queue`. All
  drivers that call `deliver_scancode` now get consistent buffered input — this
  also closes a latent §6 gap (the frame verifier/replay path never enqueued
  before). Added to the adapter's `REFERENCE_ENV_HOOKS` so the oracle keeps it.
- **Adapter:** `ancient/keys.py` simplified (no manual key_queue push — the
  chain does it, faithfully). `load_game_snapshot` repairs pre-fix snapshots
  whose saved INT9 vector (DS:C0CC) still points at the old stub.
- **Proven:** down-arrow moves the sign-in highlight (Start New Game → Viktor)
  via the real ISR chain; Enter advances screens; unit tests
  `tests/test_bios_keyboard.py` (translation, shift, buffer bound, install);
  full suite 122 green. Cached intro snapshot regenerated with the new vector.
- **Still open:** menu text renders red (index 4) but should be black — logged
  in blockers.md (separate root cause; reference port confirms black).

## 2026-07-07 (later) — red menu text fixed (file-handle table overrun)

- **Bug (owner-reported):** menu/list text drew red; should be black (reference
  port confirms black). **Root cause (a second VM bug):** the game keeps a
  per-file-handle table at DS:38CC (`[bx+38CC]=open_flags|0x8000`, bx=handle*2).
  Our DOS handle allocator used a monotonic counter with no reuse, so boot
  asset-loading pushed handles to 28+; handle 28's slot is DS:3904[0] — the
  text-colour table — so the handle table overran it, writing 0x8004 (mode-4
  flags) over colour indices 0..8. Every menu glyph then drew in colour 4 (red).
- **Fix (framework, game-agnostic):** `DOSMachine._alloc_handle` returns the
  lowest free handle (>=5) and reuses closed ones, like real DOS. Handles now
  stay <=~13; DS:3904 stays identity. Fresh sign-in renders **black** text
  (evidence: artifacts/snap_signin_fixed/frame.png). Test:
  `test_file_handles_reuse_lowest_free_slot`. blockers.md updated (RESOLVED).
- Both owner-reported issues (dead arrows, red text) were VM bugs, now fixed.
  Owner confirmed reaching real gameplay next session (2026-07-08); see the
  "first recovered island" entry at the top of this file for what followed.
  Still open from this era: AdLib in-game confirmation (Options F3, DS:1778
  write site) and demo-clock unification (play.py's chunked clock vs the
  frame verifier's wait-head clock) — both carried forward, see "Next" above.

## Blockers

None open — see blockers.md.

## 2026-07-08 — reusable pieces promoted to the upstream framework

Everything game-agnostic this port produced was ported to the original
framework repo (D:\Games\DOS\dos_re, five commits 13dd527..4bed49b): the
three AEPROG-driven BIOS/DOS services (INT10 AH=1Ah, INT15 AH=C0h, INT21
AX=4400h), the lowest-free-file-handle fix (the red-text overrun class),
the native BIOS INT 9 keyboard handler + IVT[9] wiring, the real-mode fetch
fast path + single-condition Jcc evaluation, the audit_hook_oracle
GenericHookStop fix, and the vendor-test tracked-artifact fix.

Cross-validation both ways: a 300-frame Ancient Empires gameplay run under
the upstream core produces a full-memory SHA-1 **identical** to our vendored
core (3c16e9eb…) — and runs ~11% faster (87.8 vs 79.1 fps-equivalent),
because upstream's own parallel work (lazy trace strings, hot-opcode
reorder, from its SimAnt/Win16 target) stacks with our ports.

**Recommended follow-up:** re-vendor dos_re/ from upstream into this repo to
pick up that extra ~11% (plus PUSHA/POPA, CMC, selector mode, x87 subset for
free). The digest cross-check above is the safety evidence; do it as its own
slice with the full suite + a fresh digest check as the gate.
