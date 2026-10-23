import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";

const labels = { equal: "Igual", delete: "Eliminada", insert: "Añadida" };
const signs = { equal: " ", delete: "−", insert: "+" };
const ending = (value) => value === "none" ? "sin salto final" : value;
const stamp = (clip) => new Date(clip.last_seen_at * 1000).toLocaleString("es-ES");

export default function ClipComparison({ ids, onChange, refreshRevision }) {
  const { notify } = useApp();
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [onlyChanges, setOnlyChanges] = useState(false);
  const signature = `${ids.join(",")}|${refreshRevision}`;
  const current = useRef(signature);
  current.current = signature;
  const generation = useRef(0);
  const result = snapshot?.signature === signature ? snapshot.result : null;
  useEffect(() => {
    generation.current++; setSnapshot(null); setError(""); setBusy(false);
    return () => { generation.current++; };
  }, [signature]);
  useEffect(() => {
    if (ids.length !== 2) return;
    const provide = (event) => event.detail?.provide?.({ kind: "clip-comparison", object_id: "selection", fields: {
      left_id: ids[0], right_id: ids[1], busy, error, result: result ? { left: result.left, right: result.right,
        text_scope: result.text_scope, identical_read_text: result.identical_read_text, summary: result.summary, total_rows: result.total_rows } : null,
    } });
    window.addEventListener("echo:context-request", provide);
    return () => window.removeEventListener("echo:context-request", provide);
  }, [ids, busy, error, result]);

  async function compare() {
    const requested = signature, request = ++generation.current;
    setBusy(true); setError(""); setSnapshot(null);
    try {
      const next = await api.compare([...ids]);
      if (current.current === requested && generation.current === request) setSnapshot({ signature: requested, result: next });
    } catch (failure) {
      if (current.current === requested && generation.current === request) setError(`No se pudo comparar. La selección se conserva para reintentar. ${failure.message}`);
    } finally { if (current.current === requested && generation.current === request) setBusy(false); }
  }
  async function copy() {
    const requested = signature;
    const source = (name, clip) => `${name} #${clip.id} · ${clip.source_app || "Origen desconocido"} · ${clip.source_title || ""} · ${stamp(clip)} · ${clip.chars_read}/${clip.chars} caracteres${clip.truncated ? " · texto parcial" : ""}`;
    const text = ["Comparación literal A → B", source("A", result.left), source("B", result.right),
      result.text_scope === "extracts" ? "Sólo extractos leídos; no establece igualdad de los clips completos." : "Textos guardados completos, no imágenes.",
      `${result.summary.added} líneas añadidas; ${result.summary.removed} eliminadas; ${result.summary.equal} iguales.`,
      ...(result.truncated ? ["Respuesta recortada: sólo se copian las filas recibidas."] : []),
      "Texto entre comillas JSON para conservar espacios y tabulaciones; terminador indicado por separado. No es un parche aplicable.",
      ...result.rows.map(row => `${signs[row.tag]} A${row.a ?? "—"}/B${row.b ?? "—"} ${labels[row.tag]} ${JSON.stringify(row.text)} [${ending(row.ending)}]`)].join("\n");
    try { await navigator.clipboard.writeText(text); if (current.current === requested) notify("Comparación copiada."); }
    catch { if (current.current === requested) notify("No se pudo copiar. Puedes seleccionar las líneas de la comparación."); }
  }

  const emptyText = result && (!result.left.has_text || !result.right.has_text);
  const rows = result?.rows.filter(row => !onlyChanges || row.tag !== "equal") || [];
  return <section className="clip-comparison" aria-label="Comparar dos copias">
    <div className="clip-bundle-bar">
      <div><h3 className="text-[17px] font-semibold">Comparar dos copias</h3>
        <p className="help">Selecciona exactamente dos copias. A es la primera y B la segunda; sólo se compara su texto guardado.</p></div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn" disabled={ids.length !== 2 || busy} onClick={compare}>{busy ? "Comparando…" : "Comparar A con B"}</button>
        <button type="button" className="btn" disabled={ids.length !== 2} onClick={() => onChange([...ids].reverse())}>Intercambiar A/B</button>
      </div>
    </div>
    {ids.length === 2 && <p className="help mt-2">A: #{ids[0]} → B: #{ids[1]} · Hasta 20.000 caracteres por copia; la lectura es explícita.</p>}
    {error && <p role="alert" className="clip-bundle-error">{error}</p>}
    {result && <div className="mt-4 space-y-4" aria-label="Diferencias de las copias">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[["A", result.left], ["B", result.right]].map(([side, clip]) => <div key={side} className="min-w-0">
          <h4 className="font-semibold">{side} · {clip.label ? `${clip.label} · #${clip.id}` : `Copia #${clip.id}`}</h4>
          <p className="help break-words">{clip.source_app || "Origen desconocido"}{clip.source_title ? ` · ${clip.source_title}` : ""} · {stamp(clip)}</p>
          <p className="help">{clip.chars_read.toLocaleString("es-ES")} de {clip.chars.toLocaleString("es-ES")} caracteres{clip.truncated ? " · Texto parcial" : " · Texto completo"}</p>
          {!clip.has_text && <p className="help">Sin texto guardado{clip.kind === "image" ? ": imagen sin OCR guardado" : ""}. No se comparan píxeles ni se ejecuta OCR.</p>}
        </div>)}
      </div>
      <p role="status">{emptyText ? "Hay una copia sin texto guardado." : result.identical_read_text ? result.text_scope === "extracts" ? "Los extractos leídos coinciden." : "Los textos guardados coinciden." : "Los textos leídos tienen diferencias."}</p>
      {result.text_scope === "extracts" && <p className="help">Comparación de extractos: no permite concluir que los clips completos sean iguales. Sólo se han leído los primeros 20.000 caracteres de cada copia.</p>}
      {result.truncated && <p role="alert" className="clip-bundle-error">La respuesta está recortada; no se muestran todas las filas calculadas.</p>}
      <p className="help">{result.summary.added} {result.summary.added === 1 ? "línea añadida" : "líneas añadidas"} · {result.summary.removed} {result.summary.removed === 1 ? "eliminada" : "eliminadas"} · {result.summary.equal} {result.summary.equal === 1 ? "igual" : "iguales"}</p>
      <div className="clip-bundle-bar">
        <label className="flex items-center gap-2"><input type="checkbox" checked={onlyChanges} onChange={event => setOnlyChanges(event.target.checked)} /> Sólo cambios</label>
        <button type="button" className="btn" onClick={copy}>{result.truncated ? "Copiar filas recibidas" : "Copiar comparación completa"}</button>
      </div>
      <p className="help">Espacio: · · tabulación: ⇥ · LF/CRLF indican el terminador. «Sin salto final» también forma parte de la comparación. A/B y signos indican la dirección; no es un parche.</p>
      {rows.length ? <ol className="clip-diff" aria-label="Líneas comparadas">{rows.map((row, index) => <li key={index} data-kind={row.tag}>
        <div className="clip-diff-location"><span>{signs[row.tag]} {labels[row.tag]}</span><span>A{row.a ?? "—"} / B{row.b ?? "—"}</span></div>
        <div className="min-w-0"><code className="clip-diff-text">{row.text.replace(/ /g, "·").replace(/\t/g, "⇥") || "(línea vacía)"}</code><span className="clip-diff-ending">{ending(row.ending)}</span></div>
      </li>)}</ol> : <p className="help">{onlyChanges ? "No hay líneas cambiadas en los textos leídos." : "No hay líneas de texto guardado para mostrar."}</p>}
    </div>}
  </section>;
}
