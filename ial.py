"""ial-papers: Edexcel IAL papers, specifications and exam dates from Pearson.

Talks to Pearson's public Algolia search index (the same one their past-papers
page uses in the browser) to discover every IAL document, then downloads the
PDFs straight from qualifications.pearson.com's DAM. Specifications come from the
same index. Exam timetables are published as xlsx files on Pearson's timetable
page, so those are read with zipfile and ElementTree rather than a library.

Stdlib-only. Usage examples:

    python3 cli.py subjects
    python3 cli.py units Mathematics
    python3 cli.py download --subject Mathematics --unit WMA11 --years 2022-2025
    python3 cli.py spec Biology --download
    python3 cli.py dates WBI14 WBI15 --series summer-2027
    python3 cli.py sync

Output tree:

    papers/Mathematics/WMA11-P1/Jan 2024/WMA11-P1_Jan2024_qp.pdf
    papers/Biology/_Specification/IAL-Biology-Specification-2018.pdf
    papers/manifest.json
"""

import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

APP_ID = "L639T95U5A"
API_KEY = "f79c7a8352e9ffbdaec387bf43612ee6"
INDEX = "qualifications-uk_LIVE_master-content"
ALGOLIA_HOST = f"{APP_ID}-dsn.algolia.net"
DOWNLOAD_BASE = "https://qualifications.pearson.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

FAMILY = "International-Advanced-Level"

TYPE_SHORT = {
    "Question-paper": "qp",
    "Mark-scheme": "ms",
    "Examiner-report": "er",
    "Grade-boundaries": "gb",
    "Pre-release-material": "pr",
    "Listening-Examinations-MP3": "mp3",
    "Scientific-article": "sa",
    "Advance-information-and-Pre-release-material": "ai",
    "Specification": "spec",
    "Specification-addendum": "spec-add",
}

# Pearson's index is inconsistent about casing ("Mark-scheme" vs "Mark-Scheme").
_TYPE_SHORT_CI = {k.lower(): v for k, v in TYPE_SHORT.items()}


def doc_type_variants(short):
    """All index spellings for a short type code, e.g. ms ->
    ['Mark-scheme', 'Mark-Scheme'] for use in facet filters."""
    return [k for k, v in TYPE_SHORT.items() if v == short]

# Known IAL unit codes -> common labels (maths + fallback list). Anything not
# here still works; the label is parsed from the document title instead.
UNIT_LABELS = {
    "WMA11": "P1", "WMA12": "P2", "WMA13": "P3", "WMA14": "P4",
    "WST01": "S1", "WST02": "S2", "WST03": "S3",
    "WME01": "M1", "WME02": "M2", "WME03": "M3",
    "WFM01": "FP1", "WFM02": "FP2", "WFM03": "FP3",
    "WDM11": "D1", "WDM12": "D2",
    "WPH11": "U1", "WPH12": "U2", "WPH13": "U3",
    "WPH14": "U4", "WPH15": "U5", "WPH16": "U6",
    "WCH11": "U1", "WCH12": "U2", "WCH13": "U3",
    "WCH14": "U4", "WCH15": "U5", "WCH16": "U6",
    "WBI11": "U1", "WBI12": "U2", "WBI13": "U3",
    "WBI14": "U4", "WBI15": "U5", "WBI16": "U6",
    "WEC11": "U1", "WEC12": "U2", "WEC13": "U3", "WEC14": "U4",
    "WBS11": "U1", "WBS12": "U2", "WBS13": "U3", "WBS14": "U4",
    "WAC11": "U1", "WAC12": "U2",
}

# Current (2018+) IAL specification unit codes. Anything not listed here
# (WPH01…, PH01…, C1, S1, WMA01, …) is the retired/legacy syllabus.
NEW_SPEC_UNITS = {
    "WPH11", "WPH12", "WPH13", "WPH14", "WPH15", "WPH16",
    "WCH11", "WCH12", "WCH13", "WCH14", "WCH15", "WCH16",
    "WBI11", "WBI12", "WBI13", "WBI14", "WBI15", "WBI16",
    "WMA11", "WMA12", "WMA13", "WMA14",
    "WST01", "WST02", "WST03",
    "WME01", "WME02", "WME03",
    "WFM01", "WFM02", "WFM03",
    "WDM11",
    "WEC11", "WEC12", "WEC13", "WEC14",
    "WBS11", "WBS12", "WBS13", "WBS14",
    "WAC11", "WAC12",
}


def is_new_spec(code):
    """True if a unit code belongs to the current (2018+) IAL spec."""
    return code in NEW_SPEC_UNITS

SESSION_SHORT = {
    "January": "Jan", "February": "Feb", "March": "Mar", "May": "May",
    "June": "Jun", "Summer": "Jun", "October": "Oct", "November": "Nov",
}

SESSION_FULL = {v.lower(): k for k, v in SESSION_SHORT.items()}


def expand_session(name):
    """'Jan' -> 'January'; 'June' -> 'June'."""
    n = name.strip().lower()
    return SESSION_FULL.get(n, name.strip().title())

_UNIT_CODE_RE = re.compile(r"([A-Z]{2,4}\d{2,4})[-_/ ]?(\d{2})([a-z])?", re.IGNORECASE)
_UNIT_LABEL_RE = re.compile(r"\b((?:FP|P|S|M|D|C)\d)\b", re.IGNORECASE)
_SCIENCE_PREFIXES = ("WPH", "WCH", "WBI", "PH", "CH", "BI")


def _derive_unit_label(code):
    """Conventional label for IAL science units, e.g. WPH14 -> U4,
    PH01 -> U1. Returns '' if the code isn't a known science unit."""
    if not code:
        return ""
    m = re.match(r"([A-Z]{2,3})(\d)(\d)$", code)
    if m and m.group(1).upper() in _SCIENCE_PREFIXES:
        return f"U{m.group(3)}"
    return ""


class Paper:
    """One downloadable IAL document."""

    def __init__(self, url, title, categories):
        self.url = url
        self.title = title
        facets = {}
        for c in categories or []:
            if c.startswith("Pearson-UK:"):
                rest = c[len("Pearson-UK:"):]
                key, _, val = rest.partition("/")
                facets.setdefault("Pearson-UK:" + key, []).append(val)
        self.facets = facets

        self.subject = facets.get("Pearson-UK:Qualification-Subject", [""])[0]
        self.doc_type = facets.get("Pearson-UK:Document-Type", [""])[0]
        self.secure = facets.get("Pearson-UK:secure-content", [""])[0]

        self.session, self.year = self._parse_series(
            facets.get("Pearson-UK:Exam-Series", [""])[0])

        basename = url.rstrip("/").split("/")[-1]
        self.file_basename = basename
        self.unit_code, self.unit_label, self.variant = self._parse_unit(
            basename, title)

    @staticmethod
    def _parse_series(series):
        # "January-2019" -> ("January", 2019)
        m = re.match(r"([A-Za-z]+)-?(\d{4})", series or "")
        if m:
            return m.group(1), int(m.group(2))
        return "", 0

    @staticmethod
    def _parse_unit(basename, title):
        m = _UNIT_CODE_RE.search(basename)
        code = m.group(1).upper() if m else ""
        variant = (m.group(3) or "").upper() if m else ""
        # try a label in the title first ("Pure Mathematics P1")
        lm = _UNIT_LABEL_RE.search(title)
        label = lm.group(1).upper() if lm else ""
        if not label:
            label = UNIT_LABELS.get(code, "")
        if not label:
            label = _derive_unit_label(code)
        if not label and m:
            label = m.group(2)
        return code, label, variant

    @property
    def type_short(self):
        return _TYPE_SHORT_CI.get(self.doc_type.lower(), "doc")

    @property
    def session_short(self):
        return SESSION_SHORT.get(self.session, self.session[:3].title() or "X")

    @property
    def rel_dir(self):
        """Relative folder inside the papers root."""
        if self.type_short == "gb":
            return f"Grade-boundaries/{self.session_short} {self.year}"
        unit = f"{self.unit_code}-{self.unit_label}" if self.unit_code else "other"
        subject = self.subject or "Other"
        return f"{subject}/{unit}/{self.session_short} {self.year}"

    @property
    def out_name(self):
        """Normalised filename, e.g. WMA11-P1_Jan2024_qp.pdf"""
        stem = self.file_basename.rsplit(".", 1)[0]
        ext = self.file_basename.rsplit(".", 1)[-1]
        bits = [b for b in [self.unit_code, self.unit_label] if b]
        code = "-".join(bits) if bits else stem
        if self.variant and not code.lower().endswith(self.variant.lower()):
            code += self.variant
        return f"{code}_{self.session_short}{self.year}_{self.type_short}.{ext}"

    @property
    def download_url(self):
        return DOWNLOAD_BASE + urllib.parse.quote(self.url, safe="/-_.%")

    def to_dict(self):
        return {
            "url": self.url,
            "title": self.title,
            "subject": self.subject,
            "type": self.doc_type,
            "session": self.session,
            "year": self.year,
            "unit": self.unit_code,
            "label": self.unit_label,
        }


def _algolia(endpoint, body, timeout=60):
    """POST to Algolia, return parsed JSON."""
    req = urllib.request.Request(
        f"https://{ALGOLIA_HOST}/1/indexes/{INDEX}/{endpoint}",
        data=json.dumps(body).encode(),
        headers={
            "X-Algolia-API-Key": API_KEY,
            "X-Algolia-Application-Id": APP_ID,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _family_filter():
    return f"category:Pearson-UK:Qualification-Family/{FAMILY}"


def fetch_all(doc_types=None, subjects=None, exam_series=None, max_hits=None,
              extra_filters=None):
    """Browse the whole index (no 1000-hit page cap) and return Paper list."""
    groups = []
    groups.append([_family_filter()])
    if doc_types:
        groups.append([f"category:Pearson-UK:Document-Type/{t}" for t in doc_types])
    if subjects:
        groups.append([f"category:Pearson-UK:Qualification-Subject/{s}"
                       for s in subjects])
    if exam_series:
        groups.append([f"category:Pearson-UK:Exam-Series/{s}" for s in exam_series])
    if extra_filters:
        groups.extend(extra_filters)
    facet_filters = [g for g in groups if g]

    body = {
        "attributesToRetrieve": ["url", "title", "category"],
        "hitsPerPage": 1000,
    }
    if facet_filters:
        body["facetFilters"] = facet_filters

    papers, seen, cursor = [], set(), None
    while True:
        b = dict(body)
        if cursor:
            b["cursor"] = cursor
        data = _algolia("browse", b)
        for hit in data.get("hits", []):
            u = hit.get("url", "")
            if not u or u in seen:
                continue
            seen.add(u)
            papers.append(Paper(u, hit.get("title", ""), hit.get("category", [])))
            if max_hits and len(papers) >= max_hits:
                return papers
        cursor = data.get("cursor")
        if not cursor:
            break
    return papers


def subjects_with_counts(doc_types=None):
    """Facet counts for Qualification-Subject inside IAL."""
    body = {
        "hitsPerPage": 0,
        "facetFilters": [[_family_filter()]]
        + ([[f"category:Pearson-UK:Document-Type/{t}" for t in doc_types]]
           if doc_types else []),
        "facets": ["category"],
        "maxValuesPerFacet": 500,
    }
    data = _algolia("query", body)
    out = {}
    for name, count in data.get("facets", {}).get("category", {}).items():
        if name.startswith("Pearson-UK:Qualification-Subject/"):
            out[name.rsplit("/", 1)[-1]] = count
    return dict(sorted(out.items()))


# Pearson's IAL index carries language qualifications and retired variants of
# subjects we already have. Left alone, the subject dropdown offers Biology,
# Biology-A, Biology-B, Biology-(Human) and Biology-A-(Salters-Nuffield), four of
# which have almost nothing behind them. One entry per real subject is the point.
LANGUAGE_SUBJECTS = {
    "Arabic", "Arabic-as-a-first-language", "Bangla", "Chinese", "French",
    "German", "Greek", "Greek-as-a-first-language", "Gujarati", "Italian",
    "Japanese", "Persian", "Portuguese", "Russian", "Sinhala", "Spanish",
    "Swahili", "Tamil", "Turkish", "Urdu",
    "English-(as-2nd-language)", "English-as-a-Second-Language-(ESL)",
}

# Variants that do not strip down to a base name on their own.
SUBJECT_ALIASES = {"Business-Studies": "Business"}


def root_subject(name):
    """Chase -A, -B and -(Bracketed) suffixes back to the base subject name.

    Biology-A-(Salters-Nuffield) -> Biology-A -> Biology. A name ending in a
    multi letter tag such as Applied-ICT is left alone.
    """
    n = name or ""
    while True:
        stripped = re.sub(r"-\([^)]*\)$", "", n)
        if stripped == n:
            stripped = re.sub(r"-[A-Z]$", "", n)
        if stripped == n:
            return n
        n = stripped


def subject_menu():
    """Subjects worth showing, mapped to how many question papers each has.

    Variants are merged into their base and languages are dropped. A subject stays
    if it has question papers or a specification, so a brand new spec (Computer
    Science 2026) is still reachable. News feeds and update pages drop out.
    """
    papers = subjects_with_counts(doc_types=["Question-paper"])
    specs = subjects_with_counts(doc_types=["Specification",
                                            "Specification-addendum"])
    totals = subjects_with_counts()

    def resolve(name):
        root = root_subject(name)
        return SUBJECT_ALIASES.get(root, root)

    def merged_counts(source):
        out = {}
        for name, n in source.items():
            key = resolve(name)
            if key in LANGUAGE_SUBJECTS:
                continue
            out[key] = out.get(key, 0) + n
        return out

    paper_counts = merged_counts(papers)
    present = set(paper_counts) | set(merged_counts(specs))
    # Keep only roots that exist as a subject in their own right. Biology-(Human)
    # merges into Biology because Biology is there. A stray root with no base is not.
    known = {resolve(n) for n in totals}
    return dict(sorted((k, paper_counts.get(k, 0)) for k in present if k in known))


def list_units(papers):
    """Group papers by unit code -> (label, subject, n_qp, n_ms, n_er)."""
    units = {}
    for p in papers:
        key = p.unit_code or "(other)"
        u = units.setdefault(key, {"label": p.unit_label, "subject": p.subject,
                                   "qp": 0, "ms": 0, "er": 0, "other": 0})
        u.setdefault(p.type_short, 0)
        u[p.type_short] += 1
    return units


def filter_papers(papers, unit=None, years=None, sessions=None, types=None):
    """Client-side filtering. `unit` may be a single code/label or a list
    of them (case-insensitive)."""
    unit_list = unit if isinstance(unit, (list, tuple, set)) else ([unit] if unit else None)
    if unit_list:
        unit_set = {u.lower() for u in unit_list}
    out = []
    for p in papers:
        if unit_list:
            if not (p.unit_code.lower() in unit_set or p.unit_label.lower() in unit_set):
                continue
        if years and p.year not in years:
            continue
        if sessions:
            s_ok = False
            for s in sessions:
                s = s.lower()
                if (p.session.lower() == s
                        or p.session_short.lower() == s
                        or p.session.lower().startswith(s)):
                    s_ok = True
                    break
            if not s_ok:
                continue
        if types and p.type_short not in types:
            continue
        out.append(p)
    return out


# ------------------------- specifications -------------------------

# Pearson files a few things under "Specification" that are not the spec itself:
# errata, cover letters, appendices, the old paper syllabus. They are still
# returned, ranked last, so the plain spec wins the default pick.
_SPEC_ODD_RE = re.compile(
    r"erratum|cover letter|prescribed text|appendix|qualification outline"
    r"|syllabus|poem|addendum", re.I)
_SPEC_VERSION_RE = re.compile(r"/(\d{4})/")
_SPEC_ISSUE_RE = re.compile(r"(?:issue|iss)\s*[-_ ]?(\d+)", re.I)


def spec_docs(subject=None):
    """Specification PDFs, best first. Specs have no unit code and no exam
    session, which is why they never go through the paper pipeline."""
    types = (doc_type_variants("spec") or ["Specification"]) + \
            (doc_type_variants("spec-add") or ["Specification-addendum"])
    out = []
    for d in fetch_all(doc_types=types, subjects=[subject] if subject else None):
        if d.type_short not in ("spec", "spec-add"):
            continue
        version = 0
        m = _SPEC_VERSION_RE.search(d.url or "")
        if m:
            version = int(m.group(1))
        issue = 0
        hay = "%s %s" % (d.title or "", (d.url or "").rsplit("/", 1)[-1])
        im = _SPEC_ISSUE_RE.search(hay)
        if im:
            issue = int(im.group(1))
        out.append({
            "title": d.title or "Specification",
            "url": d.url or "",
            "kind": d.type_short,
            "version": version,
            "issue": issue,
            "odd": bool(_SPEC_ODD_RE.search(d.title or "")),
        })
    out.sort(key=lambda x: (x["odd"], x["kind"] != "spec",
                            -x["version"], -x["issue"]))
    return out


def spec_filename(subject, doc):
    """Deterministic name, so asking twice is a no-op rather than a duplicate."""
    bits = ["IAL", (subject or "Subject").replace(" ", "-"), "Specification"]
    if doc.get("version"):
        bits.append(str(doc["version"]))
    if doc.get("issue"):
        bits.append("issue%d" % doc["issue"])
    return "-".join(bits) + ".pdf"


# ------------------------- exam timetables -------------------------

TIMETABLE_PAGE = ("https://qualifications.pearson.com/en/support/"
                  "support-topics/exams/exam-timetables.html")
_SERIES_DIR = "Examination-timetables-for-International-Advanced-Levels"
_SERIES_MONTH = {"january": 1, "february": 2, "march": 3, "spring": 4,
                 "summer": 6, "june": 6, "october": 10, "november": 11}
_EXCEL_EPOCH = date(1899, 12, 30)
_SS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _excel_date(value):
    """Excel stores dates as days since 1899-12-30."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ""
    if not (30000 < n < 80000):
        return ""
    return (_EXCEL_EPOCH + timedelta(days=int(n))).isoformat()


def _sheet_target(z, sheet_name):
    wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
    targets = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    for name, rid in re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wb):
        if name == sheet_name:
            t = targets.get(rid, "")
            return t if t.startswith("xl/") else "xl/" + t.lstrip("/")
    return ""


def parse_timetable(data, sheet_name="All papers"):
    """Rows of a Pearson timetable xlsx as dicts keyed by the header names.

    An xlsx is a zip of xml, so zipfile and ElementTree do the whole job with no
    dependency. Pearson put one sheet called "All papers" in these files with the
    date, the examination code and the sitting time, which is all the planner needs.
    """
    z = zipfile.ZipFile(io.BytesIO(data))
    target = _sheet_target(z, sheet_name)
    if not target:
        return []
    try:
        shared = ["".join(t.text or "" for t in si.iter(_SS + "t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_SS + "si")]
    except KeyError:
        shared = []

    rows, header = [], None
    for row in ET.fromstring(z.read(target)).iter(_SS + "row"):
        cells = {}
        for c in row.iter(_SS + "c"):
            ref = c.get("r") or ""
            m = re.match(r"[A-Z]+", ref)
            if not m:
                continue
            kind, v, inline = c.get("t"), c.find(_SS + "v"), c.find(_SS + "is")
            if kind == "s" and v is not None:
                val = shared[int(v.text)]
            elif kind == "inlineStr" and inline is not None:
                val = "".join(t.text or "" for t in inline.iter(_SS + "t"))
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            cells[m.group(0)] = val.strip()
        if not cells:
            continue
        if header is None:
            if "Date" in cells.values():
                header = cells
            continue
        rows.append({header[k]: v for k, v in cells.items() if k in header})
    for r in rows:
        r["Date"] = _excel_date(r.get("Date"))
    return rows


def timetable_series():
    """The IAL final timetables Pearson publishes, oldest series first."""
    html = _fetch(TIMETABLE_PAGE).decode("utf-8", "replace")
    pattern = r"/content/dam/pdf/Support/%s/([A-Za-z0-9._-]+\.xlsx)" % _SERIES_DIR
    out, seen = [], set()
    for fn in re.findall(pattern, html):
        m = re.match(r"ial-([a-z]+)-?(\d{4})-final", fn, re.I)
        if not m or fn in seen:
            continue
        seen.add(fn)
        word = m.group(1).lower()
        out.append({
            "file": fn,
            "label": "%s %s" % (word.title(), m.group(2)),
            "month": _SERIES_MONTH.get(word, 0),
            "year": int(m.group(2)),
            "url": "%s/content/dam/pdf/Support/%s/%s" % (DOWNLOAD_BASE, _SERIES_DIR, fn),
        })
    out.sort(key=lambda s: (s["year"], s["month"], s["label"]))
    return out


def exam_dates(units, url):
    """Exam sittings for the given unit codes in one series, in date order."""
    want = {u.upper() for u in units if u}
    out = []
    for row in parse_timetable(_fetch(url)):
        code = (row.get("Examination code") or "").upper().strip()
        unit = code.split()[0] if code else ""
        if not unit or not row.get("Date"):
            continue  # section headers and blank filler rows
        if want and unit not in want:
            continue
        out.append({
            "unit": unit,
            "subject": row.get("Subject") or "",
            "title": row.get("Title") or "",
            "date": row.get("Date") or "",
            "time": row.get("Time") or "",
            "duration": row.get("Duration") or "",
        })
    out.sort(key=lambda e: (e["date"], e["unit"]))
    return out


def parse_year_spec(spec):
    """'2022-2025' or '2024' or '2019,2021' -> set of ints."""
    years = set()
    for part in str(spec).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            years.update(range(int(a), int(b) + 1))
        elif part:
            years.add(int(part))
    return years or None
