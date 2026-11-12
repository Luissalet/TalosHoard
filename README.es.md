# Talos's Hoard

La memoria y la salud de tu ordenador en un único proceso local: historial de pantalla, portapapeles, actividad, audio y reuniones, vigilancia de servicios y espacio en disco.

## Qué es

Talos's Hoard registra lo que ocurre en tu PC y responde preguntas sobre ello: qué había en pantalla, qué copiaste, en qué trabajaste, qué se dijo en una reunión, qué servicio se cayó y por qué, y qué está llenando tu disco. Funciona en local, guarda sus datos en tu máquina y lo expone todo a un asistente por MCP.

Se organiza en seis módulos independientes. Cada módulo está **apagado en el primer arranque**: abrir la app o descubrir sus herramientas MCP no inicia ningún recolector, vigilante, modelo ni escáner. Un interruptor explícito activa un módulo; desactivarlo detiene sus procesos antes de cerrar su base de datos. Tus elecciones se conservan. El portapapeles puede funcionar mientras la captura de pantalla, la actividad y el audio siguen apagados.

## Módulos y qué hacen

| Módulo | Qué cubre |
| --- | --- |
| Pantalla | Capturas, OCR, búsqueda visual y de texto completo, fotogramas similares, línea temporal, actividad por aplicación, exclusiones, modo privado, importación y vigilancia de carpetas, fotogramas fijados, exportaciones y retención |
| Portapapeles | Historial de texto e imágenes, detección de tipo, OCR, búsqueda, favoritos, editar, borrar y restaurar, copiar, paquetes |
| Actividad | Ventanas en primer plano, gestión de inactividad y bloqueo, archivos recientes, commits de Git, proyectos, clasificaciones, reglas de privacidad, resúmenes, exportaciones y recuerdo entre módulos |
| Audio | Grabación de micrófono y sistema, importación de archivos, transcripciones en directo, búsqueda, notas, etiquetas, exportaciones, actas de reuniones, capítulos, voz a texto compartida con respaldo GPU/CPU |
| Servicios | Comprobaciones de salud, incidencias y causas probables, registros, historial de GPU, bus de eventos, incidencias de trabajos, comprobaciones de sitios, DNS, certificados y dominios, auditorías SEO/GEO programadas, avisos, políticas de reinicio |
| Disco | Escaneo y árbol de espacio, puntos calientes, archivos más grandes y antiguos, estadísticas por extensión, limpieza, salvaguardas de papelera y borrado permanente, scripts, división en ZIP, gestión de copias de modelos |

Las interfaces nativas están en `/screen/`, `/clipboard/`, `/activity/`, `/audio/`, `/services/` y `/disk/`, y comparten el tema Hoard y el copiloto de Faustus.

**Pantalla**
- Captura pantallas con OCR, que se pueden buscar por texto y por parecido visual, con línea temporal, actividad por aplicación, exclusiones, modo privado y reglas de retención; puedes pausar, borrar un intervalo, importar capturas o vigilar una carpeta.

**Portapapeles**
- Historial de texto e imágenes con detección de tipo y OCR, búsqueda, favoritos y restauración.
- **Reunir copias** combina hasta 20 recortes en un texto con avisos de origen y fecha, el separador que elijas, copia o descarga TXT; las selecciones pueden guardarse con nombre.
- **Leer texto** recorre por páginas los recortes largos; **Comparar dos copias** muestra una diferencia literal por líneas de dos recortes. Previsualizar nunca cambia los recortes guardados.

**Actividad**
- Las ventanas en primer plano, los archivos recientes y los commits de Git forman una línea temporal de proyectos con resúmenes y exportaciones.
- **Proyectos -> Retomar** lee las ventanas, aperturas de archivos y commits registrados de un proyecto durante un intervalo hacia atrás, para continuar donde lo dejaste. Un intervalo vacío significa que no hay evidencia registrada, no que no hubo trabajo.
- Borrador de **pantalla a procedimiento**: las ventanas, recortes, capturas y archivos de un intervalo se segmentan en pasos con evidencia, entradas con nombre (los valores que parecen secretos se enmascaran), salidas y una lista de incógnitas. Es un borrador para que una persona o un agente lo verifique y nunca ejecuta nada.

**Audio**
- Transcripción en directo y final del micrófono y del audio del sistema, importación y exportación, búsqueda, notas y etiquetas.
- La limpieza de eco elimina las líneas del micrófono que solo repiten lo que dijo la otra pista; las reuniones de tres minutos o más se dividen en capítulos con el modelo global, visibles en la página de la sesión, en la forma de onda, en el acta y en las exportaciones.
- **Reunión a requisitos**: cada frase se corta en cláusulas y se etiqueta con reglas lingüísticas en español e inglés como compromiso firme (responsable, contraparte y día solo cuando las palabras lo dicen), propuesta, pregunta abierta, decisión o requisito, cada una con la pista exacta y el segmento de audio de origen. «Podríamos», «quizá» y todo condicional son propuestas, nunca compromisos. Los elementos pueden vincularse a una referencia de encargo y exportarse como Markdown, JSON o como compromisos para la app de personas.
- Un banco de transcripción ejecuta grabaciones con guion conocido por el motor configurado y puntúa palabras encontradas, lado correcto, eco filtrado y líneas inventadas.
- **Buscar en esta sesión** busca dentro de una sola sesión.

**Servicios**
- Comprobaciones de salud, incidencias con causas probables, registros, historial de GPU y VRAM, disponibilidad, políticas de reinicio, lista de vigilancia, detección de reinicios y un registro de auditoría de las llamadas de agentes.
- Sitios públicos: disponibilidad, certificados TLS, caducidad de dominios y DNS. Un sitio puede activar una auditoría SEO/GEO programada (`seo_interval_h`, de 1 a 720 horas): la primera con éxito es la referencia, las siguientes se comparan con la anterior y con la referencia, y una caída de puntuación o un hallazgo crítico nuevo genera un aviso en el bus de la familia. Las categorías que no se pudieron medir nunca cuentan como empeoramiento.

**Disco**
- Escaneos con árbol y mapa de árbol (navegable con teclado), puntos calientes, archivos más grandes y antiguos, un catálogo de basura, búsqueda de archivos, explicación de carpetas, scripts de limpieza, borrado a la papelera o permanente con salvaguardas, división en ZIP y gestión de copias de modelos.

**Recuerdo entre módulos**
- El recuerdo consulta pantalla, portapapeles y audio a la vez dentro de este proceso.

## Cómo se ejecuta

Python 3.11+; se requiere Windows para la captura de escritorio y las integraciones del sistema.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m talos_hoard --no-browser
```

Abre `http://127.0.0.1:5220`. `Start.cmd` prepara el entorno si hace falta. El servidor nunca abre una ventana por su cuenta; el Hoard Hub lee `faustus-plugin.json` para el lanzamiento explícito y el acceso MCP.

| Variable | Para qué sirve |
| --- | --- |
| `TALOS_DATA_DIR`, `TALOS_PORT` / `--port` | Carpeta de datos central y puerto. |
| `TALOS_URL`, `TALOS_TOKEN_FILE` | Ajustes del puente MCP. |

Una instalación nueva guarda los datos en `data/<módulo>`. Para conservar el historial de las apps originales, con todos los módulos apagados ejecuta `scripts\adopt_data.py --parent "C:\ruta\a\Hoards"`: solo escribe `data/modules.json` y deja donde están las bases de datos, capturas, imágenes del portapapeles, grabaciones, ajustes, tokens e instantáneas de disco. Los datos de un módulo también pueden reubicarse en `data/native/<módulo>/data`, moviendo árboles completos. Desactivar un módulo nunca borra su historial; al activarlo, el motor nativo retoma sus ajustes de privacidad y retención guardados.

## Conexión con Faustus y la familia Hoard

- **MCP**: `GET /api/agent/tools` lista un centenar de herramientas y `POST /api/agent/call` usa el token de `data/mcp-token`. Las llamadas a un módulo apagado responden `module_disabled` y nunca lo activan. `python mcp_server.py` es el puente por stdio; su catálogo funciona sin un servidor en marcha y nunca lanza uno. Los módulos se controlan con `GET /api/modules`, `PUT /api/modules/{id}` (`{"enabled": true|false}`) y `POST /api/modules/stop-all`, o con las herramientas `talos_modules` y `talos_set_module`.
- **Grupos de herramientas**: pantalla (`screen_*`), recortes (`clip_*`, incluidos `clip_bundle`, `clip_compare`, `clip_selections`), actividad (`activity_*`, incluidos `activity_project_resume` y `activity_procedure_draft`), audio (`scribe_*`, incluidos `scribe_requirements`, `scribe_chapters`, `scribe_echo_check`, `scribe_bench`), servicios (`service*`, `sites_*`, incluidos `sites_seo`, `sites_seo_run`, `sites_seo_baseline`), disco y recuerdo. Todas las herramientas están listadas en [`provenance/`](provenance/).
- **Copiloto**: Talos sirve él mismo el panel de Faustus (`/api/copilot/*`, también bajo la ruta de cada módulo). La interfaz de Servicios informa al asistente del servicio, sitio, incidencia o filtro en pantalla; la conversación vive en Faustus.
- **Hub**: eventos y avisos, y entradas de compatibilidad para las identidades retiradas que mantienen funcionando los tokens, referencias y llamadas entre apps de la familia sin ejecutar los servidores antiguos. Los compromisos de las reuniones alimentan la app de personas, y las herramientas de audio también responden en `/legacy/funes/`.
- **Modelos**: las peticiones al modelo de texto usan el servicio de modelo global configurado en la familia; los motores de audio y visión conservan sus descargas locales opcionales de modelos y sus arrendamientos de GPU. Ningún modelo se carga mientras su módulo está apagado.
- **Skills**: `hoard-what-happened`, `hoard-daily-digest`, `systematic-debugging` y `local-voice-comparison` se ofrecen a los agentes que se conectan.

## Estructura del proyecto

| Ruta | Contenido |
| --- | --- |
| `talos_hoard/` | Servidor combinado, ciclo de vida de los módulos y catálogo de herramientas |
| `argus/`, `cassandra_hoard/`, `diskhoard/`, `echo/`, `funes_hoard/` | Motores de los módulos Pantalla, Servicios, Disco, Portapapeles y Audio/Actividad |
| `ui/` | Proyectos de interfaz nativa (`npm ci && npm run build` en cada uno; los recursos compilados están incluidos) |
| `compatibility/` | Manifiestos que conservan las identidades retiradas |
| `provenance/` | Licencias y commits de origen exactos; las fuentes Cinzel y Source Sans 3 se distribuyen con sus licencias SIL Open Font |
| `scripts/` | Adopción de datos, generador del catálogo, servidor de QA sintético, verificación MCP |
| `tests/`, `legacy_tests/` | Suites de pruebas |

```powershell
python -m pytest tests -q      # necesita pytest y pytest-asyncio
```

`scripts/qa_server.py` arranca una instancia sintética con captura y audio simulados y motores de red sin conexión.

Licencia: MIT (véase `LICENSE`).
