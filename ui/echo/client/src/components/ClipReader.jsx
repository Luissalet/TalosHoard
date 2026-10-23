import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { KIND_LABEL, when } from "../format.js";

const PAGE_SIZE = 4000;

export default function ClipReader({ id, onClose, refreshRevision }) {
  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  const [loaded, setLoaded] = useState(null);
  const page = loaded?.offset === offset && loaded?.retry === retry && loaded?.revision === refreshRevision ? loaded.result : null;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const heading = useRef(null);

  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    let current = true;
    setLoaded(null);
    setError("");
    setBusy(true);
    api.readClip(id, offset).then((result) => {
      if (current) setLoaded({ result, offset, retry, revision: refreshRevision });
    }).catch((reason) => {
      if (current) setError(reason.message);
    }).finally(() => { if (current) setBusy(false); });
    return () => { current = false; };
  }, [id, offset, retry, refreshRevision]);

  useEffect(() => {
    const provide = (event) => event.detail?.provide?.({
      kind: "clip-reader", object_id: String(id), dirty: false,
      fields: { offset, max_chars: PAGE_SIZE, state: busy ? "loading" : error ? "error" : "ready" },
    });
    window.addEventListener("echo:context-request", provide);
    return () => window.removeEventListener("echo:context-request", provide);
  }, [id, offset, busy, error]);

  // Native offsets count Python characters, including an emoji as one character.
  const end = page ? offset + Math.min(PAGE_SIZE, Math.max(0, page.chars - offset)) : offset;
  return (
    <section className="panel-white mb-5 min-w-0" aria-labelledby="clip-reader-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="clip-reader-heading" ref={heading} tabIndex={-1} className="text-base font-semibold">Leer texto · Copia #{id}</h2>
          <p className="help mt-1">Texto guardado, en páginas de hasta 4.000 caracteres. No modifica el portapapeles.</p>
        </div>
        <button type="button" className="btn btn-sm" onClick={onClose}>Cerrar lectura</button>
      </div>
      {busy && <p role="status" className="help mt-4">Leyendo desde el carácter {offset + 1}…</p>}
      {error && <div role="alert" className="mt-4"><p>No se pudo leer esta página: {error}</p><button type="button" className="btn btn-sm mt-2" onClick={() => setRetry(value => value + 1)}>Reintentar lectura</button></div>}
      {page && <>
        <p className="help mt-3 break-words">{KIND_LABEL[page.kind] || page.kind} · {page.source_app || "Origen desconocido"} · {when(page.last_seen_at)}</p>
        <pre aria-label={`Texto guardado de copia ${id}`} className="field mt-3 max-h-[50vh] overflow-auto whitespace-pre-wrap break-words text-sm" style={{ overflowWrap: "anywhere" }}>{page.text || "(Sin texto en esta página)"}</pre>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p role="status" className="help">{page.chars ? `${Math.min(offset + 1, page.chars)}–${end} de ${page.chars} caracteres` : "0 de 0 caracteres"}{!page.truncated && " · Fin del texto"}</p>
          <div className="flex gap-2">
            <button type="button" className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Anterior</button>
            <button type="button" className="btn btn-sm" disabled={!page.truncated} onClick={() => setOffset(end)}>Siguiente</button>
          </div>
        </div>
      </>}
    </section>
  );
}
