"""Persist human-reviewed charge progress to JSON (crash-safe resume)."""

from __future__ import print_function

import glob
import hashlib
import json
import os
import re
from datetime import datetime

from amazon_cc.qif_io import is_positive_ccard_qif_fields
from amazon_cc.statements import (
    legacy_statement_ids_from_path,
    statement_id_from_path,
)

PROGRESS_DIR = os.path.join("amazon", "review_progress")


def _legacy_safe_stem(path):
    """Old path-hash stem (kept so July progress can be migrated)."""
    base = os.path.basename(path) or "charges"
    stem = os.path.splitext(base)[0]
    stem = re.sub(r"[^\w.\-]+", "_", stem).strip("_")
    digest = hashlib.sha1(os.path.normpath(path).encode("utf-8")).hexdigest()[:8]
    return "{}_{}".format(stem[:80] or "charges", digest)


def progress_path_for(source_path, progress_dir=PROGRESS_DIR):
    """Stable path keyed by statement id (survives [APPROVED]/[REC] renames)."""
    sid = statement_id_from_path(source_path)
    return os.path.join(progress_dir, sid + ".json")


def _progress_file_rank(path):
    """Higher = better resume source (approved/reconciled beats empty stub)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return (0, 0, 0, path)
    stage = (saved.get("stage") or "").lower()
    stage_score = {"reconciled": 3, "approved": 2, "unreconciled": 1}.get(stage, 0)
    reviewed = sum(
        1 for r in (saved.get("charges") or []) if r.get("reviewed") or r.get("skipped")
    )
    has_qif = 1 if saved.get("qif_path") else 0
    return (stage_score, has_qif, reviewed, path)


def _find_existing_progress_file(source_path, progress_dir=PROGRESS_DIR):
    """Prefer richest matching progress (approved/qif), then canonical id."""
    stable = progress_path_for(source_path, progress_dir)
    sid = statement_id_from_path(source_path)
    id_stems = [sid] + legacy_statement_ids_from_path(source_path)
    candidates = []
    if os.path.isfile(stable):
        candidates.append(stable)
    for stem in id_stems:
        exact = os.path.join(progress_dir, stem + ".json")
        if os.path.isfile(exact):
            candidates.append(exact)
        candidates.extend(glob.glob(os.path.join(progress_dir, stem + "_*.json")))
        candidates.extend(glob.glob(os.path.join(progress_dir, stem + "*.json")))
    legacy = os.path.join(progress_dir, _legacy_safe_stem(source_path) + ".json")
    if os.path.isfile(legacy):
        candidates.append(legacy)

    uniq = {os.path.normpath(p) for p in candidates if os.path.isfile(p)}
    if not uniq:
        return stable

    # Prefer most advanced stage / qif / reviewed rows; break ties toward canonical.
    def _sort_key(p):
        stage_score, has_qif, reviewed, _path = _progress_file_rank(p)
        return (
            stage_score,
            has_qif,
            reviewed,
            1 if os.path.basename(p) == sid + ".json" else 0,
            p,
        )

    return max(uniq, key=_sort_key)


def charge_key(charge):
    """Stable id for a statement line: date|amount|payee."""
    d = charge.get("date")
    if isinstance(d, datetime):
        ds = d.strftime("%Y-%m-%d")
    else:
        ds = str(d or "")[:10]
    amt = "{:.2f}".format(float(charge.get("amount") or 0))
    payee = (charge.get("payee") or "").strip()
    return "{}|{}|{}".format(ds, amt, payee)


def empty_progress(source_path, charges):
    rows = []
    for i, c in enumerate(charges):
        rows.append(
            {
                "index": i,
                "key": charge_key(c),
                "date": c["date"].strftime("%Y-%m-%d") if c.get("date") else "",
                "amount": float(c.get("amount") or 0),
                "payee_statement": c.get("payee") or "",
                "reviewed": False,
                "skipped": False,
                "qif": None,
            }
        )
    return {
        "version": 1,
        "statement_id": statement_id_from_path(source_path),
        "source": os.path.normpath(source_path),
        "stage": "unreconciled",
        "qif_path": None,
        "approved_at": None,
        "reconciled_at": None,
        "side_tasks": [],
        "updated": datetime.now().isoformat(timespec="seconds"),
        "charges": rows,
    }


# 5144 Amazon card is paid by BofA 0149; CH spend belongs on Carriage House 4900.
CH_TRANSFER_TASK_ID = "ch_reimburse_4900"
CH_CARD_LAST4 = "5144"
CH_PAYING_CHECKING = "0149"
CH_REIMBURSE_FROM = "4900"


def is_ch_category(category):
    """True for CH or CH:… Quicken categories (Carriage House)."""
    cat = (category or "").strip()
    if not cat:
        return False
    root = cat.split(":", 1)[0].strip()
    return root.upper() == "CH"


def ch_reviewed_rows(progress):
    """Reviewed QIF rows categorized to CH:*."""
    out = []
    for row in progress.get("charges") or []:
        if not row.get("reviewed") or not row.get("qif"):
            continue
        if is_ch_category(row["qif"].get("category")):
            out.append(row)
    return out


def summarize_ch_charges(progress):
    rows = ch_reviewed_rows(progress)
    total = round(sum(float(r["qif"]["amount"]) for r in rows), 2)
    return {
        "count": len(rows),
        "amount": total,
        "keys": [r.get("key") for r in rows],
        "memos": [
            (r["qif"].get("memo") or r.get("payee_statement") or "").strip()
            for r in rows
        ],
    }


def build_ch_transfer_task(progress, prior_task=None):
    """
    Side task: transfer CH totals off 5144/0149 via Carriage House 4900.
    Returns None when there is no CH spend this statement.
    """
    summary = summarize_ch_charges(progress)
    if summary["amount"] <= 0 or summary["count"] == 0:
        return None

    prior = prior_task or {}
    same_amount = abs(float(prior.get("amount") or 0) - summary["amount"]) < 0.001
    same_keys = list(prior.get("charge_keys") or []) == list(summary["keys"])
    keep_done = bool(prior.get("done")) and same_amount and same_keys

    return {
        "id": CH_TRANSFER_TASK_ID,
        "type": "transfer",
        "title": "CH reimbursement from {}".format(CH_REIMBURSE_FROM),
        "detail": (
            "Amazon {} is paid by checking {}. CH categories on this card should be "
            "reimbursed from Carriage House {} (see Walnut apartment processes)."
        ).format(CH_CARD_LAST4, CH_PAYING_CHECKING, CH_REIMBURSE_FROM),
        "amount": summary["amount"],
        "count": summary["count"],
        "from_account": CH_REIMBURSE_FROM,
        "for_card": CH_CARD_LAST4,
        "paid_by_checking": CH_PAYING_CHECKING,
        "charge_keys": summary["keys"],
        "memos": summary["memos"],
        "done": keep_done,
        "done_at": prior.get("done_at") if keep_done else None,
    }


def sync_ch_transfer_side_task(progress):
    """Refresh/replace the CH transfer side task from reviewed categories."""
    tasks = list(progress.get("side_tasks") or [])
    prior = None
    kept = []
    for task in tasks:
        if task.get("id") == CH_TRANSFER_TASK_ID:
            prior = task
        else:
            kept.append(task)
    fresh = build_ch_transfer_task(progress, prior_task=prior)
    if fresh:
        kept.insert(0, fresh)
    progress["side_tasks"] = kept
    return progress


def set_side_task_done(progress, task_id, done=True):
    for task in progress.get("side_tasks") or []:
        if task.get("id") != task_id:
            continue
        task["done"] = bool(done)
        task["done_at"] = (
            datetime.now().isoformat(timespec="seconds") if done else None
        )
        return progress
    raise KeyError("side task not found: {}".format(task_id))


def open_side_tasks(progress):
    return [t for t in (progress.get("side_tasks") or []) if not t.get("done")]


def load_progress(source_path, charges, progress_dir=PROGRESS_DIR):
    """
    Load or create progress for this source. Merges prior reviewed rows by key
    onto the freshly parsed charge list. Migrates legacy hashed filenames to the
    stable statement-id path.
    """
    stable_path = progress_path_for(source_path, progress_dir)
    existing = _find_existing_progress_file(source_path, progress_dir)
    fresh = empty_progress(source_path, charges)

    if not os.path.isfile(existing):
        return fresh, stable_path

    try:
        with open(existing, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return fresh, stable_path

    by_key = {}
    for row in saved.get("charges") or []:
        by_key[row.get("key")] = row

    merged = []
    for row in fresh["charges"]:
        prev = by_key.get(row["key"])
        if prev and (prev.get("reviewed") or prev.get("skipped")):
            row = dict(row)
            row["reviewed"] = bool(prev.get("reviewed"))
            row["skipped"] = bool(prev.get("skipped"))
            row["qif"] = prev.get("qif")
            if prev.get("suggested") is not None:
                row["suggested"] = prev.get("suggested")
        merged.append(row)

    fresh["charges"] = merged
    fresh["updated"] = saved.get("updated") or fresh["updated"]
    fresh["stage"] = saved.get("stage") or fresh["stage"]
    fresh["qif_path"] = saved.get("qif_path")
    fresh["approved_at"] = saved.get("approved_at")
    fresh["reconciled_at"] = saved.get("reconciled_at")
    fresh["side_tasks"] = list(saved.get("side_tasks") or [])
    fresh["source"] = os.path.normpath(source_path)
    fresh["statement_id"] = statement_id_from_path(source_path)

    # Migrate off legacy hashed filename when needed
    if os.path.normpath(existing) != os.path.normpath(stable_path):
        save_progress(fresh, stable_path)
        return fresh, stable_path

    return fresh, stable_path


def save_progress(progress, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    progress = dict(progress)
    progress["updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(progress, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def first_unreviewed_index(progress):
    """First charge that still needs Approve. Skips do not count as done."""
    for i, row in enumerate(progress.get("charges") or []):
        if not row.get("reviewed"):
            return i
    return len(progress.get("charges") or [])


def mark_reviewed(progress, index, qif_fields, suggested=None):
    """
    Persist a human-approved QIF row.

    qif_fields: date (MM/DD/YYYY str or datetime), amount positive, payee, memo,
    category, order_id.

    suggested (optional): model guess at approve time — payee / memo / category /
    reason — kept separate from qif so training can compare original statement
    fields, suggestion, and manual adjustment.
    """
    rows = progress["charges"]
    if index < 0 or index >= len(rows):
        raise IndexError("charge index out of range")
    row = rows[index]
    dt = qif_fields.get("date")
    if isinstance(dt, datetime):
        date_s = dt.strftime("%m/%d/%Y")
        date_iso = dt.strftime("%Y-%m-%d")
    else:
        date_s = str(dt)
        try:
            date_iso = datetime.strptime(date_s.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            date_iso = date_s
    row["reviewed"] = True
    row["skipped"] = False
    if suggested is not None:
        row["suggested"] = {
            "payee": suggested.get("payee") or "",
            "memo": suggested.get("memo") or "",
            "category": suggested.get("category") or "",
            "reason": suggested.get("reason") or "",
        }
    qif = {
        "date": date_s,
        "date_iso": date_iso,
        "amount": float(qif_fields["amount"]),
        "payee": qif_fields.get("payee") or "Amazon",
        "memo": qif_fields.get("memo") or "",
        "category": qif_fields.get("category") or "",
        "order_id": qif_fields.get("order_id") or "",
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
    }
    # Partial-match bookkeeping so later charges can claim the remainder.
    if qif_fields.get("match_level"):
        qif["match_level"] = qif_fields.get("match_level") or ""
    if qif_fields.get("match_kind"):
        qif["match_kind"] = qif_fields.get("match_kind") or ""
    if qif_fields.get("matched_tracking"):
        qif["matched_tracking"] = qif_fields.get("matched_tracking") or ""
    if qif_fields.get("matched_total") is not None and qif_fields.get("matched_total") != "":
        try:
            qif["matched_total"] = float(qif_fields["matched_total"])
        except (TypeError, ValueError):
            pass
    if qif_fields.get("order_total") is not None and qif_fields.get("order_total") != "":
        try:
            qif["order_total"] = float(qif_fields["order_total"])
        except (TypeError, ValueError):
            pass
    row["qif"] = qif
    return progress


def mark_skipped(progress, index):
    rows = progress["charges"]
    if index < 0 or index >= len(rows):
        raise IndexError("charge index out of range")
    row = rows[index]
    row["skipped"] = True
    if not row.get("reviewed"):
        row["qif"] = row.get("qif")
    return progress


def reviewed_count(progress):
    return sum(1 for r in progress.get("charges") or [] if r.get("reviewed"))


def skipped_count(progress):
    return sum(1 for r in progress.get("charges") or [] if r.get("skipped"))


def all_charges_reviewed(progress):
    """True only when every charge is reviewed (skips do not count)."""
    rows = progress.get("charges") or []
    if not rows:
        return False
    return all(r.get("reviewed") for r in rows)


def mark_progress_approved(progress, qif_path):
    progress["stage"] = "approved"
    progress["qif_path"] = qif_path
    progress["approved_at"] = datetime.now().isoformat(timespec="seconds")
    sync_ch_transfer_side_task(progress)
    return progress


def mark_progress_reconciled(progress):
    progress["stage"] = "reconciled"
    progress["reconciled_at"] = datetime.now().isoformat(timespec="seconds")
    return progress


def qif_transactions_from_progress(progress):
    """Build write_ccard_qif transaction list from reviewed rows only.

    Newest-first order and C* cleared status match Airbnb / Schwab QIF imports.
    """
    txns = []
    for row in progress.get("charges") or []:
        if not row.get("reviewed") or not row.get("qif"):
            continue
        q = row["qif"]
        try:
            dt = datetime.strptime(q["date"].strip(), "%m/%d/%Y")
        except ValueError:
            dt = datetime.strptime(q.get("date_iso") or row["date"], "%Y-%m-%d")
        amt = abs(float(q["amount"]))
        # Purchases are negative on CCard; payments and refunds are positive.
        signed = amt if is_positive_ccard_qif_fields(q) else -amt
        txns.append(
            {
                "date": dt,
                "amount": signed,
                "payee": q.get("payee") or "Amazon",
                "memo": q.get("memo") or "",
                "category": q.get("category") or "",
                "cleared": "*",
                "splits": [],
                "order_id": q.get("order_id") or "",
            }
        )
    # Newest first (same ordering as Airbnb / Schwab QIF imports).
    txns.sort(
        key=lambda t: (t["date"], t.get("payee") or "", t["amount"], t.get("memo") or ""),
        reverse=True,
    )
    return txns
