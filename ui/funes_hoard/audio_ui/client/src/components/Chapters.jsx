import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useTurnRefresh } from "../copilot.js";
import { fmtClock } from "../format.js";

/** Chapters of a finished session: loaded once, written in the background after the transcription, re-read while being written. */
export function useChapters(sessionId, sessionDone) {
  const [state, setState] = useState(null);
  const timer = useRef(null);
  const load = useCallback(() => api.chapters(sessionId).then(setState).catch(() => setState(null)), [sessionId]);

  useEffect(() => {
    if (!sessionDone) return undefined;
    load();
    // The chapters of a meeting that just finished are written in the background: look again shortly.
    const later = [2000, 6000].map((ms) => setTimeout(load, ms));
    return () => later.forEach(clearTimeout);
  }, [sessionDone, load]);
  useTurnRefresh(() => { if (sessionDone) load(); });
  useEffect(() => {
    clearInterval(timer.current);
    if (state && state.generating) timer.current = setInterval(load, 2000);
    return () => clearInterval(timer.current);
  }, [state && state.generating, load]); // eslint-disable-line react-hooks/exhaustive-deps
  return [state, setState, load];
}

/** The chapter list: each line jumps to its moment. Nothing is shown for a session where chapters make no sense and none exist. */
export default function Chapters({ sessionId, state, setState, onSeek, notify, time }) {
  const [busy, setBusy] = useState(false);
  if (!state) return null;
  const { chapters, generating, last, llm, model } = state;
  const generate = async (regenerate) => {
    setBusy(true);
    try {
      setState(await api.makeChapters(sessionId, { regenerate }));
    } catch (error) {
      notify(error.message);
    }
    setBusy(false);
  };
  const noModel = !chapters && llm && !llm.available;
  const tooShort = last && last.status === "too_short";
  const failure = last && ["error", "no_model"].includes(last.status) ? last : null;
  const current = chapters ? chapters.reduce((found, c, i) => (time >= c.start_s ? i : found), -1) : -1;

  return (
    <section className="panel-white" aria-labelledby="chapters-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="chapters-title" className="text-[17px] font-semibold">Capítulos</h2>
        <button type="button" className="btn btn-sm" disabled={busy || generating || noModel} onClick={() => generate(!!chapters)}>
          {generating ? "Escribiendo…" : chapters ? "Regenerar capítulos" : "Generar capítulos"}
        </button>
      </div>
      {generating && <div className="banner banner-processing mb-3" role="status">Dividiendo la sesión en capítulos con el modelo global…</div>}
      {failure && !generating && (
        <div className="mb-3 rounded-md border p-3 text-[13px]" style={{ background: "var(--danger-bg)", color: "var(--danger-ink)", borderColor: "var(--danger-line)" }} role="alert">
          {failure.status === "no_model" ? "No hay ningún modelo de lenguaje disponible. " : "No se pudieron escribir los capítulos. "}{failure.detail}
        </div>
      )}
      {!chapters && !generating && (
        <p className="help">
          {tooShort ? last.detail : noModel
            ? `Todavía no hay capítulos y no hay modelo de lenguaje disponible (${llm.detail || "carga uno en Faustus"}). Cuando lo haya podrás generarlos.`
            : "Todavía no hay capítulos. El modelo propone dónde empieza cada tema y el código ajusta cada inicio a una línea real de la transcripción."}
        </p>
      )}
      {chapters && (
        <ol className="grid gap-1 text-[14px]">
          {chapters.map((c, i) => (
            <li key={c.start_s}>
              <button type="button" className={`chapter-row${i === current ? " current" : ""}`} onClick={() => onSeek(c.start_s)} aria-label={`Escuchar «${c.title}» desde ${fmtClock(c.start_s)}`}>
                <span className="num font-semibold" style={{ color: "var(--accent)" }}>{fmtClock(c.start_s)} ▸</span> {c.title}
              </button>
            </li>
          ))}
        </ol>
      )}
      {chapters && <p className="help mt-2">Escritos por {model || "el modelo global"}; cada inicio es el de una línea real de la transcripción.</p>}
    </section>
  );
}
