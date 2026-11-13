"""ial-papers: bulk-download Edexcel IAL past papers + mark schemes from Pearson.

Talks to Pearson's public Algolia search index (the same one their past-papers
page uses in the browser) to discover every IAL document, then downloads the
PDFs straight from qualifications.pearson.com's DAM.

Stdlib-only. Usage examples:

    python3 cli.py subjects
    python3 cli.py units Mathematics
    python3 cli.py download --subject Mathematics --unit WMA11 --years 2022-2025
    python3 cli.py sync

Output tree:

    papers/Mathematics/WMA11-P1/Jan 2024/WMA11-P1_Jan2024_qp.pdf
    papers/manifest.json
"""

import json
import re
import urllib.parse
import urllib.request

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
