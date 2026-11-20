# Amazon → Quicken (context)

Amazon Order History lookup, rule training from reconciled Chase/Quicken data, and a Streamlit reviewer that helps build CCard QIF lines for new statement months.

## Problem

Today: see an Amazon charge → open Amazon → find the order → invent memo/category in Quicken.

Wanted: local Order History + trained guesses + a simple review UI (human confirms each row) → export CCard QIF.

## Workflow (current)

```text
1) Privacy Central "Your Orders"  →  `JRSS Reconciliation/Amazon Data/Your Orders/.../Order History.csv`
2) Reconciled Quicken export     →  amazon/5144_2025_2026.QIF
3) python amazon_train.py        →  amazon_rules.json  (+ match-rate report)
4) New-month charges CSV or PDF  →  Streamlit reviewer
5) Approve each row              →  amazon/review_progress/*.json (`reviewed: true`)
6) Export reviewed QIF           →  JRSS Reconciliation/QIF files/amazon_5144_<Year>_<MonthDay>.QIF
7) Mark reconciled (after Quicken) → PDF [REC …] + QIF renamed `…_reconcile.QIF`
```

**Approve** writes human-reviewed fields to a JSON progress file under `amazon/review_progress/` (keyed by source filename). Reloading the same PDF/CSV resumes where you left off; Back still lets you edit a reviewed row and Approve again to update it.

### Train

```bash
.venv\Scripts\activate
pip install -r requirements.txt
python amazon_train.py
```

Uses [`amazon/5144_2025_2026.QIF`](amazon/5144_2025_2026.QIF) + Order History (+ Digital Content Orders). Writes [`amazon_rules.json`](amazon_rules.json).

Latest train snapshot (will change if you re-export):

- ~515 Amazon-like QIF purchases attempted  
- ~77% exact unique amount+date match (rest: splits, multi-shipment, missing digital, etc.)  
- Rules: ship-to fingerprints → category, keyword → category, payee defaults (Prime Video / Music / Kindle)
- Sparse **hand** pins in `amazon_cc/rules.py` survive retrain: `HAND_SHIP_TO_NAME` (Eunice Kang → gifts; 1310 6th St → Walnut), `HAND_ITEM_CATEGORY` (cat food → `PSNL:Pets:Pet Food`)
- Geography: **CC = Florida only**; Berkeley ships are VSV / CH / Walnut / PSNL — never CC
- Ship-to uses **frequency**: majority root wins over a minority full-category (then keyword refine)
- Keyword refine may overlay **food or pets** only. Movies, clothing, and other personal categories stay on the property ship-to
- Refine ignores size/glue words (`medium`, `large`, `small`, `extra`, `plus`, `essential`, `each`) so they cannot outvote the ship-to
- Titles with **plant food** or **fertilizer** refine to `{ship-to root}:Gardening`
- Clear tool titles (pliers, screwdriver, wrench, drill bit(s), socket set, impact socket, hand sewing) refine to `{ship-to root}:Supplies:Tools`
- Memos: soft-casing (keep `DEWALT`, lower non-proper nouns), no trailing `with`/`and`/`for`, dimensions like `18 x 30` are not `(18x)`
- After each reconciled month, append findings to [`amazon_rule_reviews.json`](amazon_rule_reviews.json) (scorecard + deferred watches; avoid overfitting)

### Review (Streamlit)

```bash
streamlit run amazon_review_app.py
```

- **Dashboard (top):** reconciled-through date, Amazon Order History coverage, txns left, ordered next-up tasks (download statement / refresh Amazon / review / export / mark reconciled)
- Auto-opens the next actionable statement; sidebar picker still lists every not-done month
- **Left:** statement charge + matched Your Orders (items, ship-to)  
- **Right:** editable payee / memo / category (pre-filled guess)  
- **Approve & Next** / Skip / Back  
- Sidebar: export approved rows to a CCard QIF under the shared JRSS folder  
- **Mark reconciled** after Quicken: tags the statement PDF `[REC …]` and appends `_reconcile` to the QIF filename  

### New-month charge list

**Primary:** CSV with columns `date`, `amount`, optional `payee` / `description`.

Example: [`amazon_charges_example.csv`](amazon_charges_example.csv)

```csv
date,amount,payee
2026-07-18,72.24,Amazon.com*EY8PT1JO3 Amzn.com/bill WA
```

**Also supported:** Chase statement PDFs under  
`C:\Users\james\OneDrive\JRSS Reconciliation\CC Chase Prime 5144\`  
(legacy repo copy under `amazon/CC Chase Prime 5144/` is fallback only).  
Filename order is **year then month** (same as Schwab):  
`Chase Prime 5144 2026 07 July15 [REC …].pdf`  
Chase online downloads named `YYYYMMDD-statements-5144-.pdf` are auto-renamed into that archive form on app start (duplicate months are hidden).  
Empty `[]` / missing tag = unreconciled; `[APPROVED …]` = QIF exported; `[REC …]` = done. Text extraction via `pypdf` works on current Chase PDFs (no OCR in v1). If a PDF yields nothing useful, drop a CSV instead.

**QIF handoff:** exports go to  
`C:\Users\james\OneDrive\JRSS Reconciliation\QIF files\`  
named `amazon_5144_<Year>_<Month><Day>.QIF` (e.g. `amazon_5144_2026_July15.QIF`). After Quicken reconcile, Mark reconciled renames to `…_reconcile.QIF`.

## Parallel to Airbnb (later)

| Step | Airbnb today | Amazon |
|------|----------------|--------|
| Drop export | `airbnb_*.csv` | `amazon/` Privacy Central + statements / charge CSV |
| Parse / group | Payout + child rows | Order ID + line items |
| Stable ID | Reference code / synthetic | Order ID |
| Map | Listing → category | Ship-to + keywords → category (trained) |
| Human loop | (none) | Streamlit approve each charge |
| Write | QIF → `qif_files/` | CCard QIF → `JRSS Reconciliation/QIF files/` |

**Accounting caveat:** This reviewer builds **categorized CCard QIF** for import/edit. If the same charges already exist uncategorized in Quicken from a bank download, prefer editing those in Quicken or replace that import path—do not double-count.

## Repo pieces

| Path | Role |
|------|------|
| `amazon_lookup.py` | CLI amount/date lookup into Order History |
| `amazon_train.py` | Match QIF ↔ orders; write `amazon_rules.json` |
| `amazon_review_app.py` | Streamlit left/right review + QIF export |
| `amazon_cc/` | QIF I/O, matching, rules, statement ingest, dashboard tasks |
| `amazon_rules.json` | Trained guess rules (safe to commit); hand pins merged on load/save |
| `amazon_rule_reviews.json` | Per-statement rule-review log (append months; deferred watches) |
| `amazon_charges_example.csv` | Sample charge CSV for the reviewer |
| `amazon/` | Local leftovers: training QIF, review_progress (**gitignored**, PII). Live Order History lives under JRSS `Amazon Data/` |
| `amazon_cc/amazon_data.py` | Resolve / archive / swap shared Amazon Data exports |

### Lookup CLI

```bash
python amazon_lookup.py 72.33
python amazon_lookup.py 48.51 --date 2026-09-29 --card 5144
```

Exact amount within ±7 days of **order or ship date** (ship catches Subscribe & Save lag); integer-dollar rewards within ±3 days; optional card last-4. Partial shipment approvals leave an order **remainder** (order total − claimed) for later charges; fully claimed orders are excluded.

**Gift card + Visa:** Privacy Central `Payment Method Type` shows `Gift Certificate/Card and Visa - 5144`, but Order History totals stay at the full merchandise amount — the statement only shows the card residual. When **no** exact/shipment/line amount match exists, orders with a gift-card tender **and** a card last-4 match if `order total > charge` inside the date window (`gift_card_partial`). Approving that row claims the **full** order so no phantom remainder is expected. The gift-card dollar amount is inferred (`order total − charge`); it is not in the CSV.

Statement **credits** (Chase negative amounts that are not card payments) match **Digital Returns.csv** / **Refund Details.csv** by refund amount ± return date. Export as a **positive** CCard amount (same as training: e.g. `Prime Video` / `PSNL:Entertainment:Movies` / product name).

Statement **AUTOMATIC PAYMENT / THANK YOU** lines are kept for approve/export (no Order History). Prefill from training QIF (typically `Amazon Chase` / `Credit Card Payment` / `[Chkng Main BofA-0149]`); export as a positive CCard payment.

## Order History notes

- **Live path (OneDrive shared):**  
  `C:\Users\james\OneDrive\JRSS Reconciliation\Amazon Data\Your Orders\Your Amazon Orders\Order History.csv`  
  (same folder for `Digital Content Orders.csv`)
- Drop a new Privacy Central unpack into `Amazon Data` as `Your Orders` or `Your Orders (1)`. **Sync** archives the previous live set to `Your Orders_archive_YYYYMMDD`, activates the newest inbound, and deletes unused delivery-photo `Media` folders.
- `Total Amount` is usually **per line** — matcher sums by Order ID.  
- Ship-to: `Shipping Address` (Florida → often `CC:*` via rules/heuristic).  
- Digital: `Digital Content Orders.csv` included in train/review matching.

## QIF shape (Chase 5144 export)

Same import conventions as Airbnb / Schwab: space-padded single-digit days,
`C*` on every txn, newest → oldest.

```text
!Type:CCard
D7/18'26
U-72.24
T-72.24
C*
PAmazon
MShort memo from items
LCC:Supplies
^
```

Memos are short. Quicken limits used in this repo:
- Transaction memo (`M…`): max **64** → Amazon suggestions cap at **63** (`memo_max_len` / `DEFAULT_MEMO_MAX_LEN`)
- Split memo (`E…`): max **25** (`SPLIT_MEMO_MAX_LEN` in Airbnb / `amazon_cc.rules`)

Categories use property roots (`CC`, `VSV`, `Walnut 1722`, `PSNL`, …).
