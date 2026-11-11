# Talos's Hoard

**Reuniones: requisitos y pendientes por reglas; pantalla: borradores de procedimiento.** Dos
análisis de solo lectura, deterministas y sin modelo: no llaman a ningún modelo de lenguaje, no
escriben en el ordenador observado ni arrancan ningún recolector.
*Reunión → requisitos* (`scribe_requirements`, HTTP `GET /audio/api/sessions/{id}/requirements`):
cada frase de una reunión transcrita se corta en cláusulas y se etiqueta con reglas lingüísticas del
castellano y del inglés (verbos modales, condicionales, interrogativas, marcadores explícitos de
decisión) como **compromiso** firme (responsable, interlocutor y fecha solo si las palabras los
dicen), **propuesta**, **pregunta abierta** (con quién debe responder: un nombre en vocativo, la otra
parte, el grupo o nadie), **decisión** o **requisito**. Cada elemento indica el indicio exacto que lo
activó (`cue`), la regla (`cue_rule`), una confianza y su fragmento de origen (`segment` y `playback`:
segundos de inicio y fin, texto de la transcripción y la llamada a `scribe_transcript` que lo lee; la
página reproduce ese tramo de audio). «Podríamos», «could», «maybe we», «quizá», «intentaré»,
«I'll try» y todo condicional son propuestas, nunca compromisos; una decisión negada o pendiente
(«todavía no hemos decidido») no es una decisión. Los requisitos y las decisiones se vinculan al
entregable o a la decisión de un encargo con una referencia externa libre (`scribe_requirement_link`,
`POST/DELETE /audio/api/sessions/{id}/requirements/links`; `engagement_ref` filtra por ella); la
referencia es solo texto, no hay CRM. Se exporta con `format` `md` (informe Markdown, títulos en `es`
o `en`) o `json`; `format: commitments` devuelve solo los compromisos firmes en el formato
`talos.commitment/1` que importa People's Hoard (`commitments_import_talos`), con todo lo demás en
`rejected` y el motivo.
*Pantalla → procedimiento* (`activity_procedure_draft`, HTTP `POST /activity/api/procedure/draft`):
las ventanas en primer plano, los recortes del portapapeles, las capturas y los archivos recientes de
un intervalo (hasta seis horas; o un registro de eventos que tú pases, que puede traer también clics y
texto escrito) se segmentan en pasos (cambios de aplicación, formularios, copiar y pegar entre
aplicaciones, clics, archivos). Cada paso conserva su evidencia (los eventos y la captura más
cercana), los valores escritos o pegados pasan a ser entradas con nombre (los que parecen secretos se
enmascaran en toda la salida), los valores copiados y pegados y los archivos son salidas, y lo que el
registro no puede decir se lista como incógnitas (intención, estados nunca observados, clics sin
elemento, huecos, un pegado que no se vio). Talos no registra clics ni pulsaciones: lo que ocurre
dentro de una ventana es solo lo que muestran los recortes y las capturas. Es un borrador para que lo
verifique una persona o un agente; nunca ejecuta nada en el ordenador observado. Ambos están en
`/static/analysis.html` (castellano o inglés) y añaden tres herramientas: el catálogo pasa a **107
herramientas** (105 más los dos controles de módulos).

**Servicios: vigilancia periódica del SEO y GEO de las webs públicas.** Una web de la lista
**Webs públicas** se apunta con `seo_interval_h` (horas entre auditorías, de 1 a 720; se edita en el
editor de la lista, con `sites_watch` o con `POST /services/api/sites`). Cada auditoría es una
llamada a la herramienta `site_audit` de la Hoard de diseño a través del hub; Servicios lee la
puntuación, la de cada categoría y los hallazgos, y guarda todas las ejecuciones (una fallida
guarda su causa y se reintenta una hora después). La primera auditoría correcta es la **línea
base**; cada ejecución se compara con la anterior (cambio de puntuación, categorías que se
movieron, hallazgos nuevos o resueltos) y con la línea base (`sites_seo_baseline` o **Aceptar como
referencia** la mueve tras un arreglo). Avisos en el bus de la familia: `cassandra.site.seo_drop`
cuando la puntuación queda al menos `seo_drop_points` (2 por defecto) por debajo de la mejor de las
últimas siete ejecuciones y por debajo de la anterior, y `cassandra.site.seo_critical` cuando aparece
un hallazgo crítico que la ejecución anterior no tenía; la primera ejecución no avisa de nada y el
aviso de Boop no lleva nombre de web, puntuación ni texto de hallazgos. MCP: `sites_seo` (estado,
deriva, hallazgos críticos y, con `history`, las últimas ejecuciones), `sites_seo_run` (auditar
ahora) y `sites_seo_baseline`; HTTP `GET /services/api/sites/seo`, `GET /services/api/sites/{id}/seo`,
`POST /services/api/sites/seo/run` y `POST /services/api/sites/{id}/seo/baseline`. La tarjeta de
webs del Panel muestra puntuación y cambio junto a cada web y un bloque **SEO y GEO** en su detalle.
La herramienta de auditoría es de Vitruvius y su sobre `site-audit/1` está verificado en vivo
contra una web pública real: las categorías que no se pudieron medir (`score: null`) nunca se
leen como un empeoramiento, los hallazgos que requieren criterio de una persona se cuentan aparte
(`counts.judgement`) y nunca disparan un aviso, y una auditoría que responde `ok: false` se guarda
como fallida con su propia causa y pista. Si Vitruvius está caído o su módulo de diseño apagado,
la ejecución queda guardada como fallida con ese motivo y nada más cambia. `CASSANDRA_SEO=0` apaga la vigilancia. El catálogo pasó entonces a **104 herramientas**
(tres nuevas para esta vigilancia, cuatro para audio).

**Audio: limpieza de eco, capítulos de reunión y banco de transcripción.** Con altavoces,
el micrófono vuelve a oír al otro lado y la pasada final escribía la misma frase dos
veces, la segunda como «yo». Al terminar la transcripción se descartan las líneas del
micrófono que sólo suenan mientras suena la pista del sistema (60 % o más de sus
fotogramas activos, y al menos el doble de bajas) o que repiten palabra por palabra lo
que dijo la otra pista en un margen de dos segundos; la sesión guarda cuántas
(`stats.final.echo`). Ajuste **Quitar el eco del micrófono** (activado por defecto);
`scribe_echo_check` lista las líneas de eco de una sesión ya hecha y, con `apply: true`,
las borra.
Las reuniones y entrevistas de tres minutos o más se dividen en 2-12 **capítulos** con
una sola llamada sin herramientas al modelo global: cada inicio se ajusta al comienzo de
una línea real de la transcripción, se ordena, se quitan duplicados y el primero pasa a
la primera línea; los títulos tienen 2-6 palabras en el idioma de la transcripción. Los
capítulos salen en la página de la sesión (pulsar salta), como marcas sobre la forma de
onda, en el acta y en las exportaciones MD/TXT. Ajuste **Dividir en capítulos al
terminar**; MCP `scribe_chapters` (`regenerate` vuelve a preguntar), HTTP
`GET/POST /audio/api/sessions/{id}/chapters`.
El **Banco de transcripción** (Ajustes → Audio, MCP `scribe_bench` / `scribe_bench_status`,
HTTP `/audio/api/bench`) pasa cuatro grabaciones con guion conocido (voces superpuestas,
eco por altavoces, música de fondo y silencio) por el motor configurado, el filtro de
alucinaciones, la limpieza de eco y la unión de pistas; puntúa palabras halladas, lado
correcto, eco colado, líneas inventadas y segundos, lo compara con la misma salida sin
limpieza de eco y guarda el resultado en `<datos de audio>/bench-results.json`. Medido con
faster-whisper small en CPU int8: llamada 90 % de palabras halladas, 100 % del lado
correcto, 0 colado, 0 inventadas; llamada con eco por altavoces 90 %, 100 % y 0 colado
(23 líneas de eco quitadas; sin limpieza se colaban 18 y salían 46 líneas en vez de 20);
música 99 %; silencio 0 líneas. Cuatro herramientas de audio nuevas:
`scribe_chapters`, `scribe_echo_check`, `scribe_bench`, `scribe_bench_status`. Las
grabaciones de prueba son de terceros con licencia CC0 y el método sigue un proyecto con
licencia MIT; véase `funes_hoard/audio_memory/NOTICE-meeting-recorder.md`.

En **Audio → Sesión**, **Buscar en esta sesión** abre la búsqueda con su ID
exacto, aunque otra sesión tenga el mismo título. Texto, tipo y fechas se
combinan con ese ámbito. **Buscar en todas las sesiones** quita sólo el ámbito
y conserva los campos. Un error ofrece reintento; cambiar criterios descarta
respuestas anteriores. Los enlaces mantienen el minuto original, incluido00:00.
Los recuentos son coincidencias devueltas dentro del límite nativo, no un total
global. `GET /audio/api/search` y `scribe_search` admiten `session_id` opcional;
omitido o vacío consulta todas, un ID inexistente devuelve cero coincidencias.
Siguen97 herramientas y el mismo índice/tokenizador nativo. Sólo lee texto
guardado: no inicia grabación, transcripción ni modelos. Los filtros se conservan
al quitar el ámbito, sin prometer persistencia tras recargar o cambiar de página.

Actividad → Hoy → **¿Dónde lo dejé?** permite consultar contextos distintos antes
de una fecha/hora local opcional, pedir hasta20 e incluir las categorías omitidas
por defecto. Fecha vacía conserva ahora/fin del día elegido. Consultar/Reintentar
aplica los campos explícitamente; Volver a este día restaura los tres contextos
iniciales. El resultado muestra el corte real devuelto con zona, máximo pedido y
categorías. Un corte futuro se reduce a ahora mediante el cálculo nativo.
Los proyectos conocidos tienen prioridad sobre las apps sin proyecto en la ventana
de tres días; no es una lista cronológica global. Ver en la línea de tiempo sigue
siendo una navegación explícita. Los campos pendientes se conservan ante error y
refresco del copilot sobre la consulta aplicada; editar descarta respuestas viejas
y cambiar día restablece filtros. Los títulos no prueban ediciones ni se abren o
verifican rutas. HTTP y MCP97 `activity_where_was_i` usan el motor existente.

En Historial del portapapeles, **Aplicación registrada** filtra por el nombre de
proceso guardado exacto, distinguiendo mayúsculas y minúsculas. Combina texto y
tipo; **Todas las aplicaciones** limpia sólo la aplicación. Se muestran hasta
200 copias recientes o 100 coincidencias por relevancia, no un total global.
El origen es el último retenido por la deduplicación nativa, no todas las
aplicaciones anteriores. Cambiar filtros descarta respuestas antiguas; reintentar
conserva filtros, lector, selección y borrador de reunión. La interfaz mantiene
su castellano actual. HTTP listado/búsqueda y `clip_search` ya admiten `app`;
`clip_recent` también lo admite ahora como opción, con el mismo filtro nativo y
97 herramientas. Leer y filtrar no captura, carga modelos ni escribe copias.

En **Actividad → Proyectos**, **Retomar** consulta ventanas en primer plano,
aperturas de archivos y commits registrados del proyecto elegido mediante el
cálculo nativo `activity_project_resume`. El detalle tiene su propio intervalo
(1–180 días) y máximo por tipo de evidencia (1–10), independientes del período de
la tabla. Cambiar un parámetro retira el resultado anterior; un error conserva
selección y parámetros para reintentar. El wrapper HTTP de la interfaz es
`POST /activity/api/projects/resume` con `project`, `days` y `limit`; la herramienta
MCP existente y el catálogo conjunto de 97 herramientas no cambian.

Se conservan las reglas nativas de nombre exacto del proyecto. Sólo aparecen
ventanas de al menos diez segundos; el tiempo activo incluye todos los episodios
activos del intervalo. La última actividad en primer plano puede ser desconocida
aunque existan aperturas registradas. Un intervalo vacío no prueba que no hubiera
trabajo. Los títulos no prueban ediciones o pendientes; las rutas registradas no
se comprueban ni se abren. Consultar contexto no activa capturas, modelos,
descubrimientos de archivos ni otras aplicaciones.

<img src="app-icon.png" width="96" alt="Talos icon">

Memoria de pantalla, portapapeles, actividad, audio, vigilancia de servicios y gestión del disco en un único proceso. Absorbe **Argus, Echo, Funes, Cassandra y DiskHoard**, conservando sus motores, funciones e historiales.

[English](README.md) · [Inventario completo de herramientas](provenance/CAPABILITIES.md) · [Procedencia del código](provenance/sources.json)

## Funciones independientes

**Todas desactivadas en la primera apertura.** Abrir Talos o consultar sus herramientas MCP no pone en marcha capturas, vigilantes, escaneos ni modelos. Cada función tiene su interruptor; puedes usar portapapeles con pantalla, actividad y audio apagados. La elección se recuerda entre sesiones. «Desactivar todas» detiene los módulos sin borrar sus datos.

- **Pantalla:** capturas, OCR, búsqueda visual y textual, imágenes similares, línea de tiempo, exclusiones, modo privado, importación de imágenes y carpetas vigiladas, fijados, exportación y retención.
- **Portapapeles:** historial de texto e imágenes, tipos, OCR, búsqueda, favoritos, edición, borrado/restauración, copiar y agrupar.
- **Actividad:** ventanas, aplicaciones, inactividad y bloqueo, archivos recientes, commits, proyectos, clasificación, privacidad, resúmenes, exportaciones y memoria conjunta.
- **Audio:** micrófono y sonido del sistema, importación, transcripción en directo, limpieza de eco entre pistas, búsqueda, notas, etiquetas, exportaciones, actas, capítulos de reunión, banco de transcripción y servicio compartido de transcripción.
- **Servicios:** salud, incidentes y causas probables, registros, GPU, bus de eventos, trabajos fallidos, sitios/DNS/certificados/dominios, auditorías SEO/GEO periódicas con línea base y deriva, avisos y políticas de reinicio.
- **Disco:** análisis de espacio, árbol, archivos grandes/antiguos, extensiones, limpieza, papelera y borrado definitivo con sus comprobaciones, scripts, selector de carpeta, ZIP divididos y copias de modelos.
  Pulsa la carpeta actual o el espacio libre de la barra de rutas y usa `Ctrl+C` para copiar la ruta completa.

Cada módulo conserva su interfaz completa. Todo comparte el tema de los Hoards, el icono de Talos y el botón de Faustus.

El copilot de Faustus lo sirve el propio Talos: `GET /api/copilot/info`, `GET /api/copilot/panel.js`, `POST /api/copilot/proxy` y `GET /api/copilot/launcher.js` (las páginas de cada módulo también responden bajo `/<módulo>/api/copilot/`). La interfaz de Servicios registra `window.hoardCopilot.context()` para que el asistente vea el servicio, la web, el incidente o el filtro en pantalla; la conversación vive en Faustus, no en Talos.

En el Historial del portapapeles puedes seleccionar hasta 20 copias guardadas y **Reunir copias**: revisar texto, origen y fecha, cambiar el orden, elegir separador, copiar todo junto o descargar TXT. La selección se conserva al filtrar y sus identificadores siguen visibles para quitar entradas. Las imágenes aportan solo el OCR ya guardado, sin adjuntar el archivo. Se leen hasta 20.000 caracteres por copia, con aviso explícito si el texto es parcial. La vista previa no modifica el historial y reutiliza `clip_bundle`; API propia `POST /clipboard/api/clips/bundle`. La herramienta nativa de reunir copias conserva su contrato.

**Leer texto** abre una copia no-imagen del Historial en páginas literales y seleccionables de 4.000 caracteres, también más allá del prefijo de Reunir. Anterior/Siguiente usan offsets nativos de Python y conservan los emoji en sus fronteras. Leer conserva búsqueda, selección y borradores; cerrar, cambiar de copia o refrescar descarta respuestas antiguas. `GET /clipboard/api/clips/{id}/text?offset=0&max_chars=4000` delega en `clip_get`, incluidas sus comprobaciones de contenido oculto o ausente. El recorte heredado de respuesta MCP sigue vigente y es independiente del tamaño de página. No se añade una acción de copiar ni de captura.

Con exactamente dos copias seleccionadas, **Comparar dos copias** lee explícitamente A/B con el mismo lector nativo y muestra diferencias literales por líneas, orígenes/fechas y conteos. Espacios, tabulaciones, LF/CRLF y ausencia de salto final son visibles. Intercambiar A/B cambia el orden; editar y refrescar por copilot retira resultados incompatibles y conserva borradores. Copiar incluye snapshot y alcance consultados. Sólo texto guardado: imágenes aportan OCR ya almacenado, sin ejecutarlo, comparar píxeles, capturar ni leer el portapapeles real. Usa difflib de Python, sin modelo/dependencia nueva; no promete diff mínimo, equivalencia semántica ni parche aplicable.

`clip_compare {left_id,right_id,max_chars_per_clip}` y `POST /clipboard/api/clips/compare` comparten cálculo. Reutiliza IDs distintos y límite del lector20.000caracteres por texto (herramienta8.000por defecto; UI20.000). `left.truncated`, `right.truncated` y `text_scope=extracts` señalan extractos; si coinciden no se afirma igualdad de clips completos. UI/API reciben todas las filas. La respuesta agente/MCP conserva el recorte aproximado20KB heredado: puede cortar filas y añadir un bloque **superior** `truncated`, separado del carácter parcial de cada clip; conteos/total_rows describen el cálculo completo. Una fila anidada muy grande puede superar ese presupuesto heredado. No se cambió ni eludió el recorte global. Consulta un prefijo menor o clip_get para el texto y no presentes respuesta recortada como diff completo. Historial y selecciones no se modifican; copiar resultado requiere acción explícita.

## Arranque

Dentro de **Reunir copias**, **Selecciones guardadas** conserva nombre, hasta 20
IDs, orden, separador y opción de origen/fecha. Cargar sustituye el borrador
editable; Revisar lee el contenido actual. Permite guardar cambios (incluido
renombrar), guardar como nueva y eliminar sólo la selección guardada. Ninguna de
esas acciones copia, mueve, fija ni edita los clips originales. Los IDs ausentes
siguen visibles para quitarlos y la lectura nativa mantiene su error explícito.
Las herramientas `clip_selections`, `clip_selection_save` y
`clip_selection_delete` comparten metadatos SQLite con
`GET/POST /clipboard/api/clips/selections` y
`DELETE /clipboard/api/clips/selections/{id}`. Tras recargar se conservan IDs y
opciones; no se guarda texto ni imagen dentro de la selección. La captura, OCR
y activación de módulos conservan sus controles explícitos existentes.

Python 3.11 o posterior; las integraciones de escritorio de Windows requieren Windows. Ejecuta `Start.cmd` o sigue los comandos del [README en inglés](README.md#run). Abre `http://127.0.0.1:5220`. El servidor no abre ventanas por su cuenta. El Hub lo descubre mediante `faustus-plugin.json` y permite iniciarlo expresamente.

## Conservar los datos existentes

Con todos los módulos apagados:

```powershell
.venv\Scripts\python.exe scripts\adopt_data.py --parent "C:\ruta\a\las Hoards"
```

Solo escribe el mapa `data/modules.json`. Las bases de datos, capturas, imágenes, grabaciones, ajustes, tokens e instantáneas de disco permanecen **en sus carpetas originales**, sin copiar, mover ni borrar. Conserva esas carpetas. Sin adopción se usan carpetas nuevas `data/<módulo>`.

Al activar una función se reanuda su comportamiento nativo, incluidos sus ajustes previos de privacidad y retención. Al desactivarla se espera a que termine el trabajo en curso antes de mostrar «Desactivada». Las transmisiones de eventos se desconectan; las descargas grandes se sirven por partes.

## API, MCP y compatibilidad

En Portapapeles → Historial, **Ver imagen** abre el PNG guardado completo sin
copiarlo al portapapeles. Puedes ajustarlo al espacio disponible o verlo al 100%
con desplazamiento local, consultar dimensiones/origen/ID y reintentar una carga
fallida. Conserva filtros y selección; el lector de texto sigue disponible.
Usa las rutas nativas de imagen y metadatos. `clip_get` de MCP mantiene dimensiones
y texto OCR: no devuelve píxeles ni realiza OCR nuevo.

El catálogo contiene **107 herramientas**: las 91 originales, tres para selecciones guardadas, clip_compare, dos para consultar/cambiar los módulos, seis de audio (`scribe_chapters`, `scribe_echo_check`, `scribe_bench`, `scribe_bench_status`, `scribe_requirements`, `scribe_requirement_link`), tres de vigilancia SEO/GEO (`sites_seo`, `sites_seo_run`, `sites_seo_baseline`) y `activity_procedure_draft`. La API de control es `/api/modules`; el catálogo y las llamadas, `/api/agent/tools` y `/api/agent/call`. El puente `mcp_server.py` descubre las herramientas sin arrancar Talos. Una llamada a una función apagada devuelve `module_disabled`.

Las identidades antiguas pueden quedar en el Hub como entradas de compatibilidad **sin lanzador**, apuntando a Talos. Conservan la autenticación de la familia, referencias y llamadas internas; no ejecutan servidores antiguos. Las herramientas de audio que otras Hoards pedían a Funes siguen disponibles en `/legacy/funes/`. La prueba diferencial de la absorción (`scripts/differential/funes_absorption/`) compara el último commit de Funes anterior al traslado con los módulos Actividad y Audio de Talos sobre las mismas 130 llamadas grabadas, por la ruta principal y por la heredada: coinciden en las 130 (tres pasadas seguidas) y un fallo provocado a propósito se detecta; las diferencias previstas (módulos en un solo servidor, un único punto de entrada, argumentos y herramientas nuevos) están en su README. `scripts/differential/module_absorption/` hace lo mismo con las otras cuatro apps absorbidas (Pantalla/Argus 85 llamadas, Portapapeles/Echo 124, Servicios/Cassandra 148, Disco/DiskHoard 123), cada una por la dirección principal de Talos y por el prefijo del propio módulo, sobre datos hechos con el código antiguo y con motores falsos de captura, portapapeles, procesos, red, Faustus y Ollama (README y `RESULT.md` de esa carpeta; `tests/test_differential_modules.py` cubre sus ayudantes).

Los modelos de texto usan el servicio global Sparks configurado en la familia. Voz e imagen mantienen sus motores y coordinación de GPU. Ningún modelo se carga con su módulo apagado. Los detalles de configuración, compilación y pruebas figuran en [README.md](README.md).


## Datos propios y compatibilidad

Los datos nativos pueden trasladarse a `data/native/<módulo>/data`, con configuración privada junto a cada módulo. La ficción de Writer utiliza su perfil de escritorio `writers-hoard/fiction/data`. Traslada árboles completos, incluidos WAL/SHM de SQLite, medios, modelos descargados y sesiones del navegador; actualiza las rutas absolutas guardadas antes de activar el módulo. Los manifiestos de `compatibility/<id>/faustus-plugin.json` conservan identidades, nombres de herramientas y tokens sin necesitar el repositorio retirado. Añade el directorio `compatibility` de cada producto a las raíces del Hub antes de la raíz general. El catálogo y los puentes compatibles nunca arrancan aplicaciones. Todos los módulos permanecen apagados durante el traslado.

Las instrucciones anteriores de adopción in-place describen una importación opcional. Una vez comprobados el traslado y las rutas, ya no es necesario conservar las carpetas de los productos antiguos.
