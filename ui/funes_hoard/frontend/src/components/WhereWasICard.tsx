import { useEffect, useReducer, useRef } from "react";
import { FileText, GitCommit, History } from "lucide-react";
import { api, errorMessage, formatClock, formatDuration, formatLongDate, isoDay, localeFor } from "../api";
import { STRINGS, type Lang } from "../i18n";
import { useEditorSnapshot, useTurnRefresh } from "../copilot";
import { initialWhere, whereQuery, whereReducer, type WhereDraft, type WhereQuery } from "./where-state";

export function WhereWasICard({ day, isToday, lang, onShow }: {
  day: string; isToday: boolean; lang: Lang; onShow: (day: string, at?: number) => void;
}) {
  const t = STRINGS[lang];
  const [state, dispatch] = useReducer(whereReducer, undefined, () => initialWhere(day, isToday));
  const ticket = useRef(0);
  const load = async (query: WhereQuery) => {
    const current = ++ticket.current;
    dispatch({ type: "start", day, ticket: current });
    try {
      const data = await api.whereWasI(query);
      dispatch({ type: "resolve", ticket: current, data, query });
    } catch (error) { dispatch({ type: "reject", ticket: current, error: errorMessage(error) }); }
  };
  useEffect(() => {
    dispatch({ type: "reset", day, isToday });
    void load(initialWhere(day, isToday).applied);
    // Tickets never repeat across days or StrictMode's initial effect replay.
    return () => { ticket.current++; };
  }, [day, isToday]);
  useTurnRefresh(() => { void load(state.applied); });
  useEditorSnapshot(() => ({ kind: "where-before-filter", object_id: null,
    dirty: !!state.draft.before || state.draft.contexts !== "3" || state.draft.allCategories,
    fields: { day, before: state.draft.before, contexts: state.draft.contexts,
      all_categories: state.draft.allCategories, applied_before: state.result?.data.before ?? null } }));
  const edit = (draft: WhereDraft) => dispatch({ type: "edit", draft });
  const read = () => {
    try { void load(whereQuery(state.draft, day, isToday)); }
    catch (error) { dispatch({ type: "input-error", error: errorMessage(error) }); }
  };
  const reset = () => {
    const next = initialWhere(day, isToday);
    dispatch({ type: "reset", day, isToday });
    void load(next.applied);
  };
  const result = state.day === day ? state.result : null;
  const fileName = (path: string) => path.split(/[\\/]/).pop() || path;
  return <section className="card where-card" style={{ marginTop: 16 }} aria-label={t.where_title}>
    <h2 className="section-title"><History size={14} aria-hidden="true" /> {t.where_title}</h2>
    <p className="muted where-scope">{t.where_scope}</p>
    <form className="where-controls" onSubmit={(event) => { event.preventDefault(); read(); }}>
      <label>{t.where_before}<input type="datetime-local" value={state.draft.before} onChange={(event) => edit({ ...state.draft, before: event.target.value })} /></label>
      <label>{t.where_count}<input type="number" min={1} max={20} step={1} required value={state.draft.contexts} onChange={(event) => edit({ ...state.draft, contexts: event.target.value })} /></label>
      <label className="where-checkbox"><input type="checkbox" checked={state.draft.allCategories} onChange={(event) => edit({ ...state.draft, allCategories: event.target.checked })} />{t.where_all_categories}</label>
      <div className="where-actions"><button className="btn btn-primary" type="submit" disabled={state.busy}>{state.busy ? t.where_loading : state.error ? t.resume_retry : t.where_read}</button>
        <button className="btn" type="button" onClick={reset}>{t.where_reset}</button></div>
    </form>
    {state.busy && <p role="status">{t.where_loading}</p>}
    {state.error && <p className="form-error" role="alert">{state.error}</p>}
    {result && <div>
      <p className="where-applied">{t.where_applied}: <time dateTime={new Date(result.data.before * 1000).toISOString()}>{new Date(result.data.before * 1000).toLocaleString(localeFor(lang), { timeZoneName: "short" })}</time>
        {" · "}{t.where_maximum}: {result.query.contexts}{" · "}{result.query.all_categories ? t.where_all_applied : t.where_work_applied}</p>
      <p className="muted where-scope">{t.resume_caution}</p>
      {!result.data.contexts.length && <p className="muted" role="status">{t.where_empty}</p>}
      <div className="where-list">{result.data.contexts.map((c) => {
        const cDay = isoDay(new Date(c.end * 1000));
        return <div className="where-item" key={`${c.start}-${c.project ?? c.app}`}>
          <div className="row" style={{ justifyContent: "space-between", gap: 8, flexWrap: "nowrap" }}>
            <div style={{ minWidth: 0 }}><strong>{c.project || c.app}</strong><span className="muted"> · {cDay !== day ? `${formatLongDate(c.start, lang)}, ` : ""}{formatClock(c.start, lang)}–{formatClock(c.end, lang)} · {formatDuration(c.duration_s)}</span>
              {(c.recent_titles?.length ? c.recent_titles.slice(0, 2) : [c.title || "—"]).map((title) => <div className="detail-title where-title" title={title} key={title}>{title}</div>)}</div>
            <button className="btn btn-small" type="button" onClick={() => onShow(cDay, c.end - 1)}>{t.where_show}</button>
          </div>
          {(c.files.length > 0 || c.commits.length > 0) && <ul className="where-refs">
            {c.files.slice(0, 3).map((f) => <li key={f} title={f}><FileText size={12} aria-hidden="true" /> {fileName(f)}</li>)}
            {c.commits.slice(0, 2).map((cm) => <li key={cm.sha} title={cm.sha}><GitCommit size={12} aria-hidden="true" /> {cm.subject} <code>{cm.sha.slice(0, 7)}</code></li>)}
          </ul>}
        </div>;
      })}</div>
    </div>}
  </section>;
}
