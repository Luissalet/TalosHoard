"""Writes the two WAV inputs of the differential: a pure tone (no speech) and a speech-like signal (syllable-rate bursts of
filtered noise) that a voice-activity gate accepts. Seeded, so the files are identical on every run."""
import math, random, struct, sys, wave
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
R = 16000
def write(name, samples):
    with wave.open(str(out / name), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(R)
        w.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, int(s)))) for s in samples))
write("tone.wav", (8000 * math.sin(2 * math.pi * 220 * i / R) for i in range(R * 4)))
rng = random.Random(7); lp = 0.0; sig = []
for i in range(R * 8):
    t = i / R
    gate = 1.0 if (t % 1.6) < 1.2 else 0.0                   # 1.2 s of "speech", 0.4 s pause
    env = gate * (0.55 + 0.45 * math.sin(2 * math.pi * 4.0 * t)) # syllable rhythm
    lp = 0.7 * lp + 0.3 * rng.uniform(-1, 1)                    # low-passed noise
    voiced = math.sin(2 * math.pi * 140 * t) * 0.5 + math.sin(2 * math.pi * 280 * t) * 0.3
    sig.append(9000 * env * (voiced + 1.4 * lp))
write("speech.wav", sig)
print("ok")
