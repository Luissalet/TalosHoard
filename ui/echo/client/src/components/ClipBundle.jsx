import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { KIND_LABEL } from "../format.js";
import ClipComparison from "./ClipComparison.jsx";

export default function ClipBundle({ ids, onChange, refreshRevision }) {
  const { notify } = useApp();
  const [bundle, setBundle] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [origins, setOrigins] = useState(true);
  const [separator, setSeparator] = useState("\n\n");
  const [saved, setSaved] = useState([]);
  const [pick, setPick] = useState("");
  const [activeId, setActiveId] = useState(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const active = saved.find((row) => row.id === activeId);
  const dirty = active && (name !== active.name || separator !== active.separator || origins !== active.include_origins || JSON.stringify(ids) !== JSON.stringify(active.ids));
  const current = useRef(ids);
  current.current = ids;
  useEffect(() => {
    if (!ids.length) return;
    const provide = (event) => event.detail?.provide?.({ kind: "clip-bundle", object_id: activeId ? String(activeId) : "selection", dirty: true, fields: { name, ids, include_origins: origins, separator } });
    window.addEventListener("echo:context-request", provide);
    return () => window.removeEventListener("echo:context-request", provide);
  }, [ids, origins, separator, name, activeId]);
  async function refreshSelections() {
    setError("");
    try { setSaved((await api.selections()).selections); }
    catch (failure) { setError(`No se pudieron listar las selecciones guardadas. ${failure.message}`); }
  }
  useEffect(() => { refreshSelections(); }, []);
  function openSelection() {
    const row = saved.find((value) => String(value.id) === pick);
    if (!row) return;
    setActiveId(row.id); setName(row.name); onChange([...row.ids]);
    setOrigins(row.include_origins); setSeparator(row.separator); setBundle(null); setError("");
  }
  async function saveSelection(asNew = false) {
    setSaving(true); setError("");
    try {
      const { selection } = await api.saveSelection({ ...(activeId && !asNew ? { id: activeId } : {}), name, ids, separator, include_origins: origins });
      setSaved((rows) => [selection, ...rows.filter((row) => row.id !== selection.id)]);
      setActiveId(selection.id); setPick(String(selection.id)); setName(selection.name);
      notify("Selección guardada. Las copias originales no se han modificado.");
    } catch (failure) { setError(`No se pudo guardar la selección. ${failure.message}`); }
    finally { setSaving(false); }
  }
  async function deleteSelection() {
    if (!activeId) return;
    setSaving(true); setError("");
    try {
      await api.deleteSelection(activeId);
      setSaved((rows) => rows.filter((row) => row.id !== activeId));
      setActiveId(null); setPick("");
      notify("Selección guardada eliminada. El borrador y las copias siguen disponibles.");
    } catch (failure) { setError(`No se pudo eliminar la selección guardada. ${failure.message}`); }
    finally { setSaving(false); }
  }
  const byId = new Map((bundle || []).map((clip) => [clip.id, clip]));
  const ready = ids.length > 0 && ids.every((id) => byId.has(id));
  const clips = ready ? ids.map((id) => byId.get(id)) : [];
  const stamp = (clip) => new Date(clip.last_seen_at * 1000).toLocaleString("es-ES");
  const text = clips.map((clip, index) => {
    const content = clip.text || (clip.kind === "image" ? "[Imagen sin texto OCR guardado]" : "[Copia sin texto]");
    const note = clip.truncated ? `\n[Texto parcial: ${Array.from(clip.text).length} de ${clip.chars} caracteres]` : "";
    const source = [clip.source_app || "Origen desconocido", clip.source_title, stamp(clip)].filter(Boolean).join(" · ");
    return (origins ? `${index + 1}. ${clip.label || KIND_LABEL[clip.kind] || clip.kind} · #${clip.id}\n${source}\n\n` : "") + content + note;
  }).join(separator);

  async function load() {
    const requested = [...ids];
    setBusy(true);
    setError("");
    try {
      const response = await api.bundle(requested);
      if (requested.length === current.current.length && requested.every((id) => current.current.includes(id))) setBundle(response.clips);
    } catch (failure) {
      setBundle(null);
      setError(`No se pudo leer la selección. Si una copia ya no está disponible, quítala y vuelve a intentarlo. ${failure.message}`);
    } finally { setBusy(false); }
  }
  function move(index, offset) {
    const next = [...ids];
    [next[index], next[index + offset]] = [next[index + offset], next[index]];
    onChange(next);
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      notify(`${clips.length} copias reunidas en el portapapeles.`);
    } catch { notify("No se pudo copiar. Puedes seleccionar el texto de la vista previa."); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "talos-portapapeles.txt";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className="clip-bundle mb-5" aria-label="Reunir copias">
    <fieldset disabled={saving} className="min-w-0 border-0 p-0 m-0">
    <div className="clip-bundle-bar">
      <div><h2 className="text-[17px] font-semibold">Reunir copias</h2><p className="help" aria-live="polite">{ids.length ? `${ids.length} seleccionadas · se conservan al filtrar` : "Selecciona copias del historial para revisar y copiar sus textos juntos."}</p></div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn" disabled={!ids.length || busy} onClick={load}>{busy ? "Leyendo…" : "Revisar selección"}</button>
        {!!ids.length && <button type="button" className="btn" onClick={() => { onChange([]); setBundle(null); setError(""); }}>Vaciar selección</button>}
      </div>
    </div>
    <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="min-w-0">
        <label className="label" htmlFor="clip-saved-selection">Selecciones guardadas</label>
        <select id="clip-saved-selection" className="field w-full" value={pick} onChange={(event) => setPick(event.target.value)}>
          <option value="">{saved.length ? "Elige una selección" : "Aún no hay selecciones guardadas"}</option>
          {saved.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.ids.length} copias</option>)}
        </select>
        <div className="mt-2 flex flex-wrap gap-2"><button type="button" className="btn" disabled={!pick || busy} onClick={openSelection}>Cargar selección</button><button type="button" className="btn" onClick={refreshSelections}>Actualizar lista</button></div>
        <p className="help mt-2">Cargar sustituye el borrador actual. Los textos se leen al revisar la selección.</p>
      </div>
      <div className="min-w-0">
        <label className="label" htmlFor="clip-selection-name">Nombre de la selección</label>
        <input id="clip-selection-name" className="field w-full" maxLength={200} value={name} onChange={(event) => setName(event.target.value)} placeholder="Por ejemplo, notas de la reunión" />
        <p className="help mt-2 break-words" aria-live="polite">{active ? `Editando: ${active.name}${dirty ? " · cambios sin guardar" : " · guardada"}` : "Nueva selección: se guardan IDs, orden y opciones, sin duplicar textos."}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className="btn" disabled={!ids.length || !name.trim()} onClick={() => saveSelection()}>{saving ? "Guardando…" : activeId ? "Guardar cambios" : "Guardar selección"}</button>
          {activeId && <><button type="button" className="btn" disabled={!ids.length || !name.trim()} onClick={() => saveSelection(true)}>Guardar como nueva</button><button type="button" className="btn" onClick={deleteSelection}>Eliminar selección guardada</button></>}
        </div>
      </div>
    </div>
    {ids.length > 0 && <div className="clip-selected-ids" aria-label="Copias seleccionadas">{ids.map((id, index) => <button key={id} type="button" className="btn btn-sm" onClick={() => onChange(ids.filter((value) => value !== id))} aria-label={`Quitar copia ${id} de la selección`}>{index + 1}. #{id} ×</button>)}</div>}
    {ids.length === 20 && <p className="help">El paquete nativo reúne hasta 20 copias. Quita alguna para añadir otra.</p>}
    {error && <p role="alert" className="clip-bundle-error">{error}</p>}
    {ids.length > 0 && <div className="clip-bundle-bar mt-4">
        <label className="flex items-center gap-2"><input type="checkbox" checked={origins} onChange={(event) => setOrigins(event.target.checked)} /> Incluir origen y fecha</label>
        <label className="flex items-center gap-2">Separar con <select className="field w-auto" value={separator} onChange={(event) => setSeparator(event.target.value)}><option value={"\n\n"}>Línea en blanco</option><option value={"\n"}>Salto de línea</option><option value={", "}>Coma</option></select></label>
      </div>}
    {ready && <div className="clip-bundle-preview">
      <ol className="clip-bundle-order" aria-label="Orden del paquete">{clips.map((clip, index) => <li key={clip.id}>
        <div className="min-w-0 flex-1"><strong>{index + 1}. {clip.label || `Copia #${clip.id}`}</strong><p className="help">{clip.source_app || "Origen desconocido"} · {stamp(clip)}{clip.truncated ? ` · Texto parcial: ${Array.from(clip.text).length}/${clip.chars} caracteres` : ""}</p></div>
        <button className="btn btn-sm" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Subir copia ${clip.id}`}>Subir</button>
        <button className="btn btn-sm" disabled={index === clips.length - 1} onClick={() => move(index, 1)} aria-label={`Bajar copia ${clip.id}`}>Bajar</button>
      </li>)}</ol>
      <label className="label" htmlFor="clip-bundle-text">Texto que se copiará · {Array.from(text).length.toLocaleString("es-ES")} caracteres</label>
      <textarea id="clip-bundle-text" className="field clip-bundle-text" readOnly value={text} rows={9} />
      <p className="help">Se usa el texto guardado, incluido OCR si lo hay; las imágenes no se adjuntan. Hasta 20.000 caracteres por copia, con aviso si el texto es parcial.</p>
      <div className="mt-3 flex flex-wrap gap-2"><button className="btn btn-primary" onClick={copy}>Copiar textos juntos</button><button className="btn" onClick={download}>Descargar TXT</button></div>
    </div>}
    <ClipComparison ids={ids} onChange={onChange} refreshRevision={refreshRevision} />
    </fieldset>
  </section>;
}
