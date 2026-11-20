###########################################
# AMAZON ORDER LOOKUP
###########################################
# Look up Amazon Order History rows by card
# charge amount (optional date / last-4).
# Prints what was bought and where it shipped.
###########################################

from __future__ import print_function

import argparse
import os
import re
import sys
from datetime import datetime, timedelta

import pandas as pd

def _default_order_history():
    try:
        from amazon_cc.amazon_data import order_history_path

        return order_history_path()
    except Exception:
        return os.path.join(
            "amazon", "Your Orders", "Your Amazon Orders", "Order History.csv"
        )


ORDER_HISTORY = _default_order_history()

DEFAULT_TOLERANCE = 0.0  # Quicken amounts are exact; date may drift vs Amazon
DEFAULT_DATE_WINDOW_DAYS = 7
# Integer-dollar rewards matches use a tighter date window than exact amount hits.
DEFAULT_REWARDS_WINDOW_DAYS = 3
# When nothing matches primary windows, surface exact/rewards hits out this far.
DEFAULT_NEAR_MISS_WINDOW_DAYS = 30
# Privacy Central omits Amazon Rewards Points; Chase charge = order total − N dollars.
DEFAULT_MAX_REWARDS_DOLLARS = 50


def money(value):
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in ("Not Available", "Not Applicable"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_order_date(value):
    text = str(value).strip()
    if not text:
        return None
    # 2016-05-23T23:13:09Z or with fractional seconds
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    return None


def format_date(dt):
    if dt is None:
        return "?"
    return dt.strftime("%m/%d/%Y")


def load_orders(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "Order History not found at {!r}. Unpack the Privacy Central "
            "Your Orders export under amazon/.".format(path)
        )
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = [
        "Order ID",
        "Order Date",
        "Product Name",
        "Shipping Address",
        "Total Amount",
        "Payment Method Type",
        "Order Status",
        "Original Quantity",
        "Unit Price",
        "Unit Price Tax",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError("Order History missing columns: {}".format(missing))

    df["_line_total"] = df["Total Amount"].map(money)
    df["_qty"] = df["Original Quantity"].map(
        lambda v: int(float(v)) if str(v).strip() not in ("", "Not Available", "Not Applicable") else 1
    )
    df["_parsed_date"] = df["Order Date"].map(parse_order_date)
    return df


def card_last4(payment_method):
    matches = re.findall(r"(\d{4})", str(payment_method))
    return matches[-1] if matches else ""


def payment_uses_gift_card(payment_method):
    """True when Payment Method Type mentions a gift certificate/card tender."""
    text = str(payment_method or "").lower()
    return "gift certificate" in text or "gift card" in text


def order_uses_gift_card(order):
    """True when any payment tender on the order is a gift certificate/card."""
    for pay in order.get("payments") or []:
        if payment_uses_gift_card(pay):
            return True
    return bool(order.get("uses_gift_card"))


def _shipment_key(row):
    """Group multi-package orders by carrier tracking when present."""
    track = str(row.get("Carrier Name & Tracking Number", "") or "").strip()
    if track and track not in ("Not Available", "Not Applicable"):
        return track
    ship = str(row.get("Ship Date", "") or "").strip()
    if ship and ship not in ("Not Available", "Not Applicable"):
        return "ship:{}".format(ship)
    # Last resort: one pseudo-shipment per line
    return "line:{}:{}".format(row.get("ASIN", ""), row.get("_line_total", 0))


def build_order_summaries(df, include_cancelled=False):
    if not include_cancelled:
        df = df[df["Order Status"].str.lower() != "cancelled"].copy()

    orders = []
    for order_id, group in df.groupby("Order ID", sort=False):
        dates = [d for d in group["_parsed_date"] if d is not None]
        order_date = min(dates) if dates else None
        payments = sorted(
            {p for p in group["Payment Method Type"] if p and p != "Not Available"}
        )
        addresses = []
        for addr in group["Shipping Address"]:
            addr = str(addr).strip()
            if addr and addr not in ("Not Available", "Not Applicable") and addr not in addresses:
                addresses.append(addr)

        items = []
        for _, row in group.iterrows():
            items.append(
                {
                    "name": row["Product Name"],
                    "qty": row["_qty"],
                    "line_total": row["_line_total"],
                    "unit": money(row["Unit Price"]),
                    "tax": money(row["Unit Price Tax"]),
                    "asin": row.get("ASIN", ""),
                    "tracking": str(
                        row.get("Carrier Name & Tracking Number", "") or ""
                    ).strip(),
                    "ship_date": str(row.get("Ship Date", "") or "").strip(),
                    "_ship_key": _shipment_key(row),
                }
            )

        # Shipments = packages that may each hit the card separately
        ship_map = {}
        for item in items:
            key = item.get("_ship_key") or "unknown"
            if key not in ship_map:
                ship_map[key] = {
                    "key": key,
                    "tracking": item.get("tracking") or "",
                    "ship_date": item.get("ship_date") or "",
                    "items": [],
                    "addresses": [],
                }
            ship_map[key]["items"].append(item)
        shipments = []
        for ship in ship_map.values():
            ship["total"] = float(sum(i.get("line_total") or 0 for i in ship["items"]))
            shipments.append(ship)
        shipments.sort(key=lambda s: (-s["total"], s.get("key") or ""))

        last4s = sorted({card_last4(p) for p in payments if card_last4(p)})
        uses_gift = any(payment_uses_gift_card(p) for p in payments)
        orders.append(
            {
                "order_id": order_id,
                "order_date": order_date,
                "total": float(group["_line_total"].sum()),
                "payments": payments,
                "last4s": last4s,
                "uses_gift_card": uses_gift,
                "addresses": addresses,
                "status": sorted(set(group["Order Status"])),
                "items": items,
                "shipments": shipments,
            }
        )
    return orders


def parse_user_date(text):
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        "Date must be YYYY-MM-DD or MM/DD/YYYY (got {!r})".format(text)
    )


def amounts_match(order_total, amount, tolerance):
    # Compare in cents so float noise does not break exact Quicken amounts.
    return amount_match_info(order_total, amount, tolerance=tolerance) is not None


def amount_match_info(
    order_total,
    amount,
    tolerance=DEFAULT_TOLERANCE,
    allow_integer_rewards=False,
    max_rewards_dollars=DEFAULT_MAX_REWARDS_DOLLARS,
):
    """
    Return match metadata or None.

    exact / tolerance: totals agree (within tolerance).
    rewards: Order History total exceeds the card charge by a whole number of
    dollars (1..max) — typical when Rewards Points are applied on Amazon.com
    but omitted from Privacy Central Totals.
    """
    order_cents = int(round(float(order_total) * 100))
    amt_cents = int(round(float(amount) * 100))
    if tolerance <= 0:
        if order_cents == amt_cents:
            return {"kind": "exact", "rewards_dollars": 0}
    elif abs(float(order_total) - float(amount)) <= tolerance:
        return {"kind": "tolerance", "rewards_dollars": 0}

    if allow_integer_rewards and order_cents > amt_cents:
        diff_cents = order_cents - amt_cents
        if diff_cents % 100 == 0:
            dollars = diff_cents // 100
            if 1 <= dollars <= int(max_rewards_dollars):
                return {"kind": "rewards", "rewards_dollars": int(dollars)}
    return None


def _as_naive_date(value):
    """Normalize datetime/date/ISO string to a date, or None."""
    if value is None or value == "" or value in ("Not Available", "Not Applicable"):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).date()
    # datetime.date has year/month/day but no hour
    if hasattr(value, "year") and hasattr(value, "month") and not hasattr(value, "hour"):
        return value
    parsed = parse_order_date(value)
    if parsed is not None:
        return parsed.replace(tzinfo=None).date()
    return None


def _iter_order_event_dates(order):
    """
    Dates that can align with a Chase post: order placed, or package shipped.

    Amazon often charges near Ship Date (Subscribe & Save delays), while
    Privacy Central Order Date stays at purchase time.
    """
    seen = set()
    if order.get("order_date") is not None:
        d = _as_naive_date(order.get("order_date"))
        if d is not None and d not in seen:
            seen.add(d)
            yield "order", d
    for ship in order.get("shipments") or []:
        d = _as_naive_date(ship.get("ship_date"))
        if d is not None and d not in seen:
            seen.add(d)
            yield "ship", d
    for item in order.get("items") or []:
        d = _as_naive_date(item.get("ship_date"))
        if d is not None and d not in seen:
            seen.add(d)
            yield "ship", d


def _best_date_delta(order, date):
    """
    Closest absolute day gap between charge date and order/ship dates.

    Returns (delta_days, basis) where basis is 'order' or 'ship', or (None, None).
    """
    if date is None:
        return None, None
    charge_d = date.date() if hasattr(date, "date") else date
    best = None
    basis = None
    for kind, event_d in _iter_order_event_dates(order):
        delta = abs((event_d - charge_d).days)
        # Prefer closer dates; on ties prefer ship (card post timing).
        if best is None or delta < best or (delta == best and kind == "ship"):
            best = delta
            basis = kind
    return best, basis


def _date_delta_days(order, date):
    """Absolute days to nearest order/ship date, or None."""
    delta, _basis = _best_date_delta(order, date)
    return delta


def _passes_card_and_date(order, date, last4, window_days):
    if last4 and last4 not in (order.get("last4s") or []):
        if order.get("last4s"):
            return False
    if date is not None:
        delta = _date_delta_days(order, date)
        if delta is None or delta > window_days:
            return False
    return True


def _accept_amount_match(info, order, date, rewards_window_days):
    """Exact/tolerance use the outer date window; rewards need ±rewards_window_days."""
    if info is None:
        return False
    if info.get("kind") != "rewards":
        return True
    delta = _date_delta_days(order, date)
    if delta is None:
        return False
    return delta <= rewards_window_days


def _annotate_match(order, info, level, matched_total, match_items, tracking="", date=None):
    matched = dict(order)
    matched["match_kind"] = info["kind"]
    matched["match_level"] = level
    matched["matched_total"] = float(matched_total)
    matched["rewards_dollars"] = info.get("rewards_dollars") or 0
    matched["match_items"] = list(match_items or [])
    matched["matched_tracking"] = tracking or ""
    delta, basis = _best_date_delta(order, date) if date is not None else (None, None)
    matched["date_delta_days"] = delta
    matched["date_basis"] = basis or ""
    return matched


def match_orders(
    orders,
    amount,
    date=None,
    last4=None,
    tolerance=DEFAULT_TOLERANCE,
    window_days=DEFAULT_DATE_WINDOW_DAYS,
    allow_integer_rewards=None,
    max_rewards_dollars=DEFAULT_MAX_REWARDS_DOLLARS,
    rewards_window_days=DEFAULT_REWARDS_WINDOW_DAYS,
):
    """
    Match card charges to Order History.

    Tries, in order: full order total → shipment/package total → single line.
    Date windows use the nearer of Order Date or Ship Date (Amazon often posts
    the card near shipment, e.g. Subscribe & Save).
    Integer-dollar rewards matching runs only when a charge date is provided
    and that nearer date is within rewards_window_days (±3 by default).
    Exact amount matches use window_days (±7 by default).
    Exact amount matches sort above rewards; order-level above shipment/line.
    """
    if allow_integer_rewards is None:
        allow_integer_rewards = date is not None

    matches = []
    for order in orders:
        if not _passes_card_and_date(order, date, last4, window_days):
            continue

        info = amount_match_info(
            order["total"],
            amount,
            tolerance=tolerance,
            allow_integer_rewards=allow_integer_rewards,
            max_rewards_dollars=max_rewards_dollars,
        )
        if _accept_amount_match(info, order, date, rewards_window_days):
            matches.append(
                _annotate_match(
                    order,
                    info,
                    "order",
                    order["total"],
                    order.get("items") or [],
                    date=date,
                )
            )
            continue  # full order hit is enough

        shipment_hit = False
        for ship in order.get("shipments") or []:
            info = amount_match_info(
                ship.get("total") or 0,
                amount,
                tolerance=tolerance,
                allow_integer_rewards=allow_integer_rewards,
                max_rewards_dollars=max_rewards_dollars,
            )
            if not _accept_amount_match(info, order, date, rewards_window_days):
                continue
            shipment_hit = True
            matches.append(
                _annotate_match(
                    order,
                    info,
                    "shipment",
                    ship.get("total") or 0,
                    ship.get("items") or [],
                    tracking=ship.get("tracking") or ship.get("key") or "",
                    date=date,
                )
            )
        if shipment_hit:
            continue

        # Single-line fallback (same shipment may still miss if grouping failed)
        line_hit = False
        for item in order.get("items") or []:
            info = amount_match_info(
                item.get("line_total") or 0,
                amount,
                tolerance=tolerance,
                allow_integer_rewards=allow_integer_rewards,
                max_rewards_dollars=max_rewards_dollars,
            )
            if not _accept_amount_match(info, order, date, rewards_window_days):
                continue
            line_hit = True
            matches.append(
                _annotate_match(
                    order,
                    info,
                    "line",
                    item.get("line_total") or 0,
                    [item],
                    tracking=item.get("tracking") or "",
                    date=date,
                )
            )
        if line_hit:
            continue

        # Gift Certificate/Card + Visa: Order History totals stay at the full
        # merchandise amount; the statement only shows the card residual.
        # Privacy Central does not export the gift-card dollar amount, so match
        # when payment mentions a gift card, a card last-4 is present (not
        # gift-only), and order total is strictly greater than the charge.
        if order_uses_gift_card(order) and (order.get("last4s") or []):
            order_total = float(order.get("total") or 0)
            if order_total > float(amount) + float(tolerance):
                gift_inferred = round(order_total - float(amount), 2)
                gift_hit = _annotate_match(
                    order,
                    {"kind": "gift_card_partial", "rewards_dollars": 0},
                    "gift_card",
                    float(amount),
                    order.get("items") or [],
                    date=date,
                )
                gift_hit["gift_card_inferred"] = gift_inferred
                matches.append(gift_hit)

    # Gift-card residual is a fallback only. A large gift+card order would
    # otherwise appear on every smaller charge in the same ±7 day window.
    if any(m.get("match_kind") != "gift_card_partial" for m in matches):
        matches = [m for m in matches if m.get("match_kind") != "gift_card_partial"]

    def sort_key(o):
        kind = o.get("match_kind") or ""
        if kind in ("exact", "tolerance"):
            kind_rank = 0
        elif kind == "gift_card_partial":
            kind_rank = 1
        else:
            kind_rank = 2
        level_rank = {
            "order": 0,
            "gift_card": 1,
            "remainder": 2,
            "shipment": 3,
            "line": 4,
        }.get(o.get("match_level") or "order", 5)
        rewards = int(o.get("rewards_dollars") or 0)
        # Prefer ship-aligned and closer day gaps
        basis_rank = 0 if o.get("date_basis") == "ship" else 1
        delta = o.get("date_delta_days")
        delta_rank = delta if delta is not None else 999
        od = o.get("order_date") or datetime.min
        if getattr(od, "tzinfo", None) is not None:
            od = od.replace(tzinfo=None)
        return (
            kind_rank,
            level_rank,
            rewards,
            basis_rank,
            delta_rank,
            -od.toordinal() if hasattr(od, "toordinal") else 0,
        )

    matches.sort(key=sort_key)
    return matches


def print_order(order):
    date_s = format_date(
        order["order_date"].replace(tzinfo=None) if order["order_date"] else None
    )
    pay = ", ".join(order["payments"]) if order["payments"] else "(payment unknown)"
    status = ", ".join(order["status"])
    print("=" * 60)
    print("Order {}    {}    ${:.2f}".format(order["order_id"], date_s, order["total"]))
    print("Status: {}    Payment: {}".format(status, pay))
    if order["addresses"]:
        for addr in order["addresses"]:
            print("Ship to: {}".format(addr))
    else:
        print("Ship to: (not available)")
    print("Items:")
    for item in order["items"]:
        name = item["name"]
        if len(name) > 90:
            name = name[:87] + "..."
        print(
            "  - qty {:>2}  ${:>8.2f}  {}".format(item["qty"], item["line_total"], name)
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Look up Amazon orders by charge amount (from Order History.csv)."
    )
    parser.add_argument("amount", type=float, help="Card charge amount, e.g. 48.51")
    parser.add_argument(
        "--date",
        type=parse_user_date,
        help="Charge/order date (YYYY-MM-DD or MM/DD/YYYY); matches within --window days",
    )
    parser.add_argument(
        "--card",
        dest="last4",
        help="Card last four digits to filter Payment Method Type",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="Amount match tolerance in dollars (default {:.2f}; usually leave at 0)".format(
            DEFAULT_TOLERANCE
        ),
    )
    parser.add_argument(
        "--window",
        type=int,
        default=DEFAULT_DATE_WINDOW_DAYS,
        help="Days ± around --date (default {})".format(DEFAULT_DATE_WINDOW_DAYS),
    )
    parser.add_argument(
        "--csv",
        default=ORDER_HISTORY,
        help="Path to Order History.csv (default: {})".format(ORDER_HISTORY),
    )
    parser.add_argument(
        "--include-cancelled",
        action="store_true",
        help="Include Cancelled orders",
    )
    args = parser.parse_args(argv)

    try:
        df = load_orders(args.csv)
        orders = build_order_summaries(df, include_cancelled=args.include_cancelled)
        matches = match_orders(
            orders,
            amount=args.amount,
            date=args.date,
            last4=args.last4,
            tolerance=args.tolerance,
            window_days=args.window,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print("FAILED: {}".format(exc), file=sys.stderr)
        return 1

    if args.tolerance <= 0:
        filters = ["amount=${:.2f} (exact)".format(args.amount)]
    else:
        filters = ["amount=${:.2f} +/-${:.2f}".format(args.amount, args.tolerance)]
    if args.date:
        filters.append(
            "date={} +/-{}d".format(args.date.strftime("%m/%d/%Y"), args.window)
        )
    if args.last4:
        filters.append("card=****{}".format(args.last4))
    print("Lookup: {}".format(", ".join(filters)))
    print("Orders scanned: {} (from {})".format(len(orders), args.csv))
    print()

    if not matches:
        print("No matching orders.")
        return 0

    print("Matches: {}".format(len(matches)))
    for order in matches:
        print_order(order)
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
