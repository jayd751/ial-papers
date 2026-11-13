"""Parallel downloader with resume, retry and PDF validation."""

import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request

from ial import Paper, USER_AGENT

PDF_MAGIC = b"%PDF"
FAILURES_FILE = "failures.json"
RETRY_DAYS = 7  # don't retry known-bad URLs for a week

_TTY = sys.stdout.isatty()
_G, _R, _Y, _C, _D, _B = ("\033[32m", "\033[31m", "\033[33m", "\033[36m",
                          "\033[2m", "\033[1m") if _TTY else ("",) * 6
_X = "\033[0m" if _TTY else ""
BAR_W = 30


def _bar(done, total):
    frac = done / total if total else 1
    fill = int(BAR_W * frac)
    return "█" * fill + "░" * (BAR_W - fill)


def _load_failures(dest_root):
    try:
        with open(os.path.join(dest_root, FAILURES_FILE)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_failures(dest_root, failures):
    with open(os.path.join(dest_root, FAILURES_FILE), "w") as f:
        json.dump(failures, f, indent=2)


def _is_valid_pdf(path):
    try:
        with open(path, "rb") as f:
            return f.read(8).startswith(PDF_MAGIC)
    except OSError:
        return False


def download_one(paper: Paper, dest_root: str, force=False, timeout=90,
                 retries=3):
    """Download a single paper. Returns (status, path, reason).

    status: 'downloaded' | 'skipped' | 'failed'
    """
    dest_dir = os.path.join(dest_root, paper.rel_dir)
    dest = os.path.join(dest_dir, paper.out_name)
    os.makedirs(dest_dir, exist_ok=True)

    if not force and os.path.exists(dest) and os.path.getsize(dest) > 0:
        return ("skipped", dest, "exists")

    tmp = dest + ".part"
    if os.path.exists(tmp):
        os.remove(tmp)

    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(paper.download_url,
                                         headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r, \
                    open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            if _is_valid_pdf(tmp):
                os.replace(tmp, dest)
                return ("downloaded", dest, f"{os.path.getsize(dest)} bytes")
            last_err = "not a PDF (locked or HTML error page)"
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < retries:
            time.sleep(2 * attempt)
    if os.path.exists(tmp):
        os.remove(tmp)
    return ("failed", dest, last_err)


def _paper_rel(p):
    return os.path.join(p.rel_dir, p.out_name).replace(os.sep, "/")


def download_many(papers, dest_root, workers=4, force=False, quiet=False,
                  limit=None, on_progress=None, force_keys=None):
    """Download a list of papers concurrently. Returns summary dict.

    on_progress, if given, is called after each item completes with
    (done, total, summary, failures).

    force_keys, if given, is a set of relative paths (as produced by
    _paper_rel) that should be re-downloaded even if the file already
    exists on disk.
    """
    todo = papers[:limit] if limit else papers
    summary = {"total": len(todo), "downloaded": 0, "skipped": 0, "failed": 0}
    failures = []

    if not todo:
        return summary, failures

    os.makedirs(dest_root, exist_ok=True)
    known_bad = {} if force else _load_failures(dest_root)
    now = time.time()
    fresh_bad = {u for u, ts in known_bad.items()
                 if now - ts < RETRY_DAYS * 86400}
    attempts, skipped_bad = [], 0
    for p in todo:
        if p.download_url in fresh_bad:
            skipped_bad += 1
        else:
            attempts.append(p)
    summary["skipped"] += skipped_bad

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        for p in attempts:
            pf = force or (force_keys is not None and _paper_rel(p) in force_keys)
            futs[ex.submit(download_one, p, dest_root, pf)] = p
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            status, path, reason = fut.result()
            summary[status] += 1
            if status == "failed":
                failures.append((path, reason))
                known_bad[futs[fut].download_url] = now
            done += 1
            if on_progress:
                on_progress(done, len(futs), summary, failures)
            if not quiet and (done % 5 == 0 or done == len(futs)):
                print(f"\r  {_C}{_bar(done, len(futs))}{_X} "
                      f"{done}/{len(futs)}  "
                      f"{_G}ok={summary['downloaded']}{_X} "
                      f"{_Y}skip={summary['skipped']}{_X} "
                      f"{_R}fail={summary['failed']}{_X}   ",
                      end="", flush=True)
    if not quiet:
        print()
    _save_failures(dest_root, known_bad)
    return summary, failures


def save_manifest(papers, dest_root, path="manifest.json"):
    """Persist the full catalogue + known download paths."""
    data = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(papers),
        "papers": [p.to_dict() for p in papers],
    }
    with open(os.path.join(dest_root, path), "w") as f:
        json.dump(data, f, indent=2)


def load_manifest(dest_root, path="manifest.json"):
    mpath = os.path.join(dest_root, path)
    if not os.path.exists(mpath):
        return None
    with open(mpath) as f:
        return json.load(f)
