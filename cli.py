#!/usr/bin/env python3
"""CLI for ial-papers: discover and bulk-download IAL past papers.

Commands:
  subjects                      list IAL subjects with document counts
  units SUBJECT                 list units (codes + labels) for a subject
  papers --subject X ...        list matching papers (no download)
  download --subject X ...      download matching papers
  sync                          download anything in the catalogue we don't have
"""

import argparse
import os
import sys
import webbrowser

import ial
from downloader import download_many, save_manifest, load_manifest

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papers")
DEFAULT_TYPES = ["qp", "ms"]


def type_names(args):
    types = getattr(args, "types", None)
    if not types:
        return None
    out = []
    for t in types:
        variants = ial.doc_type_variants(t)
        out.extend(variants or [t])
    return out


def session_names(args):
    return getattr(args, "sessions", None) or None


def load_catalogue(args):
    """Fetch papers from the index with the common CLI filters applied."""
    doc_types = type_names(args)
    exam_series = None
    if getattr(args, "years", None):
        ys = ial.parse_year_spec(args.years)
        if getattr(args, "sessions", None):
            exam_series = []
            for s in session_names(args):
                for y in sorted(ys):
                    exam_series.append(f"{ial.expand_session(s)}-{y}")
    print(f"Querying Pearson index (subject={args.subject or 'all'}, "
          f"types={getattr(args, 'types', None) or 'all'}) ...", file=sys.stderr)
    papers = ial.fetch_all(doc_types=doc_types,
                           subjects=[args.subject] if args.subject else None,
                           exam_series=exam_series)
    papers = ial.filter_papers(papers, unit=getattr(args, "unit", None),
                               years=ial.parse_year_spec(args.years)
                               if getattr(args, "years", None) else None,
                               sessions=session_names(args),
                               types=getattr(args, "types", None))
    return papers


def cmd_subjects(args):
    counts = ial.subjects_with_counts(doc_types=type_names(args))
    print(f"{'SUBJECT':40s} DOCS")
    for name, count in counts.items():
        print(f"{name:40s} {count}")


def cmd_units(args):
    papers = ial.fetch_all(doc_types=type_names(args),
                           subjects=[args.subject])
    units = ial.list_units(papers)
    print(f"{'CODE':10s} {'LABEL':8s}  QP   MS   ER   OTHER   (subject: "
          f"{args.subject})")
    for code, u in sorted(units.items()):
        print(f"{code:10s} {u['label']:8s} {u['qp']:4d} {u['ms']:4d} "
              f"{u['er']:4d} {u['other']:4d}")


def cmd_stats(args):
    import dashboard
    data = dashboard.build_data(args.out or DEFAULT_OUT)
    k = data["kpi"]
    cat = data["catalogue"]

    def row(text):
        pad = max(1, 52 - len(text) - 2)
        return f"│  {text}" + " " * pad + "│"

    line = "─" * 52
    print(f"┌{line}┐")
    print(row("⚡ IAL PAPERS — LOCAL COLLECTION"))
    print(f"├{line}┤")
    print(row(f"PDFs on disk     : {k['files']:>6d}"))
    print(row(f"Total size       : {k['size_mb']:>8.1f} MB"))
    print(row(f"Subjects         : {k['subjects']:>6d}"))
    print(row(f"Units            : {k['units']:>6d}"))
    if cat["total"] >= cat["downloaded"]:
        cov = 100 * cat["downloaded"] / cat["total"]
        print(row(f"Catalogue cover  : {cov:>7.1f}%"))
        print(row(f"Awaiting publish : {len(data['missing']):>6d}"))
    else:
        print(row("Catalogue cover  : n/a (sync a subject first)"))
    print(f"├{line}┤")
    for t in ("qp", "ms", "er", "gb"):
        n = k["types"].get(t, 0)
        if n:
            print(row(f"{dashboard.TYPE_LABELS[t]:<18}: {n:>5d}"))
    print(f"└{line}┘")
    for s in data["subjects"]:
        held = sum(1 for p in data["papers"] if p["subject"] == s)
        total = cat["per_subject"].get(s, held)
        units = len(set(p["unit"] for p in data["papers"] if p["subject"] == s))
        pct = 100 * held / total if total else 0
        print(f"  {s:<20s} {held:>4d}/{total:<4d} ({pct:5.1f}%)  units: {units}")


def cmd_dashboard(args):
    import dashboard
    root = args.out or DEFAULT_OUT
    path, data = dashboard.render(root, out_path=os.path.join(root, "dashboard.html"))
    print(f"dashboard -> {os.path.abspath(path)}")
    print(f"  {data['kpi']['files']} papers · {data['kpi']['size_mb']} MB · "
          f"{len(data['subjects'])} subjects")
    if args.open:
        webbrowser.open("file://" + os.path.abspath(path))


def cmd_papers(args):
    papers = load_catalogue(args)
    for p in papers:
        print(f"{p.rel_dir:60s}  {p.out_name}")
    print(f"\n{len(papers)} papers matched", file=sys.stderr)


def cmd_download(args):
    papers = load_catalogue(args)
    print(f"{len(papers)} papers matched", file=sys.stderr)
    if not papers:
        return
    out = args.out or DEFAULT_OUT
    if args.dry_run:
        for p in papers[:args.limit or 10]:
            print(f"  [dry-run] {p.rel_dir}/{p.out_name}")
        print(f"  ... ({len(papers)} total)", file=sys.stderr)
        return
    summary, failures = download_many(papers, out, workers=args.workers,
                                      force=args.force, limit=args.limit)
    save_manifest(papers, out)
    print(f"\nDone: {summary['downloaded']} downloaded, "
          f"{summary['skipped']} skipped, {summary['failed']} failed "
          f"-> {out}")
    for path, reason in failures[:20]:
        print(f"  FAILED {path}: {reason}", file=sys.stderr)


def cmd_sync(args):
    """Fetch the full catalogue for a subject and grab anything missing."""
    papers = ial.fetch_all(doc_types=type_names(args),
                           subjects=[args.subject] if args.subject else None)
    papers = ial.filter_papers(papers, unit=getattr(args, "unit", None),
                               years=ial.parse_year_spec(args.years)
                               if getattr(args, "years", None) else None,
                               sessions=session_names(args),
                               types=getattr(args, "types", None))
    out = args.out or DEFAULT_OUT
    # only try files we don't already have (cheap local check)
    todo = [p for p in papers
            if not os.path.exists(os.path.join(out, p.rel_dir, p.out_name))]
    print(f"Catalogue: {len(papers)} papers, {len(todo)} missing locally",
          file=sys.stderr)
    if args.dry_run:
        for p in todo[:20]:
            print(f"  [dry-run] {p.rel_dir}/{p.out_name}")
        return
    summary, failures = download_many(todo, out, workers=args.workers,
                                      force=args.force)
    save_manifest(papers, out)
    print(f"\nDone: {summary['downloaded']} downloaded, "
          f"{summary['skipped']} skipped, {summary['failed']} failed "
          f"-> {out}")
    for path, reason in failures[:20]:
        print(f"  FAILED {path}: {reason}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_filters(p):
        p.add_argument("--subject", help="e.g. Mathematics, Physics, Chemistry")
        p.add_argument("--unit", help="unit code or label, e.g. WMA11 or P1")
        p.add_argument("--years", help="e.g. 2024 or 2022-2025 or 2019,2021")
        p.add_argument("--sessions", nargs="+",
                       help="e.g. Jan Jun Oct (IAL sessions: January/June/October)")
        p.add_argument("--types", nargs="+",
                       default=["qp", "ms"],
                       help="qp ms er gb ... (default: qp ms)")

    p = sub.add_parser("subjects", help="list IAL subjects")
    p.add_argument("--types", nargs="+", help="filter doc types")
    p.set_defaults(func=cmd_subjects)

    p = sub.add_parser("units", help="list units for a subject")
    p.add_argument("subject")
    p.add_argument("--types", nargs="+", default=["qp", "ms", "er"])
    p.set_defaults(func=cmd_units)

    p = sub.add_parser("papers", help="list matching papers")
    add_filters(p)
    p.set_defaults(func=cmd_papers)

    p = sub.add_parser("download", help="download matching papers")
    add_filters(p)
    p.add_argument("--out", help="output root (default: ./papers)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true",
                   help="re-download even if file exists")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, help="max downloads (testing)")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("sync", help="fetch catalogue, download missing files")
    p.add_argument("--subject")
    p.add_argument("--unit")
    p.add_argument("--years")
    p.add_argument("--sessions", nargs="+")
    p.add_argument("--types", nargs="+", default=["qp", "ms"])
    p.add_argument("--out")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("stats", help="show what's on disk")
    p.add_argument("--out")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("dashboard", help="generate dashboard.html from a papers tree")
    p.add_argument("--out", help="papers root (default: ./papers)")
    p.add_argument("--open", action="store_true", help="open in browser after generating")
    p.set_defaults(func=cmd_dashboard)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
