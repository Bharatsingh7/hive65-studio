"""System-audio analyser: captures what is playing (WASAPI loopback on Windows,
the PipeWire/PulseAudio monitor on Linux) and exposes what effects react to.

    bands        per-column spectrum, 0..1, auto-gained
    level        overall loudness, 0..1
    bass/mid/treble   smoothed energies, 0..1
    kick/snare/hat    envelopes that jump to 1 on a hit and decay
    hits[name]   counters for "beat", "kick", "snare", "hat" (see Effect.hit)
    bpm, phase   tempo estimate and position within the current beat (0..1)
"""
import threading
import time
from collections import deque

import numpy as np

RATE = 48000
BLOCK = 1024
FFT_SIZE = 2048

# Frequency ranges for the drum detectors (Hz).
RANGES = {"kick": (35, 150), "snare": (180, 2500), "hat": (6000, 16000)}


def _loopback_mic():
    import soundcard as sc
    speaker = sc.default_speaker()
    return sc.get_microphone(id=str(speaker.name), include_loopback=True)


class _Onset:
    """Spectral-flux onset detector for one frequency range."""

    def __init__(self, idx, threshold, min_gap):
        self.idx, self.threshold, self.min_gap = idx, threshold, min_gap
        self.prev = None
        self.history = deque(maxlen=43)  # ~1 s of flux values
        self.last = 0.0

    def __call__(self, mag, now, sensitivity=1.0):
        cur = mag[self.idx]
        if self.prev is None:
            self.prev = cur
            return False, 0.0
        flux = float(np.maximum(cur - self.prev, 0).sum())
        self.prev = cur
        self.history.append(flux)
        mean = np.mean(self.history)
        std = np.std(self.history) + 1e-9
        strength = (flux - mean) / std
        threshold = self.threshold / np.sqrt(sensitivity)
        if strength > threshold and flux > 1e-4 / sensitivity and now - self.last > self.min_gap:
            self.last = now
            return True, min(1.0, strength / (threshold * 2.5))
        return False, 0.0


class AudioAnalyzer:
    def __init__(self, bands=16, fmin=40.0, fmax=16000.0):
        self.n = bands
        self.bands = np.zeros(bands)
        self.level = self.bass = self.mid = self.treble = 0.0
        self.kick = self.snare = self.hat = 0.0
        self.hits = {"beat": 0, "kick": 0, "snare": 0, "hat": 0}
        self.bpm, self.phase = 120.0, 0.0
        self.beat = False  # legacy one-shot flag, see take_beat()
        # 0.25 (only loud parts react) .. 3.0 (very reactive). Scales gain, the
        # auto-gain floor and how easily drum hits are detected.
        self.sensitivity = 1.0

        freqs = np.fft.rfftfreq(FFT_SIZE, 1 / RATE)
        edges = np.geomspace(fmin, fmax, bands + 1)
        self._bins = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            b = np.where((freqs >= lo) & (freqs < hi))[0]
            self._bins.append(b if len(b) else np.array([np.searchsorted(freqs, lo)]))
        rng = lambda lo, hi: np.where((freqs >= lo) & (freqs < hi))[0]
        self._onsets = {"kick": _Onset(rng(*RANGES["kick"]), 1.6, 0.16),
                        "snare": _Onset(rng(*RANGES["snare"]), 1.9, 0.12),
                        "hat": _Onset(rng(*RANGES["hat"]), 2.1, 0.07)}
        self._bass_i, self._mid_i, self._treble_i = rng(30, 250), rng(250, 4000), rng(4000, 16000)
        self._buf = np.zeros(FFT_SIZE)
        self._peak = np.full(bands, 1e-3)
        self._epeak = np.full(3, 1e-3)
        self._beats = deque(maxlen=16)
        self._last_beat = 0.0
        self._stop = threading.Event()
        self.error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()

    def take_beat(self):
        """Return True once per detected beat (single consumer; prefer Effect.hit)."""
        if self.beat:
            self.beat = False
            return True
        return False

    def _run(self):
        try:
            mic = _loopback_mic()
            window = np.hanning(FFT_SIZE)
            with mic.recorder(samplerate=RATE, blocksize=BLOCK) as rec:
                while not self._stop.is_set():
                    data = rec.record(numframes=BLOCK)
                    self._process(data, window)
        except Exception as e:  # no audio device etc.: effects just see silence
            self.error = str(e)

    def _process(self, data, window):
        now = time.time()
        mono = data.mean(axis=1) if data.ndim > 1 else data
        self._buf = np.roll(self._buf, -len(mono))
        self._buf[-len(mono):] = mono
        mag = np.abs(np.fft.rfft(self._buf * window))
        sens = max(0.1, float(self.sensitivity))
        silent = float(np.sqrt(np.mean(mono ** 2))) < 1e-4 / sens

        raw = np.log1p(np.array([mag[b].mean() for b in self._bins]) * 10)
        self._peak = np.maximum(np.maximum(self._peak * 0.995, raw), 0.05 / sens)
        bands = np.clip(raw / self._peak * sens, 0, 1) if not silent else np.zeros(self.n)
        self.bands = np.maximum(bands, self.bands * 0.85)
        self.level = float(np.mean(self.bands))

        e = np.log1p(np.array([mag[self._bass_i].mean(), mag[self._mid_i].mean(),
                               mag[self._treble_i].mean()]) * 10)
        self._epeak = np.maximum(np.maximum(self._epeak * 0.996, e), 0.05 / sens)
        en = np.clip(e / self._epeak * sens, 0, 1) if not silent else np.zeros(3)
        self.bass = self.bass * 0.6 + en[0] * 0.4
        self.mid = self.mid * 0.6 + en[1] * 0.4
        self.treble = self.treble * 0.6 + en[2] * 0.4

        decay = 0.82
        self.kick, self.snare, self.hat = self.kick * decay, self.snare * decay, self.hat * 0.7
        if not silent:
            for name, det in self._onsets.items():
                hit, strength = det(mag, now, sens)
                if hit:
                    setattr(self, name, max(getattr(self, name), 0.5 + 0.5 * strength))
                    self.hits[name] += 1
                    if name == "kick":
                        self._on_beat(now)

        if self._last_beat:
            self.phase = min(1.0, (now - self._last_beat) / (60.0 / self.bpm))

    def _on_beat(self, now):
        self.hits["beat"] += 1
        self.beat = True
        if self._last_beat:
            ioi = now - self._last_beat
            if 0.25 < ioi < 1.5:
                self._beats.append(ioi)
                if len(self._beats) >= 4:
                    bpm = 60.0 / float(np.median(self._beats))
                    while bpm < 80:
                        bpm *= 2
                    while bpm > 180:
                        bpm /= 2
                    self.bpm = self.bpm * 0.8 + bpm * 0.2
        self._last_beat = now
        self.phase = 0.0
