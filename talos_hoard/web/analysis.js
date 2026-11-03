// Meeting requirements and procedure drafts. Plain DOM, textContent only: transcripts and window titles are private data, never markup.
const S = {
  es: {
    nav_modules: 'Funciones', nav_analysis: 'Reuniones y procedimientos', title: 'Reuniones y procedimientos',
    intro: 'Clasificación por reglas, sin modelo. Todo es un borrador que una persona o un agente debe revisar.',
    tab_meeting: 'Reunión → requisitos y pendientes', tab_procedure: 'Pantalla → procedimiento', session: 'Sesión', min_conf: 'Confianza mínima', read: 'Leer',
    export_md: 'Exportar Markdown', export_json: 'Exportar JSON', export_commitments: 'Compromisos firmes (para importar)', start: 'Desde', end: 'Hasta', draft: 'Proponer procedimiento',
    p_note: 'Talos registra ventana en primer plano, portapapeles, capturas y archivos recientes; no registra clics ni pulsaciones. El borrador no ejecuta nada en el ordenador observado y enmascara los valores que parecen secretos.',
    commitment: 'Compromisos firmes', proposal: 'Propuestas (no son compromisos)', question: 'Preguntas abiertas', decision: 'Decisiones', requirement: 'Requisitos',
    none: 'Nada detectado.', owner: 'responsable', due: 'fecha', to: 'a', cue: 'indicio', conf: 'confianza', must_answer: 'debe responder', unassigned: 'sin asignar', group: 'el grupo',
    conditional: 'condicional', hedged: 'con reserva', links: 'vinculado a', link_ph: 'Id del entregable o decisión', link_btn: 'Vincular', unlink: 'Quitar',
    open_session: 'Abrir la sesión', summary: (s) => `${s.total} elementos: ${s.by_kind.commitment} compromisos, ${s.by_kind.proposal} propuestas, ${s.open_questions} preguntas abiertas, ${s.by_kind.decision} decisiones, ${s.by_kind.requirement} requisitos.`,
    no_audio: 'El módulo Audio está apagado. Actívalo en Funciones para leer reuniones.', no_activity: 'El módulo Actividad está apagado. Actívalo en Funciones para proponer un procedimiento.',
    no_sessions: 'No hay reuniones grabadas.', steps: 'Pasos', inputs: 'Entradas', outputs: 'Salidas', unknowns: 'Lo que no se sabe', evidence: 'evidencia', shot: 'captura', no_shot: 'sin captura',
    masked: 'enmascarado', loading: 'Cargando…', orphans: 'Vínculos sin elemento (la transcripción cambió)',
  },
  en: {
    nav_modules: 'Modules', nav_analysis: 'Meetings and procedures', title: 'Meetings and procedures',
    intro: 'Classified by rules, no model. Everything is a draft that a person or an agent must review.',
    tab_meeting: 'Meeting → requirements and pending items', tab_procedure: 'Screen → procedure', session: 'Session', min_conf: 'Minimum confidence', read: 'Read',
    export_md: 'Export Markdown', export_json: 'Export JSON', export_commitments: 'Firm commitments (to import)', start: 'From', end: 'To', draft: 'Propose a procedure',
    p_note: 'Talos records the foreground window, clipboard, screenshots and recent files; it does not record clicks or keystrokes. The draft executes nothing on the observed computer and masks values that look like secrets.',
    commitment: 'Firm commitments', proposal: 'Proposals (not commitments)', question: 'Open questions', decision: 'Decisions', requirement: 'Requirements',
    none: 'Nothing detected.', owner: 'owner', due: 'due', to: 'to', cue: 'cue', conf: 'confidence', must_answer: 'must answer', unassigned: 'unassigned', group: 'the group',
    conditional: 'conditional', hedged: 'hedged', links: 'linked to', link_ph: 'Deliverable or decision id', link_btn: 'Link', unlink: 'Remove',
    open_session: 'Open the session', summary: (s) => `${s.total} items: ${s.by_kind.commitment} commitments, ${s.by_kind.proposal} proposals, ${s.open_questions} open questions, ${s.by_kind.decision} decisions, ${s.by_kind.requirement} requirements.`,
    no_audio: 'The Audio module is off. Turn it on in Modules to read meetings.', no_activity: 'The Activity module is off. Turn it on in Modules to propose a procedure.',
    no_sessions: 'No recorded meetings.', steps: 'Steps', inputs: 'Inputs', outputs: 'Outputs', unknowns: 'Unknowns', evidence: 'evidence', shot: 'screenshot', no_shot: 'no screenshot',
    masked: 'masked', loading: 'Loading…', orphans: 'Links without an item (the transcript changed)',
  },
};
const $ = (s) => document.querySelector(s);
const ORDER = ['commitment', 'decision', 'requirement', 'question', 'proposal'];
let lang = (() => { try { return localStorage.getItem('talos-lang') || (navigator.language || 'es').slice(0, 2); } catch { return 'es'; } })();
if (!S[lang]) lang = 'es';
let last = { meeting: null, procedure: null };
const t = (k) => S[lang][k];

function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined && text !== null && text !== '') n.textContent = text; if (cls) n.className = cls; return n; }
async function request(path, init = {}) {
  const r = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', 'X-Hoard-Request': '1' } });
  const type = r.headers.get('content-type') || '';
  const body = type.includes('json') ? await r.json() : await r.text();
  if (!r.ok) { const e = new Error(typeof body === 'object' ? (body.detail && body.detail.error) || (typeof body.detail === 'string' ? body.detail : body.error) || r.statusText : r.statusText); e.status = r.status; throw e; }
  return body;
}
const showError = (m) => { $('#error').textContent = m || ''; $('#error').hidden = !m; };
const hms = (s) => { s = Math.max(0, Math.floor(s)); const m = Math.floor(s / 60); return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };

function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach((n) => { const v = S[lang][n.dataset.i18n]; if (typeof v === 'string') n.textContent = v; });
  $('#lang').value = lang;
  if (last.meeting) renderMeeting(last.meeting);
  if (last.procedure) renderProcedure(last.procedure);
}

function who(item) {
  const a = item.addressee || {};
  if (a.kind === 'person' || a.kind === 'speaker') return a.name;
  if (a.kind === 'group') return t('group');
  return t('unassigned');
}

function renderItem(sid, item) {
  const box = el('div', '', 'item');
  box.append(el('div', item.text, 'text'));
  const meta = el('div', '', 'meta');
  const bits = [`${hms(item.segment.start_s)} (${item.speaker})`, `${t('cue')}: «${item.cue}»`, `${t('conf')}: ${item.confidence.toFixed(2)}`];
  if (item.kind === 'commitment') {
    bits.push(`${t('owner')}: ${item.owner}`);
    if (item.counterpart) bits.push(`${t('to')}: ${item.counterpart}`);
    if (item.due || item.due_text) bits.push(`${t('due')}: ${item.due || item.due_text}`);
  } else if (item.kind === 'question') bits.push(`${t('must_answer')}: ${who(item)}`);
  else if (item.kind === 'proposal') { if (item.conditional) bits.push(t('conditional')); if (item.hedged) bits.push(t('hedged')); }
  bits.forEach((b) => meta.append(el('span', b)));
  const open = el('a', t('open_session')); open.href = `/audio/#/sesiones/${encodeURIComponent(sid)}`; meta.append(open);
  box.append(meta);
  const player = el('audio'); player.controls = true; player.preload = 'none';
  player.src = `/audio/api/sessions/${encodeURIComponent(sid)}/audio#t=${item.playback.start_s},${item.playback.end_s}`;
  box.append(player);
  if (item.refs && item.refs.length) {
    const links = el('div', '', 'meta'); links.append(el('span', t('links') + ':'));
    for (const r of item.refs) {
      const tag = el('span', `${r.ref} (${r.ref_kind})`, 'tag'); links.append(tag);
      const rm = el('button', t('unlink')); rm.type = 'button';
      rm.onclick = async () => { try { await request(`/audio/api/sessions/${encodeURIComponent(sid)}/requirements/links?item_id=${encodeURIComponent(item.id)}&ref=${encodeURIComponent(r.ref)}`, { method: 'DELETE' }); await loadMeeting(); } catch (e) { showError(e.message); } };
      links.append(rm);
    }
    box.append(links);
  }
  if (item.kind === 'requirement' || item.kind === 'decision') {
    const form = el('form'); const input = el('input'); input.placeholder = t('link_ph'); input.maxLength = 200; input.setAttribute('aria-label', t('link_ph'));
    const kind = el('select'); for (const k of ['deliverable', 'decision']) { const o = el('option', k); o.value = k; kind.append(o); }
    const b = el('button', t('link_btn')); b.type = 'submit';
    form.append(input, kind, b);
    form.onsubmit = async (e) => { e.preventDefault(); if (!input.value.trim()) return; try { await request(`/audio/api/sessions/${encodeURIComponent(sid)}/requirements/links`, { method: 'POST', body: JSON.stringify({ item_id: item.id, ref: input.value.trim(), ref_kind: kind.value }) }); await loadMeeting(); } catch (err) { showError(err.message); } };
    box.append(form);
  }
  return box;
}

function renderMeeting(data) {
  const root = $('#meeting-items'); root.replaceChildren();
  $('#meeting-summary').textContent = S[lang].summary(data.summary);
  for (const kind of ORDER) {
    const items = data.items.filter((i) => i.kind === kind);
    const g = el('div', '', 'group'); g.append(el('h2', `${t(kind)} (${items.length})`));
    if (!items.length) g.append(el('p', t('none'), 'muted'));
    items.forEach((i) => g.append(renderItem(data.session_id, i)));
    root.append(g);
  }
  if (data.orphan_links && data.orphan_links.length) {
    const g = el('div', '', 'group'); g.append(el('h2', t('orphans')));
    data.orphan_links.forEach((o) => g.append(el('p', `${o.item_id} → ${o.ref}`, 'muted')));
    root.append(g);
  }
}

function exportLinks(sid) {
  const q = `min_confidence=${encodeURIComponent($('#min-conf').value || 0)}`;
  const base = `/audio/api/sessions/${encodeURIComponent(sid)}/requirements`;
  $('#export-md').href = `${base}?format=md&locale=${lang}&${q}`;
  $('#export-json').href = `${base}?${q}`;
  $('#export-commitments').href = `${base}?format=commitments&${q}`;
}

async function loadMeeting() {
  const sid = $('#session').value; if (!sid) return;
  showError(''); $('#meeting-summary').textContent = t('loading');
  try {
    const data = await request(`/audio/api/sessions/${encodeURIComponent(sid)}/requirements?min_confidence=${encodeURIComponent($('#min-conf').value || 0)}`);
    last.meeting = data; renderMeeting(data); exportLinks(sid);
  } catch (e) { $('#meeting-summary').textContent = ''; showError(e.status === 409 ? t('no_audio') : e.message); }
}

async function loadSessions() {
  const select = $('#session'); select.replaceChildren();
  try {
    const data = await request('/audio/api/sessions?limit=100');
    for (const s of data.sessions) { const o = el('option', `${s.title} · ${new Date(s.started_at * 1000).toLocaleString(lang)}`); o.value = s.id; select.append(o); }
    if (!data.sessions.length) { $('#meeting-summary').textContent = t('no_sessions'); return; }
    const wanted = new URLSearchParams(location.search).get('session'); if (wanted) select.value = wanted;
    await loadMeeting();
  } catch (e) { showError(e.status === 409 ? t('no_audio') : e.message); }
}

function renderProcedure(d) {
  const root = $('#procedure'); root.replaceChildren();
  root.append(el('p', d.verify, 'muted'));
  root.append(el('h2', t('steps')));
  const ol = el('ol', '', 'steps');
  for (const s of d.steps) {
    const li = el('li', s.title);
    const shot = s.screenshot ? `${t('shot')}: ${s.screenshot.ref || s.screenshot.ts}` : t('no_shot');
    li.append(el('div', `${s.t_start}s · ${t('evidence')}: ${s.evidence.map((e) => `${e.type}@${e.t}s`).join(', ')} · ${shot}`, 'meta'));
    if (s.inputs.length) li.append(el('div', `${t('inputs')}: ${s.inputs.join(', ')}`, 'meta'));
    ol.append(li);
  }
  root.append(ol);
  for (const [key, list, fmt] of [['inputs', d.inputs, (i) => `${i.name} (${i.source}): ${i.masked ? '[' + t('masked') + ']' : i.example}`], ['outputs', d.outputs, (o) => o.description + (o.value ? ': ' + o.value : '')]]) {
    root.append(el('h2', t(key)));
    const ul = el('ul', '', 'unknowns'); list.forEach((i) => ul.append(el('li', fmt(i)))); if (!list.length) ul.append(el('li', t('none'))); root.append(ul);
  }
  root.append(el('h2', t('unknowns')));
  const ul = el('ul', '', 'unknowns'); d.unknowns.forEach((u) => ul.append(el('li', u.message))); root.append(ul);
}

async function loadProcedure() {
  showError('');
  try {
    const body = { start: $('#p-start').value.trim() || null, end: $('#p-end').value.trim() || null, locale: lang };
    const d = await request('/activity/api/procedure/draft', { method: 'POST', body: JSON.stringify(body) });
    last.procedure = d; renderProcedure(d);
    const md = await request('/activity/api/procedure/draft', { method: 'POST', body: JSON.stringify({ ...body, format: 'md' }) });
    $('#p-export').href = 'data:text/markdown;charset=utf-8,' + encodeURIComponent(md.text);
  } catch (e) { showError(e.status === 409 ? t('no_activity') : e.message); }
}

function tab(name) {
  for (const n of ['meeting', 'procedure']) { $(`#tab-${n}`).setAttribute('aria-selected', String(n === name)); $(`#panel-${n}`).hidden = n !== name; }
}
$('#tab-meeting').onclick = () => tab('meeting');
$('#tab-procedure').onclick = () => tab('procedure');
$('#load-meeting').onclick = loadMeeting;
$('#session').onchange = loadMeeting;
$('#load-procedure').onclick = loadProcedure;
$('#lang').onchange = (e) => { lang = e.target.value; try { localStorage.setItem('talos-lang', lang); } catch { /* private mode */ } applyLang(); if (last.meeting) exportLinks(last.meeting.session_id); };
applyLang();
await loadSessions();
