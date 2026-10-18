# Talos's Hoard

<img src="app-icon.png" width="96" alt="Talos icon">

Screen memory, clipboard history, desktop activity, audio, service monitoring and disk management in one local process. Incorporates Argus, Echo, Funes, Cassandra and DiskHoard.

[Castellano](README.es.md) · [Complete tool inventory](provenance/CAPABILITIES.md) · [Source provenance](provenance/sources.json)

## Independent modules

Every module is **OFF on first start**. Opening the app or discovering its MCP tools starts no collector, watcher, model or scanner. An explicit switch enables a module; disabling it stops its workers before closing its database. Your choices persist. Clipboard can run while screen capture, activity and audio remain off.

| Module | Preserved functions |
|---|---|
| Screen | Screenshots, OCR, visual and full-text search, similar frames, timeline, application activity, exclusions, private mode, import and folder watching, pinned frames, exports and retention |
| Clipboard | Text and image history, type detection, OCR, search, favourites, edit/delete/restore, copy and bundles |
| Activity | Foreground windows, idle/lock handling, recent files, Git commits, projects, classifications, privacy rules, summaries, exports and cross-module recall |
| Audio | Microphone/system recording, file import, streaming transcripts, search, notes, tags, exports, minutes, shared speech-to-text and GPU/CPU fallback |
| Services | Health checks, incidents, probable causes, logs, GPU history, event bus, job incidents, site/DNS/certificate/domain checks, notifications and restart policies |
| Disk | Space scan/tree, hotspots, largest and stale files, extension statistics, cleanup, recycle/permanent deletion safeguards, scripts, folder picker, ZIP splitting and model-backup management |

The full native interfaces remain under `/screen/`, `/clipboard/`, `/activity/`, `/audio/`, `/services/` and `/disk/`. The shared Hoard theme, product icon and Faustus copilot apply throughout. Capture backends and operating-system integrations retain their original platform requirements.

## Run

Python 3.11+; Windows is required for Windows desktop capture and system integrations. From this folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m talos_hoard --no-browser
```

Open `http://127.0.0.1:5220`. `Start.cmd` performs the initial environment setup if needed. The server never opens a window automatically. Hoard Hub reads `faustus-plugin.json` for explicit launch and MCP access.

## Existing data

No history is copied, moved, cleared or converted during adoption. With all modules OFF, map the old data folders in place:

```powershell
.venv\Scripts\python.exe scripts\adopt_data.py --parent "C:\path\to\Hoards"
```

This writes only `data/modules.json`. Existing databases, screenshots, clipboard images, recordings, settings, tokens and disk snapshots stay in their original folders. Keep those folders. `data_paths` can also be edited while the server is stopped. A new installation without adoption uses `data/<module>`.

On activation, the native engine resumes its normal behaviour, including its saved privacy and retention settings. Disabling a module never deletes its history. In-progress operations finish before OFF is reported; live event streams are disconnected. Large media responses stream without loading whole recordings into memory.

`TALOS_DATA_DIR`, `TALOS_PORT` and `--port` override the central data folder and port. Original module environment variables still configure their capture/model backends. `TALOS_TOKEN_FILE` and `TALOS_URL` configure the MCP bridge.

## API and MCP

`GET /api/modules`, `PUT /api/modules/{id}` with `{"enabled":true|false}`, and `POST /api/modules/stop-all` control the modules. `GET /api/agent/tools` exposes 93 tools: all 91 native tools plus `talos_modules` and `talos_set_module`. `POST /api/agent/call` requires the bearer token in `data/mcp-token`. Calls to an OFF module return `module_disabled`; they never enable it implicitly.

Run `.venv\Scripts\python.exe mcp_server.py` for stdio MCP. Its catalogue works without a running Talos server and never launches one. Native API names, record identifiers and source citations are preserved. Recall calls screen, clipboard and audio directly inside this process.

Retired Hoard identities may remain registered as **non-launchable compatibility entries** pointing at these module routes. They preserve family token authentication, references and cross-Hoard calls; they do not run old servers. Funes's family audio tools are also routed through `/legacy/funes/`.

## Development and verification

Install `pytest pytest-asyncio` in the same environment. Run `python -m pytest tests -q`. `legacy_tests/` retains the incorporated engines' regression tests; run each engine's suite separately where helper modules have identical names. `scripts/qa_server.py` starts a synthetic instance with fake capture/audio and offline network engines. `scripts/verify_mcp.py --data-dir <QA-data>` checks the real stdio transport against that instance.

UI sources live under `ui/`; each has its own lockfile. Run `npm ci` and `npm run build` inside the relevant UI directory. Built assets ship with the repository. `scripts/build_catalog.py` rebuilds the static native tool definitions without opening histories or starting engines.

Text-model requests use the family's configured global Sparks service. Audio and visual engines retain their native optional model downloads and local GPU leases; no model loads while its module is OFF. `provenance/` records licenses and exact source commits. Cinzel and Source Sans 3 ship under their included SIL Open Font Licenses.
