"""Ingest Chase Prime 5144 statement PDFs (and optional charge CSVs).

Statement stages (bracket tag in the filename):
  [] or missing     → unreconciled (in review)
  [APPROVED …]      → all charges approved + QIF exported (not yet Quicken-reconciled)
  [REC JRS M-D-YY]  → reconciled in Quicken; hidden from the reviewer picker
"""

from __future__ import print_function

import os
import re
from datetime import datetime
from glob import glob

import pandas as pd

from amazon_cc.qif_io import parse_qif_amount

# Owner-shared reconciliation folder (source of truth for statement PDFs)
JRSS_RECONCILIATION_DIR = os.path.join(
    os.path.expanduser("~"),
    "OneDrive",
    "JRSS Reconciliation",
)
STATEMENTS_DIR = os.path.join(JRSS_RECONCILIATION_DIR, "CC Chase Prime 5144")
# Shared handoff folder for Quicken import (OneDrive sync)
QIF_DIR = os.path.join(JRSS_RECONCILIATION_DIR, "QIF files")
# Legacy nested copy under the repo (fallback only)
LEGACY_STATEMENTS_DIR = os.path.join(
    "amazon", "CC Chase Prime 5144", "CC Chase Prime 5144"
)
LEGACY_QIF_DIR = "qif_files"
QIF_RECONCILE_SUFFIX = "_reconcile"

REC_TAG = "REC"
APPROVED_TAG = "APPROVED"
RECONCILER_INITIALS = "JRS"

_MONTH_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Year-first (current): Chase Prime 5144 2026 07 July15 [tag].pdf
# Legacy (month-first): Chase Prime 5144 07 July15 2026 [tag].pdf
_STATEMENT_NAME_RE = re.compile(
    r"(?i)Chase\s+Prime\s+5144\s+"
    r"(?:"
    r"(?P<year>\d{4})\s+(?P<num>\d{2})\s+(?P<mon>[A-Za-z]+)(?P<day>\d{1,2})"
    r"|"
    r"(?P<num_old>\d{2})\s+(?P<mon_old>[A-Za-z]+)(?P<day_old>\d{1,2})\s+(?P<year_old>\d{4})"
    r")"
)
# Chase online download: 20261117-statements-5144-.pdf (YYYYMMDD = statement date)
_CHASE_DOWNLOAD_RE = re.compile(
    r"(?i)^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})-statements-5144-?\.pdf$"
)
_BRACKET_RE = re.compile(r"\[([^\]]*)\]\s*$")

# Match existing archive spelling (April/June/July/Sept, not Apr/Jun/Jul/Sep).
_MONTH_CANONICAL = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "Aug",
    9: "Sept",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}
# Historical filenames use day 15 even when Chase stamps the PDF ~17th.
STATEMENT_FILENAME_DAY = 15
# Chase typically publishes the PDF around the 17th of the closing month.
STATEMENT_PUBLISH_DAY = 17


def match_chase_download_name(path_or_name):
    """
    Parse Chase online download basename YYYYMMDD-statements-5144-.pdf.
    Returns dict with year/month/day from the stamp, plus archive mon/day
    (filename day 15), or None.
    """
    base = os.path.basename(path_or_name)
    m = _CHASE_DOWNLOAD_RE.match(base)
    if not m:
        return None
    year = int(m.group("year"))
    month = int(m.group("month"))
    stamp_day = int(m.group("day"))
    if month < 1 or month > 12:
        return None
    mon = _MONTH_CANONICAL[month]
    return {
        "year": year,
        "num": month,
        "num_token": month,
        "mon": mon,
        "day": STATEMENT_FILENAME_DAY,
        "stamp_day": stamp_day,
        "source": "chase_download",
    }


def match_statement_name(path_or_name):
    """
    Parse Chase Prime 5144 statement basename fields.
    Returns dict with year, num (1-12 from month name when possible), mon, day,
    or None. Also accepts Chase download names (YYYYMMDD-statements-5144-.pdf).
    """
    core = statement_core_name(path_or_name)
    m = _STATEMENT_NAME_RE.search(core)
    if not m:
        return match_chase_download_name(path_or_name)
    if m.group("year"):
        year = int(m.group("year"))
        num_token = int(m.group("num"))
        mon = m.group("mon")
        day = int(m.group("day"))
    else:
        year = int(m.group("year_old"))
        num_token = int(m.group("num_old"))
        mon = m.group("mon_old")
        day = int(m.group("day_old"))
    mon_num = _MONTH_NUM.get(mon.lower()) or num_token
    return {
        "year": year,
        "num": mon_num,
        "num_token": num_token,
        "mon": mon,
        "day": day,
    }


def statement_display_label(path_or_name, include_stage=True):
    """
    Human label for dashboards/pickers, e.g. '2026 Sept 15 · review'.
    Avoids raw Chase download filenames.
    """
    parsed = match_statement_name(path_or_name)
    if parsed:
        label = "{} {} {}".format(parsed["year"], parsed["mon"], parsed["day"])
    else:
        label = statement_core_name(path_or_name) or os.path.basename(path_or_name)
    if not include_stage:
        return label
    stage = statement_stage(path_or_name)
    stage_label = {
        "unreconciled": "review",
        "approved": "import / reconcile",
        "reconciled": "done",
    }.get(stage, stage)
    return "{} · {}".format(label, stage_label)


def canonical_path_for_period(statements_dir, year, month, day=None, tag=""):
    """Build canonical PDF path for a statement period (empty tag → [])."""
    day = STATEMENT_FILENAME_DAY if day is None else day
    mon = _MONTH_CANONICAL.get(month) or "Mon"
    core = "Chase Prime 5144 {} {:02d} {}{}".format(year, month, mon, day)
    if tag is None:
        name = "{}.pdf".format(core)
    else:
        name = "{} [{}].pdf".format(core, tag)
    return os.path.join(statements_dir, name)


def _iter_statement_pdf_paths(statements_dir, include_downloads=True):
    """Yield PDF paths under statements_dir (non-recursive)."""
    if not os.path.isdir(statements_dir):
        return
    for name in os.listdir(statements_dir):
        if not name.lower().endswith(".pdf"):
            continue
        if not include_downloads and match_chase_download_name(name):
            continue
        yield os.path.join(statements_dir, name)


def find_statement_for_period(statements_dir, year, month, include_downloads=False):
    """Return existing PDF path for year/month (any stage), or None."""
    statements_dir = resolve_statements_dir(statements_dir)
    matches = []
    for path in _iter_statement_pdf_paths(
        statements_dir, include_downloads=include_downloads
    ):
        parsed = match_statement_name(path)
        if parsed and parsed["year"] == year and parsed["num"] == month:
            matches.append(path)

    def sort_key(p):
        # Prefer archived Chase Prime names over raw downloads
        download = 1 if match_chase_download_name(p) else 0
        period = parse_statement_period(p)
        return (download, period or datetime.max, os.path.basename(p).lower())

    matches.sort(key=sort_key)
    return matches[0] if matches else None


def normalize_downloaded_statements(statements_dir=None):
    """
    Rename Chase download PDFs to year-first archive names with [] tag.
    If that month already exists, leave the download in place and report it
    as a duplicate (caller can hide it from pickers).
    Returns dict with renamed, duplicates, errors lists.
    """
    statements_dir = resolve_statements_dir(statements_dir)
    result = {"renamed": [], "duplicates": [], "errors": [], "dir": statements_dir}
    if not os.path.isdir(statements_dir):
        return result
    for name in sorted(os.listdir(statements_dir)):
        parsed = match_chase_download_name(name)
        if not parsed:
            continue
        src = os.path.join(statements_dir, name)
        if not os.path.isfile(src):
            continue
        existing = find_statement_for_period(
            statements_dir, parsed["year"], parsed["num"], include_downloads=False
        )
        if existing:
            result["duplicates"].append(
                {
                    "download": src,
                    "existing": existing,
                    "period": datetime(parsed["year"], parsed["num"], parsed["day"]),
                }
            )
            continue
        dest = canonical_path_for_period(
            statements_dir, parsed["year"], parsed["num"], parsed["day"], tag=""
        )
        try:
            if os.path.exists(dest):
                result["duplicates"].append(
                    {
                        "download": src,
                        "existing": dest,
                        "period": datetime(parsed["year"], parsed["num"], parsed["day"]),
                    }
                )
                continue
            os.rename(src, dest)
            result["renamed"].append({"from": src, "to": dest})
        except OSError as exc:
            result["errors"].append("{}: {}".format(name, exc))
    return result


def resolve_statements_dir(preferred=None):
    """Prefer JRSS shared folder; fall back to repo-local copy if missing."""
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend([STATEMENTS_DIR, LEGACY_STATEMENTS_DIR])
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return preferred or STATEMENTS_DIR


def statement_core_name(path_or_name):
    """Basename without extension or trailing [bracket tag]."""
    base = os.path.splitext(os.path.basename(path_or_name))[0]
    return _BRACKET_RE.sub("", base).strip()


def canonical_statement_core_name(path_or_name):
    """
    Year-first core name for Explorer chronological sort, matching Schwab:
    Chase Prime 5144 YYYY MM MonthDay
    MM is taken from the month name (fixes misnumbered Aug/Sept files).
    """
    parsed = match_statement_name(path_or_name)
    if not parsed:
        return statement_core_name(path_or_name)
    return "Chase Prime 5144 {} {:02d} {}{}".format(
        parsed["year"], parsed["num"], parsed["mon"], parsed["day"]
    )


def statement_id_from_path(path):
    """
    Stable id across tag renames and year-first vs legacy month-first names.
    Canonical: Chase_Prime_5144_YYYY_MonthDay
    """
    parsed = match_statement_name(path)
    if parsed:
        return "Chase_Prime_5144_{}_{}{}".format(
            parsed["year"], parsed["mon"], parsed["day"]
        )
    core = statement_core_name(path)
    return re.sub(r"[^\w.\-]+", "_", core).strip("_") or "statement"


def legacy_statement_ids_from_path(path):
    """Older progress-file stems that may still exist on disk."""
    ids = []
    parsed = match_statement_name(path)
    if parsed:
        # Pre-canonical: Chase_Prime_5144_YYYY_MM_MonthDay (kept MM in id)
        ids.append(
            "Chase_Prime_5144_{}_{:02d}_{}{}".format(
                parsed["year"],
                parsed["num_token"],
                parsed["mon"],
                parsed["day"],
            )
        )
        if parsed["num_token"] != parsed["num"]:
            ids.append(
                "Chase_Prime_5144_{}_{:02d}_{}{}".format(
                    parsed["year"],
                    parsed["num"],
                    parsed["mon"],
                    parsed["day"],
                )
            )
        # Pre-year-first: Chase_Prime_5144_MM_MonthDay_YYYY
        ids.append(
            "Chase_Prime_5144_{:02d}_{}{}_{}".format(
                parsed["num_token"],
                parsed["mon"],
                parsed["day"],
                parsed["year"],
            )
        )
        if parsed["num_token"] != parsed["num"]:
            ids.append(
                "Chase_Prime_5144_{:02d}_{}{}_{}".format(
                    parsed["num"],
                    parsed["mon"],
                    parsed["day"],
                    parsed["year"],
                )
            )
        # Raw sanitized legacy/new cores
        legacy_core = "Chase Prime 5144 {:02d} {}{} {}".format(
            parsed["num_token"], parsed["mon"], parsed["day"], parsed["year"]
        )
        ids.append(re.sub(r"[^\w.\-]+", "_", legacy_core).strip("_"))
        ids.append(
            re.sub(r"[^\w.\-]+", "_", canonical_statement_core_name(path)).strip("_")
        )
    core = statement_core_name(path)
    ids.append(re.sub(r"[^\w.\-]+", "_", core).strip("_"))
    # Dedup preserve order
    out = []
    seen = set()
    for sid in ids:
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def bracket_tag(path_or_name):
    base = os.path.splitext(os.path.basename(path_or_name))[0]
    m = _BRACKET_RE.search(base)
    if not m:
        return ""
    return (m.group(1) or "").strip()


def statement_stage(path_or_name):
    """Return 'reconciled' | 'approved' | 'unreconciled' from filename tag."""
    tag = bracket_tag(path_or_name).upper()
    if tag.startswith(REC_TAG):
        return "reconciled"
    if tag.startswith(APPROVED_TAG):
        return "approved"
    return "unreconciled"


def parse_statement_period(path_or_name):
    """
    Closing/period date from filename (month name + day + year).
    Returns datetime or None. Prefer month name over the MM token
    (some files mis-number Aug/Sept as 07).
    """
    parsed = match_statement_name(path_or_name)
    if not parsed:
        return None
    try:
        return datetime(parsed["year"], parsed["num"], parsed["day"])
    except ValueError:
        return None


def format_rec_date(when=None):
    """Match existing REC tags: M-D-YY (unpadded)."""
    when = when or datetime.now()
    return "{}-{}-{}".format(when.month, when.day, when.strftime("%y"))


def approved_tag(when=None, initials=RECONCILER_INITIALS):
    return "{} {} {}".format(APPROVED_TAG, initials, format_rec_date(when))


def reconciled_tag(when=None, initials=RECONCILER_INITIALS):
    return "{} {} {}".format(REC_TAG, initials, format_rec_date(when))


def rename_statement_tag(path, new_tag):
    """
    Set/replace the trailing [tag] on a statement PDF. Returns new path.
    Also normalizes the core name to year-first (Schwab-style) form.
    """
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        raise RuntimeError("Statement file not found: {}".format(path))
    dirname = os.path.dirname(path)
    core = canonical_statement_core_name(path)
    new_name = "{} [{}].pdf".format(core, new_tag)
    new_path = os.path.join(dirname, new_name)
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(
        os.path.abspath(new_path)
    ):
        return path
    if os.path.exists(new_path):
        raise RuntimeError("Target already exists: {}".format(new_path))
    os.rename(path, new_path)
    return new_path


def rename_statement_year_first(path):
    """
    Rename a statement PDF to year-first core name; preserve [tag] and extension.
    Returns new path (or same path if already canonical).
    """
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        raise RuntimeError("Statement file not found: {}".format(path))
    dirname = os.path.dirname(path)
    _stem, ext = os.path.splitext(os.path.basename(path))
    ext = ext or ".pdf"
    tag = bracket_tag(path)
    core = canonical_statement_core_name(path)
    if tag:
        new_name = "{} [{}]{}".format(core, tag, ext)
    else:
        # Keep empty [] if the original used it
        base = os.path.splitext(os.path.basename(path))[0]
        if base.rstrip().endswith("[]"):
            new_name = "{} []{}".format(core, ext)
        else:
            new_name = "{}{}".format(core, ext)
    new_path = os.path.join(dirname, new_name)
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(
        os.path.abspath(new_path)
    ):
        return path
    if os.path.exists(new_path):
        raise RuntimeError("Target already exists: {}".format(new_path))
    os.rename(path, new_path)
    return new_path


def resolve_qif_dir(preferred=None):
    """Prefer JRSS shared QIF folder; fall back to repo-local qif_files."""
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend([QIF_DIR, LEGACY_QIF_DIR])
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return preferred or QIF_DIR


def qif_basename_for_statement(path):
    """Account + statement date, year-first: amazon_5144_2026_July15.QIF."""
    parsed = match_statement_name(path)
    if parsed:
        return "amazon_5144_{}_{}{}.QIF".format(
            parsed["year"], parsed["mon"], parsed["day"]
        )
    return "amazon_5144_{}.QIF".format(statement_id_from_path(path))


def qif_path_for_statement(path, qif_dir=None):
    """One QIF per statement month under the shared JRSS QIF folder."""
    qif_dir = resolve_qif_dir(qif_dir)
    return os.path.join(qif_dir, qif_basename_for_statement(path))


def qif_is_reconciled_name(path_or_name):
    """True if basename already ends with _reconcile before the extension."""
    stem, _ext = os.path.splitext(os.path.basename(path_or_name))
    return stem.lower().endswith(QIF_RECONCILE_SUFFIX.lower())


def rename_qif_reconciled(qif_path):
    """
    Append _reconcile before the extension after Quicken import/reconcile.
    e.g. amazon_5144_2026_July15.QIF → amazon_5144_2026_July15_reconcile.QIF
    Returns the new path (or the same path if already tagged).
    """
    qif_path = os.path.normpath(qif_path)
    if not os.path.isfile(qif_path):
        raise RuntimeError("QIF file not found: {}".format(qif_path))
    if qif_is_reconciled_name(qif_path):
        return qif_path
    dirname = os.path.dirname(qif_path)
    stem, ext = os.path.splitext(os.path.basename(qif_path))
    new_name = "{}{}{}".format(stem, QIF_RECONCILE_SUFFIX, ext or ".QIF")
    new_path = os.path.join(dirname, new_name)
    if os.path.exists(new_path):
        raise RuntimeError("Target already exists: {}".format(new_path))
    os.rename(qif_path, new_path)
    return new_path


def list_statement_pdfs(statements_dir=None, hide_download_duplicates=True):
    """
    List PDFs by stage, each list sorted chronologically by statement period.

    Raw Chase downloads (YYYYMMDD-statements-5144-.pdf) are included only when
    that year/month does not already have an archived Chase Prime filename, and
    only when hide_download_duplicates is True (default). Prefer running
    normalize_downloaded_statements() first so downloads become archive names.
    """
    statements_dir = resolve_statements_dir(statements_dir)
    out = {
        "reconciled": [],
        "approved": [],
        "unreconciled": [],
        "dir": statements_dir,
        "hidden_downloads": [],
    }
    if not os.path.isdir(statements_dir):
        return out

    # First pass: archived names only, so we know which months are covered.
    covered_months = set()
    archived_paths = []
    download_paths = []
    for path in _iter_statement_pdf_paths(statements_dir, include_downloads=True):
        if match_chase_download_name(path):
            download_paths.append(path)
            continue
        archived_paths.append(path)
        parsed = match_statement_name(path)
        if parsed:
            covered_months.add((parsed["year"], parsed["num"]))

    for path in archived_paths:
        out[statement_stage(path)].append(path)

    for path in download_paths:
        parsed = match_chase_download_name(path)
        key = (parsed["year"], parsed["num"]) if parsed else None
        if hide_download_duplicates and key and key in covered_months:
            out["hidden_downloads"].append(path)
            continue
        out[statement_stage(path)].append(path)

    def sort_key(p):
        period = parse_statement_period(p)
        return (period or datetime.max, os.path.basename(p).lower())

    for key in ("reconciled", "approved", "unreconciled"):
        out[key] = sorted(out[key], key=sort_key)
    return out


def next_incomplete_statement(statements_dir=None):
    """
    Earliest statement still needing work: unreconciled (review) first, else
    approved (Quicken import / mark reconciled). None if fully caught up.
    """
    listed = list_statement_pdfs(statements_dir)
    for path in listed.get("unreconciled") or []:
        return path
    for path in listed.get("approved") or []:
        return path
    return None


def next_unreconciled_statement(statements_dir=None):
    """Earliest unreconciled PDF, or None."""
    listed = list_statement_pdfs(statements_dir)
    items = listed.get("unreconciled") or []
    return items[0] if items else None


def add_months(year, month, delta):
    """Shift a year/month by delta months. Returns (year, month)."""
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def expected_statement_periods(through_date=None, start_after=None):
    """
    Statement periods (year, month, day=15) expected to exist by through_date.
    A period for month M is expected once through_date is on/after the publish
    day (17) of month M.
    """
    through_date = through_date or datetime.now()
    through_date = through_date.replace(hour=0, minute=0, second=0, microsecond=0)
    periods = []
    # Walk back a few years from through_date's month; caller filters.
    y, m = through_date.year, through_date.month
    # If before publish day this month, last expected is prior month.
    if through_date.day < STATEMENT_PUBLISH_DAY:
        y, m = add_months(y, m, -1)
    # Generate from start_after+1 month up to current expected.
    if start_after is None:
        # Default: only the current expected month (caller usually passes last REC)
        start_y, start_m = add_months(y, m, -0)
        cursor = (start_y, start_m)
        periods.append(
            {
                "year": cursor[0],
                "month": cursor[1],
                "day": STATEMENT_FILENAME_DAY,
                "period": datetime(cursor[0], cursor[1], STATEMENT_FILENAME_DAY),
            }
        )
        return periods

    start_y, start_m = start_after.year, start_after.month
    cy, cm = add_months(start_y, start_m, 1)
    end_y, end_m = y, m
    while (cy, cm) <= (end_y, end_m):
        periods.append(
            {
                "year": cy,
                "month": cm,
                "day": STATEMENT_FILENAME_DAY,
                "period": datetime(cy, cm, STATEMENT_FILENAME_DAY),
            }
        )
        cy, cm = add_months(cy, cm, 1)
    return periods


def reconciled_through_date(statements_dir=None):
    """Latest reconciled statement period date, or None."""
    listed = list_statement_pdfs(statements_dir)
    best = None
    for path in listed.get("reconciled") or []:
        period = parse_statement_period(path)
        if period and (best is None or period > best):
            best = period
    return best


def parse_statement_date(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().replace(tzinfo=None)
        except Exception:
            pass
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%b %d %Y",
        "%B %d %Y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        num = float(text)
        if 40000 < num < 60000:
            return pd.to_datetime(num, unit="D", origin="1899-12-30").to_pydatetime()
    except Exception:
        pass
    raise ValueError("Unrecognized date: {!r}".format(value))


def _pick_column(columns, candidates):
    lower = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for c in columns:
        cl = c.lower()
        for cand in candidates:
            if cand in cl:
                return c
    return None


def load_charges_csv(path):
    """
    Load charges from a simple CSV.

    Expected columns (flexible names):
      date / Transaction Date
      amount / Amount
      payee / Description (optional)
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        return []
    date_col = _pick_column(
        df.columns, ("date", "transaction date", "trans date", "posting date")
    )
    amount_col = _pick_column(
        df.columns, ("amount", "charge", "debit", "transaction amount")
    )
    payee_col = _pick_column(
        df.columns, ("payee", "description", "memo", "name", "merchant")
    )
    if not date_col or not amount_col:
        raise RuntimeError(
            "CSV needs date and amount columns. Found: {}".format(list(df.columns))
        )

    charges = []
    for _, row in df.iterrows():
        raw_amt = parse_qif_amount(row[amount_col])
        if raw_amt == 0:
            continue
        date = parse_statement_date(row[date_col])
        payee = row[payee_col] if payee_col else ""
        charges.append(
            {
                "date": date,
                "amount": abs(raw_amt),
                "signed_amount": -abs(raw_amt),
                "payee": payee.strip(),
                "source": os.path.basename(path),
                "raw_amount": raw_amt,
            }
        )
    charges.sort(key=lambda c: (c["date"] or datetime.min, c["amount"]))
    return charges


def extract_pdf_text(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(
            "pypdf is not installed. pip install pypdf  (or use a charges CSV)"
        )
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts)


def _statement_year_hint(path_or_name=None, text=""):
    """
    Prefer filename period year over scanning PDF text (account numbers can
    contain false '20xx' hits like 2060).
    """
    parsed = match_statement_name(path_or_name) if path_or_name else None
    if parsed:
        return parsed["year"]
    # Chase footer often embeds YY/MM/DD like 26/10/17
    footer = re.search(r"(?i)\b(\d{2})/(\d{2})/(\d{2})\b", text or "")
    if footer:
        yy = int(footer.group(1))
        return 2000 + yy if yy < 70 else 1900 + yy
    due = re.search(
        r"(?i)Payment Due Date:\s*\d{1,2}/\d{1,2}/(\d{2,4})", text or ""
    )
    if due:
        y = due.group(1)
        if len(y) == 2:
            yy = int(y)
            # Due date is typically next month; still same calendar year usually
            return 2000 + yy if yy < 70 else 1900 + yy
        return int(y)
    return None


def parse_charges_from_pdf_text(text, source_name="statement.pdf", year_hint=None):
    """
    Best-effort Chase-like line parse: DATE  DESCRIPTION  AMOUNT
    """
    if not text or len(text.strip()) < 40:
        return []

    charges = []
    line_re = re.compile(
        r"(?P<date>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+"
        r"(?P<desc>.+?)\s+"
        r"(?P<amount>-?\$?\d{1,3}(?:,\d{3})*\.\d{2})\s*$"
    )
    if year_hint is None:
        year_hint = _statement_year_hint(source_name, text)

    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        m = line_re.search(line)
        if not m:
            continue
        desc = m.group("desc").strip()
        low = desc.lower()
        if any(
            x in low
            for x in (
                "previous balance",
                "new balance",
                "minimum payment",
                "payment thank",
                "total fees",
                "opening",
            )
        ):
            continue
        amt = parse_qif_amount(m.group("amount"))
        if amt == 0:
            continue
        date_s = m.group("date")
        try:
            if date_s.count("/") == 1 and year_hint:
                date = datetime.strptime(
                    "{}/{}".format(date_s, year_hint % 100), "%m/%d/%y"
                )
            elif date_s.count("/") == 2:
                parts = date_s.split("/")
                if len(parts[2]) == 2:
                    date = datetime.strptime(date_s, "%m/%d/%y")
                else:
                    date = datetime.strptime(date_s, "%m/%d/%Y")
            else:
                continue
        except ValueError:
            continue
        # Statement lines can cross calendar year (Dec→Jan). If MM/DD year is
        # far from the statement year, nudge toward the nearer adjacent year.
        if year_hint and date_s.count("/") == 1:
            if date.year == year_hint and date.month == 12:
                pass
            elif date.month == 1 and date.year == year_hint:
                # January lines on a Jan statement are fine; on a Dec statement
                # they belong to next year — rare on these mid-month cycles.
                pass
            elif abs(date.year - year_hint) > 1:
                try:
                    date = date.replace(year=year_hint)
                except ValueError:
                    pass
        # Chase marks purchases positive and refund credits negative in extract.
        is_credit = amt < 0 and "payment" not in desc.lower()
        charges.append(
            {
                "date": date,
                "amount": abs(amt),
                "signed_amount": -abs(amt) if amt > 0 else amt,
                "payee": desc,
                "source": source_name,
                "raw_amount": amt,
                "is_credit": is_credit,
            }
        )

    seen = set()
    unique = []
    for c in charges:
        key = (c["date"], round(c["amount"], 2), c["payee"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda c: (c["date"] or datetime.min, c["amount"]))
    return unique


def load_charges_pdf(path):
    text = extract_pdf_text(path)
    year_hint = _statement_year_hint(path, text)
    return parse_charges_from_pdf_text(
        text, source_name=os.path.basename(path), year_hint=year_hint
    )


def load_charges(path):
    """Load charges from .csv or .pdf path."""
    lower = path.lower()
    if lower.endswith(".csv"):
        return load_charges_csv(path)
    if lower.endswith(".pdf"):
        return load_charges_pdf(path)
    raise RuntimeError(
        "Unsupported statement file (use .csv or .pdf): {}".format(path)
    )


def find_dropped_charge_csvs(search_dir="amazon"):
    """Find charge CSVs under amazon/ and repo-root example files."""
    patterns = [
        os.path.join(search_dir, "*charges*.csv"),
        os.path.join(search_dir, "*5144*.csv"),
        os.path.join(search_dir, "statements", "*.csv"),
        "amazon_charges_example.csv",
        "*charges*.csv",
    ]
    found = []
    for pat in patterns:
        for path in glob(pat):
            base = os.path.basename(path).lower()
            if "order history" in base or "filedescriptions" in base:
                continue
            if not os.path.isfile(path):
                continue
            found.append(os.path.normpath(path))
    return sorted(set(found))
