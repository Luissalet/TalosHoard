import { useEffect, useRef, useState } from "react";
import { api, errorMessage, formatDuration, localeFor, type ProjectResume as ResumeResult } from "../api";
import { STRINGS, type Lang } from "../i18n";
import { useEditorSnapshot } from "../copilot";

export function ProjectResume({ project, lang, onClose }: { project: string; lang: Lang; onClose: () => void }) {
  const t = STRINGS[lang];
  const [days, setDays] = useState("30");
  const [limit, setLimit] = useState("5");
  const [result, setResult] = useState<ResumeResult | null>(null);
  const [appliedLimit, setAppliedLimit] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);
  useEditorSnapshot(() => ({ kind: "project-resume-filter", object_id: null,
    dirty: days !== "30" || limit !== "5", fields: { project, days, limit } }));
  const load = async (selectedDays: number, selectedLimit: number) => {
    const current = ++request.current;
    setResult(null); setAppliedLimit(null); setError(null); setBusy(true);
    try {
      const response = await api.projectResume({ project, days: selectedDays, limit: selectedLimit });
      if (current !== request.current) return;
      setResult(response); setAppliedLimit(selectedLimit);
    } catch (failure) { if (current === request.current) setError(errorMessage(failure)); }
    finally { if (current === request.current) setBusy(false); }
  };
  useEffect(() => {
    void load(30, 5);
    return () => { request.current++; };
  }, [project]); // Each project mounts its own draft; later responses cannot replace it.
  const invalidate = () => { request.current++; setResult(null); setAppliedLimit(null); setError(null); setBusy(false); };
  const date = (value: number | null) => value == null ? t.resume_unknown : new Date(value * 1000).toLocaleString(localeFor(lang));

  return <section className="card project-resume" aria-label={`${t.resume_title}: ${project}`}>
    <div className="resume-heading"><h2>{t.resume_title}: {project}</h2><button className="btn" type="button" onClick={onClose}>{t.resume_close}</button></div>
    <p className="muted">{t.resume_scope}</p>
    <form className="resume-controls" onSubmit={(event) => { event.preventDefault(); void load(Number(days), Number(limit)); }}>
      <label>{t.resume_days}<input type="number" min={1} max={180} step={1} required value={days} onChange={(event) => { setDays(event.target.value); invalidate(); }} /></label>
      <label>{t.resume_limit}<input type="number" min={1} max={10} step={1} required value={limit} onChange={(event) => { setLimit(event.target.value); invalidate(); }} /></label>
      <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? t.resume_loading : error ? t.resume_retry : t.resume_read}</button>
    </form>
    {busy && <p role="status">{t.resume_loading}</p>}
    {error && <p role="alert">{error}</p>}
    {result && <div className="resume-result">
      <p>{t.resume_applied}: {date(result.since)} — {date(result.until)} · {t.resume_per_type}: {appliedLimit}</p>
      <dl><dt>{t.resume_last}</dt><dd>{date(result.last_activity)}</dd><dt>{t.resume_active}</dt><dd>{formatDuration(result.active_s)}</dd></dl>
      <p className="muted">{t.resume_caution}</p>
      {!result.found && <p role="status">{t.resume_none}</p>}
      <h3>{t.resume_windows} ({result.recent_windows.length})</h3>
      <p className="muted">{t.resume_window_scope}</p>
      {result.recent_windows.length ? <ul>{result.recent_windows.map((item, index) => <li key={index}><strong>{item.app}</strong><p>{item.title}</p><p className="muted">{date(item.start)} — {date(item.end)} · {formatDuration(item.duration_s)}</p></li>)}</ul> : <p className="muted">{t.resume_empty}</p>}
      <h3>{t.resume_files} ({result.recent_files.length})</h3>
      {result.recent_files.length ? <ul>{result.recent_files.map((item) => <li key={item.path}><p>{item.path}</p><p className="muted">{date(item.ts)}</p></li>)}</ul> : <p className="muted">{t.resume_empty}</p>}
      <h3>{t.resume_commits} ({result.recent_commits.length})</h3>
      {result.recent_commits.length ? <ul>{result.recent_commits.map((item, index) => <li key={index}><strong>{item.subject}</strong><p className="muted">{item.sha} · {date(item.ts)}</p></li>)}</ul> : <p className="muted">{t.resume_empty}</p>}
    </div>}
  </section>;
}
