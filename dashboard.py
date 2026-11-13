"""Generate a self-contained, zero-dependency HTML dashboard for a papers tree.

Scans the output directory for PDFs, cross-references manifest.json (the
catalogue) and failures.json (unpublished papers), and writes one
dashboard.html file with everything embedded. No CDN, works offline.
"""

import datetime
import html
import json
import os
import re

TYPE_COLORS = {
    "qp": "#58a6ff",
    "ms": "#3fb950",
    "er": "#d29922",
    "gb": "#bc8cff",
    "pr": "#f778ba",
    "ai": "#f778ba",
    "mp3": "#79c0ff",
    "sa": "#8b949e",
    "doc": "#8b949e",
}
TYPE_LABELS = {
    "qp": "Question paper", "ms": "Mark scheme", "er": "Examiner report",
    "gb": "Grade boundaries", "pr": "Pre-release", "ai": "Advance info",
    "mp3": "Listening", "sa": "Scientific article", "doc": "Other",
}
SESSION_ORDER = ["Jan", "Feb", "Mar", "May", "Jun", "Oct", "Nov"]

_NAME_RE = re.compile(
    r"^(?P<unit>[A-Za-z0-9-]+)_(?P<session>[A-Za-z]{3})"
    r"(?P<year>\d{4})_(?P<type>[a-z0-9]+)\.pdf$")
_URL_UNIT_RE = re.compile(r"([A-Z]{2,4}\d{2,4})", re.IGNORECASE)
_URL_YEAR_RE = re.compile(r"(\d{4})")
_TYPE_SUFFIX = {"-que-": "qp", "-rms-": "ms", "-msc-": "ms", "-pef-": "er"}


def parse_name(fname):
    m = _NAME_RE.match(fname)
    if not m:
        return None
    d = m.groupdict()
    d["year"] = int(d["year"])
    return d


def scan_files(root):
    """Walk the tree; return list of paper dicts."""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        parts = rel.split(os.sep)
        subject = parts[0] if parts and parts[0] not in (".", "") else "?"
        for f in files:
            if not f.endswith(".pdf"):
                continue
            meta = parse_name(f)
            if not meta:
                continue
            path = os.path.join(dirpath, f)
            meta.update({
                "path": path,
                "subject": subject,
                "size": os.path.getsize(path),
            })
            out.append(meta)
    return out


def load_manifest(root):
    try:
        with open(os.path.join(root, "manifest.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_failures(root):
    try:
        with open(os.path.join(root, "failures.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def parse_failure(url):
    base = url.rstrip("/").split("/")[-1].lower()
    unit = _URL_UNIT_RE.search(base)
    year = _URL_YEAR_RE.search(base)
    typ = "doc"
    for suf, t in _TYPE_SUFFIX.items():
        if suf in base:
            typ = t
            break
    return {
        "unit": unit.group(1).upper() if unit else "?",
        "year": int(year.group(1)) if year else 0,
        "type": typ,
        "name": base,
    }


def build_data(root):
    files = scan_files(root)
    manifest = load_manifest(root)
    failures = load_failures(root)

    subjects, total_bytes = set(), 0
    type_counts = {}
    rows = []  # flat table rows
    for p in files:
        subjects.add(p["subject"])
        total_bytes += p["size"]
        type_counts[p["type"]] = type_counts.get(p["type"], 0) + 1
        rows.append(p)

    catalogue = {"total": 0, "downloaded": len(files), "per_subject": {}}
    if manifest:
        catalogue["total"] = len(manifest.get("papers", []))
        for mp in manifest.get("papers", []):
            s = mp.get("subject", "?")
            catalogue["per_subject"][s] = \
                catalogue["per_subject"].get(s, 0) + 1

    missing = [parse_failure(u) for u in failures]
    miss_units = sorted(set(m["unit"] for m in missing))

    return {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "root": root,
        "kpi": {
            "files": len(files),
            "size_mb": round(total_bytes / 1e6, 1),
            "subjects": len(subjects),
            "units": len(set(p["unit"] for p in files)),
            "types": type_counts,
        },
        "catalogue": catalogue,
        "subjects": sorted(subjects),
        "papers": rows,
        "missing": missing,
        "missing_units": miss_units,
    }


def _esc(s):
    return html.escape(str(s), quote=True)


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IAL Papers — Dashboard</title>
<style>
:root{
  --bg:#0b0e14; --card:#131722; --line:#1f2637; --text:#e6e9ef;
  --muted:#8b93a7; --accent:#7cff4f; --blue:#58a6ff; --green:#3fb950;
  --amber:#d29922; --purple:#bc8cff; --red:#f85149;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;
  padding:32px 40px 80px;min-height:100vh}
h1{font-size:22px;font-weight:700;letter-spacing:-.02em}
h1 .bolt{color:var(--accent)}
.sub{color:var(--muted);font-size:13px;margin-top:2px}
header{display:flex;justify-content:space-between;align-items:flex-start;
  margin-bottom:28px;flex-wrap:wrap;gap:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:14px;margin-bottom:28px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px}
.kpi .num{font-size:30px;font-weight:800;letter-spacing:-.03em}
.kpi .lbl{color:var(--muted);font-size:12px;text-transform:uppercase;
  letter-spacing:.08em;margin-top:2px}
.kpi .sub{font-size:12px;color:var(--muted);margin-top:4px}
section{margin-bottom:32px}
h2{font-size:16px;margin-bottom:14px;letter-spacing:-.01em}
h2 .hint{color:var(--muted);font-weight:400;font-size:12px;margin-left:8px}
.controls{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
select,input{background:var(--card);border:1px solid var(--line);color:var(--text);
  border-radius:8px;padding:8px 12px;font-size:13px;outline:none}
select:focus,input:focus{border-color:var(--accent)}
.heat{overflow-x:auto;border:1px solid var(--line);border-radius:12px;
  background:var(--card);padding:10px}
table.heatmap{border-collapse:separate;border-spacing:2px}
.heatmap th{font-size:11px;color:var(--muted);font-weight:500;text-align:center;
  padding:2px 4px;min-width:20px}
.heatmap td.unit{font-size:12px;font-weight:600;text-align:right;
  padding-right:10px;white-space:nowrap;color:var(--text)}
.heatmap td.cell{background:#0d1017;border:1px solid var(--line);border-radius:4px;
  padding:2px 3px;height:24px;min-width:22px;cursor:default}
.seg{display:inline-block;width:5px;height:14px;border-radius:2px;
  margin-right:2px;vertical-align:middle;opacity:.25}
.seg.on{opacity:1}
.legend{display:flex;gap:16px;margin-top:10px;font-size:12px;color:var(--muted);
  flex-wrap:wrap}
.legend .sw{display:inline-block;width:10px;height:10px;border-radius:3px;
  margin-right:5px;vertical-align:-1px}
table.files{width:100%;border-collapse:collapse;font-size:13px}
table.files th{color:var(--muted);text-align:left;font-weight:500;
  font-size:11px;text-transform:uppercase;letter-spacing:.06em;
  padding:8px 10px;border-bottom:1px solid var(--line)}
table.files td{padding:7px 10px;border-bottom:1px solid #161b28}
table.files tr:hover td{background:#141926}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;
  font-weight:600}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.missing{display:flex;flex-wrap:wrap;gap:8px}
.mchip{background:#2a1a12;border:1px solid #5c3a1e;color:#f0b36b;
  border-radius:8px;padding:6px 10px;font-size:12px}
.coverage{height:8px;background:#0d1017;border-radius:6px;overflow:hidden;
  border:1px solid var(--line)}
.coverage .fill{height:100%;background:linear-gradient(90deg,var(--green),var(--accent))}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:18px;margin-bottom:14px}
.foot{color:var(--muted);font-size:12px;margin-top:40px}
a{color:var(--accent)}
</style>
</head>
<body>
<header>
  <div>
    <h1>⚡ IAL Papers <span class="bolt">Dashboard</span></h1>
    <div class="sub">Generated __GEN__ · source: <span class="mono">__ROOT__</span></div>
  </div>
  <div class="sub">Re-run <span class="mono">python3 cli.py dashboard</span> after each sync</div>
</header>

<div class="kpis">
  <div class="kpi"><div class="num" id="k-files">–</div><div class="lbl">Papers downloaded</div></div>
  <div class="kpi"><div class="num" id="k-size">–</div><div class="lbl">Total size</div></div>
  <div class="kpi"><div class="num" id="k-subjects">–</div><div class="lbl">Subjects</div></div>
  <div class="kpi"><div class="num" id="k-units">–</div><div class="lbl">Units</div></div>
  <div class="kpi"><div class="num" id="k-cov">–</div><div class="lbl">Catalogue coverage</div>
    <div class="sub" id="k-cov-sub"></div></div>
</div>

<section>
  <h2>Coverage by subject <span class="hint">downloaded vs. last-synced catalogue</span></h2>
  <div id="cov-bars"></div>
</section>

<section>
  <h2>Paper matrix <span class="hint">rows = units · columns = session × year · cells = types held</span></h2>
  <div class="controls">
    <select id="s-subject"></select>
    <input id="s-search" placeholder="Filter files… (e.g. WMA11, ms, 2024)">
  </div>
  <div class="heat"><table class="heatmap" id="heat"></table>
    <div class="legend">
      <span><span class="sw" style="background:var(--blue)"></span>Question paper</span>
      <span><span class="sw" style="background:var(--green)"></span>Mark scheme</span>
      <span><span class="sw" style="background:var(--amber)"></span>Examiner report</span>
      <span><span class="sw" style="background:var(--purple)"></span>Grade boundaries</span>
    </div>
  </div>
</section>

<section>
  <h2>Files <span class="hint" id="f-count"></span></h2>
  <table class="files"><thead>
    <tr><th>File</th><th>Unit</th><th>Session</th><th>Type</th><th>Size</th></tr>
  </thead><tbody id="f-body"></tbody></table>
</section>

<section id="sec-missing">
  <h2>Awaiting Pearson publication <span class="hint">listed in the index, not downloadable yet</span></h2>
  <div class="missing" id="missing-chips"></div>
</section>

<div class="foot">Data from Pearson's official past-papers index · dashboard.html is fully self-contained — share it as one file.</div>

<script>
const DATA = __DATA__;
const TCOL = __TCOL__;
const TLAB = __TLAB__;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// KPIs
const k = DATA.kpi;
$('k-files').textContent = k.files;
$('k-size').textContent = (k.size_mb >= 1000
  ? (k.size_mb/1000).toFixed(2)+' GB' : k.size_mb.toFixed(1)+' MB');
$('k-subjects').textContent = k.subjects;
$('k-units').textContent = k.units;
const cat = DATA.catalogue;
const covOk = cat.total && cat.total >= cat.downloaded;
$('k-cov').textContent = covOk
  ? Math.round(100*cat.downloaded/cat.total)+'%' : '–';
$('k-cov-sub').textContent = covOk
  ? cat.downloaded+' / '+cat.total+' papers'
  : 'run sync for full catalogue';

// coverage bars
const bars = $('cov-bars');
for (const s of DATA.subjects) {
  const held = DATA.papers.filter(p => p.subject === s).length;
  const total = (cat.per_subject && cat.per_subject[s]) || held;
  const pct = total ? Math.round(100*held/total) : 0;
  const row = document.createElement('div');
  row.className = 'card';
  row.innerHTML = '<div style="display:flex;justify-content:space-between;margin-bottom:8px">'
    +'<b>'+esc(s)+'</b><span class="sub">'+held+' / '+total+'</span></div>'
    +'<div class="coverage"><div class="fill" style="width:'+pct+'%"></div></div>';
  bars.appendChild(row);
}

// matrix
const byUnit = {};
for (const p of DATA.papers) {
  const key = p.subject+'|'+p.unit;
  (byUnit[key] = byUnit[key] || []).push(p);
}
let cols = [];
const colSet = new Set();
for (const p of DATA.papers) colSet.add(p.year+'|'+p.session);
const SORD = {Jan:0,Feb:1,Mar:2,May:3,Jun:4,Oct:5,Nov:6};
cols = [...colSet].map(c => c.split('|')).sort((a,b) =>
  (a[0]-b[0]) || ((SORD[a[1]]??9)-(SORD[b[1]]??9)));

const sel = $('s-subject');
for (const s of DATA.subjects) {
  const o = document.createElement('option');
  o.value = s; o.textContent = s;
  sel.appendChild(o);
}

function renderHeat() {
  const subject = sel.value;
  const units = Object.keys(byUnit)
    .filter(k => k.startsWith(subject+'|'))
    .map(k => k.split('|')[1])
    .filter((v,i,a) => a.indexOf(v) === i)
    .sort();
  const heat = $('heat');
  let html = '<tr><th></th>';
  let lastYear = '';
  for (const [y, s] of cols) {
    if (y !== lastYear) { html += '<th colspan="4">'+y+'</th>'; lastYear = y; }
  }
  html += '</tr><tr><th></th>';
  for (const [y, s] of cols) {
    html += '<th>'+s+'</th>';
  }
  html += '</tr>';
  for (const u of units) {
    html += '<tr><td class="unit">'+esc(u)+'</td>';
    const key = subject+'|'+u;
    const list = byUnit[key] || [];
    for (const [y, s] of cols) {
      const held = {};
      for (const p of list)
        if (p.year === +y && p.session === s) held[p.type] = 1;
      html += '<td class="cell" title="'+esc(u)+' · '+s+' '+y+'">'
        + ['qp','ms','er','gb'].map(t =>
            '<span class="seg'+(held[t]?' on':'')+'" style="background:'+TCOL[t]+'"></span>'
          ).join('') + '</td>';
    }
    html += '</tr>';
  }
  heat.innerHTML = html;
}
sel.onchange = renderHeat;

// file table
function typeBadge(t) {
  return '<span class="badge" style="background:'+(TCOL[t]||'#8b949e')+'22;color:'+(TCOL[t]||'#8b949e')+'">'
    +(TLAB[t]||t)+'</span>';
}
function renderFiles() {
  const q = $('s-search').value.trim().toLowerCase();
  const rows = DATA.papers.filter(p =>
    !q || (p.subject+' '+p.unit+' '+p.session+' '+p.year+' '+p.type+' '+p.path).toLowerCase().includes(q));
  const body = $('f-body');
  body.innerHTML = rows.map(p =>
    '<tr><td class="mono">'+esc(p.path.split('/').pop())+'</td>'
    +'<td>'+esc(p.unit)+'</td><td>'+esc(p.session+' '+p.year)+'</td>'
    +'<td>'+typeBadge(p.type)+'</td><td class="sub">'+(p.size/1e6).toFixed(1)+' MB</td></tr>'
  ).join('');
  $('f-count').textContent = rows.length + ' files';
}
$('s-search').oninput = renderFiles;

// missing
const chips = $('missing-chips');
if (DATA.missing.length) {
  const seen = new Set();
  chips.innerHTML = DATA.missing.map(m => {
    const key = m.unit+'_'+m.year+'_'+m.type;
    if (seen.has(key)) return '';
    seen.add(key);
    return '<span class="mchip">'+esc(m.unit)+' · '+m.year+' · '+(TLAB[m.type]||m.type)+'</span>';
  }).join('');
} else {
  $('sec-missing').style.display = 'none';
}

renderHeat();
renderFiles();
</script>
</body>
</html>
"""


def render(root, out_path="dashboard.html"):
    data = build_data(root)
    page = (PAGE
            .replace("__GEN__", data["generated"])
            .replace("__ROOT__", _esc(data["root"]))
            .replace("__DATA__", json.dumps(data))
            .replace("__TCOL__", json.dumps(TYPE_COLORS))
            .replace("__TLAB__", json.dumps(TYPE_LABELS)))
    with open(out_path, "w") as f:
        f.write(page)
    return out_path, data


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "papers"
    path, data = render(root)
    print(f"dashboard -> {path}")
    print(f"papers: {data['kpi']['files']} files, "
          f"{data['kpi']['size_mb']} MB, "
          f"{len(data['subjects'])} subjects")
