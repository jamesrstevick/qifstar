# qifstar

Convert Airbnb year-to-date payout CSV exports into Quicken-compatible QIF files. **Duplicate imports are avoided** by logging each payout’s **Reference code** after a successful run; the next run only imports payouts that are not already in the log.

## What it does

- Expects **one** `airbnb_*.csv` at the **repo root** (e.g. `airbnb_12_2025-03_2026.csv`), not inside `airbnb_files/`.
- Groups each **Payout** row with the **Reservation**, **Resolution Adjustment**, and **Misc Credit** rows that belong to it.
- Maps listings to Quicken categories (`airbnb_to_quicken_properties` in `airbnb_to_qif.py`); writes **split** lines when one payout has multiple reservations.
- **Misc Credit–only** payouts (e.g. Prohost incentives) become a single QIF line (payee/memo/category from `header.py`).
- Matches payouts to bank accounts using the **Details** text (checking numbers). Only accounts listed in **`accounts`** in `airbnb_to_qif.py` are written to the QIF; other accounts (e.g. a third checking) are still parsed but not exported.
- **All-or-nothing:** if anything fails validation (unknown listing for a written account, split totals ≠ payout, mixed Misc Credit + reservations, etc.), the run stops with **FAILED** — **no** QIF, **no** `logs.csv` append, **no** archive move for that run.
- On **success:** writes the QIF, **appends** a row to **`logs.csv`**, and moves the source CSV to **`airbnb_files_archive/`** as `originalname_PROCESSED_MMDDYYYY.csv`.

## Requirements

- Python 3.x
- `pip install -r requirements.txt` (pandas)

## Setup

1. Clone or download this repo.
2. Create a venv and install dependencies:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # macOS/Linux
   pip install -r requirements.txt
   ```

3. Ensure **`qif_files/`** exists (the script errors if it is missing). **`airbnb_files_archive/`** is created if needed.
4. Configure **`accounts`** in `airbnb_to_qif.py` (which Quicken bank accounts get QIF sections). Full account matching uses **`all_acounts`** and **`account_numbers`** in the same file plus names in **`header.py`**.

## How to run

1. **Close** the CSV in Excel or other apps so it is not locked.
2. Place **exactly one** `airbnb_*.csv` at the **repository root** (filenames containing `_PROCESSED_` are ignored by the picker).
3. Run:

   ```bash
   python airbnb_to_qif.py
   ```

4. **First run** with an empty or missing `logs.csv` imports **every** payout in that file. For a mid-year start, either use a CSV that only contains rows you have not yet imported, or seed **`payout_refs`** in `logs.csv` from earlier imports.
5. **Later runs:** the script skips any payout whose **Reference code** already appears in **`payout_refs`** in any row of `logs.csv`. It also checks that new payout dates are not **before** the previous run’s **`last_txn_date`** (sanity check).
6. Import the new QIF from `qif_files/` into Quicken.

### Terminal output (success)

- Date range covered by this batch  
- Transaction count **per** configured account  
- **SUCCESS:** path to the QIF  
- **Log updated:** path to `logs.csv`  
- Message when the source file is archived (or a warning if the file could not be deleted after copy).

On **failure**, you get **FAILED**, the error message, and a note that the QIF, log, and source CSV were **not** updated (for errors raised as `RuntimeError` before those steps).

### If there is nothing new

If every payout in the file was already logged, the script prints that there is nothing to do and exits without writing a QIF or changing files.

## Project layout

| Path | Purpose |
|------|--------|
| `airbnb_to_qif.py` | Main converter: discovery, validation, QIF build, log append, archive |
| `header.py` | Folders, account display names, CSV column names, Misc Credit labels |
| `logs.csv` | One row per successful run; **`payout_refs`** lists Reference codes written to the QIF (for dedup) |
| `qif_files/` | Output QIF files (`qifstar_<from>_<to>_run<MMDDYYYY>.QIF`) |
| `airbnb_files_archive/` | Processed source CSVs renamed with `_PROCESSED_MMDDYYYY` |
| `airbnb_files/` | Legacy / optional; not used as the primary input path |
| `.gitignore` | Ignores typical finance exports and QIFs; **`logs.csv` is not ignored** |
| `convert_script.py` | Old Mint → QIF experiment (incomplete) |

## Customization

- **Accounts in the QIF:** `accounts` vs `all_acounts` and `account_numbers` in `airbnb_to_qif.py`; display names in `header.py`.
- **Listing → category:** `airbnb_to_quicken_properties` in `airbnb_to_qif.py`.

## CSV format

Airbnb payout export with columns including: **Date**, **Type**, **Start date**, **End date**, **Confirmation code**, **Nights**, **Guest**, **Listing**, **Details**, **Reference code**, **Paid out**, **Amount**. Names match `header.py`. Every **Payout** row must have a non-empty **Reference code**; non-empty reference codes must be **unique** in the file.

## License

Use and modify as you like. No warranty.
