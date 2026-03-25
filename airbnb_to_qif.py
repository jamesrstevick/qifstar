###########################################
# AIRBNB TO QIF FILE CONVERTER
###########################################
# Date: 6/11/2025
# Python 3.0
# Version 1.0
###########################################


# Imported Libraries
import csv
import glob
import os
import shutil
import sys
from datetime import datetime
import pandas as pd
from tkinter import messagebox
from header import *  # includes TYPES_AS_SPLITS


###########################################
# INPUTS
###########################################
# Accounts to include in the QIF (only these are written); all_acounts below is used only to match payouts
accounts = [CH_CHK_1687, BOFA_CHK_0149]  # CH_CHK_1687, BOFA_CHK_0149
# Put one airbnb_*.csv at repo root (YTD export). Successful runs append logs.csv and archive the CSV to
# airbnb_files_archive as name_PROCESSED_MMDDYYYY.csv. Next run skips payouts already in logs (by Reference code).
# If logs.csv is empty, every payout in the file is imported—use a CSV that only has new rows since last Quicken
# import, or seed logs.csv with prior payout_refs if you are mid-year.
###########################################




all_acounts = [CH_CHK_1687, BOFA_CHK_0149, JOHN_CHK_7949]
airbnb_keys = [DATE, TYPE, ARRIVE, DEPART, CONF_CODE, NIGHTS, GUEST, LISTING, DETAILS, PAYOUT, AMOUNT, REFERENCE_CODE]
quicken_keys = [DATE, ARRIVE, DEPART, CONF_CODE, NIGHTS, GUEST, LISTING, DETAILS, PAYOUT, AMOUNT]


# Dictionaries
account_numbers = {CH_CHK_1687:'1687',
                   BOFA_CHK_0149:'0149',
                   JOHN_CHK_7949:'7949'}

airbnb_to_quicken_properties = {'Private Room in a 10-BR Grad/Post Doc Villa House!':'Rental Inc:Villas:VSV1',
                                'Private BR in Friendly 10BR Grad / Post Doc House!':'Rental Inc:Villas:VSV2',
                                'Private Bedroom in Graduate Student House':'Rental Inc:Villas:VSV3',
                                'Cozy private room in Graduate House':'Rental Inc:Villas:VSV4',
                                'Grad Study Bedroom Close 2 UCB':'Rental Inc:Villas:VSV5',
                                'Peaceful Private Grad Study Room':'Rental Inc:Villas:VSV6',
                                'Largest room - grad student home':'Rental Inc:Villas:VSV7',
                                'Private Spacious Grad Room':'Rental Inc:Villas:VSV8',
                                'Corner Room in Big Grad House':'Rental Inc:Villas:VSV9',
                                'Private Room in Quiet Grad House':'Rental Inc:Villas:VSV10',
                                'Guest Room w/ Private Bathroom Close to Dwtn & UCB':'Rental Inc:Wal 1722:Guest Room',
                                'Bright, Furnished 1BR with Charm, Close to Campus':'Rental Inc:Wal 1722:Wal1',
                                'Quiet North Berkeley Apartment Next to Campus':'Rental Inc:Wal 1722:Wal2',
                                'Two Blocks to Campus and Downtown (Northside)':'Rental Inc:Wal 1722:Wal3',
                                'Large 1-BR Apartment with Old World Charm':'Rental Inc:Wal 1722:Wal4',
                                'Cozy North Berkeley Apt in Prime Location':'Rental Inc:Wal 1722:Wal5',
                                'Great Spacious 1-BR Right by Campus + Gourmet Dwtn':'Rental Inc:Wal 1722:Wal6',
                                'Spacious 2nd Floor 1-BR Apt in the Heart of Berk!':'Rental Inc:Wal 1722:Wal7',
                                'Lovely North Berkeley Apt-Just Blocks to Downtown':'Rental Inc:Wal 1722:Wal8',
                                'North Berkeley + Super Central':'Rental Inc:Wal 1722:Wal9',
                                'Ground floor bungalow unit close to campus':'Rental Inc:Wal 1722:Wisteria',
                                'Stay Right on the Beach!':'Rental Inc:Coral Cove:CC2',
                                'Oceanfront Elegance - Sun Sand & Style':'Rental Inc:Coral Cove:CC3',
                                'Stay on the Beach!':'Rental Inc:Coral Cove:CC4',
                                'Delray Beach Villa on the Ocean':'Rental Inc:Coral Cove:CC5',
                                'Seaside Serenity: Chic 1-Bed/2-Bath on A1A':'Rental Inc:Coral Cove:CC6',
                                'Cozy beach bungalow steps to the Sand!':'Rental Inc:Coral Cove:CC7',
                                'Spacious Victorian Home':'Rental Inc:Carriage House:CH1',
                                'Modern Apartment in North Berkeley':'Rental Inc:Carriage House:CH2',
                                'Modern Apartment in Great North Berkeley Area':'Rental Inc:Carriage House:CH3',
                                'Big Remodeled 3BR w/ Lush Garden':'Rental Inc:Carriage House:CHA',
                                'Sunny 3BR/2BA Duplex Unit - 2nd Floor':'Rental Inc:Carriage House:CHB',
                                'Charming Kennebunkport Coastal Home':'Rental Inc:Glen Cove'}

properties = {'W':'1722 Walnut',
              'H':'1636 Walnut',
              'VSV':'1446 MLK',
              'CH':'1716 Rose',
              'MH':'100 Ocean',
              'CC':'88 S Ocean',
              'MC':'301 NE 6th',
              'PSNL':'Personal'}

units = {'W':['1','2','3','4','5','6','7','8','9'],
         'H':['G','A','B'],
         'VSV':['1','2','3','4','5','6','7','8','9','10'], 
         'CH':['1','2','3','A','B'],
         'MH':[''],
         'CC':['2','3','4','5','6','7'],
         'MC':['1','2','3','4','5','6','7','8','9']}

months = {'1':'January',
          '2':'February',
          '3':'March',
          '4':'April',
          '5':'May',
          '6':'June',
          '7':'July',
          '8':'August',
          '9':'September',
          '10':'October',
          '11':'November',
          '12':'December'}

# Helper Functions
# def add_transaction(date, amount, check, payee, memo, category):
#     #TODO: Write transaction function
#     pass

def quicken_date(date):
    if not isinstance(date, str):
        date = pd.to_datetime(date).strftime("%m/%d/%Y")
    date_splits = date.split('/')
    day = date_splits[0]
    month = date_splits[1]
    year = date_splits[2]
    if day[0] == '0':
        day = day[1]
    if month[0] == '0':
        month = ' ' + month[1]
    year = year[-2:]
    return day + '/' + month + "'" + year

def shorter_date(date):
    if not isinstance(date, str):
        date = pd.to_datetime(date).strftime("%m/%d/%Y")
    date_splits = date.split('/')
    day = date_splits[0]
    month = date_splits[1]
    year = date_splits[2]
    if day[0] == '0':
        day = day[1]
    if month[0] == '0':
        month = month[1]
    year = year[-2:]
    return day + '/' + month + '/' + year

def _safe_str(val):
    """Convert CSV value to str; treat NaN/empty as ''."""
    if pd.isna(val):
        return ''
    return str(val).strip()


def _parse_csv_date(val):
    """Parse Date column from CSV (handles Timestamp / string)."""
    s = str(val).strip().split()[0]
    return datetime.strptime(s, DATE_TIME_FORMAT)

def create_memo(row_dict):
    guest = _safe_str(row_dict[GUEST])
    memo = guest + ", " +\
    shorter_date(row_dict[ARRIVE]) +\
    "-" + shorter_date(row_dict[DEPART]) +\
    " ({} Nights) [{}]".format(int(row_dict[NIGHTS]), _safe_str(row_dict[CONF_CODE]))
    return memo

# Memo in split can only handle 25 characters
def create_short_memo(row_dict):
    input_name = _safe_str(row_dict[GUEST])
    name_split = input_name.split(" ") if input_name else ['']
    name_split_filtered = [x for x in name_split if x != '']
    name = name_split_filtered[-1] if name_split_filtered else ''
    conf = _safe_str(row_dict[CONF_CODE])
    memo = name[:12] + " [{}]".format(conf)
    return memo


def _find_source_airbnb_csv(main_folder):
    """Single airbnb_*.csv at repo root; exclude already-archived PROCESSED copies."""
    pattern = os.path.join(main_folder, "airbnb_*.csv")
    candidates = [p for p in glob.glob(pattern) if "_PROCESSED_" not in os.path.basename(p)]
    if len(candidates) == 0:
        raise RuntimeError(
            f"No airbnb_*.csv found in {main_folder}. Place a YTD export named like airbnb_12_2025-03_2026.csv here."
        )
    if len(candidates) > 1:
        raise RuntimeError(
            "Multiple airbnb_*.csv files at repo root; leave only one export:\n  " + "\n  ".join(candidates)
        )
    return candidates[0]


def _assert_reference_codes_unique(df):
    """Non-empty Reference code values must be unique across the file."""
    seen = {}
    for idx, row in df.iterrows():
        ref = _safe_str(row[REFERENCE_CODE])
        if not ref:
            continue
        if ref in seen:
            raise RuntimeError(
                f"Duplicate Reference code in CSV: {ref!r} (rows at index {seen[ref]} and {idx})."
            )
        seen[ref] = idx


def _assert_payout_rows_have_reference(df):
    for idx, row in df.iterrows():
        if row[TYPE] == TYPE_PAYOUT and not _safe_str(row[REFERENCE_CODE]):
            raise RuntimeError(
                f"Payout on {row[DATE]} has no Reference code; cannot track or deduplicate imports."
            )


def _filter_unprocessed_payout_rows(df, already_refs):
    """Keep rows of payout groups whose payout Reference code is not in already_refs."""
    mask = []
    include = True
    saw_payout = False
    for _, row in df.iterrows():
        if row[TYPE] == TYPE_PAYOUT:
            saw_payout = True
            ref = _safe_str(row[REFERENCE_CODE])
            include = ref not in already_refs
        elif not saw_payout:
            include = False
        mask.append(include)
    return df.loc[mask].reset_index(drop=True)


def _load_logs_state(logs_path):
    """Returns (set of all payout refs from prior runs, last_txn_date from last row or None)."""
    if not os.path.isfile(logs_path):
        return set(), None
    with open(logs_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return set(), None
    all_refs = set()
    for r in rows:
        pr = r.get("payout_refs") or ""
        for x in pr.split(","):
            x = x.strip()
            if x:
                all_refs.add(x)
    last = rows[-1]
    last_txn = last.get("last_txn_date") or None
    return all_refs, last_txn


def _sanity_new_dates_after_previous(last_log_last_txn, df):
    """Every new payout date must be >= previous run's last transaction date."""
    if not last_log_last_txn or not last_log_last_txn.strip():
        return
    prev_ts = datetime.strptime(last_log_last_txn.strip(), DATE_TIME_FORMAT).timestamp()
    for _, row in df.iterrows():
        if row[TYPE] != TYPE_PAYOUT:
            continue
        dts = _parse_csv_date(row[DATE]).timestamp()
        if dts + 1e-6 < prev_ts:
            raise RuntimeError(
                f"Sanity check failed: payout on {row[DATE]} (ref {_safe_str(row[REFERENCE_CODE])!r}) is "
                f"before last logged transaction date {last_log_last_txn!r}. "
                "Investigate logs.csv or CSV order; new entries should not be older than the previous upload's last date."
            )


def _validate_split_totals(transactions):
    """Every payout must have splits and they must sum to Paid out (all-or-nothing)."""
    for item in transactions:
        if len(item[SPLITS]) < 1:
            raise RuntimeError(
                f"Payout {item[PAYOUT_REF]!r} (Quicken date {item[DATE]}) has no split rows — need at least one "
                "Reservation, Resolution Adjustment, or Misc Credit under this payout."
            )
        total_splits = round(sum(float(split[AMOUNT]) for split in item[SPLITS]), 2)
        payout_total = round(float(item[TOTAL]), 2)
        if total_splits != payout_total:
            raise RuntimeError(
                f"Payout {item[PAYOUT_REF]!r} (Quicken date {item[DATE]}): split amounts sum to {total_splits} "
                f"but Paid out is {payout_total}."
            )


def _build_qif_string(filtered_transactions, accounts):
    """Build full QIF text in memory (single write on success). Returns (text, count_by_account)."""
    count_by_account = dict.fromkeys(accounts, 0)
    parts = []
    for account in accounts:
        parts.append("!Account\n")
        parts.append(f"N{account}\n")
        parts.append("TBank\n")
        parts.append("^\n")
        parts.append("!Type:Bank\n")
        for entry in filtered_transactions:
            if entry[ACCOUNT] != account:
                continue
            count_by_account[account] += 1
            parts.append(f"D{entry[DATE]}\n")
            parts.append(f"U{entry[TOTAL]}\n")
            parts.append(f"T{entry[TOTAL]}\n")
            parts.append("C*\n")
            parts.append("NAirbnb\n")
            if entry.get(SINGLE_LINE_MISC_CREDIT):
                parts.append(f"P{entry[PAYEE]}\n")
                parts.append(f"M{entry[MEMO]}\n")
                parts.append(f"L{entry[CATEGORY]}\n")
            elif len(entry[SPLITS]) == 1:
                split = entry[SPLITS][0]
                parts.append(f"P{split[PAYEE]}\n")
                parts.append(f"M{split[MEMO]}\n")
                parts.append(f"L{split[CATEGORY]}\n")
            else:
                parts.append(f"P{entry[SPLITS][0][PAYEE]}\n")
                parts.append(f"M{entry[SPLITS][0][MEMO]}\n")
                parts.append("L--Split--\n")
                for split in entry[SPLITS]:
                    parts.append(f"S{split[CATEGORY]}\n")
                    parts.append(f"E{split[SHORTER_MEMO]}\n")
                    parts.append(f"${split[AMOUNT]}\n")
            parts.append("^\n")
        parts.append("\n")
    return "".join(parts), count_by_account


def run_airbnb_to_qif():
    main_folder = os.getcwd()
    if QIF_FOLDER not in os.listdir(main_folder):
        messagebox.showinfo("WARNING", "Cannot find " + QIF_FOLDER)
        quit()

    archive_folder = os.path.join(main_folder, AIRBNB_ARCHIVE_FOLDER)
    if not os.path.isdir(archive_folder):
        os.makedirs(archive_folder)

    quif_path = os.path.join(main_folder, QIF_FOLDER)
    logs_path = os.path.join(main_folder, LOGS_CSV)

    source_csv_path = _find_source_airbnb_csv(main_folder)

    full_airbnb_data = pd.read_csv(source_csv_path)
    if REFERENCE_CODE not in full_airbnb_data.columns:
        raise RuntimeError(f'CSV must have a "{REFERENCE_CODE}" column.')
    full_airbnb_data = full_airbnb_data[airbnb_keys]

    _assert_payout_rows_have_reference(full_airbnb_data)
    _assert_reference_codes_unique(full_airbnb_data)

    already_refs, last_log_last_txn = _load_logs_state(logs_path)

    airbnb_data = _filter_unprocessed_payout_rows(full_airbnb_data, already_refs)
    if len(airbnb_data) == 0:
        print("No new payouts to import (already logged). Nothing to do.")
        return

    _sanity_new_dates_after_previous(last_log_last_txn, airbnb_data)

    run_dt = datetime.now()
    run_mmdyyyy = run_dt.strftime("%m%d%Y")
    run_iso = run_dt.isoformat(timespec="seconds")

    payout_dates = []
    for _, row in airbnb_data.iterrows():
        if row[TYPE] == TYPE_PAYOUT:
            payout_dates.append(_parse_csv_date(row[DATE]))
    min_d = min(payout_dates)
    max_d = max(payout_dates)
    span_start = min_d.strftime("%m-%d-%Y").replace("/", "-")
    span_end = max_d.strftime("%m-%d-%Y").replace("/", "-")
    qif_basename = f"qifstar_{span_start}_{span_end}_run{run_mmdyyyy}.QIF"
    qif_file = os.path.join(quif_path, qif_basename.replace("/", "-"))

    date_range_display = f"{min_d.strftime(DATE_TIME_FORMAT)} – {max_d.strftime(DATE_TIME_FORMAT)}"

    transactions = []
    in_splits = False
    missing_listings = []

    for row in airbnb_data.iterrows():
        row = row[1]
        if row[TYPE] == TYPE_PAYOUT:
            if in_splits == True:
                transactions.append(transaction_dict.copy())
                in_splits = False
            transaction_dict = {}
            transaction_dict[PAYOUT_DATE_RAW] = str(row[DATE]).strip()
            transaction_dict[DATE] = quicken_date(row[DATE])
            transaction_dict[DATE_FILTER] = _parse_csv_date(row[DATE]).timestamp()
            transaction_dict[TOTAL] = row[PAYOUT]
            for account in all_acounts:
                if account_numbers[account] in _safe_str(row[DETAILS]):
                    transaction_dict[ACCOUNT] = account
                    break
            if ACCOUNT not in transaction_dict:
                raise RuntimeError(
                    f"Payout on {row[DATE]} (amount {row[PAYOUT]}) could not be assigned to an account. "
                    f'Details from CSV: "{_safe_str(row[DETAILS])}". '
                    f"Expected one of: {list(account_numbers.values())}. Add or fix account match and re-run."
                )
            transaction_dict[PAYOUT_REF] = _safe_str(row[REFERENCE_CODE])
            transaction_dict[SPLITS] = []
        else:
            if row[TYPE] not in TYPES_AS_SPLITS:
                continue
            in_splits = True
            split_dict = {}
            split_dict[AMOUNT] = row[AMOUNT]
            if row[TYPE] == TYPE_MISC_CREDIT:
                split_dict[SPLIT_TYPE] = "misc_credit"
                split_dict[PAYEE] = MISC_CREDIT_PAYEE
                split_dict[MEMO] = MISC_CREDIT_MEMO
                split_dict[SHORTER_MEMO] = MISC_CREDIT_MEMO
                split_dict[CATEGORY] = MISC_CREDIT_CATEGORY
            else:
                split_dict[SPLIT_TYPE] = "reservation"
                split_dict[PAYEE] = _safe_str(row[GUEST])
                split_dict[MEMO] = create_memo(row)
                split_dict[SHORTER_MEMO] = create_short_memo(row)
                if row[LISTING] in airbnb_to_quicken_properties:
                    split_dict[CATEGORY] = airbnb_to_quicken_properties[row[LISTING]]
                else:
                    listing_name = _safe_str(row[LISTING]) or "(blank)"
                    if transaction_dict[ACCOUNT] in accounts:
                        missing_listings.append((listing_name, row[DATE], _safe_str(row[GUEST])))
                    split_dict[CATEGORY] = "[Unknown listing - set in Quicken]"
            transaction_dict[SPLITS].append(split_dict.copy())
    if in_splits == True:
        transactions.append(transaction_dict.copy())
        in_splits = False

    if missing_listings:
        unique_listings = sorted(set(m[0] for m in missing_listings))
        lines = [f"  Listing: {m[0]!r}  |  Date: {m[1]}  |  Guest: {m[2]}" for m in missing_listings]
        raise RuntimeError(
            "FAIL: One or more listings are not in airbnb_to_quicken_properties.\n\n"
            "What was expected: Every Reservation/Resolution Adjustment row must have a Listing that appears "
            "as a key in the airbnb_to_quicken_properties dict in airbnb_to_qif.py.\n\n"
            "What didn't happen: No Quicken category could be assigned for the row(s) below; script stops so you can add them.\n\n"
            f"Missing listing(s) to add (unique, {len(unique_listings)}): {unique_listings}\n\n"
            "Occurrences (listing | date | guest):\n" + "\n".join(lines)
        )

    for item in transactions:
        if len(item[SPLITS]) < 1:
            raise RuntimeError(
                f"Payout {item[PAYOUT_REF]!r} (Quicken date {item[DATE]}) has no split rows under it."
            )
        types_in_payout = {s[SPLIT_TYPE] for s in item[SPLITS]}
        if "misc_credit" in types_in_payout and "reservation" in types_in_payout:
            date_str = item[DATE]
            raise RuntimeError(
                f"Payout on {date_str} has mixed split types (Misc Credit and Reservation/Resolution). "
                "Not supported. Please address this case."
            )
        if types_in_payout == {"misc_credit"}:
            item[SINGLE_LINE_MISC_CREDIT] = True
            item[PAYEE] = item[SPLITS][0][PAYEE]
            item[MEMO] = item[SPLITS][0][MEMO]
            item[CATEGORY] = item[SPLITS][0][CATEGORY]

    _validate_split_totals(transactions)

    filtered_transactions = transactions
    qif_text, count_by_account = _build_qif_string(filtered_transactions, accounts)

    with open(qif_file, "w", encoding="utf-8") as f:
        f.write(qif_text)

    written = [e for e in filtered_transactions if e[ACCOUNT] in accounts]
    count_1687 = sum(1 for e in written if e[ACCOUNT] == CH_CHK_1687)
    count_0149 = sum(1 for e in written if e[ACCOUNT] == BOFA_CHK_0149)
    payout_refs_sorted = sorted({e[PAYOUT_REF] for e in written})
    payout_refs_field = ",".join(payout_refs_sorted)

    if written:
        parsed = sorted(
            (datetime.strptime(str(e[PAYOUT_DATE_RAW]).strip(), DATE_TIME_FORMAT), e[PAYOUT_REF]) for e in written
        )
        first_txn_date = parsed[0][0].strftime(DATE_TIME_FORMAT)
        last_txn_date = parsed[-1][0].strftime(DATE_TIME_FORMAT)
        first_ref_code = parsed[0][1]
        last_ref_code = parsed[-1][1]
    else:
        first_txn_date = last_txn_date = first_ref_code = last_ref_code = ""

    log_fields = [
        "run_date_mmdyyyy",
        "script_run_iso",
        "source_csv",
        "qif_filename",
        "first_txn_date",
        "last_txn_date",
        "first_ref_code",
        "last_ref_code",
        "count_1687",
        "count_0149",
        "payout_refs",
        "prior_last_txn_date",
        "sanity_note",
    ]
    log_row = {
        "run_date_mmdyyyy": run_mmdyyyy,
        "script_run_iso": run_iso,
        "source_csv": os.path.basename(source_csv_path),
        "qif_filename": os.path.basename(qif_file),
        "first_txn_date": first_txn_date,
        "last_txn_date": last_txn_date,
        "first_ref_code": first_ref_code,
        "last_ref_code": last_ref_code,
        "count_1687": str(count_1687),
        "count_0149": str(count_0149),
        "payout_refs": payout_refs_field,
        "prior_last_txn_date": last_log_last_txn or "",
        "sanity_note": "ok" if (last_log_last_txn or "").strip() else "first_run_no_prior_log",
    }
    write_header = (not os.path.isfile(logs_path)) or os.path.getsize(logs_path) == 0
    with open(logs_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.DictWriter(lf, fieldnames=log_fields)
        if write_header:
            w.writeheader()
        w.writerow(log_row)

    base_name = os.path.basename(source_csv_path)
    stem, ext = os.path.splitext(base_name)
    archive_dest = os.path.join(archive_folder, f"{stem}_PROCESSED_{run_mmdyyyy}{ext}")
    try:
        shutil.move(source_csv_path, archive_dest)
    except OSError:
        shutil.copy2(source_csv_path, archive_dest)
        try:
            os.remove(source_csv_path)
        except OSError as ex:
            print(
                f"WARNING: Copied source to {archive_dest} but could not remove {source_csv_path}: {ex}\n"
                "Delete the original file manually when nothing has it open (e.g. OneDrive/Excel)."
            )
        else:
            print(f"Archived source CSV to {archive_dest} (removed original)")
    else:
        print(f"Archived source CSV to {archive_dest}")

    print(f"Date range: {date_range_display}")
    for account in accounts:
        print(f"  {account}: {count_by_account[account]} transactions")
    print(f"SUCCESS: QIF written to {qif_file}")
    print(f"Log updated: {logs_path}")


if __name__ == "__main__":
    try:
        run_airbnb_to_qif()
    except RuntimeError as e:
        print(f"\nFAILED\n\n{e}\n\nNo QIF was written. logs.csv and the source CSV were not changed.")
        sys.exit(1)







# DATE D
# Total AMOUNT UT
# DEP N fixed
# Transactions


# D12/27'18
# U1,164.00
# T1,164.00
# NDEP
# PAirbnb
# MJulie Dunbar, 12/26-1/1/19
# LRents Received:CH:1




# tmp_year = []
# tmp_month = []
# tmp_day = []
# for row in mint_data.iterrows(): 
#     tmp_date = row[1]['Date'].split('/')
#     tmp_year.append(tmp_date[2])
#     tmp_month.append(tmp_date[0])
#     tmp_day.append(tmp_date[1])
# mint_data['year'] = pd.Series(tmp_year)
# mint_data['month'] = pd.Series(tmp_month)
# mint_data['day'] = pd.Series(tmp_day)

# mint_data = mint_data[(mint_data['year']==str(year)) & (mint_data['month']==str(month))]
# print("Found {} transaction in {}, {}\n".format(len(mint_data),months[str(month)],year))

# qif_editor = open(qif_file,'w')

# for row in mint_data.iterrows(): 
#     tmp_date = row[1]['Date'][:-5] + '\'' + row[1]['Date'][-4:]
#     tmp_amount = row[1]['Amount']
#     tmp_memo = row[1]['Notes']
#     tmp_category = row[1]['Category']
#     tmp_payee = row[1]['Description']
#     tmp_check = 'DEP' #TODO
#     add_transaction(tmp_date, tmp_amount, tmp_check, tmp_payee, tmp_memo, tmp_category)

