"""Parse and write Quicken CCard QIF (Amazon Chase 5144 style)."""

from __future__ import print_function

import re
from collections import Counter
from datetime import datetime


def parse_qif_date(text):
    """Parse Quicken dates like 1/ 3'25 or 12/15'25 into datetime."""
    text = str(text).strip()
    m = re.match(r"^(\d{1,2})/\s*(\d{1,2})'(\d{2})$", text)
    if not m:
        raise ValueError("Unrecognized QIF date: {!r}".format(text))
    month, day, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    year = 2000 + yy if yy < 70 else 1900 + yy
    return datetime(year, month, day)


def format_qif_date(dt):
    """Format datetime as Quicken CCard date (M/ D'YY with space-padded day)."""
    if isinstance(dt, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                dt = datetime.strptime(dt.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            dt = parse_qif_date(dt)
    day = dt.day
    month = dt.month
    yy = dt.year % 100
    day_s = " {}".format(day) if day < 10 else str(day)
    return "{}/{}'{:02d}".format(month, day_s, yy)


def parse_qif_amount(text):
    text = str(text).replace(",", "").replace("$", "").strip()
    if not text:
        return 0.0
    return float(text)


def parse_ccard_qif(path):
    """
    Parse a CCard QIF into a list of transaction dicts.

    Keys: date (datetime), amount (float, signed as in file), payee, memo,
    category, cleared, splits (list of {category, memo, amount} or empty).
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    transactions = []
    cur = {
        "date": None,
        "amount": None,
        "payee": "",
        "memo": "",
        "category": "",
        "cleared": "",
        "splits": [],
    }
    split_cat = None
    split_memo = ""

    def flush():
        if cur["date"] is None and cur["amount"] is None:
            return
        transactions.append(
            {
                "date": cur["date"],
                "amount": cur["amount"] if cur["amount"] is not None else 0.0,
                "payee": cur["payee"],
                "memo": cur["memo"],
                "category": cur["category"],
                "cleared": cur["cleared"],
                "splits": list(cur["splits"]),
            }
        )

    for line in lines:
        if not line:
            continue
        if line.startswith("!Type:") or line.startswith("!Account"):
            continue
        if line.startswith("^"):
            if split_cat is not None:
                # incomplete split line ignored
                split_cat = None
                split_memo = ""
            flush()
            cur = {
                "date": None,
                "amount": None,
                "payee": "",
                "memo": "",
                "category": "",
                "cleared": "",
                "splits": [],
            }
            continue

        code, rest = line[0], line[1:]
        if code == "D":
            cur["date"] = parse_qif_date(rest)
        elif code in ("U", "T"):
            # Prefer T if both present; last write wins — both usually equal
            cur["amount"] = parse_qif_amount(rest)
        elif code == "P":
            cur["payee"] = rest
        elif code == "M":
            cur["memo"] = rest
        elif code == "L":
            cur["category"] = rest
        elif code == "C":
            cur["cleared"] = rest
        elif code == "S":
            if split_cat is not None:
                cur["splits"].append(
                    {"category": split_cat, "memo": split_memo, "amount": None}
                )
            split_cat = rest
            split_memo = ""
        elif code == "E":
            split_memo = rest
        elif code == "$":
            amt = parse_qif_amount(rest)
            if split_cat is not None:
                cur["splits"].append(
                    {"category": split_cat, "memo": split_memo, "amount": amt}
                )
                split_cat = None
                split_memo = ""

    if cur["date"] is not None or cur["amount"] is not None:
        flush()
    return transactions


def write_ccard_qif(path, transactions, cleared="*"):
    """
    Write CCard QIF. Each txn: date, amount (negative for charges), payee,
    memo, category; optional splits list.

    Default cleared is ``*`` (emits ``C*``), matching Airbnb / Schwab imports.
    Pass cleared="" to omit the C line.
    """
    lines = ["!Type:CCard"]
    for txn in transactions:
        lines.append("D{}".format(format_qif_date(txn["date"])))
        amt = float(txn["amount"])
        # Quicken uses comma in thousands for large amounts
        amt_s = "{:,.2f}".format(amt)
        lines.append("U{}".format(amt_s))
        lines.append("T{}".format(amt_s))
        clr = txn.get("cleared", cleared)
        if clr:
            lines.append("C{}".format(clr))
        lines.append("P{}".format(txn.get("payee", "Amazon")))
        memo = txn.get("memo") or ""
        if memo:
            lines.append("M{}".format(memo))
        cat = txn.get("category") or ""
        lines.append("L{}".format(cat))
        for sp in txn.get("splits") or []:
            lines.append("S{}".format(sp["category"]))
            if sp.get("memo"):
                lines.append("E{}".format(sp["memo"]))
            if sp.get("amount") is not None:
                lines.append("${:,.2f}".format(float(sp["amount"])))
        lines.append("^")

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def is_amazon_like_payee(payee):
    p = (payee or "").lower()
    keys = ("amazon", "prime video", "prime", "kindle", "wholefds", "whole foods")
    return any(k in p for k in keys)


def is_statement_card_payment(payee):
    """
    True for Chase statement payment credits (not Amazon purchases).

    Examples: AUTOMATIC PAYMENT - THANK YOU
    """
    raw = (payee or "").strip().lower()
    if not raw:
        return False
    norm = re.sub(r"[^a-z0-9]+", " ", raw).strip()
    if "automatic payment" in norm:
        return True
    if "payment" in norm and "thank you" in norm:
        return True
    if "autopay" in norm or "auto pay" in norm:
        return True
    return False


def is_statement_refund_credit(charge):
    """
    True for Amazon/merchant refund credits on the statement (not card payments).

    Chase PDF extract marks these with a negative raw amount; amount is abs().
    """
    if not charge:
        return False
    if is_statement_card_payment(charge.get("payee") or ""):
        return False
    if charge.get("is_credit") is True:
        return True
    raw = charge.get("raw_amount")
    try:
        return raw is not None and float(raw) < 0
    except (TypeError, ValueError):
        return False


def is_card_payment_qif_fields(qif_fields):
    """True when approved fields look like a card payment / checking transfer."""
    if not qif_fields:
        return False
    if (qif_fields.get("match_level") or "") == "payment":
        return True
    cat = qif_fields.get("category") or ""
    if cat.startswith("["):
        return True
    memo = (qif_fields.get("memo") or "").lower()
    if "credit card payment" in memo or "monthly credit card" in memo:
        return True
    payee = (qif_fields.get("payee") or "").lower()
    if "card payment" in payee:
        return True
    return False


def is_refund_qif_fields(qif_fields):
    """True when approved fields are an Amazon refund/return credit."""
    if not qif_fields:
        return False
    level = (qif_fields.get("match_level") or "").lower()
    if level == "refund":
        return True
    if (qif_fields.get("match_kind") or "").lower() == "refund":
        return True
    return False


def is_positive_ccard_qif_fields(qif_fields):
    """CCard QIF amount should be positive (payments and refunds)."""
    return is_card_payment_qif_fields(qif_fields) or is_refund_qif_fields(qif_fields)


def card_payment_template_from_qif(qif_path):
    """
    Most common monthly card-payment transfer from a training CCard QIF.

    Prefers Amazon Chase → [Chkng Main BofA-0149] style rows (positive amounts).
    """
    default = {
        "payee": "Amazon Chase",
        "memo": "Credit Card Payment",
        "category": "[Chkng Main BofA-0149]",
        "reason": "card_payment_default",
    }
    try:
        txns = parse_ccard_qif(qif_path)
    except (OSError, ValueError):
        return default

    counts = Counter()
    for txn in txns:
        if float(txn.get("amount") or 0) <= 0:
            continue
        cat = txn.get("category") or ""
        if not cat.startswith("["):
            continue
        payee = (txn.get("payee") or "").strip()
        memo = (txn.get("memo") or "").strip()
        memo_l = memo.lower()
        payee_l = payee.lower()
        looks_payment = (
            "credit card payment" in memo_l
            or "monthly credit card" in memo_l
            or "card payment" in payee_l
            or payee_l == "amazon chase"
        )
        if not looks_payment:
            continue
        counts[(payee, memo, cat)] += 1

    if not counts:
        return default

    # Prefer Amazon Chase templates when present
    preferred = [
        (key, n)
        for key, n in counts.items()
        if "amazon chase" in (key[0] or "").lower()
    ]
    pool = preferred if preferred else list(counts.items())
    (payee, memo, cat), n = max(pool, key=lambda item: item[1])
    return {
        "payee": payee or default["payee"],
        "memo": memo or default["memo"],
        "category": cat or default["category"],
        "reason": "card_payment_training:{}x".format(n),
    }


def is_skippable_for_orders(txn):
    """Transfers, payments, and non-purchase rows that won't match Order History."""
    cat = txn.get("category") or ""
    if cat.startswith("["):
        return True
    memo = (txn.get("memo") or "").lower()
    if "credit card payment" in memo or "monthly credit card" in memo:
        return True
    payee = (txn.get("payee") or "").lower()
    if "card payment" in payee or "payment" == payee:
        return True
    return False


def charge_amount(txn):
    """Positive dollars for a purchase charge (QIF stores charges as negative)."""
    amt = float(txn.get("amount") or 0.0)
    return abs(amt)


def _is_categories_export(path):
    """True if path looks like a Quicken Categories.QIF (!Type:Cat) export."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return "!Type:Cat" in head


def parse_categories_qif(path):
    """
    Parse a Quicken category list export (!Type:Cat).
    Returns unique category path strings from N… records (skips tags / junk).
    """
    cats = []
    seen = set()
    mode = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []

    skip = {"--split--", "", "...,,, ?"}
    for line in lines:
        if not line:
            continue
        if line.startswith("!Type:"):
            mode = line[6:].strip()
            continue
        if mode != "Cat":
            continue
        if not line.startswith("N"):
            continue
        name = line[1:].strip()
        if not name or name.lower() in skip:
            continue
        if name not in seen:
            seen.add(name)
            cats.append(name)
    return cats


def load_known_categories(qif_path, extra=None, include_transfers=False):
    """
    Unique Quicken category paths (exact strings).

    Accepts either:
      - Categories.QIF (!Type:Cat export), or
      - a training CCard QIF (categories collected from L / split S lines).

    Skips transfers ([Account]) and --Split-- by default.
    Set include_transfers=True for card-payment rows.
    """
    cats = set(extra or [])
    try:
        if _is_categories_export(qif_path):
            for cat in parse_categories_qif(qif_path):
                if include_transfers or not cat.startswith("["):
                    cats.add(cat)
            return sorted(cats, key=lambda s: s.lower())
        txns = parse_ccard_qif(qif_path)
    except (OSError, ValueError):
        return sorted(cats, key=lambda s: s.lower())
    for txn in txns:
        cat = txn.get("category") or ""
        if cat and cat != "--Split--":
            if include_transfers or not cat.startswith("["):
                cats.add(cat)
        for sp in txn.get("splits") or []:
            sc = sp.get("category") or ""
            if sc and sc != "--Split--":
                if include_transfers or not sc.startswith("["):
                    cats.add(sc)
    return sorted(cats, key=lambda s: s.lower())


def nearest_category(guess, known):
    """Map a guessed category to an exact known path, or None."""
    if not known:
        return None
    if not guess:
        return None
    if guess in known:
        return guess
    # Case-insensitive exact
    lower = {c.lower(): c for c in known}
    if guess.lower() in lower:
        return lower[guess.lower()]
    # Prefer same root with :Supplies, else first category sharing root
    root = guess.split(":")[0]
    supplies = "{}:Supplies".format(root)
    if supplies in known:
        return supplies
    for c in known:
        if c == root or c.startswith(root + ":"):
            return c
    return None
