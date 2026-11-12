# Talos's Hoard

Your computer's memory and health in one local process: screen history, clipboard, activity, audio and meetings, service monitoring and disk space.

## What it is

Talos's Hoard records what happens on your PC and answers questions about it: what was on screen, what you copied, what you worked on, what was said in a meeting, which service went down and why, and what is eating your disk. It runs locally, keeps its data on your machine and exposes everything to an assistant through MCP.

It is organised as six independent modules. Every module is **off on first start**: opening the app or discovering its MCP tools starts no collector, watcher, model or scanner. An explicit switch enables a module; disabling it stops its workers before closing its database. Your choices persist. Clipboard can run while screen capture, activity and audio stay off.

## Modules and what they do

| Module | What it covers |
| --- | --- |
| Screen | Screenshots, OCR, visual and full-text search, similar frames, timeline, application activity, exclusions, private mode, import and folder watching, pinned frames, exports and retention |
| Clipboard | Text and image history, type detection, OCR, search, favourites, edit, delete and restore, copy, bundles |
| Activity | Foreground windows, idle and lock handling, recent files, Git commits, projects, classifications, privacy rules, summaries, exports and cross-module recall |
| Audio | Microphone and system recording, file import, streaming transcripts, search, notes, tags, exports, meeting minutes, chapters, shared speech-to-text with GPU/CPU fallback |
| Services | Health checks, incidents and probable causes, logs, GPU history, event bus, job incidents, site, DNS, certificate and domain checks, scheduled SEO/GEO audits, notifications, restart policies |
| Disk | Space scan and tree, hotspots, largest and stale files, extension statistics, cleanup, recycle-bin and permanent-deletion safeguards, scripts, ZIP splitting, model-backup management |

The native interfaces live under `/screen/`, `/clipboard/`, `/activity/`, `/audio/`, `/services/` and `/disk/`, sharing the Hoard theme and the Faustus copilot.

**Screen**
- Captures screenshots with OCR, searchable by text and by visual similarity, with a timeline, per-application activity, exclusions, a private mode and retention rules; you can pause, delete a range, import screenshots or watch a folder.

**Clipboard**
- History of text and images with type detection and OCR, search, favourites and restore.
- **Reunir copias** combines up to 20 clips into one text with source and date notices, a separator of your choice, copy or TXT download; selections can be saved by name.
- **Leer texto** pages through long clips; **Comparar dos copias** shows a literal line diff of two clips. Previewing never changes stored clips.

**Activity**
- Foreground windows, recent files and Git commits become a timeline of projects with summaries and exports.
- **Projects -> Resume** reads a project's recorded windows, file openings and commits over a look-back interval, to pick up where you left off. An empty interval means no recorded evidence, not no work.
- **Screen to procedure** draft: windows, clips, screenshots and files of a range are segmented into steps with evidence, named inputs (secret-looking values masked), outputs and a list of unknowns. It is a draft for a person or agent to verify and never executes anything.

**Audio**
- Live and final transcription of microphone and system audio, import and export, search, notes and tags.
- Echo clean-up removes microphone lines that only repeat what the other track said; meetings of three minutes or more are split into chapters by the global model, shown in the session page, on the waveform, in the minutes and in exports.
- **Meeting to requirements**: every sentence is cut into clauses and labelled by Spanish and English linguistic rules as a firm commitment (owner, counterpart and due day only when the words say them), proposal, open question, decision or requirement, each with the exact cue and the source audio segment. "Could", "maybe" and every conditional are proposals, never commitments. Items can be tied to an engagement reference and exported as Markdown, JSON or as commitments for the people app.
- A transcription bench runs recordings with a known script through the configured engine and scores found words, correct side, leaked echo and invented lines.
- **Buscar en esta sesión** searches within one session.

**Services**
- Health checks, incidents with probable causes, logs, GPU and VRAM history, uptime, restart policies, a watch list, reboot detection and an audit trail of agent calls.
- Public sites: uptime, TLS certificates, domain expiry and DNS. A site can opt in to a scheduled SEO/GEO audit (`seo_interval_h`, 1 to 720 hours): the first success is the baseline, later runs are compared with the previous run and the baseline, and a drop in score or a new critical finding raises an alert on the family bus. Categories that could not be measured never count as a worsening.

**Disk**
- Scans with a tree and treemap (keyboard navigable), hotspots, largest and stale files, a junk catalogue, find files, folder explanations, cleanup scripts, deletion to the recycle bin or permanent with safeguards, ZIP splitting and management of model backups.

**Cross-module recall**
- Recall queries screen, clipboard and audio together inside this process.

## Run it

Python 3.11+; Windows is required for desktop capture and system integrations.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m talos_hoard --no-browser
```

Open `http://127.0.0.1:5220`. `Start.cmd` sets up the environment if needed. The server never opens a window automatically; the Hoard Hub reads `faustus-plugin.json` for explicit launch and MCP access.

| Variable | Purpose |
| --- | --- |
| `TALOS_DATA_DIR`, `TALOS_PORT` / `--port` | Central data folder and port. |
| `TALOS_URL`, `TALOS_TOKEN_FILE` | Settings for the MCP bridge. |

A new installation stores data in `data/<module>`. To keep the history of the original apps, with every module off run `scripts\adopt_data.py --parent "C:\path\to\Hoards"`: it writes only `data/modules.json` and leaves databases, screenshots, clipboard images, recordings, settings, tokens and disk snapshots where they are. Module data can also be relocated into `data/native/<module>/data`, moving whole trees. Disabling a module never deletes its history; on activation the native engine resumes with its saved privacy and retention settings.

## Connect to Faustus and the Hoard family

- **MCP**: `GET /api/agent/tools` lists about a hundred tools and `POST /api/agent/call` takes the bearer token in `data/mcp-token`. Calls to an off module answer `module_disabled` and never enable it. `python mcp_server.py` is the stdio bridge; its catalogue works without a running server and never launches one. Modules are controlled with `GET /api/modules`, `PUT /api/modules/{id}` (`{"enabled": true|false}`) and `POST /api/modules/stop-all`, or the tools `talos_modules` and `talos_set_module`.
- **Tool groups**: screen (`screen_*`), clips (`clip_*`, including `clip_bundle`, `clip_compare`, `clip_selections`), activity (`activity_*`, including `activity_project_resume` and `activity_procedure_draft`), audio (`scribe_*`, including `scribe_requirements`, `scribe_chapters`, `scribe_echo_check`, `scribe_bench`), services (`service*`, `sites_*`, including `sites_seo`, `sites_seo_run`, `sites_seo_baseline`), disk and recall. Every tool is listed in [`provenance/`](provenance/).
- **Copilot**: Talos serves the Faustus panel itself (`/api/copilot/*`, also under each module's path). The Services interface tells the assistant which service, site, incident or filter is on screen; the conversation lives in Faustus.
- **Hub**: events and notifications, and compatibility entries for retired identities that keep family tokens, references and cross-app calls working without running the old servers. The meeting commitments feed the people app, and the audio tools also answer on `/legacy/funes/`.
- **Models**: text-model requests use the family's configured global model service; audio and visual engines keep their optional local model downloads and GPU leases. No model loads while its module is off.
- **Skills**: `hoard-what-happened`, `hoard-daily-digest`, `systematic-debugging` and `local-voice-comparison` are offered to connecting agents.

## Project layout

| Path | Contents |
| --- | --- |
| `talos_hoard/` | Combined server, module lifecycle and tool catalogue |
| `argus/`, `cassandra_hoard/`, `diskhoard/`, `echo/`, `funes_hoard/` | Engines of the Screen, Services, Disk, Clipboard and Audio/Activity modules |
| `ui/` | Native interface projects (`npm ci && npm run build` in each; built assets are included) |
| `compatibility/` | Manifests that preserve the retired identities |
| `provenance/` | Licences and exact source commits; Cinzel and Source Sans 3 fonts ship under their SIL Open Font Licenses |
| `scripts/` | Data adoption, catalogue builder, synthetic QA server, MCP verification |
| `tests/`, `legacy_tests/` | Test suites |

```powershell
python -m pytest tests -q      # needs pytest and pytest-asyncio
```

`scripts/qa_server.py` starts a synthetic instance with fake capture and audio and offline network engines.

License: MIT (see `LICENSE`).
