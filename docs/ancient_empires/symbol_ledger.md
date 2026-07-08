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
| 1010:6C26 | wait_ticks(AX=delta) — spin head 6C40 (target dword SS:BP-4/BP-2) | TRACED | lindis 6C26..6C56; spin observed |
| 1010:6C57 | set_deadline(AX=delta) → DS:C0D0/C0D2 | TRACED | lindis 6C57..6C6E |
| 1010:6C6F | wait_deadline — spin head 6C71 (tick32 < DS:C0D0/C0D2) | TRACED | lindis; exercised as timer_wait boundary in 4000-frame lockstep |
| 1010:6C87 | deadline_elapsed? (non-blocking) | TRACED | lindis 6C87..6CA5; called from intro 55BA and menu AFF9 |
| DS:0B76/0B78 | 32-bit master tick counter | TRACED | ISR increments; wait helpers compare |
| DS:C0D0/C0D2 | deadline dword | TRACED | set by 6C57, read by 6C6F/6C87 |
| DS:0B7A/0B7C | saved BIOS INT 08 far vector | TRACED | installer 6B7A stores via INT21 AH=35 |
| 1010:C1A0 | per-tick service (suspected audio/sequencer — UNCONFIRMED) | OBSERVED | called from ISR each tick behind flag checks DS:237C/176E/1772 |
| 1010:6B1A | blocking key read (INT16 AH=00, F1..F10 special path via 792C/7964) | TRACED | lindis + live INT16 counts |
| 1010:6B4A | non-blocking key check (INT16 AH=01) | TRACED | lindis + live INT16 counts |
| 1010:6B66 | flush keyboard buffer | TRACED | lindis 6B66..6B73 |
| 1010:6B7A | timer install (saves old vec, installs 6BCF, PIT←0x13B1) | TRACED | lindis |
| 1010:6BAC | timer uninstall (restores vec, PIT←0x10000) | TRACED | lindis |
| 1010:5595 | intro input-wait loop head (Enter=0D/Esc=1B exits, attract timeout) | TRACED | lindis 5595..55C6; park histogram |
| 1010:B08A | sign-in/menu poll-loop head (call 6B4A; AFF9 call 6C87) | TRACED | one-cycle trace (24 instructions) |
| DS:08FC | last key read in intro loop | OBSERVED | 559F stores AX |
| 1010:6E11..6E97 | DAT load/decompress hot loop (boot) | OBSERVED | park histogram during load |
| DS:3924 | far-ptr table to page buffers (blit source/dest) | OBSERVED | blit routine at 0604..063D uses it; 320-byte rows |
| F000:E987 | native BIOS INT 09h keyboard handler (framework) | VERIFIED | dos_re.DOSMachine.bios_int9_keyboard; IVT[9] target at power-on; tests/test_bios_keyboard.py |
| DS:C0CC | saved previous INT9 vector (game chains buffered keys here) | TRACED | install 6B88; snapshot repair repoints stale F000:FF53→F000:E987 |
| DS:0B72 | route-keys-to-BIOS-buffer flag (menus set it; ISR chains special keys only when !=0) | TRACED | ISR 6AE9 cmp [0B72],0; non-special keys always chain (di=0 path) |
| 1010:01CE | set_text_style(style) — DS:40C8 = VGA colour table DS:3904[style] | TRACED | lindis; reads DS:BFCD |
| 1010:0215 | set_color_pair(idx,vga,ega) → DS:3904[idx]/DS:00BE[idx] | TRACED | lindis 0215..0231 |
| DS:3904 | VGA text-colour table (identity init; menu overwrites 0..8 → 0x8004) | OBSERVED | see blockers.md red-text |
| DS:009C / DS:00DE | VGA / EGA text-colour source tables (memcpy'd at 0232) | TRACED | lindis |
| DS:BFCD | video/colour mode selector (1..5; =5 here) | OBSERVED | switch 502C..504B |
| 1010:17A4 | glyph blitter — ORs 1bpp rows using DS:40C8 low byte as colour | TRACED | lindis; matches KB graphics.md |
