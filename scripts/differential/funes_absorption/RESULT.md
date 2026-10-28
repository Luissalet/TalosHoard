# Last run (28 Oct 2026)

Oracle: Funes at commit `8980fb147433c58877a0429a88b1a97761eb4c0b` (last one before the absorption), run as its own server.
Probe: Talos with the Activity and Audio modules on. Corpus: 130 cases (seed `funes-absorption`, sha256 `307f0fb9…d26867`).

| Harness | Result | Stability |
| --- | --- | --- |
| `funes-absorption-talos` (`/api/agent/call`) | pass, 130 of 130 cases identical | 3 of 3 runs |
| `funes-absorption-legacy` (`/legacy/funes/api/agent/call`) | pass, 130 of 130 cases identical | 3 of 3 runs |

Negative control (`--mutate`: the note store drops the first character of a note): both harnesses fail at case `c000083`
(`scribe_note`, expected "Segunda nota: pedir presupuesto.", got "egunda nota: ..."), so the comparison does see a regression.

## What the first, unmasked runs showed

Before the masks were written, the raw comparison listed every place where the two sides differ. They fell in three groups; none is a
lost capability:

1. **Intended architecture** (kept out of the comparison, see the README): the addresses and up/down wording of sibling apps in
   `sources_status` and `recall`; one entry point instead of two (the original Activity route did not know the audio-only tools);
   wording of errors that the original wrapped as `404: {...}` text; the body of an unknown-tool answer.
2. **Additive**: `scribe_search` gained the optional `session_id`; four audio tools and the `echo` statistics block exist only in Talos.
3. **Noise**: generated ids, the clock, job ids, the length of live recordings, a language model that happened to be reachable on the
   test machine (the test now points it to a closed port on both sides).

Data written by the original code (activity history, three audio sessions with tags, notes and stored minutes) opened in Talos without
conversion errors and every read, search and export of it matched; writes (tags, notes, import, transcription jobs, live recording on one
and on two tracks, stop, delete) matched as well. No bug was opened: nothing was lost.
