# Talos's Hoard: ficha para Faustus

## Qué añade esta versión
- Voz a texto de respaldo en CPU (`transcribe_engines`, `transcribe_file` con `engine`; ajustes «Motor» y «Whistle para audios cortos»).
- Reuniones a requisitos y pendientes (`scribe_requirements`, `scribe_requirement_link`; REST bajo `/audio/api/sessions/{id}/requirements`).
- Observación de pantalla a borrador de procedimiento (`activity_procedure_draft`; REST `POST /activity/api/procedure/draft`).
- Página `/static/analysis.html` (castellano e inglés) con ambas vistas.
- `faustus_attention` y `faustus_farm` (y la tarjeta de la granja del panel) siguen a Faustus cuando corre en una Spark: prueban `CASSANDRA_FAUSTUS_URL` y luego la dirección que publica el Hub, y aceptan direcciones de la tailnet (`*.ts.net`, `100.64.0.0/10`) además de loopback. El resultado trae `url` (la que contestó) y, si ninguna contesta, `tried`.
- El catálogo de `/api/agent/tools` pasa a 107 herramientas.
- En Disco, la carpeta actual y el espacio libre de la barra de rutas seleccionan la ruta completa para copiarla con `Ctrl+C`.

## Voz a texto de respaldo
- Dos motores: faster-whisper (el preciso, GPU cuando la hay) y Whistle, un modelo de unos 17 MB que reconoce español, inglés, alemán, francés, italiano, neerlandés y polaco en CPU en décimas de segundo por audio corto.
- En Ajustes, «Motor» elige `auto`, `whisper` o `whistle`; `auto` usa faster-whisper y pasa a Whistle cuando no puede cargarse. «Whistle para audios cortos» fija los segundos por debajo de los cuales se transcribe con Whistle primero (0 = solo como respaldo).
- `transcribe_file` acepta `engine` por trabajo y devuelve `engine` junto al texto, los segmentos y las palabras con sus tiempos; `transcribe_engines` dice qué motores hay, sus idiomas y qué hace `auto`.
- El motor elegido se aplica también a las grabaciones e importaciones de sesiones, no solo a la API.
- El modelo se descarga una vez y se guarda en la caché del paquete; `FUNES_WHISTLE_WEIGHTS` apunta a un fichero ya descargado. El contador anónimo del paquete queda desactivado salvo que se ponga `CACTUS_TELEMETRY`.
- Se instala aparte: `pip install cactus-compute` (o el extra `whistle`). Sin él, todo sigue funcionando con faster-whisper.

## Reuniones
- Reglas lingüísticas deterministas, sin modelo, en castellano e inglés: compromiso firme, propuesta, pregunta abierta (con quién debe responder), decisión y requisito.
- Cada elemento da el indicio exacto (`cue`, `cue_rule`), la confianza y el fragmento de origen con reproducción (inicio, fin, texto).
- «Podríamos», «could», «maybe we», condicionales y decisiones negadas o pendientes nunca son compromisos firmes.
- Los requisitos y decisiones se vinculan a un entregable o decisión con una referencia externa libre (no hay CRM).
- Exporta Markdown, JSON y `commitments` (formato `talos.commitment/1`, que People importa con `commitments_import_talos`).

## Procedimiento desde pantalla
- Pasos: cambios de aplicación, formularios, copiar y pegar, clics, archivos, cada uno con su evidencia (eventos y captura más cercana).
- Entradas con nombre; los valores que parecen secretos se enmascaran en toda la salida.
- Incógnitas explícitas: intención no visible, estados no observados, clics sin elemento, huecos, pegados no vistos.
- Es solo un borrador: no ejecuta nada en el ordenador observado.

## Límites
- Talos no registra clics ni pulsaciones; con el registro propio del módulo solo hay ventanas, portapapeles, capturas y archivos. Un registro de eventos aportado puede traer más.
- Las reglas son heurísticas: pueden fallar con frases largas, ironía o transcripciones con errores; por eso se muestra el indicio.
- Si se regenera la transcripción, los identificadores de elemento pueden cambiar y los vínculos quedan huérfanos (se listan como tales).
- La interfaz de audio en React no se ha reconstruido; las vistas nuevas están en `/static/analysis.html`.

## Pruebas
- `python3 -m pytest -q tests` (incluye `tests/test_meeting_requirements.py`) y `legacy_tests/funes_hoard`.

## Pendientes
- Ninguno abierto.

## Skills for the agents that connect

This app carries procedures from the skill library of the family's workspace for the agents that connect to it: `hoard-what-happened`, `hoard-daily-digest`, `systematic-debugging`, `local-voice-comparison`. They are named in what an agent reads on connecting, read with `skills_list` and `skill_read`, searched and assigned with `skills_library` and `skills_assign`, and offered as prompts. The person chooses them on the skills page (`/api/agent/skills/page`) or in the hub's Skills tab; the `skills` block of `faustus-plugin.json` holds what the app asks for by default.

## App Dock

El servidor fusionado se puede enmarcar dentro del App Dock de Faustus: una navegación enmarcada (`iframe`/`frame`, solo GET) pasa la guarda cuando la página que la abre es un origen de Faustus conocido (el configurado o el que el Hub publica en su colocación). Los orígenes ajenos y los marcos `embed`/`object` se siguen rechazando. Lo cubre `tests/test_modules.py::test_dock_frames_from_a_known_faustus_origin_only`.
