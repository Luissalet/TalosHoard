"""Builds the shared starting data for the differential test with the OLD Funes code (run with it first on PYTHONPATH):
the demo activity history and three audio sessions (with tags, notes and stored minutes) at fixed times."""
import json, os, sys, shutil
from pathlib import Path
import funes_hoard
assert Path(funes_hoard.__file__).resolve().parent.parent == Path.cwd().resolve(), f"run this from the old Funes tree, not {funes_hoard.__file__}"
out = Path(sys.argv[1]); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
from funes_hoard.db import Database
from funes_hoard.demo import seed_demo_data
import datetime as _dt
FIXED_NOW = _dt.datetime(2026, 9, 24, 20, 0, 0).timestamp()
db = Database(out); seed_demo_data(db, now=FIXED_NOW); db.close()
from funes_hoard.audio_memory.db import Database as ADb
from funes_hoard.audio_memory.store import SessionStore
from funes_hoard.audio_memory.minutes import MinutesStore
from funes_hoard.audio_memory.merge import Labelled
audio = out / "audio"; audio.mkdir()
adb = ADb(audio / "scribe-hoard.db"); st = SessionStore(adb, audio / "sessions")
T = 1_790_000_000.0  # 2026-09-21: fixed
meeting = [("yo", "Buenos días a todos, empezamos la reunión de producto."), ("otros", "Repasamos la agenda: estado, lanzamiento y presupuesto."),
 ("otros", "Primero un resumen rápido de la semana pasada."), ("yo", "Hubo dos incidencias menores en el servicio de pagos."),
 ("otros", "Se resolvieron el mismo día, sin impacto para los clientes."), ("yo", "Pasamos al estado del producto y a las funciones nuevas."),
 ("otros", "El editor colaborativo ya está en pruebas con diez clientes."), ("otros", "Los comentarios piden mejorar la velocidad de carga."),
 ("yo", "Hemos reducido el tiempo de carga de seis a dos segundos."), ("otros", "Falta pulir la exportación a PDF con tablas grandes."),
 ("yo", "Lucía se encarga de corregir la exportación esta semana."), ("otros", "Hablemos del plan de lanzamiento de la versión dos."),
 ("yo", "La fecha objetivo es el quince de noviembre."), ("otros", "Marketing necesita el material de prensa diez días antes."),
 ("yo", "Propongo congelar las funciones el uno de noviembre."), ("otros", "De acuerdo, y dejamos una semana para pruebas finales."),
 ("yo", "Sobre el presupuesto, la infraestructura subió un doce por ciento."), ("otros", "Podemos apagar los servidores de pruebas fuera de horario."),
 ("yo", "Mario programa el arranque y la parada automática."), ("otros", "Vamos cerrando: Lucía arregla la exportación y Mario los servidores.")]
call = [("otros", "Hi, thanks for calling back about the delivery."), ("yo", "Sure, I can confirm the delivery for Thursday."), ("otros", "Perfect, then we close the deal this week."),
        ("yo", "I will send you the summary by email tomorrow."), ("otros", "Great, talk soon.")]
note = [("yo", "Recordar revisar el contrato de alquiler antes del viernes."), ("yo", "Llamar a la gestoría por el trimestre.")]
def make(title, kind, lang, lines, start, step, tags, notes):
    s = st.create(title, kind, True, kind != "note", lang, status="done", started_at=start)
    segs = [Labelled(i * step, i * step + step * 0.8, sp, tx) for i, (sp, tx) in enumerate(lines)]
    st.add_segments(s["id"], segs, live=False)
    st.update(s["id"], duration_s=len(lines) * step, ended_at=start + len(lines) * step)
    if tags: st.change_tags(s["id"], add=tags)
    if notes: st.append_notes(s["id"], notes)
    return s["id"]
ids = {"meeting": make("Reunión de producto", "meeting", "es", meeting, T, 20.0, ["producto", "semanal"], "Acordar fecha de lanzamiento."),
       "call": make("Llamada con proveedor", "interview", "en", call, T + 86400, 15.0, ["proveedor"], ""),
       "note": make("Nota de voz", "note", "es", note, T + 2 * 86400, 10.0, [], "")}
MinutesStore(adb).save({"session_id": ids["meeting"], "summary": "Reunión de producto: estado, lanzamiento y presupuesto.",
  "decisions": ["Congelar las funciones el uno de noviembre", "Apagar los servidores de pruebas fuera de horario"],
  "action_items": [{"owner": "Lucía", "action": "Corregir la exportación a PDF", "counterpart": "", "due_date": "2026-09-28", "due_text": "esta semana",
                    "evidence": {"start_s": 200.0, "end_s": 216.0, "speaker": "yo", "quote": "Lucía se encarga de corregir la exportación esta semana."}},
                   {"owner": "Mario", "action": "Programar el arranque y la parada automática", "counterpart": "", "due_date": None, "due_text": "",
                    "evidence": {"start_s": 360.0, "end_s": 376.0, "speaker": "yo", "quote": "Mario programa el arranque y la parada automática."}}],
  "open_questions": ["¿Quién prepara el material de prensa?"], "participants": ["yo", "otros"], "model": "fixture-model", "created_at": 1789980000.0, "stats": {"fixture": True}})
adb.close()
(out / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
print("base ready", out, ids)
