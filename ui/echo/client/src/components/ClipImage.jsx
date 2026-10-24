import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { when } from "../format.js";

export default function ClipImage({ id, onClose, refreshRevision }) {
  const [retry, setRetry] = useState(0);
  const [original, setOriginal] = useState(false);
  const [loaded, setLoaded] = useState(null);
  const [pixels, setPixels] = useState(null);
  const [error, setError] = useState("");
  const heading = useRef(null);
  const key = JSON.stringify([id, retry, refreshRevision]);
  const clip = loaded?.key === key ? loaded.clip : null;
  const dimensions = pixels?.key === key ? pixels : null;

  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    let current = true;
    setLoaded(null);
    setPixels(null);
    setError("");
    api.clip(id).then((clip) => {
      if (!current) return;
      if (clip.kind !== "image" || clip.sensitive) {
        setError("Esta copia no tiene una imagen visible.");
      } else setLoaded({ key, clip });
    }).catch((reason) => { if (current) setError(reason.message); });
    return () => { current = false; };
  }, [id, retry, refreshRevision, key]);

  useEffect(() => {
    const provide = (event) => event.detail?.provide?.({
      kind: "clip-image", object_id: String(id), dirty: false,
      fields: { state: error ? "error" : dimensions ? "ready" : "loading", scale: original ? "original" : "fit" },
    });
    window.addEventListener("echo:context-request", provide);
    return () => window.removeEventListener("echo:context-request", provide);
  }, [id, error, dimensions, original]);

  return (
    <section className="panel-white mb-5 min-w-0" aria-labelledby="clip-image-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="clip-image-heading" ref={heading} tabIndex={-1} className="text-base font-semibold">Ver imagen · Copia #{id}</h2>
          <p className="help mt-1">Imagen guardada completa. No modifica el portapapeles.</p>
        </div>
        <button type="button" className="btn btn-sm" onClick={onClose}>Cerrar imagen</button>
      </div>
      {clip && <p className="help mt-3 break-words">{clip.source_app || "Origen desconocido"} · {when(clip.last_seen_at)}{dimensions && ` · ${dimensions.width} × ${dimensions.height} px`}</p>}
      {!error && <>
        <div className="my-3 flex flex-wrap items-center gap-2" aria-label="Tamaño de la imagen">
          <button type="button" className={`btn btn-sm${!original ? " btn-primary" : ""}`} aria-pressed={!original} onClick={() => setOriginal(false)}>Ajustar</button>
          <button type="button" className={`btn btn-sm${original ? " btn-primary" : ""}`} aria-pressed={original} onClick={() => setOriginal(true)}>100 %</button>
          <span className="help">{original ? "Tamaño original. Desplázate para ver el resto." : "Se ajusta al espacio disponible, sin recortar."}</span>
        </div>
        {!dimensions && <p role="status" className="help mb-3">Cargando imagen…</p>}
        {clip && <div className="max-h-[60vh] overflow-auto" tabIndex={0} role="region" aria-label={`Imagen guardada de copia ${id}`}>
          <img key={key} src={`${api.imageUrl(id)}?preview=${retry}-${refreshRevision}`} alt={`Imagen guardada de copia ${id}`}
            className={original ? "block max-w-none" : "block max-h-[60vh] max-w-full object-contain"}
            onLoad={(event) => setPixels({ key, width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
            onError={() => setError("No se pudo cargar el PNG guardado.")} />
        </div>}
      </>}
      {error && <div role="alert" className="mt-4"><p>{error}</p><button type="button" className="btn btn-sm mt-2" onClick={() => setRetry(value => value + 1)}>Reintentar imagen</button></div>}
    </section>
  );
}
