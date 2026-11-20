"""Dashboard status + ordered next-up tasks for the Amazon CC reviewer."""

from __future__ import print_function

import json
import os
from datetime import datetime

import pandas as pd

from amazon_cc.progress import (
    CH_TRANSFER_TASK_ID,
    all_charges_reviewed,
    load_progress,
    open_side_tasks,
    progress_path_for,
    reviewed_count,
    skipped_count,
)
from amazon_cc.amazon_data import (
    digital_orders_path,
    ingest_pending_amazon_exports,
    live_orders_dir,
    order_history_path,
    resolve_amazon_data_dir,
)
from amazon_cc.statements import (
    STATEMENT_FILENAME_DAY,
    STATEMENT_PUBLISH_DAY,
    expected_statement_periods,
    find_statement_for_period,
    list_statement_pdfs,
    load_charges,
    match_statement_name,
    next_incomplete_statement,
    normalize_downloaded_statements,
    parse_statement_period,
    qif_basename_for_statement,
    reconciled_through_date,
    resolve_qif_dir,
    resolve_statements_dir,
    statement_display_label,
    statement_stage,
)


def amazon_data_through(order_history=None, digital=None):
    """
    Latest usable Amazon export date (max of order/ship/digital dates).
    Returns datetime (naive) or None.
    """
    order_history = order_history or order_history_path()
    digital = digital or digital_orders_path()
    dates = []
    for path, cols in (
        (order_history, ("Order Date", "Ship Date")),
        (digital, ("Order Date", "Delivery Date", "Fulfilled Date")),
    ):
        if not path or not os.path.isfile(path):
            continue
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=lambda c: True)
        except Exception:
            continue
        for col in cols:
            if col not in df.columns:
                continue
            series = pd.to_datetime(df[col], errors="coerce", utc=True)
            mx = series.max()
            if pd.notna(mx):
                dates.append(mx.to_pydatetime().replace(tzinfo=None))
    return max(dates) if dates else None


def _charge_stats_for_path(path):
    """
    Return {total, reviewed, skipped, remaining, ready_to_export, stage, error}.
    Uses progress JSON when present; otherwise parses the statement.
    """
    stage = statement_stage(path)
    stats = {
        "path": path,
        "stage": stage,
        "label": statement_display_label(path),
        "period": parse_statement_period(path),
        "total": 0,
        "reviewed": 0,
        "skipped": 0,
        "remaining": 0,
        "ready_to_export": False,
        "side_tasks_open": 0,
        "error": None,
    }
    try:
        charges = load_charges(path)
    except Exception as exc:
        stats["error"] = str(exc)
        return stats

    progress = None
    ppath = progress_path_for(path)
    if os.path.isfile(ppath) or charges:
        try:
            progress, _ = load_progress(path, charges)
        except Exception:
            progress = None

    total = len(charges)
    stats["total"] = total
    if progress:
        stats["reviewed"] = reviewed_count(progress)
        stats["skipped"] = skipped_count(progress)
        stats["ready_to_export"] = (
            stage == "unreconciled" and all_charges_reviewed(progress)
        )
        stats["side_tasks_open"] = len(open_side_tasks(progress))
        # Prefer progress stage when more advanced than filename (rare edge)
        pstage = (progress.get("stage") or "").lower()
        if pstage in ("approved", "reconciled") and stage == "unreconciled":
            stats["stage"] = pstage
    else:
        stats["reviewed"] = 0
        stats["skipped"] = 0

    if stats["stage"] == "unreconciled":
        stats["remaining"] = max(total - stats["reviewed"], 0)
    else:
        stats["remaining"] = 0
    return stats


def build_statement_inventory(statements_dir=None):
    """Inventory of all statements with charge counts (chronological)."""
    listed = list_statement_pdfs(statements_dir)
    rows = []
    for stage in ("reconciled", "approved", "unreconciled"):
        for path in listed.get(stage) or []:
            rows.append(_charge_stats_for_path(path))
    rows.sort(key=lambda r: (r.get("period") or datetime.max, r["path"]))
    return {
        "dir": listed.get("dir"),
        "hidden_downloads": list(listed.get("hidden_downloads") or []),
        "statements": rows,
        "unreconciled": [r for r in rows if r["stage"] == "unreconciled"],
        "approved": [r for r in rows if r["stage"] == "approved"],
        "reconciled": [r for r in rows if r["stage"] == "reconciled"],
    }


def build_status_summary(inventory=None, statements_dir=None, amazon_through=None):
    """Top-of-dashboard KPIs."""
    inventory = inventory or build_statement_inventory(statements_dir)
    rec_through = reconciled_through_date(inventory.get("dir"))
    incomplete = inventory["unreconciled"] + inventory["approved"]
    txns_left = sum(r.get("remaining") or 0 for r in inventory["unreconciled"])
    txns_to_reconcile = sum(r.get("total") or 0 for r in inventory["approved"])
    next_path = None
    if inventory["unreconciled"]:
        next_path = inventory["unreconciled"][0]["path"]
    elif inventory["approved"]:
        next_path = inventory["approved"][0]["path"]

    if amazon_through is None:
        amazon_through = amazon_data_through()

    return {
        "reconciled_through": rec_through,
        "amazon_through": amazon_through,
        "unreconciled_count": len(inventory["unreconciled"]),
        "approved_count": len(inventory["approved"]),
        "reconciled_count": len(inventory["reconciled"]),
        "transactions_left_to_review": txns_left,
        "transactions_waiting_quicken": txns_to_reconcile,
        "next_path": next_path,
        "next_label": statement_display_label(next_path) if next_path else None,
        "statements_behind": len(incomplete),
    }


def _format_short_date(dt):
    if not dt:
        return "—"
    return "{}/{}/{}".format(dt.month, dt.day, dt.strftime("%y"))


def build_dashboard_tasks(
    inventory=None,
    statements_dir=None,
    amazon_through=None,
    today=None,
):
    """
    Ordered next-up tasks for the operator.

    Priority:
      1) Download missing statement(s) that should already be available
      2) Refresh Amazon Order History through a needed statement date
      3) Review / finish approving charges (earliest first)
      4) Export QIF when a statement is fully approved
      5) Mark reconciled after Quicken (approved stage)
      6) Open side tasks (e.g. CH reimbursement)
    """
    today = today or datetime.now()
    inventory = inventory or build_statement_inventory(statements_dir)
    statements_dir = inventory.get("dir") or statements_dir
    if amazon_through is None:
        amazon_through = amazon_data_through()

    tasks = []
    rec_through = reconciled_through_date(statements_dir)

    # --- Missing statements that should already be published ---
    expected = expected_statement_periods(through_date=today, start_after=rec_through)
    for exp in expected:
        path = find_statement_for_period(
            statements_dir, exp["year"], exp["month"], include_downloads=True
        )
        if path:
            continue
        mon = exp["period"].strftime("%b")
        # Prefer archive month spelling via display helpers
        label = "{} {} {}".format(exp["year"], mon, exp["day"])
        tasks.append(
            {
                "id": "download_statement_{}_{:02d}".format(exp["year"], exp["month"]),
                "kind": "download_statement",
                "priority": 10,
                "title": "Download Chase statement for {}".format(label),
                "detail": (
                    "A statement dated around the {}th should be available in "
                    "Chase (publish ~day {}). Save it into the 5144 folder."
                ).format(STATEMENT_FILENAME_DAY, STATEMENT_PUBLISH_DAY),
                "period": exp["period"],
                "path": None,
            }
        )

    # --- Amazon coverage: one task through the earliest incomplete period we lack ---
    amazon_need = None
    amazon_for = None
    for row in inventory["unreconciled"] + inventory["approved"]:
        period = row.get("period")
        if not period:
            continue
        if amazon_through and amazon_through.date() >= period.date():
            continue
        amazon_need = period
        amazon_for = row
        break
    if amazon_need is not None:
        # If an earlier month is already reviewable, don't put Amazon refresh first.
        earliest_incomplete = None
        for row in inventory["unreconciled"] + inventory["approved"]:
            if row.get("period"):
                earliest_incomplete = row["period"]
                break
        blocks_next = (
            earliest_incomplete is None
            or earliest_incomplete.date() >= amazon_need.date()
        )
        tasks.append(
            {
                "id": "amazon_through_{}".format(amazon_need.strftime("%Y%m%d")),
                "kind": "amazon_data",
                "priority": 20 if blocks_next else 35,
                "title": "Update Amazon Order History through {}".format(
                    _format_short_date(amazon_need)
                ),
                "detail": (
                    "Current Amazon export goes through {}. "
                    "Needed before reviewing {}."
                ).format(
                    _format_short_date(amazon_through),
                    (amazon_for or {}).get("label")
                    or statement_display_label((amazon_for or {}).get("path") or ""),
                ),
                "period": amazon_need,
                "path": (amazon_for or {}).get("path"),
                "amazon_through": amazon_through,
            }
        )

    # --- Review / export for unreconciled ---
    for row in inventory["unreconciled"]:
        path = row["path"]
        period = row.get("period")
        blocked = bool(
            period
            and (not amazon_through or amazon_through.date() < period.date())
        )
        if row.get("ready_to_export"):
            tasks.append(
                {
                    "id": "export_{}".format(os.path.basename(path)),
                    "kind": "export_qif",
                    "priority": 40,
                    "title": "Export QIF & mark approved — {}".format(
                        statement_display_label(path, include_stage=False)
                    ),
                    "detail": "All {} charges approved.".format(row.get("total") or 0),
                    "period": period,
                    "path": path,
                    "blocked": blocked,
                }
            )
        else:
            left = row.get("remaining") or 0
            total = row.get("total") or 0
            # Unblocked reviews first (30); Amazon refresh (35); then blocked (36)
            tasks.append(
                {
                    "id": "review_{}".format(os.path.basename(path)),
                    "kind": "review",
                    "priority": 36 if blocked else 30,
                    "title": "Review charges — {}".format(
                        statement_display_label(path, include_stage=False)
                    ),
                    "detail": "{} of {} left to approve{}".format(
                        left,
                        total,
                        " (Amazon data may be incomplete)" if blocked else "",
                    ),
                    "period": period,
                    "path": path,
                    "blocked": blocked,
                    "remaining": left,
                    "total": total,
                }
            )

    # --- Mark reconciled for approved ---
    for row in inventory["approved"]:
        path = row["path"]
        tasks.append(
            {
                "id": "reconcile_{}".format(os.path.basename(path)),
                "kind": "mark_reconciled",
                "priority": 50,
                "title": "Mark reconciled in Quicken — {}".format(
                    statement_display_label(path, include_stage=False)
                ),
                "detail": (
                    "Import the exported QIF, reconcile in Quicken, then mark done "
                    "({} transactions)."
                ).format(row.get("total") or 0),
                "period": row.get("period"),
                "path": path,
            }
        )

    # --- Side tasks from progress of incomplete statements ---
    for row in inventory["unreconciled"] + inventory["approved"]:
        if not row.get("side_tasks_open"):
            continue
        path = row["path"]
        try:
            charges = load_charges(path)
            progress, _ = load_progress(path, charges)
        except Exception:
            continue
        for side in open_side_tasks(progress):
            if side.get("id") == CH_TRANSFER_TASK_ID:
                title = "Transfer ${:.2f} from 4900 → reimburse 5144/0149".format(
                    float(side.get("amount") or 0)
                )
            else:
                title = side.get("title") or "Side task"
            tasks.append(
                {
                    "id": "side_{}_{}".format(
                        os.path.basename(path), side.get("id") or "task"
                    ),
                    "kind": "side_task",
                    "priority": 60,
                    "title": title,
                    "detail": side.get("detail") or "",
                    "period": row.get("period"),
                    "path": path,
                    "side_task_id": side.get("id"),
                }
            )

    tasks.sort(
        key=lambda t: (
            t.get("priority") or 99,
            t.get("period") or datetime.max,
            t.get("title") or "",
        )
    )
    return tasks


def next_actionable_statement(tasks=None, inventory=None, statements_dir=None):
    """
    Statement path to auto-open: earliest review/export/reconcile task with a path.
    Falls back to next_incomplete_statement().
    """
    tasks = tasks if tasks is not None else build_dashboard_tasks(
        inventory=inventory, statements_dir=statements_dir
    )
    for task in tasks:
        if task.get("kind") in ("review", "export_qif", "mark_reconciled") and task.get(
            "path"
        ):
            if task.get("blocked"):
                continue
            return task["path"]
    # If everything is blocked by Amazon data, still open the earliest incomplete
    # so the user can inspect / pick another month.
    return next_incomplete_statement(statements_dir)


def _read_progress_json(path):
    """Load progress JSON if present — no PDF parse."""
    ppath = progress_path_for(path)
    if not os.path.isfile(ppath):
        return None, ppath
    try:
        with open(ppath, "r", encoding="utf-8") as fh:
            return json.load(fh), ppath
    except (OSError, ValueError):
        return None, ppath


def find_qifs_for_statement(path, qif_dir=None):
    """
    Locate exported / reconciled QIF files for a statement by expected basename.
    Returns dict with keys: approved (non-_reconcile), reconciled (_reconcile), all.
    """
    qif_dir = resolve_qif_dir(qif_dir)
    base = qif_basename_for_statement(path)
    stem, ext = os.path.splitext(base)
    ext = ext or ".QIF"
    approved = os.path.join(qif_dir, base)
    reconciled = os.path.join(qif_dir, stem + "_reconcile" + ext)
    found_approved = approved if os.path.isfile(approved) else None
    found_reconciled = reconciled if os.path.isfile(reconciled) else None
    return {
        "approved": found_approved,
        "reconciled": found_reconciled,
        "expected_approved": approved,
        "expected_reconciled": reconciled,
    }


def run_sync_audit(statements_dir=None, qif_dir=None, today=None, prior_tasks=None):
    """
    Quick file/name/count audit (no statement transaction parsing).

    - Renames new Chase downloads into archive names
    - Re-reads Amazon Order History coverage date
    - Checks expected statements exist for open download tasks
    - Checks PDF stage tags vs QIF filenames (_reconcile pairing)
    - Checks progress JSON stage vs filename stage
    - Reports stage counts and duplicate downloads

    Returns a report dict with ok / warnings / errors / resolved / counts.
    """
    today = today or datetime.now()
    statements_dir = resolve_statements_dir(statements_dir)
    qif_dir = resolve_qif_dir(qif_dir)
    report = {
        "ok": [],
        "warnings": [],
        "errors": [],
        "resolved": [],
        "counts": {},
        "renamed": [],
        "duplicates": [],
        "amazon_through": None,
        "reconciled_through": None,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "statements_dir": statements_dir,
        "qif_dir": qif_dir,
    }

    # 1) Ingest new Chase downloads
    norm = normalize_downloaded_statements(statements_dir)
    for item in norm.get("renamed") or []:
        report["renamed"].append(
            "{} → {}".format(
                os.path.basename(item["from"]), os.path.basename(item["to"])
            )
        )
        report["resolved"].append(
            "Renamed download to {}".format(os.path.basename(item["to"]))
        )
    for item in norm.get("duplicates") or []:
        report["duplicates"].append(os.path.basename(item["download"]))
    for err in norm.get("errors") or []:
        report["errors"].append("Rename failed: {}".format(err))

    # 1b) Amazon Data: migrate legacy + archive/swap inbound Your Orders (N)
    amazon_ingest = ingest_pending_amazon_exports()
    report["amazon_data_dir"] = amazon_ingest.get("dir")
    for msg in amazon_ingest.get("messages") or []:
        report["resolved"].append(msg)
    if amazon_ingest.get("pending_left"):
        report["warnings"].append(
            "Extra Amazon inbound folders left: {}".format(
                ", ".join(amazon_ingest["pending_left"])
            )
        )
    live = live_orders_dir()
    if os.path.isdir(live):
        report["ok"].append("Amazon live data: {}".format(live))
    else:
        report["errors"].append(
            "No live Amazon Your Orders under {}".format(resolve_amazon_data_dir())
        )

    listed = list_statement_pdfs(statements_dir)
    unrec = listed.get("unreconciled") or []
    approved = listed.get("approved") or []
    reconciled = listed.get("reconciled") or []
    hidden = listed.get("hidden_downloads") or []

    report["counts"] = {
        "unreconciled": len(unrec),
        "approved": len(approved),
        "reconciled": len(reconciled),
        "hidden_downloads": len(hidden),
        "amazon_5144_qifs": 0,
    }

    # 2) Amazon coverage (date columns only)
    amazon_through = amazon_data_through()
    report["amazon_through"] = amazon_through
    if amazon_through:
        report["ok"].append(
            "Amazon Order History through {}".format(_format_short_date(amazon_through))
        )
    else:
        report["errors"].append("Amazon Order History not found or has no dates")

    rec_through = reconciled_through_date(statements_dir)
    report["reconciled_through"] = rec_through
    if rec_through:
        report["ok"].append(
            "Reconciled through {}".format(_format_short_date(rec_through))
        )

    # 3) Missing expected statements (download tasks)
    expected = expected_statement_periods(through_date=today, start_after=rec_through)
    for exp in expected:
        path = find_statement_for_period(
            statements_dir, exp["year"], exp["month"], include_downloads=True
        )
        label = "{} {:02d}".format(exp["year"], exp["month"])
        if path:
            report["ok"].append(
                "Statement on disk for {} ({})".format(
                    label, statement_display_label(path, include_stage=False)
                )
            )
        else:
            report["warnings"].append(
                "Missing expected statement for {} (download from Chase)".format(label)
            )

    # Resolve prior download / amazon tasks if files appeared
    for task in prior_tasks or []:
        kind = task.get("kind")
        if kind == "download_statement" and task.get("period"):
            p = task["period"]
            found = find_statement_for_period(
                statements_dir, p.year, p.month, include_downloads=True
            )
            if found:
                report["resolved"].append(
                    "Download task cleared — found {}".format(
                        statement_display_label(found, include_stage=False)
                    )
                )
        elif kind == "amazon_data" and task.get("period"):
            need = task["period"]
            if amazon_through and amazon_through.date() >= need.date():
                report["resolved"].append(
                    "Amazon data now covers through {} (needed {})".format(
                        _format_short_date(amazon_through),
                        _format_short_date(need),
                    )
                )
            elif amazon_through:
                report["warnings"].append(
                    "Amazon still only through {} — need {}".format(
                        _format_short_date(amazon_through),
                        _format_short_date(need),
                    )
                )

    # Earliest incomplete period vs Amazon
    incomplete_paths = unrec + approved
    for path in incomplete_paths:
        period = parse_statement_period(path)
        if not period:
            continue
        if amazon_through and amazon_through.date() >= period.date():
            continue
        report["warnings"].append(
            "Amazon data short for {} (have {}, need {})".format(
                statement_display_label(path, include_stage=False),
                _format_short_date(amazon_through),
                _format_short_date(period),
            )
        )
        break  # one is enough

    # 4) Stage ↔ QIF filename pairing (names only)
    amazon_qifs = []
    if os.path.isdir(qif_dir):
        for name in os.listdir(qif_dir):
            if name.lower().startswith("amazon_5144_") and name.lower().endswith(".qif"):
                amazon_qifs.append(os.path.join(qif_dir, name))
    report["counts"]["amazon_5144_qifs"] = len(amazon_qifs)

    for path in unrec:
        qifs = find_qifs_for_statement(path, qif_dir=qif_dir)
        label = statement_display_label(path, include_stage=False)
        if qifs["reconciled"]:
            report["errors"].append(
                "{} is still []/unreconciled but has {}".format(
                    label, os.path.basename(qifs["reconciled"])
                )
            )
        elif qifs["approved"]:
            report["warnings"].append(
                "{} is unreconciled but QIF exists ({}) — export/tag may be out of sync".format(
                    label, os.path.basename(qifs["approved"])
                )
            )

    for path in approved:
        qifs = find_qifs_for_statement(path, qif_dir=qif_dir)
        label = statement_display_label(path, include_stage=False)
        if qifs["reconciled"]:
            report["warnings"].append(
                "{} is [APPROVED] but {} already exists — mark reconciled?".format(
                    label, os.path.basename(qifs["reconciled"])
                )
            )
        elif not qifs["approved"]:
            report["errors"].append(
                "{} is [APPROVED] but missing {}".format(
                    label, os.path.basename(qifs["expected_approved"])
                )
            )
        else:
            report["ok"].append(
                "{} ↔ {}".format(label, os.path.basename(qifs["approved"]))
            )

    # Spot-check recent reconciled only when a tool-exported QIF exists
    for path in reconciled[-8:]:
        qifs = find_qifs_for_statement(path, qif_dir=qif_dir)
        label = statement_display_label(path, include_stage=False)
        if qifs["reconciled"]:
            report["ok"].append(
                "{} ↔ {}".format(label, os.path.basename(qifs["reconciled"]))
            )
        elif qifs["approved"]:
            report["warnings"].append(
                "{} is [REC] but QIF not renamed to _reconcile ({})".format(
                    label, os.path.basename(qifs["approved"])
                )
            )
        # else: reconciled before this exporter — no amazon_5144 QIF expected

    # Orphan amazon_5144 QIFs with no matching statement month
    stmt_keys = set()
    for path in unrec + approved + reconciled:
        parsed = match_statement_name(path)
        if parsed:
            stmt_keys.add(
                "amazon_5144_{}_{}{}".format(
                    parsed["year"], parsed["mon"], parsed["day"]
                ).lower()
            )
    for qpath in amazon_qifs:
        stem = os.path.splitext(os.path.basename(qpath))[0]
        key = stem.lower().replace("_reconcile", "")
        if key not in stmt_keys and not stem.lower().startswith("amazon_5144_20"):
            continue
        if key not in stmt_keys:
            # Only flag if it looks like our year-first naming
            if "_20" in stem:
                report["warnings"].append(
                    "QIF with no matching statement PDF: {}".format(
                        os.path.basename(qpath)
                    )
                )

    # 5) Progress JSON stage vs filename (no PDF)
    for path in incomplete_paths:
        progress, ppath = _read_progress_json(path)
        if not progress:
            continue
        file_stage = statement_stage(path)
        prog_stage = (progress.get("stage") or "unreconciled").lower()
        label = statement_display_label(path, include_stage=False)
        n_charges = len(progress.get("charges") or [])
        n_rev = sum(
            1 for r in (progress.get("charges") or []) if r.get("reviewed")
        )
        if prog_stage != file_stage and not (
            prog_stage == "unreconciled" and file_stage == "unreconciled"
        ):
            report["warnings"].append(
                "{} progress stage={} but filename stage={} ({}/{} reviewed)".format(
                    label, prog_stage, file_stage, n_rev, n_charges
                )
            )
        elif n_charges:
            report["ok"].append(
                "{} progress {}/{} reviewed".format(label, n_rev, n_charges)
            )

    if hidden:
        report["warnings"].append(
            "{} duplicate Chase download(s) hidden (same month already archived)".format(
                len(hidden)
            )
        )

    cats_path = os.path.join(qif_dir, "Categories.QIF")
    if os.path.isfile(cats_path):
        report["ok"].append("Categories.QIF present")
    else:
        report["warnings"].append("Categories.QIF missing from QIF folder")

    report["counts"]["ok"] = len(report["ok"])
    report["counts"]["warnings"] = len(report["warnings"])
    report["counts"]["errors"] = len(report["errors"])
    report["counts"]["resolved"] = len(report["resolved"])
    return report
