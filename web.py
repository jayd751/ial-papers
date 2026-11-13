#!/usr/bin/env python3
"""web.py — click-to-download dashboard for ial-papers.

Run:  python3 web.py   then open http://localhost:8000
"""

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ial
from downloader import download_many, save_manifest, _paper_rel

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "papers")
SETTINGS_FILE = os.path.join(HERE, "settings.json")
FORCE_FILE = os.path.join(HERE, "force.json")
PORT = 8000
YEAR_MIN, YEAR_MAX = 2003, 2025

JOBS = {}
_JOB_SEQ = 0
_UNIT_CACHE = {}

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IAL Papers — Downloader</title>
<style>
  :root {
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2330; --line:#30363d;
    --fg:#e6edf3; --mut:#8b949e; --gold:#d4b26a; --gold-l:#e8c56a;
    --green:#3fb950; --red:#f85149; --blue:#58a6ff;
  }
  :root[data-theme="light"] {
    --bg:#f6f3ec; --panel:#ffffff; --panel2:#f1ede3; --line:#dcd5c6;
    --fg:#1c2230; --mut:#6b7280; --gold:#b08a3e; --gold-l:#8a6826;
    --green:#1a7f37; --red:#cf222e; --blue:#0969da;
  }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif;
         background:var(--bg); color:var(--fg); }
  header { border-bottom:1px solid var(--line); padding:1rem 1.4rem .6rem; }
  .headrow { display:flex; justify-content:space-between; align-items:center; }
  header h1 { margin:0; font-size:1.15rem; }
  header h1 span { color:var(--gold-l); }
  #theme { background:var(--panel2); color:var(--fg); border:1px solid var(--line);
       padding:.45rem .8rem; border-radius:8px; cursor:pointer; font:inherit; font-size:.85rem; }
  nav { display:flex; gap:.4rem; margin-top:.7rem; }
  nav button { background:var(--panel2); color:var(--mut); border:1px solid var(--line);
       padding:.5rem 1rem; font:inherit; border-radius:8px 8px 0 0; cursor:pointer; }
  nav button.active { background:var(--panel); color:var(--gold-l); border-bottom-color:var(--panel); }
  main { max-width:1100px; margin:1.2rem auto; padding:0 1.2rem; }
  .tab { display:none; } .tab.active { display:block; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:1.1rem; }
  @media (max-width:860px) { .grid2 { grid-template-columns:1fr; } }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:1.1rem; }
  h2 { margin:0 0 .9rem; font-size:.8rem; text-transform:uppercase; letter-spacing:.12em; color:var(--gold-l); }
  label.lbl { display:block; margin:1rem 0 .4rem; font-size:.85rem; color:var(--mut); }
  select, input[type=text] { width:100%; padding:.55rem .6rem; font:inherit;
       background:var(--panel2); color:var(--fg); border:1px solid var(--line); border-radius:7px; }
  .checks { display:flex; flex-wrap:wrap; gap:.6rem; }
  .checks label { display:flex; align-items:center; gap:.4rem; font-size:.9rem; cursor:pointer; }
  .checks input, .files input, .setuplist input { accent-color:var(--gold); }
  .years { display:grid; grid-template-columns:1fr 1fr; gap:1rem; }
  .years .yr { background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:.6rem .8rem; }
  .years .yr b { display:block; font-size:1.5rem; color:var(--gold-l); }
  .years .yr span { font-size:.72rem; color:var(--mut); text-transform:uppercase; letter-spacing:.05em; }
  input[type=range] { width:100%; accent-color:var(--gold); margin-top:.4rem; }
  .yrrange { text-align:center; margin-top:.6rem; color:var(--mut); font-size:.9rem; }
  .unitbox { max-height:220px; overflow:auto; border:1px solid var(--line); border-radius:8px;
             background:var(--panel2); padding:.5rem .7rem; }
  .unitbox label { display:flex; gap:.5rem; padding:.2rem 0; font-size:.88rem; cursor:pointer; align-items:center; }
  .unitbox .u { color:var(--mut); font-size:.78rem; }
  .unit-actions { margin-top:.5rem; font-size:.8rem; color:var(--blue); cursor:pointer; user-select:none; }
  .unit-actions span { margin-right:1rem; }
  button.cta { margin-top:1.3rem; width:100%; padding:.75rem; font:inherit; font-weight:600;
       background:var(--gold); color:#1a140a; border:0; border-radius:8px; cursor:pointer; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  button.danger { background:#3a1515; color:#ffb3ad; border:1px solid #6b2b2b; }
  button.small { width:auto; padding:.5rem 1rem; margin:0; }
  .bar { height:10px; background:var(--panel2); border-radius:999px; overflow:hidden; margin-top:1.1rem; display:none; }
  .bar > div { height:100%; width:0%; background:linear-gradient(90deg,var(--gold),var(--gold-l)); transition:width .25s; }
  .status { margin-top:.6rem; font-size:.9rem; color:var(--mut); min-height:1.4em; }
  .status.ok { color:var(--green); } .status.err { color:var(--red); }
  .fail { margin-top:.8rem; font-size:.8rem; color:var(--red); } .fail div { padding:.15rem 0; }
  .hint { color:var(--mut); font-size:.8rem; }
  .ondisk .row { display:flex; justify-content:space-between; padding:.35rem 0; border-bottom:1px solid var(--line); font-size:.9rem; }
  .ondisk .row:last-child { border-bottom:0; }
  .ondisk .row span:last-child { color:var(--mut); }

  .libtoolbar { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap; margin-bottom:.8rem; }
  .libtoolbar select { width:auto; min-width:140px; }
  .files { max-height:460px; overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--panel2); }
  .files .frow { display:flex; gap:.5rem; align-items:center; padding:.3rem .6rem; border-bottom:1px solid var(--line); font-size:.82rem; }
  .files .frow:last-child { border-bottom:0; }
  .files .frow label { display:flex; gap:.5rem; align-items:center; cursor:pointer; width:100%; }
  .files .frow input { accent-color:var(--green); }
  .files .frow .sz { color:var(--mut); margin-left:auto; white-space:nowrap; }
  .files .frow .grp { color:var(--mut); font-size:.75rem; }
  .danger-zone { display:flex; gap:.6rem; align-items:center; margin-top:1rem; flex-wrap:wrap; }
  .danger-zone select { width:auto; min-width:150px; }

  .setuplist { max-height:420px; overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--panel2); }
  .subj { border-bottom:1px solid var(--line); }
  .subj:last-child { border-bottom:0; }
  .subj > label { display:flex; gap:.5rem; padding:.5rem .7rem; cursor:pointer; font-weight:600; align-items:center; }
  .subj .subunits { padding:0 .7rem .6rem 2rem; display:none; }
  .subj.open .subunits { display:block; }
  .subj .subunits label { display:flex; gap:.5rem; padding:.15rem 0; font-size:.85rem; cursor:pointer; }
  .subj .count { color:var(--mut); font-weight:400; font-size:.8rem; }
  .toggle { display:flex; align-items:center; gap:.6rem; margin:1rem 0; }
  .toggle input { width:18px; height:18px; accent-color:var(--gold); }
  a { color:var(--blue); }
</style>
</head>
<body>
<header>
  <div class="headrow">
    <h1>IAL Papers <span>· Downloader</span></h1>
    <button id="theme">☀ Light</button>
  </div>
  <nav>
    <button data-tab="download" class="active">Download</button>
    <button data-tab="library">Library</button>
    <button data-tab="setup">Setup</button>
  </nav>
</header>
<main>

  <!-- DOWNLOAD TAB -->
  <section id="tab-download" class="tab active">
    <div class="grid2">
      <div class="card">
        <h2>Download papers</h2>
        <label class="lbl">Subject</label>
        <select id="subject"><option value="">Loading…</option></select>

        <label class="lbl">Units</label>
        <div class="unitbox" id="units"><div class="hint">Pick a subject first.</div></div>
        <div class="unit-actions"><span id="uall">✓ Select all</span><span id="unone">✗ Clear</span></div>
        <p class="hint" style="margin:.3rem 0 0">No unit selected = all units for that subject.</p>

        <label class="lbl">Years</label>
        <div class="years">
          <div class="yr"><b id="y0v">2022</b><span>start year</span><input type="range" id="y0" min="YEAR_MIN" max="YEAR_MAX" value="2022" step="1"></div>
          <div class="yr"><b id="y1v">2025</b><span>end year</span><input type="range" id="y1" min="YEAR_MIN" max="YEAR_MAX" value="2025" step="1"></div>
        </div>
        <div class="yrrange" id="yrlabel">2022 – 2025</div>

        <label class="lbl">Sessions</label>
        <div class="checks" id="sessions">
          <label><input type="checkbox" value="Jan" checked> Jan</label>
          <label><input type="checkbox" value="Jun" checked> Jun</label>
          <label><input type="checkbox" value="Oct" checked> Oct</label>
        </div>

        <label class="lbl">Document types</label>
        <div class="checks" id="types">
          <label><input type="checkbox" value="qp" checked> Question paper</label>
          <label><input type="checkbox" value="ms" checked> Mark scheme</label>
          <label><input type="checkbox" value="er"> Examiner report</label>
          <label><input type="checkbox" value="gb"> Grade boundaries</label>
        </div>
        <p class="hint" style="margin:.3rem 0 0">Grade boundaries are one PDF per session covering every subject.</p>

        <label class="lbl">Regional / timezone variants</label>
        <div class="checks"><label><input type="checkbox" id="incl-regional"> Include regional papers (codes ending A / R)</label></div>

        <button class="cta" id="go" disabled>Loading subjects…</button>
        <div class="bar" id="bar"><div id="barfill"></div></div>
        <div class="status" id="status"></div>
        <div class="fail" id="failures"></div>
      </div>

      <div class="card">
        <h2>On disk</h2>
        <p class="hint">Downloads land in <code>ial-papers/papers/</code>.</p>
        <div class="ondisk" id="ondisk">Loading…</div>
        <h2 style="margin-top:1.4rem">After downloading</h2>
        <p class="hint">Open any PDF and it's a real, official paper. Use the <b>Library</b> tab to review, sort, or delete what you've downloaded.</p>
      </div>
    </div>
  </section>

  <!-- LIBRARY TAB -->
  <section id="tab-library" class="tab">
    <div class="card">
      <h2>Downloaded papers</h2>
      <p class="hint">Papers on disk are automatically skipped on future downloads. Untick a paper to re-download it.</p>
      <div class="libtoolbar">
        <select id="libfilter"><option value="">All subjects</option></select>
        <select id="libsort">
          <option value="subject">Sort: subject</option>
          <option value="unit">Sort: unit</option>
          <option value="session">Sort: session (newest)</option>
          <option value="file">Sort: paper name</option>
        </select>
        <span class="hint" id="libcount"></span>
      </div>
      <div class="files" id="files">Loading…</div>

      <div class="danger-zone">
        <select id="delsubject"><option value="">— delete by subject —</option></select>
        <button class="danger small" id="del-subject">Delete subject</button>
        <button class="danger small" id="del-all">Delete everything</button>
      </div>
      <div class="status" id="libstatus"></div>
    </div>
  </section>

  <!-- SETUP TAB -->
  <section id="tab-setup" class="tab">
    <div class="card" style="max-width:720px">
      <h2>Your subjects & units</h2>
      <p class="hint">Tick the subjects you're taking, then tick the units for each. Save, and the Download tab will be confined to just those.</p>
      <div class="toggle">
        <input type="checkbox" id="confined">
        <label for="confined">Confine downloads to my setup (untick to browse everything)</label>
      </div>
      <div class="setuplist" id="setuplist">Loading subjects…</div>
      <button class="cta" id="savesetup">Save setup</button>
      <div class="status" id="setupstatus"></div>
    </div>
  </section>

</main>

<script>
const $ = (id) => document.getElementById(id);
let currentJob = null, pollTimer = null;
let ALL_SUBJECTS = {}, SETTINGS = { confined:false, subjects:{} }, FORCE = new Set();
let FILES = [];

async function json(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

// ---- theme ----
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  $('theme').textContent = t === 'light' ? '🌙 Dark' : '☀ Light';
  try { localStorage.setItem('ial-theme', t); } catch (e) {}
}
$('theme').addEventListener('click', () => setTheme(
  document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light'));

// ---- tabs ----
document.querySelectorAll('nav button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  $('tab-' + b.dataset.tab).classList.add('active');
}));

// ---- subjects / units ----
async function loadSubjects() {
  ALL_SUBJECTS = await json('/api/subjects');
  renderSubjectSelect();
  renderSetupList();
  $('go').disabled = false; $('go').textContent = 'Download';
}

function renderSubjectSelect() {
  const sel = $('subject');
  const confined = SETTINGS.confined && Object.keys(SETTINGS.subjects).length;
  const names = confined ? Object.keys(SETTINGS.subjects).filter(s => SETTINGS.subjects[s] !== null) : Object.keys(ALL_SUBJECTS);
  sel.innerHTML = '<option value="">— pick a subject —</option>';
  names.sort().forEach(name => {
    const o = document.createElement('option');
    o.value = name;
    o.textContent = `${name} (${ALL_SUBJECTS[name] || '?'} docs)`;
    sel.appendChild(o);
  });
}

async function loadUnits(subject) {
  const box = $('units');
  if (!subject) { box.innerHTML = '<div class="hint">Pick a subject first.</div>'; return; }
  box.innerHTML = '<div class="hint">Loading…</div>';
  const units = await json('/api/units?subject=' + encodeURIComponent(subject));
  const codes = Object.keys(units).sort();
  if (!codes.length) { box.innerHTML = '<div class="hint">No units found.</div>'; return; }
  const allowed = SETTINGS.confined ? (SETTINGS.subjects[subject] || []) : null;
  const visible = allowed && allowed.length ? codes.filter(c => allowed.includes(c)) : codes;
  const pretty = (l) => { const m = /^U(\\d)$/.exec(l||''); return m ? `Unit ${m[1]}` : (l||'?'); };
  const row = (c) => { const u = units[c];
    return `<label><input type="checkbox" value="${c}"><span>${c} · ${pretty(u.label)}</span><span class="u">${u.qp}qp/${u.ms}ms</span></label>`; };
  const nw = visible.filter(c => units[c].spec === 'new');
  const old = visible.filter(c => units[c].spec !== 'new');
  box.innerHTML =
    (nw.length ? `<div class="hint" style="margin:.2rem 0 .3rem">New syllabus (2018+)</div>` + nw.map(row).join('') : '') +
    (old.length ? `<div class="hint" style="margin:.6rem 0 .3rem">Old syllabus (legacy)</div>` + old.map(row).join('') : '') +
    (!visible.length ? '<div class="hint">No units for this subject.</div>' : '');
}

function selectedUnits() { return [...document.querySelectorAll('#units input:checked')].map(i => i.value); }

// ---- download job ----
function poll() {
  if (!currentJob) return;
  json('/api/status?id=' + currentJob).then((s) => {
    const bar = $('bar'), fill = $('barfill'), st = $('status');
    bar.style.display = 'block';
    if (s.state === 'querying') { st.textContent = 'Querying Pearson index…'; st.className='status'; fill.style.width='4%'; }
    else if (s.state === 'downloading') {
      const pct = s.total ? Math.round(100*s.done/s.total) : 0;
      fill.style.width = pct+'%';
      st.textContent = `Downloading… ${s.done}/${s.total} (${s.downloaded} ok, ${s.failed} failed)`;
      st.className='status';
    }
    if (s.state === 'done') {
      clearInterval(pollTimer); currentJob=null; fill.style.width='100%'; st.className='status ok';
      st.textContent = `Done: ${s.downloaded} downloaded, ${s.skipped} skipped, ${s.failed} failed → ${s.out}`;
      $('go').disabled=false; $('go').textContent='Download';
      $('failures').innerHTML = (s.failures||[]).slice(0,12).map(f=>`<div>⚠ ${f.path} — ${f.reason}</div>`).join('');
      refreshAll();
    } else if (s.state === 'error') {
      clearInterval(pollTimer); currentJob=null; st.className='status err'; st.textContent=s.message;
      $('go').disabled=false; $('go').textContent='Download';
    }
  }).catch(()=>{});
}

// ---- on disk / library ----
async function refreshAll() { await Promise.all([loadOnDisk(), loadFiles()]); }

async function loadOnDisk() {
  const d = await json('/api/ondisk');
  const box = $('ondisk');
  box.innerHTML = (!d.length) ? '<p class="hint">Nothing yet — download something!</p>'
    : d.map(s=>`<div class="row"><span>${s.subject}</span><span>${s.pdfs} papers · ${s.size_mb} MB</span></div>`).join('');
}

async function loadFiles() {
  FILES = await json('/api/files');
  FORCE = new Set(await json('/api/force'));
  renderFiles();
  // populate filter + delete-by-subject selects
  const subs = [...new Set(FILES.map(f=>f.subject))].sort();
  const opts = subs.map(s=>`<option value="${s}">${s}</option>`).join('');
  $('libfilter').innerHTML = '<option value="">All subjects</option>' + opts;
  $('delsubject').innerHTML = '<option value="">— delete by subject —</option>' + opts;
}

function renderFiles() {
  const subj = $('libfilter').value, sort = $('libsort').value;
  let list = FILES.filter(f => !subj || f.subject === subj);
  if (sort === 'unit') list.sort((a,b)=> (a.unit||'').localeCompare(b.unit||'') || a.session.localeCompare(b.session) || a.filename.localeCompare(b.filename));
  else if (sort === 'session') list.sort((a,b)=> b.session.localeCompare(a.session) || (a.unit||'').localeCompare(b.unit||''));
  else if (sort === 'file') list.sort((a,b)=> a.filename.localeCompare(b.filename));
  else list.sort((a,b)=> a.subject.localeCompare(b.subject) || (a.unit||'').localeCompare(b.unit||'') || a.session.localeCompare(b.session));
  $('libcount').textContent = `${list.length} file(s)`;
  const box = $('files');
  if (!list.length) { box.innerHTML = '<p class="hint" style="padding:.6rem">No files match.</p>'; return; }
  box.innerHTML = list.map(f => {
    const checked = !FORCE.has(f.path);  // checked = have it = excluded from re-download
    return `<div class="frow"><label><input type="checkbox" class="fchk" data-path="${f.path}" title="Untick to re-download" ${checked?'checked':''}>
      <span>${f.filename}</span><span class="grp">${f.unit||''} · ${f.session}</span>
      <span class="sz">${f.size_mb} MB</span></label></div>`;
  }).join('');
  document.querySelectorAll('#files .fchk').forEach(cb => cb.addEventListener('change', async (e) => {
    await json('/api/force', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ path: e.target.dataset.path, excluded: e.target.checked }) });
    FORCE = new Set(await json('/api/force'));
  }));
}

// ---- setup ----
function renderSetupList() {
  const box = $('setuplist');
  const names = Object.keys(ALL_SUBJECTS).sort();
  box.innerHTML = names.map(s => `
    <div class="subj ${SETTINGS.subjects[s] ? 'open' : ''}" data-subj="${s}">
      <label><input type="checkbox" class="s-on" ${SETTINGS.subjects[s] ? 'checked' : ''}> ${s}
        <span class="count">${ALL_SUBJECTS[s]||'?'} docs</span></label>
      <div class="subunits" id="su-${s}"><div class="hint">Loading units…</div></div>
    </div>`).join('');
  document.querySelectorAll('#setuplist .s-on').forEach(cb => cb.addEventListener('change', async (e) => {
    const s = cb.closest('.subj').dataset.subj;
    if (cb.checked) { SETTINGS.subjects[s] = []; cb.closest('.subj').classList.add('open'); loadSetupUnits(s); }
    else { delete SETTINGS.subjects[s]; cb.closest('.subj').classList.remove('open'); }
  }));
}

async function loadSetupUnits(s) {
  const host = $('su-' + s);
  try {
    const units = await json('/api/units?subject=' + encodeURIComponent(s));
    const codes = Object.keys(units).sort();
    const pretty = (l) => { const m=/^U(\\d)$/.exec(l||''); return m?`Unit ${m[1]}`:(l||'?'); };
    host.innerHTML = '<label><input type="checkbox" class="u-all"> All units</label>' + codes.map(c => {
      const u = units[c];
      return `<label><input type="checkbox" class="u-one" value="${c}" ${(SETTINGS.subjects[s]||[]).includes(c)?'checked':''}>
        ${c} · ${pretty(u.label)} <span class="count">${u.qp}qp</span></label>`;
    }).join('');
    const allCb = host.querySelector('.u-all');
    const oneCbs = [...host.querySelectorAll('.u-one')];
    allCb.checked = (SETTINGS.subjects[s] || []).length === 0;
    const sync = () => {
      const picked = oneCbs.filter(c=>c.checked).map(c=>c.value);
      SETTINGS.subjects[s] = picked;
      allCb.checked = picked.length === 0;
    };
    allCb.addEventListener('change', () => { if (allCb.checked) { SETTINGS.subjects[s]=[]; oneCbs.forEach(c=>c.checked=false); } });
    oneCbs.forEach(c=>c.addEventListener('change', sync));
  } catch (e) { host.innerHTML = '<div class="hint">Could not load units.</div>'; }
}

async function loadSettings() {
  SETTINGS = await json('/api/settings');
  $('confined').checked = !!SETTINGS.confined;
  if (Object.keys(ALL_SUBJECTS).length) { renderSubjectSelect(); renderSetupList(); }
}

$('confined').addEventListener('change', () => { SETTINGS.confined = $('confined').checked; renderSubjectSelect(); });

// ---- events ----
$('subject').addEventListener('change', e => loadUnits(e.target.value));
$('uall').addEventListener('click', () => document.querySelectorAll('#units input').forEach(i=>i.checked=true));
$('unone').addEventListener('click', () => document.querySelectorAll('#units input').forEach(i=>i.checked=false));
$('libfilter').addEventListener('change', renderFiles);
$('libsort').addEventListener('change', renderFiles);

$('go').addEventListener('click', async () => {
  const body = {
    subject: $('subject').value,
    units: selectedUnits(),
    year_start: +$('y0').value, year_end: +$('y1').value,
    sessions: [...document.querySelectorAll('#sessions input:checked')].map(i=>i.value),
    types: [...document.querySelectorAll('#types input:checked')].map(i=>i.value),
    include_regional: $('incl-regional').checked,
  };
  if (!body.subject) { $('status').className='status err'; $('status').textContent='Pick a subject first.'; return; }
  if (!body.types.length) { $('status').className='status err'; $('status').textContent='Pick at least one document type.'; return; }
  if (body.year_start > body.year_end) { const t=body.year_start; body.year_start=body.year_end; body.year_end=t; }
  $('go').disabled=true; $('go').textContent='Working…';
  $('failures').innerHTML=''; $('status').textContent='Starting…'; $('status').className='status';
  const r = await json('/api/download', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
  currentJob = r.id; poll(); pollTimer = setInterval(poll, 600);
});

async function delPaths(paths) {
  const r = await json('/api/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ mode:'selected', paths }) });
  $('libstatus').className='status ok'; $('libstatus').textContent = `Deleted ${r.deleted} file(s).`;
  refreshAll();
}
$('del-subject').addEventListener('click', async () => {
  const s = $('delsubject').value; if (!s) { $('libstatus').textContent='Pick a subject first.'; return; }
  const paths = FILES.filter(f=>f.subject===s).map(f=>f.path);
  if (!confirm(`Delete all ${paths.length} file(s) for ${s}?`)) return;
  const r = await json('/api/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ mode:'subject', subject:s }) });
  $('libstatus').className='status ok'; $('libstatus').textContent=`Deleted ${r.deleted} file(s).`; refreshAll();
});
$('del-all').addEventListener('click', async () => {
  if (!confirm(`Delete ALL ${FILES.length} downloaded file(s)?`)) return;
  const r = await json('/api/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ mode:'all' }) });
  $('libstatus').className='status ok'; $('libstatus').textContent=`Deleted ${r.deleted} file(s).`; refreshAll();
});

$('savesetup').addEventListener('click', async () => {
  await json('/api/settings', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ confined: $('confined').checked, subjects: SETTINGS.subjects }) });
  $('setupstatus').className='status ok'; $('setupstatus').textContent='Saved.';
  renderSubjectSelect();
});

// year sliders
function syncYearLabels() {
  let a=+$('y0').value, b=+$('y1').value;
  $('y0').max=b; $('y1').min=a;
  $('y0v').textContent=a; $('y1v').textContent=b; $('yrlabel').textContent=`${a} – ${b}`;
}
$('y0').addEventListener('input', () => { if (+$('y0').value > +$('y1').value) $('y0').value=$('y1').value; syncYearLabels(); });
$('y1').addEventListener('input', () => { if (+$('y1').value < +$('y0').value) $('y1').value=$('y0').value; syncYearLabels(); });

// boot
(async () => {
  let savedTheme = 'dark';
  try { savedTheme = localStorage.getItem('ial-theme') || 'dark'; } catch (e) {}
  setTheme(savedTheme);
  await loadSubjects();
  await loadSettings();
  await refreshAll();
  syncYearLabels();
})();
</script>
</body>
</html>
"""


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def _get_settings():
    s = _load_json(SETTINGS_FILE, {"confined": False, "subjects": {}})
    s.setdefault("confined", False)
    s.setdefault("subjects", {})
    return s


def _get_force():
    return set(_load_json(FORCE_FILE, []))


def _save_force(s):
    _save_json(FORCE_FILE, sorted(s))


def _send_json(handler, obj, code=200):
    data = json.dumps(obj).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _doc_type_variants(types):
    out = []
    for t in types:
        out.extend(ial.doc_type_variants(t) or [t])
    return out


def _scan_ondisk():
    subjects = []
    if not os.path.isdir(OUT_ROOT):
        return []
    for name in sorted(os.listdir(OUT_ROOT)):
        d = os.path.join(OUT_ROOT, name)
        if os.path.isdir(d):
            n = size = 0
            for dirpath, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(".pdf"):
                        n += 1
                        try:
                            size += os.path.getsize(os.path.join(dirpath, f))
                        except OSError:
                            pass
            if n:
                subjects.append({"subject": name, "pdfs": n,
                                 "size_mb": round(size / 1e6, 1)})
    return subjects


def _list_files():
    out = []
    if not os.path.isdir(OUT_ROOT):
        return []
    for dirpath, _, filenames in os.walk(OUT_ROOT):
        for fn in filenames:
            if fn.lower().endswith(".pdf"):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, OUT_ROOT).replace(os.sep, "/")
                parts = rel.split("/")
                subject = parts[0] if parts else ""
                if subject == "Grade-boundaries":
                    unit, session = "", (parts[1] if len(parts) > 1 else "")
                else:
                    unit = parts[1] if len(parts) > 1 else ""
                    session = parts[2] if len(parts) > 2 else ""
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                out.append({"path": rel, "size_mb": round(size / 1e6, 2),
                            "subject": subject, "unit": unit, "session": session,
                            "filename": fn})
    out.sort(key=lambda x: (x["subject"], x["unit"], x["session"], x["filename"]))
    return out


def _safe_delete(rel):
    full = os.path.realpath(os.path.join(OUT_ROOT, rel))
    root = os.path.realpath(OUT_ROOT)
    if not full.startswith(root + os.sep):
        return False
    try:
        os.remove(full)
        return True
    except OSError:
        return False


def _prune_empty():
    for dirpath, dirnames, filenames in os.walk(OUT_ROOT, topdown=False):
        if os.path.realpath(dirpath) == os.path.realpath(OUT_ROOT):
            continue
        if not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass


def _years_range(start, end):
    try:
        a, b = int(start), int(end)
        if a > b:
            a, b = b, a
        return list(range(a, b + 1))
    except (TypeError, ValueError):
        return None


def _run_job(job_id, body):
    job = JOBS[job_id]
    try:
        subject = body.get("subject") or ""
        units = [u for u in (body.get("units") or []) if u]
        years = _years_range(body.get("year_start"), body.get("year_end"))
        sessions = body.get("sessions") or None
        types = body.get("types") or ["qp", "ms"]

        job["state"] = "querying"

        gb_wanted = "gb" in types
        paper_types = [t for t in types if t != "gb"]

        papers = []
        if paper_types:
            doc_types = _doc_type_variants(paper_types)
            fetched = ial.fetch_all(doc_types=doc_types,
                                    subjects=[subject] if subject else None)
            papers.extend(ial.filter_papers(fetched, unit=units or None,
                                            years=years, sessions=sessions,
                                            types=paper_types))
        if gb_wanted:
            gb = ial.fetch_all(doc_types=["Grade-boundaries"])
            papers.extend(ial.filter_papers(gb, years=years, sessions=sessions,
                                            types=["gb"]))

        if not body.get("include_regional"):
            papers = [p for p in papers if not p.variant]

        seen = set()
        uniq = []
        for p in papers:
            if p.url not in seen:
                seen.add(p.url)
                uniq.append(p)
        papers = uniq

        job["total"] = len(papers)
        if not papers:
            job["state"] = "done"
            job.update(downloaded=0, skipped=0, failed=0,
                       out=OUT_ROOT, failures=[])
            return

        force_keys = _get_force()
        job_force = {_paper_rel(p) for p in papers} & force_keys

        def on_progress(done, total, summary, failures):
            job.update(state="downloading", done=done, total=total,
                       downloaded=summary["downloaded"],
                       skipped=summary["skipped"],
                       failed=summary["failed"],
                       failures=[{"path": p, "reason": r} for p, r in failures])

        summary, failures = download_many(papers, OUT_ROOT, workers=6,
                                          on_progress=on_progress,
                                          force_keys=force_keys)
        save_manifest(papers, OUT_ROOT)

        # Clear force flags for papers we just (re-)downloaded successfully.
        remaining = (force_keys - job_force) | {
            k for k in job_force
            if not os.path.exists(os.path.join(OUT_ROOT, k.replace("/", os.sep)))
        }
        _save_force(remaining)

        job.update(state="done", done=summary["total"], total=summary["total"],
                   downloaded=summary["downloaded"], skipped=summary["skipped"],
                   failed=summary["failed"], out=OUT_ROOT,
                   failures=[{"path": p, "reason": r} for p, r in failures])
    except Exception as exc:  # noqa: BLE001
        job.update(state="error", message=f"{type(exc).__name__}: {exc}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            data = HTML.replace("YEAR_MIN", str(YEAR_MIN)).replace(
                "YEAR_MAX", str(YEAR_MAX)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/subjects":
            _send_json(self, ial.subjects_with_counts())
            return
        if path == "/api/units":
            subject = qs.get("subject", [""])[0]
            if not subject:
                _send_json(self, {}, 400)
                return
            if subject not in _UNIT_CACHE:
                papers = ial.fetch_all(
                    doc_types=_doc_type_variants(["qp", "ms", "er"]),
                    subjects=[subject])
                units = ial.list_units(papers)
                _UNIT_CACHE[subject] = {
                    k: {"label": v["label"], "qp": v["qp"], "ms": v["ms"],
                        "er": v["er"],
                        "spec": "new" if ial.is_new_spec(k) else "old"}
                    for k, v in units.items()}
            _send_json(self, _UNIT_CACHE[subject])
            return
        if path == "/api/ondisk":
            _send_json(self, _scan_ondisk())
            return
        if path == "/api/files":
            _send_json(self, _list_files())
            return
        if path == "/api/settings":
            _send_json(self, _get_settings())
            return
        if path == "/api/force":
            _send_json(self, sorted(_get_force()))
            return
        if path == "/api/status":
            job_id = qs.get("id", [""])[0]
            job = JOBS.get(job_id)
            if not job:
                _send_json(self, {"state": "error", "message": "unknown job"}, 404)
                return
            _send_json(self, job)
            return
        _send_json(self, {"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {}

        if self.path == "/api/download":
            global _JOB_SEQ
            _JOB_SEQ += 1
            job_id = str(_JOB_SEQ)
            JOBS[job_id] = {"id": job_id, "state": "queued", "done": 0,
                            "total": 0, "downloaded": 0, "skipped": 0,
                            "failed": 0, "failures": [], "out": OUT_ROOT}
            threading.Thread(target=_run_job, args=(job_id, body), daemon=True).start()
            _send_json(self, {"id": job_id})
            return
        if self.path == "/api/delete":
            mode = body.get("mode", "selected")
            if mode == "all":
                paths = [f["path"] for f in _list_files()]
            elif mode == "subject":
                subj = body.get("subject")
                paths = [f["path"] for f in _list_files() if f["subject"] == subj]
            else:
                paths = body.get("paths") or []
            deleted = 0
            for rel in paths:
                if _safe_delete(rel):
                    deleted += 1
            _prune_empty()
            _send_json(self, {"deleted": deleted})
            return
        if self.path == "/api/force":
            p = body.get("path")
            s = _get_force()
            if body.get("excluded"):
                s.discard(p)
            elif p:
                s.add(p)
            _save_force(s)
            _send_json(self, {"force": sorted(s)})
            return
        if self.path == "/api/settings":
            s = body
            s.setdefault("confined", False)
            s.setdefault("subjects", {})
            _save_json(SETTINGS_FILE, s)
            _send_json(self, s)
            return
        _send_json(self, {"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"IAL Papers downloader → http://localhost:{PORT}")
    print("Press Ctrl+C to stop.\n")
    try:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(
            f"http://localhost:{PORT}")).start()
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
