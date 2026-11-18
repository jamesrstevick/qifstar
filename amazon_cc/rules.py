"""Train and apply category/memo/payee rules from QIF ↔ Order pairs."""

from __future__ import print_function

import json
import os
import re
from collections import Counter, defaultdict

DEFAULT_RULES_PATH = "amazon_rules.json"

# Sparse hand memo rules (prefer few; add only when a pattern is clear).
# Applied when an order has exactly one line item (qty may be > 1).
#
# Safe accessory cue: title has "holder" plus toilet paper / paper towel
# (covers SunnyPoint / InterDesign / etc. without guessing from "stand" alone).
# Safe consumable cue: same paper phrases plus roll(s)/pack, and not a holder.


def memo_from_single_item_rules(items):
    """
    If the order is a single product line and the title matches a known
    household staple phrase, return the short Quicken-style memo; else None.
    """
    if not items or len(items) != 1:
        return None
    name = (items[0].get("name") or "").lower()
    if not name:
        return None

    has_tp = "toilet paper" in name
    has_pt = "paper towel" in name  # towel / towels
    if not has_tp and not has_pt:
        return None

    # Hardware / fixture — require "holder" (high precision in Order History)
    if "holder" in name:
        if has_tp and has_pt:
            return "Toilet paper and paper towel holder"
        if has_tp:
            return "Toilet paper holder"
        return "Paper towel holder"

    # Consumable paper goods — need roll/pack signal so titles that merely
    # mention toilet paper (storage, cleaners, etc.) do not auto-memo.
    if not re.search(r"\brolls?\b|\bpack\b", name):
        return None

    hits = []
    if has_tp:
        hits.append("Toilet paper")
    if has_pt:
        hits.append("Paper towels")
    if len(hits) > 1:
        return "Toilet paper and paper towels"
    return hits[0]


# Payee substring -> fixed category / payee override (before address rules)
PAYEE_DEFAULTS = [
    {
        "payee_contains": "prime video",
        "payee": "Prime Video",
        "category": "PSNL:Entertainment:Movies",
    },
    {
        "payee_contains": "amazon music",
        "payee": "Amazon Music",
        "category": "PSNL:Entertainment:Music",
    },
    {
        "payee_contains": "kindle",
        "payee": "Kindle Svcs",
        "category": "PSNL:Entertainment:Books",
    },
]

# Sparse hand ship-to pins (name and/or street). Prefer few; add only when
# stable and not inferable from product keywords. Survives amazon_train.py.
HAND_SHIP_TO_NAME = [
    {
        "name_contains": "EUNICE KANG",
        "category": "PSNL:Gifts Given",
        "root": "PSNL",
        # Fingerprint uses street# as ZIP key today (same quirk as Lyle pin).
        "fingerprint": "EUNICE KANG 28550 GRANDVIEW DR MORENO VALLEY CA | 28550",
        "note": "Grandma — usually gifts given (same Grandview house as Lyle)",
    },
    {
        "street_contains": "1310 6TH ST",
        "category": "Walnut 1722:Supplies",
        "root": "Walnut 1722",
        "fingerprint": "GLEN STEVICK 1310 6TH ST BERKELEY CA 94710 | 94710",
        "note": "Berkeley address (not CC). July+Aug mostly Walnut 1722",
    },
]

# Sparse hand item → category (beats ship-to when the product is clearly personal).
HAND_ITEM_CATEGORY = [
    {
        "title_contains": "cat food",
        "category": "PSNL:Pets:Pet Food",
        "note": "Personal pet food, even when shipped to a property address",
    },
]

# Property roots that live in Berkeley (never CC — CC is Florida).
BERKELEY_PROPERTY_ROOTS = frozenset(
    {"Walnut 1722", "VSV", "CH", "1636 Walnut", "MH"}
)

# Trailing glue words that make a bad memo ending ("Shower Head with").
_MEMO_TRAILING_GLUE = frozenset(
    """
    with and for of the a an to from or on in at by as into onto over
    under per via plus without within
    """.split()
)


def normalize_address(addr):
    """Collapse shipping address for ship-to → category root lookup."""
    if not addr:
        return ""
    text = str(addr).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Drop country noise
    text = text.replace(" UNITED STATES", "").strip()
    return text


def address_fingerprint(addr):
    """Shorter key: street number + street + city + state + ZIP if present."""
    norm = normalize_address(addr)
    if not norm:
        return ""
    # Prefer last ZIP (5 digit) + state token + earlier street chunk
    zip_m = re.search(r"\b(\d{5})(?:\s+\d{4})?\b", norm)
    zip5 = zip_m.group(1) if zip_m else ""
    # Keep first ~6 tokens (name + street) + zip
    tokens = norm.split()
    head = " ".join(tokens[:8])
    if zip5:
        return "{} | {}".format(head, zip5)
    return head


def category_root(category):
    if not category or category == "--Split--":
        return ""
    if category.startswith("["):
        return ""
    return category.split(":")[0]


# Product-type phrases for memos (nouns + useful descriptors). Brand names are
# ignored on purpose. Longest needles first so "sheet set" wins over "sheet".
# Add sparingly when a bad brand-prefix memo shows up in review.
MEMO_PRODUCT_PHRASES = (
    ("bedding sheet set", "Bedding sheet set"),
    ("sheet set", "Sheet set"),
    ("duvet insert", "Duvet insert"),
    ("pillow protectors", "Pillow protectors"),
    ("pillow cases", "Pillow cases"),
    ("pillow case", "Pillow case"),
    ("throw pillows", "Throw pillows"),
    ("shower curtain liner", "Shower curtain liner"),
    ("shower curtain liners", "Shower curtain liners"),
    ("shower curtains", "Shower curtains"),
    ("shower curtain", "Shower curtain"),
    ("curtain rods", "Curtain rods"),
    ("blackout curtains", "Blackout curtains"),
    ("toilet paper holder", "Toilet paper holder"),
    ("paper towel holder", "Paper towel holder"),
    ("paper towels", "Paper towels"),
    ("toilet paper", "Toilet paper"),
    ("bathroom rug", "Bathroom rug"),
    ("kitchen rugs", "Kitchen rugs"),
    ("kitchen rug", "Kitchen rug"),
    ("area rug", "Area rug"),
    ("bath mat", "Bath mat"),
    ("towel set", "Towel set"),
    ("bath towels", "Bath towels"),
    ("trash bags", "Trash bags"),
    ("california king", "California king"),
    ("twin xl", "Twin XL"),
    ("comforter", "Comforter"),
    ("duvet", "Duvet"),
    ("pillows", "Pillows"),
    ("curtains", "Curtains"),
    ("queen", "Queen"),
    ("king", "King"),
    ("twin", "Twin"),
    ("full", "Full"),
    ("rug", "Rug"),
)


def _phrase_boundary_pattern(needle):
    """Match needle with alnum boundaries (handles Twin XL, etc.)."""
    return re.compile(
        r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])",
        re.IGNORECASE,
    )


def extract_product_memo_phrases(name):
    """
    Pull product-type phrases from a title (longest non-overlapping first).
    Returns canonical labels in title order, e.g. ['Sheet set', 'Twin XL'].
    """
    text = re.sub(r"\s+", " ", (name or "").strip())
    if not text:
        return []
    low = text.lower()
    cands = []
    for needle, label in MEMO_PRODUCT_PHRASES:
        for m in _phrase_boundary_pattern(needle).finditer(low):
            cands.append((m.start(), m.end(), len(needle), label))
    # Prefer longer phrases; then earlier in the title
    cands.sort(key=lambda x: (-x[2], x[0]))
    chosen = []
    used = []
    for start, end, _nlen, label in cands:
        if any(start < u_end and end > u_start for u_start, u_end in used):
            continue
        used.append((start, end))
        chosen.append((start, label))
    chosen.sort(key=lambda x: x[0])
    labels = []
    for _pos, label in chosen:
        if label not in labels:
            labels.append(label)
    return labels


def _fallback_brandish_short(name, max_words=4):
    """Last resort: first words of the title (often brand-heavy)."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    name = re.split(r"[|,]| - ", name)[0].strip()
    words = name.split()
    return " ".join(words[:max_words]) if words else name


def format_memo_casing(memo):
    """
    Soft casing: keep ALL-CAPS brands (DEWALT); preserve the first token's
    capitalization (Briout / Purina); lowercase other non-proper words.
    'DEWALT Drill Bit Set, White Touch Up Paint'
      → 'DEWALT drill bit set, white touch up paint'
    """
    memo = memo or ""
    if not memo:
        return memo
    first_token = True
    segments = []
    for segment in memo.split(", "):
        words = segment.split()
        out = []
        for word in words:
            # Preserve trailing qty markers like (2x)
            if re.fullmatch(r"\(\d+x\)", word, flags=re.I):
                out.append(word)
                first_token = False
                continue
            m = re.match(r"^([A-Za-z0-9&'#.\-]+)(.*)$", word)
            if not m:
                out.append(word)
                first_token = False
                continue
            core, suffix = m.group(1), m.group(2)
            letters = re.sub(r"[^A-Za-z]", "", core)
            if letters.isupper() and len(letters) >= 2:
                out.append(core + suffix)
            elif first_token:
                # Keep Amazon/brand capitalization on the leading name only
                out.append(core + suffix)
            else:
                out.append(core.lower() + suffix)
            first_token = False
        segments.append(" ".join(out))
    return ", ".join(segments)


def strip_trailing_memo_glue(memo):
    """Drop dangling with/and/for/of/... so memos end on a noun/adjective."""
    memo = (memo or "").rstrip(" ,;")
    if not memo:
        return memo
    # If truncated with ellipsis, clean words before '...'
    ellip = memo.endswith("...")
    body = memo[:-3].rstrip() if ellip else memo
    words = body.split()
    while words and words[-1].lower().strip(".,;:") in _MEMO_TRAILING_GLUE:
        words.pop()
    body = " ".join(words).rstrip(" ,;")
    if ellip and body:
        return body + "..."
    return body


# Pack/qty cues only — not dimensions like "18 x 30" / "13 x 13 Inch" / "16x24".
_TITLE_QTY_PATTERNS = (
    re.compile(r"\bset\s+of\s+(\d+)\b", re.I),
    re.compile(r"\bpack\s+of\s+(\d+)\b", re.I),
    re.compile(r"\bcount\s+of\s+(\d+)\b", re.I),
    re.compile(r"\b(\d+)\s*[- ]?\s*pack\b", re.I),
    re.compile(r"\b(\d+)\s*[- ]?\s*count\b", re.I),
    re.compile(r"\b(\d+)\s*[- ]?\s*piece(?:s)?\b", re.I),
    re.compile(r"\((\d+)\s*x\)", re.I),  # explicit "(2x)"
    # "2x" / "2 x" as multiplier, but not "18 x 30" or "18x30"
    re.compile(r"\b(\d+)\s*x\b(?!\s*\d)", re.I),
    re.compile(r"\bset\s+of\s+(two|three|four|five|six)\b", re.I),
    re.compile(r"\bpack\s+of\s+(two|three|four|five|six)\b", re.I),
)

_WORD_QTY = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}


def qty_hint_from_title(name):
    """
    Infer pack size from title text (e.g. 'set of 2', '2-pack') when Amazon
    line qty is still 1. Returns 1 if nothing reliable is found.

    Skips dimension pairs (18 x 30, 16x24, 13 x 13 Inch).
    """
    text = name or ""
    # Blank out WxH dimension spans so qty patterns cannot see them.
    text = re.sub(
        r"\b\d+\s*[x×]\s*\d+\b",
        " ",
        text,
        flags=re.I,
    )
    best = 1
    for pat in _TITLE_QTY_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1)
            if raw.isdigit():
                n = int(raw)
            else:
                n = _WORD_QTY.get(raw.lower(), 1)
            if 2 <= n <= 24 and n > best:
                best = n
    return best


def effective_item_qty(item):
    """Amazon Original Quantity, or pack size stated in the product title."""
    try:
        qty = int(item.get("qty") or 1)
    except (TypeError, ValueError):
        qty = 1
    if qty < 1:
        qty = 1
    title_qty = qty_hint_from_title(item.get("name") or "")
    return max(qty, title_qty)


# Quicken memo field limits (used across qifstar):
# - Transaction memo (M…): max 64 chars → suggestions cap at 63
# - Split memo (E…): max 25 chars (airbnb_to_qif.create_short_memo)
DEFAULT_MEMO_MAX_LEN = 63
SPLIT_MEMO_MAX_LEN = 25


def clamp_memo(memo, max_len=DEFAULT_MEMO_MAX_LEN):
    """Truncate memo to max_len; never end on glue words (with/and/for/…)."""
    memo = strip_trailing_memo_glue(memo or "")
    if len(memo) <= max_len:
        return memo
    if max_len <= 3:
        return memo[:max_len]
    truncated = memo[: max_len - 3].rstrip(", ")
    # Prefer cutting at a comma boundary when close.
    if ", " in truncated and len(truncated) > max_len // 2:
        head, _sep, _tail = truncated.rpartition(", ")
        if head:
            truncated = head
    truncated = strip_trailing_memo_glue(truncated)
    if not truncated:
        truncated = memo[: max_len - 3].rstrip(", ")
        truncated = strip_trailing_memo_glue(truncated) or truncated
    return truncated + "..."


def shorten_memo_from_items(items, max_len=DEFAULT_MEMO_MAX_LEN):
    """
    Build a short memo from product titles.

    Prefer product-type nouns/descriptors from MEMO_PRODUCT_PHRASES; fall back
    to a short title prefix only when no phrase hits. Exact phrase repeats
    across line items are collapsed (Bath mat + Bath mat → one Bath mat).
    (Nx) when a single line has Amazon qty N>=2 or the title says set/pack of N.
    Soft-cases non-proper nouns; strips trailing with/and/for.
    """
    parts = []
    seen = set()
    named_items = []

    for item in items:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        named_items.append(item)

        phrases = extract_product_memo_phrases(name)
        labels = phrases if phrases else [_fallback_brandish_short(name)]
        for label in labels:
            if not label:
                continue
            label = strip_trailing_memo_glue(label)
            if not label:
                continue
            key = label.lower()
            if key not in seen:
                seen.add(key)
                parts.append(label)
        if len(", ".join(parts)) >= max_len:
            break

    memo = ", ".join(parts)
    memo = strip_trailing_memo_glue(memo)
    # Qty multiplier only for a single SKU line (not two different bath mats)
    if len(named_items) == 1 and memo:
        qty = effective_item_qty(named_items[0])
        if qty >= 2:
            memo = "{} ({}x)".format(memo, qty)

    return clamp_memo(format_memo_casing(memo), max_len)


def train_rules(train_pairs):
    """
    Build rules dict from matched {txn, orders} pairs (exactly one order each).
    """
    ship_to_root = defaultdict(Counter)
    ship_to_full_cat = defaultdict(Counter)
    keyword_to_cat = defaultdict(Counter)
    payee_to_cat = defaultdict(Counter)

    for pair in train_pairs:
        txn = pair["txn"]
        order = pair["orders"][0]
        cat = txn.get("category") or ""
        if cat == "--Split--" or cat.startswith("["):
            continue
        root = category_root(cat)
        payee = txn.get("payee") or "Amazon"
        payee_to_cat[payee.lower()][cat] += 1

        for addr in order.get("addresses") or []:
            fp = address_fingerprint(addr)
            if fp and root:
                ship_to_root[fp][root] += 1
                ship_to_full_cat[fp][cat] += 1

        for item in order.get("items") or []:
            name = (item.get("name") or "").lower()
            for word in re.findall(r"[a-z]{4,}", name):
                if word in _STOP:
                    continue
                keyword_to_cat[word][cat] += 1

    def top_map(counter_map, min_count=1):
        out = {}
        for key, ctr in counter_map.items():
            if not ctr:
                continue
            val, n = ctr.most_common(1)[0]
            if n >= min_count:
                out[key] = {"value": val, "count": n}
        return out

    rules = {
        "version": 1,
        "trained_pairs": len(train_pairs),
        "payee_defaults": PAYEE_DEFAULTS,
        "ship_to_root": top_map(ship_to_root),
        "ship_to_category": top_map(ship_to_full_cat),
        "keyword_category": top_map(keyword_to_cat, min_count=2),
        "payee_category": top_map(payee_to_cat),
        "default_category": "PSNL:Shopping",
        "default_payee": "Amazon",
        "memo_max_len": DEFAULT_MEMO_MAX_LEN,
    }
    return merge_hand_ship_to(rules)


_STOP = frozenset(
    """
    with from that this your have pack pack of for and the amazon basics
    black white size pack count piece pieces set unit units inches inch
    home market kitchen foods whole fresh pack oz lbs pack pack
    """.split()
)


def merge_hand_ship_to(rules):
    """
    Overlay HAND_SHIP_TO_NAME onto ship_to_* maps (hand wins).
    Also stores the list under hand_ship_to_name for visibility in JSON.
    """
    rules = dict(rules or {})
    ship_cat = dict(rules.get("ship_to_category") or {})
    ship_root = dict(rules.get("ship_to_root") or {})
    hand_out = []
    for rule in HAND_SHIP_TO_NAME:
        hand_out.append(dict(rule))
        fp = (rule.get("fingerprint") or "").strip()
        if not fp:
            continue
        cat = rule.get("category")
        root = rule.get("root") or category_root(cat or "")
        if cat:
            ship_cat[fp] = {"value": cat, "count": max(1, int((ship_cat.get(fp) or {}).get("count") or 0)), "hand": True}
        if root:
            ship_root[fp] = {
                "value": root,
                "count": max(1, int((ship_root.get(fp) or {}).get("count") or 0)),
                "hand": True,
            }
    rules["ship_to_category"] = ship_cat
    rules["ship_to_root"] = ship_root
    rules["hand_ship_to_name"] = hand_out
    rules["hand_item_category"] = [dict(r) for r in HAND_ITEM_CATEGORY]
    return rules


def hand_ship_to_from_addresses(addresses):
    """
    If any ship-to address matches a HAND_SHIP_TO_NAME pin, return
    (category, reason_tag); else (None, None).
    """
    for addr in addresses or []:
        up = " ".join(str(addr).upper().split())
        for rule in HAND_SHIP_TO_NAME:
            name_needle = (rule.get("name_contains") or "").upper().strip()
            street_needle = (rule.get("street_contains") or "").upper().strip()
            if name_needle and name_needle in up:
                tag = name_needle.replace(" ", "_").lower()
                return rule.get("category"), "hand_ship_to:{}".format(tag)
            if street_needle and street_needle in up:
                tag = street_needle.replace(" ", "_").lower()
                return rule.get("category"), "hand_ship_to:{}".format(tag)
    return None, None


def hand_item_category_from_items(items):
    """Hand product pins (e.g. cat food → PSNL:Pets:Pet Food)."""
    blob = " ".join((i.get("name") or "") for i in items or []).lower()
    if not blob:
        return None, None
    for rule in HAND_ITEM_CATEGORY:
        needle = (rule.get("title_contains") or "").lower().strip()
        if needle and needle in blob:
            tag = needle.replace(" ", "_")
            return rule.get("category"), "hand_item:{}".format(tag)
    return None, None


def address_is_florida(addr):
    up = " {} ".format(str(addr or "").upper())
    return (
        " FL " in up
        or up.rstrip().endswith(" FL")
        or "FLORIDA" in up
        or re.search(r"\bFL\s+\d{5}\b", up) is not None
    )


def address_is_berkeley(addr):
    """Berkeley / East Bay property area — not Florida CC."""
    up = " ".join(str(addr or "").upper().split())
    if "BERKELEY" in up:
        return True
    # Common Berkeley ZIPs used in this account
    if re.search(r"\b9470[0-9]\b", up):
        return True
    return False


def order_ship_region(order):
    """Return 'florida', 'berkeley', or '' from order addresses."""
    addrs = order.get("addresses") or [] if order else []
    if any(address_is_florida(a) for a in addrs):
        return "florida"
    if any(address_is_berkeley(a) for a in addrs):
        return "berkeley"
    return ""


def category_allowed_for_region(category, region):
    """CC is Florida-only; Berkeley ships are VSV/CH/Walnut/PSNL/etc."""
    if not category:
        return False
    root = category_root(category)
    if region == "berkeley" and root == "CC":
        return False
    if region == "florida" and root in BERKELEY_PROPERTY_ROOTS:
        return False
    return True


def pick_ship_to_category(fp, rules):
    """
    Choose ship-to guess using frequency: prefer full category when its root
    agrees with the majority root, or when its count is at least the root
    count; otherwise fall back to {root}:Supplies (or PSNL:Shopping).
    """
    hit_cat = (rules.get("ship_to_category") or {}).get(fp)
    hit_root = (rules.get("ship_to_root") or {}).get(fp)
    if hit_cat and hit_root:
        cat = hit_cat["value"]
        root = hit_root["value"]
        cat_n = int(hit_cat.get("count") or 0)
        root_n = int(hit_root.get("count") or 0)
        if category_root(cat) == root or cat_n >= root_n:
            return cat, "ship_to_category"
        # Majority root disagrees with a minority full-category (e.g. Glen@FL
        # groceries n=7 vs CC root n=15) → trust the root.
        if root == "PSNL":
            return "PSNL:Shopping", "ship_to_root:PSNL"
        return "{}:Supplies".format(root), "ship_to_root:{}".format(root)
    if hit_cat:
        return hit_cat["value"], "ship_to_category"
    if hit_root:
        root = hit_root["value"]
        if root == "PSNL":
            return "PSNL:Shopping", "ship_to_root:PSNL"
        return "{}:Supplies".format(root), "ship_to_root:{}".format(root)
    return None, None


def keyword_category_votes(items, rules, region=""):
    """
    Weighted keyword votes (trained counts = likelihood). Categories that are
    impossible for the ship region are dropped.
    """
    votes = Counter()
    for item in items or []:
        name = (item.get("name") or "").lower()
        for word in re.findall(r"[a-z]{4,}", name):
            hit = (rules.get("keyword_category") or {}).get(word)
            if not hit:
                continue
            cat = hit["value"]
            if not category_allowed_for_region(cat, region):
                continue
            votes[cat] += hit.get("count", 1)
    return votes


def keyword_category_vote(items, rules, region=""):
    votes = keyword_category_votes(items, rules, region=region)
    if not votes:
        return None
    return votes.most_common(1)[0][0]


def refine_category_with_keywords(base, items, rules, region=""):
    """
    After a ship-to root/base guess, use keyword frequency to pick a more
    specific category under the same root (CC:Supplies:Tools) or a personal
    PSNL overlay (groceries / pets) when those keywords dominate.
    """
    if not base:
        return None
    votes = keyword_category_votes(items, rules, region=region)
    if not votes:
        return None
    base_root = category_root(base)
    filtered = Counter()
    for cat, n in votes.items():
        root = category_root(cat)
        if root == base_root or root == "PSNL":
            filtered[cat] += n
    if not filtered:
        return None
    best, best_n = filtered.most_common(1)[0]
    if best == base:
        return None
    # Require some evidence; PSNL overlays need a clearer signal than a tweak
    # under the same property root.
    if category_root(best) == "PSNL" and base_root != "PSNL":
        if best_n < 4:
            return None
        return best
    if best_n < 2:
        return None
    return best


def save_rules(rules, path=DEFAULT_RULES_PATH):
    rules = merge_hand_ship_to(rules)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rules, fh, indent=2, sort_keys=True)
        fh.write("\n")


def load_rules(path=DEFAULT_RULES_PATH):
    if not os.path.isfile(path):
        return merge_hand_ship_to(
            {
                "version": 1,
                "trained_pairs": 0,
                "payee_defaults": PAYEE_DEFAULTS,
                "ship_to_root": {},
                "ship_to_category": {},
                "keyword_category": {},
                "payee_category": {},
                "default_category": "PSNL:Shopping",
                "default_payee": "Amazon",
                "memo_max_len": DEFAULT_MEMO_MAX_LEN,
            }
        )
    with open(path, "r", encoding="utf-8") as fh:
        rules = json.load(fh)
    if "payee_defaults" not in rules:
        rules["payee_defaults"] = PAYEE_DEFAULTS
    if not rules.get("memo_max_len"):
        rules["memo_max_len"] = DEFAULT_MEMO_MAX_LEN
    return merge_hand_ship_to(rules)


def guess_from_order(order, statement_payee="", rules=None):
    """
    Guess payee, memo, category for a charge given a matched order (+ rules).
    """
    rules = rules or load_rules()
    payee_in = (statement_payee or "").strip()
    payee_l = payee_in.lower()

    # Fixed digital payees
    for rule in rules.get("payee_defaults") or PAYEE_DEFAULTS:
        needle = rule["payee_contains"]
        if needle in payee_l or needle in " ".join(
            (i.get("name") or "").lower() for i in order.get("items") or []
        ):
            # Only force Prime Video / Music / Kindle when payee hints or title hints
            if needle in payee_l or (
                needle == "prime video"
                and any(
                    "prime video" in (i.get("name") or "").lower()
                    for i in order.get("items") or []
                )
            ):
                max_len = rules.get("memo_max_len", DEFAULT_MEMO_MAX_LEN)
                raw_memo = (
                    memo_from_single_item_rules(order.get("items") or [])
                    or shorten_memo_from_items(
                        order.get("items") or [], max_len
                    )
                    or rule.get("payee")
                )
                return {
                    "payee": rule["payee"],
                    "memo": clamp_memo(format_memo_casing(raw_memo), max_len),
                    "reason": "payee_default:{}".format(needle),
                    "category": rule["category"],
                }

    items = order.get("items") or []
    max_len = rules.get("memo_max_len", DEFAULT_MEMO_MAX_LEN)
    memo_rule = memo_from_single_item_rules(items)
    if memo_rule:
        memo = clamp_memo(format_memo_casing(memo_rule), max_len)
        memo_reason = "single_item_memo"
    else:
        memo = shorten_memo_from_items(items, max_len)
        memo_reason = None
    payee = payee_in if payee_in else rules.get("default_payee", "Amazon")
    if "amazon" in payee.lower() or not payee_in:
        payee = "Amazon"

    category = None
    reason = []
    if memo_reason:
        reason.append(memo_reason)

    region = order_ship_region(order)

    # Hand item pins (cat food, etc.) beat ship-to at property addresses
    item_cat, item_reason = hand_item_category_from_items(items)
    if item_cat:
        category = item_cat
        reason.append(item_reason)

    # Hand ship-to name/street pins (family gifts, 1310 6th St, etc.)
    if not category:
        hand_cat, hand_reason = hand_ship_to_from_addresses(
            order.get("addresses") or []
        )
        if hand_cat and category_allowed_for_region(hand_cat, region):
            category = hand_cat
            reason.append(hand_reason)

    # Ship-to: frequency-aware full category vs majority root
    if not category:
        for addr in order.get("addresses") or []:
            fp = address_fingerprint(addr)
            cat, tag = pick_ship_to_category(fp, rules)
            if cat and category_allowed_for_region(cat, region):
                category = cat
                reason.append(tag)
                break
            if cat and not category_allowed_for_region(cat, region):
                # e.g. trained CC at a Berkeley address — skip, try keywords
                continue

    # Keyword vote (counts = likelihood); region filters impossible roots
    if not category:
        cat = keyword_category_vote(items, rules, region=region)
        if cat:
            category = cat
            reason.append("keyword")

    if not category and region == "florida":
        category = "CC:Supplies"
        reason.append("florida_heuristic")

    if not category and region == "berkeley":
        # Untrained Berkeley address: prefer Walnut 1722 over CC/default shopping
        category = "Walnut 1722:Supplies"
        reason.append("berkeley_default")

    if not category:
        category = rules.get("default_category", "PSNL:Shopping")
        reason.append("default")

    # Frequency refine: same-root subcategory or strong PSNL overlay (groceries)
    # Skip when a hand item/ship pin already chose the category.
    if category and not any(
        r.startswith("hand_item:") or r.startswith("hand_ship_to:")
        for r in reason
    ):
        refined = refine_category_with_keywords(
            category, items, rules, region=region
        )
        if refined:
            category = refined
            reason.append("keyword_refine")

    return {
        "payee": payee,
        "memo": memo or "Amazon order",
        "category": category,
        "reason": "+".join(reason) if reason else "default",
    }


def guess_without_order(statement_payee="", rules=None):
    rules = rules or load_rules()
    payee_in = (statement_payee or "").strip()
    payee_l = payee_in.lower()
    for rule in rules.get("payee_defaults") or PAYEE_DEFAULTS:
        if rule["payee_contains"] in payee_l:
            return {
                "payee": rule["payee"],
                "memo": "",
                "category": rule["category"],
                "reason": "payee_default_no_order",
            }
    return {
        "payee": payee_in or rules.get("default_payee", "Amazon"),
        "memo": "",
        "category": rules.get("default_category", "PSNL:Shopping"),
        "reason": "no_order",
    }
