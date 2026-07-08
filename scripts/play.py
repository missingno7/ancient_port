"""Run Ancient Empires inside the dos_re VM — the interactive entrypoint.

This is the owner's window into the port (bring-up phase: the ORACLE runs —
pure original ASM, no recovered hooks yet).  It boots AEPROG.EXE (or resumes
a snapshot), paces the game with its own 236.69 Hz master tick delivered as
real INT 08h IRQs, renders the VGA mode 13h framebuffer, forwards the
keyboard through the game's dual input path, and plays AdLib (Nuked-OPL3) +
PC-speaker audio from the emulated ports.

Hotkeys:
  F11  start/stop input-demo recording  -> artifacts/demos/
  F12  save a full machine snapshot     -> artifacts/
  (Esc and all other keys go to the game.)

Usage:
  python scripts/play.py                        boot from cold
  python scripts/play.py --boot-intro           skip to the intro screen
                                                (cached canonical snapshot)
  python scripts/play.py --snapshot DIR         resume any saved snapshot
  python scripts/play.py --play-demo DIR        replay a recorded demo
  python scripts/play.py --frames N             headless smoke (SDL dummy ok)

Determinism: the demo clock is the presented-frame index.  Each frame runs a
fixed --chunk-steps instruction budget with the frame's IRQ quota interleaved
at fixed sub-batch boundaries, so a recording replays bit-identically under
the same {chunk_steps, present_hz} (stored in the demo manifest and restored
on replay).  Audio is observer-only and never affects game state.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dos_re.cpu import HaltExecution  # noqa: E402
from dos_re.input_demo import InputDemoPlayback, InputDemoRecorder  # noqa: E402
from dos_re.interrupts import deliver_interrupt, deliver_scancode  # noqa: E402
from dos_re.keyboard import KeyDispatcher  # noqa: E402
from dos_re.snapshot import write_snapshot  # noqa: E402

from ancient.keys import deliver_game_key  # noqa: E402
from ancient.runtime import DEFAULT_EXE, boot_to_intro, create_game_runtime, load_game_snapshot  # noqa: E402

WIDTH, HEIGHT = 320, 200
INTRO_SNAPSHOT = ROOT / "artifacts" / "snap_intro"


# ---------------------------------------------------------------- audio sink

class AudioSink:
    """Observer-only live audio: AdLib via Nuked-OPL3 + PC-speaker square wave.

    The VM exposes both as callbacks (dos.set_adlib_callback /
    set_speaker_callback); this sink renders them into one pygame mixer
    channel with a small jitter lead.  It never writes game state, so demos
    replay identically with audio on or off.
    """

    def __init__(self, pygame, rt, present_hz: int) -> None:
        import numpy as np

        self._np = np
        self._pygame = pygame
        self.available = False
        self.opl_label = "off"
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            except Exception as exc:  # headless/dummy audio hosts
                print(f"[audio] mixer unavailable ({exc}); audio off")
                return
        rate, _size, channels = pygame.mixer.get_init()
        self._rate, self._channels = int(rate), int(channels)
        self._chunk = max(256, self._rate // max(1, present_hz))
        self._lead = int(self._rate * 0.10)
        self._buf = np.zeros((0, self._channels), dtype=np.int16)
        self._started = False
        if pygame.mixer.get_num_channels() < 2:
            pygame.mixer.set_num_channels(2)
        self._channel = pygame.mixer.Channel(1)

        self._opl = None
        try:
            from pynuked_opl3 import OPL3

            self._opl = OPL3(sample_rate=self._rate)
            self.opl_label = "pynuked-opl3"
        except Exception as exc:
            self.opl_label = "unavailable"
            print(f"[audio] Nuked-OPL3 not built ({exc}); AdLib silent, "
                  f"speaker still on. Build once: python -m pynuked_opl3._ffi_build")
        # PC speaker square-wave state (phase-continuous across chunks).
        self._spk_on = False
        self._spk_freq = 0.0
        self._spk_phase = 0.0
        rt.dos.set_adlib_callback(self._on_adlib, emit_current=True)
        rt.dos.set_speaker_callback(self._on_speaker, emit_current=True)
        self.available = True

    def _on_adlib(self, reg: int, value: int) -> None:
        if self._opl is not None:
            self._opl.write(reg, value)

    def _on_speaker(self, on: bool, freq: float) -> None:
        self._spk_on, self._spk_freq = bool(on), float(freq or 0.0)

    def _speaker_chunk(self, n: int):
        np = self._np
        if not (self._spk_on and self._spk_freq > 0):
            return None
        step = self._spk_freq / self._rate
        phases = self._spk_phase + np.arange(n) * step
        self._spk_phase = float(phases[-1] + step) % 1.0
        return np.where((phases % 1.0) < 0.5, 5000, -5000).astype(np.int16)

    def pump(self) -> None:
        if not self.available:
            return
        np = self._np
        n = self._chunk
        if self._opl is not None:
            pcm = np.frombuffer(self._opl.generate_stereo(n), dtype="<i2").reshape(-1, 2)
            out = pcm.astype(np.int32)
        else:
            out = np.zeros((n, 2), dtype=np.int32)
        spk = self._speaker_chunk(n)
        if spk is not None:
            out += spk[:, None]
        out = np.clip(out, -32768, 32767).astype(np.int16)
        if self._channels == 1:
            out = out[:, :1]
        self._buf = np.concatenate([self._buf, out])
        if not self._started:
            if len(self._buf) >= self._lead:
                self._channel.play(self._next_sound())
                self._started = True
            return
        if not self._channel.get_busy():
            self._started = False
            return
        if self._channel.get_queue() is None and len(self._buf) >= self._chunk:
            self._channel.queue(self._next_sound())

    def _next_sound(self):
        chunk, self._buf = self._buf[:self._chunk], self._buf[self._chunk:]
        arr = chunk if self._channels > 1 else chunk.reshape(-1)
        return self._pygame.sndarray.make_sound(self._np.ascontiguousarray(arr))


# ------------------------------------------------------------- deterministic clock
#
# This is the INTERACTIVE driver's chunked clock: one presented frame = a
# fixed --chunk-steps budget with the frame's IRQ quota interleaved at fixed
# sub-batch points.  The frame VERIFIER counts wait-head boundaries instead
# (ancient/input_waits.py).  Demos recorded here replay identically under
# this clock (manifest stores chunk_steps/present_hz); unifying the two
# clock definitions is the open porting-guide step-6 item tracked in
# docs/ancient_empires/run_status.md.

def ticks_for_frame(frame: int, ticks_per_frame: float) -> int:
    """IRQ quota for presented frame ``frame`` — a pure function of the frame
    index, so recordings replay identically."""
    return int((frame + 1) * ticks_per_frame) - int(frame * ticks_per_frame)


def master_tick_hz(rt) -> float:
    reload = rt.dos.pit_channel0_reload or 0x10000
    return rt.dos.PIT_INPUT_HZ / reload


_PARK_PROBE_BATCH = 512  # steps between parked-in-wait probes (any value gives
                         # identical machine state; it only tunes probe overhead)


def _run_budget_or_park(rt, budget: int) -> None:
    """Step up to ``budget`` instructions, stopping early -- parked at the
    spin's canonical head -- once the game enters a registered tick-wait whose
    condition cannot change until the next delivered IRQ.

    This is the cookbook's deterministic timing fast-forward: idle spin
    iterations are provably identical (the loop only re-reads the tick counter
    and its target, and only our IRQ delivery advances the tick), so skipping
    them changes nothing the game can observe.  Parking exactly at the head
    (ancient.timing.park_at_wait_head) makes the stop point -- and therefore
    the IRQ delivery point -- a pure function of machine state, independent of
    the probe batch size.  No state is faked and no IRQ is skipped: the budget
    is simply not burned interpreting a busy-wait (pitfalls #12/#13)."""
    from ancient.timing import park_at_wait_head

    cpu = rt.cpu
    remaining = budget
    while remaining > 0:
        if park_at_wait_head(cpu) is not None:
            return
        batch = _PARK_PROBE_BATCH if remaining > _PARK_PROBE_BATCH else remaining
        cpu.run(batch)
        remaining -= batch
    park_at_wait_head(cpu)  # budget spent mid-iteration: still park canonically


def run_frame(rt, frame: int, *, chunk_steps: int, ticks_per_frame: float) -> None:
    """Advance one presented frame of the chunked demo clock.

    The single shared frame-advance for the interactive loop AND headless
    record/replay tests — never duplicate this loop (drifting copies void
    demo proofs).  A frame is UP TO ``chunk_steps`` instructions: each of the
    frame's IRQ-quota sub-budgets ends early (parked at the wait head) when
    the game is idling in a tick wait, so the budget is spent on real work,
    never on interpreting spin iterations.  Recordings replay identically
    under the same {chunk_steps, present_hz} (both stored in the manifest;
    demos recorded under the pre-parking clock are not replay-compatible —
    none were promoted)."""
    ticks = ticks_for_frame(frame, ticks_per_frame)
    sub = chunk_steps // (ticks + 1)
    for _ in range(ticks):
        _run_budget_or_park(rt, sub)
        deliver_interrupt(rt, 0x08)
    _run_budget_or_park(rt, chunk_steps - sub * ticks)


# ---------------------------------------------------------------------- main

def _decode_frame(rt, np):
    pal = list(rt.dos.vga_palette or ())
    while len(pal) < 256:
        pal.append((len(pal),) * 3)
    palette = np.asarray(pal[:256], dtype=np.uint8)
    arr = np.frombuffer(rt.cpu.mem.data, np.uint8, count=WIDTH * HEIGHT, offset=0xA0000)
    return palette[arr.reshape(HEIGHT, WIDTH)]


def _load_runtime(args) -> object:
    exe = Path(args.exe)
    if args.play_demo:
        playback = InputDemoPlayback.load(args.play_demo)
        if playback.is_cold_start:
            rt = create_game_runtime(exe, install_replacements=False)
        else:
            rt = load_game_snapshot(exe, playback.snapshot_path())
        meta = playback.manifest.get("metadata", {})
        args.chunk_steps = int(meta.get("chunk_steps", args.chunk_steps))
        args.present_hz = int(meta.get("present_hz", args.present_hz))
        print(f"replaying {args.play_demo} [chunk_steps={args.chunk_steps} "
              f"present_hz={args.present_hz} events={len(playback.events)}]")
        return rt, playback
    if args.snapshot:
        return load_game_snapshot(exe, args.snapshot), None
    if args.boot_intro:
        if not (INTRO_SNAPSHOT / "memory_1mb.bin").is_file():
            print("building canonical intro snapshot (one-time, ~4 min)...")
            rt = create_game_runtime(exe, install_replacements=False)
            boot_to_intro(rt)
            write_snapshot(rt, INTRO_SNAPSHOT, status="intro screen (canonical boot recipe)",
                           steps=rt.cpu.instruction_count)
        return load_game_snapshot(exe, INTRO_SNAPSHOT), None
    return create_game_runtime(exe, install_replacements=False), None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--exe", default=str(DEFAULT_EXE))
    p.add_argument("--snapshot", default=None, help="resume from a snapshot directory")
    p.add_argument("--boot-intro", action="store_true",
                   help="start at the intro screen (cached canonical snapshot)")
    p.add_argument("--play-demo", default=None, help="replay a recorded demo directory")
    p.add_argument("--record-demo", default=None, metavar="NAME",
                   help="start recording immediately under this name")
    p.add_argument("--demo-dir", default=str(ROOT / "artifacts" / "demos"))
    p.add_argument("--present-hz", type=int, default=60)
    p.add_argument("--chunk-steps", type=int, default=40_000,
                   help="VM instruction budget per presented frame (demo clock unit)")
    p.add_argument("--scale", type=int, default=3)
    p.add_argument("--square-pixels", action="store_true")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--frames", type=int, default=0,
                   help="exit after N presented frames (headless smoke)")
    args = p.parse_args(argv)

    import numpy as np
    import pygame
    from display import Display

    rt, playback = _load_runtime(args)
    rt.cpu.trace_enabled = False
    replaying = playback is not None

    pygame.init()
    display = Display((WIDTH * args.scale, int(HEIGHT * 1.2) * args.scale),
                      title="Ancient Empires — dos_re oracle")
    display.par = 1.0 if args.square_pixels else 1.2
    audio = None if args.no_audio else AudioSink(pygame, rt, args.present_hz)

    frame = 0
    recorder: dict[str, InputDemoRecorder | None] = {"rec": None}

    def start_recording(name: str) -> None:
        rec = InputDemoRecorder(
            root=Path(args.demo_dir), name=name,
            metadata={"exe": Path(args.exe).name, "chunk_steps": args.chunk_steps,
                      "present_hz": args.present_hz})
        out = rec.start(rt, boundary=frame)
        recorder["rec"] = rec
        print(f"recording demo [chunk_steps={args.chunk_steps} present_hz={args.present_hz}] -> {out}")

    def stop_recording() -> None:
        rec = recorder["rec"]
        if rec is not None and rec.active:
            out = rec.stop(boundary=frame)
            print(f"saved demo ({rec.event_count} events) -> {out}")
        recorder["rec"] = None

    dispatcher = KeyDispatcher(
        lambda sc: deliver_game_key(rt, sc, recorder=recorder["rec"], boundary=frame))
    scancodes = _scancode_table(pygame)
    clock = pygame.time.Clock()
    tick_hz = master_tick_hz(rt)
    ticks_per_frame = tick_hz / max(1, args.present_hz)
    print(f"master tick {tick_hz:.2f} Hz -> {ticks_per_frame:.3f} IRQs/frame; "
          f"audio: {'off' if audio is None or not audio.available else audio.opl_label + ' + speaker'}")

    if args.record_demo and not replaying:
        start_recording(args.record_demo)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                display.resize(event.w, event.h)
            elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F12:
                    out = ROOT / "artifacts" / f"snapshot_ae_{datetime.now():%Y%m%d_%H%M%S}"
                    write_snapshot(rt, out, status="manual play.py snapshot",
                                   steps=rt.cpu.instruction_count)
                    print(f"snapshot: {out}")
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    if recorder["rec"] is None:
                        start_recording(args.record_demo or "ae")
                    else:
                        stop_recording()
                elif not replaying:
                    sc = scancodes.get(event.key)
                    if sc is not None:
                        (dispatcher.post_down if event.type == pygame.KEYDOWN
                         else dispatcher.post_up)(sc)

        # One canonical input point per frame, before stepping (replay-aligned).
        if replaying:
            playback.apply_to_runtimes(frame, [rt], deliver=deliver_scancode)
        else:
            dispatcher.pump()

        try:
            run_frame(rt, frame, chunk_steps=args.chunk_steps,
                      ticks_per_frame=ticks_per_frame)
        except HaltExecution:
            pass
        if rt.cpu.halted:
            print(f"program exited at {rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X} "
                  f"after {rt.cpu.instruction_count} instructions")
            running = False

        if audio is not None:
            audio.pump()
        display.draw_game(_decode_frame(rt, np))
        display.flip()
        frame += 1
        if args.frames and frame >= args.frames:
            running = False
        clock.tick(args.present_hz)

    stop_recording()
    import hashlib
    digest = hashlib.sha1(bytes(rt.cpu.mem.data)).hexdigest()[:16]
    print(f"presented {frame} frames; CPU at {rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X}, "
          f"{rt.cpu.instruction_count} instructions; state digest {digest}")
    pygame.quit()
    return 0


# pygame key -> XT scan code (make). Break = make | 0x80.
def _scancode_table(pygame) -> dict[int, int]:
    k = pygame
    table = {
        k.K_ESCAPE: 0x01, k.K_MINUS: 0x0C, k.K_EQUALS: 0x0D, k.K_BACKSPACE: 0x0E,
        k.K_TAB: 0x0F, k.K_RETURN: 0x1C, k.K_LCTRL: 0x1D, k.K_RCTRL: 0x1D,
        k.K_LSHIFT: 0x2A, k.K_RSHIFT: 0x36, k.K_LALT: 0x38, k.K_RALT: 0x38,
        k.K_SPACE: 0x39, k.K_UP: 0x48, k.K_LEFT: 0x4B, k.K_RIGHT: 0x4D,
        k.K_DOWN: 0x50, k.K_COMMA: 0x33, k.K_PERIOD: 0x34, k.K_SLASH: 0x35,
        k.K_SEMICOLON: 0x27, k.K_QUOTE: 0x28, k.K_BACKQUOTE: 0x29,
        k.K_LEFTBRACKET: 0x1A, k.K_RIGHTBRACKET: 0x1B, k.K_BACKSLASH: 0x2B,
        k.K_HOME: 0x47, k.K_PAGEUP: 0x49, k.K_END: 0x4F, k.K_PAGEDOWN: 0x51,
        k.K_INSERT: 0x52, k.K_DELETE: 0x53,
    }
    for i, key in enumerate((k.K_1, k.K_2, k.K_3, k.K_4, k.K_5, k.K_6, k.K_7,
                             k.K_8, k.K_9, k.K_0)):
        table[key] = 0x02 + i
    for i, ch in enumerate("qwertyuiop"):
        table[getattr(k, f"K_{ch}")] = 0x10 + i
    for i, ch in enumerate("asdfghjkl"):
        table[getattr(k, f"K_{ch}")] = 0x1E + i
    for i, ch in enumerate("zxcvbnm"):
        table[getattr(k, f"K_{ch}")] = 0x2C + i
    for i in range(10):  # F1..F10
        table[getattr(k, f"K_F{i + 1}")] = 0x3B + i
    return table


if __name__ == "__main__":
    raise SystemExit(main())
