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

## Arranque

Python 3.11 o posterior; las integraciones de escritorio de Windows requieren Windows. Ejecuta `Start.cmd` o sigue los comandos del [README en inglés](README.md#run). Abre `http://127.0.0.1:5220`. El servidor no abre ventanas por su cuenta. El Hub lo descubre mediante `faustus-plugin.json` y permite iniciarlo expresamente.

## Conservar los datos existentes

Con todos los módulos apagados:

```powershell
.venv\Scripts\python.exe scripts\adopt_data.py --parent "C:\ruta\a\las Hoards"
```

Solo escribe el mapa `data/modules.json`. Las bases de datos, capturas, imágenes, grabaciones, ajustes, tokens e instantáneas de disco permanecen **en sus carpetas originales**, sin copiar, mover ni borrar. Conserva esas carpetas. Sin adopción se usan carpetas nuevas `data/<módulo>`.

Al activar una función se reanuda su comportamiento nativo, incluidos sus ajustes previos de privacidad y retención. Al desactivarla se espera a que termine el trabajo en curso antes de mostrar «Desactivada». Las transmisiones de eventos se desconectan; las descargas grandes se sirven por partes.

## API, MCP y compatibilidad

El catálogo contiene **93 herramientas**: las 91 originales y dos para consultar/cambiar los módulos. La API de control es `/api/modules`; el catálogo y las llamadas, `/api/agent/tools` y `/api/agent/call`. El puente `mcp_server.py` descubre las herramientas sin arrancar Talos. Una llamada a una función apagada devuelve `module_disabled`.

Las identidades antiguas pueden quedar en el Hub como entradas de compatibilidad **sin lanzador**, apuntando a Talos. Conservan la autenticación de la familia, referencias y llamadas internas; no ejecutan servidores antiguos. Las herramientas de audio que otras Hoards pedían a Funes siguen disponibles en `/legacy/funes/`.

Los modelos de texto usan el servicio global Sparks configurado en la familia. Voz e imagen mantienen sus motores y coordinación de GPU. Ningún modelo se carga con su módulo apagado. Los detalles de configuración, compilación y pruebas figuran en [README.md](README.md).


## Datos propios y compatibilidad

Los datos nativos pueden trasladarse a `data/native/<módulo>/data`, con configuración privada junto a cada módulo. La ficción de Writer utiliza su perfil de escritorio `writers-hoard/fiction/data`. Traslada árboles completos, incluidos WAL/SHM de SQLite, medios, modelos descargados y sesiones del navegador; actualiza las rutas absolutas guardadas antes de activar el módulo. Los manifiestos de `compatibility/<id>/faustus-plugin.json` conservan identidades, nombres de herramientas y tokens sin necesitar el repositorio retirado. Añade el directorio `compatibility` de cada producto a las raíces del Hub antes de la raíz general. El catálogo y los puentes compatibles nunca arrancan aplicaciones. Todos los módulos permanecen apagados durante el traslado.

Las instrucciones anteriores de adopción in-place describen una importación opcional. Una vez comprobados el traslado y las rutas, ya no es necesario conservar las carpetas de los productos antiguos.
