"""Match QIF / statement charges to Amazon Order History summaries."""

from __future__ import print_function

import os

import pandas as pd

from amazon_lookup import (
    DEFAULT_DATE_WINDOW_DAYS,
    DEFAULT_MAX_REWARDS_DOLLARS,
    DEFAULT_NEAR_MISS_WINDOW_DAYS,
    DEFAULT_REWARDS_WINDOW_DAYS,
    DEFAULT_TOLERANCE,
    _best_date_delta,
    amount_match_info,
    build_order_summaries,
    load_orders,
    match_orders,
    money,
    parse_order_date,
)
from amazon_cc.qif_io import (
    charge_amount,
    is_amazon_like_payee,
    is_skippable_for_orders,
    parse_ccard_qif,
)

from amazon_cc.amazon_data import (
    digital_orders_path as resolve_digital_orders_path,
    digital_returns_path as resolve_digital_returns_path,
    order_history_path as resolve_order_history_path,
    refund_details_path as resolve_refund_details_path,
)


def load_digital_order_summaries(path=None):
    """Group digital rows by Order ID using sum of Transaction Amount."""
    path = path or resolve_digital_orders_path()
    if not path or not os.path.isfile(path):
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "Order ID" not in df.columns or "Transaction Amount" not in df.columns:
        return []
    df["_line_total"] = df["Transaction Amount"].map(money)
    df["_parsed_date"] = df["Order Date"].map(parse_order_date)
    orders = []
    for order_id, group in df.groupby("Order ID", sort=False):
        dates = [d for d in group["_parsed_date"] if d is not None]
        items = []
        for _, row in group.iterrows():
            # Skip pure tax component rows with $0 transaction if product already listed
            name = row.get("Product Name") or ""
            items.append(
                {
                    "name": name,
                    "qty": 1,
                    "line_total": row["_line_total"],
                    "unit": money(row.get("Price", 0)),
                    "tax": money(row.get("Price Tax", 0)),
                    "asin": row.get("ASIN", ""),
                }
            )
        # Collapse duplicate product names for display
        seen = set()
        uniq_items = []
        for item in items:
            key = (item["name"], round(item["line_total"], 2))
            if key in seen:
                continue
            if item["line_total"] == 0 and item["name"] in {
                i["name"] for i in uniq_items
            }:
                continue
            seen.add(key)
            uniq_items.append(item)
        total = float(group["_line_total"].sum())
        if total <= 0:
            continue
        orders.append(
            {
                "order_id": order_id,
                "order_date": min(dates) if dates else None,
                "total": total,
                "payments": [],
                "last4s": [],
                "addresses": [],
                "status": sorted(set(group.get("Order Status", pd.Series(dtype=str)))),
                "items": uniq_items,
                "shipments": [
                    {
                        "key": "digital",
                        "tracking": "",
                        "ship_date": "",
                        "total": total,
                        "items": uniq_items,
                        "addresses": [],
                    }
                ],
                "source": "digital",
            }
        )
    return orders


def load_digital_refund_summaries(path=None):
    """
    Digital Returns.csv → one summary per Order ID + return date.

    Amount Refunded is repeated on Price/Tax component rows; use that value
    when present, else sum Transaction Amount. order_date is the return date
    so charge-date windows align with Chase refund posts.
    """
    path = path or resolve_digital_returns_path()
    if not path or not os.path.isfile(path):
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "Order ID" not in df.columns:
        return []
    refunds = []
    group_cols = ["Order ID"]
    if "Return Date" in df.columns:
        group_cols.append("Return Date")
    for key, group in df.groupby(group_cols, sort=False):
        if isinstance(key, tuple):
            order_id, return_raw = key[0], key[1] if len(key) > 1 else ""
        else:
            order_id, return_raw = key, ""
        refund_amts = []
        for raw in group.get("Amount Refunded", pd.Series(dtype=str)):
            val = money(raw)
            if val > 0:
                refund_amts.append(val)
        if refund_amts:
            total = float(refund_amts[0])
        else:
            total = float(sum(money(x) for x in group.get("Transaction Amount", [])))
        if total <= 0:
            continue
        return_date = parse_order_date(return_raw) if return_raw else None
        # Prefer a real product name (skip empty / numeric junk)
        names = []
        for raw in group.get("Product Name", pd.Series(dtype=str)):
            name = (raw or "").strip()
            if not name or name.lower() in ("not available", "not applicable"):
                continue
            if name.isdigit():
                continue
            names.append(name)
        product = names[0] if names else "Digital refund"
        items = [
            {
                "name": product,
                "qty": 1,
                "line_total": total,
                "unit": total,
                "tax": 0.0,
                "asin": (group["ASIN"].iloc[0] if "ASIN" in group.columns else "")
                or "",
            }
        ]
        statuses = []
        for col in ("Return Status", "Status"):
            if col in group.columns:
                statuses.extend(
                    sorted(
                        {
                            s
                            for s in group[col].tolist()
                            if s and s not in ("Not Available", "Not Applicable")
                        }
                    )
                )
        refunds.append(
            {
                "order_id": order_id,
                "order_date": return_date,
                "total": total,
                "payments": [],
                "last4s": [],
                "addresses": [],
                "status": statuses,
                "items": items,
                "shipments": [
                    {
                        "key": "digital_refund",
                        "tracking": "",
                        "ship_date": return_raw or "",
                        "total": total,
                        "items": items,
                        "addresses": [],
                    }
                ],
                "source": "digital_refund",
                "match_kind": "refund",
                "match_level": "refund",
                "matched_total": total,
                "return_date": return_date,
            }
        )
    return refunds


def load_physical_refund_summaries(path=None, orders_by_id=None):
    """
    Refund Details.csv → refund summaries (physical / retail).
    Attaches Order History items when orders_by_id is provided.
    """
    path = path or resolve_refund_details_path()
    if not path or not os.path.isfile(path):
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "Order ID" not in df.columns or "Refund Amount" not in df.columns:
        return []
    orders_by_id = orders_by_id or {}
    refunds = []
    for _, row in df.iterrows():
        total = money(row.get("Refund Amount"))
        if total <= 0:
            continue
        order_id = (row.get("Order ID") or "").strip()
        return_date = parse_order_date(
            row.get("Refund Date") or row.get("Creation Date") or ""
        )
        order = orders_by_id.get(order_id) or {}
        items = list(order.get("items") or [])
        if not items:
            reason = (row.get("Reversal Reason") or "").strip() or "Refund"
            items = [
                {
                    "name": reason,
                    "qty": 1,
                    "line_total": total,
                    "unit": total,
                    "tax": 0.0,
                    "asin": "",
                }
            ]
        refunds.append(
            {
                "order_id": order_id,
                "order_date": return_date,
                "total": total,
                "payments": [],
                "last4s": list(order.get("last4s") or []),
                "addresses": list(order.get("addresses") or []),
                "status": [
                    s
                    for s in (
                        row.get("Payment Status"),
                        row.get("Reversal Status"),
                        row.get("Reversal Reason"),
                    )
                    if s
                ],
                "items": items,
                "shipments": [
                    {
                        "key": "physical_refund",
                        "tracking": "",
                        "ship_date": "",
                        "total": total,
                        "items": items,
                        "addresses": list(order.get("addresses") or []),
                    }
                ],
                "source": "physical_refund",
                "match_kind": "refund",
                "match_level": "refund",
                "matched_total": total,
                "return_date": return_date,
            }
        )
    return refunds


def load_order_index(
    order_history_path=None,
    include_cancelled=False,
    include_digital=True,
    digital_path=None,
    include_refunds=True,
):
    """
    Purchase orders (+ digital). Refunds are loaded separately via
    load_refund_index() so purchase matching does not hit refund amounts.
    """
    oh_path = order_history_path or resolve_order_history_path()
    dig_path = digital_path or resolve_digital_orders_path()
    df = load_orders(oh_path)
    orders = build_order_summaries(df, include_cancelled=include_cancelled)
    for o in orders:
        o.setdefault("source", "retail")
    if include_digital:
        orders.extend(load_digital_order_summaries(dig_path))
    return orders


def load_refund_index(orders=None):
    """Digital + physical refund summaries for matching statement credits."""
    by_id = _orders_by_id(orders or [])
    refunds = list(load_digital_refund_summaries())
    refunds.extend(load_physical_refund_summaries(orders_by_id=by_id))
    return refunds


def find_refunds_for_credit(
    refunds,
    amount,
    date=None,
    window_days=DEFAULT_DATE_WINDOW_DAYS,
    tolerance=DEFAULT_TOLERANCE,
):
    """Match a statement credit (refund) to Digital/physical refund rows."""
    amount = float(amount)
    hits = []
    for refund in refunds or []:
        total = float(refund.get("total") or refund.get("matched_total") or 0)
        info = amount_match_info(
            total, amount, tolerance=tolerance, allow_integer_rewards=False
        )
        if info is None:
            continue
        delta, basis = _best_date_delta(refund, date) if date is not None else (None, None)
        if date is not None:
            if delta is None or delta > window_days:
                continue
        annotated = dict(refund)
        annotated.update(
            {
                "match_kind": "refund",
                "match_level": "refund",
                "matched_total": total,
                "rewards_dollars": 0,
                "match_items": list(refund.get("items") or []),
                "matched_tracking": "",
                "date_delta_days": delta,
                "date_basis": basis or "return",
                "amount_match": info.get("kind") or "exact",
            }
        )
        hits.append(annotated)
    hits.sort(
        key=lambda h: (
            h.get("date_delta_days") if h.get("date_delta_days") is not None else 999,
            -float(h.get("matched_total") or 0),
            h.get("order_id") or "",
        )
    )
    return hits


def order_claims_from_progress(progress, except_index=None):
    """
    Sum prior approvals per Amazon order on this statement.

    Returns {order_id: {"amount": float, "trackings": set([str]), "count": int}}.
    Partial shipment approvals leave a remainder (order total − claimed amount)
    available for later charges.

    Gift-card partial matches (card residual only; gift covered the rest) claim
    the full order_total so we do not look for a second card charge that never
    posts.
    """
    claims = {}
    for i, row in enumerate((progress or {}).get("charges") or []):
        if except_index is not None and i == except_index:
            continue
        if not row.get("reviewed"):
            continue
        qif = row.get("qif") or {}
        oid = (qif.get("order_id") or "").strip()
        if not oid:
            continue
        entry = claims.setdefault(oid, {"amount": 0.0, "trackings": set(), "count": 0})
        kind = (qif.get("match_kind") or "").strip()
        level = (qif.get("match_level") or "").strip()
        if kind == "gift_card_partial" or level == "gift_card":
            order_total = float(qif.get("order_total") or 0)
            charge_amt = float(qif.get("amount") or 0)
            # Prefer stored order total; fall back to charge if missing.
            claim_amt = order_total if order_total > 0 else charge_amt
            if claim_amt > entry["amount"]:
                entry["amount"] = round(claim_amt, 2)
        else:
            entry["amount"] = round(
                entry["amount"] + float(qif.get("amount") or 0), 2
            )
        entry["count"] += 1
        tracking = (qif.get("matched_tracking") or "").strip()
        if tracking:
            entry["trackings"].add(tracking)
    return claims


def _orders_by_id(orders):
    return {str(o.get("order_id") or "").strip(): o for o in orders or []}


def _remaining_items(order, claim):
    """Items not on a already-claimed shipment tracking (or all items if unknown)."""
    items = list(order.get("items") or [])
    trackings = (claim or {}).get("trackings") or set()
    if not trackings:
        return items
    left = []
    for item in items:
        track = (item.get("tracking") or item.get("_ship_key") or "").strip()
        if track and track in trackings:
            continue
        left.append(item)
    return left if left else items


def apply_order_claims(hits, orders, amount, order_claims=None, date=None):
    """
    Process-of-elimination against prior approvals on this statement.

    - Fully claimed orders (claimed >= order total) are dropped.
    - Already-used shipment trackings are dropped.
    - Full-order hits are dropped once any amount has been claimed (use remainder).
    - If charge amount equals leftover order balance, add a remainder match.
    """
    hits = list(hits or [])
    if not order_claims:
        return hits

    by_id = _orders_by_id(orders)
    amount = float(amount)
    kept = []
    seen_remainder = set()

    for hit in hits:
        oid = str(hit.get("order_id") or "").strip()
        claim = order_claims.get(oid)
        if not claim:
            kept.append(hit)
            continue
        order = by_id.get(oid)
        order_total = float(order.get("total") or 0) if order else 0.0
        claimed = float(claim.get("amount") or 0)
        remaining = round(order_total - claimed, 2) if order_total else None

        if remaining is not None and remaining <= 0.005:
            continue  # fully allocated

        tracking = (hit.get("matched_tracking") or "").strip()
        if tracking and tracking in (claim.get("trackings") or set()):
            continue

        level = hit.get("match_level") or "order"
        if level == "order" and claimed > 0.005:
            # Prior partial claim — do not re-offer the full order total.
            continue

        matched_total = float(hit.get("matched_total") or hit.get("total") or 0)
        if remaining is not None and matched_total > remaining + 0.005:
            continue

        annotated = dict(hit)
        if remaining is not None and claimed > 0.005:
            annotated["order_remaining"] = remaining
            annotated["order_claimed"] = claimed
        kept.append(annotated)

    # Explicit remainder candidates when leftover equals this charge.
    for oid, claim in order_claims.items():
        order = by_id.get(oid)
        if not order:
            continue
        order_total = float(order.get("total") or 0)
        claimed = float(claim.get("amount") or 0)
        remaining = round(order_total - claimed, 2)
        if remaining <= 0.005:
            continue
        if abs(remaining - amount) > 0.001:
            continue
        if oid in seen_remainder:
            continue
        # Skip if a shipment/line hit already covers this remaining package.
        if any(
            str(h.get("order_id") or "").strip() == oid
            and abs(float(h.get("matched_total") or 0) - amount) < 0.001
            for h in kept
        ):
            continue
        seen_remainder.add(oid)
        items = _remaining_items(order, claim)
        remainder_hit = dict(order)
        remainder_hit.update(
            {
                "match_kind": "exact",
                "match_level": "remainder",
                "matched_total": remaining,
                "rewards_dollars": 0,
                "match_items": items,
                "matched_tracking": "",
                "order_remaining": remaining,
                "order_claimed": claimed,
                "date_delta_days": None,
                "date_basis": "remainder",
            }
        )
        # Reuse ship/order date proximity for sorting when possible
        delta, basis = _best_date_delta(order, date) if date is not None else (None, None)
        remainder_hit["date_delta_days"] = delta
        if basis:
            remainder_hit["date_basis"] = basis
        kept.insert(0, remainder_hit)

    return kept


def find_orders_for_charge(
    orders,
    amount,
    date=None,
    last4="5144",
    window_days=DEFAULT_DATE_WINDOW_DAYS,
    tolerance=DEFAULT_TOLERANCE,
    allow_integer_rewards=None,
    max_rewards_dollars=DEFAULT_MAX_REWARDS_DOLLARS,
    rewards_window_days=DEFAULT_REWARDS_WINDOW_DAYS,
    order_claims=None,
    exclude_order_ids=None,
):
    hits = match_orders(
        orders,
        amount=float(amount),
        date=date,
        last4=last4,
        tolerance=tolerance,
        window_days=window_days,
        allow_integer_rewards=allow_integer_rewards,
        max_rewards_dollars=max_rewards_dollars,
        rewards_window_days=rewards_window_days,
    )
    # Legacy: treat full exclude list as fully claimed (no remainder).
    claims = dict(order_claims or {})
    if exclude_order_ids:
        for oid in exclude_order_ids:
            oid = str(oid or "").strip()
            if not oid or oid in claims:
                continue
            order = _orders_by_id(orders).get(oid)
            total = float(order.get("total") or 0) if order else 0.0
            claims[oid] = {
                "amount": total if total else 1e9,
                "trackings": set(),
                "count": 1,
            }
    return apply_order_claims(
        hits, orders, amount=amount, order_claims=claims, date=date
    )


def _match_identity(order):
    return (
        order.get("order_id"),
        order.get("match_level"),
        order.get("matched_tracking") or "",
        round(float(order.get("matched_total") or 0), 2),
        order.get("match_kind"),
        int(order.get("rewards_dollars") or 0),
    )


def find_near_miss_orders(
    orders,
    amount,
    date=None,
    last4="5144",
    window_days=DEFAULT_DATE_WINDOW_DAYS,
    rewards_window_days=DEFAULT_REWARDS_WINDOW_DAYS,
    near_window_days=DEFAULT_NEAR_MISS_WINDOW_DAYS,
    max_rewards_dollars=DEFAULT_MAX_REWARDS_DOLLARS,
    order_claims=None,
    exclude_order_ids=None,
):
    """
    Amount matches outside the primary date windows but within near_window_days.

    Honors partial claims: leftover balance on a partially approved order can
    still surface (remainder / unused shipment).
    """
    primary = find_orders_for_charge(
        orders,
        amount=amount,
        date=date,
        last4=last4,
        window_days=window_days,
        rewards_window_days=rewards_window_days,
        max_rewards_dollars=max_rewards_dollars,
        order_claims=order_claims,
        exclude_order_ids=exclude_order_ids,
    )
    primary_ids = {_match_identity(o) for o in primary}
    loose = find_orders_for_charge(
        orders,
        amount=amount,
        date=date,
        last4=last4,
        window_days=near_window_days,
        rewards_window_days=near_window_days,
        max_rewards_dollars=max_rewards_dollars,
        allow_integer_rewards=date is not None,
        order_claims=order_claims,
        exclude_order_ids=exclude_order_ids,
    )
    near = []
    for order in loose:
        if _match_identity(order) in primary_ids:
            continue
        delta = order.get("date_delta_days")
        basis = order.get("date_basis") or "order"
        annotated = dict(order)
        if order.get("match_level") == "remainder":
            why = "remainder ${:.2f} after prior claim(s)".format(
                float(order.get("matched_total") or 0)
            )
        elif order.get("match_kind") == "rewards":
            why = "rewards via {} ±{}d (outside ±{}d)".format(
                basis,
                delta if delta is not None else "?",
                rewards_window_days,
            )
        else:
            why = "exact via {} ±{}d (outside ±{}d)".format(
                basis,
                delta if delta is not None else "?",
                window_days,
            )
        annotated["near_miss_reason"] = why
        near.append(annotated)
    return near


def match_qif_to_orders(
    qif_path,
    order_history_path=None,
    last4="5144",
    window_days=DEFAULT_DATE_WINDOW_DAYS,
    amazon_only=True,
):
    """
    Pair each eligible QIF purchase with Order History matches.

    Returns dict with rows, counts, and match_rate among attempted rows.
    """
    txns = parse_ccard_qif(qif_path)
    orders = load_order_index(order_history_path=order_history_path)

    rows = []
    attempted = 0
    matched = 0
    ambiguous = 0
    unmatched = 0
    skipped = 0

    for txn in txns:
        if is_skippable_for_orders(txn):
            skipped += 1
            rows.append({"txn": txn, "status": "skipped", "orders": []})
            continue
        if amazon_only and not is_amazon_like_payee(txn.get("payee")):
            skipped += 1
            rows.append({"txn": txn, "status": "skipped_non_amazon", "orders": []})
            continue

        attempted += 1
        amt = charge_amount(txn)
        hits = find_orders_for_charge(
            orders,
            amount=amt,
            date=txn.get("date"),
            last4=last4,
            window_days=window_days,
        )
        if not hits:
            unmatched += 1
            status = "unmatched"
        elif len(hits) == 1:
            matched += 1
            status = "matched"
        else:
            ambiguous += 1
            status = "ambiguous"
        rows.append({"txn": txn, "status": status, "orders": hits})

    rate = (float(matched) / attempted) if attempted else 0.0
    return {
        "rows": rows,
        "orders_count": len(orders),
        "txn_count": len(txns),
        "attempted": attempted,
        "matched": matched,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
        "skipped": skipped,
        "match_rate": rate,
        # unique matches usable for training (exactly one order)
        "train_pairs": [
            r for r in rows if r["status"] == "matched" and r["orders"]
        ],
    }


def summarize_match_report(result):
    lines = [
        "QIF transactions: {}".format(result["txn_count"]),
        "Order History orders: {}".format(result["orders_count"]),
        "Skipped (payments/transfers/non-Amazon): {}".format(result["skipped"]),
        "Attempted Amazon-like purchases: {}".format(result["attempted"]),
        "Exact unique match: {} ({:.1%})".format(
            result["matched"], result["match_rate"]
        ),
        "Ambiguous (multiple orders): {}".format(result["ambiguous"]),
        "Unmatched: {}".format(result["unmatched"]),
    ]
    return "\n".join(lines)
