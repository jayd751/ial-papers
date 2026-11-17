#!/usr/bin/env python3
"""web.py — the ial-papers app. Papers, specifications, official exam dates, a
study planner and a score log, all running locally.

Run:  python3 web.py   then open http://localhost:8000
"""

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ial
from downloader import download_many, save_manifest, _paper_rel

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "papers")
SETTINGS_FILE = os.path.join(HERE, "settings.json")
FORCE_FILE = os.path.join(HERE, "force.json")
PLAN_FILE = os.path.join(HERE, "plan.json")
SCORES_FILE = os.path.join(HERE, "scores.json")
# Specifications live beside the papers but never in the paper grid. One folder
# per subject, out of the unit/session tree the downloader writes.
SPEC_DIR = "_Specification"
PORT = 8000
YEAR_MIN, YEAR_MAX = 2003, 2026  # YEAR_MAX must track the newest year in the index

SERVER = None  # set in __main__, used by the Close server button
JOBS = {}
_JOB_SEQ = 0
_UNIT_CACHE = {}

# NOTE: this is a normal Python string, so backslashes are escapes. Inside the
# JavaScript below, write \\r\\n and \\d, never \r\n or \d. A single \r becomes a
# real carriage return and takes the whole script tag down with it, which is
# exactly what happened once already.
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
  .headbtns { display:flex; gap:.4rem; }
  #theme, #closeserver { background:var(--panel2); color:var(--fg); border:1px solid var(--line);
       padding:.45rem .8rem; border-radius:8px; cursor:pointer; font:inherit; font-size:.85rem; }
  #closeserver { color:#ffb3ad; border-color:#6b2b2b; }
  #closeserver:hover { background:#3a1515; }
  .stopped { max-width:520px; margin:4rem auto; background:var(--panel); border:1px solid var(--line);
             border-radius:12px; padding:2rem; text-align:center; }
  .stopped h2 { margin-top:0; }
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
  /* ---- study planner ---- */
  .pcal { display: flex; flex-direction: column; gap: 1.4rem; margin-top: .9rem; }
  .pm { display: flex; flex-direction: column; gap: .4rem; }
  .pmhead { display: flex; align-items: baseline; gap: .6rem;
            border-bottom: 1px solid var(--line); padding-bottom: .35rem; }
  .pmhead b { font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; color: var(--gold-l); }
  .pmhead span { font-size: .72rem; color: var(--mut); }
  .pcal-head, .pweek { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: .35rem; }
  .pcal-head { font-size: .66rem; text-transform: uppercase; letter-spacing: .09em; color: var(--mut); }
  .pcal-head span { text-align: center; }
  .pday { background: var(--panel2); border: 1px solid var(--line); border-radius: 8px;
          min-height: 74px; padding: .3rem; font-size: .72rem; color: var(--mut); }
  .pday.out { opacity: .32; }
  .pday.today { border-color: var(--gold-l); }
  .pday.exam { border-color: var(--red); }
  .pday .dnum { display: block; font-size: .7rem; opacity: .75; }
  .pday .examt { display: block; font-size: .6rem; text-transform: uppercase;
                 letter-spacing: .06em; color: var(--red); }
  .ptask { margin-top: .25rem; padding: .28rem .35rem; border-radius: 6px; font-size: .7rem;
           line-height: 1.25; background: var(--panel); border: 1px solid var(--line);
           color: var(--fg); cursor: pointer; }
  .ptask.done { opacity: .45; text-decoration: line-through; }
  .ptask.paper { border-left: 3px solid #58a6ff; }
  .ptask.review { border-left: 3px solid #3fb950; }
  .ptask.mock { border-left: 3px solid #d29922; }
  .ptask b { font-weight: 600; }
  .ptask .sub { display: block; font-size: .64rem; color: var(--mut); }
  .pcal-toolbar { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
  .pstat { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: .5rem; margin: .6rem 0; }
  .pstat div { background: var(--panel2); border: 1px solid var(--line); border-radius: 8px; padding: .5rem .6rem; }
  .pstat b { display: block; font-size: 1.15rem; }
  .pstat span { font-size: .7rem; color: var(--mut); }
  .warn { border-left: 3px solid #d29922; background: var(--panel2); padding: .5rem .7rem;
          border-radius: 6px; font-size: .8rem; margin: .5rem 0; }
  .poolrow { display: flex; gap: .4rem; flex-wrap: wrap; font-size: .75rem; margin-top: .3rem; }
  .poolrow span { background: var(--panel2); border: 1px solid var(--line); border-radius: 999px;
                  padding: .1rem .45rem; color: var(--mut); }
  .pcal-toolbar .btnlink { background: none; border: 0; color: var(--blue); cursor: pointer;
                  font: inherit; font-size: .8rem; padding: 0; }
  /* ---- specifications ---- */
  .specrow { display: flex; gap: .6rem; align-items: center; flex-wrap: wrap; }
  .specrow select { width: auto; min-width: 200px; flex: 1; }
  .speconfile { display: flex; gap: .6rem; align-items: center; font-size: .82rem;
                padding: .35rem 0; border-bottom: 1px solid var(--line); }
  .speconfile:last-child { border-bottom: 0; }
  .speconfile .sz { margin-left: auto; color: var(--mut); }
  /* ---- scores ---- */
  .srow { display: grid; grid-template-columns: 6.2rem 1fr 4.5rem 2rem; gap: .5rem;
          align-items: center; padding: .3rem 0; border-bottom: 1px solid var(--line);
          font-size: .82rem; }
  .srow:last-child { border-bottom: 0; }
  .srow .d { color: var(--mut); font-size: .75rem; }
  .srow .p { font-weight: 600; }
  .srow .x { background: none; border: 0; color: var(--red); cursor: pointer; font-size: .95rem; }
  .schart { width: 100%; height: auto; display: block; overflow: visible; }
  .schart .grid { stroke: var(--line); stroke-width: 1; }
  .schart .axis { fill: var(--mut); font-size: 10px; }
  .schart .line { fill: none; stroke: var(--blue); stroke-width: 2; }
  .schart .avg { fill: none; stroke: var(--gold); stroke-width: 2; stroke-dasharray: 5 4; }
  .schart .dot { fill: var(--blue); }
  .schart .dot:hover { fill: var(--gold-l); }
  .savgs { display: flex; gap: .5rem; flex-wrap: wrap; margin: .6rem 0; }
  .savgs span { background: var(--panel2); border: 1px solid var(--line); border-radius: 999px;
                padding: .15rem .55rem; font-size: .75rem; color: var(--mut); }
  .savgs b { color: var(--fg); }
  .examrow { display: flex; gap: .5rem; align-items: center; padding: .22rem 0;
             border-bottom: 1px solid var(--line); font-size: .8rem; }
  .examrow:last-of-type { border-bottom: 0; }
  .examrow .d { min-width: 8rem; }
  .examrow .u { margin-left: auto; color: var(--mut); }
</style>
</head>
<body>
<header>
  <div class="headrow">
    <h1>IAL Papers <span>· Downloader</span></h1>
    <div class="headbtns">
      <button id="theme">☀ Light</button>
      <button id="closeserver" title="Stop the local server">Close server</button>
    </div>
  </div>
  <nav>
    <button data-tab="download" class="active">Download</button>
    <button data-tab="library">Library</button>
    <button data-tab="setup">Setup</button>
    <button data-tab="planner">Planner</button>
    <button data-tab="scores">Scores</button>
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
          <div class="yr"><b id="y1v">2026</b><span>end year</span><input type="range" id="y1" min="YEAR_MIN" max="YEAR_MAX" value="YEAR_MAX" step="1"></div>
        </div>
        <div class="yrrange" id="yrlabel">2022 – 2026</div>

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

    <div class="card" style="max-width:720px; margin-top:1.1rem">
      <h2>Specifications</h2>
      <p class="hint">The official Pearson specification for a subject. One PDF, kept in its own folder so it never mixes with your papers. No units to pick, because a spec covers the whole subject.</p>
      <div class="specrow">
        <select id="spec-subject"><option value="">— pick a subject —</option></select>
        <button class="cta small" id="spec-get">Get specification</button>
      </div>
      <div class="status" id="spec-status"></div>
      <div id="spec-list"></div>
    </div>
  </section>


  <!-- PLANNER TAB -->
  <section id="tab-planner" class="tab">
    <div class="grid2">
      <div class="card">
        <h2>Plan your past papers</h2>
        <p class="hint">Pick what you are sitting, the gap you need to close and how hard you want to go. The planner works out how many papers that takes and spreads them across the weeks you have left.</p>

        <label class="lbl">Subject</label>
        <select id="p-subject"><option value="">— pick a subject —</option></select>

        <label class="lbl">Units</label>
        <div class="unitbox" id="p-units"><div class="hint">Pick a subject first.</div></div>
        <div class="unit-actions"><span id="p-uall">✓ Select all</span><span id="p-unone">✗ Clear</span></div>

        <label class="lbl">Paper pool</label>
        <div class="checks" id="p-scope">
          <label><input type="radio" name="p-scope" value="new" checked> New spec only</label>
          <label><input type="radio" name="p-scope" value="all"> New + legacy</label>
          <label><input type="radio" name="p-scope" value="count"> Only this many</label>
        </div>
        <div class="row" id="p-countrow" style="display:none">
          <input type="number" id="p-count" value="5" min="1" max="200" style="max-width:90px">
          <span class="hint">papers across all selected units</span>
        </div>

        <label class="lbl">Grades</label>
        <div class="row">
          <select id="p-current" style="max-width:110px"></select>
          <span class="hint">now</span>
          <span class="hint">→</span>
          <select id="p-target" style="max-width:110px"></select>
          <span class="hint">target</span>
        </div>

        <label class="lbl">Dates</label>
        <div class="row">
          <input type="date" id="p-start">
          <span class="hint">start</span>
          <input type="date" id="p-exam">
          <span class="hint">exam day</span>
        </div>

        <label class="lbl">Official exam dates</label>
        <div class="row">
          <select id="p-series" style="max-width:200px"><option value="">loading…</option></select>
          <button class="small" id="p-getdates">Find my dates</button>
        </div>
        <div id="p-examlist" class="hint"></div>

        <label class="lbl">Intensity</label>
        <div class="row">
          <select id="p-intensity" style="max-width:230px">
            <option value="2">Light · 2 sessions a week</option>
            <option value="3">Steady · 3 sessions a week</option>
            <option value="4" selected>Focused · 4 sessions a week</option>
            <option value="5">Hard · 5 sessions a week</option>
            <option value="6">Brutal · 6 sessions a week</option>
            <option value="7">Maximum · 7 sessions a week</option>
          </select>
          <input type="number" id="p-mins" value="75" min="20" max="240" style="max-width:90px">
          <span class="hint">minutes per session</span>
        </div>

        <button class="cta" id="p-build">Build plan</button>
        <div class="status" id="p-status"></div>
      </div>

      <div class="card">
        <h2>What it works out</h2>
        <div id="p-summary" class="hint">Nothing planned yet.</div>
        <h2 style="margin-top:1.3rem">Papers available</h2>
        <div id="p-pool" class="hint">Pick a subject.</div>
      </div>
    </div>

    <div class="card" id="p-calendar-card" style="display:none">
      <div class="pcal-toolbar">
        <h2 style="margin:0">Plan</h2>
        <span class="hint" id="p-progress"></span>
        <span style="flex:1"></span>
        <button class="small" id="p-ics">Download .ics</button>
        <button class="small danger" id="p-clear">Clear plan</button>
      </div>
      <div class="pcal" id="p-calendar"></div>
    </div>
  </section>

  <!-- SCORES TAB -->
  <section id="tab-scores" class="tab">
    <div class="grid2">
      <div class="card">
        <h2>Log a score</h2>
        <p class="hint">Marks from a paper you have done. The chart plots them by the date you sat them, so it shows your progress rather than the year printed on the paper.</p>

        <label class="lbl">Date you did it</label>
        <input type="date" id="s-date">

        <label class="lbl">Subject</label>
        <select id="s-subject"><option value="">— optional —</option></select>

        <label class="lbl">Paper</label>
        <input type="text" id="s-label" list="s-papers" placeholder="e.g. WBI11 · January 2024">
        <datalist id="s-papers"></datalist>

        <label class="lbl">Marks</label>
        <div class="row">
          <input type="number" id="s-raw" min="0" step="0.5" placeholder="mark" style="max-width:110px">
          <span class="hint">out of</span>
          <input type="number" id="s-total" min="1" step="0.5" placeholder="total" style="max-width:110px">
        </div>

        <button class="cta" id="s-add">Log it</button>
        <div class="status" id="s-status"></div>
      </div>

      <div class="card">
        <h2>Improvement</h2>
        <div id="s-chart" class="hint">No scores yet.</div>
        <div class="savgs" id="s-avgs"></div>
        <div id="s-list"></div>
      </div>
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
    o.textContent = `${name.replace(/-/g, ' ')} (${ALL_SUBJECTS[name] ? ALL_SUBJECTS[name] + ' papers' : 'new spec'})`;
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
      <label><input type="checkbox" class="s-on" ${SETTINGS.subjects[s] ? 'checked' : ''}> ${s.replace(/-/g, ' ')}
        <span class="count">${ALL_SUBJECTS[s] || 0} papers</span></label>
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

// ---- specifications ----
// Deliberately its own control. A spec is one PDF per subject, not a paper, so it
// gets one button and its own folder instead of another checkbox in the paper grid.
let SPEC_DATA = null;

function renderSpecSubjectSelect() {
  const sel = $('spec-subject');
  const names = Object.keys(ALL_SUBJECTS || {}).sort();
  sel.innerHTML = '<option value="">— pick a subject —</option>' +
    names.map((n) => '<option value="' + n + '">' + n.replace(/-/g, ' ') + '</option>').join('');
}

async function loadSpec(subject) {
  SPEC_DATA = null;
  $('spec-list').innerHTML = '';
  if (!subject) { $('spec-status').className = 'status'; $('spec-status').textContent = 'Pick a subject.'; return; }
  $('spec-status').className = 'status';
  $('spec-status').textContent = 'Looking for the specification…';
  try {
    SPEC_DATA = await json('/api/spec?subject=' + encodeURIComponent(subject));
  } catch (e) {
    $('spec-status').className = 'status err';
    $('spec-status').textContent = 'Could not reach the local server.';
    return;
  }
  renderSpec();
}

function renderSpec() {
  const d = SPEC_DATA;
  const st = $('spec-status');
  const onDisk = (d && d.on_disk) || [];
  $('spec-list').innerHTML = onDisk.length
    ? onDisk.map((f) =>
      '<div class="speconfile"><span>' + f.filename + '</span>' +
      '<span class="sz">' + f.size_mb + ' MB</span>' +
      '<a href="/api/pdf?path=' + encodeURIComponent(f.path) + '" target="_blank" rel="noopener">Open</a></div>').join('')
    : '';
  if (!d) { st.textContent = ''; return; }
  if (d.error) { st.className = 'status err'; st.textContent = d.error; return; }
  if (!d.chosen) {
    st.className = 'status err';
    st.textContent = 'Pearson lists no specification for that subject.';
    return;
  }
  st.className = 'status';
  const bits = [];
  if (d.chosen.version) bits.push(d.chosen.version);
  if (d.chosen.issue) bits.push('issue ' + d.chosen.issue);
  st.textContent = 'Found ' + d.chosen.title.trim() + (bits.length ? ' (' + bits.join(', ') + ')' : '') +
    (onDisk.length ? ' · already saved' : '');
}

$('spec-subject').addEventListener('change', (e) => loadSpec(e.target.value));
$('spec-get').addEventListener('click', async () => {
  const subject = $('spec-subject').value;
  if (!subject || !SPEC_DATA || !SPEC_DATA.chosen) { $('spec-status').textContent = 'Pick a subject first.'; return; }
  const st = $('spec-status');
  st.className = 'status';
  st.textContent = 'Downloading…';
  $('spec-get').disabled = true;
  try {
    const r = await json('/api/spec', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject, url: SPEC_DATA.chosen.url })
    });
    if (!r.ok) throw new Error(r.error || 'download failed');
    st.className = 'status ok';
    st.textContent = r.skipped ? 'Already saved at ' + r.path : 'Saved to ' + r.path;
    await loadSpec(subject);
  } catch (e) {
    st.className = 'status err';
    st.textContent = String(e.message || e);
  } finally {
    $('spec-get').disabled = false;
  }
});

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
  renderSpecSubjectSelect();
  $('spec-status').textContent = 'Pick a subject to see the specification Pearson lists.';
  await refreshAll();
  syncYearLabels();
  await pInit();
  await sLoad();
})();

// ---- close the local server ----
$('closeserver').addEventListener('click', async () => {
  if (!confirm('Stop the server? Downloads and the planner stop working until you start it again.')) return;
  try {
    await fetch('/api/shutdown', { method: 'POST', headers: { 'X-Ial-Papers': 'shutdown' } });
  } catch (e) { /* the connection drops as the process exits, which is expected */ }

  document.body.innerHTML =
    '<div class="stopped">' +
    '<h2>Server stopped</h2>' +
    '<p class="hint">Python is no longer running. Downloads are saved in <code>papers/</code> and the plan is saved in <code>plan.json</code>.</p>' +
    '<p class="hint">You can close this tab. To start again, double click <b>start-mac.command</b> or run <code>python3 web.py</code>.</p>' +
    '</div>';
});

// ================= study planner =================
// The maths first. It is deliberately free of DOM calls so a node harness can
// eval this block and check plans against real catalogue data.

const GRADES = ['A*', 'A', 'B', 'C', 'D', 'E', 'U'];
const GRADE_RANK = { 'A*': 6, A: 5, B: 4, C: 3, D: 2, E: 1, U: 0 };
// Papers per unit for a grade gap of 0, 1, 2, 3, 4+. Maintenance, then real work.
const PAPERS_PER_GAP = [2, 4, 6, 8, 10];
const SESSION_RANK = { January: 1, February: 2, March: 3, June: 6, Summer: 6, October: 10, November: 11 };
const MAX_PER_WEEK = 7;
const WEEK_OFFSETS = { 1: [1], 2: [1, 4], 3: [1, 3, 5], 4: [1, 2, 4, 5], 5: [1, 2, 3, 4, 5], 6: [1, 2, 3, 4, 5, 6], 7: [1, 2, 3, 4, 5, 6, 7] };

function gradeGap(current, target) {
  return Math.max(0, (GRADE_RANK[target] || 0) - (GRADE_RANK[current] || 0));
}

function papersRequired(gap, unitCount) {
  const perUnit = PAPERS_PER_GAP[Math.min(gap, PAPERS_PER_GAP.length - 1)];
  return perUnit * Math.max(1, unitCount);
}

function sessionRank(session) {
  return SESSION_RANK[session] || 6;
}

function plural(n, one, many) {
  return n + ' ' + (Number(n) === 1 ? one : (many || one + 's'));
}

function paperSortKey(p) {
  return [Number(p.year) || 0, sessionRank(p.session), p.unit || ''];
}

function sortPapersAscending(papers) {
  return papers.slice().sort((a, b) => {
    const ka = paperSortKey(a), kb = paperSortKey(b);
    for (let i = 0; i < 3; i += 1) {
      if (ka[i] < kb[i]) return -1;
      if (ka[i] > kb[i]) return 1;
    }
    return 0;
  });
}

function unitStacks(pool) {
  const byUnit = {};
  for (const p of sortPapersAscending(pool)) (byUnit[p.unit] = byUnit[p.unit] || []).push(p);
  return byUnit;
}

/**
 * k indices across 0..n-1, always including both ends, so the picks cover the
 * whole history instead of hugging the newest papers.
 */
function evenIndices(n, k) {
  if (k >= n) return Array.from({ length: n }, (_, i) => i);
  if (k <= 1) return [n - 1];  // one paper should be the newest one
  const out = [];
  for (let i = 0; i < k; i += 1) out.push(Math.round((i * (n - 1)) / (k - 1)));
  return Array.from(new Set(out));
}

/**
 * Take `wanted` papers out of a pool, spread evenly across each unit's history.
 *
 * Old behaviour took the newest N, so every plan came out as 2025-2026 only and
 * "new spec" and "new + legacy" produced identical plans. This keeps the newest
 * paper of every unit (it becomes the timed mock) and samples the rest backwards,
 * which is the order to actually sit them in.
 */
function selectEvenly(pool, wanted) {
  const stacks = unitStacks(pool);
  const codes = Object.keys(stacks);
  const total = pool.length;
  const take = Math.max(0, Math.min(Math.floor(wanted) || 0, total));
  if (!take) return [];
  if (take >= total) return sortPapersAscending(pool);

  // Quota per unit, at least one each, proportional to how much each unit has.
  const quota = {};
  let assigned = 0;
  for (const c of codes) {
    if (stacks[c].length) { quota[c] = 1; assigned += 1; }
  }
  let left = take - assigned;
  if (left > 0) {
    const order = codes.slice().sort((a, b) => (stacks[b].length - stacks[a].length) || a.localeCompare(b));
    let progress = true;
    while (left > 0 && progress) {
      progress = false;
      for (const c of order) {
        if (left <= 0) break;
        if (quota[c] < stacks[c].length) { quota[c] += 1; left -= 1; progress = true; }
      }
    }
  } else if (left < 0) {
    // Fewer papers than units. Drop the units whose newest paper is oldest, so a
    // tiny plan still covers the units that were examined most recently.
    const order = codes.slice().sort((a, b) => {
      const ka = paperSortKey(stacks[a][stacks[a].length - 1]);
      const kb = paperSortKey(stacks[b][stacks[b].length - 1]);
      return ka[0] - kb[0] || ka[1] - kb[1] || a.localeCompare(b);
    });
    for (const c of order) {
      if (left >= 0) break;
      if (quota[c] > 0) { quota[c] = 0; left += 1; }
    }
  }

  const picked = [];
  for (const c of codes) {
    const stack = stacks[c];
    const n = quota[c] || 0;
    if (!n) continue;
    for (const i of evenIndices(stack.length, n)) picked.push(stack[i]);
  }
  return sortPapersAscending(picked);
}

/** The pool as filtered, with no trimming. Trimming is a separate decision. */
function selectPool(papers, units, scope) {
  let pool = papers.filter((p) => units.includes(p.unit));
  if (scope === 'new') pool = pool.filter((p) => p.spec === 'new');
  pool = sortPapersAscending(pool);
  return { pool, available: pool.length };
}

/**
 * Why a pool came out empty, when the reason is not just "no papers". Ticking a
 * legacy unit such as BI04 while the pool is set to new spec only gives zero and
 * used to blame the catalogue.
 */
function poolNote(papers, units, scope) {
  if (scope !== 'new' || !units.length) return '';
  const inUnits = papers.filter((p) => units.includes(p.unit));
  if (!inUnits.length) return '';
  if (inUnits.some((p) => p.spec === 'new')) return '';
  return 'Every unit you ticked is legacy, and the pool is set to new spec only. Switch the pool to New + legacy, or tick a unit under Current spec.';
}

function parseDay(iso) {
  return new Date(iso + 'T00:00:00');
}

function isoDay(date) {
  const d = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 10);
}

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function mondayOf(date) {
  const d = new Date(date);
  const day = d.getDay() || 7; // Sunday counts as 7
  return addDays(d, 1 - day);
}

function buildSlots(startIso, examIso, perWeek) {
  const offsets = WEEK_OFFSETS[perWeek] || WEEK_OFFSETS[4];
  const start = parseDay(startIso);
  const exam = parseDay(examIso);
  const slots = [];
  let monday = mondayOf(start);

  while (monday < exam) {
    for (const offset of offsets) {
      const day = addDays(monday, offset - 1);
      if (day >= start && day < exam) slots.push(day);
    }
    monday = addDays(monday, 7);
  }
  return slots;
}

/**
 * The smallest sessions-per-week the plan actually fits into, or null when even
 * a session every day of the week is not enough. Guessing at this with
 * ceil(tasks / weeks) used to promise a number that did not fit.
 */
function sessionsPerWeekNeeded(taskCount, startIso, examIso) {
  for (let perWeek = 1; perWeek <= MAX_PER_WEEK; perWeek += 1) {
    if (buildSlots(startIso, examIso, perWeek).length >= taskCount) return perWeek;
  }
  return null;
}

function buildSequence(pool) {
  // Every paper except the newest of its unit is practice. The newest paper of
  // each unit is the timed mock, and mocks sit at the very end of the plan so
  // the last thing done before the exam is the closest thing to the exam.
  const counts = {};
  for (const p of pool) counts[p.unit] = (counts[p.unit] || 0) + 1;
  const newest = {};
  for (const p of sortPapersAscending(pool)) newest[p.unit] = p;

  const practice = [];
  const mocks = [];
  for (const p of sortPapersAscending(pool)) {
    if (newest[p.unit] === p && counts[p.unit] > 1) mocks.push(p);
    else practice.push(p);
  }

  const tasks = [];
  const addBlock = (list, type) => {
    list.forEach((paper, index) => {
      tasks.push({ type, paper });
      // Every second paper is followed by a review of both, which is the spacing.
      if (index % 2 === 1) {
        tasks.push({ type: 'review', covers: [list[index - 1], paper] });
      }
    });
  };
  addBlock(practice, 'paper');
  addBlock(mocks, 'mock');
  return tasks;
}

/** Largest evenly spread subset of `pool` whose tasks still fit the slots. */
function fitPool(pool, slotCount, maxPapers) {
  if (!slotCount) return [];
  let k = Math.min(pool.length, maxPapers, slotCount);
  while (k > 1 && buildSequence(selectEvenly(pool, k)).length > slotCount) k -= 1;
  return selectEvenly(pool, k);
}

/**
 * Spread the sessions across the whole run-up instead of bunching them at the
 * start. A 5-paper plan over 8 weeks should not finish by week two.
 *
 * Dates are strictly increasing and the last session lands on the last free day,
 * so the plan always walks forward and never stacks two sessions on one day.
 */
function spreadSchedule(tasks, slots) {
  const n = Math.min(tasks.length, slots.length);
  if (!n) return [];
  const out = [];
  let cursor = 0;
  for (let i = 0; i < n; i += 1) {
    const target = n === 1 ? slots.length - 1
      : Math.round((i * (slots.length - 1)) / (n - 1));
    // Leave room for the sessions still to come, then never go backwards.
    const ceiling = slots.length - (n - 1 - i) - 1;
    let index = Math.max(cursor, Math.min(target, ceiling));
    if (i === n - 1) index = slots.length - 1;
    if (index >= slots.length) index = slots.length - 1;
    cursor = index + 1;
    const date = isoDay(slots[index]);
    out.push({ ...tasks[i], date, id: taskId(tasks[i]) });
  }
  return out;
}

function buildPlan(config, papers) {
  const units = config.units && config.units.length ? config.units : Object.keys(
    papers.reduce((acc, p) => { acc[p.unit] = 1; return acc; }, {}));
  const gap = gradeGap(config.current, config.target);
  const selection = selectPool(papers, units, config.scope);
  const available = selection.available;

  // How many papers the request actually asks for. The grade gap decides it,
  // unless the pool scope is an explicit count.
  const wanted = config.scope === 'count'
    ? Math.max(1, Number(config.count) || 5)
    : papersRequired(gap, units.length);

  const slots = buildSlots(config.start, config.exam, Number(config.perWeek) || 4);
  const days = Math.max(1, Math.round((parseDay(config.exam) - parseDay(config.start)) / 86400000));
  const weeks = Math.max(1, Math.ceil(days / 7));

  // What the full request would cost in sessions, at this intensity.
  const askedPool = selectEvenly(selection.pool, Math.min(wanted, available));
  const asked = buildSequence(askedPool);
  const feasible = asked.length <= slots.length;
  const perWeekNeeded = feasible
    ? null
    : sessionsPerWeekNeeded(asked.length, config.start, config.exam);
  const recommendedPerWeek = perWeekNeeded
    || Math.min(MAX_PER_WEEK, Math.max(1, Math.ceil(asked.length / weeks)));

  // Then build the plan that fits. Trim from the papers, never from the mocks.
  const pool = fitPool(selection.pool, slots.length, Math.min(wanted, available));
  const tasks = buildSequence(pool);
  const scheduled = spreadSchedule(tasks, slots);

  const warnings = [];
  if (!slots.length) {
    warnings.push('There are no free days between the start date and the exam, so nothing can be scheduled. Move one of the dates.');
  }
  if (!available) {
    warnings.push(poolNote(papers, units, config.scope)
      || 'No papers match. Widen the pool or download more for this subject.');
  } else if (available < wanted) {
    warnings.push('That pool holds ' + available + ' papers and this asks for ' + wanted +
      '. The plan uses what is there.');
  }
  const fitTarget = Math.min(wanted, available);
  if (available && slots.length && pool.length < fitTarget) {
    warnings.push('The plan fits ' + pool.length + ' of the ' + fitTarget + ' papers into the ' +
      plural(slots.length, 'session') + ' you have before the exam, so it uses a spread of those. ' +
      (perWeekNeeded
        ? 'At ' + perWeekNeeded + ' sessions a week all ' + fitTarget + ' would fit.'
        : 'Even ' + MAX_PER_WEEK + ' sessions a week would not fit all ' + fitTarget +
          ', so take fewer units or a smaller pool.'));
  }

  const mins = Number(config.mins) || 75;

  return {
    config,
    gap,
    wanted,
    pool,
    available,
    tasks: scheduled,
    unscheduled: Math.max(0, tasks.length - scheduled.length),
    stats: {
      papers: pool.length,
      mocks: scheduled.filter((t) => t.type === 'mock').length,
      reviews: scheduled.filter((t) => t.type === 'review').length,
      sessions: scheduled.length,
      sessionsAsked: asked.length,
      scheduled: scheduled.length,
      slots: slots.length,
      weeks,
      days,
      feasible,
      recommendedPerWeek,
      perWeekNeeded,
      hours: Math.round((scheduled.length * mins) / 60 * 10) / 10
    },
    warnings
  };
}

function taskId(task) {
  if (task.type === 'review') {
    return ['review', task.covers.map((p) => p.unit + p.session + p.year).join('-')].join('|');
  }
  return [task.type, task.paper.unit, task.paper.session, task.paper.year].join('|');
}

function paperName(paper) {
  return (paper.unit || '?') + ' · ' + (paper.session || '?') + ' ' + (paper.year || '');
}

function taskLabel(task) {
  if (task.type === 'review') {
    return 'Review ' + task.covers.map((p) => p.unit).join(' + ');
  }
  return paperName(task.paper);
}

const DOWS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

/**
 * The plan as calendar months, each with its own weekday header and its weeks.
 * A week is filed under the month its Thursday falls in, so a week that straddles
 * a month end does not show up under the wrong heading.
 */
function calendarMonths(startIso, examIso, tasks) {
  const start = parseDay(startIso);
  const exam = parseDay(examIso);
  const examIsoDay = isoDay(exam);
  const byDate = {};
  for (const task of tasks) (byDate[task.date] = byDate[task.date] || []).push(task);

  const months = [];
  const seen = {};
  let monday = mondayOf(start);
  while (monday <= exam) {
    const days = [];
    for (let i = 0; i < 7; i += 1) {
      const day = addDays(monday, i);
      const iso = isoDay(day);
      days.push({
        date: iso,
        dayNum: day.getDate(),
        inRange: day >= start && day <= exam,
        isExam: iso === examIsoDay,
        tasks: byDate[iso] || []
      });
    }
    const anchor = addDays(monday, 3);
    const key = anchor.getFullYear() + '-' + String(anchor.getMonth() + 1).padStart(2, '0');
    if (!seen[key]) {
      seen[key] = { key, label: MONTHS[anchor.getMonth()] + ' ' + anchor.getFullYear(), weeks: [] };
      months.push(seen[key]);
    }
    seen[key].weeks.push(days);
    monday = addDays(monday, 7);
  }
  return months;
}

// ================= wiring =================

let P_CATALOGUE = null;
let P_PLAN = null;
let P_STATE = { config: {}, done: {} };
let pSaveTimer = null;

function pSave() {
  clearTimeout(pSaveTimer);
  pSaveTimer = setTimeout(() => {
    fetch('/api/planner/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: P_STATE.config, done: P_STATE.done })
    }).catch(() => {});
  }, 300);
}

function pGradeSelects() {
  const cur = $('p-current'), tgt = $('p-target');
  cur.innerHTML = ''; tgt.innerHTML = '';
  for (const g of GRADES) {
    cur.appendChild(new Option(g, g));
    tgt.appendChild(new Option(g, g));
  }
  const cfg = P_STATE.config || {};
  cur.value = cfg.current || 'C';
  tgt.value = cfg.target || 'A';
}

function pDates() {
  const today = isoDay(new Date());
  $('p-start').value = (P_STATE.config || {}).start || today;
  $('p-exam').value = (P_STATE.config || {}).exam || isoDay(addDays(new Date(), 56));
}

// ---- official exam dates ----
// Pearson publishes one xlsx per series. The server reads the sheet, this only
// has to show the sittings and offer to drop the right date into the plan.
let P_EXAMS = null;
const DOW_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function fmtDate(iso) {
  if (!iso) return '';
  const d = parseDay(iso);
  return DOW_SHORT[d.getDay()] + ' ' + d.getDate() + ' ' + MONTHS[d.getMonth()].slice(0, 3) + ' ' + d.getFullYear();
}

async function pLoadSeries() {
  const sel = $('p-series');
  try {
    const d = await json('/api/timetable');
    if (!d.series || !d.series.length) {
      sel.innerHTML = '<option value="">no timetables found</option>';
      return;
    }
    sel.innerHTML = d.series.map((s) =>
      '<option value="' + s.file + '"' + (d.picked && d.picked.file === s.file ? ' selected' : '') +
      '>' + s.label + '</option>').join('');
  } catch (e) {
    sel.innerHTML = '<option value="">unavailable</option>';
  }
}

async function pFindDates() {
  const box = $('p-examlist');
  const units = pSelectedUnits();
  if (!units.length) { box.textContent = 'Tick some units first.'; return; }
  box.textContent = 'Reading the Pearson timetable…';
  try {
    P_EXAMS = await json('/api/timetable?units=' + encodeURIComponent(units.join(',')) +
      '&series=' + encodeURIComponent($('p-series').value || ''));
  } catch (e) {
    box.textContent = 'Could not reach the local server.';
    return;
  }
  pRenderDates();
}

function pRenderDates() {
  const d = P_EXAMS;
  const box = $('p-examlist');
  if (!d) { box.textContent = ''; return; }
  if (d.error) { box.innerHTML = '<div class="warn">' + d.error + '</div>'; return; }
  if (!d.papers.length) {
    box.textContent = 'Pearson lists no ' + d.picked.label + ' sittings for the units you ticked.';
    return;
  }
  const rows = d.papers.map((p) =>
    '<div class="examrow"><span class="d">' + fmtDate(p.date) + '</span>' +
    '<span>' + p.unit + '</span>' +
    '<span class="u">' + p.time + ' · ' + p.duration + '</span></div>').join('');
  box.innerHTML = rows +
    '<div class="row" style="margin-top:.5rem">' +
    '<button class="small" data-exam="' + d.first + '">Plan up to the first paper</button>' +
    '<button class="small" data-exam="' + d.last + '">the last paper</button></div>';
  box.querySelectorAll('[data-exam]').forEach((b) => b.addEventListener('click', () => {
    $('p-exam').value = b.dataset.exam;
    pBuild();
    $('p-status').textContent = 'Exam date set to ' + fmtDate(b.dataset.exam) +
      ' from the ' + d.picked.label + ' timetable.';
  }));
}

async function pLoadSubject(subject, keepUnits) {
  const box = $('p-units');
  if (!subject) { box.innerHTML = '<div class="hint">Pick a subject first.</div>'; return; }
  box.innerHTML = '<div class="hint">Loading papers…</div>';
  $('p-pool').textContent = 'Loading…';

  let data;
  try {
    data = await json('/api/planner/catalogue?subject=' + encodeURIComponent(subject));
  } catch (e) {
    box.innerHTML = '<div class="hint">Could not load the catalogue.</div>';
    return;
  }
  P_CATALOGUE = data;

  const units = {};
  for (const p of data.papers) {
    if (!p.unit) continue;
    const u = units[p.unit] = units[p.unit] || { n: 0, spec: p.spec, label: p.label };
    u.n += 1;
  }
  const codes = Object.keys(units).sort();
  if (!codes.length) {
    box.innerHTML = '<div class="hint">No question papers found for this subject. Try the Download tab first.</div>';
    $('p-pool').textContent = data.warning || 'Nothing found.';
    return;
  }

  const chosen = keepUnits && keepUnits.length ? keepUnits : codes.filter((c) => units[c].spec === 'new');
  const pretty = (l) => { const m = /^U(\\d)$/.exec(l || ''); return m ? 'Unit ' + m[1] : (l || ''); };
  const row = (c) =>
    '<label><input type="checkbox" value="' + c + '"' + (chosen.includes(c) ? ' checked' : '') + '>' +
    '<span>' + c + ' · ' + pretty(units[c].label) + '</span>' +
    '<span class="u">' + units[c].n + ' qp</span></label>';
  // Split the list the way the download tab does. BI04 and WBI14 both print as
  // "Unit 4", and the legacy one silently vanishes under a new spec pool.
  const nw = codes.filter((c) => units[c].spec === 'new');
  const old = codes.filter((c) => units[c].spec !== 'new');
  box.innerHTML =
    (nw.length ? '<div class="hint" style="margin:.2rem 0 .3rem">Current spec</div>' + nw.map(row).join('') : '') +
    (old.length ? '<div class="hint" style="margin:.6rem 0 .3rem">Legacy (skipped by new spec only)</div>' + old.map(row).join('') : '');

  pPoolSummary();
}

function pSelectedUnits() {
  return Array.from(document.querySelectorAll('#p-units input:checked')).map((i) => i.value);
}

function pPoolSummary() {
  const el = $('p-pool');
  if (!P_CATALOGUE) { el.textContent = 'Pick a subject.'; return; }
  const units = pSelectedUnits();
  const scope = (document.querySelector('input[name="p-scope"]:checked') || {}).value || 'new';
  const sel = selectPool(P_CATALOGUE.papers, units, scope);
  const scopeLabel = scope === 'new' ? 'new spec' : scope === 'all' ? 'new + legacy' : 'selected';
  const years = sel.pool.map((p) => Number(p.year) || 0).filter(Boolean);
  const span = years.length
    ? Math.min.apply(null, years) + '–' + Math.max.apply(null, years)
    : 'no years';
  const note = sel.available ? '' : poolNote(P_CATALOGUE.papers, units, scope);

  el.innerHTML =
    '<b>' + sel.pool.length + '</b> papers in the pool (' + scopeLabel + ')' +
    '<div class="poolrow">' +
    (P_CATALOGUE.warning ? '<span>⚠ ' + P_CATALOGUE.warning + '</span>' : '<span>source: ' + P_CATALOGUE.source + '</span>') +
    '<span>' + new Set(sel.pool.map((p) => p.unit)).size + ' units</span>' +
    '<span>' + span + '</span>' +
    '</div>' +
    (note ? '<div class="warn">' + note + '</div>' : '');
}

function pRenderSummary(plan) {
  const el = $('p-summary');
  const s = plan.stats;
  const verdict = s.feasible
    ? 'Fits: ' + s.sessions + ' sessions into ' + s.slots + ' available.'
    : (s.perWeekNeeded
      ? 'Does not fit at this intensity. Needs ' + s.perWeekNeeded + ' sessions a week.'
      : 'Does not fit at this intensity. Even ' + MAX_PER_WEEK + ' sessions a week is not enough.');

  el.innerHTML =
    '<div class="pstat">' +
    '<div><b>' + s.papers + '</b><span>papers</span></div>' +
    '<div><b>' + s.mocks + '</b><span>timed mocks</span></div>' +
    '<div><b>' + s.reviews + '</b><span>reviews</span></div>' +
    '<div><b>' + s.weeks + '</b><span>weeks left</span></div>' +
    '<div><b>' + s.hours + '</b><span>hours in total</span></div>' +
    '</div>' +
    '<p class="hint" style="margin:.3rem 0">Grade gap ' + plan.gap + ' · asked for ' + plan.wanted +
    ' papers · ' + verdict + '</p>' +
    (plan.warnings.length ? plan.warnings.map((w) => '<div class="warn">' + w + '</div>').join('') : '') +
    (s.perWeekNeeded && s.perWeekNeeded <= MAX_PER_WEEK
      ? '<button class="small" id="p-useweek" style="margin-top:.5rem">Set intensity to ' +
        s.perWeekNeeded + ' a week and rebuild</button>'
      : '');

  const useWeek = $('p-useweek');
  if (useWeek) useWeek.addEventListener('click', () => {
    $('p-intensity').value = String(s.perWeekNeeded);
    pBuild();
  });
}

function pRenderCalendar(plan) {
  const card = $('p-calendar-card');
  const grid = $('p-calendar');
  if (!plan.tasks.length) { card.style.display = 'none'; return; }
  card.style.display = '';

  const done = P_STATE.done || {};
  const total = plan.tasks.length;
  const completed = plan.tasks.filter((t) => done[t.id]).length;
  $('p-progress').textContent = completed + ' of ' + total + ' done';

  const months = calendarMonths(plan.config.start, plan.config.exam, plan.tasks);
  const todayIso = isoDay(new Date());

  const cell = (day) => {
    const cls = ['pday'];
    if (!day.inRange) cls.push('out');
    if (day.date === todayIso) cls.push('today');
    if (day.isExam) cls.push('exam');
    const tasks = day.tasks.map((t) => {
      const tcls = ['ptask', t.type === 'review' ? 'review' : t.type === 'mock' ? 'mock' : 'paper'];
      if (done[t.id]) tcls.push('done');
      return '<div class="' + tcls.join(' ') + '" data-task="' + t.id + '">' +
        '<b>' + taskLabel(t) + '</b>' +
        '<span class="sub">' + (t.type === 'review' ? 'review session' : t.type === 'mock' ? 'timed mock' : 'past paper') + '</span>' +
        '</div>';
    }).join('');
    const num = day.inRange ? '<span class="dnum">' + day.dayNum + '</span>' : '<span class="dnum"></span>';
    const exam = day.isExam ? '<span class="examt">exam</span>' : '';
    return '<div class="' + cls.join(' ') + '">' + num + exam + tasks + '</div>';
  };

  grid.innerHTML = months.map((month) => {
    let count = 0;
    for (const week of month.weeks) for (const day of week) count += day.tasks.length;
    const head = '<div class="pmhead"><b>' + month.label + '</b><span>' +
      (count ? plural(count, 'session') : 'nothing scheduled') + '</span></div>';
    const dows = DOWS.map((d) => '<span>' + d + '</span>').join('');
    const weeks = month.weeks.map((days) =>
      '<div class="pweek">' + days.map(cell).join('') + '</div>').join('');
    return '<div class="pm">' + head + '<div class="pcal-head">' + dows + '</div>' + weeks + '</div>';
  }).join('');

  grid.querySelectorAll('[data-task]').forEach((el) => {
    el.addEventListener('click', () => {
      const id = el.dataset.task;
      P_STATE.done = P_STATE.done || {};
      if (P_STATE.done[id]) delete P_STATE.done[id]; else P_STATE.done[id] = true;
      pSave();
      const completedNow = plan.tasks.filter((t) => P_STATE.done[t.id]).length;
      $('p-progress').textContent = completedNow + ' of ' + total + ' done';
      el.classList.toggle('done', !!P_STATE.done[id]);
    });
  });
}

function pBuild() {
  if (!P_CATALOGUE) { $('p-status').textContent = 'Pick a subject first.'; return; }
  const scope = (document.querySelector('input[name="p-scope"]:checked') || {}).value || 'new';
  const config = {
    subject: $('p-subject').value,
    units: pSelectedUnits(),
    scope,
    count: Math.max(1, Math.min(200, Number($('p-count').value) || 5)),
    current: $('p-current').value,
    target: $('p-target').value,
    start: $('p-start').value,
    exam: $('p-exam').value,
    perWeek: Number($('p-intensity').value) || 4,
    mins: Number($('p-mins').value) || 75
  };

  if (!config.units.length) { $('p-status').textContent = 'Pick at least one unit.'; return; }
  if (!config.start || !config.exam || config.exam <= config.start) {
    $('p-status').textContent = 'The exam date has to be after the start date.';
    return;
  }

  P_STATE.config = config;
  P_PLAN = buildPlan(config, P_CATALOGUE.papers);
  pSave();
  pRenderSummary(P_PLAN);
  pRenderCalendar(P_PLAN);
  pPoolSummary();

  $('p-status').textContent = P_PLAN.stats.feasible
    ? 'Plan built. ' + P_PLAN.stats.papers + ' papers over ' + P_PLAN.stats.weeks + ' weeks.'
    : 'Plan built but it does not fit. Read the warning.';
}

function pIcs() {
  if (!P_PLAN || !P_PLAN.tasks.length) return;
  const subject = P_PLAN.config.subject || 'IAL';
  const mins = Number(P_PLAN.config.mins) || 75;
  const stamp = (d) => d.replace(/-/g, '');
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ial-papers//planner//EN', 'CALSCALE:GREGORIAN'];

  for (const task of P_PLAN.tasks) {
    const title = subject + ' · ' + taskLabel(task) + ' (' + (task.type === 'review' ? 'review' : task.type === 'mock' ? 'timed mock' : 'paper') + ')';
    const start = stamp(task.date) + 'T180000';
    const endDate = new Date(parseDay(task.date));
    endDate.setMinutes(endDate.getMinutes() + mins);
    const end = stamp(isoDay(endDate)) + 'T' + String(endDate.getHours()).padStart(2, '0') + String(endDate.getMinutes()).padStart(2, '0') + '00';
    lines.push('BEGIN:VEVENT');
    lines.push('UID:' + task.id.replace(/[^A-Za-z0-9]/g, '-') + '@ial-papers');
    lines.push('DTSTAMP:' + stamp(isoDay(new Date())) + 'T000000Z');
    lines.push('DTSTART:' + start);
    lines.push('DTEND:' + end);
    lines.push('SUMMARY:' + title.replace(/[,;]/g, ' '));
    lines.push('DESCRIPTION:Generated by ial-papers study planner');
    lines.push('END:VEVENT');
  }
  lines.push('END:VCALENDAR');

  const blob = new Blob([lines.join('\\r\\n')], { type: 'text/calendar' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'ial-plan-' + (P_PLAN.config.subject || 'study').replace(/\\s+/g, '-').toLowerCase() + '.ics';
  a.click();
  URL.revokeObjectURL(a.href);
}

async function pInit() {
  // State first. Loading it after filling the date inputs used to reset the
  // saved start and exam dates to today, so a rebuild silently moved the plan.
  try {
    P_STATE = await json('/api/planner/state');
    P_STATE.done = P_STATE.done || {};
  } catch (e) { P_STATE = { config: {}, done: {} }; }

  pGradeSelects();
  pDates();
  pLoadSeries();

  const cfg = P_STATE.config || {};
  if (cfg.current) $('p-current').value = cfg.current;
  if (cfg.target) $('p-target').value = cfg.target;
  if (cfg.perWeek) $('p-intensity').value = String(cfg.perWeek);
  if (cfg.mins) $('p-mins').value = cfg.mins;
  if (cfg.scope) {
    const radio = document.querySelector('input[name="p-scope"][value="' + cfg.scope + '"]');
    if (radio) radio.checked = true;
    $('p-countrow').style.display = cfg.scope === 'count' ? '' : 'none';
  }
  if (cfg.count) $('p-count').value = cfg.count;

  // Subject list comes from the downloader's own subject index.
  const sel = $('p-subject');
  sel.innerHTML = '';
  if (!Object.keys(ALL_SUBJECTS || {}).length) {
    try { ALL_SUBJECTS = await json('/api/subjects'); } catch (e) {}
  }
  const finalList = Object.keys(ALL_SUBJECTS || {});
  if (!finalList.length) {
    sel.innerHTML = '<option value="">No subjects found</option>';
  } else {
    sel.innerHTML = '<option value="">— pick a subject —</option>';
    finalList.sort().forEach((name) => sel.appendChild(new Option(name, name)));
  }
  if (cfg.subject) {
    sel.value = cfg.subject;
    await pLoadSubject(cfg.subject, cfg.units);
    if (cfg.start && cfg.exam) pBuild();
  }
}

try {
$('p-subject').addEventListener('change', (e) => { pLoadSubject(e.target.value); });
$('p-uall').addEventListener('click', () => {
  document.querySelectorAll('#p-units input').forEach((i) => { i.checked = true; });
  pPoolSummary();
});
$('p-unone').addEventListener('click', () => {
  document.querySelectorAll('#p-units input').forEach((i) => { i.checked = false; });
  pPoolSummary();
});
document.querySelectorAll('#p-units').forEach((box) => box.addEventListener('change', () => {
  // A changed unit selection makes any exam dates on screen stale.
  P_EXAMS = null;
  $('p-examlist').textContent = '';
  pPoolSummary();
}));
$('p-getdates').addEventListener('click', pFindDates);
$('p-series').addEventListener('change', () => {
  P_EXAMS = null;
  $('p-examlist').textContent = '';
});
$('p-scope').addEventListener('change', () => {
  const scope = (document.querySelector('input[name="p-scope"]:checked') || {}).value;
  $('p-countrow').style.display = scope === 'count' ? '' : 'none';
  pPoolSummary();
});
$('p-count').addEventListener('input', pPoolSummary);
$('p-build').addEventListener('click', pBuild);
$('p-ics').addEventListener('click', pIcs);
$('p-clear').addEventListener('click', () => {
  if (!confirm('Clear the plan and its ticks?')) return;
  P_STATE = { config: {}, done: {} };
  P_PLAN = null;
  pSave();
  $('p-calendar-card').style.display = 'none';
  $('p-summary').innerHTML = '<span class="hint">Nothing planned yet.</span>';
});
} catch (err) {
  // A broken planner must never take the downloader down with it.
  console.error('planner wiring failed', err);
  const box = $('p-summary');
  if (box) box.innerHTML = '<div class="warn">The planner failed to start. The other tabs still work.</div>';
}

// ================= score log =================
// Marks over time. The x axis is the date the paper was sat, not the year of the
// paper, so sitting a 2019 paper today shows up as today.
let SCORES = [];

function sFillSubject() {
  const sel = $('s-subject');
  const names = Object.keys(ALL_SUBJECTS || {}).sort();
  const keep = sel.value || (P_STATE.config || {}).subject || '';
  sel.innerHTML = '<option value="">— optional —</option>' +
    names.map((n) => '<option value="' + n + '">' + n.replace(/-/g, ' ') + '</option>').join('');
  if (keep) sel.value = keep;
}

function sPaperOptions() {
  const list = $('s-papers');
  const done = P_PLAN && P_PLAN.tasks
    ? P_PLAN.tasks.filter((t) => (P_STATE.done || {})[t.id])
    : [];
  list.innerHTML = done.map((t) =>
    '<option value="' + taskLabel(t) + '"></option>').join('');
}

function sDateValue(s) {
  const d = new Date((s.date || '') + 'T00:00:00');
  return isNaN(d.getTime()) ? null : d.getTime();
}

function sRenderChart(sorted) {
  const el = $('s-chart');
  if (!sorted.length) {
    el.className = 'hint';
    el.innerHTML = 'No scores yet. Log one and it appears here.';
    return;
  }
  el.className = '';
  const W = 660, H = 240, L = 38, R = 14, T = 14, B = 30;
  const times = sorted.map(sDateValue);
  const valid = times.filter((t) => t !== null);
  let t0 = 0, t1 = Math.max(1, sorted.length - 1);
  if (valid.length >= 2) {
    const lo = Math.min.apply(null, valid), hi = Math.max.apply(null, valid);
    if (lo !== hi) { t0 = lo; t1 = hi; }
  }
  const xOf = (i) => {
    const v = times[i] === null ? i : times[i];
    return L + ((v - t0) / (t1 - t0)) * (W - L - R);
  };
  const yOf = (pct) => T + (1 - Math.max(0, Math.min(100, pct)) / 100) * (H - T - B);

  const parts = [];
  parts.push('<svg class="schart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Score over time">');
  for (const mark of [0, 25, 50, 75, 100]) {
    const y = yOf(mark);
    parts.push('<line class="grid" x1="' + L + '" y1="' + y + '" x2="' + (W - R) + '" y2="' + y + '"></line>');
    parts.push('<text class="axis" x="' + (L - 6) + '" y="' + (y + 3) + '" text-anchor="end">' + mark + '</text>');
  }

  const pts = sorted.map((s, i) => xOf(i).toFixed(1) + ',' + yOf(s.pct).toFixed(1)).join(' ');
  parts.push('<polyline class="line" points="' + pts + '"></polyline>');

  // Trailing average of the last three scores, which is the honest trend line.
  const avg = sorted.map((s, i) => {
    const slice = sorted.slice(Math.max(0, i - 2), i + 1);
    return slice.reduce((a, x) => a + x.pct, 0) / slice.length;
  });
  if (sorted.length >= 2) {
    parts.push('<polyline class="avg" points="' +
      avg.map((v, i) => xOf(i).toFixed(1) + ',' + yOf(v).toFixed(1)).join(' ') + '"></polyline>');
  }

  sorted.forEach((s, i) => {
    parts.push('<circle class="dot" cx="' + xOf(i).toFixed(1) + '" cy="' + yOf(s.pct).toFixed(1) +
      '" r="4"><title>' + (s.date || '') + ' · ' + (s.label || s.unit || 'paper') + ' · ' +
      s.pct + '%</title></circle>');
  });

  const first = sorted[0], last = sorted[sorted.length - 1];
  parts.push('<text class="axis" x="' + L + '" y="' + (H - 8) + '">' + (first.date || '') + '</text>');
  if (sorted.length > 1) {
    parts.push('<text class="axis" x="' + (W - R) + '" y="' + (H - 8) + '" text-anchor="end">' + (last.date || '') + '</text>');
  }
  parts.push('</svg>');
  el.innerHTML = parts.join('');
}

function sRender() {
  const sorted = SCORES.slice().sort((a, b) =>
    String(a.date || '').localeCompare(String(b.date || '')));
  sRenderChart(sorted);

  const avgs = $('s-avgs');
  if (!sorted.length) { avgs.innerHTML = ''; }
  else {
    const last = sorted[sorted.length - 1];
    const recent = sorted.slice(-3);
    const recentAvg = recent.reduce((a, s) => a + s.pct, 0) / recent.length;
    const best = sorted.reduce((a, s) => (s.pct > a.pct ? s : a), sorted[0]);
    const firstAvg = sorted.slice(0, 3).reduce((a, s) => a + s.pct, 0) / Math.min(3, sorted.length);
    const trend = recentAvg - firstAvg;
    avgs.innerHTML =
      '<span>last <b>' + last.pct + '%</b></span>' +
      '<span>last 3 avg <b>' + recentAvg.toFixed(1) + '%</b></span>' +
      '<span>best <b>' + best.pct + '%</b></span>' +
      '<span>since start <b>' + (trend >= 0 ? '+' : '') + trend.toFixed(1) + '</b></span>';
  }

  const list = $('s-list');
  if (!sorted.length) { list.innerHTML = ''; return; }
  list.innerHTML = sorted.slice().reverse().map((s) =>
    '<div class="srow"><span class="d">' + (s.date || '—') + '</span>' +
    '<span class="p">' + (s.label || s.unit || 'paper') + '</span>' +
    '<span>' + s.pct + '%</span>' +
    '<button class="x" data-score="' + s.id + '" title="Delete">✕</button></div>').join('');
  list.querySelectorAll('[data-score]').forEach((b) => b.addEventListener('click', () => sDelete(b.dataset.score)));
}

async function sLoad() {
  try { SCORES = (await json('/api/scores')).scores || []; } catch (e) { SCORES = []; }
  sFillSubject();
  sRender();
  sPaperOptions();
}

async function sDelete(id) {
  const r = await json('/api/scores', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'delete', id })
  });
  if (r.ok) { SCORES = r.scores; sRender(); }
}

$('s-add').addEventListener('click', async () => {
  const st = $('s-status');
  const raw = Number($('s-raw').value);
  const total = Number($('s-total').value);
  const date = $('s-date').value || isoDay(new Date());
  if (!(total > 0)) { st.className = 'status err'; st.textContent = 'Put in the total marks for the paper.'; return; }
  if (!(raw >= 0) || raw > total) { st.className = 'status err'; st.textContent = 'The mark has to be between 0 and the total.'; return; }

  const label = $('s-label').value.trim();
  const body = {
    action: 'add', date, label,
    subject: $('s-subject').value,
    unit: (label.split('·')[0] || '').trim(),
    raw, total
  };
  try {
    const r = await json('/api/scores', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(r.error || 'could not save');
    SCORES = r.scores;
    st.className = 'status ok';
    st.textContent = 'Logged ' + raw + '/' + total + ' (' + Math.round(raw * 1000 / total) / 10 + '%).';
    $('s-raw').value = ''; $('s-total').value = ''; $('s-label').value = '';
    sRender();
  } catch (e) {
    st.className = 'status err';
    st.textContent = String(e.message || e);
  }
});

$('s-date').value = isoDay(new Date());

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
                if os.path.basename(dirpath) == SPEC_DIR:
                    continue  # a spec is not a past paper, do not count it here
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


_PLANNER_CACHE = {}


def _planner_catalogue(subject, refresh=False):
    """Question papers available for a subject, newest last.

    Tries Pearson first so the planner can offer papers that are not downloaded
    yet, then falls back to manifest.json, which is what the downloader already
    knows about. Offline is a supported state, not an error.
    """
    if not refresh and subject in _PLANNER_CACHE:
        return _PLANNER_CACHE[subject]

    papers, source, warning = [], "manifest", ""

    try:
        # Pearson's facet values are full names ("Question-paper"), not the
        # short codes the UI uses, so they go through the same mapping the
        # downloader uses.
        live = ial.fetch_all(doc_types=_doc_type_variants(["qp"]),
                             subjects=[subject] if subject else None)
        for p in live:
            if getattr(p, "type_short", "") != "qp":
                continue
            papers.append({
                "unit": p.unit_code or "",
                "label": p.unit_label or "",
                "session": p.session or "",
                "year": int(p.year or 0),
                "variant": getattr(p, "variant", "") or "",
                "spec": "new" if ial.is_new_spec(p.unit_code or "") else "legacy",
                "title": p.title or "",
                "url": p.url or "",
            })
        if papers:
            source = "live"
        else:
            warning = "Pearson returned nothing, using the local catalogue instead."
    except Exception as exc:  # offline, blocked, rate limited
        warning = "Could not reach Pearson (%s), using the local catalogue." % type(exc).__name__

    if not papers:
        manifest_path = os.path.join(OUT_ROOT, "manifest.json")
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
            for p in manifest.get("papers", []):
                if p.get("type") != "Question-paper":
                    continue
                if subject and p.get("subject") != subject:
                    continue
                unit = p.get("unit") or ""
                papers.append({
                    "unit": unit,
                    "label": p.get("label") or "",
                    "session": p.get("session") or "",
                    "year": int(p.get("year") or 0),
                    "variant": "",
                    "spec": "new" if ial.is_new_spec(unit) else "legacy",
                    "title": p.get("title") or "",
                    "url": p.get("url") or "",
                })
        except (OSError, ValueError):
            papers = []

    # One entry per unit/session/year. Regional variants (A/R suffixes) are the
    # same paper for planning purposes; keep the plain one when there is a choice.
    best = {}
    for p in papers:
        key = (p["unit"], p["session"], p["year"])
        rank = 0 if not p["variant"] else 1
        if key not in best or rank < best[key][0]:
            best[key] = (rank, p)
    clean = sorted((v[1] for v in best.values()),
                   key=lambda p: (p["year"], p["session"], p["unit"]))

    result = {"subject": subject, "source": source, "warning": warning,
              "papers": clean}
    _PLANNER_CACHE[subject] = result
    return result


# ------------------------- specifications -------------------------
# The discovery rules live in ial.py so the CLI uses the same ones. web.py owns
# the cache, the folder layout and the download.
_SPEC_CACHE = {}


def _spec_docs(subject):
    """Specification PDFs for one subject, best first."""
    try:
        return ial.spec_docs(subject), ""
    except Exception as exc:  # offline, blocked, rate limited
        return [], "Could not reach Pearson (%s)." % type(exc).__name__


def _spec_on_disk(subject=None):
    """Specification PDFs already saved, as paths relative to papers/."""
    if not os.path.isdir(OUT_ROOT):
        return []
    names = [subject] if subject else sorted(os.listdir(OUT_ROOT))
    out = []
    for name in names:
        folder = os.path.join(OUT_ROOT, name, SPEC_DIR)
        if not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            if not fn.lower().endswith(".pdf"):
                continue
            full = os.path.join(folder, fn)
            try:
                size = round(os.path.getsize(full) / 1e6, 2)
            except OSError:
                size = 0
            out.append({"subject": name, "filename": fn, "size_mb": size,
                        "path": "%s/%s/%s" % (name, SPEC_DIR, fn)})
    return out


def _spec_candidates(subject, refresh=False):
    if not refresh and subject in _SPEC_CACHE:
        return _SPEC_CACHE[subject]
    docs, error = _spec_docs(subject)
    chosen = next((d for d in docs if not d["odd"]), docs[0] if docs else None)
    result = {
        "subject": subject,
        "chosen": chosen,
        "others": [d for d in docs if d is not chosen],
        "error": error,
        "on_disk": _spec_on_disk(subject),
    }
    _SPEC_CACHE[subject] = result
    return result


def _download_spec(subject, doc):
    """Fetch one spec PDF into papers/<Subject>/_Specification/."""
    folder = os.path.join(OUT_ROOT, subject, SPEC_DIR)
    os.makedirs(folder, exist_ok=True)
    name = ial.spec_filename(subject, doc)
    dest = os.path.join(folder, name)
    rel = "%s/%s/%s" % (subject, SPEC_DIR, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return {"ok": True, "path": rel, "skipped": True}

    url = ial.DOWNLOAD_BASE + urllib.parse.quote(doc["url"], safe="/-_.%")
    req = urllib.request.Request(url, headers={"User-Agent": ial.USER_AGENT})
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=90) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        with open(tmp, "rb") as f:
            if not f.read(8).startswith(b"%PDF"):
                raise ValueError("Pearson did not return a PDF")
        os.replace(tmp, dest)
    except Exception as exc:  # noqa: BLE001
        if os.path.exists(tmp):
            os.remove(tmp)
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return {"ok": True, "path": rel, "skipped": False}


def _get_scores():
    data = _load_json(SCORES_FILE, {"scores": []})
    if not isinstance(data.get("scores"), list):
        data = {"scores": []}
    return data


# ------------------------- exam timetables -------------------------
# Pearson publishes the IAL timetable as an xlsx per series. One scrape of the
# timetables page finds them, then the parsed rows are cached for the session.
_TT_SERIES = {"series": None}
_TT_ROWS = {}


def _tt_series(refresh=False):
    if refresh or _TT_SERIES["series"] is None:
        try:
            _TT_SERIES["series"] = ial.timetable_series()
        except Exception:  # offline, blocked
            _TT_SERIES["series"] = _TT_SERIES["series"] or []
    return _TT_SERIES["series"]


def _tt_next(series):
    """The first series that has not already happened, else the last one listed."""
    today = date.today()
    for s in series:
        if (s["year"], s["month"]) >= (today.year, today.month):
            return s
    return series[-1] if series else None


def _tt_sittings(url):
    if url not in _TT_ROWS:
        _TT_ROWS[url] = ial.exam_dates([], url)
    return _TT_ROWS[url]


def _timetable(units, series_file, refresh=False):
    series = _tt_series(refresh=refresh)
    if not series:
        return {"series": [], "picked": None, "papers": [], "error":
                "Could not read Pearson's timetable page."}
    picked = next((s for s in series if s["file"] == series_file), None) or _tt_next(series)
    out = {
        "series": [{"label": s["label"], "file": s["file"]} for s in series],
        "picked": {"label": picked["label"], "file": picked["file"]},
        "papers": [],
        "first": "",
        "last": "",
        "error": "",
    }
    if not units:
        return out
    try:
        sittings = _tt_sittings(picked["url"])
    except Exception as exc:  # noqa: BLE001
        out["error"] = "Could not read the %s timetable (%s)." % (
            picked["label"], type(exc).__name__)
        return out
    want = {u.upper() for u in units}
    papers = [p for p in sittings if p["unit"] in want]
    papers.sort(key=lambda p: (p["date"], p["unit"]))
    out["papers"] = papers
    if papers:
        out["first"] = papers[0]["date"]
        out["last"] = papers[-1]["date"]
    return out


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
                if SPEC_DIR in parts[:2]:
                    continue  # the spec is not a paper and stays out of the grid
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


def _stop_server():
    """Ask serve_forever to return, then let the process exit."""
    if SERVER is not None:
        SERVER.shutdown()
    os._exit(0)


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
            _send_json(self, ial.subject_menu())
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
        if path == "/api/planner/catalogue":
            subject = qs.get("subject", [""])[0]
            if not subject:
                _send_json(self, {"error": "subject required"}, 400)
                return
            refresh = qs.get("refresh", [""])[0] in ("1", "true", "yes")
            _send_json(self, _planner_catalogue(subject, refresh=refresh))
            return
        if path == "/api/planner/state":
            _send_json(self, _load_json(PLAN_FILE, {"config": {}, "done": {}}))
            return
        if path == "/api/spec":
            subject = qs.get("subject", [""])[0]
            if not subject:
                _send_json(self, {"error": "subject required"}, 400)
                return
            refresh = qs.get("refresh", [""])[0] in ("1", "true", "yes")
            _send_json(self, _spec_candidates(subject, refresh=refresh))
            return
        if path == "/api/pdf":
            rel = qs.get("path", [""])[0]
            full = os.path.realpath(os.path.join(OUT_ROOT, rel))
            root = os.path.realpath(OUT_ROOT)
            if not rel or not full.startswith(root + os.sep) or not os.path.isfile(full):
                _send_json(self, {"error": "not found"}, 404)
                return
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                _send_json(self, {"error": "unreadable"}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition",
                             'inline; filename="%s"' % os.path.basename(full))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/scores":
            _send_json(self, _get_scores())
            return
        if path == "/api/timetable":
            units = [u.strip() for u in qs.get("units", [""])[0].split(",") if u.strip()]
            series = qs.get("series", [""])[0]
            refresh = qs.get("refresh", [""])[0] in ("1", "true", "yes")
            _send_json(self, _timetable(units, series, refresh=refresh))
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
        if self.path == "/api/shutdown":
            # Custom header check: a plain cross-site form post cannot set one,
            # so another page in the browser cannot stop the server.
            if self.headers.get("X-Ial-Papers") != "shutdown":
                _send_json(self, {"error": "missing header"}, 403)
                return
            _send_json(self, {"ok": True, "message": "server stopping"})
            threading.Timer(0.3, _stop_server).start()
            return
        if self.path == "/api/planner/state":
            body.setdefault("config", {})
            body.setdefault("done", {})
            _save_json(PLAN_FILE, body)
            _send_json(self, {"saved": True})
            return
        if self.path == "/api/spec":
            subject = body.get("subject") or ""
            if not subject:
                _send_json(self, {"ok": False, "error": "subject required"}, 400)
                return
            candidates = _spec_candidates(subject)
            pool = ([candidates["chosen"]] if candidates["chosen"] else []) \
                + candidates["others"]
            doc = next((d for d in pool if d and d["url"] == body.get("url")), None)
            if doc is None:
                # The UI may send a url that came from an earlier session. Rebuild
                # just enough of the record to name the file sensibly.
                if not body.get("url"):
                    _send_json(self, {"ok": False, "error": "no specification url"}, 400)
                    return
                m = ial._SPEC_VERSION_RE.search(body["url"])
                doc = {"url": body["url"], "title": body.get("title") or "",
                       "kind": "spec", "version": int(m.group(1)) if m else 0,
                       "issue": 0, "odd": False}
            result = _download_spec(subject, doc)
            _SPEC_CACHE.pop(subject, None)
            _send_json(self, result)
            return
        if self.path == "/api/scores":
            data = _get_scores()
            action = body.get("action") or "add"
            scores = data["scores"]
            if action == "add":
                try:
                    raw = float(body.get("raw"))
                    total = float(body.get("total"))
                except (TypeError, ValueError):
                    _send_json(self, {"ok": False, "error": "marks must be numbers"}, 400)
                    return
                if total <= 0 or raw < 0 or raw > total:
                    _send_json(self, {"ok": False,
                                      "error": "raw marks have to be between 0 and the total"},
                               400)
                    return
                entry = {
                    "id": body.get("id") or str(int(time.time() * 1000)),
                    "date": body.get("date") or "",
                    "subject": body.get("subject") or "",
                    "unit": body.get("unit") or "",
                    "label": body.get("label") or "",
                    "raw": raw,
                    "total": total,
                    "pct": round(raw * 100.0 / total, 1),
                }
                scores.append(entry)
            elif action == "delete":
                data["scores"] = scores = [s for s in scores if s.get("id") != body.get("id")]
            else:
                _send_json(self, {"ok": False, "error": "unknown action"}, 400)
                return
            _save_json(SCORES_FILE, data)
            _send_json(self, {"ok": True, "scores": scores})
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
    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    SERVER.serve_forever()
