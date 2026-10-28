import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { Lane, StatePill } from "../components/ui.jsx";
import { isoClock } from "../format.js";
import { changedFields, rebaseForm } from "../copilot-context.js";
import { useCopilotRefresh, useCopilotView } from "../copilot-view.js";

const DASH = "\u2014";

// green above the warning threshold, amber at it, red at the danger one (the same days Cassandra warns at)
const tone = (days, warn, danger) =>
  days === null || days === undefined ? "var(--muted)" : days <= danger ? "var(--danger)" : days <= warn ? "var(--warn)" : "var(--ok)";

function CertCell({ tls }) {
  if (!tls) return <span className="help num" data-testid="site-cert-days">{DASH}</span>;
  const bad = tls.ok === false;
  const days = tls.days_left;
  const color = bad ? "var(--danger)" : tone(days, 21, 7);
  return (
    <span className="num" data-testid="site-cert-days" style={{ color }} title={tls.error || tls.issuer || ""}>
      {days === null || days === undefined ? (bad ? "!" : DASH) : `${days} d`}
    </span>
  );
}

function DomainCell({ domain }) {
  const days = domain?.days_left;
  return (
    <span className="num" data-testid="site-domain-days" style={{ color: tone(days, 30, 7) }} title={domain?.detail || domain?.registrar || ""}>
      {days === null || days === undefined ? DASH : `${days} d`}
    </span>
  );
}

const signed = (n) => (n === null || n === undefined ? DASH : `${n > 0 ? "+" : ""}${Math.round(n * 10) / 10}`);
const deltaColor = (n) => (n === null || n === undefined || n === 0 ? "var(--muted)" : n < 0 ? "var(--danger)" : "var(--ok)");

function SeoPanel({ site, seo, t, lang, onRun, onBaseline }) {
  const running = seo?.state === "running";
  return (
    <div className="mt-2 space-y-1 border-t pt-2" style={{ borderColor: "var(--line)" }} data-testid="site-seo">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold" title={t("seo_source")}>{t("seo_title")}</div>
        <div className="flex gap-2">
          <button type="button" className="btn btn-sm" disabled={running} onClick={() => onRun(site)} data-testid="seo-run">{t("seo_run")}</button>
          {seo?.score !== null && seo?.score !== undefined && (
            <button type="button" className="btn btn-sm" onClick={() => onBaseline(site)} data-testid="seo-baseline">{t("seo_baseline")}</button>
          )}
        </div>
      </div>
      {(!seo || seo.state === "off") && <div className="help">{t("seo_off")}</div>}
      {seo?.state === "pending" && <div className="help">{t("seo_pending")}</div>}
      {running && <div className="help">{t("seo_running")}</div>}
      {seo?.state === "unavailable" && (
        <div style={{ color: "var(--warn)" }} data-testid="seo-error">
          {t("seo_unavailable", { error: seo.error_kind && t(`seo_err_${seo.error_kind}`) !== `seo_err_${seo.error_kind}` ? t(`seo_err_${seo.error_kind}`) : seo.error || "" })}
        </div>
      )}
      {seo?.score !== null && seo?.score !== undefined && (
        <>
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span><span className="help">{t("seo_score")}</span> <span className="num text-[20px] font-semibold" data-testid="seo-score">{Math.round(seo.score * 10) / 10}</span></span>
            {seo.state === "unavailable" && seo.scored_at ? <span className="help">{t("seo_measured")} {isoClock(seo.scored_at, lang)}</span> : null}
            <span className="num" style={{ color: deltaColor(seo.delta_previous) }} data-testid="seo-delta-prev">{signed(seo.delta_previous)} <span className="help">{t("seo_vs_prev")}</span></span>
            <span className="num" style={{ color: deltaColor(seo.delta_baseline) }} data-testid="seo-delta-base">{signed(seo.delta_baseline)} <span className="help">{t("seo_vs_base")}</span></span>
          </div>
          {seo.categories?.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1" data-testid="seo-categories">
              {seo.categories.map((c) => (
                <span key={c.name} className="num">
                  <span className="help">{c.name}</span> {Math.round(c.score)}
                  {c.delta_previous ? <span style={{ color: deltaColor(c.delta_previous) }}> {signed(c.delta_previous)}</span> : null}
                </span>
              ))}
            </div>
          )}
          <div data-testid="seo-critical">
            {seo.critical?.length ? (
              <>
                <div style={{ color: "var(--danger)" }}>{t("seo_critical")}</div>
                <ul className="ml-4 list-disc">{seo.critical.map((f) => <li key={f.id || f.title}>{f.title}{f.category ? <span className="help"> {"·"} {f.category}</span> : null}</li>)}</ul>
              </>
            ) : <div className="help">{t("seo_no_critical")}</div>}
          </div>
          {seo.new_findings?.length > 0 && <div className="help">{t("seo_new")}: {seo.new_findings.map((f) => f.title).slice(0, 6).join(" · ")}</div>}
          {seo.resolved_findings?.length > 0 && <div className="help">{t("seo_resolved")}: {seo.resolved_findings.map((f) => f.title).slice(0, 6).join(" · ")}</div>}
        </>
      )}
      {seo?.last_run && (
        <div className="help">
          {t("seo_last")}: {isoClock(seo.last_run, lang)}
          {seo.next_run ? ` · ${t("seo_next")}: ${isoClock(seo.next_run, lang)}` : ""}
          {seo.runs ? ` · ${t("seo_runs", { n: seo.runs })}` : ""}
        </div>
      )}
    </div>
  );
}

function Detail({ site, seo, onRunSeo, onBaselineSeo, t, lang }) {
  const tls = site.tls;
  const domain = site.domain;
  const dns = site.dns || {};
  return (
    <div className="space-y-1 px-3 pb-3 pt-2 text-[12px]" style={{ background: "var(--surface-2)" }} data-testid="site-detail">
      <div className="help">
        {site.url} {"\u00b7"} {t("site_every")} {site.interval_min} min {"\u00b7"} {t("site_expect")} {(site.expect_status || []).join(", ")}
      </div>
      {site.cause && site.state !== "up" && <div style={{ color: "var(--danger)" }}>{site.cause}</div>}
      {site.failing_checks ? <div style={{ color: "var(--warn)" }}>{t("site_failing", { n: site.failing_checks })}</div> : null}
      {site.redirect && <div>{t("site_redirect")}: {site.redirect}</div>}
      {site.keyword && (
        <div>
          {t("site_keyword")} "{site.keyword}": {site.keyword_ok === false ? t("site_keyword_missing") : site.keyword_ok ? t("site_keyword_found") : DASH}
        </div>
      )}
      <div>
        {t("site_cert")}: {tls ? (tls.error ? tls.error : `${t("site_valid_until")} ${isoClock(tls.not_after, lang)}${tls.issuer ? ` \u00b7 ${t("site_issuer")} ${tls.issuer}` : ""}`) : t("site_no_tls")}
      </div>
      <div>
        {t("site_domain")} {domain?.name || DASH}:{" "}
        {domain?.expires
          ? `${t("site_expires")} ${isoClock(domain.expires, lang)}${domain.registrar ? ` \u00b7 ${domain.registrar}` : ""}`
          : t("site_domain_unknown")}
      </div>
      {dns.addresses?.length > 0 && (
        <div className="help num">
          DNS {dns.addresses.join(", ")}
          {dns.changes ? ` \u00b7 ${t("site_dns_changed")} ${dns.changes}` : ""}
        </div>
      )}
      {site.last_change && (
        <div className="help">
          {t("site_last_change")}: {site.last_change.from} {"\u2192"} {site.last_change.to} {"\u00b7"} {isoClock(site.last_change.at, lang)}
        </div>
      )}
      <div className="help">
        {t("site_last_check")}: {isoClock(site.last_check, lang)}
        {site.open_incident && (
          <>
            {" \u00b7 "}
            <a href={`#/incidents/${site.open_incident}`}>{t("see_incident")} #{site.open_incident}</a>
          </>
        )}
      </div>
      <SeoPanel site={site} seo={seo} t={t} lang={lang} onRun={onRunSeo} onBaseline={onBaselineSeo} />
    </div>
  );
}
const parseExpect = (text) => text.split(/[\s,]+/).filter(Boolean);

const baseOf = (site) => ({
  name: site.name,
  url: site.url,
  expect: (site.expect_status || []).join(", "),
  keyword: site.keyword || "",
  interval: String(site.interval_min),
  enabled: Boolean(site.enabled),
  seo: site.seo_interval_h ? String(site.seo_interval_h) : "",
});

// The arguments of the update for the fields the user changed (a site edit is a patch: what the assistant changed meanwhile is kept).
const siteUpdate = (changed) => {
  const body = {};
  if ("name" in changed) body.name = changed.name;
  if ("url" in changed) body.url = changed.url;
  if ("expect" in changed) body.expect_status = parseExpect(changed.expect);
  if ("keyword" in changed) body.keyword = changed.keyword;
  if ("interval" in changed) body.interval_min = Number(changed.interval);
  if ("enabled" in changed) body.enabled = changed.enabled;
  if ("seo" in changed) body.seo_interval_h = changed.seo === "" ? 0 : Number(changed.seo);
  return body;
};

function EditRow({ site, onSave, onRemove, t }) {
  const base = useMemo(() => baseOf(site), [site.name, site.url, (site.expect_status || []).join(", "), site.keyword, site.interval_min, site.enabled, site.seo_interval_h]); // eslint-disable-line react-hooks/exhaustive-deps
  const [form, setForm] = useState(base);
  const baseRef = useRef(base);
  // A refreshed site (the assistant edited it) updates the fields the user did not touch and keeps the ones being typed.
  useEffect(() => {
    setForm((current) => rebaseForm(baseRef.current, base, current));
    baseRef.current = base;
  }, [base]);
  const changed = changedFields(base, form);
  useCopilotView(`site-form:${site.id}`, Object.keys(changed).length ? { id: site.id, fields: changed } : null);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const save = () => {
    if (!Object.keys(changed).length) return;
    onSave({ id: site.id, ...siteUpdate(changed) });
  };
  return (
    <div className="flex flex-wrap items-center gap-2 border-t px-3 py-2" style={{ borderColor: "var(--line)" }} data-testid="site-edit-row">
      <input className="field flex-[1_1_130px]" value={form.name} onChange={set("name")} aria-label={t("name")} />
      <input className="field mono flex-[2_1_220px]" value={form.url} onChange={set("url")} aria-label={t("url")} />
      <input className="field num w-[110px]" value={form.expect} onChange={set("expect")} aria-label={t("site_expect")} title={t("site_expect")} />
      <input className="field flex-[1_1_120px]" value={form.keyword} onChange={set("keyword")} placeholder={t("site_keyword")} aria-label={t("site_keyword")} />
      <input className="field num w-[80px]" type="number" min="1" max="1440" value={form.interval} onChange={set("interval")} aria-label={t("site_interval")} title={t("site_interval")} />
      <input className="field num w-[90px]" type="number" min="0" max="720" value={form.seo} onChange={set("seo")} placeholder="SEO h" aria-label={t("seo_every")} title={t("seo_every")} data-testid="site-seo-interval" />
      <label className="flex items-center gap-1 text-[12px]">
        <input type="checkbox" checked={form.enabled} onChange={set("enabled")} /> {t("site_enabled")}
      </label>
      <div className="flex gap-2">
        <button type="button" className="btn btn-sm" onClick={save}>{t("save")}</button>
        <button type="button" className="btn btn-sm btn-danger" onClick={() => onRemove(site)}>{t("remove")}</button>
      </div>
    </div>
  );
}

function AddRow({ onAdd, t }) {
  const [form, setForm] = useState({ url: "", name: "", keyword: "", interval: "" });
  useCopilotView("site-add", Object.values(form).some(Boolean) ? { fields: Object.fromEntries(Object.entries(form).filter(([, v]) => v)) } : null);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const add = async () => {
    const body = { url: form.url.trim() };
    if (form.name.trim()) body.name = form.name.trim();
    if (form.keyword.trim()) body.keyword = form.keyword.trim();
    if (form.interval) body.interval_min = Number(form.interval);
    if (await onAdd(body)) setForm({ url: "", name: "", keyword: "", interval: "" });
  };
  return (
    <div className="flex flex-wrap items-center gap-2 border-t px-3 py-3" style={{ borderColor: "var(--line)" }} data-testid="site-add-row">
      <input className="field mono flex-[2_1_220px]" value={form.url} onChange={set("url")} placeholder="https://example.com/" aria-label={t("url")} />
      <input className="field flex-[1_1_130px]" value={form.name} onChange={set("name")} placeholder={t("name")} aria-label={t("name")} />
      <input className="field flex-[1_1_120px]" value={form.keyword} onChange={set("keyword")} placeholder={t("site_keyword")} aria-label={t("site_keyword")} />
      <input className="field num w-[80px]" type="number" min="1" max="1440" value={form.interval} onChange={set("interval")} placeholder="5" aria-label={t("site_interval")} title={t("site_interval")} />
      <button type="button" className="btn btn-sm btn-primary" disabled={!form.url.trim()} onClick={add}>{t("site_add")}</button>
    </div>
  );
}

export default function SitesCard() {
  const { act, t, lang } = useApp();
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [seo, setSeo] = useState({});

  const load = useCallback(async () => {
    try {
      setData(await api.sites(24));
    } catch {
      // the shell shows the connection error
    }
    try {
      const overview = await api.seoSites();
      setSeo(Object.fromEntries((overview.sites || []).map((s) => [s.id, s])));
    } catch {
      // an older server has no SEO routes: the sites card works without them
    }
  }, []);
  const seoRunning = Object.values(seo).some((s) => s.state === "running");
  useEffect(() => {
    load();
    const timer = setInterval(load, seoRunning ? 3000 : 15000);
    return () => clearInterval(timer);
  }, [load, seoRunning]);

  useCopilotView("sites", { open, editing });
  useCopilotRefresh(load);

  const checkNow = async () => {
    setBusy(true);
    await act(() => api.checkSites(), t("sites_checked"));
    await load();
    setBusy(false);
  };
  const save = async (body) => {
    const result = await act(() => api.watchSite(body), t("saved"));
    await load();
    return result;
  };
  const runSeo = async (site) => {
    await act(() => api.runSeo(site.id), t("seo_run_done"));
    await load();
  };
  const baselineSeo = async (site) => {
    await act(() => api.seoBaseline(site.id), t("seo_baseline_done"));
    await load();
  };
  const remove = async (site) => {
    if (!window.confirm(t("site_remove_confirm", { name: site.name }))) return;
    await act(() => api.unwatchSite(site.id));
    await load();
  };

  if (!data || (!data.summary?.enabled && !data.sites.length)) return null;
  const sites = data.sites;
  const lanesWindow = { since: data.since, until: data.until };
  return (
    <section className="panel p-0" data-testid="sites-card">
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 pb-1 pt-3">
        <div>
          <h2 className="text-[13px] font-semibold" style={{ color: "var(--muted)" }}>{t("sites_title")}</h2>
          <div className="help text-[11px]">{t("sites_help")}</div>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn btn-sm" onClick={checkNow} disabled={busy || !sites.length}>{busy ? t("checking") : t("sites_check")}</button>
          <button type="button" className="btn btn-sm" onClick={() => setEditing(!editing)} aria-pressed={editing}>{editing ? t("sites_done") : t("sites_edit")}</button>
        </div>
      </div>
      {data.error && <div className="px-3 pb-2 text-[12px]" style={{ color: "var(--warn)" }}>{data.error}</div>}
      {sites.length === 0 && <div className="help px-3 pb-3 text-[12px]">{t("sites_empty")} <span className="mono">{data.sites_file}</span></div>}
      {sites.map((site) => (
        <React.Fragment key={site.id}>
          <div className="site-row" data-testid="site-row" role="button" tabIndex={0} aria-expanded={open === site.id}
            onClick={() => setOpen(open === site.id ? null : site.id)} onKeyDown={(e) => e.key === "Enter" && setOpen(open === site.id ? null : site.id)}>
            <div className="min-w-0">
              <div className="truncate font-medium">{site.name}</div>
              <div className="help num truncate text-[11px]">
                {site.id}
                {site.lane?.uptime_pct !== null && site.lane?.uptime_pct !== undefined ? ` \u00b7 ${site.lane.uptime_pct}%` : ""}
                {seo[site.id]?.score !== null && seo[site.id]?.score !== undefined ? (
                  <span data-testid="site-seo-score">{` \u00b7 SEO ${Math.round(seo[site.id].score)}`}<span style={{ color: seo[site.id].delta_previous < 0 ? "var(--danger)" : "var(--muted)" }}>{seo[site.id].delta_previous ? ` (${signed(seo[site.id].delta_previous)})` : ""}</span></span>
                ) : null}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              <StatePill state={site.state} t={t} />
              {site.status ? <span className="help num text-[11px]">{site.status}</span> : null}
            </div>
            <div className="num text-[12px]" title={t("latency")}>{site.latency_ms ? `${Math.round(site.latency_ms)} ms` : DASH}</div>
            <div className="text-[12px]" title={t("site_cert")}><CertCell tls={site.tls} /></div>
            <div className="text-[12px]" title={t("site_domain")}><DomainCell domain={site.domain} /></div>
            <div className="lane-cell">
              {site.lane ? <Lane segments={site.lane.segments} since={lanesWindow.since} until={lanesWindow.until} t={t} lang={lang} /> : <div className="lane" />}
            </div>
          </div>
          {open === site.id && <Detail site={site} seo={seo[site.id]} onRunSeo={runSeo} onBaselineSeo={baselineSeo} t={t} lang={lang} />}
        </React.Fragment>
      ))}
      {editing && (
        <div data-testid="sites-editor">
          <div className="help px-3 pt-2 text-[11px]">{t("sites_file")}: <span className="mono">{data.sites_file}</span></div>
          {sites.map((site) => <EditRow key={site.id} site={site} onSave={save} onRemove={remove} t={t} />)}
          <AddRow onAdd={save} t={t} />
        </div>
      )}
    </section>
  );
}