# Symbol ledger — addresses → evidence (status ladder: OBSERVED < TRACED < VERIFIED)

Address convention: cs=1010 code offsets equal the knowledge base's flat
offsets; DGROUP DS=1FB3 (doc `DS:xxxx` offsets apply directly).

| Address | Name (working) | Status | Evidence |
|---|---|---|---|
| 1010:6BCF | timer ISR (INT 08) | OBSERVED | IVT[08] after boot in this VM; matches KB `exe_map.md` 0x6BCF |
| 1010:699E | keyboard ISR (INT 09) | TRACED | IVT[09]; full ISR trace 2026-07-06: reads port 60h, E0/E1 filter, special-key table search |
| 1010:6A0B (cs data) | special-key scancode word table ×15 | TRACED | ISR trace; values 1D,1F,29,2B,46,47,48,49,4A,4B,4D,4E,50,54,58 |
| 1010:6AF1 | chain to saved BIOS INT9 via DS:C0CC | TRACED | ISR trace: non-special keys `pushf; call far ds:[C0CC]` (= F000:FF53 stub) |
| DS:0B68, DS:0B6C | last special key (make state) | OBSERVED | ISR writes both from AX=masked scancode at 1010:6A53/6A56 |
| DS:0B72 | ISR mode/pass-through flag (checked before BIOS chain) | OBSERVED | 6AE9 `cmp ds:[0B72],0` |
| DS:C0CC | saved previous INT 09 far vector | TRACED | contains F000:FF53 after boot |
| PIT ch0 reload 0x13B1 | master tick 236.69 Hz | OBSERVED | dos.pit_channel0_reload after boot; matches KB |
| 1010:5557 (ret inside helper ~5330..5381) | tick-wait poll helper (name TBD) | OBSERVED | spin site when no timer IRQs pumped; loops `call …; cmp ax,[bp+08]; jl` |
