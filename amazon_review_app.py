###########################################
# AMAZON CC STREAMLIT REVIEWER
###########################################
# Left: Order History match. Right: editable
# QIF fields. Approve persists reviewed=true
# to amazon/review_progress/*.json (resume-safe).
###########################################

from __future__ import print_function

import json
import os
from datetime import datetime

import streamlit as st

from amazon_cc.matching import (
    find_near_miss_orders,
    find_orders_for_charge,
    find_refunds_for_credit,
    load_order_index,
    load_refund_index,
    order_claims_from_progress,
)
from amazon_cc.progress import (
    CH_TRANSFER_TASK_ID,
    all_charges_reviewed,
    first_unreviewed_index,
    is_ch_category,
    load_progress,
    mark_progress_approved,
    mark_progress_reconciled,
    mark_reviewed,
    mark_skipped,
    qif_transactions_from_progress,
    reviewed_count,
    save_progress,
    set_side_task_done,
    skipped_count,
    summarize_ch_charges,
    sync_ch_transfer_side_task,
)
from amazon_cc.qif_io import (
    card_payment_template_from_qif,
    format_qif_date,
    is_statement_card_payment,
    is_statement_refund_credit,
    load_known_categories,
    nearest_category,
    write_ccard_qif,
)
from amazon_cc.rules import (
    DEFAULT_MEMO_MAX_LEN,
    DEFAULT_RULES_PATH,
    clamp_memo,
    guess_from_order,
    guess_without_order,
    load_rules,
)
from amazon_cc.amazon_data import order_history_path
from amazon_cc.dashboard import (
    amazon_data_through,
    build_dashboard_tasks,
    build_statement_inventory,
    build_status_summary,
    next_actionable_statement,
    run_sync_audit,
)
from amazon_cc.statements import (
    QIF_DIR,
    approved_tag,
    legacy_statement_ids_from_path,
    list_statement_pdfs,
    load_charges,
    match_statement_name,
    next_incomplete_statement,
    normalize_downloaded_statements,
    qif_basename_for_statement,
    qif_path_for_statement,
    reconciled_tag,
    rename_qif_reconciled,
    rename_statement_tag,
    resolve_qif_dir,
    resolve_statements_dir,
    statement_display_label,
    statement_id_from_path,
    statement_stage,
)

TRAINING_QIF = "amazon/5144_2025_2026.QIF"
# Full Quicken category list export (shared JRSS QIF folder)
CATEGORIES_QIF = os.path.join(QIF_DIR, "Categories.QIF")


def _init_state():
    defaults = {
        "charges": [],
        "index": 0,
        "progress": None,
        "progress_path": None,
        "orders_cache": None,
        "refunds_cache": None,
        "rules": None,
        "categories": None,
        "loaded_path": None,
        "last4": "5144",
        "seed_sig": None,
        "auto_loaded": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _ensure_orders():
    # Reload if cache predates shipment-aware summaries
    cached = st.session_state.orders_cache
    if cached is not None:
        sample = next((o for o in cached if o.get("source") != "digital"), None)
        if sample is not None and "shipments" not in sample:
            st.session_state.orders_cache = None
    if st.session_state.orders_cache is None:
        with st.spinner("Loading Order History..."):
            st.session_state.orders_cache = load_order_index(order_history_path())
            st.session_state.refunds_cache = None
    return st.session_state.orders_cache


def _ensure_refunds():
    if st.session_state.refunds_cache is None:
        with st.spinner("Loading Amazon refunds..."):
            st.session_state.refunds_cache = load_refund_index(_ensure_orders())
    return st.session_state.refunds_cache


def _ensure_rules():
    if st.session_state.rules is None:
        st.session_state.rules = load_rules(DEFAULT_RULES_PATH)
    return st.session_state.rules


def _ensure_categories(include_transfers=False):
    cache_key = "categories_xfer" if include_transfers else "categories"
    # Bust cache when Categories.QIF is replaced
    cat_mtime = None
    if os.path.isfile(CATEGORIES_QIF):
        try:
            cat_mtime = os.path.getmtime(CATEGORIES_QIF)
        except OSError:
            cat_mtime = None
    if st.session_state.get("_categories_mtime") != cat_mtime:
        st.session_state["_categories_mtime"] = cat_mtime
        st.session_state["categories"] = None
        st.session_state["categories_xfer"] = None
    if st.session_state.get(cache_key) is None:
        # Prefer full Quicken Categories.QIF export; fall back to training QIF.
        cat_source = CATEGORIES_QIF if os.path.isfile(CATEGORIES_QIF) else TRAINING_QIF
        cats = load_known_categories(
            cat_source, include_transfers=include_transfers
        )
        # Keep any training-QIF categories missing from the export
        if cat_source != TRAINING_QIF and os.path.isfile(TRAINING_QIF):
            for c in load_known_categories(
                TRAINING_QIF, include_transfers=include_transfers
            ):
                if c not in cats:
                    cats = sorted(set(cats) | {c}, key=lambda s: s.lower())
        # Keep common defaults from rules even if rare in QIF
        for rule in (_ensure_rules().get("payee_defaults") or []):
            if rule.get("category"):
                if rule["category"] not in cats:
                    cats = sorted(
                        set(cats) | {rule["category"]}, key=lambda s: s.lower()
                    )
        if include_transfers:
            tmpl = card_payment_template_from_qif(TRAINING_QIF)
            if tmpl.get("category") and tmpl["category"] not in cats:
                cats = sorted(set(cats) | {tmpl["category"]}, key=lambda s: s.lower())
        if not cats:
            cats = ["PSNL:Shopping"]
        st.session_state[cache_key] = cats
    # Keep legacy key populated for older session code paths
    if not include_transfers:
        st.session_state.categories = st.session_state[cache_key]
    return st.session_state[cache_key]


def _guess_for_charge(charge, selected_order, rules):
    """Order-based guess, or training-QIF card-payment template, or no-order fallback."""
    if selected_order:
        guess_order = dict(selected_order)
        if selected_order.get("match_items"):
            guess_order["items"] = selected_order["match_items"]
        guess = guess_from_order(
            guess_order,
            statement_payee=charge.get("payee") or "",
            rules=rules,
        )
        # Tag gift-card residual matches in memo + reason so review/QIF show it.
        if (
            selected_order.get("match_kind") == "gift_card_partial"
            or selected_order.get("match_level") == "gift_card"
        ):
            max_len = (rules or {}).get("memo_max_len", DEFAULT_MEMO_MAX_LEN)
            memo = (guess.get("memo") or "").strip()
            tag = "(gift card)"
            if tag not in memo.lower():
                # Reserve room so clamp does not drop the gift-card tag.
                room = max(0, int(max_len) - len(tag) - 1)
                base = clamp_memo(memo, room) if memo else ""
                memo = "{} {}".format(base, tag).strip() if base else tag
                memo = clamp_memo(memo, max_len)
            guess = dict(guess)
            guess["memo"] = memo
            reason = guess.get("reason") or ""
            if "gift_card" not in reason:
                guess["reason"] = (
                    "{}+gift_card_partial".format(reason) if reason else "gift_card_partial"
                )
        # Digital refunds in training keep the product memo (no "refund" suffix).
        return guess
    if is_statement_card_payment(charge.get("payee") or ""):
        return card_payment_template_from_qif(TRAINING_QIF)
    return guess_without_order(
        statement_payee=charge.get("payee") or "", rules=rules
    )


def _load_file(path):
    charges = load_charges(path)
    progress, ppath = load_progress(path, charges)
    # Persist immediately so the file exists even before first approve
    save_progress(progress, ppath)
    st.session_state.charges = charges
    st.session_state.progress = progress
    st.session_state.progress_path = ppath
    st.session_state.loaded_path = path
    st.session_state.index = first_unreviewed_index(progress)
    st.session_state.seed_sig = None


def _persist():
    if st.session_state.progress and st.session_state.progress_path:
        save_progress(st.session_state.progress, st.session_state.progress_path)


def _resolve_exported_qif_path(statement_path, progress=None):
    """Locate the exported QIF for a statement (progress path, then shared/legacy dirs)."""
    candidates = []
    if progress and progress.get("qif_path"):
        candidates.append(progress["qif_path"])
    for qif_dir in (QIF_DIR, "qif_files"):
        candidates.append(qif_path_for_statement(statement_path, qif_dir=qif_dir))
        # Legacy month-first basename (pre year-first rename)
        parsed = match_statement_name(statement_path)
        if parsed:
            legacy = "amazon_5144_{}{}_{}.QIF".format(
                parsed["mon"], parsed["day"], parsed["year"]
            )
            candidates.append(os.path.join(qif_dir, legacy))
        # Older exports used amazon_5144_<statement_id>.QIF (sometimes with MM)
        for sid in [statement_id_from_path(statement_path)] + legacy_statement_ids_from_path(
            statement_path
        ):
            if sid:
                candidates.append(os.path.join(qif_dir, "amazon_5144_{}.QIF".format(sid)))
    # Also accept already-reconciled *_reconcile.QIF next to candidates
    expanded = []
    for cand in candidates:
        if not cand:
            continue
        expanded.append(cand)
        stem, ext = os.path.splitext(cand)
        if not stem.lower().endswith("_reconcile"):
            expanded.append(stem + "_reconcile" + (ext or ".QIF"))
    seen = set()
    for cand in expanded:
        norm = os.path.normcase(os.path.abspath(cand))
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isfile(cand):
            return cand
    return None


def _export_statement_qif():
    """
    Export one QIF for the loaded statement only when every charge is approved.
    Writes to JRSS Reconciliation/QIF files; renames PDF to [APPROVED …] (stage 2).
    """
    path = st.session_state.loaded_path
    progress = st.session_state.progress
    if not path or not progress:
        raise RuntimeError("No statement loaded.")
    if statement_stage(path) == "reconciled":
        raise RuntimeError("This statement is already reconciled.")
    if not all_charges_reviewed(progress):
        n_all = len(progress.get("charges") or [])
        n_rev = reviewed_count(progress)
        n_skip = skipped_count(progress)
        raise RuntimeError(
            "Export requires every charge approved ({}/{} reviewed, {} skipped).".format(
                n_rev, n_all, n_skip
            )
        )
    # Always write to the shared OneDrive JRSS QIF folder (not repo qif_files).
    os.makedirs(QIF_DIR, exist_ok=True)
    out_path = os.path.join(QIF_DIR, qif_basename_for_statement(path))
    txns = qif_transactions_from_progress(progress)
    write_ccard_qif(out_path, txns, cleared="*")
    mark_progress_approved(progress, out_path)
    _persist()
    if path.lower().endswith(".pdf") and statement_stage(path) != "approved":
        new_path = rename_statement_tag(path, approved_tag())
        st.session_state.loaded_path = new_path
        progress["source"] = os.path.normpath(new_path)
        _persist()
    return out_path, len(txns)


def _mark_statement_reconciled(path):
    """
    After Quicken reconcile: rename PDF to [REC JRS M-D-YY], append _reconcile
    to the exported QIF, and drop the statement from the picker.
    """
    if statement_stage(path) != "approved":
        raise RuntimeError(
            "Mark reconciled only after export/approve (filename should be [APPROVED …])."
        )

    # Load progress first so we know where the QIF was written
    progress = None
    ppath = None
    is_loaded = bool(
        st.session_state.loaded_path
        and os.path.normcase(os.path.abspath(st.session_state.loaded_path))
        == os.path.normcase(os.path.abspath(path))
    )
    if is_loaded:
        progress = st.session_state.progress
        ppath = st.session_state.progress_path
    else:
        try:
            charges = load_charges(path)
        except Exception:
            charges = []
        if charges:
            progress, ppath = load_progress(path, charges)

    qif_old = _resolve_exported_qif_path(path, progress)
    if not qif_old:
        raise RuntimeError(
            "No exported QIF found to rename for this statement. "
            "Expected under {} (or the path stored at export).".format(resolve_qif_dir())
        )
    qif_new = rename_qif_reconciled(qif_old)
    new_path = rename_statement_tag(path, reconciled_tag())

    if progress is not None:
        mark_progress_reconciled(progress)
        progress["source"] = os.path.normpath(new_path)
        progress["qif_path"] = os.path.normpath(qif_new)
        if is_loaded:
            _persist()
            st.session_state.charges = []
            st.session_state.progress = None
            st.session_state.progress_path = None
            st.session_state.loaded_path = None
            st.session_state.index = 0
            st.session_state.seed_sig = None
            st.session_state.auto_loaded = False
        elif ppath:
            save_progress(progress, ppath)
    return new_path, qif_new


def _current_charge():
    charges = st.session_state.charges
    idx = st.session_state.index
    if not charges or idx >= len(charges):
        return None
    return charges[idx]


def _current_progress_row():
    progress = st.session_state.progress or {}
    rows = progress.get("charges") or []
    idx = st.session_state.index
    if idx < 0 or idx >= len(rows):
        return None
    return rows[idx]


def _order_claims(except_index=None):
    """Prior approvals on this statement → claimed amount/trackings per order."""
    return order_claims_from_progress(
        st.session_state.progress, except_index=except_index
    )


def _matches_for(charge):
    if is_statement_card_payment(charge.get("payee") or ""):
        return []
    if is_statement_refund_credit(charge):
        return find_refunds_for_credit(
            _ensure_refunds(),
            amount=charge["amount"],
            date=charge.get("date"),
            window_days=7,
        )
    orders = _ensure_orders()
    return find_orders_for_charge(
        orders,
        amount=charge["amount"],
        date=charge.get("date"),
        last4=st.session_state.last4,
        window_days=7,
        order_claims=_order_claims(except_index=st.session_state.index),
    )


def _near_misses_for(charge):
    if is_statement_card_payment(charge.get("payee") or ""):
        return []
    if is_statement_refund_credit(charge):
        # Wider window for delayed refund posts vs Return Date
        return find_refunds_for_credit(
            _ensure_refunds(),
            amount=charge["amount"],
            date=charge.get("date"),
            window_days=30,
        )
    orders = _ensure_orders()
    return find_near_miss_orders(
        orders,
        amount=charge["amount"],
        date=charge.get("date"),
        last4=st.session_state.last4,
        order_claims=_order_claims(except_index=st.session_state.index),
    )


def _amazon_order_url(order_id):
    """Your Orders detail page for a retail or digital Order ID."""
    oid = (order_id or "").strip()
    if not oid:
        return ""
    return "https://www.amazon.com/gp/your-account/order-details?orderID={}".format(
        oid
    )


def _money_text(amount):
    """Dollar text that Streamlit will not render as KaTeX ($…$)."""
    return "\\${:.2f}".format(float(amount))


def _non_closed_statuses(statuses):
    """Statuses that are not Amazon 'Closed' (complete). Empty if all closed."""
    out = []
    for raw in statuses or []:
        s = (raw or "").strip()
        if not s:
            continue
        if s.lower() == "closed":
            continue
        out.append(s)
    return out


def _format_order_block(order, charge_amount=None):
    """
    Detail under the matched-order radio:
    Description (link|date|amount, address, warnings), then Items.
    """
    lines = []
    d = order.get("order_date")
    d_s = d.strftime("%m/%d/%Y") if d else "?"
    oid = order.get("order_id") or ""
    url = _amazon_order_url(oid)

    csv_amt = float(order.get("matched_total") or order.get("total") or 0)
    level = order.get("match_level") or "order"
    # Full-order views (including gift-card residual) show Order History total.
    amt_show = (
        float(order.get("total") or 0)
        if level in ("order", "gift_card")
        else csv_amt
    )

    lines.append("Description:")
    if url:
        head = "[{}]({})".format(oid, url)
    else:
        head = oid or "?"
    lines.append(
        "- {} | {} | {}".format(head, d_s, _money_text(amt_show))
    )

    addrs = order.get("addresses") or []
    is_digital = order.get("source") == "digital" or str(oid).upper().startswith("D0")
    if is_digital:
        lines.append("- *(digital — no shipping address)*")
    elif addrs:
        for a in addrs:
            lines.append("- {}".format(a))
    else:
        lines.append("- *(address not available)*")

    odd = _non_closed_statuses(order.get("status") or [])
    if odd:
        lines.append(
            "- ⚠️ **Warning — status not Closed:** {}".format(", ".join(odd))
        )

    rewards = int(order.get("rewards_dollars") or 0)
    if order.get("match_kind") == "rewards" and rewards > 0:
        lines.append(
            "- ⚠️ Likely **{}** Rewards Points (CSV {} vs charge {})".format(
                _money_text(rewards),
                _money_text(csv_amt),
                _money_text(charge_amount if charge_amount is not None else 0),
            )
        )

    if order.get("match_kind") == "gift_card_partial" or level == "gift_card":
        order_total = float(order.get("total") or 0)
        card_amt = (
            float(charge_amount)
            if charge_amount is not None
            else float(order.get("matched_total") or 0)
        )
        gift_amt = order.get("gift_card_inferred")
        if gift_amt is None and order_total > card_amt:
            gift_amt = round(order_total - card_amt, 2)
        pay = ", ".join(order.get("payments") or []) or "Gift Certificate/Card"
        lines.append(
            "- ⚠️ **Gift card + card** — Order History total {} vs card charge "
            "{} (inferred gift ~{}). Payment: {}. "
            "Open the order link above to confirm the gift-card split on Amazon.".format(
                _money_text(order_total),
                _money_text(card_amt),
                _money_text(gift_amt if gift_amt is not None else 0),
                pay,
            )
        )

    if level == "remainder":
        claimed = order.get("order_claimed")
        lines.append(
            "- ⚠️ **Order remainder** — {} left after prior claim(s) of {} (order {})".format(
                _money_text(csv_amt),
                _money_text(claimed if claimed is not None else 0),
                _money_text(order.get("total") or 0),
            )
        )
    elif level in ("shipment", "line") and abs(csv_amt - float(order.get("total") or 0)) > 0.001:
        left = order.get("order_remaining")
        extra = ""
        if left is not None:
            extra = " — {} still open on this order after prior claim(s)".format(
                _money_text(left)
            )
        lines.append(
            "- ⚠️ Partial {} match — {} of {}{}".format(
                level,
                _money_text(csv_amt),
                _money_text(order.get("total") or 0),
                extra,
            )
        )

    match_items = order.get("match_items") or []
    all_items = order.get("items") or []
    matched_keys = {
        (i.get("name"), round(float(i.get("line_total") or 0), 2)) for i in match_items
    }

    lines.append("")
    lines.append("Items:")
    if level in ("shipment", "line", "remainder") and match_items and (
        level == "remainder" or len(match_items) < len(all_items)
    ):
        for item in match_items:
            name = item.get("name") or ""
            lines.append(
                "- qty {}  ${:.2f}  {}".format(
                    item.get("qty", 1), item.get("line_total", 0), name
                )
            )
        lines.append("")
        lines.append("Also on this order:")
        for item in all_items:
            key = (item.get("name"), round(float(item.get("line_total") or 0), 2))
            if key in matched_keys:
                continue
            name = item.get("name") or ""
            lines.append(
                "- qty {}  ${:.2f}  {}".format(
                    item.get("qty", 1), item.get("line_total", 0), name
                )
            )
    else:
        for item in all_items:
            name = item.get("name") or ""
            lines.append(
                "- qty {}  ${:.2f}  {}".format(
                    item.get("qty", 1), item.get("line_total", 0), name
                )
            )
    return "\n".join(lines)


def _seed_fields(idx, order_sel, guess, progress_row, include_transfers=False):
    sig = "{}_{}_{}".format(idx, order_sel, "xfer" if include_transfers else "cat")
    if st.session_state.seed_sig == sig:
        return
    st.session_state.seed_sig = sig
    known = _ensure_categories(include_transfers=include_transfers)
    fallback = nearest_category("PSNL:Shopping", known) or known[0]

    # Prefer human-saved QIF if this row was already reviewed
    if progress_row and progress_row.get("reviewed") and progress_row.get("qif"):
        q = progress_row["qif"]
        st.session_state["payee_{}".format(idx)] = q.get("payee", "Amazon")
        st.session_state["memo_{}".format(idx)] = q.get("memo", "")
        want = q.get("category") or ""
        cat = want if want in known else (nearest_category(want, known) or fallback)
        st.session_state["cat_{}".format(idx)] = cat
        st.session_state["date_{}".format(idx)] = q.get("date", "")
        st.session_state["_guess_reason"] = "human_reviewed (editable)"
        return

    st.session_state["payee_{}".format(idx)] = guess.get("payee", "Amazon")
    st.session_state["memo_{}".format(idx)] = guess.get("memo", "")
    want = guess.get("category") or ""
    cat = want if want in known else (nearest_category(want, known) or fallback)
    st.session_state["cat_{}".format(idx)] = cat
    reason = guess.get("reason", "")
    if want and want != cat:
        reason = "{} → mapped to {}".format(reason, cat)
    st.session_state["_guess_reason"] = reason


def _inject_theme_css():
    """Blue accents on dark grey — avoid Streamlit default red/green Christmas look."""
    st.markdown(
        """
        <style>
        :root {
            --amazon-blue: #3b82f6;
            --amazon-blue-hover: #2563eb;
        }
        .stButton > button[kind="primary"],
        button[data-testid="baseButton-primary"] {
            background-color: var(--amazon-blue) !important;
            border-color: var(--amazon-blue) !important;
            color: #f8fafc !important;
        }
        .stButton > button[kind="primary"]:hover,
        button[data-testid="baseButton-primary"]:hover {
            background-color: var(--amazon-blue-hover) !important;
            border-color: var(--amazon-blue-hover) !important;
        }
        code {
            background-color: #1e293b !important;
            color: #93c5fd !important;
        }
        div[data-testid="stAlert"] {
            border-left-color: var(--amazon-blue) !important;
        }
        /* Two side panels — subtle page outlines */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #161b22;
            border: 1px solid #3a4556 !important;
            border-radius: 10px;
            padding: 0.75rem 1rem 1rem 1rem;
            min-height: 28rem;
        }
        .task-row {
            padding: 0.35rem 0;
            border-bottom: 1px solid #2a3340;
        }
        /* Radio label sits flush above the order detail line */
        div[data-testid="stVerticalBlock"] > div:has([data-testid="stRadio"]) {
            margin-bottom: 0 !important;
        }
        div[data-testid="stVerticalBlock"] > div:has([data-testid="stRadio"]) + div {
            margin-top: -1rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _fmt_dash_date(dt):
    if not dt:
        return "—"
    return "{}/{}/{}".format(dt.month, dt.day, dt.strftime("%y"))


@st.cache_data(ttl=120, show_spinner=False)
def _cached_amazon_through():
    return amazon_data_through()


@st.cache_data(ttl=60, show_spinner="Scanning statements…")
def _cached_inventory(statements_dir, _mtime_key):
    # _mtime_key busts cache when folder contents change
    return build_statement_inventory(statements_dir)


def _folder_mtime_key(statements_dir):
    try:
        names = sorted(os.listdir(statements_dir))
    except OSError:
        return "missing"
    return "{}|{}".format(len(names), "|".join(names))


def _render_sync_report(report):
    """Show last Sync audit results."""
    if not report:
        return
    counts = report.get("counts") or {}
    with st.expander(
        "Sync audit — {} err · {} warn · {} resolved".format(
            counts.get("errors") or 0,
            counts.get("warnings") or 0,
            counts.get("resolved") or 0,
        ),
        expanded=bool(counts.get("errors") or counts.get("resolved")),
    ):
        st.caption(
            "Checked {} · review {} · approved {} · done {} · QIFs {}".format(
                report.get("checked_at") or "?",
                counts.get("unreconciled") or 0,
                counts.get("approved") or 0,
                counts.get("reconciled") or 0,
                counts.get("amazon_5144_qifs") or 0,
            )
        )
        for line in report.get("resolved") or []:
            st.success(line)
        for line in report.get("errors") or []:
            st.error(line)
        for line in report.get("warnings") or []:
            st.warning(line)
        ok_lines = report.get("ok") or []
        if ok_lines:
            with st.expander("Passed checks ({})".format(len(ok_lines))):
                for line in ok_lines:
                    st.caption("✓ {}".format(line))


def _run_sync_and_refresh(statements_dir, prior_tasks):
    """Clear caches, run name/count audit, stash report, rerun."""
    report = run_sync_audit(
        statements_dir=statements_dir,
        prior_tasks=prior_tasks,
    )
    st.session_state["sync_report"] = report
    _cached_inventory.clear()
    _cached_amazon_through.clear()
    # Force Order History + category reload after Amazon Data / Categories swap
    st.session_state.orders_cache = None
    st.session_state.refunds_cache = None
    st.session_state["_categories_mtime"] = None
    st.session_state["categories"] = None
    st.session_state["categories_xfer"] = None
    return report


def _render_dashboard(statements_dir, inventory, tasks, status):
    """Status metrics, next-up tasks, and statement progress table."""
    head_l, head_r = st.columns((4, 1), gap="small")
    with head_l:
        st.subheader("Dashboard")
    with head_r:
        if st.button(
            ":material/sync: Sync",
            help=(
                "Re-check folders for new Amazon/statement files, rename Chase "
                "downloads, and audit stage tags vs QIF names (no txn parse)."
            ),
            width="stretch",
        ):
            with st.spinner("Syncing…"):
                _run_sync_and_refresh(statements_dir, prior_tasks=tasks)
            st.rerun()

    _render_sync_report(st.session_state.get("sync_report"))

    with st.container(horizontal=True):
        st.metric(
            "Reconciled through",
            _fmt_dash_date(status.get("reconciled_through")),
            border=True,
            help="Latest statement tagged [REC …]",
        )
        st.metric(
            "Amazon data through",
            _fmt_dash_date(status.get("amazon_through")),
            border=True,
            help="Max order/ship date in your Order History export",
        )
        st.metric(
            "Txns left to review",
            status.get("transactions_left_to_review") or 0,
            border=True,
        )
        st.metric(
            "Statements behind",
            status.get("statements_behind") or 0,
            delta="{} approved · {} in review".format(
                status.get("approved_count") or 0,
                status.get("unreconciled_count") or 0,
            ),
            delta_color="off",
            border=True,
        )

    left, right = st.columns((1.2, 1), gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("**Next up**")
            if not tasks:
                st.success("Caught up — nothing waiting.")
            else:
                for i, task in enumerate(tasks[:8]):
                    kind = task.get("kind")
                    icon = {
                        "download_statement": ":material/download:",
                        "amazon_data": ":material/cloud_download:",
                        "review": ":material/rate_review:",
                        "export_qif": ":material/upload_file:",
                        "mark_reconciled": ":material/done_all:",
                        "side_task": ":material/swap_horiz:",
                    }.get(kind, ":material/task:")
                    st.markdown("{} **{}**".format(icon, task.get("title") or ""))
                    if task.get("detail"):
                        st.caption(task["detail"])
                    if task.get("path") and kind in (
                        "review",
                        "export_qif",
                        "mark_reconciled",
                    ):
                        if st.button(
                            "Open {}".format(
                                statement_display_label(
                                    task["path"], include_stage=False
                                )
                            ),
                            key="task_open_{}".format(i),
                        ):
                            try:
                                _load_file(task["path"])
                                st.session_state.auto_loaded = True
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                    if i < min(len(tasks), 8) - 1:
                        st.divider()
                if len(tasks) > 8:
                    st.caption("+ {} more task(s)".format(len(tasks) - 8))

    with right:
        with st.container(border=True):
            st.markdown("**Statements**")
            show = [
                r
                for r in inventory.get("statements") or []
                if r.get("stage") != "reconciled"
                or (
                    status.get("reconciled_through")
                    and r.get("period")
                    and r["period"] >= status["reconciled_through"]
                )
            ]
            # Always show incomplete + last few reconciled for context
            incomplete = [
                r
                for r in inventory.get("statements") or []
                if r.get("stage") in ("unreconciled", "approved")
            ]
            recent_rec = [
                r
                for r in inventory.get("reconciled") or []
            ][-3:]
            show = recent_rec + incomplete
            if not show:
                st.caption("No statements found.")
            else:
                for row in show:
                    stage = row.get("stage")
                    color = {
                        "reconciled": "green",
                        "approved": "orange",
                        "unreconciled": "blue",
                    }.get(stage, "gray")
                    badge = {
                        "reconciled": "done",
                        "approved": "approved",
                        "unreconciled": "review",
                    }.get(stage, stage)
                    period = row.get("period")
                    title = (
                        period.strftime("%b %Y")
                        if period
                        else statement_display_label(
                            row["path"], include_stage=False
                        )
                    )
                    st.markdown(
                        "**{}** :{}-badge[{}] · {} txns".format(
                            title, color, badge, row.get("total") or 0
                        )
                    )
                    if stage == "unreconciled":
                        total = max(int(row.get("total") or 0), 1)
                        done = int(row.get("reviewed") or 0)
                        st.progress(
                            float(done) / float(total),
                            text="{}/{} approved".format(done, row.get("total") or 0),
                        )
                    elif stage == "approved":
                        st.caption("QIF exported — reconcile in Quicken")
                    elif row.get("error"):
                        st.caption("Parse error: {}".format(row["error"]))

            hidden = inventory.get("hidden_downloads") or []
            if hidden:
                with st.expander("Duplicate Chase downloads (hidden)"):
                    for path in hidden:
                        st.caption(os.path.basename(path))
                    st.caption(
                        "Same month already has an archived filename — safe to delete "
                        "the YYYYMMDD-statements-5144 download copies."
                    )


def main():
    st.set_page_config(page_title="Amazon CC Reviewer", layout="wide")
    _inject_theme_css()
    _init_state()
    st.title("Amazon CC reconciliation")
    st.caption(
        "Stage 1 review → Stage 2 export QIF ([APPROVED]) → Stage 3 Quicken "
        "reconcile ([REC …] + `*_reconcile.QIF`)."
    )

    statements_dir = resolve_statements_dir()

    # Rename Chase download PDFs (YYYYMMDD-statements-5144-.pdf) to archive names
    norm = normalize_downloaded_statements(statements_dir)
    if norm.get("renamed"):
        _cached_inventory.clear()
        for item in norm["renamed"]:
            st.toast(
                "Renamed {} → {}".format(
                    os.path.basename(item["from"]),
                    os.path.basename(item["to"]),
                )
            )

    mtime_key = _folder_mtime_key(statements_dir)
    inventory = _cached_inventory(statements_dir, mtime_key)
    amazon_through = _cached_amazon_through()
    status = build_status_summary(
        inventory=inventory,
        statements_dir=statements_dir,
        amazon_through=amazon_through,
    )
    dash_tasks = build_dashboard_tasks(
        inventory=inventory,
        statements_dir=statements_dir,
        amazon_through=amazon_through,
    )

    pdfs = list_statement_pdfs(statements_dir)
    unreconciled = pdfs.get("unreconciled") or []
    approved = pdfs.get("approved") or []
    incomplete = unreconciled + approved

    # Auto-load next actionable statement once per session
    if (
        not st.session_state.auto_loaded
        and not st.session_state.loaded_path
    ):
        nxt = next_actionable_statement(
            tasks=dash_tasks,
            inventory=inventory,
            statements_dir=statements_dir,
        )
        if nxt:
            try:
                _load_file(nxt)
                st.session_state.auto_loaded = True
            except Exception as exc:
                st.session_state.auto_loaded = True
                st.sidebar.error("Auto-load failed: {}".format(exc))
        else:
            st.session_state.auto_loaded = True

    _render_dashboard(statements_dir, inventory, dash_tasks, status)
    st.divider()

    with st.sidebar:
        st.header("Workflow")
        st.caption(statements_dir)
        st.write(
            "Review: {} · Approved: {} · Done: {}".format(
                len(unreconciled),
                len(approved),
                len(pdfs.get("reconciled") or []),
            )
        )
        st.session_state.last4 = st.text_input("Card last-4", st.session_state.last4)

        st.subheader("Open statement")
        if not incomplete:
            st.info("No open statements — all caught up or waiting on downloads.")
            path_choice = None
        else:
            default_idx = 0
            if st.session_state.loaded_path in incomplete:
                default_idx = incomplete.index(st.session_state.loaded_path)
            elif status.get("next_path") in incomplete:
                default_idx = incomplete.index(status["next_path"])
            path_choice = st.selectbox(
                "Not-done statements",
                options=incomplete,
                index=default_idx,
                format_func=statement_display_label,
                help="Any statement still in review or waiting on Quicken reconcile.",
            )
            if st.button("Load statement", type="primary"):
                try:
                    _load_file(path_choice)
                    st.session_state.auto_loaded = True
                    _cached_inventory.clear()
                    st.success(
                        "Loaded {} ({} charges, {} reviewed)".format(
                            statement_display_label(path_choice, include_stage=False),
                            len(st.session_state.charges),
                            reviewed_count(st.session_state.progress),
                        )
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        st.divider()
        progress = st.session_state.progress
        if progress:
            n_rev = reviewed_count(progress)
            n_all = len(progress.get("charges") or [])
            n_skip = skipped_count(progress)
            st.write("Reviewed: {} / {}".format(n_rev, n_all))
            if n_skip:
                st.caption("Skipped: {} (must Approve before export)".format(n_skip))
            ready = all_charges_reviewed(progress)
            if ready:
                st.success("All charges approved — ready to export.")
            else:
                st.caption("Export unlocks when every charge is approved.")
            if st.session_state.loaded_path:
                st.caption(
                    statement_display_label(st.session_state.loaded_path)
                )
        else:
            st.write("Reviewed: 0")

        st.subheader("2 — Export QIF (approve month)")
        st.caption("Writes to shared folder: {}".format(QIF_DIR))
        if progress and all_charges_reviewed(progress):
            ch_preview = summarize_ch_charges(progress)
            if ch_preview["count"]:
                st.warning(
                    "CH on 5144: ${:.2f} across {} charge(s) — export will create a "
                    "4900 reimbursement side task (5144 is paid by 0149)."
                    .format(ch_preview["amount"], ch_preview["count"])
                )
        if st.button("Export statement QIF & mark approved"):
            try:
                out_path, n_txn = _export_statement_qif()
                _cached_inventory.clear()
                st.success(
                    "Wrote {} ({} txns). Statement tagged [APPROVED].".format(
                        out_path, n_txn
                    )
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        st.subheader("Side tasks")
        st.caption(
            "5144 is for VSV/W/CC/OB and paid by 0149. CH spend here must be "
            "reimbursed from Carriage House 4900."
        )
        if progress:
            # Once the month is fully approved (or a CH task already exists),
            # keep the 4900 reimbursement task amount in sync.
            if all_charges_reviewed(progress) or any(
                t.get("id") == CH_TRANSFER_TASK_ID
                for t in (progress.get("side_tasks") or [])
            ):
                before = json.dumps(progress.get("side_tasks") or [], sort_keys=True)
                sync_ch_transfer_side_task(progress)
                after = json.dumps(progress.get("side_tasks") or [], sort_keys=True)
                if before != after:
                    _persist()
            side_tasks = [
                t
                for t in (progress.get("side_tasks") or [])
                if t.get("id") == CH_TRANSFER_TASK_ID
            ]
            if not side_tasks:
                st.caption("No CH reimbursement task yet (appears when CH:* is used).")
            for task in side_tasks:
                label = (
                    "Transfer ${:.2f} from 4900 → reimburse 5144/0149 ({} CH charge{})"
                ).format(
                    float(task.get("amount") or 0),
                    int(task.get("count") or 0),
                    "" if int(task.get("count") or 0) == 1 else "s",
                )
                checked = st.checkbox(
                    label,
                    value=bool(task.get("done")),
                    key="side_task_{}_{}".format(
                        progress.get("statement_id") or "stmt",
                        task.get("id"),
                    ),
                    help=task.get("detail") or "",
                )
                if bool(checked) != bool(task.get("done")):
                    set_side_task_done(progress, task["id"], done=checked)
                    _persist()
                    st.rerun()
                if task.get("memos"):
                    with st.expander("CH charges in this transfer"):
                        for memo in task.get("memos") or []:
                            st.caption("• {}".format(memo or "(no memo)"))
        else:
            st.caption("Load a statement to see side tasks.")

        st.subheader("3 — Mark reconciled")
        st.caption(
            "After importing the QIF and reconciling in Quicken. "
            "Renames the statement PDF to [REC …] and appends _reconcile to the QIF."
        )
        # Refresh approved list after possible export rename
        pdfs = list_statement_pdfs(statements_dir)
        approved = pdfs.get("approved") or []
        if not approved:
            st.caption("No [APPROVED] statements waiting.")
        else:
            for apath in approved:
                label = statement_display_label(apath, include_stage=False)
                qif_hint = _resolve_exported_qif_path(
                    apath,
                    st.session_state.progress
                    if st.session_state.loaded_path
                    and os.path.normcase(
                        os.path.abspath(st.session_state.loaded_path)
                    )
                    == os.path.normcase(os.path.abspath(apath))
                    else None,
                )
                if qif_hint:
                    st.caption("QIF: {}".format(os.path.basename(qif_hint)))
                if st.button(
                    "Mark reconciled: {}".format(label),
                    key="rec_{}".format(os.path.basename(apath)),
                ):
                    try:
                        new_path, qif_new = _mark_statement_reconciled(apath)
                        _cached_inventory.clear()
                        msg = "Statement → {}".format(
                            statement_display_label(new_path)
                        )
                        if qif_new:
                            msg += " · QIF → {}".format(os.path.basename(qif_new))
                        st.success(msg)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

        st.divider()
        if st.button("Reset session (keeps progress file)"):
            st.session_state.charges = []
            st.session_state.index = 0
            st.session_state.progress = None
            st.session_state.progress_path = None
            st.session_state.loaded_path = None
            st.session_state.seed_sig = None
            st.session_state.auto_loaded = False
            _cached_inventory.clear()
            st.rerun()

    charges = st.session_state.charges
    if not charges:
        nxt = next_incomplete_statement(statements_dir)
        st.info(
            "No statement loaded. Pick any not-done statement in the sidebar, "
            "or wait for auto-load of the next one."
        )
        if nxt:
            st.caption("Next up: {}".format(statement_display_label(nxt)))
        return

    idx = st.session_state.index
    progress = st.session_state.progress
    n_all = len(charges)
    n_rev = reviewed_count(progress) if progress else 0
    n_skip = skipped_count(progress) if progress else 0
    # Bar tracks position through the statement (Charge N/N), not approved count —
    # sidebar bars own the reviewed/approved progress.
    charge_pos = n_all if idx >= n_all else min(idx + 1, n_all)
    st.progress(float(charge_pos) / max(n_all, 1))
    stage = statement_stage(st.session_state.loaded_path or "")
    cur_row = None
    if progress and idx < n_all:
        rows = progress.get("charges") or []
        if 0 <= idx < len(rows):
            cur_row = rows[idx]
    if cur_row and cur_row.get("reviewed"):
        status_mark = " ✓"
    elif cur_row and cur_row.get("skipped"):
        status_mark = " (skipped)"
    else:
        status_mark = ""
    st.write(
        "Charge **{}/{}**{}  |  approved **{}**  |  {}  |  {}".format(
            charge_pos,
            n_all,
            status_mark,
            n_rev,
            stage,
            statement_display_label(
                st.session_state.loaded_path or "?", include_stage=False
            ),
        )
    )

    if idx >= n_all:
        if progress and all_charges_reviewed(progress):
            st.success(
                "All {} charges approved. Export the statement QIF from the sidebar "
                "(stage 2).".format(n_rev)
            )
        else:
            st.warning(
                "All charges visited, but {} still need Approve "
                "({} skipped). Export requires every charge approved.".format(
                    n_all - n_rev, n_skip
                )
            )
        if st.button("Go to first unapproved"):
            st.session_state.index = first_unreviewed_index(progress) if progress else 0
            if st.session_state.index >= n_all:
                st.session_state.index = 0
            st.session_state.seed_sig = None
            st.rerun()
        return

    charge = _current_charge()
    prog_row = _current_progress_row()
    rules = _ensure_rules()
    is_payment = is_statement_card_payment(charge.get("payee") or "")
    is_refund = (not is_payment) and is_statement_refund_credit(charge)
    matches = _matches_for(charge)

    if prog_row and prog_row.get("reviewed"):
        st.info("✓ Approved — you can still edit and Approve again to update.")
    elif prog_row and prog_row.get("skipped"):
        st.warning("Skipped — Approve required before export (Skip only defers).")

    left, right = st.columns(2, gap="medium")

    with left:
        with st.container(border=True):
            st.subheader("Your Orders")
            kind_label = "Refund" if is_refund else "Statement"
            st.write(
                "{}: **{}**  ${:.2f}  {}".format(
                    kind_label,
                    charge["date"].strftime("%m/%d/%Y") if charge["date"] else "?",
                    charge["amount"],
                    charge.get("payee") or "",
                )
            )
            if is_refund:
                st.caption(
                    "Statement credit — matched against Digital Returns / Refund "
                    "Details. QIF export will be a **positive** CCard amount "
                    "(same as training refunds)."
                )
            if is_payment:
                st.info(
                    "Credit card payment (statement payment credit) — no Amazon "
                    "Order History row expected. QIF fields are prefilled from "
                    "your training QIF template; approve to keep it in the export."
                )
                order_sel = None
                selected_order = None
            elif not matches:
                st.warning(
                    "No {} match (exact ±7 days{}).".format(
                        "refund" if is_refund else "Order History",
                        ""
                        if is_refund
                        else ", or integer-dollar rewards ±3 days, card",
                    )
                )
                near_misses = _near_misses_for(charge)
                if near_misses:
                    if len(near_misses) == 1:
                        st.caption(
                            "Only unused same-amount order within ±30 days "
                            "(others already assigned on this statement, if any) — "
                            "likely this one:"
                        )
                    else:
                        st.caption(
                            "Near misses by amount (outside ±7/±3 windows, ±30 days; "
                            "excludes orders already approved on this statement):"
                        )
                    labels = []
                    for o in near_misses:
                        d = (
                            o["order_date"].strftime("%m/%d/%Y")
                            if o.get("order_date")
                            else "?"
                        )
                        csv_amt = float(
                            o.get("matched_total") or o.get("total") or 0
                        )
                        label = "{} — {} — {} — {}".format(
                            o["order_id"],
                            d,
                            _money_text(csv_amt),
                            o.get("near_miss_reason") or "near miss",
                        )
                        labels.append(label)
                    # None option so Approve can still proceed without an order
                    none_label = "(none — leave unmatched)"
                    order_sel = st.radio(
                        "Near-miss order(s)",
                        options=list(range(-1, len(near_misses))),
                        format_func=lambda i: none_label
                        if i < 0
                        else labels[i],
                        key="near_sel_{}".format(idx),
                    )
                    if order_sel is not None and order_sel >= 0:
                        selected_order = near_misses[order_sel]
                        st.markdown(
                            _format_order_block(
                                selected_order,
                                charge_amount=charge.get("amount"),
                            )
                        )
                    else:
                        selected_order = None
                else:
                    st.caption(
                        "No same-amount Order History hit within ±30 days either "
                        "(no order link available from the export)."
                    )
                    order_sel = None
                    selected_order = None
            else:
                labels = []
                for o in matches:
                    d = (
                        o["order_date"].strftime("%m/%d/%Y")
                        if o.get("order_date")
                        else "?"
                    )
                    csv_amt = float(o.get("matched_total") or o.get("total") or 0)
                    # Keep radio label plain; escape $ so Streamlit KaTeX won't blue-box it
                    label = "{} — {} — {}".format(
                        o["order_id"], d, _money_text(csv_amt)
                    )
                    if o.get("match_level") == "refund" or o.get("match_kind") == "refund":
                        label = "{} (refund)".format(label)
                    elif o.get("match_kind") == "gift_card_partial" or o.get(
                        "match_level"
                    ) == "gift_card":
                        gift = o.get("gift_card_inferred")
                        order_total = float(o.get("total") or 0)
                        if gift is not None:
                            label = "{} (gift card; order {} / gift ~{})".format(
                                label,
                                _money_text(order_total),
                                _money_text(gift),
                            )
                        else:
                            label = "{} (gift card; order {})".format(
                                label, _money_text(order_total)
                            )
                    elif o.get("match_level") == "remainder":
                        label = "{} (remainder)".format(label)
                    elif o.get("match_level") in ("shipment", "line"):
                        label = "{} (partial)".format(label)
                    if o.get("date_basis") == "ship":
                        label = "{} (via ship)".format(label)
                    if o.get("match_kind") == "rewards" and o.get("rewards_dollars"):
                        label = "{} (rewards −{})".format(
                            label, _money_text(int(o["rewards_dollars"]))
                        )
                    labels.append(label)
                order_sel = st.radio(
                    "Matched refund(s)" if is_refund else "Matched order(s)",
                    options=list(range(len(matches))),
                    format_func=lambda i: labels[i],
                    key="order_sel_{}".format(idx),
                )
                selected_order = matches[order_sel]
                st.markdown(
                    _format_order_block(
                        selected_order, charge_amount=charge.get("amount")
                    )
                )

    with right:
        with st.container(border=True):
            st.subheader("QIF fields")
            guess = _guess_for_charge(charge, selected_order, rules)

            _seed_fields(
                idx,
                order_sel if order_sel is not None else -1,
                guess,
                prog_row,
                include_transfers=is_payment,
            )
            st.caption(
                "Guess reason: {}".format(st.session_state.get("_guess_reason", ""))
            )
            if selected_order and (
                selected_order.get("match_kind") == "gift_card_partial"
                or selected_order.get("match_level") == "gift_card"
            ):
                oid = selected_order.get("order_id") or ""
                url = _amazon_order_url(oid)
                gift = selected_order.get("gift_card_inferred")
                order_total = float(selected_order.get("total") or 0)
                link = "[{}]({})".format(oid, url) if url else oid
                st.warning(
                    "Gift card used on this order — statement shows card residual "
                    "only (order {}, inferred gift ~{}). Check {} if needed.".format(
                        _money_text(order_total),
                        _money_text(gift if gift is not None else 0),
                        link,
                    )
                )

            known_cats = _ensure_categories(include_transfers=is_payment)
            date_default = (
                charge["date"].strftime("%m/%d/%Y") if charge["date"] else ""
            )
            if "date_{}".format(idx) not in st.session_state:
                st.session_state["date_{}".format(idx)] = date_default
            # Amount is locked to the statement charge
            amt_locked = float(charge["amount"])
            if "cat_{}".format(idx) not in st.session_state:
                st.session_state["cat_{}".format(idx)] = known_cats[0]
            # Ensure selectbox index is valid
            if st.session_state["cat_{}".format(idx)] not in known_cats:
                st.session_state["cat_{}".format(idx)] = (
                    nearest_category(st.session_state["cat_{}".format(idx)], known_cats)
                    or known_cats[0]
                )

            date_s = st.text_input("Date (MM/DD/YYYY)", key="date_{}".format(idx))
            st.markdown(
                "**Amount** (from statement, locked): `${:.2f}`".format(amt_locked)
            )
            payee = st.text_input("Payee", key="payee_{}".format(idx))
            memo = st.text_input("Memo (free text)", key="memo_{}".format(idx))
            category = st.selectbox(
                "Category (exact Quicken path)",
                options=known_cats,
                key="cat_{}".format(idx),
                help="Categories from your Quicken Categories.QIF export — exact paths only.",
            )
            if is_ch_category(category):
                st.warning(
                    "CH on 5144: this card is paid by 0149. Month export will add a "
                    "side task to reimburse from Carriage House 4900."
                )

            c1, c2, c3 = st.columns(3)
            with c1:
                approve = st.button("Approve & Next", type="primary")
            with c2:
                skip = st.button("Skip")
            with c3:
                back = st.button("Back")

            if approve:
                try:
                    dt = datetime.strptime(date_s.strip(), "%m/%d/%Y")
                    amt = abs(amt_locked)
                except Exception as exc:
                    st.error("Bad date: {}".format(exc))
                else:
                    qif_fields = {
                        "date": dt,
                        "amount": amt,
                        "payee": payee,
                        "memo": memo,
                        "category": category,
                        "order_id": selected_order["order_id"]
                        if selected_order
                        else "",
                    }
                    if is_payment:
                        qif_fields["match_level"] = "payment"
                    elif selected_order:
                        qif_fields["match_level"] = (
                            selected_order.get("match_level")
                            or ("refund" if is_refund else "")
                        )
                        qif_fields["match_kind"] = (
                            selected_order.get("match_kind") or ""
                        )
                        qif_fields["matched_tracking"] = (
                            selected_order.get("matched_tracking") or ""
                        )
                        qif_fields["matched_total"] = selected_order.get(
                            "matched_total"
                        )
                        qif_fields["order_total"] = selected_order.get("total")
                    elif is_refund:
                        # Manual refund approve still exports as a positive credit
                        qif_fields["match_level"] = "refund"
                    mark_reviewed(
                        st.session_state.progress,
                        idx,
                        qif_fields,
                        suggested={
                            "payee": guess.get("payee") or "",
                            "memo": guess.get("memo") or "",
                            "category": guess.get("category") or "",
                            "reason": guess.get("reason") or "",
                        },
                    )
                    _persist()
                    st.session_state.index = idx + 1
                    st.session_state.seed_sig = None
                    st.rerun()
            if skip:
                mark_skipped(st.session_state.progress, idx)
                _persist()
                st.session_state.index = idx + 1
                st.session_state.seed_sig = None
                st.rerun()
            if back and idx > 0:
                st.session_state.index = idx - 1
                st.session_state.seed_sig = None
                st.rerun()

            try:
                preview = format_qif_date(
                    datetime.strptime(date_s.strip(), "%m/%d/%Y")
                )
            except Exception:
                preview = ""
            st.caption("QIF date preview: {}".format(preview))


if __name__ == "__main__":
    main()
