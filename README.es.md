# Talos's Hoard

<img src="app-icon.png" width="96" alt="Talos icon">

Memoria de pantalla, portapapeles, actividad, audio, vigilancia de servicios y gestión del disco en un único proceso. Absorbe **Argus, Echo, Funes, Cassandra y DiskHoard**, conservando sus motores, funciones e historiales.

[English](README.md) · [Inventario completo de herramientas](provenance/CAPABILITIES.md) · [Procedencia del código](provenance/sources.json)

## Funciones independientes

**Todas desactivadas en la primera apertura.** Abrir Talos o consultar sus herramientas MCP no pone en marcha capturas, vigilantes, escaneos ni modelos. Cada función tiene su interruptor; puedes usar portapapeles con pantalla, actividad y audio apagados. La elección se recuerda entre sesiones. «Desactivar todas» detiene los módulos sin borrar sus datos.

- **Pantalla:** capturas, OCR, búsqueda visual y textual, imágenes similares, línea de tiempo, exclusiones, modo privado, importación de imágenes y carpetas vigiladas, fijados, exportación y retención.
- **Portapapeles:** historial de texto e imágenes, tipos, OCR, búsqueda, favoritos, edición, borrado/restauración, copiar y agrupar.
- **Actividad:** ventanas, aplicaciones, inactividad y bloqueo, archivos recientes, commits, proyectos, clasificación, privacidad, resúmenes, exportaciones y memoria conjunta.
- **Audio:** micrófono y sonido del sistema, importación, transcripción en directo, búsqueda, notas, etiquetas, exportaciones, actas y servicio compartido de transcripción.
- **Servicios:** salud, incidentes y causas probables, registros, GPU, bus de eventos, trabajos fallidos, sitios/DNS/certificados/dominios, avisos y políticas de reinicio.
- **Disco:** análisis de espacio, árbol, archivos grandes/antiguos, extensiones, limpieza, papelera y borrado definitivo con sus comprobaciones, scripts, selector de carpeta, ZIP divididos y copias de modelos.

Cada módulo conserva su interfaz completa. Todo comparte el tema de los Hoards, el icono de Talos y el botón de Faustus.

En el Historial del portapapeles puedes seleccionar hasta 20 copias guardadas y **Reunir copias**: revisar texto, origen y fecha, cambiar el orden, elegir separador, copiar todo junto o descargar TXT. La selección se conserva al filtrar y sus identificadores siguen visibles para quitar entradas. Las imágenes aportan solo el OCR ya guardado, sin adjuntar el archivo. Se leen hasta 20.000 caracteres por copia, con aviso explícito si el texto es parcial. La vista previa no modifica el historial y reutiliza `clip_bundle`; API propia `POST /clipboard/api/clips/bundle`. La herramienta nativa de reunir copias conserva su contrato.

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

El catálogo contiene **97 herramientas**: las 91 originales, tres para selecciones guardadas, clip_compare y dos para consultar/cambiar los módulos. La API de control es `/api/modules`; el catálogo y las llamadas, `/api/agent/tools` y `/api/agent/call`. El puente `mcp_server.py` descubre las herramientas sin arrancar Talos. Una llamada a una función apagada devuelve `module_disabled`.

Las identidades antiguas pueden quedar en el Hub como entradas de compatibilidad **sin lanzador**, apuntando a Talos. Conservan la autenticación de la familia, referencias y llamadas internas; no ejecutan servidores antiguos. Las herramientas de audio que otras Hoards pedían a Funes siguen disponibles en `/legacy/funes/`.

Los modelos de texto usan el servicio global Sparks configurado en la familia. Voz e imagen mantienen sus motores y coordinación de GPU. Ningún modelo se carga con su módulo apagado. Los detalles de configuración, compilación y pruebas figuran en [README.md](README.md).


## Datos propios y compatibilidad

Los datos nativos pueden trasladarse a `data/native/<módulo>/data`, con configuración privada junto a cada módulo. La ficción de Writer utiliza su perfil de escritorio `writers-hoard/fiction/data`. Traslada árboles completos, incluidos WAL/SHM de SQLite, medios, modelos descargados y sesiones del navegador; actualiza las rutas absolutas guardadas antes de activar el módulo. Los manifiestos de `compatibility/<id>/faustus-plugin.json` conservan identidades, nombres de herramientas y tokens sin necesitar el repositorio retirado. Añade el directorio `compatibility` de cada producto a las raíces del Hub antes de la raíz general. El catálogo y los puentes compatibles nunca arrancan aplicaciones. Todos los módulos permanecen apagados durante el traslado.

Las instrucciones anteriores de adopción in-place describen una importación opcional. Una vez comprobados el traslado y las rutas, ya no es necesario conservar las carpetas de los productos antiguos.
