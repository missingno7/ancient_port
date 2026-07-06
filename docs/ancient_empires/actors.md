# Actor system: table, records, script space, VM

Status: record layout and opcode set **CANONICAL** (round-trip
assembler/disassembler over all stock data + working simulation); event-id
semantics as flagged.

## Actor block

Each level part ends with a 3000-byte (`0x0BB8`) actor block at part offset
`0x2754`, copied at runtime to `DS:B3AE`:

```text
+0x000        count (byte)
+0x001..      count × 0x20-byte actor records
...           shared actor bytecode space (one per part, NOT per actor)
```

**Script space is shared.** Actor records are instance/state objects holding
entry pointers into one common bytecode region. Two actors can point at the
same address; scripts can jump into non-entry-point code. Model reachability
("reachable from A5"), not ownership.

## Actor record — 0x20 bytes

| Offset | Field |
|---:|---|
| `0x00` | mode/type — `0` runs, `1` sleeps (secondary actors/projectiles start at 1) |
| `0x01` | zero-based room index |
| `0x02..0x03` | X, 16-bit LE — **full resolution**, not the halved raw-x of payload objects |
| `0x04..0x05` | Y, 16-bit LE |
| `0x06` | current frame |
| `0x07` | frame variant / horizontal-flip bit |
| `0x08` | hidden / start-state |
| `0x09` | delay — also the **laser freeze duration** copied into `+0x0A` when a beam hits (`0x4C7A`); records with `0x09 == 0` (projectiles) cannot be frozen |
| `0x0A` | cooldown / freeze timer (counts down at `0x4B39/0x4B70`; frozen actor skips its script) |
| `0x0B` | frame range min |
| `0x0C` | frame range max |
| `0x0D..0x0E` | `script_pc` (entry pointer into shared script space) |
| `0x0F..0x10` | `saved_pc` (call return slot) |
| `0x11..0x12` | loop counter A |
| `0x13..0x14` | loop counter B |
| `0x15..0x16` | loop counter C |
| `0x17..0x18` | `restart_pc` — separate entry used by death/collision cleanup, **not** the normal wake address |
| `0x19` | contact behaviour |
| `0x1A` | vertical marker — **current spider-thread length**; the draw loop (`0x4F39`, after the sprite blit at `0x4F33`) draws a 1-px VGA colour `0x0F` line at `x+16` from `y−value+1` to `y`, anchored at the spawn position; nonzero in stock data = "has thread" |
| `0x1B` | activated flag |
| `0x1C..0x1F` | runtime tail/state |

Draw/update loops filter by `rec[0x01] ==` current room and use
`0x02/0x04/0x06`.

Confirmed frame families include: ant, bat, green spitter, ladybug, scorpion
shooter, spider, snake, praying mantis, plus projectile/secondary actors
(fireball, energy orb, pill projectile, sparkles).

## Timing

Master timer ~236.69 Hz (PIT reload `0x13B1`). **Actor scripts advance once
every 24 master ticks** (~9.862 actor ticks/s). The player loop reschedules at
the same 0x18-tick cadence.

## Actor VM

Bytecode dispatched from the per-actor `script_pc`. Observed opcode range in
all stock data: `0x00..0x1B` **excluding `0x06`** (loop C is defined but
unused in shipped levels).

| Op | Size | Mnemonic / semantics |
|---:|---:|---|
| `0x00` | 1 | `yield` — end current tick (all-zero tails are padding) |
| `0x01` | 3 | `jump rel16` |
| `0x02` | 3 | `call rel16` (stores return in `saved_pc`) |
| `0x03` | 1 | `return` from `saved_pc` |
| `0x04` | 5 | `loop_a rel16, count16` — counted loop using record counter A |
| `0x05` | 5 | `loop_b rel16, count16` |
| `0x06` | 5 | `loop_c rel16, count16` (defined; unused in stock data) |
| `0x07` | 2 | `play_sound id` — calls CAF1 (`0x4CEF..0x4CF3`) |
| `0x08` | 2 | `trigger_control id` — activates control record by index via `0x338A` (handler `0x4CFA`) |
| `0x09` | 2 | `emit_symbol id` — **zero-based** raw id; runtime signal = `raw + 1` (raw 0 → `S1`) |
| `0x0A` | 2 | `set_actor_mode_1 ref` — put referenced actor to sleep |
| `0x0B` | 2 | `set_actor_mode_0 ref` — wake referenced actor (its stored PC runs) |
| `0x0C` | 3 | `set_frames min, max` — frame range |
| `0x0D` | 2 | `set_frame packed` — bit 7 = variant/flip, low 7 = frame |
| `0x0E` | 4 | `move dx, dy, frame_delta` — signed deltas; frame_delta bit 7 = variant |
| `0x0F` | 4 | `move_to x_raw, y, frame_delta` — x = `x_raw*2` |
| `0x10` | 5 | `move_to_room x_raw, y, packed_frame, room` |
| `0x11` | 1 | `hide` (and yield) |
| `0x12` | 1 | `show` |
| `0x13` | 3 | `if_tile_solid offset16` — runtime tile `& 0x07` non-zero |
| `0x14` | 3 | `if_tile_passable offset16` — runtime tile `& 0x07` zero |
| `0x15` | 3 | `if_conveyor_grey offset16` — tile `& 0x10` clear |
| `0x16` | 3 | `if_conveyor_teal offset16` — tile `& 0x10` set |
| `0x17` | 2 | `if_player_x_gt x_raw` (compares `player_x > x_raw*2`) |
| `0x18` | 2 | `if_player_x_lt x_raw` |
| `0x19` | 2 | `if_player_y_gt y` |
| `0x1A` | 2 | `if_player_y_lt y` |
| `0x1B` | 2 | `if_random_lt threshold` |

### Condition model (proven over every stock script)

Condition opcodes `0x13..0x1B` guard **exactly the one immediately following
command**: true → it executes; false → it is skipped and execution continues
after it. The guarded command is usually `jump`/`call` but stock data also
guards `yield`, `set_frame`, `return`, `set_actor_mode`. Do not model these as
free-form skip records.

### Branch targets

Relative branches (`0x01`, `0x02`, `0x04..0x06`) are relative to the **next
instruction**.

### Runtime tile offsets

Tile-condition offsets (`0x13..0x16`) index the room terrain **runtime
buffer**, whose x origin is **two tile columns left** of the visible room:
visible `(x, y)` in room r → runtime offset for buffer x = `x − 2`. (Known
anchor: room 1 visible tile `(14,3)` = runtime offset `0x04A8`.) The runtime
buffer reflects moved `0x07` footprints of platforms and green blocks, so
actor branches see live collision.

### Projectile lifecycle pattern (stock data)

Shooters wake a hidden projectile with `set_actor_mode_0`; the projectile ends
itself with `set_actor_mode_1` + `hide`, leaving its PC parked at the dormant
`script_pc`. `restart_pc` is used by cleanup/death paths.

### Player interaction

`0x4B0C` tests the player's box against each actor in the `DS:B3AE` table; a
triggered trigger-zone actor runs its script (which typically reaches opcode
`0x08` gated by `0x17..0x1A` player-position conditions). Command-2 levers are
activated only through this path (and the laser), never by walking.

## Open items (UNPROVEN)

- Event-id *names* for `0x07/0x08/0x09` are semantic labels still being
  confirmed case-by-case; the structural shape (op + one id byte) is proven.
- Cycle-exact VM timing beyond the 24-tick cadence.
- Any opcode above `0x1B` (never observed; treat as invalid).

## Editing rules that keep files valid

- Deleting an actor must not delete its script bytes (may be shared/reached).
- Refuse deletion while `set_actor_mode_*` references the actor.
- Any script length change is a repack: all entry pointers and relative
  branches must be fixed up.
