# Talos verification

Verified on Windows with isolated synthetic histories. Original histories were not opened by the test servers.

- Product suite: 14 passed, including independent OFF defaults, saved state, native module APIs, Funes audio compatibility, strict switch values and retained external data locations.
- Streaming: the first SSE event arrives before the producer completes; disabling cancels a live stream before closing its engine. Media responses retain native streaming and range support.
- Shutdown: OFF intent persists before a deliberately blocked shutdown; the dashboard remains responsive.
- Actual stdio MCP: discovery of 93 tools, disabled call rejection, clipboard enable/call/disable and rejection after disable all passed. Discovery does not launch the server.
- Incorporated regression suites: Argus 64 passed (one slow test deselected), Echo 48, Funes 95, Cassandra 25, Disk 107 passed and one skipped. Argus was repeated with unhandled thread exceptions treated as errors after fixing its worker shutdown race.
- All seven native UI builds across Talos and Hermes completed. Talos screen, clipboard, activity, audio, services and disk pages were opened through the browser with synthetic/offline engines. Clipboard ran independently of screen capture.
- Desktop and mobile module controls use the canonical family theme, local fonts, generated family-style icons and the common Faustus control. The independent finish review records its precise scope separately.

Hardware audio capture, GPU inference, live purchases, mail ingestion and destructive disk operations were not triggered in these checks. Existing engine tests and static tool parity preserve those capabilities; these checks do not claim a fresh live validation of every external provider or device.

Source commits and native tool inventory are recorded in `provenance/`. Data adoption only writes the central module-to-folder mapping, with every module OFF. Private preservation receipts are kept outside the public repository.
