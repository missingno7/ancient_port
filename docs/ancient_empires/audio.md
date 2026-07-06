# Audio: PC-speaker SFX, music bytecode, OPL/PSG synthesis

Status: **CANONICAL** — ASM-traced and verified against DOSBox-X DRO captures
and real-game recordings; the port's decoder is capture-accurate.

## Ground truths

- **There is no PCM/sample audio anywhere in the binary.** Confirmed three
  ways: all 62 `out` instructions target OPL/PSG/PIT/speaker or VGA register
  ports; there are no Sound Blaster DSP ports (`0x226/0x22A/0x22C/0x22E`) and
  no DMA programming; the timer ISR (`0x6BCF`, ~236.69 Hz, PIT reload
  `0x13B1`) only calls the sound tick `0xC1A0` — no sample-rate DAC loop.
  "Sampled-sounding" drums are high-feedback FM.
- Devices (`0xC77A` switches on config `DS:1778`, active port `DS:1830`):
  `1` = Tandy/PCjr SN76489 PSG at port `0xC0` (single-port writes `0xC8D4`);
  `2` = AdLib/OPL2 (YM3812) — patches uploaded via `0xD99B`;
  `3` = port `0x205`, then falls back to the PSG-style branch (not PCM).
- The duration unit everywhere is the **master tick** (~236.69 Hz).

## Type `0x44` resources — three distinct kinds

| Kind | Description |
|---|---|
| PC-speaker SFX bank | `AE000:065` — the CAF1 `play_sound(id)` bank |
| PC-speaker music | single-stream music, stream starts at offset `0x96` |
| Sound-card music | multi-channel; leading 16-bit words are channel/stream offsets, then a header/config area before stream 0 |

## Shared bytecode (music and SFX)

Streams are `[opcode][arg]` byte pairs. Low nibble of the opcode = command
kind; high nibble = parameter (octave / subcommand / shift):

```text
0x0       rest / speaker off
0x1..0xC  musical note (chromatic: note-1 + octave*12)
0xD       control command
0xE       direct PIT/effect pitch (SFX path)
0xF       terminator / loop endpoint
```

`?D` controls:

```text
0D xx   gate cutoff: 0 disables; >0 sets threshold (SFX default 6)
1D xx   duration bend +round(base * xx/100)
2D xx   duration bend −round(base * xx/100)
3D xx   direct-effect (?E) duration in ticks (SFX default 1)
4D xx   base duration = xx * 4 ticks (SFX default 0x4B*4)
5D xx   PSG instrument/envelope selector (music)
6D xx   PSG auxiliary volume/timbre (music)
```

Note-duration decoding (`0xC9A4`): an argument with bit `0x80` set takes the
full-base-duration branch — it stores unchanged `base + bend` (it is **not**
`arg & 0x7F` literal ticks).

`5D/6D` feed the PSG envelope updater `0xC440`, which `0xC27D` invokes **only
for device 1** — they do not affect OPL playback.

## PC-speaker SFX engine (CAF1 = `0xCAF1`)

`play_sound(id)` reads `AE000:065`. The bank's first 16-bit words are
**relative offsets into the resource per sound id** (word 0 = `0x0096` =
offset of sound 0 — not a divisor).

- **Priority**: a new id is ignored if it is numerically **greater** than the
  currently playing id (`cmp di,[DS:1E8A] / ja skip`) — lower id = higher
  priority.
- Init state: gate cutoff 6 (`DS:1E8E`), `?E` duration 1 (`DS:1E92`),
  bend 0 (`DS:1E86`), remaining ticks 0 (`DS:1E90`).
- **Per-event read tick**: the SFX updater (`0xC8E2/0xC914`) fetches the next
  event only on a later tick that sees the counter at zero, so each SFX event
  occupies `duration + 1` ticks. The music player (`0xC1F7`) does **not** have
  this extra tick.
- `?E` direct pitch (`0xCA9B`): `arg == 0` → speaker off; else
  `divisor = ((base − (arg << 7)) & 0xFFFF) >> opcode_high_nibble`, programmed
  into PIT channel 2 (port `0x42`), gate via port `0x61`. The divisor base is
  the first word of the EXE table at `DS:17FC` = **`0x8E88`**.
- Loop layer: global flag `DS:1774` makes the `?F` terminator restart the same
  id instead of stopping (used hardcoded for ids `0x18` at `0x58DB/0x5965` and
  `0x19` at `0xB820`).

## Music playback

- Multi-channel music shares **global** base-duration/bend words
  (`DS:1788/178A`) across all channels — decode with synchronized stream
  cursors (channel 0 often carries the leading `4D 64` that every channel
  inherits); per-channel decoding drifts.
- Note gate: for non-PSG devices `0xC27D` decrements the live duration and
  cuts the note at the configured threshold — the short off-interval between
  notes is authentic, keep it in register traces.

## OPL (AdLib) pipeline — device 2

- **FM patch table embedded in the EXE** at `DS:301A`
  (file offset `0x200 + 0xFA30 + 0x301A = 0x12C4A`), **56 (`0x38`) bytes per
  patch**: two 13-word operator register blocks (operator block at patch
  `+0x1A`, stride 2) plus a 2-bit feedback/connection value and two waveform
  words; patch words `+0x34/+0x36` are the two operators' OPL base-register
  offsets.
- Each **music resource header** selects instruments:

  ```text
  0x00..0x07  leading stream/channel offset words
  0x08..0x10  nine OPL instrument ids (0xFF = voice disabled)
  0x11..0x19  nine voice config values = per-voice PITCH OFFSETS in semitones
  0x1A..0x22  nine per-voice levels
  ```

- Instrument upload (`0xD935` loop, per voice): copy patch to working bank
  `DS:3044`, override carrier total level at patch `+0x2A` with
  **`0x3F − level*9`**, upload via `0xDA66 → 0xE0C0 → 0xC898` into the
  per-voice register shadow at `DS:C91B` (14 bytes/voice), flushed by `0xE1C4`.
- Register writer `0xC898`: `out` reg → 6 settling `in`s → `inc dx` → `out`
  value → 35 settling `in`s (canonical OPL2 signature).
- **Voice stacking**: each of the 3 melodic channels drives up to 3 OPL voices
  (channel 0 → voices 0,1,2; etc.). `note_for_voice = stream_note +
  pitch_offset[voice]` (offsets from header `0x11..0x19`, e.g. AE000:054 uses
  `24,12,24, 0,0,12, 0,0,12` — octave stacks at full level are why the music
  sounds "deep"). Voice enable flags (`DS:C6AB+`) are set only when the id
  isn't `0xFF`.
- Pitch: `0xE48A` does no Hz math. `block = note / 12`, `semitone = note % 12`
  (tables `0xC5EA/0xC64A`), FNUM row at `0xC6C3` =
  `157 16B 181 198 1B0 1CA 1E5 202 220 241 263 287`; note index clamped to
  `0..0x5F`; writes A0/B0 directly.
- **Feedback** (reg `0xC0` bits 1..3) comes from the **modulator** operator's
  shadow byte (DRO-capture confirmed; e.g. AE000:054 ids `1B`=7, `0F`=5,
  `0E`/`14`=3, `01`=1, `17`=0). High feedback is the gritty "sampled-sounding"
  timbre.
- Dynamic volume: `0xE1F2` scales carrier total level by a per-voice runtime
  volume (voices can swell/fade during a song).
- Confirmed non-features for OPL: the detune/chorus tables (`0xCA24/0xCA6D`)
  exist but the setter `0xDF98` is never called (zero detune); vibrato/envelope
  updater `0xC440` and the `6D` dynamic path run only for device 1.

## PC-speaker SFX id catalogue (`AE000:065`)

High-confidence (EXE call-site + capture verified):

| ID | Meaning | Key evidence |
|---:|---|---|
| `0x00` | temporary invincibility activation | `0x41FA/0xBE67` set `DS:072C=0x3A` then play 0; ~695 `?E` events ≈ 5.9 s |
| `0x01` | landing/impact | `0x4462` |
| `0x02` | collectible/artifact pickup | `0x3BA2`, collision result `< 7` |
| `0x03` | room-gated apple pickup / green-symbol motif | `0x3C4A`, collision result `== 7`, clears `room[0x3E5..0x3E7]` |
| `0x0A` | button/switch/control family | `0x36F0`, collision results `0x20..0x2F` |
| `0x0C` | normal jump | `0x4133` (jump counter 5) |
| `0x0E` | laser/jello puzzle cell **take** | `0x8DA4` (board table `DS:C316`) |
| `0x0F` | laser beam hit / reflect | `0x5D11/0x5D34/0x5D57` after reflector classifier |
| `0x10` | high jump (rocket boots / up-jump variant) | `0x40B7` (jump counter 8) |
| `0x11` | failed invincibility use (no charges) | `0x4204/0xBE71` |
| `0x14` | laser/headlamp shot start | `0x4222` right after beam init `0x5A3B`; capture match |
| `0x17` | blocked/invalid action (laser already active, jello slot busy) | `0x422C/0xBE93`, `0x8D4C/0x8FB2` |
| `0x1A` | laser/jello puzzle cell **place** | `0x8FE2` (inverse of `0x0E`) |
| `0x1B` | artifact/end puzzle success fanfare | `0x904C` after validator `0x969D` |

Actor-script sounds (VM opcode `0x07`): `0x04` fireballs, `0x06` pill
projectiles / mantis, `0x07` energy orbs, `0x12`/`0x15` sparkles, `0x05`
unknown actors.

Lower-confidence (**UNPROVEN naming**, call sites recorded): `0x08` (`0x34FC`),
`0x09` (`0x9D80`), `0x0B` movement bump/snap (`0x4083`), `0x0D` room/level
transition (`0x233E/0x249F`), `0x13` (no caller found), `0x16` (`0x3510`),
`0x18`/`0x19` looped transition effects (loop flag `DS:1774`).
