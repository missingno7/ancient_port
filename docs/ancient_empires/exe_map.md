# AEPROG.EXE map — routines and data-segment variables

The hook/state-mirror reference for `dos_re`. Addresses follow the source
project's flat disassembly of the loaded image; `DS:xxxx` file offset =
`0x200 + 0xFA30 + xxxx`. All entries below were traced in the disassembly.

## EXE facts

- Plain MZ, not packed. MZ header `0x200` bytes. DGROUP = paragraph `0x0FA3`
  (recoverable as the first relocated word: 16-bit word at loaded-image
  offset 1).
- VGA DAC palette (768 bytes, 6-bit) at `DS:011E`.
- OPL FM patch table at `DS:301A` (56 bytes/patch); working copies `DS:3044`.
- Answer-puzzle question records at `DS:0DCC` (40 × 24 bytes).
- Menu strings: `DS:0DBA` "Help F1", `DS:0E20` "File F2", `DS:0EC3`
  "Options F3", dialog item strings contiguous after.

## Core loop / timing

| Address | Role |
|---|---|
| `0x6BCF` | Timer ISR — PIT reload `0x13B1` → ~236.69 Hz; calls sound tick `0xC1A0` |
| `0x69F5` | Keyboard IRQ handler (own key state; `0x4B` left, `0x4D` right, `0x48` up/action) |
| `0x3A75` | Main player loop |
| `0x3AA5` | Reschedules player loop after `0x18` (24) master ticks |
| `0x6B4A` / `0x6B1A` | Keyboard poll wrappers |
| `0x5593` | Wait-for-key helper (menus) |
| `0x7932` / `0x7964` | Generic selectable-list (menu/dialog) engine |

## Rendering

| Address | Role |
|---|---|
| `0x3CC` → `0x1A98` | Transparent blitter (logical colour 0 keyed), pure top-left |
| `0x3C9` → `0x1930` | Opaque block-copy blitter |
| `0x2BC0` | Backdrop blit (AE001 resource `30 + region`), blue clear = VGA index 1 |
| `0x2BF7` | compact3 background decor pass (`code >= 0x80`) |
| `0x2C71` / `0x2CCF` | Terrain tile loop / rope tiles inside it |
| `0x2D3E` | compact3 foreground decor pass (`code < 0x80`) |
| `0x28AC` | Static moving-platform draw + `0x07` footprint write (anchor `x_raw*2−4, y+0xB4`) |
| `0x2E32` | Header diamond/artifact pickups |
| `0x2E89` | Room-gated apple (runtime `room[0x3E5..0x3E7]`) |
| `0x2F10` | Control buttons/switches/triggers draw (pressed art `0x9B6E` vs `0x9AE0`) |
| `0x3085` | Puzzle symbol draw (symbol overlay +4 px X) |
| `0x3132` | Green blocks draw |
| `0x4EF8` | Actor draw loop (vertical base `0xB8` via `0x399A/0x399E`); `0x4F33` sprite, `0x4F39` spider-thread line |
| `0xD61C` | Laser crystal draw |
| `0xD586` | Animated-decor refresh (12-byte after-visual table) |
| `0xD81C` / `0xD99C` | 4-byte animated-decor record handlers |
| `0x21A9` | Startup font load (resources 0, 1) via `0x68AA` |
| `0x6CA6` / `0x6CF6` / `0x6D3C` / `0x17A4` | select_font / measure_string / draw_string / glyph blitter |
| `0x656C` | Resource fetch (`0xF348` decompress) |
| `0x5321` | Map/menu subimage compositor |

## Gameplay

| Address | Role |
|---|---|
| `0x1F17` / `0x1F91` | Horizontal / vertical tile-span collision probes |
| `0x3DC1..0x3E60` | Horizontal walk branches |
| `0x3E60..0x3F85` | Ladder climbing |
| `0x410C..0x4137` | Normal jump (counter 5, SFX `0x0C`) |
| `0x40B3..0x40D8` | High jump (counter 8, SFX `0x10`) |
| `0x408A` | Boots jump |
| `0x4240..0x4372` | Edge room transitions |
| `0x438C/0x4396/0x43A0/0x43AA` | Left/right/up/down room-link arrays (10 bytes each, 1-based) |
| `0x4517` | load_room (early-out when `DS:073C` == room) |
| `0x3B05` / `0x3C50` | Walk-onto-button probe path (`0x3C67` excludes command-2) |
| `0x1D89A` | Object-box list probe (player body box `X/2+1, Y+1, 14×39`) |
| `0x32FA` / `0x338A` | Control terrain-effect toggle / control activation (also referenced as the moving-platform per-frame redraw entry) |
| `0x36F0` | Control-object collision handler (SFX `0x0A`) |
| `0x4B0C` | Player-vs-actor box tests |
| `0x4CFA` / `0x4CEF` | Actor VM opcode `0x08` (trigger control) / opcode `0x07` (play_sound → CAF1) |
| `0x4C7A`, `0x4B39/0x4B70` | Actor freeze on laser hit, freeze countdown |
| `0x5A3B` / `0x5AC3` | Laser start / per-tick updater (8×1-px substeps) |
| `0x5C07` / `0x5C2F..0x5C67` | Reflector 4-px cadence gate / jello-lever object probe |
| `0x5F3C` / `0x6036` | Reflector sprite-nibble classifier / 30×30 broad-phase box |
| `0x60A9` / `0x60D2` / `0x6181` | Self-rotate tick / `0x80` rotation flag / controlled reflector step |
| `0x5D80` | Beam-tail countdown after head death |
| `0x3CC8..0x3D13` | Exit-door activation (x±2, y..y+16, Up held) |
| `0x233E` / `0x249F` | Level-transition door animation (SFX `0x0D`) |
| `0x471A..0x473C` | Player runtime X/Y init from header `0x03/0x04` |
| `0x7277` / `0x727D` / `0x7313` | Get tool / cycle tool (Enter) / immortality count decrement |
| `0x41FA` / `0xBE67` | Immortality activation (timer `DS:072C = 0x3A`, SFX `0x00`) |
| `0x8DA4` / `0x8FE2` / `0x950C` / `0x969D` | Artifact puzzle take/drop/redraw/validate |
| `0x9B68..0x9D78` / `0x9DCC` / `0x9A0E` | Answer puzzle init / door check / symbol draw |
| `0x904C` | Puzzle-success fanfare (SFX `0x1B`) |
| `0x6FCA/0x6FDA/0x7202/0x7298/0x7417/0x7443` | HUD load/frame/artifacts/tool/region/cavern draws |
| `0x56C6` / `0x55C7` / `0x5708` / `0x576A` | Map screen resource load / pointer tables / music prep (`0xD5BA`) / music start (`0xD5F9`) |

## Audio routines

| Address | Role |
|---|---|
| `0xC1A0` | Sound tick (from timer ISR) |
| `0xC1F7` | Music stream advance (no per-event read tick) |
| `0xC27D` | Music note gate / device dispatch (calls `0xC440` only for device 1) |
| `0xC440` | PSG envelope/vibrato updater |
| `0xC5B3` / `0xC5C6` | `5D` / `6D` control handlers (PSG state at `17C4/17DC`) |
| `0xC5EA` / `0xC64A` / `0xC6C3` | note→block, note→semitone, FNUM tables |
| `0xC678` → `0xDB60` → `0xE48A` → `0xC898` | OPL melodic note-on chain |
| `0xC77A` | Device select (`DS:1778` → port `DS:1830`) |
| `0xC898` / `0xC8D4` | OPL two-port register writer / SN76489 single-port writer |
| `0xC8E2` / `0xC914` | SFX stream advance (per-event read tick: each event = duration+1 ticks) |
| `0xC9A4` | Note/rest duration decode (bit `0x80` = full base duration) |
| `0xCA03` | `?D` control dispatch |
| `0xCA9B` | `?E` direct-pitch (PIT divisor from `DS:17FC` base `0x8E88`) |
| `0xCADB` / `0xCAE6` / `0xCAD0` | Speaker off / PIT ch.2 write / speaker gate on |
| `0xCAF1` | `play_sound(id)` — CAF1, lower id = higher priority |
| `0xD935` / `0xDA66` / `0xE0C0` / `0xE1C4` | OPL instrument upload chain (per-voice shadow `DS:C91B`) |
| `0xE1F2` | Total-level flush with per-voice runtime volume |
| `0xD8F0` | patch pointer = `DS:301A + id*0x38` |
| `0xDEFA` / `0xDE7E` / `0xDDD9` | Pitch-table preparation |
| `0xD5BA` / `0xD5F9` | Music prep/start by resource id |
| `0x58DB` / `0x5965` / `0xB820` | Hardcoded loop-flag users (`DS:1774`, sounds `0x18`/`0x19`) |

## Data-segment variable map

### Player / gameplay

| DS | Meaning |
|---|---|
| `072C` | invulnerability timer (set to `0x3A`) |
| `072E` | player animation frame |
| `0730` | jump counter |
| `0734` | horizontal move amount |
| `0736` / `0738` | player X / Y |
| `073A` | facing |
| `073C` | currently loaded room (load_room early-out) |
| `0740` | jump delta table |
| `0B68` | held-Up key state |
| `0B7E` | selected tool (0..2) |
| `0B80` | immortality uses remaining |
| `BFBA` | current room index |
| `4374` | runtime copy of level part (first `0x2750` bytes) |
| `B3AE` | runtime actor table (count + 0x20-byte records) |
| `BFC0` | runtime control records |
| `BFDE` / `BFE2` / `BFE6` | map-screen resource pointers (res `0x34`/`0x38`/`0x37`) |

### Laser

| DS | Meaning |
|---|---|
| `08FE` | laser active flag |
| `0900` | 12-way direction/dither rows |
| `0A20` | reflector self-rotate countdown (reset 10) |
| `C04E` | ring index (init `0x17`) |
| `C050..C07F` / `C080..C0AF` | 24-slot X / Y coordinate rings |
| `C0B0` | dither-table phase |
| `C0B6` | reflector collision latch |
| `C0B8` | direction row (3 right, 9 left) |
| `C0BE` | pending jello/lever trigger |
| `C0C0` | inactive-tail countdown (init `0x18`) |
| `C0C2` | reflector runtime frame (`& 0x1F`) |

### Puzzles

| DS | Meaning |
|---|---|
| `0DCC` | answer-puzzle question records (40 × 24 B) |
| `C132` | held puzzle piece |
| `C316` | artifact-puzzle board (4×6 `(tile, orientation)`) |

### Audio

| DS | Meaning |
|---|---|
| `1770` | sound-busy wait flag |
| `1774` | SFX loop/retrigger flag |
| `1778` | configured sound device (1 PSG, 2 OPL, 3 port 0x205) |
| `1788` / `178A` | music global base-duration / bend (shared across channels) |
| `17C4` / `17DC` | per-channel PSG envelope state |
| `17FC` | PIT divisor table (first word `0x8E88` = `?E` base) |
| `1830` | active sound port |
| `1E84` / `1E86` | CAF1 base duration / bend |
| `1E88` / `1E8A` | active SFX stream pointer / active sound id |
| `1E8C` | phrase/envelope state (duration arg bit `0x10`) |
| `1E8E` | gate cutoff threshold (init 6) |
| `1E90` | remaining ticks |
| `1E92` | `?E` direct-pitch duration (init 1) |
| `1E94` | gate enabled state |
| `301A` / `3044` | OPL patch ROM / working patch bank |
| `C6AB..C6AD+` | per-voice enable flags |
| `C91B` | per-voice OPL register shadow (14 B/voice) |
| `CA62..` | nine per-voice pitch offsets (from music header `0x11..0x19`) |

### Text / video

| DS | Meaning |
|---|---|
| `011E` | VGA DAC palette (768 B) |
| `40C8` | current text colour |
| `C0DE` | glyph bitmap base |
| `C0E0` / `C0E2` / `C0E4` / `C0E6` | font segment / offset-lo / width / offset-hi pointers |
| `C0E8` / `C0EA` | line height / current font index |

## Caveats

- `0x338A` appears in the source notes both as "activate control" and as the
  per-frame moving-platform redraw entry; treat the exact split as
  to-be-confirmed when hooking.
- `0x1D89A` is written with five hex digits in the source notes (likely a
  flat/linear address); confirm segment:offset when placing a hook.
