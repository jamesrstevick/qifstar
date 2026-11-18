# Schwab One 9593 → Quicken (research)

Rules for turning Schwab source data into a QIF for the Quicken register that holds this account. This note is only for **BRK Schwab One 9593**.

The manual file [`9593-2026-first-half.QIF`](9593-2026-first-half.QIF) is the truth for 1/1/2026–6/30/2026. It was exported from Quicken after the account was reconciled. Training sources: monthly PDFs in `C:\Users\james\OneDrive\JRSS Reconciliation\BRK Schwab One 9593`, and the transactions CSV [`Living_Trust_XXX593_Transactions_20261116-152255.csv`](Living_Trust_XXX593_Transactions_20261116-152255.csv) (Schwab export 1/1/2026–10/31/2026; only Jan–Jun used for rules). Working inputs for the generator live in this folder (`schwab_9593/`); the script is repo-root `schwab_9593_to_qif.py`; outputs go to `qif_files/schwab_9593_<MM-DD-YYYY>_<MM-DD-YYYY>_run<MMDDYYYY>.QIF`.

## Closed-month process (end-of-month statements)

This is a **month-closed** workflow, not a mid-cycle catch-up.

| | |
|---|---|
| Statement cadence | **End of month** (calendar month). Periods look like `September 1-30, 2026` / `Ending Value as of 09/30`. Not mid-month statements (some other accounts use those). |
| When you may run | Any calendar day is fine for *running the script*. |
| Which months to include | Only months that are **fully closed** and whose statement PDF is in hand. A month is closed after its last calendar day; the statement usually arrives a few days later. |
| Example | Running on **9/24** must **not** include September — September is still open and the Sep statement is not available. On 9/24 you may process August (and earlier unprocessed closed months) once the Aug statement exists. |
| Change in Market Value | Comes from that month’s statement Positions Summary. No statement ⇒ that month cannot be finalized in the QIF. |
| CSV | May contain activity in the current open month; still **exclude** open months from `--start` / `--end`. |

Practical rule: `--end` should be the latest month whose end-of-month statement PDF is present under the statements folder (and preferably reconciled / ready to book).

## Scope

| | |
|---|---|
| Quicken register | `Schwab One ...9593-Cash` (Schwab One trust `7845-9593`, Scherer–Stevick 2006 Family Trust). Type `Bank`. Buys and sells are not investment-lot transactions. |
| Truth files | `9593-2026-first-half.QIF`, `9593-2026-two-month.QIF` (in this folder) |
| Statements used | `BRK Schwab One 9593 2026 01 Jan` through `2026 06 June` (the `[REC …]` copies). Filename order is **year then month** so Explorer sorts chronologically. |
| Transactions CSV | `Living_Trust_*Transactions*.csv` in this folder — preferred for cash activity |
| Tickers | `schwab_9593_tickers.json` in this folder |
| Generator | Repo-root `schwab_9593_to_qif.py` → `qif_files/schwab_9593_<from>_<to>_run<MMDDYYYY>.QIF` |
| Not used for rules | 2025 statements. Jul–Oct 2026 used for live import tests after rules were set. |

Every month, the QIF lines for that month sum to **ending account value − beginning account value**. That is the check a new file has to pass.

## Where to read the statement

Use **Transaction Details** for cash movements. The date column is the settlement / process date. Ignore these sections:

- **Bank Sweep Activity.** Same money moving between brokerage cash and the sweep. Interest shows up here a day or two earlier than in Transaction Details. Take the Transaction Details row only.
- **Pending / Open Activity.** Not in account value. The payable month’s Transaction Details is the row that becomes a QIF line (April’s pending CVS dividend is the May 4 dividend; May’s pending Ford dividend is the June 1 dividend).
- **Income Summary and the page-1 Deposits / Withdrawals / Dividends totals.** Useful as a cross-check. The lines come from Transaction Details.
- **YTD column** on the account summary. This period only.

## What becomes a QIF line

| Statement row | QIF? |
|---|---|
| `Deposit` / `MoneyLink` | Yes. `NDEP` |
| `Withdrawal` to Schwab Bank `440000798045` or Bank of America | Yes. `NTXFR` to that Quicken account |
| `Withdrawal` / `Journaled Funds` to any other account | Yes, one line. Category and memo stay blank (see Coral Cove below) |
| `Interest` / `Bank Interest` | Yes. `NINT` |
| `Dividend` / `Qual. Dividend` or `Cash Dividend` | Yes. `NDIV` |
| `Dividend` / `Foreign Tax Paid` | Yes. Negative amount, still `NDIV`, same dividend category as the security |
| `Expense` / `ADR Pass Thru Fee` | Yes. Negative amount, `NFee`, same dividend category as the security |
| Positions Summary **Change in Market Value** | Yes. One `NChange` line per statement. Not a Transaction Details row |
| `Purchase`, `Sale` (stocks, ETFs, ADRs) | No |
| `Sale` or `Purchase` of `SNAXX` | No. $1 money fund; cash moving inside the account |
| `Qual Div Reinvest` and the matching `Purchase` / `Reinvested Shares` | No. Both rows. See March |
| Realized gain on a sale | No. Not its own line |
| Pending dividends, bank-sweep transfers, margin, positions, cost basis | No |

Commissions and industry fees sit inside the trade’s net amount. They are not separate lines. May’s realized gain of $2,555.48 is not a line either.

## Change in Market Value

One line per statement:

| Field | Value |
|---|---|
| Date | **Ending Value as of** date on Positions Summary (the statement period end) |
| Amount | The **Change in Market Value** column on **Positions - Summary**, this period, sign preserved. Parentheses are negative |
| `N` | `Change` |
| Payee | `Change In Value` |
| Memo | `Change in Investments` |
| Category | `Investments` |

That column is the fifth amount in the positions bridge:

`Beginning Value + Transfer of Securities + Dividends Reinvested + Cash Activity + Change in Market Value = Ending Value`

Do **not** use page 1 **Market Appreciation/(Depreciation)**. In a month with no reinvested dividend the two numbers are the same. In March they are not, and the truth file uses the positions column.

| Month | Page 1 Market Appreciation | Positions Change in Market Value | Truth QIF |
|---|---:|---:|---:|
| Jan | 20,934.51 | 20,934.51 | 20,934.51 on 1/30 |
| Feb | (9,469.60) | (9,469.60) | −9,469.60 on 2/28 |
| Mar | (19,480.11) | **(19,325.97)** | **−19,325.97** on 3/31 |
| Apr | 114,012.66 | 114,012.66 | 114,012.66 on 4/30 |
| May | 58,304.35 | 58,304.35 | 58,304.35 on 5/31 |
| Jun | 28,434.47 | 28,434.47 | 28,434.47 on 6/30 |

March is the proof. Ford paid $154.14 and reinvested it (`Qual Div Reinvest` plus `Purchase Reinvested Shares`, 11.4628 shares, on 3/2). That pair is not in the QIF. Page 1 appreciation is `(19,480.11)`, which is the positions change `(19,325.97)` plus the reinvested `(154.14)`. Booking page-1 appreciation **and** leaving the reinvested dividend out would miss the account value by $154.14. Booking the positions change and leaving the pair out matches the statement: ending $2,375,693.82 − beginning $2,360,375.89 = **$15,317.93**, and the March QIF sums to the same number.

For a new statement, date the Change line the Ending Value as of date. Same-day order next to a dividend does not matter; the truth file itself flips the order (March dividend then change, April change then dividend). January’s truth file is dated 1/30 instead of 1/31 — within the ≤2-day tolerance below.

## QIF shape

The truth export has no account header (it was pulled from one open register). A **generated** file must name the account the same way `airbnb_to_qif.py` does, so Quicken routes every line into the right register without a prompt:

```text
!Account
NSchwab One ...9593-Cash
TBank
^
!Type:Bank
D4/17'26
U13,677.43
T13,677.43
C*
NDEP
PBerkeley Eng
MGRS Salary
LGRS Salary, BEAR
^
```

| Field | Rule |
|---|---|
| Account block | Exactly once at the top: `!Account` / `NSchwab One ...9593-Cash` / `TBank` / `^`, then `!Type:Bank`. Match the Airbnb QIF pattern (`!Account`, `N…`, `TBank`, `^`). Name must match Quicken **exactly** (spaces, `...` vs `…`). |
| `D` | Transaction Details date, as `M/D'YY`, with a **space** before single-digit days (`9/ 1'26`, same as Airbnb QIF) |
| `U` and `T` | Same amount. Thousands separators. Leading minus when negative. No plus sign |
| `C` | `C*` on every transaction (same as Airbnb QIF imports) |
| `N` | `DEP`, `TXFR`, `INT`, `DIV`, `Fee`, or `Change` |
| `P` | Payee from the tables below |
| `M` | Salary memo `GRS Salary`; also dividend / interest / foreign tax / ADR fee / change-in-value memos. Transfer memos stay omitted |
| `L` | Category, or `[Quicken account]` for a transfer |
| Order | Newest → oldest (same as Airbnb QIF) |

Two statement rows that share a date, symbol, and action stay two lines. January 30 has SNAXX dividends of $602.73 and $5,856.47. February has SNAXX on 2/19 ($30.13) and 2/27 ($5,608.27). Do not combine them.

## Quicken import notes (Sep–Oct 2026 test)

Learned while importing the Sep–Oct 2026 generated QIF (`qif_files/schwab_9593_09-01-2026_10-31-2026_run….QIF`):

### Pick the account in the dialog

Import worked reliably when the Quicken QIF dialog’s destination account was set to **`Schwab One ...9593-Cash`** (and Transactions + Category List checked).

Why that matters ([Quicken Community](https://community.quicken.com/discussion/7947776/importing-qif-files-creates-separate-new-account)):

- If the file has an `!Account` / `N…` header, that name **overrides** the dropdown unless it matches an existing account **exactly**.
- A slight name mismatch (ellipsis character, spacing) can create a new account or route oddly.
- For a **single-account** QIF, Quicken users often omit the `!Account` block and only choose the account in the GUI. We still emit the header (Airbnb-style); **also select the correct account in the dialog** so the register is unambiguous.

### Partial imports / “skipped” lines

On an early import, Quicken accepted only 9 of 15 lines. The six skipped were not bad QIF records (same shape as lines that imported). Likely causes:

1. **Duplicate matching by amount** — Quicken can treat an import as a duplicate of an existing register row by **amount even when the dates differ** ([QIF notes](https://en.wikipedia.org/wiki/Quicken_Interchange_Format)). The skipped set fit that pattern (e.g. Ford **$155.86** also on 6/1; **−$75,000** transfer also on 1/26).
2. **Wrong/ambiguous account routing** before the destination was chosen explicitly — fixed by selecting `Schwab One ...9593-Cash` in the import dialog.

Also match Airbnb formatting on generated files: `C*` on every txn, space before single-digit days (`9/ 1'26`), newest-first order. Unrecognized-category prompts (e.g. first `Dividends:GOOG`) are expected; create the category when Quicken asks.

## Categories and payees

### Income

| Statement | `N` | Payee | Category |
|---|---|---|---|
| MoneyLink deposit, description starts `Berkeley Eng` (either case; the PDF cuts it off at “Berkeley Eng and”) | `DEP` | `Berkeley Eng` | `GRS Salary, BEAR` (memo always `GRS Salary`) |
| Bank Interest | `INT` | `Bank Int` | `Interest:Schwab One` |
| Cash or qualified dividend, symbol `SNAXX` | `DIV` | `Schwab SNAXX` | `Dividends:SNAXX` |
| symbol `CVS` | `DIV` | `CVS Stock Dividend` | `Dividends:CVS` |
| symbol `HD` | `DIV` | `Home Depot` | `Dividends:Home Depot` |
| symbol `F` | `DIV` | `Ford Motor Company` | `Dividends:Ford Motor` |
| symbol `NVO`, action qualified dividend | `DIV` | `Novo Nordisk Dividend` | `Dividends:NOVO` |
| symbol `NVO`, `Foreign Tax Paid` | `DIV` | `Novo Nordisk Foreign Tax` | `Dividends:NOVO` |
| symbol `NVO`, `ADR Pass Thru Fee` / CSV `ADR Mgmt Fee` | `Fee` | `Novo Nordisk ADR Pass Thru Fee` | `Dividends:NOVO` |
| symbol `NOK`, qualified dividend | `DIV` | `Nokia Dividend` | `Dividends:NOK` |
| symbol `NOK`, foreign tax / ADR fee | `DIV` / `Fee` | `Nokia Foreign Tax` / `Nokia ADR Pass Thru Fee` | `Dividends:NOK` |
| any other dividend symbol | `DIV` | `{TICKER} Dividend` | `Dividends:{TICKER}` |

Ticker list is **[`schwab_9593_tickers.json`](schwab_9593_tickers.json)** (this folder). The script is ticker-agnostic: defaults are `Dividends:{TICKER}` / `{TICKER} Dividend` (and matching foreign-tax / ADR payees). Known friendly names (Home Depot, NOVO, …) are overrides in that file. Any new `Symbol` seen in the CSV date range (including buys/sells) is appended automatically.

Foreign tax and the ADR fee stay in `Dividends:NOVO`. They are not a general expense category. Page 1 “Expenses (15.00)” in April is the ADR fee, and the truth file books that −$15.00 under `Dividends:NOVO`.

A dividend is included or dropped based on the **action**, not the reinvestment footnote. March Ford is `Qual Div Reinvest` and is omitted. June Ford is `Qual. Dividend` $155.86 and is included.

Memos that restate the action, taken from the truth file’s usual wording:

| Action | Memo |
|---|---|
| Cash or qualified dividend | `Dividend` |
| Bank interest | `Interest` |
| Foreign tax paid | `Foreign tax dividend` |
| ADR pass thru fee | `ADR pass Thru Fee` |
| Change in Market Value | `Change in Investments` |

The truth file sometimes says `Dividends` or `Qual dividend` or `Interest Earned`. Those are the same memo. Use the table.

### Transfers

Category is the Quicken account the statement names. Memo is empty. The truth file’s memos were typed from context and are not on the PDF.

| Statement destination | Category | Truth memos (do not generate) |
|---|---|---|
| `TRANSFER FUNDS TO SCHWAB BANK - 440000798045` | `[Chking Schwab ...045]` | “Transf from Schwab One to Checking”, “Funds needed for remodel from Brokerage -9593”, “Transfer to Checking” |
| `MoneyLink Txn Tfr` to `BANK OF AMERICA` / `ELIZABETH SCHERE` | `[Chkng Main BofA-0149]` | “Low balance transfer” (May 26 in the truth file is spelled “tranfer”) |
| `JOURNAL TO …709` (CSV truncation) | `[Auto Trader  XXXXX709]` | Memo blank; payee `Auto Trader` |
| `JOURNAL TO …384` | `[John Misc Loan]` | Different Quicken account than Auto Trader. Memo blank; payee `John Stevick` |
| `JOURNAL TO …580` (e.g. `21466580`) | HOA / Coral Cove **split** (see below) | **Not coded yet** — note only until percentage breakdowns are provided |

The Schwab Bank number on the statement ends in `045`, which is the Quicken account. The Bank of America number `0149` is **not** on the statement; the counterparty text is the match, and all four H1 transfers use that one account.

Payee for both Schwab Bank `…045` and Bank of America transfers: **`From 9593 Schwab One`** (matches Jul–Oct truth / BofA H1 lines). Older H1 nicknames (`Move Money From 9593`, `Transfer To Checking`, …) are not used. Memo stays empty.

Any other withdrawal: one `NTXFR` line, amount and date from Transaction Details, **no memo and no category**. Do not guess a split.

### HOA / Coral Cove (`…580`) — note only, do not code yet

A journal or transfer **into account `…580`** (statement `JOURNAL TO 21466580`, CSV `JOURNAL TO ...580`) is a transfer into the **HOA** account. In Quicken it should be a **split**, not a single blank transfer. That split pattern is already saved in Quicken.

**Example (1/29/2026, total −$11,006.30)** from the truth file — payee `Coral Cove Condo Assn`, memo `Assessments`, each split memo `1st and 2nd Q of 2024`:

| Category | Amount |
|---|---:|
| `CC2:Assessments` | −1,347.96 |
| `CC3:Assessments` | −1,409.80 |
| `CC4:Assessments` | −1,409.80 |
| `CC5:Assessments` | −1,793.16 |
| `CC6:Assessments` | −2,176.52 |
| `CC7:Assessments` | −2,869.06 |
| | **−11,006.30** |

**TODO (later):** when percentage breakdowns (or fixed shares) per `CC2`–`CC7` are provided, code the generator to emit this QIF split for any `…580` journal. Until then, leave `…580` unmapped in code (blank category/memo import, or skip automation). Do not hard-code the January dollar amounts as the permanent rule — they are one assessment batch, not necessarily the ongoing %.

## Salary memo

Every Berkeley Eng deposit gets memo **`GRS Salary`** and category `GRS Salary, BEAR` (matches the truth file). The statement/CSV only say `Berkeley Eng and`; the memo is a fixed Quicken convention, not parsed from Schwab.

## Dates: statement vs truth file

Amounts match in every case. A new file always uses the **Transaction Details** date (or the Ending Value as of date for Change in Market Value). Bank-sweep interest dates (the 15th) are not the QIF date — take Transaction Details.

**Tolerance:** same month and within **2 days** of the statement date is fine. Do not treat those as mismatches when checking a generated file against this truth export.

### Acceptable (≤2 days)

| Statement | Truth QIF | Δ days | Amount | What it is |
|---|---|---:|---:|---|
| 1/31 Change in Market Value | 1/30 | 1 | 20,934.51 | Change in value |
| 4/8 journal to Schwab Bank `…045` | 4/6 | 2 | −50,000.00 | Transfer to `[Chking Schwab ...045]` |
| 5/14 MoneyLink to Bank of America | 5/15 | 1 | −30,000.00 | Transfer to `[Chkng Main BofA-0149]` |
| 5/26 MoneyLink to Bank of America | 5/27 | 1 | −20,000.00 | Transfer to `[Chkng Main BofA-0149]` |

### Flagged — more than 2 days (likely manual error)

Decide later whether to trust the statement/CSV date, fix Quicken, or leave the truth file alone. Generator should still emit the **statement / CSV primary** date.

| Statement / CSV | Truth QIF | Δ days | Amount | What it is | Notes |
|---|---|---:|---:|---|---|
| 5/18 bank interest | 5/4 | **14** | 0.36 | `Interest:Schwab One` | Truth date is the same day as the May 4 Berkeley Eng deposit and CVS dividend. Statement and CSV both post mid-month (CSV `05/18/2026 as of 05/15/2026`). |
| 5/22 MoneyLink to Bank of America | 5/26 | **4** | −30,000.00 | Transfer to `[Chkng Main BofA-0149]` | Same month, but past the 2-day window. Neighboring BofA transfers are only ±1 day off. CSV primary is 5/22, same as the statement. |
| 6/30 SNAXX cash dividend | 6/18 | **12** | 5,962.82 | `Dividends:SNAXX` | Truth file put this on the same day as the June 18 salary and HD dividend. Statement Transaction Details and CSV both have **6/30**. |
| 7/23 journal to Schwab Bank `…045` (−25,000) | 7/31 | **8** | −25,000.00 | Transfer to `[Chking Schwab ...045]` | From `9593-2026-two-month.QIF` vs CSV/generator. Fix the Quicken date to **7/23**. |
| 8/17 bank interest | 8/11 | **6** | 1.56 | `Interest:Schwab One` | Two-month truth dated 8/11 (same day as NOK dividend). CSV is `08/17/2026 as of 08/15/2026`. Fix Quicken to **8/17**. |

Programmatic imports use the CSV primary date, so new months should not recreate these date misses. The rows above are only for cleaning up already-entered Quicken data.

## Month by month

Omitted rows are listed so a later pass does not “fix” them back in. Amounts are the statement amounts.

### January (period end 1/31)

Beginning $2,389,075.21 → ending $2,336,785.54. Change in value **+20,934.51**.

| Date | What | Amount | QIF |
|---|---|---:|---|
| 1/2 | Sale SNAXX 100,000 sh | +100,000.00 | omit |
| 1/14 | Buy DTREF, EULIF, INTC, JPAN, NVO | −141,797.45 | omit |
| 1/16 | Buy CPER | −32,956.84 | omit |
| 1/16 | Bank interest 12/16/25–1/15/26 | +0.89 | `INT` → `Interest:Schwab One` |
| 1/20 | MoneyLink Berkeley Eng | +13,322.03 | `DEP` → `GRS Salary, BEAR` |
| 1/21 | Journal to Schwab Bank `…045` | −7,000.00 | `TXFR` → `[Chking Schwab ...045]`, memo empty |
| 1/22 | Buy INTC | −5,291.50 | omit |
| 1/26 | Sale SNAXX 100,000 sh | +100,000.00 | omit |
| 1/26 | Journal to Schwab Bank `…045` | −75,000.00 | `TXFR` → `[Chking Schwab ...045]`, memo empty |
| 1/29 | Journal to 21466580 | −11,006.30 | one `TXFR`, category and memo empty |
| 1/30 | SNAXX cash dividend | +602.73 | `DIV` |
| 1/30 | SNAXX cash dividend | +5,856.47 | `DIV` |
| 1/31 | Change in Market Value | +20,934.51 | `Change` (truth 1/30, ≤2 days OK) |

### February (period end 2/28)

Beginning $2,336,785.54 → ending $2,360,375.89. Change in value **−9,469.60**. No trades.

| Date | What | Amount | QIF |
|---|---|---:|---|
| 2/2 | CVS qualified dividend | +66.50 | `DIV` → `Dividends:CVS` |
| 2/3 | MoneyLink Berkeley Eng | +13,677.43 | `DEP` |
| 2/17 | Bank interest 1/16–2/15 | +0.19 | `INT` |
| 2/18 | MoneyLink Berkeley Eng | +13,677.43 | `DEP` |
| 2/19 | SNAXX cash dividend | +30.13 | `DIV` |
| 2/27 | SNAXX cash dividend | +5,608.27 | `DIV` |
| 2/28 | Change in Market Value | −9,469.60 | `Change` |

### March (period end 3/31)

Beginning $2,360,375.89 → ending $2,375,693.82. Change in value **−19,325.97**. Page 1 appreciation `(19,480.11)` is the wrong number.

| Date | What | Amount | QIF |
|---|---|---:|---|
| 3/2 | Ford qualified div reinvest | +154.14 | omit |
| 3/2 | Purchase reinvested Ford shares | −154.14 | omit |
| 3/4 | MoneyLink Berkeley Eng | +14,048.38 | `DEP` |
| 3/16 | Bank interest 2/16–3/15 | +0.44 | `INT` |
| 3/18 | MoneyLink Berkeley Eng | +14,558.53 | `DEP` |
| 3/26 | HD qualified dividend | +58.25 | `DIV` → `Dividends:Home Depot` |
| 3/31 | SNAXX cash dividend | +5,978.30 | `DIV` |
| 3/31 | Change in Market Value | −19,325.97 | `Change` |

Pending on this statement: NVO qualified dividend $1,275.10 payable 4/8. It is an April line, not a March line. April then splits it into the $1,217.38 dividend, −$328.69 foreign tax, and −$15.00 ADR fee (those three are the April cash; the pending figure is the gross estimate).

### April (period end 4/30)

Beginning $2,375,693.82 → ending $2,443,906.01. Change in value **+114,012.66**.

| Date | What | Amount | QIF |
|---|---|---:|---|
| 4/6 | MoneyLink Berkeley Eng | +13,677.43 | `DEP` |
| 4/8 | Journal to Schwab Bank `…045` | −50,000.00 | `TXFR` → `[Chking Schwab ...045]` (truth 4/6, ≤2 days OK) |
| 4/8 | NVO qualified dividend | +1,217.38 | `DIV` → `Dividends:NOVO` |
| 4/8 | NVO foreign tax paid | −328.69 | `DIV` → `Dividends:NOVO` |
| 4/8 | NVO ADR pass thru fee | −15.00 | `Fee` → `Dividends:NOVO` |
| 4/14 | MoneyLink Bank of America | −30,000.00 | `TXFR` → `[Chkng Main BofA-0149]`, memo empty |
| 4/16 | Bank interest 3/16–4/15 | +0.66 | `INT` |
| 4/17 | MoneyLink Berkeley Eng | +13,677.43 | `DEP` |
| 4/30 | SNAXX cash dividend | +5,970.32 | `DIV` |
| 4/30 | Change in Market Value | +114,012.66 | `Change` |

Pending: CVS $66.50 payable 5/4. That is the May dividend.

### May (period end 5/31)

Beginning $2,443,906.01 → ending $2,457,815.71. Change in value **+58,304.35**.

| Date | What | Amount | QIF |
|---|---|---:|---|
| 5/4 | MoneyLink Berkeley Eng | +14,409.03 | `DEP` |
| 5/4 | CVS qualified dividend | +66.50 | `DIV` |
| 5/14 | Buy NOK, buy PLAB | −7,332.50 and −5,267.00 | omit |
| 5/14 | MoneyLink Bank of America | −30,000.00 | `TXFR` (truth 5/15, ≤2 days OK) |
| 5/18 | Bank interest 4/16–5/15 | +0.36 | `INT` — **flagged**: truth dated 5/4 (14 days off) |
| 5/19 | MoneyLink Berkeley Eng | +15,009.23 | `DEP` |
| 5/22 | MoneyLink Bank of America | −30,000.00 | `TXFR` — **flagged**: truth dated 5/26 (4 days off) |
| 5/26 | Sale EULIF, NOK, CPER | +8,058.87, +3,064.90, +7,721.80 | omit, including realized gain $2,555.48 |
| 5/26 | MoneyLink Bank of America | −20,000.00 | `TXFR` (truth 5/27, ≤2 days OK) |
| 5/29 | SNAXX cash dividend | +6,120.23 | `DIV` |
| 5/31 | Change in Market Value | +58,304.35 | `Change` |

Pending: Ford $155.86 payable 6/1. That is the June dividend.

### June (period end 6/30)

Beginning $2,457,815.71 → ending $2,522,990.13. Change in value **+28,434.47**. No trades.

| Date | What | Amount | QIF |
|---|---|---:|---|
| 6/1 | Ford qualified dividend | +155.86 | `DIV` → `Dividends:Ford Motor` |
| 6/3 | MoneyLink Berkeley Eng | +15,357.83 | `DEP` |
| 6/16 | Bank interest 5/16–6/15 | +0.12 | `INT` |
| 6/18 | MoneyLink Berkeley Eng | +15,205.07 | `DEP` |
| 6/18 | HD qualified dividend | +58.25 | `DIV` |
| 6/30 | SNAXX cash dividend | +5,962.82 | `DIV` — **flagged**: truth dated 6/18 (12 days off) |
| 6/30 | Change in Market Value | +28,434.47 | `Change` |

## CSV export (Jan–Jun training)

Sample: [`Living_Trust_XXX593_Transactions_20261116-152255.csv`](Living_Trust_XXX593_Transactions_20261116-152255.csv). Columns: `Date`, `Action`, `Symbol`, `Description`, `Quantity`, `Price`, `Fees & Comm`, `Amount`.

**Verdict:** the CSV is enough for every cash QIF line in the truth window. Prefer it over scraping Transaction Details from the PDF. It is **not** enough alone: Change in Market Value (and beginning/ending values for the month tie-out) still come from the monthly statement Positions Summary.

### Include / omit by `Action`

| CSV `Action` | QIF? | Maps like |
|---|---|---|
| `MoneyLink Deposit` | Yes | `NDEP` |
| `MoneyLink Transfer` | Yes | `NTXFR` (Bank of America) |
| `Journal` | Yes | `NTXFR` (Schwab Bank `…045`, or blank category if other) |
| `Bank Interest` | Yes | `NINT` |
| `Cash Dividend` / `Qualified Dividend` | Yes | `NDIV` |
| `Foreign Tax Paid` | Yes | `NDIV` (negative) |
| `ADR Mgmt Fee` | Yes | `NFee` (statement called this ADR Pass Thru Fee) |
| `Buy` / `Sell` | No | including SNAXX |
| `Qual Div Reinvest` / `Reinvest Shares` | No | March Ford pair |
| (no CSV row) | Yes | monthly Change in Market Value from the PDF |

Descriptions are truncated (`…045`, `…580`, `Berkeley Eng and`) but still enough for the destination rules. `Credit Interest` did not appear in H1; treat like `Bank Interest` if it shows up.

### Dates: primary vs `as of`

Some CSV dates look like `06/16/2026 as of 06/15/2026`. **Use the first date only** (process / settle). Ignore the `as of` date for the QIF `D` field.

In Jan–Jun, **every included CSV primary date matches the statement Transaction Details date exactly** (41/41). No included row landed in the wrong month vs the statement.

The month-boundary worry (CSV in December, statement in January) did **not** show up on included rows in this window. What did show up is the opposite trap if you used `as of`:

| CSV Date field | Primary | as of | Amount | What happens |
|---|---|---|---:|---|
| `02/19/2026 as of 01/30/2026` | 2/19 | 1/30 | 30.13 | SNAXX cash dividend. Statement and truth both use **2/19**. Using `as of` would put a February dividend into January. |

Other `as of` rows in H1 stay in the same month (bank interest as-of the 15th; two MoneyLink deposits as-of 1–3 days earlier). Always take the primary date.

### CSV vs truth QIF dates

Same tolerance as above (≤2 days OK). The three **flagged** truth dates are still wrong vs the CSV primary. Coral Cove is CSV/statement 1/29 vs truth 1/28 (1 day, OK).

### Buys/sells: trade date vs settlement

Omitted trades often sit **1–4 days earlier** on the CSV than on the statement (CSV looks like trade date; statement Transaction Details is settlement). Examples: Jan buys 1/13 vs statement 1/14; May sales 5/22 vs statement 5/26. Irrelevant for the QIF as long as those actions stay omitted.

### Export window caveat

This sample’s earliest row is **1/13/2026**, not 1/1. The 1/2 SNAXX sell on the January statement is missing from the CSV. That row would be omitted anyway. For a real run, confirm the export covers the full period you intend to book; do not assume “requested 1/1” means the file starts on 1/1.

## Tie-out

Non-change QIF lines equal external cash (deposits, withdrawals, cash dividends, foreign tax, ADR fee, bank interest). Buys, sells, SNAXX trades, and reinvest pairs are out. Adding Change in Market Value equals the change in account value.

| Month | External cash | Change in Market Value | Sum | Ending − beginning |
|---|---:|---:|---:|---:|
| Jan | −73,224.18 | 20,934.51 | −52,289.67 | −52,289.67 |
| Feb | 33,059.95 | −9,469.60 | 23,590.35 | 23,590.35 |
| Mar | 34,643.90 | −19,325.97 | 15,317.93 | 15,317.93 |
| Apr | −45,800.47 | 114,012.66 | 68,212.19 | 68,212.19 |
| May | −44,394.65 | 58,304.35 | 13,909.70 | 13,909.70 |
| Jun | 36,739.95 | 28,434.47 | 65,174.42 | 65,174.42 |

May’s external-cash figure is not the Transaction Details total `(38,148.58)`. That total includes the buys and sells. Strip those (net +6,246.07 of sale proceeds over purchases) and the remainder is −44,394.65, which is also the Positions Summary cash-activity column after the same removal. January works the same way once the SNAXX sales and the stock purchases are removed (Transaction Details total `(53,269.97)` versus external cash −73,224.18).

## A new month (recommended path)

1. Confirm the month(s) are **closed** and the **end-of-month** statement PDF is available (see Closed-month process above). Do not include the current open month.
2. Open the QIF with `!Account` / `NSchwab One ...9593-Cash` / `TBank` / `^` / `!Type:Bank`.
3. Prefer the transactions CSV for cash activity. Filter to the closed statement month(s). Use the **primary** date only (strip ` as of …`). Emit lines for include-actions; skip Buy/Sell/reinvest.
4. Map symbol and destination with the tables above. Unknown deposit / dividend / journal still becomes a line: date, amount, payee from the source, **category blank, memo blank**.
5. From that month’s PDF Positions Summary, add one Change line (Change in Market Value, Ending Value as of date). Optionally read beginning/ending account value for the tie-out.
6. Check that the lines sum to ending account value minus beginning account value.
7. Do not copy memos from this truth file onto transfers or unknown journals. Salary memo is always `GRS Salary`.

PDF Transaction Details remain a fallback if there is no CSV; the include/omit and category rules are the same.
