# Differential test of the absorption of Pantalla, Portapapeles, Servicios and Disco

Checks that nothing the original Argus, Echo, Cassandra and DiskHoard did with their tools was lost when their code moved into Talos. For
each module the **oracle** is the last commit of the original repository before the absorption, run as its own server; the **probe** is
Talos with only that module on. Both start from the same data (built by the old code, so Talos also opens an old-format database, snapshot
or folder), receive the same recorded sequence of tool calls and write a trace; the differential kit (`hoard_link.parity`, HoardLink
repository) compares the traces exactly and names the first divergence. The method is the one of `../funes_absorption/`.

Each module runs two harnesses over the same corpus: `harness_main.py` calls Talos's own address (`/api/agent/call`, Talos token) and
`harness_native.py` calls the module's prefix (`/<module>/api/agent/call`, the module's token).

## Running it

```
# the oracles: the last commit of each original repository before the absorption, into one folder each (only read)
git archive <commit> | tar -x -C <root>/ArgusHoard        # also EchoHoard, CassandraHoard, DiskHoard
python scripts/differential/module_absorption/run.py --pre-root <root> --kit <HoardLink checkout> --work <folder outside the repo> \
       [--module argus|echo|cassandra|disk|all] [--stable 3] [--mutate]
```

The kit counts consecutive passes between invocations that share the same `--work` folder, so "stable 3 of 3" means three runs in a row.
Everything runs on private ports with temporary data; the work folder holds the reports (`<module>/state/<harness>/report.json`) and can be
deleted afterwards. `--mutate` is the negative control: Talos runs with a deliberate regression in that module and the test must fail.
The commits used for the last run are in `RESULT.md`.

| Module | Original | Cases | Fakes (nothing real is touched) |
| --- | --- | --- | --- |
| Pantalla (`screen`) | Argus | 85 | screen capture, window probe and OCR engine replaced; rendered screens as data |
| Portapapeles (`clipboard`) | Echo | 124 | the fake clipboard backend; no write reaches the real clipboard |
| Servicios (`services`) | Cassandra | 148 | fixed clock, fake network, process table, GPU, hub and restart backend; poller, bus mirror and site watcher off; a fake Faustus on a private port |
| Disco (`disk`) | DiskHoard | 123 | a scan saved by the old code, a copy of a fixture tree per side, only the permanent delete mode inside that copy (never the trash), a toy Ollama store and "Ollama not running" |

## What is compared

All the tools of the original of each app, with argument errors and not-found answers: the first case compares the tool list (presence,
required arguments and argument types). Pantalla: search, similar, timeline, frame text, pin, recent, activity, days, pause/resume, delete range, imports and
watched folders. Portapapeles: recent (kind and time filters), search, get with paging, bundle, set, copy, pin with label and tags, delete, status and
the capture switch, including hidden (sensitive) clips. Servicios: status, incidents, why down, logs, GPU timeline, history, the audit trail of the bus and its
statistics, the secrets audit, Faustus attention and farm (with a fake Faustus that answers by token), public sites and their history, restart, and the two
writing tools (`svc_watch`, `sites_watch`). Disco: the scan saved by the old code read before any new scan, then a fresh scan of a fixture tree read every way
(dir, hotspots, junk, stale, top files, types, find, explain, script), ZIP plan, split, status and cancel, the Ollama backup tools on a toy store, and delete,
rescan and the "changed since the scan" refusal.

Masked before comparing: the clock, temporary paths (the temporary folders of the three sides have names of the same length, because ZIP manifests carry
paths), ports, ids generated per run, and the per-module volatile keys listed in each `mod_<module>.py`. Not covered: real capture, real OCR, real services and
processes, the real network, the web interfaces, the trash, concurrency and data migrated from a real installation.

## Differences that are intended (and therefore not failures)

- The sibling apps are now modules of one server: one entry point answers every tool through any route.
- Added on purpose: the optional `app` argument of `clip_recent` and four clipboard tools (`clip_compare`, `clip_selections`, `clip_selection_save`,
  `clip_selection_delete`); the SEO/GEO watch of Servicios (three tools, two optional arguments of `sites_watch`, the `seo` block of the status). Listed in
  `ADDITIVE_ARGUMENTS` of each module: any other new argument fails the test.
- Services no longer lists the retired identities of the absorbed apps; the fixture apps use other ids so this does not show.

## Result

See `RESULT.md` for the last run.
