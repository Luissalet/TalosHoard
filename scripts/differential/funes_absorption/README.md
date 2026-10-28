# Differential test of the Funes absorption

Checks that nothing the original Funes did with its Activity and Audio tools was lost when its code moved into Talos. The **oracle** is the
last Funes commit before the absorption, run as its own server; the **probe** is Talos with the Activity and Audio modules on. Both start
from the same data (built by the old code, so Talos also opens an old-format audio database), receive the same recorded sequence of tool calls
and write a trace; the differential kit (`hoard_link.parity`, HoardLink repository) compares the traces exactly and names the first
divergence.

Two harnesses run the same corpus: `harness_talos.py` calls Talos's `/api/agent/call`, `harness_legacy.py` calls the old address
`/legacy/funes/api/agent/call`.

## Running it

```
git archive <last commit before the absorption> | tar -x -C <empty folder>          # the oracle; it is only read
python scripts/differential/funes_absorption/run.py --pre <that folder> --kit <HoardLink checkout> [--work <folder outside the repo>] [--stable 3] [--mutate]
```

Everything runs on private ports with temporary data and fake audio, a fake transcriber, a stand-in activity probe, no language model and
no other app; the work folder holds the reports (`state/<harness>/report.json`) and can be deleted afterwards. `--mutate` is the negative
control: Talos runs with a deliberate regression in the note store and the test must fail.

## What is compared (130 cases)

All 19 Activity and 16 Audio tools of the original, with both argument errors and not-found answers: summaries, timelines, search,
projects, recent files, where-was-I, agent days, recall, sources, pause, sessions, transcripts (ranges and size limits), search, tags,
notes, exports in every format, stored minutes, minutes for a session without a model, file import (speech, a pure tone, a missing file),
transcription jobs, live recordings (microphone only and microphone plus system), stop, delete and unknown tools. The first case also
compares the tool list: presence, required arguments and argument types of every original tool.

Masked before comparing: generated session ids (by first appearance), the clock, temporary paths, ports, job ids, the length of live
recordings, and for live recordings only who said what (not segment boundaries). Not covered: real capture, a real speech model, minutes
written by a model, the web interfaces and concurrency.

## Differences that are intended (and therefore not failures)

- The sibling apps are now modules of one server: their addresses in `sources_status`/`recall` change, and a module that is off reads
  "disabled" where the original said "unreachable" (masked as "down").
- One entry point: Talos answers every tool through any route, while the original Activity route did not know the audio-only tools
  (`scribe_status`, `scribe_delete`, ...). Errors of the audio tools reached through the Activity route are no longer re-wrapped as
  `404: {...}` text, and the body of an unknown-tool answer is `{"detail": "Unknown tool"}`. These cases compare only "failed or not".
- Added on purpose: the optional `session_id` argument of `scribe_search` (listed in `ADDITIVE_ARGUMENTS`; any other new argument fails
  the test), four new audio tools (`scribe_chapters`, `scribe_echo_check`, `scribe_bench`, `scribe_bench_status`) and an `echo` block in
  the statistics of a transcribed session.

## Result

See `RESULT.md` for the last run.
