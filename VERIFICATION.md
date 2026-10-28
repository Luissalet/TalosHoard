# Talos verification

Verified on Windows with isolated synthetic histories. Original histories were not opened by the test servers.

- Product suite: 15 passed, including independent OFF defaults, saved state, native module APIs, Funes audio compatibility, strict switch values and retained external data locations.
- Retired services are excluded after merging discovery and saved restart overrides. A regression reproduced the old Argus restart command remaining active, then passed with the fix; the saved settings file stays unchanged.
- Streaming: the first SSE event arrives before the producer completes; disabling cancels a live stream before closing its engine. Media responses retain native streaming and range support.
- Shutdown: OFF intent persists before a deliberately blocked shutdown; the dashboard remains responsive.
- Actual stdio MCP: discovery of 93 tools, disabled call rejection, clipboard enable/call/disable and rejection after disable all passed. Discovery does not launch the server.
- Incorporated regression suites: Argus 64 passed (one slow test deselected), Echo 48, Funes 95, Cassandra 25, Disk 107 passed and one skipped. Argus was repeated with unhandled thread exceptions treated as errors after fixing its worker shutdown race.
- All seven native UI builds across Talos and Hermes completed. Talos screen, clipboard, activity, audio, services and disk pages were opened through the browser with synthetic/offline engines. Clipboard ran independently of screen capture.
- Desktop and mobile module controls use the canonical family theme, local fonts, generated family-style icons and the common Faustus control. The independent finish review records its precise scope separately.

- Audio echo clean-up, chapters and bench (28 Oct 2026): 51 new tests (echo and chapters 40, bench 11) plus the whole Funes suite (558 passed; 4 failures that exist without these changes: `test_cli` x2, `test_manifest`, `test_timeparse` reference the standalone Funes entry point, id and `mcp_server.py` that the absorption removed). Live on an isolated instance (private port, temporary data, all other modules OFF): `scribe_chapters` through `/api/agent/call` with the real global model wrote five chapters for a 20-minute Spanish meeting and answered from the store on the second call; `scribe_echo_check` listed and removed two echo lines; `scribe_bench` ran the music and silence cases with faster-whisper small on CPU (99 % found, 0 lines for silence, both inside their thresholds). A headless browser showed the chapters panel, five ticks on the waveform, the two new switches and the bench table; the full bench with the four cases was measured separately (see README).

Hardware audio capture, GPU inference, live purchases, mail ingestion and destructive disk operations were not triggered in these checks. Existing engine tests and static tool parity preserve those capabilities; these checks do not claim a fresh live validation of every external provider or device.

Source commits and native tool inventory are recorded in `provenance/`. Data adoption only writes the central module-to-folder mapping, with every module OFF. Private preservation receipts are kept outside the public repository.
