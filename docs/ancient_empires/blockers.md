# Blockers — evidence log for slices that could not be finished byte-exact

## OPEN — menu text drawn red (should be black)

**Symptom:** In VGA mode 13h the menu/list text (player names, "Explorer/
Expert") renders as color index 4 (red). The reference port
(`ancient-empires-reverse-engineered/.../rendering/dialog_screen.py`, capture-
accurate vs DOSBox) draws this text **black (0,0,0)** — so red is a real bug,
not faithful behavior.

**Evidence gathered (2026-07-07):**
- DAC palette is faithful: index 4 = (170,0,0) red, matching the game's own
  source at DS:011E and the EXE-embedded palette (INT 10h AX=1012h upload).
  So the palette is correct; the text is drawn with the wrong *index*.
- Glyph blitter 1010:17A4 uses text colour word DS:40C8 (low byte = index).
  In the user snapshot DS:40C8 = 0x8004 → index 4.
- Text colour comes from the VGA colour table DS:3904[style] (set_text_style
  1010:01CE). Table init = identity [0,1,..,15] (copied from DS:009C). At the
  sign-in screen indices **0..8 are overwritten to 0x8004** (index 4); 9..15
  keep identity. Only writer is set_color_pair 1010:0215 (`mov [bx+3904],ax`),
  but no direct `call 0215` found — caller is indirect/unlocated.
- Video-mode selector DS:BFCD = 5 (a switch at 1010:502C..504B sets 1..5);
  set_text_style keys off it. 5 is presumably VGA (game runs mode 13h).

**Why blocked:** root cause of the 0x8004 (index-4) text colour not yet found
— need to trace the indirect caller of set_color_pair / what computes 0x8004,
and confirm whether a VM instruction diverged (should compute index 0) vs a
mis-set video/colour mode. Not guessing a colour patch (charter rule).
**Next:** watch the physical write to DS:3904 (0x1FB30+0x3904) during the
intro→sign-in transition to capture the value's provenance and caller.
