"""
Schwab One 9593 (Living Trust) transactions CSV (+ monthly PDF Change in Market Value)
→ Quicken Bank QIF for account Schwab One ...9593-Cash.

Rules: SCHWAB_9593.md
"""

from __future__ import print_function

import argparse
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

ACCOUNT_NAME = "Schwab One ...9593-Cash"
DEFAULT_STMT_DIR = r"C:\Users\james\OneDrive\JRSS Reconciliation\BRK Schwab One 9593"
DATA_FOLDER = "schwab_9593"
QIF_FOLDER = "qif_files"
TICKERS_FILE = "schwab_9593_tickers.json"

OMIT_ACTIONS = frozenset(
    {
        "Buy",
        "Sell",
        "Reinvest Shares",
        "Qual Div Reinvest",
    }
)

SCHWAB_BANK_045 = "[Chking Schwab ...045]"
BOFA_0149 = "[Chkng Main BofA-0149]"
# Journal destination suffix (CSV truncates as ...709 / ...384) → Quicken transfer account
JOURNAL_BY_SUFFIX = {
    "709": ("Auto Trader", "[Auto Trader  XXXXX709]"),
    "384": ("John Stevick", "[John Misc Loan]"),
}

MONEY_RE = re.compile(r"\(?\$?-?[\d,]+\.\d{2}\)?")
CSV_DATE_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{4})(?: as of \d{1,2}/\d{1,2}/\d{4})?$"
)


def _d(amount):
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_qif_date(dt):
    """M/D'YY with a space before single-digit days (matches Airbnb QIF / Quicken export)."""
    return "{0}/{1:>2}'{2:02d}".format(dt.month, dt.day, dt.year % 100)


def format_qif_amount(amount):
    """Thousands separators, two decimals, leading minus when negative."""
    d = _d(amount)
    sign = "-" if d < 0 else ""
    return "{0}{1:,.2f}".format(sign, abs(d))


def parse_csv_amount(raw):
    if raw is None or str(raw).strip() == "":
        return None
    s = str(raw).strip().replace("$", "").replace(",", "")
    return _d(s)


def parse_csv_date(raw):
    """Return primary date only; ignore 'as of'."""
    m = CSV_DATE_RE.match(raw.strip())
    if not m:
        raise ValueError("Unrecognized CSV date: {0!r}".format(raw))
    return datetime.strptime(m.group(1), "%m/%d/%Y")


def parse_money_token(tok):
    tok = tok.strip()
    neg = tok.startswith("(") or tok.startswith("-")
    digits = re.sub(r"[^\d.]", "", tok)
    if not digits:
        raise ValueError(tok)
    val = _d(digits)
    return -val if neg else val


def data_dir(repo_root):
    return os.path.join(repo_root, DATA_FOLDER)


def find_transactions_csv(repo_root):
    pattern = os.path.join(data_dir(repo_root), "Living_Trust_*Transactions*.csv")
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            "No Living_Trust_*Transactions*.csv found in {0}".format(
                data_dir(repo_root)
            )
        )
    return matches[-1]


def tickers_path(repo_root):
    return os.path.join(data_dir(repo_root), TICKERS_FILE)


def default_ticker_entry(symbol):
    """Ticker-agnostic defaults; optional overrides live in schwab_9593_tickers.json."""
    return {
        "category": "Dividends:{0}".format(symbol),
        "dividend_payee": "{0} Dividend".format(symbol),
        "foreign_tax_payee": "{0} Foreign Tax".format(symbol),
        "adr_fee_payee": "{0} ADR Pass Thru Fee".format(symbol),
    }


def load_tickers(path):
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("{0} must be a JSON object of ticker -> overrides".format(path))
    return data


def save_tickers(path, tickers):
    ordered = {}
    for key in sorted(tickers.keys()):
        ordered[key] = tickers[key]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(ordered, f, indent=2, sort_keys=False)
        f.write("\n")


def ensure_ticker(tickers, symbol):
    """Add symbol with defaults if new. Returns True if added."""
    if not symbol or symbol in tickers:
        return False
    tickers[symbol] = default_ticker_entry(symbol)
    return True


def ticker_fields(tickers, symbol):
    """Resolved category/payees for a symbol (defaults filled for missing keys)."""
    base = default_ticker_entry(symbol)
    overrides = tickers.get(symbol) or {}
    out = dict(base)
    for key, val in overrides.items():
        if val:
            out[key] = val
    return out


def load_csv_rows(csv_path, start, end, tickers):
    """
    Load include-rows with primary date in [start, end].
    Also registers every Symbol seen in-range (including Buy/Sell) into tickers.
    Returns (include_rows, newly_added_symbols).
    """
    rows = []
    newly_added = []
    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            action = (raw.get("Action") or "").strip()
            if not action:
                continue
            dt = parse_csv_date(raw["Date"])
            d = dt.date()
            if d < start or d > end:
                continue
            symbol = (raw.get("Symbol") or "").strip()
            if symbol and ensure_ticker(tickers, symbol):
                newly_added.append(symbol)
            if action in OMIT_ACTIONS:
                continue
            amount = parse_csv_amount(raw.get("Amount"))
            if amount is None:
                raise ValueError("Missing amount on {0} {1}".format(raw["Date"], action))
            rows.append(
                {
                    "date": dt,
                    "action": action,
                    "symbol": symbol,
                    "description": (raw.get("Description") or "").strip(),
                    "amount": amount,
                }
            )
    rows.sort(key=lambda r: (r["date"], r["action"], r["symbol"], r["amount"]))
    return rows, newly_added


def map_row(row, tickers):
    """
    Return dict with keys: date, amount, num, payee, memo (or None), category (or None).
    Unknown mappings keep payee from source and blank memo/category.
    """
    action = row["action"]
    symbol = row["symbol"]
    desc = row["description"]
    amount = row["amount"]
    dt = row["date"]

    if action in ("MoneyLink Deposit",):
        if desc.lower().startswith("berkeley eng"):
            return {
                "date": dt,
                "amount": amount,
                "num": "DEP",
                "payee": "Berkeley Eng",
                "memo": "GRS Salary",
                "category": "GRS Salary, BEAR",
            }
        return {
            "date": dt,
            "amount": amount,
            "num": "DEP",
            "payee": desc or "Deposit",
            "memo": None,
            "category": None,
        }

    if action in ("Bank Interest", "Credit Interest"):
        return {
            "date": dt,
            "amount": amount,
            "num": "INT",
            "payee": "Bank Int",
            "memo": "Interest",
            "category": "Interest:Schwab One",
        }

    if action == "MoneyLink Transfer":
        if "BANK OF AMERICA" in desc.upper() or "ELIZABETH SCHERE" in desc.upper():
            return {
                "date": dt,
                "amount": amount,
                "num": "TXFR",
                "payee": "From 9593 Schwab One",
                "memo": None,
                "category": BOFA_0149,
            }
        return {
            "date": dt,
            "amount": amount,
            "num": "TXFR",
            "payee": desc or "MoneyLink Transfer",
            "memo": None,
            "category": None,
        }

    if action == "Journal":
        desc_u = desc.upper()
        if "SCHWAB BANK" in desc_u and ("045" in desc_u or "...045" in desc):
            return {
                "date": dt,
                "amount": amount,
                "num": "TXFR",
                "payee": "From 9593 Schwab One",
                "memo": None,
                "category": SCHWAB_BANK_045,
            }
        suffix_m = re.search(r"\.\.\.(\d{3,})\s*$", desc) or re.search(
            r"(\d{3,})\s*$", desc.replace(" ", "")
        )
        if suffix_m:
            suffix = suffix_m.group(1)
            # Prefer last 3 digits for truncated CSV forms (...709, ...384)
            for key, (payee, cat) in JOURNAL_BY_SUFFIX.items():
                if suffix.endswith(key) or key == suffix:
                    return {
                        "date": dt,
                        "amount": amount,
                        "num": "TXFR",
                        "payee": payee,
                        "memo": None,
                        "category": cat,
                    }
        return {
            "date": dt,
            "amount": amount,
            "num": "TXFR",
            "payee": desc or "Journal",
            "memo": None,
            "category": None,
        }

    if action in ("Cash Dividend", "Qualified Dividend"):
        if not symbol:
            return {
                "date": dt,
                "amount": amount,
                "num": "DIV",
                "payee": desc or "Dividend",
                "memo": None,
                "category": None,
            }
        fields = ticker_fields(tickers, symbol)
        return {
            "date": dt,
            "amount": amount,
            "num": "DIV",
            "payee": fields["dividend_payee"],
            "memo": "Dividend",
            "category": fields["category"],
        }

    if action == "Foreign Tax Paid":
        if not symbol:
            return {
                "date": dt,
                "amount": amount,
                "num": "DIV",
                "payee": desc or "Foreign Tax Paid",
                "memo": None,
                "category": None,
            }
        fields = ticker_fields(tickers, symbol)
        return {
            "date": dt,
            "amount": amount,
            "num": "DIV",
            "payee": fields["foreign_tax_payee"],
            "memo": "Foreign tax dividend",
            "category": fields["category"],
        }

    if action == "ADR Mgmt Fee":
        if not symbol:
            return {
                "date": dt,
                "amount": amount,
                "num": "Fee",
                "payee": desc or "ADR Mgmt Fee",
                "memo": None,
                "category": None,
            }
        fields = ticker_fields(tickers, symbol)
        return {
            "date": dt,
            "amount": amount,
            "num": "Fee",
            "payee": fields["adr_fee_payee"],
            "memo": "ADR pass Thru Fee",
            "category": fields["category"],
        }

    # Unknown include-like action: emit blank category/memo
    return {
        "date": dt,
        "amount": amount,
        "num": "DEP" if amount >= 0 else "TXFR",
        "payee": desc or action,
        "memo": None,
        "category": None,
    }


def find_statement_pdf(stmt_dir, year, month):
    """Prefer BRK Schwab One 9593 named PDFs for the month; else Brokerage Statement_YYYY-MM-."""
    month_tokens = {
        1: ("Jan",),
        2: ("Feb",),
        3: ("Mar",),
        4: ("April", "Apr"),
        5: ("May",),
        6: ("June", "Jun"),
        7: ("July", "Jul"),
        8: ("Aug",),
        9: ("Sept", "Sep"),
        10: ("Oct",),
        11: ("Nov",),
        12: ("Dec",),
    }
    tokens = month_tokens[month]
    num = "{0:02d}".format(month)
    year_s = str(year)
    candidates = []
    seen = set()
    for path in glob.glob(os.path.join(stmt_dir, "*.PDF")) + glob.glob(
        os.path.join(stmt_dir, "*.pdf")
    ):
        if path in seen:
            continue
        seen.add(path)
        base = os.path.basename(path)
        if base.startswith("Brokerage Statement_{0}-{1}-".format(year_s, num)):
            candidates.append(path)
            continue
        if "BRK Schwab One 9593" not in base or year_s not in base:
            continue
        # Filenames like "BRK Schwab One 9593 2026 07 July [REC ...].PDF"
        if not re.search(r"\b{0}\b".format(num), base):
            continue
        if not any(tok in base for tok in tokens):
            continue
        candidates.append(path)

    brk = [p for p in candidates if "BRK Schwab One 9593" in os.path.basename(p)]
    pool = brk or candidates
    if not pool:
        raise FileNotFoundError(
            "No statement PDF for {0}-{1:02d} in {2}".format(year, month, stmt_dir)
        )
    rec = [p for p in pool if "REC" in os.path.basename(p)]
    return sorted(rec or pool)[-1]


def extract_positions_change(pdf_path):
    """
    From Positions - Summary bridge line:
    Beginning + Transfer + DivReinvested + CashActivity + Change = Ending
    Returns (change, beginning, ending, end_date).
    """
    if PdfReader is None:
        raise RuntimeError("pypdf is required to read statement PDFs")
    reader = PdfReader(pdf_path)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    idx = text.find("Positions - Summary")
    if idx < 0:
        raise ValueError("Positions - Summary not found in {0}".format(pdf_path))
    chunk = text[idx : idx + 1200]
    end_m = re.search(r"Ending Value\s*\nas of (\d{2}/\d{2})", chunk)
    if not end_m:
        # sometimes same line
        end_m = re.search(r"as of (\d{2}/\d{2})\s+Cost Basis", chunk)
    if not end_m:
        raise ValueError("Ending Value as of date not found in {0}".format(pdf_path))
    # Year from filename or nearby; use statement period if needed
    year_m = re.search(r"(20\d{2})", os.path.basename(pdf_path))
    year = int(year_m.group(1)) if year_m else datetime.now().year
    end_date = datetime.strptime("{0}/{1}".format(end_m.group(1), year), "%m/%d/%Y")

    # Bridge amounts line: first line of $-amounts after Market Value =
    after = chunk.split("Market Value", 1)[-1]
    money_line = None
    for line in after.splitlines():
        toks = MONEY_RE.findall(line)
        if len(toks) >= 6:
            money_line = toks
            break
    if not money_line:
        raise ValueError("Could not parse Positions Summary amounts in {0}".format(pdf_path))

    beginning = parse_money_token(money_line[0])
    # money_line[1]=transfer, [2]=div reinvested, [3]=cash activity, [4]=change, [5]=ending
    change = parse_money_token(money_line[4])
    ending = parse_money_token(money_line[5])
    return change, beginning, ending, end_date


def change_txn(change_amount, end_date):
    return {
        "date": end_date,
        "amount": _d(change_amount),
        "num": "Change",
        "payee": "Change In Value",
        "memo": "Change in Investments",
        "category": "Investments",
    }


def months_in_range(start, end):
    """Yield (year, month) for each calendar month touching [start, end]."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def build_transactions(csv_path, stmt_dir, start, end, tickers):
    cash_src, newly_added = load_csv_rows(csv_path, start, end, tickers)
    cash_rows = [map_row(r, tickers) for r in cash_src]
    changes = []
    tieouts = []
    for year, month in months_in_range(start, end):
        pdf = find_statement_pdf(stmt_dir, year, month)
        change, beginning, ending, end_date = extract_positions_change(pdf)
        # Only include change if end_date falls in requested window
        if start <= end_date.date() <= end:
            changes.append(change_txn(change, end_date))
            tieouts.append(
                {
                    "year": year,
                    "month": month,
                    "pdf": pdf,
                    "beginning": beginning,
                    "ending": ending,
                    "change": _d(change),
                    "end_date": end_date,
                }
            )
    txns = cash_rows + changes
    # Newest first (same ordering as Airbnb QIF imports).
    txns.sort(
        key=lambda t: (t["date"], t["num"], t["payee"], t["amount"]),
        reverse=True,
    )
    return txns, tieouts, newly_added


def render_qif(txns):
    parts = [
        "!Account\n",
        "N{0}\n".format(ACCOUNT_NAME),
        "TBank\n",
        "^\n",
        "!Type:Bank\n",
    ]
    for t in txns:
        parts.append("D{0}\n".format(format_qif_date(t["date"])))
        amt = format_qif_amount(t["amount"])
        parts.append("U{0}\n".format(amt))
        parts.append("T{0}\n".format(amt))
        parts.append("C*\n")
        parts.append("N{0}\n".format(t["num"]))
        parts.append("P{0}\n".format(t["payee"]))
        if t.get("memo"):
            parts.append("M{0}\n".format(t["memo"]))
        if t.get("category"):
            parts.append("L{0}\n".format(t["category"]))
        parts.append("^\n")
    return "".join(parts)


def verify_tieouts(txns, tieouts):
    """Per month: sum of QIF lines in that month == ending - beginning."""
    ok = True
    for info in tieouts:
        y, m = info["year"], info["month"]
        month_sum = _d(0)
        for t in txns:
            if t["date"].year == y and t["date"].month == m:
                month_sum += _d(t["amount"])
        expected = _d(info["ending"]) - _d(info["beginning"])
        if month_sum != expected:
            ok = False
            print(
                "TIE-OUT FAIL {0}-{1:02d}: QIF sum {2} != ending-beginning {3}".format(
                    y, m, month_sum, expected
                )
            )
        else:
            print(
                "TIE-OUT OK   {0}-{1:02d}: sum {2} (change {3})".format(
                    y, m, month_sum, info["change"]
                )
            )
    return ok


def parse_month(s):
    """YYYY-MM → first day date."""
    dt = datetime.strptime(s, "%Y-%m")
    return dt.date().replace(day=1)


def month_end(d):
    if d.month == 12:
        nxt = d.replace(year=d.year + 1, month=1, day=1)
    else:
        nxt = d.replace(month=d.month + 1, day=1)
    from datetime import timedelta

    return nxt - timedelta(days=1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Schwab One 9593 CSV (+ PDF Change) → Quicken QIF"
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Start month YYYY-MM (inclusive)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End month YYYY-MM (inclusive)",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Transactions CSV (default: newest Living_Trust_*Transactions*.csv in schwab_9593/)",
    )
    parser.add_argument(
        "--stmt-dir",
        default=DEFAULT_STMT_DIR,
        help="Directory of monthly Schwab statement PDFs",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output QIF path (default: qif_files/schwab_9593_"
            "<MM-DD-YYYY>_<MM-DD-YYYY>_run<MMDDYYYY>.QIF)"
        ),
    )
    args = parser.parse_args(argv)

    repo_root = os.getcwd()
    start = parse_month(args.start)
    end = month_end(parse_month(args.end))
    if end < start:
        print("ERROR: end before start", file=sys.stderr)
        return 1

    if not os.path.isdir(data_dir(repo_root)):
        print(
            "ERROR: data folder not found: {0}".format(data_dir(repo_root)),
            file=sys.stderr,
        )
        return 1

    csv_path = args.csv or find_transactions_csv(repo_root)
    if not os.path.isdir(args.stmt_dir):
        print("ERROR: statement dir not found: {0}".format(args.stmt_dir), file=sys.stderr)
        return 1

    qif_dir = os.path.join(repo_root, QIF_FOLDER)
    if not os.path.isdir(qif_dir):
        os.makedirs(qif_dir)

    run_dt = datetime.now()
    run_mmdyyyy = run_dt.strftime("%m%d%Y")
    span_start = start.strftime("%m-%d-%Y")
    span_end = end.strftime("%m-%d-%Y")
    out_path = args.out or os.path.join(
        qif_dir,
        "schwab_9593_{0}_{1}_run{2}.QIF".format(span_start, span_end, run_mmdyyyy),
    )

    print("CSV:  {0}".format(csv_path))
    print("PDFs: {0}".format(args.stmt_dir))
    print("Range: {0} .. {1}".format(start.isoformat(), end.isoformat()))

    tpath = tickers_path(repo_root)
    tickers = load_tickers(tpath)
    txns, tieouts, newly_added = build_transactions(
        csv_path, args.stmt_dir, start, end, tickers
    )
    if newly_added:
        save_tickers(tpath, tickers)
        print(
            "New ticker(s) added to {0}: {1}".format(
                TICKERS_FILE, ", ".join(sorted(newly_added))
            )
        )

    if not txns:
        print("ERROR: no transactions in range", file=sys.stderr)
        return 1

    for info in tieouts:
        print(
            "Statement {0}-{1:02d}: {2}".format(
                info["year"], info["month"], os.path.basename(info["pdf"])
            )
        )

    ok = verify_tieouts(txns, tieouts)
    text = render_qif(txns)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    blank_cat = sum(1 for t in txns if not t.get("category"))
    print("Wrote {0} transactions → {1}".format(len(txns), out_path))
    if blank_cat:
        print("Note: {0} line(s) have blank category (manual follow-up)".format(blank_cat))
    if not ok:
        print("FAILED tie-out", file=sys.stderr)
        return 1
    print("SUCCESS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
