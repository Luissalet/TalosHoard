"""Native engines incorporated in this repository; no original servers run."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from echo.hoard_link.guard import check_request


SPECS = [
    {"id": "screen", "name": "Pantalla", "origin": "Argus", "description": "Capturas, OCR, búsqueda visual, importaciones y línea de tiempo."},
    {"id": "clipboard", "name": "Portapapeles", "origin": "Echo", "description": "Texto, imágenes, búsqueda, favoritos y recuperación del portapapeles."},
    {"id": "activity", "name": "Actividad", "origin": "Funes", "description": "Ventanas, aplicaciones, archivos recientes, commits y memoria conjunta."},
    {"id": "audio", "name": "Audio", "origin": "Funes Audio", "description": "Grabación, importación, transcripción, notas y actas de reuniones."},
    {"id": "services", "name": "Servicios", "origin": "Cassandra", "description": "Salud, incidentes, registros, GPU, sitios y políticas de reinicio."},
    {"id": "disk", "name": "Disco", "origin": "DiskHoard", "description": "Análisis de espacio, limpieza, archivos grandes, ZIP y copias de modelos."},
]


def factory(key, data_dir, *, port):
    if key == "activity":
        from funes_hoard.api import create_app
        return create_app(data_dir, static_dir=Path(__file__).parent.parent / "funes_hoard" / "static", port=port, audio_enabled=False)
    if key == "audio":
        from funes_hoard.audio_memory.config import Config
        from funes_hoard.audio_memory.main import create_app
        from funes_hoard.hoard_link import Link
        from funes_hoard import backend
        link = Link(backend.load_link_config(data_dir.parent))
        config = Config.from_env()
        config.data_dir, config.port, config.data_dir_configured = data_dir, port, True
        app = create_app(config, link_provider=lambda: link)
        original = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(instance):
            try:
                async with original(instance):
                    yield
            finally:
                await link.aclose()
        app.router.lifespan_context = lifespan
        return app
    if key == "disk":
        os.environ["DISKHOARD_DATA_DIR"] = str(data_dir)
        from .disk import create_app
        return create_app(data_dir, port)
    import importlib
    package = {"screen": "argus", "clipboard": "echo", "services": "cassandra_hoard"}[key]
    Config = importlib.import_module(package + ".config").Config
    config = Config.from_env()
    config.data_dir, config.port, config.data_dir_configured = data_dir, port, True
    if key == "services":
        config.retired_ids = ("argus", "echo", "funes", "cassandra", "diskhoard", "tantalus", "phileas")
    return importlib.import_module(package + ".main").create_app(config)

from echo.hoard_link.copilot import install_copilot
