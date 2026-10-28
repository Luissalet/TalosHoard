"""Echo between the two tracks of a recording.

With the microphone ("yo") and the system loopback ("otros") captured apart, the speakers play the other side and the microphone
hears them again, a little later and quieter. The final pass would then transcribe the same sentence twice and attribute the second
copy to the user. Two checks remove those copies from the microphone track:

* **Overlap.** The microphone's active frames are compared with the system track's: a segment is echo when at least 60 % of its active
  frames are frames where the system is sounding (within three frames either side, echo trails behind) and the microphone is at least
  twice as quiet as the system there. Both tracks are levelled to their own speech level first, so a hot loopback does not make the
  user's voice look quiet. A user who talks over the other side at normal volume keeps the line.
* **Words.** A microphone line whose words come back, word for word, in the other track within two seconds of it is the other side
  leaking in: at least half of its three-word groups appear in the other lines, or, for one or two words, the same words in a row.

Method and thresholds follow the transcript clean-up of a meeting recorder published under the MIT licence (see
``NOTICE-meeting-recorder.md`` next to this file); the code is Funes's own, written for its segments and its WAV tracks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from .audio.wav import SAMPLE_RATE, to_float32

FRAME_MS = 30
FRAME = SAMPLE_RATE * FRAME_MS // 1000
AROUND = 3  # frames either side of a microphone frame where the system still counts as sounding
OVERLAP_MIN = 0.6  # share of the segment's active frames that must be echo-like
QUIETER = 2.0  # the microphone must be at least this many times quieter than the system around it
TEXT_WINDOW_S = 2.0  # lines of the other track this close in time are compared word for word
TRIGRAM_SHARE = 0.5
NOISE_FLOOR = 0.002
LEVEL_MIN = 0.01  # a track whose speech level is below this is levelled as if it were this loud (do not amplify pure noise)


@dataclass
class EchoStats:
    """What the echo pass did to one recording; stored on the session with the transcription counters."""

    checked: int = 0
    removed_text: int = 0
    removed_overlap: int = 0
    texts: list[str] = field(default_factory=list)

    @property
    def removed(self) -> int:
        return self.removed_text + self.removed_overlap

    def as_dict(self) -> dict:
        return {"checked": self.checked, "removed": self.removed, "removed_text": self.removed_text,
                "removed_overlap": self.removed_overlap, "texts": self.texts[-20:]}


# ---------------------------------------------------------------- audio side --
def frame_levels(samples: np.ndarray) -> np.ndarray:
    """RMS of every 30 ms frame (float, 0..1)."""
    floats = to_float32(np.asarray(samples))
    if len(floats) == 0:
        return np.zeros(0, dtype=np.float32)
    frames = -(-len(floats) // FRAME)
    padded = np.zeros(frames * FRAME, dtype=np.float32)
    padded[: len(floats)] = floats
    return np.sqrt(np.mean(padded.reshape(frames, FRAME) ** 2, axis=1)).astype(np.float32)


def active_frames(levels: np.ndarray) -> np.ndarray:
    """Frames with sound in them: above four times the track's own noise floor (its 10th percentile), never below 0.002."""
    if len(levels) == 0:
        return np.zeros(0, dtype=bool)
    floor = float(np.sort(levels)[len(levels) // 10])
    return levels >= max(floor * 4.0, NOISE_FLOOR)


def levelled(levels: np.ndarray, active: np.ndarray) -> np.ndarray:
    """Levels divided by the track's speech level (95th percentile of its active frames)."""
    if len(levels) == 0 or not active.any():
        return levels.copy()
    speech = float(np.percentile(levels[active], 95))
    return levels / max(speech, LEVEL_MIN)


@dataclass
class TrackProfile:
    levels: np.ndarray
    active: np.ndarray
    levelled: np.ndarray

    @classmethod
    def of(cls, samples: np.ndarray) -> "TrackProfile":
        levels = frame_levels(samples)
        active = active_frames(levels)
        return cls(levels, active, levelled(levels, active))


def echo_share(start: float, end: float, mic: TrackProfile, other: TrackProfile) -> float | None:
    """Share of the microphone's active frames in ``start..end`` that are echo-like; None when the microphone is silent there."""
    first = max(0, int(start * 1000) // FRAME_MS)
    last = min(len(mic.levels), -(-int(end * 1000) // FRAME_MS))
    indexes = [i for i in range(first, last) if mic.active[i]]
    if not indexes:
        return None
    echo = 0
    for i in indexes:
        lo, hi = max(0, i - AROUND), min(len(other.levels), i + AROUND + 1)
        if hi <= lo or not other.active[lo:hi].any():
            continue
        if mic.levelled[i] * QUIETER < float(other.levelled[lo:hi].max()):
            echo += 1
    return echo / len(indexes)


# ----------------------------------------------------------------- text side --
def words_of(text: str) -> list[str]:
    out = []
    for raw in (text or "").split():
        word = "".join(ch for ch in raw if ch.isalnum()).lower()
        if word:
            out.append(word)
    return out


def _trigrams(words: Sequence[str]) -> list[tuple[str, ...]]:
    return [tuple(words[i:i + 3]) for i in range(len(words) - 2)]


def repeats_other_side(text: str, others: Iterable[str]) -> bool:
    """True when the words of ``text`` come back, word for word, in the lines of the other track."""
    own = words_of(text)
    if not own:
        return False
    theirs = [words_of(line) for line in others]
    grams = _trigrams(own)
    if not grams:
        return any(own == other[i:i + len(own)] for other in theirs for i in range(len(other) - len(own) + 1))
    known = {gram for other in theirs for gram in _trigrams(other)}
    return sum(1 for gram in grams if gram in known) >= len(grams) * TRIGRAM_SHARE


# --------------------------------------------------------------------- driver --
Line = tuple[float, float, str]  # start_s, end_s, text


def find_echo(mic: Sequence[Line], other: Sequence[Line], mic_samples: np.ndarray | None = None,
              other_samples: np.ndarray | None = None) -> list[str | None]:
    """For every microphone line: ``"text"``, ``"overlap"`` or None (keep). ``overlap`` needs both audio tracks; without them only
    the word rule applies."""
    profiles = None
    if mic_samples is not None and other_samples is not None and len(mic_samples) and len(other_samples):
        profiles = (TrackProfile.of(mic_samples), TrackProfile.of(other_samples))
    verdicts: list[str | None] = []
    for start, end, text in mic:
        near = [t for (s, e, t) in other if s < end + TEXT_WINDOW_S and start < e + TEXT_WINDOW_S]
        if near and repeats_other_side(text, near):
            verdicts.append("text")
            continue
        share = echo_share(start, end, *profiles) if profiles else None
        verdicts.append("overlap" if share is not None and share >= OVERLAP_MIN else None)
    return verdicts


def drop_echo(mic_segments: list, other_segments: list, mic_samples: np.ndarray | None = None,
              other_samples: np.ndarray | None = None) -> tuple[list, EchoStats]:
    """The microphone's transcribed segments (objects with start/end/text) without the ones that are echo."""
    stats = EchoStats(checked=len(mic_segments))
    verdicts = find_echo([(s.start, s.end, s.text) for s in mic_segments], [(s.start, s.end, s.text) for s in other_segments],
                         mic_samples, other_samples)
    kept = []
    for segment, verdict in zip(mic_segments, verdicts):
        if verdict is None:
            kept.append(segment)
            continue
        if verdict == "text":
            stats.removed_text += 1
        else:
            stats.removed_overlap += 1
        stats.texts.append(segment.text[:120])
    return kept, stats
