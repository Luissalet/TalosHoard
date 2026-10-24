import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useEditorSnapshot, useTurnRefresh } from "../copilot.js";
import { changedFields } from "../copilot-context.js";
import { useApp } from "../App.jsx";
import { Empty, PageHeader } from "../components/ui.jsx";
import { fmtClock, fmtDateTime, KIND_LABEL, SPEAKER_LABEL } from "../format.js";

export default function Buscar() {
  const { route } = useApp();
  const sessionId = route.query.get("session_id") || "";
  const sessionTitle = route.query.get("session_title") || "";
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const queryKey = JSON.stringify({ q: q.trim(), kind, from, to, session_id: sessionId });
  const currentResult = result?.key === queryKey ? result.data : null;
  const currentError = error?.key === queryKey ? error.message : null;

  const [tick, setTick] = useState(0);

  useEffect(() => {
    let current = true;
    setResult(null); setError(null); setLoading(q.trim().length >= 2);
    if (q.trim().length < 2) return undefined;
    const timer = setTimeout(() => {
      api.search({ q: q.trim(), kind, from, to, session_id: sessionId }).then((r) => {
        if (current) setResult({ key: queryKey, data: r });
      }).catch((e) => { if (current) setError({ key: queryKey, message: e.message }); })
        .finally(() => { if (current) setLoading(false); });
    }, 250);
    return () => { current = false; clearTimeout(timer); };
  }, [queryKey, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  // After an assistant turn the same search runs again in place (the typed filters are untouched).
  useTurnRefresh(() => setTick((n) => n + 1));
  useEditorSnapshot(() => {
    const fields = changedFields({ q: "", kind: "", from: "", to: "" }, { q, kind, from, to });
    return { kind: "search-form", object_id: null, dirty: Object.keys(fields).length > 0, fields,
      scope: { session_id: sessionId || null }, applied_query: currentResult ? JSON.parse(queryKey) : null };
  });
  const clearScope = () => {
    const params = new URLSearchParams(route.query);
    params.delete("session_id"); params.delete("session_title");
    window.location.hash = `#/buscar${params.size ? `?${params}` : ""}`;
  };

  return (
    <div>
      <PageHeader title="Buscar" description={sessionId ? "Busca en la transcripción de la sesión indicada. Cada resultado lleva a su momento exacto." : "Busca una palabra en todas las transcripciones. Cada resultado lleva al momento exacto de la sesión."} />
      {sessionId && <div className="mb-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center" aria-label="Ámbito de búsqueda">
        <div className="w-full min-w-0 flex-1">
          <p className="font-semibold break-words">Sólo esta sesión{sessionTitle ? `: ${sessionTitle}` : ""}</p>
          <p className="help break-all">ID: {sessionId}</p>
        </div>
        <button type="button" className="btn" onClick={clearScope}>Buscar en todas las sesiones</button>
      </div>}
      <div className="mb-4 grid gap-2 md:grid-cols-[minmax(0,1fr)_150px_140px_140px]">
        <input className="field" autoFocus placeholder="salario, presupuesto, entrega…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Palabras" />
        <select className="field" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo">
          <option value="">Todos los tipos</option>
          {Object.entries(KIND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <input className="field" type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Desde" />
        <input className="field" type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="Hasta" />
      </div>
      {currentError && <div className="mb-3 flex flex-wrap items-center gap-3" role="alert"><p className="help">{currentError}</p><button type="button" className="btn" onClick={() => setTick((n) => n + 1)}>Reintentar búsqueda</button></div>}
      {!currentResult ? (
        <p className="help" role="status">{loading ? "Buscando…" : currentError ? "Los filtros se conservan para reintentar." : "Escribe al menos dos letras."}</p>
      ) : currentResult.sessions.length === 0 ? (
        <Empty title="Sin resultados">Prueba con otra palabra: la búsqueda ignora acentos y completa la última palabra.</Empty>
      ) : (
        <div className="grid gap-4">
          <p className="help" role="status">{currentResult.total} {currentResult.total === 1 ? "coincidencia mostrada" : "coincidencias mostradas"} en {currentResult.sessions.length} {currentResult.sessions.length === 1 ? "sesión" : "sesiones"}{sessionId ? " · Sólo esta sesión" : ""}</p>
          {currentResult.sessions.map(({ session, hits }) => (
            <section key={session.id} className="panel-white">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <a href={`#/sesiones/${session.id}`} className="min-w-0 flex-1 truncate text-[15px] font-semibold" style={{ color: "var(--accent)" }}>{session.title}</a>
                <span className="chip">{KIND_LABEL[session.kind]}</span>
                <span className="help">{fmtDateTime(session.started_at)}</span>
              </div>
              {hits.map((h) => (
                <a key={h.segment_id} href={`#/sesiones/${session.id}?t=${h.start_s}`} className={`seg seg-${h.speaker}`}>
                  <span className="t num">{fmtClock(h.start_s)}</span>
                  <span className="who">{SPEAKER_LABEL[h.speaker] || h.speaker}</span>
                  <span className="text min-w-0 break-words" dangerouslySetInnerHTML={{ __html: escapeButMark(h.snippet) }} />
                </a>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

// The snippet comes from SQLite with <mark> markers around matches; everything else is escaped.
function escapeButMark(snippet) {
  const escaped = snippet.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return escaped.replace(/&lt;mark&gt;/g, "<mark>").replace(/&lt;\/mark&gt;/g, "</mark>");
}
