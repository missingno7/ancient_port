# Gameplay logic recovered from AEPROG.EXE

Status: everything here is disassembly-traced; items the source project ported
and regression-tested are marked *(ported)*. UNPROVEN items flagged inline.

## Main player loop — `0x3A75`

Polls the BIOS-wrapper keyboard reads `0x6B4A/0x6B1A`, then updates:

| Var | Meaning |
|---|---|
| `DS:0736` | player X (full pixels) |
| `DS:0738` | player Y |
| `DS:073A` | facing direction |
| `DS:072E` | animation frame |
| `DS:0730` | jump counter |
| `DS:0734` | horizontal move amount (normally 4 px) |
| `DS:0740` | jump delta table |

`0x3AA5` schedules the next player-loop run after `0x18` (24) master ticks —
gameplay advances at ~9.862 Hz.

Keyboard ISR ~`0x69F5`: scancode `0x4B` = left, `0x4D` = right, `0x48` =
shared action/jump (up), Home/PgUp = diagonal + action. Enter (`0x0D`) cycles
the tool; Space uses it. `DS:0B68` holds the held-Up state.

### Walking *(ported)*

Horizontal branches `0x3DC1..0x3E60` move by `DS:0734` after collision query
`0x1F91`. Player frames 0..11 for ordinary walking; Explorer player sprites
are `AE000:004`.

### Collision probes `0x1F17` / `0x1F91` *(ported)*

`0x1F17` ORs a horizontal tile span; `0x1F91` ORs a vertical tile span. Both
derive the cell **count** from the un-offset coordinate (`cap − x/8 + 1`) but
index from the border-shifted start (`x/8 − 1`, `y/8 − 2`) — the same border
shift must be applied to the span **end**, otherwise the vertical probe bleeds
two rows into the floor and blocks all walking (the port hit this bug).

### Jumping *(ported)*

- Grounded jump `0x410C..0x4137`: jump counter **5**, frame 9, SFX `0x0C`.
- Alternate/high jump `0x40B3..0x40D8`: counter **8**, SFX `0x10`.
- Jump delta table `DS:0740`: normal jump consumes `8, 8, 8, 4, 2` px.

### Ladders `0x3E60..0x3F85` *(ported)*

With Up held, probes the ladder column at `x + 0x10 − facing*4` via `0x1F91`;
first grab snaps onto the ladder centre, then ascends 4 or 2 px/tick. Down
while on a ladder (`0x3F41`) descends 4 px until it ends. Climb frames
alternate `0x14/0x15`, move amount becomes 8; the `or si,si` test at `0x3F85`
makes climbing bypass jump and gravity branches.

## Room transitions — `0x4240..0x4372` *(ported)*

Current room = `DS:BFBA`. Four 10-byte one-based link arrays (`0x438C` left,
`0x4396` right, `0x43A0` up, `0x43AA` down; 0 = none) decide edges. Crossing a
linked edge swaps rooms and re-enters from the opposite side:
`x=0x120` entering from left, `x=0` from right, `y=0x90` from top, `y=0` from
bottom; without a link the player clamps at the boundary.

**Room state persists**: `load_room` (`0x4517`) returns early when `DS:073C`
already equals the requested room — a room is initialised only on first entry;
revisits resume paused state. All rooms' actors/controls live in one
persistent table.

## Controls: buttons, switches, levers *(ported)*

Records at `DS:BFC0` (`+1` command, `+2` x, `+3` y, `+4` pressed). Two real
activation paths — there is **no** generic sprite-overlap toggle:

1. **Walk-onto-button** (`0x3B05/0x3C50`): each frame the player loop probes
   the object-box list (`0x1D89A` in the project's disassembly numbering) with
   the player body box (`x = X/2 + 1`, `y = Y + 1`, `w = 14`, `h = 39`);
   control records appear with code `index + 8`. When the probed code
   *changes* (debounced), `0x338A` toggles the control — **buttons only**
   (command 0/1). Command-2 levers are explicitly excluded (`0x3C67`).
2. **Actor-VM trigger** (`0x4CFA`): a trigger-zone actor's script reaches
   opcode `0x08`, gated by player-position conditions `0x17..0x1A`, and calls
   `0x2A2D/0x338A` for a control index. Floor "levers" are trigger-zone
   actors; their hitbox is the actor's frame bounds, not the control record.

`0x32FA` applies a control's terrain effect (XOR bit `0x10` on tiles).
Active controls on one target combine by parity/XOR.

## Tools (Enter cycles `DS:0B7E`, Space uses) *(laser & boots ported)*

| Tool | Index | HUD sprite | Space action |
|---|---|---|---|
| Flashlight/laser | 0 | AE000:063:3 | fire laser (`0x5A3B`), SFX `0x14` |
| Jumping boots | 1 | AE000:063:4 | grounded high jump: counter 8 (~48 px vs normal ~24), SFX `0x10` (`0x408A`) |
| Immortality | 2 | AE000:063:5 | 4 uses/level (`DS:0B80`, HUD `AE000:063:6..10`); decrement via `0x7313`, sets invuln timer `DS:072C = 0x3A`, SFX `0x00`; empty → SFX `0x11` |

`0x727D`: Enter increments `DS:0B7E`, wraps at 3, redraws the HUD tool sprite
at (152, 166). `0x7277` returns the selected tool.

## Laser / headlamp beam (fully traced, *ported*)

Start `0x5A3B` (only when `DS:08FE` clear; else SFX `0x17`):

- seeds two 24-slot (`0x18`-word) coordinate rings `DS:C050../DS:C080..` with
  `(player_x + 0x10, player_y + 4)`; ring index `DS:C04E = 0x17`; direction
  row `DS:C0B8` (3 = right, 9 = left); inactive-tail countdown `DS:C0C0 =
  0x18`; sets `DS:08FE = 1`.
- **No instant beam**: the updater `0x5AC3` advances only **eight 1-pixel
  substeps per tick** through the ring — the visible laser is a short 1-px
  yellow line moving through space. `DS:C0C0` is not a range limit: it only
  counts down (`0x5D80`) after the head dies. Range is bounded by solid
  terrain, room edge, or collision.
- Room edges checked every pixel; solid terrain only when the head crosses an
  8-px tile boundary.
- **Object probe** (`0x5C2F..0x5C67`): fires at the sampled point *before* the
  solid-tile kill at the same point (matters for beams reflected back into a
  sensor). Converts full-pixel X to raw-X space with `x >> 1` for both
  directions. Command-2 jello/levers use a registered box of 8 raw-X units ×
  16 px. One pending trigger (`DS:C0BE`) then `SI` cleared — a single beam
  toggles a lever **once**; the visible trail must not retrigger.
- **Actor freeze** (`0x4C7A`): copies actor byte `+0x09` into freeze timer
  `+0x0A`; actors with `+0x09 == 0` (projectiles) don't freeze; frozen actors
  skip their script and count down at `0x4B39/0x4B70`.
- **Reflectors** (object codes `0x30..0x4F`): the classification branch runs
  only when `(substep_counter & 3) == 0` (4-px cadence, `0x5C07`). `0x5F3C`
  does pixel-precise triangular-face classification: subtract the raw section-C
  anchor (`local_x = laser_x − x_raw*2`, `local_y = laser_y − y`), index the
  30×30 packed 4-bpp sprite nibble; only specific logical colours reflect —
  normal branch colours `2/3/4` → classes `1/2/3`, alternate branch
  `0x0B/0x09/0x08` → same classes; transparent pixels inside the 30×30
  broad-phase box (0x0F raw-x × 0x1E px, `0x6036`) return class 0.
  New direction = `frame − old_dir`, `frame − old_dir − 8`, or
  `frame − old_dir + 8`, normalised into the 12-way rows at `DS:0900`; SFX
  `0x0F`. Collision latch `DS:C0B6` prevents reclassifying the same reflector
  while inside its box; the dither phase `DS:C0B0` is preserved across
  reflection. Runtime frame masked `0x1F` (`DS:C0C2`).
- Reflector rotation: `code & 0x80` self-rotating — `0x60A9` returns while a
  laser is active, else decrements `DS:0A20`; at zero resets to 10 and steps
  all `0x80` reflectors one frame. `code & 0x40` reverses step direction.
  Controlled reflectors step per `R`-target trigger (`0x6181`).

## Exit door and level exit *(ported)*

Normal exit activation (`0x3CC8..0x3D13`): the door object registered at
`(header[0x06]*2, header[0x07])`; the player anchor must be within **x ± 2 px**
and y within `y..y+16` (much narrower than the 46×33 artwork — prevents rope
false-positives), gated by held-Up `DS:0B68`. `0x233E` opens the themed door,
plays player frames `AE000:004:12..15`, closes it behind the player.

## Ancient-Artifact puzzle (after collecting all pieces) *(ported)*

- Panel background `AE001:063`; artifact image/title
  `AE001:(65 + chamber + region*8 + (4 if Expert))`; title blitted at
  (140, 44); `AE001:064` = Explorer/Expert instruction bands.
- Board at `DS:C316`: 4 rows × 6 columns of `(tile, orientation)` cells;
  columns 0..2 loose pieces, 3..5 assembly target.
- `0x8DA4` picks a cell into `DS:C132` (SFX `0x0E`), `0x8FE2` drops it back
  (SFX `0x1A`), `0x950C` redraws the held piece at the cursor.
- Explorer: no flipping. Expert: `F` cycles held orientation.
- `0x969D` validates one of four orientation/order patterns; success plays
  SFX `0x1B` and reveals the exit door.

## Exit-door answer puzzle (between levels) *(ported)*

- Odd progression stages load `AE001:020` — a special `0x2750`-byte room
  resource whose first room holds terrain/tiles/rope. Room frames
  `AE001:030..033` selected by theme. Symbols from bank `AE001:034`
  (182 monochrome 40×29 glyphs).
- Question definitions are **embedded in the EXE at `DS:0DCC`**: 40 records ×
  24 bytes (Explorer 0..19, Expert 20..39). Each record: eleven
  `(symbol, transform)` pairs, allowed-missing-cell bitmask at `+0x16`,
  first-wrong-answer hint resource at `+0x17`.
- Init `0x9B68..0x9D78`: picks the allowed missing cell, draws a question mark
  (symbol 145), randomises the correct answer among door positions 9..11,
  fills the other doors from record slots 9 and 10.
- The player traverses the room with the ordinary movement loop (terrain
  collision, rope climbing). The object-collision loop passes the entered door
  index to `0x9DCC`; only a positive result reaches the level-transition
  animation `0x233E`.

## HUD *(ported)*

- `0x6FCA` loads resource `0x3F` (`AE000:063`); `0x6FDA` blits HUD sprite 0 at
  (6, 162).
- `0x7202` draws collected artifact segments (`AE000:063:1`) from (16, 176),
  +18 px per piece.
- `0x7298` selected tool sprites 3..5 at (152, 166).
- `0x7417` region sprites 11..15 at (244, 175); `0x7443` cavern sprites 16..19
  at `(244 + cavern*16, 186)`.
- `0x471A..0x473C` initialises player X/Y from header bytes `0x03..0x04`.
- Most HUD labels are pixels in `AE000:063`, not font text.
- Level naming: level index N → region `N/4`, chamber `N%4`
  (Near East, Egypt, Greece and Rome, India and China, Ancient World; I..IV).

## Menus, dialogs, map screen

- Menu-bar labels are plain strings in DGROUP: `Help   F1` at `DS:0DBA`,
  `File   F2` at `DS:0E20`, `Options F3` at `DS:0EC3`; dialog item lists
  (`Hall of Fame`, `Start New Game`, …) contiguous after, reached via
  far-pointer tables. Highlighted rows invert text colour `DS:40C8`.
- Difficulty dialog: `Which Level of Difficulty?` with rows `Explorer/Expert
  Level of Difficulty`; selection maps directly to part index 0/1. *(ported)*
- Map screen: `0x56C6` loads resources `0x38`/`0x37` into `DS:BFE2/BFE6`,
  `0x55C7` builds pointer tables (resource `0x34` → `DS:BFDE`), `0x5708`
  prepares AE000 resource `0x35` and `0x576A` starts its music
  (AE000:049/050 pair). Backing image AE000:026, map AE000:028, region icons
  AE000:029..032 (033..036 completed), selector AE000:037. Composite draws via
  `0x5321` with offsets from `DS:BFE2` (`+0x0344`, `+0x0498`, `+0x05FA`,
  `+0x066C`). Generic selectable-list engine at `0x7932/0x7964`; key waits
  `0x5593/0x6B1A`. Capture alignment: 12-px black margins top/bottom — port
  composites AE000:026 at (0,12), AE000:028 at (5,15). *(ported)*
- Note: map-flow "resource `0x34`" is AE000:034 (a small `0x47` image) — a
  different thing from AE001:034 (answer-symbol bank).

## Not yet recovered (UNPROVEN / open)

- Complete lives/damage/hazard response, collectible/inventory schema.
- Exact moving-platform motion table and player/platform coupling.
- Conveyor effect on the player (tiles + CV records are decoded; player
  physics coupling not traced).
- The F1/F2/F3 menu-state machine and dialog border draw (fonts and strings
  are fully traced).
- Exact per-frame animated-decor draw order (`0xD586/0xD81C/0xD99C`).
