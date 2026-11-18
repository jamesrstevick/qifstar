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
_BRACKET_RE = re.compile(r"\[([^\]]*)\]\s*$")


def match_statement_name(path_or_name):
    """
    Parse Chase Prime 5144 statement basename fields.
    Returns dict with year, num (1-12 from month name when possible), mon, day,
    or None.
    """
    core = statement_core_name(path_or_name)
    m = _STATEMENT_NAME_RE.search(core)
    if not m:
        return None
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


def list_statement_pdfs(statements_dir=None):
    """
    List PDFs by stage, each list sorted chronologically by statement period.
    """
    statements_dir = resolve_statements_dir(statements_dir)
    out = {"reconciled": [], "approved": [], "unreconciled": [], "dir": statements_dir}
    if not os.path.isdir(statements_dir):
        return out
    for name in os.listdir(statements_dir):
        if not name.lower().endswith(".pdf"):
            continue
        path = os.path.join(statements_dir, name)
        stage = statement_stage(name)
        out[stage].append(path)

    def sort_key(p):
        period = parse_statement_period(p)
        return (period or datetime.max, os.path.basename(p).lower())

    for key in ("reconciled", "approved", "unreconciled"):
        out[key] = sorted(out[key], key=sort_key)
    return out


def next_unreconciled_statement(statements_dir=None):
    """Earliest unreconciled PDF, or None."""
    listed = list_statement_pdfs(statements_dir)
    items = listed.get("unreconciled") or []
    return items[0] if items else None


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


def parse_charges_from_pdf_text(text, source_name="statement.pdf"):
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
    year_hint = None
    ym = re.search(r"20\d{2}", text)
    if ym:
        year_hint = int(ym.group(0))

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
        charges.append(
            {
                "date": date,
                "amount": abs(amt),
                "signed_amount": -abs(amt) if amt > 0 else amt,
                "payee": desc,
                "source": source_name,
                "raw_amount": amt,
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
    return parse_charges_from_pdf_text(text, source_name=os.path.basename(path))


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
