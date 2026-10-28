import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { fmtDateTime } from "../format.js";

const pct = (value) => (value === null || value === undefined ? "—" : `${Math.round(value * 100)} %`);

function Row({ result }) {
  const without = result.without_echo_cleanup || {};
  const verdict = result.meets;
  return (
    <tr style={{ borderTop: "1px solid var(--line)" }}>
      <th scope="row" className="py-2 pr-3 text-left font-semibold" title={result.about}>{result.case}</th>
      <td className="num py-2 pr-3 text-right">{pct(result.found)}</td>
      <td className="num py-2 pr-3 text-right">{pct(result.side)}</td>
      <td className="num py-2 pr-3 text-right" title="Líneas del micrófono que eran el audio del sistema. Con la limpieza de eco / sin ella.">{result.leaked} / {without.leaked ?? "—"}</td>
      <td className="num py-2 pr-3 text-right">{result.invented}</td>
      <td className="num py-2 pr-3 text-right">{result.lines}</td>
      <td className="num py-2 pr-3 text-right">{result.seconds}</td>
      <td className="py-2 text-right">
        {verdict ? <span className={`chip ${verdict.ok ? "chip-ok" : "chip-warn"}`} title={verdict.failures.join(" · ")}>{verdict.ok ? "dentro" : "por debajo"}</span> : <span className="help">—</span>}
      </td>
    </tr>
  );
}

/** Measures the configured engine on four hard calls with a known script and shows the scores (also without the echo clean-up). */
export default function Bench({ notify }) {
  const [info, setInfo] = useState(null);
  const [job, setJob] = useState(null);
  const timer = useRef(null);
  const load = useCallback(() => api.bench().then((data) => { setInfo(data); if (data.running) setJob(data.running); }).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const running = job && (job.status === "queued" || job.status === "running");
  useEffect(() => {
    clearInterval(timer.current);
    if (!running) return undefined;
    timer.current = setInterval(async () => {
      try {
        const next = await api.benchJob(job.job_id);
        setJob(next);
        if (next.status === "done" || next.status === "error") load();
      } catch { /* the next tick tries again */ }
    }, 2000);
    return () => clearInterval(timer.current);
  }, [running, job && job.job_id, load]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    try {
      setJob(await api.startBench({}));
    } catch (error) {
      notify(error.message);
    }
  };
  if (!info) return null;
  const last = info.last;
  return (
    <section className="panel mb-5" aria-labelledby="bench-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="bench-title" className="text-[17px] font-semibold">Banco de transcripción</h2>
        <button type="button" className="btn btn-sm btn-primary" disabled={running} onClick={start}>{running ? "Midiendo…" : "Medir el motor"}</button>
      </div>
      <p className="help mb-2">
        Cuatro llamadas con guion conocido (voces superpuestas, eco por altavoces, música de fondo y silencio) pasan por el mismo camino que una grabación: puerta de silencio, modelo, filtro de alucinaciones, limpieza de eco y unión de pistas.
        Mide el motor configurado ({info.engine && info.engine.model ? `${info.engine.name} ${info.engine.model}` : info.engine && info.engine.name}) y ocupa la cola de transcripción uno o dos minutos.
      </p>
      {running && <div className="banner banner-processing mb-2" role="status">Midiendo{job.current ? `: ${job.current}` : ""} ({job.done}/{job.cases.length})</div>}
      {job && job.status === "error" && <div className="mb-2 rounded-md border p-3 text-[13px]" style={{ background: "var(--danger-bg)", color: "var(--danger-ink)", borderColor: "var(--danger-line)" }} role="alert">{job.error}</div>}
      {last ? (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="help">
                <th scope="col" className="pb-1 pr-3 text-left">Caso</th>
                <th scope="col" className="pb-1 pr-3 text-right" title="Palabras del guion que están en la transcripción cerca de su momento">Palabras halladas</th>
                <th scope="col" className="pb-1 pr-3 text-right" title="De las halladas, las que van en el lado correcto de la llamada">Lado correcto</th>
                <th scope="col" className="pb-1 pr-3 text-right" title="Líneas del micrófono que eran el audio del sistema: con limpieza / sin limpieza de eco">Eco colado</th>
                <th scope="col" className="pb-1 pr-3 text-right" title="Líneas cuyas palabras no están en el guion">Inventadas</th>
                <th scope="col" className="pb-1 pr-3 text-right">Líneas</th>
                <th scope="col" className="pb-1 pr-3 text-right">Segundos</th>
                <th scope="col" className="pb-1 text-right" title="Frente a lo medido con el motor por defecto; solo informa">Referencia</th>
              </tr>
            </thead>
            <tbody>{last.cases.map((result) => <Row key={result.case} result={result} />)}</tbody>
          </table>
          <p className="help mt-2">Última medición: {fmtDateTime(last.finished_at)} con {last.engine && last.engine.model ? `${last.engine.name} ${last.engine.model}` : last.engine && last.engine.name} en {last.engine && last.engine.device_used ? last.engine.device_used : "—"}.</p>
        </div>
      ) : (
        <p className="help">Todavía no se ha medido este motor.</p>
      )}
    </section>
  );
}
