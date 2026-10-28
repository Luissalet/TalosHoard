# Bench recordings

Four synthetic calls (microphone track + system track + `truth.json` with every line: speaker, side, start, end, words) used by
`funes_hoard/audio_memory/bench.py`. They come from the bench of a meeting recorder published under the MIT licence; the
recordings are generated from scripts with public-domain / CC0 voices and published there as CC0. See `../NOTICE-meeting-recorder.md`.

| Case | What it tests |
|---|---|
| `call` | Overlapping speech: you on a headset, three people on the other side who interrupt each other |
| `call-speakers` | Echo: the same call through speakers, so the other side leaks into the microphone 40 ms late |
| `music` | The other side talks with music in the background |
| `silence` | Room noise only: the transcript must be empty |

`thresholds.json` holds the scores measured for the default engine; they are informative (`meets` in the results), nothing blocks on them.
