"""Shared Amazon Privacy Central export under JRSS Reconciliation/Amazon Data.

Canonical live tree:
  …/Amazon Data/Your Orders/Your Amazon Orders/Order History.csv
  …/Amazon Data/Your Orders/Your Amazon Orders/Digital Content Orders.csv

New downloads often land as ``Your Orders (1)`` (or ``Your Orders (2)``, …).
``ingest_pending_amazon_exports`` archives the current ``Your Orders`` folder
and promotes the newest inbound copy into place.
"""

from __future__ import print_function

import os
import re
import shutil
from datetime import datetime

from amazon_cc.statements import JRSS_RECONCILIATION_DIR

AMAZON_DATA_DIR = os.path.join(JRSS_RECONCILIATION_DIR, "Amazon Data")
LIVE_ORDERS_DIRNAME = "Your Orders"
LEGACY_ORDERS_DIR = os.path.join("amazon", "Your Orders")

_INBOUND_ORDERS_RE = re.compile(
    r"(?i)^Your Orders(?:\s*\((\d+)\))?$"
)
_ARCHIVE_ORDERS_RE = re.compile(
    r"(?i)^Your Orders_archive_"
)


def resolve_amazon_data_dir(preferred=None):
    """Prefer JRSS Amazon Data; create it if the JRSS parent exists."""
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.append(AMAZON_DATA_DIR)
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    # Ensure shared folder exists when OneDrive JRSS is present
    parent = JRSS_RECONCILIATION_DIR
    if os.path.isdir(parent):
        os.makedirs(AMAZON_DATA_DIR, exist_ok=True)
        return AMAZON_DATA_DIR
    return preferred or AMAZON_DATA_DIR


def live_orders_dir(amazon_data_dir=None):
    return os.path.join(
        resolve_amazon_data_dir(amazon_data_dir), LIVE_ORDERS_DIRNAME
    )


def order_history_path(amazon_data_dir=None):
    """Path to live Order History.csv (JRSS first, then legacy repo copy)."""
    primary = os.path.join(
        live_orders_dir(amazon_data_dir),
        "Your Amazon Orders",
        "Order History.csv",
    )
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(
        LEGACY_ORDERS_DIR, "Your Amazon Orders", "Order History.csv"
    )
    if os.path.isfile(legacy):
        return legacy
    return primary


def digital_orders_path(amazon_data_dir=None):
    """Path to live Digital Content Orders.csv."""
    primary = os.path.join(
        live_orders_dir(amazon_data_dir),
        "Your Amazon Orders",
        "Digital Content Orders.csv",
    )
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(
        LEGACY_ORDERS_DIR, "Your Amazon Orders", "Digital Content Orders.csv"
    )
    if os.path.isfile(legacy):
        return legacy
    return primary


def digital_returns_path(amazon_data_dir=None):
    """Path to live Digital Returns.csv (refunds for digital / Appstore orders)."""
    primary = os.path.join(
        live_orders_dir(amazon_data_dir),
        "Your Amazon Orders",
        "Digital Returns.csv",
    )
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(
        LEGACY_ORDERS_DIR, "Your Amazon Orders", "Digital Returns.csv"
    )
    if os.path.isfile(legacy):
        return legacy
    return primary


def refund_details_path(amazon_data_dir=None):
    """Path to live Refund Details.csv (mostly physical-order refunds)."""
    primary = os.path.join(
        live_orders_dir(amazon_data_dir),
        "Your Returns & Refunds",
        "Refund Details.csv",
    )
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(
        LEGACY_ORDERS_DIR, "Your Returns & Refunds", "Refund Details.csv"
    )
    if os.path.isfile(legacy):
        return legacy
    return primary


def _folder_has_order_history(folder):
    return os.path.isfile(
        os.path.join(folder, "Your Amazon Orders", "Order History.csv")
    )


def _inbound_sort_key(name):
    """Higher = newer inbound (Your Orders (2) > (1) > bare Your Orders)."""
    m = _INBOUND_ORDERS_RE.match(name)
    if not m:
        return -1
    if m.group(1) is None:
        return 0
    return int(m.group(1))


def list_inbound_order_folders(amazon_data_dir=None):
    """
    Folders that look like a fresh Privacy Central unpack waiting to become live.
    Excludes archives. Includes ``Your Orders (N)`` and a non-live ``Your Orders``
    only when it is not already the live path (N/A — live is always that name).
    Returns paths sorted newest-inbound first.
    """
    root = resolve_amazon_data_dir(amazon_data_dir)
    if not os.path.isdir(root):
        return []
    live = os.path.normcase(os.path.abspath(live_orders_dir(root)))
    found = []
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        if _ARCHIVE_ORDERS_RE.match(name):
            continue
        if not _INBOUND_ORDERS_RE.match(name):
            continue
        if os.path.normcase(os.path.abspath(path)) == live:
            continue
        if not _folder_has_order_history(path):
            continue
        found.append(path)
    found.sort(
        key=lambda p: (_inbound_sort_key(os.path.basename(p)), os.path.getmtime(p)),
        reverse=True,
    )
    return found


def archive_stamp_for_orders_dir(orders_dir):
    """Prefer Order History mtime date; fall back to today."""
    oh = os.path.join(orders_dir, "Your Amazon Orders", "Order History.csv")
    when = datetime.now()
    if os.path.isfile(oh):
        try:
            when = datetime.fromtimestamp(os.path.getmtime(oh))
        except OSError:
            pass
    return when.strftime("%Y%m%d")


def archive_live_orders(amazon_data_dir=None):
    """
    Rename live ``Your Orders`` → ``Your Orders_archive_YYYYMMDD``.
    Returns archive path, or None if there was no live folder.
    """
    root = resolve_amazon_data_dir(amazon_data_dir)
    live = live_orders_dir(root)
    if not os.path.isdir(live):
        return None
    stamp = archive_stamp_for_orders_dir(live)
    dest = os.path.join(root, "{}_archive_{}".format(LIVE_ORDERS_DIRNAME, stamp))
    if os.path.exists(dest):
        suffix = 2
        while os.path.exists("{}_{}".format(dest, suffix)):
            suffix += 1
        dest = "{}_{}".format(dest, suffix)
    os.rename(live, dest)
    return dest


def promote_orders_folder(source_dir, amazon_data_dir=None):
    """
    Archive current live orders (if any), then rename source_dir to live
    ``Your Orders``. Returns dict with archived, live, from.
    """
    root = resolve_amazon_data_dir(amazon_data_dir)
    source_dir = os.path.normpath(source_dir)
    if not os.path.isdir(source_dir):
        raise RuntimeError("Amazon orders folder not found: {}".format(source_dir))
    if not _folder_has_order_history(source_dir):
        raise RuntimeError(
            "Not a Privacy Central Your Orders tree (missing Order History.csv): "
            "{}".format(source_dir)
        )
    archived = archive_live_orders(root)
    live = live_orders_dir(root)
    if os.path.exists(live):
        raise RuntimeError("Live orders folder still exists after archive: {}".format(live))
    os.rename(source_dir, live)
    return {"archived": archived, "live": live, "from": source_dir}


def migrate_legacy_orders_into_amazon_data(amazon_data_dir=None, as_archive=True):
    """
    Move repo ``amazon/Your Orders`` into the JRSS Amazon Data folder.
    If as_archive=True (default), stores as Your Orders_archive_YYYYMMDD so a
    newer inbound can become live. If live is empty and as_archive=False,
    installs as live.
    """
    root = resolve_amazon_data_dir(amazon_data_dir)
    legacy = os.path.normpath(LEGACY_ORDERS_DIR)
    if not os.path.isdir(legacy) or not _folder_has_order_history(legacy):
        return {"moved": False, "reason": "no legacy Your Orders"}
    # Already under JRSS? skip
    if os.path.normcase(os.path.abspath(os.path.dirname(legacy))) == os.path.normcase(
        os.path.abspath(root)
    ):
        return {"moved": False, "reason": "already in Amazon Data"}

    stamp = archive_stamp_for_orders_dir(legacy)
    if as_archive or os.path.isdir(live_orders_dir(root)):
        dest = os.path.join(
            root, "{}_archive_{}".format(LIVE_ORDERS_DIRNAME, stamp)
        )
    else:
        dest = live_orders_dir(root)
    if os.path.exists(dest):
        suffix = 2
        while os.path.exists("{}_{}".format(dest, suffix)):
            suffix += 1
        dest = "{}_{}".format(dest, suffix)
    shutil.move(legacy, dest)
    return {"moved": True, "from": legacy, "to": dest}


def strip_media_folders(amazon_data_dir=None, include_archives=False):
    """
    Delete Privacy Central delivery-photo ``Media`` folders (not used by matching).

    Scans live ``Your Orders`` and inbound ``Your Orders (N)`` trees. Archives
    are left alone unless include_archives=True.
    Returns list of deleted paths.
    """
    root = resolve_amazon_data_dir(amazon_data_dir)
    if not os.path.isdir(root):
        return []

    targets = []
    live = live_orders_dir(root)
    if os.path.isdir(live):
        targets.append(live)
    targets.extend(list_inbound_order_folders(root))
    if include_archives:
        for name in os.listdir(root):
            if _ARCHIVE_ORDERS_RE.match(name):
                path = os.path.join(root, name)
                if os.path.isdir(path):
                    targets.append(path)

    deleted = []
    seen = set()
    for base in targets:
        base_abs = os.path.normcase(os.path.abspath(base))
        if base_abs in seen:
            continue
        seen.add(base_abs)
        for dirpath, dirnames, _files in os.walk(base):
            # Copy names — we may mutate dirnames to prune the walk
            for name in list(dirnames):
                if name.lower() != "media":
                    continue
                media_path = os.path.join(dirpath, name)
                try:
                    shutil.rmtree(media_path)
                    deleted.append(media_path)
                    dirnames.remove(name)
                except OSError as exc:
                    deleted.append("{} (failed: {})".format(media_path, exc))
    return deleted


def ingest_pending_amazon_exports(amazon_data_dir=None):
    """
    If inbound folders like ``Your Orders (1)`` exist, promote the newest and
    archive the previous live set. Also migrates legacy repo copy once.
    Always strips unused Media photo folders from live/inbound trees.
    Returns a result dict suitable for Sync audit reporting.
    """
    root = resolve_amazon_data_dir(amazon_data_dir)
    result = {
        "dir": root,
        "migrated_legacy": None,
        "promoted": None,
        "pending_left": [],
        "removed_media": [],
        "messages": [],
    }

    inbound = list_inbound_order_folders(root)
    live = live_orders_dir(root)
    has_live = os.path.isdir(live) and _folder_has_order_history(live)
    # Archive legacy if live already exists or a newer inbound is waiting;
    # otherwise install legacy directly as live.
    legacy_result = migrate_legacy_orders_into_amazon_data(
        root, as_archive=(has_live or bool(inbound))
    )
    result["migrated_legacy"] = legacy_result
    if legacy_result.get("moved"):
        result["messages"].append(
            "Moved legacy repo export → {}".format(
                os.path.basename(legacy_result["to"])
            )
        )

    inbound = list_inbound_order_folders(root)
    if inbound:
        newest = inbound[0]
        promoted = promote_orders_folder(newest, root)
        result["promoted"] = promoted
        result["messages"].append(
            "Activated {} as Your Orders".format(os.path.basename(promoted["from"]))
        )
        if promoted.get("archived"):
            result["messages"].append(
                "Archived previous → {}".format(os.path.basename(promoted["archived"]))
            )

    result["pending_left"] = [
        os.path.basename(p) for p in list_inbound_order_folders(root)
    ]
    if result["pending_left"]:
        result["messages"].append(
            "Still pending (not activated): {}".format(
                ", ".join(result["pending_left"])
            )
        )

    # Drop delivery-photo Media folders (live + any leftover inbound)
    removed = strip_media_folders(root, include_archives=False)
    result["removed_media"] = removed
    for path in removed:
        if "failed:" in path:
            result["messages"].append("Media cleanup failed: {}".format(path))
        else:
            result["messages"].append(
                "Removed photo Media folder → {}".format(path)
            )
    return result
