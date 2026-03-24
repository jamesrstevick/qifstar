# qifstar

Convert Airbnb payout CSV exports into Quicken-compatible QIF files for import. Uses a date range (typically by month) so you can avoid overlapping transactions when importing into Quicken.

## What it does

- Reads the Airbnb CSV from `airbnb_files/` (exported from your Airbnb payout/transaction history).
- Groups **Payout** rows with their **Reservation** (and related) rows into single QIF transactions.
- Maps each listing to your Quicken category (e.g. `Rental Inc:Villas:VSV1`) and writes split transactions when one payout covers multiple reservations.
- Filters by a configurable date range and writes one QIF file per run to `qif_files/`, named by that range (e.g. `qifstar_01-01-2026_02-28-2026.QIF`).

## Requirements

- Python 3.x
- Dependencies in `requirements.txt` (see below)

## Setup

1. Clone or download this repo.
2. Create a virtual environment (recommended) and install dependencies:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # macOS/Linux
   pip install -r requirements.txt
   ```

3. Put your Airbnb CSV in the `airbnb_files/` folder. The script uses the first CSV it finds in that folder.
4. Ensure the `qif_files/` folder exists (the script checks for it).

## How to run

1. **Set your date range and accounts** in `airbnb_to_qif.py` (near the top):

   ```python
   # Accounts to include in the QIF (from header.py)
   accounts = [CH_CHK_1687, BOFA_CHK_0149]

   # Date filter: include transactions in this range (MM/DD/YYYY)
   start_date = "01/01/2026"
   end_date = "02/28/2026"
   ```

2. Run the converter:

   ```bash
   python airbnb_to_qif.py
   ```

3. The script will:
   - Read the CSV from `airbnb_files/`,
   - Filter transactions by the date range,
   - Write a QIF file to `qif_files/qifstar_<start>_<end>.QIF`.

4. Import the generated QIF file into Quicken (File → Import).

Using **monthly** date ranges (e.g. 01/01/2026–01/31/2026) helps avoid importing the same transactions more than once.

## Project layout

| Path               | Purpose |
|--------------------|--------|
| `airbnb_to_qif.py` | Main converter: CSV → QIF with date filter and splits |
| `header.py`        | Constants: folder names, account names, CSV/QIF column names, listing→category mapping |
| `airbnb_files/`    | Input: place your Airbnb CSV here |
| `qif_files/`       | Output: generated QIF files |
| `records.txt`      | Referenced by script (for future use, e.g. tracking processed months) |
| `convert_script.py`| Older Mint-to-Quicken script (incomplete; not required for Airbnb conversion) |

## Customization

- **Accounts**  
  Defined in `header.py` (e.g. `CH_CHK_1687`, `BOFA_CHK_0149`). The script matches rows to accounts using the “Details” column (e.g. “Checking 1687”, “Checking 0149”). Add or change accounts in `header.py` and in the `accounts` and `account_numbers` dict in `airbnb_to_qif.py`.

- **Listing → Quicken category**  
  The mapping is in `airbnb_to_qif.py` in `airbnb_to_quicken_properties`. Add or edit listing names and their Quicken category strings (e.g. `Rental Inc:Villas:VSV1`) to match your chart of accounts.

## CSV format

The script expects an Airbnb payout/transaction export CSV with columns including: Date, Type (e.g. Payout, Reservation), Start date, End date, Confirmation code, Nights, Guest, Listing, Details, Paid out, Amount. Column names are aligned with `header.py` (e.g. `Start date`, `End date`, `Confirmation code`).

## License

Use and modify as you like. No warranty.
