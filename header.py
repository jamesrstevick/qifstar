

AIRBNB_FOLDER = "airbnb_files"
QIF_FOLDER = "qif_files"
AIRBNB_ARCHIVE_FOLDER = "airbnb_files_archive"
LOGS_CSV = "logs.csv"

CH_CHK_1687 = "Chking CH BofA - 1687"
BOFA_CHK_0149 = "Chkng Main BofA-0149"
JOHN_CHK_7949 = "Chkng John - 7949"

TYPE_BANK = "!Type:Bank"
DELIMITER = "^"

# Airbnb headers
DATE = "Date"
ARRIVE = "Start date"
DEPART = "End date"
CONF_CODE = "Confirmation code"
NIGHTS = "Nights"
GUEST = "Guest"
LISTING = "Listing"
DETAILS = "Details"
REFERENCE_CODE = "Reference code"
PAYOUT = "Paid out"
AMOUNT = "Amount"
TYPE = "Type"
TYPE_PAYOUT = "Payout"
TYPE_MISC_CREDIT = "Misc Credit"
TYPE_RESOLUTION_ADJ = "Resolution Adjustment"
TYPE_RESOLUTION_PAYOUT = "Resolution Payout"
TYPE_ADJUSTMENT = "Adjustment"
# Row types we add as splits (all count toward payout total)
TYPES_AS_SPLITS = (
    "Reservation",
    TYPE_RESOLUTION_ADJ,
    TYPE_RESOLUTION_PAYOUT,
    TYPE_ADJUSTMENT,
    TYPE_MISC_CREDIT,
)
# Misc Credit single-line transaction (no split)
MISC_CREDIT_PAYEE = "Airbnb Rewards"
MISC_CREDIT_MEMO = "Misc Credit"
MISC_CREDIT_CATEGORY = "Airbnb Rewards"

# Quicken headers
TOTAL = "total"
SPLITS = "splits"
PAYEE = "payee"
MEMO = "memo"
SHORTER_MEMO = "shorter_memo"
CATEGORY = "category"
DATE_FILTER = "date_filter"
ACCOUNT = "account"
SPLIT_TYPE = "split_type"
SINGLE_LINE_MISC_CREDIT = "single_line_misc_credit"
PAYOUT_REF = "payout_ref"  # internal key on transaction dict (Reference code or synthetic payout ID)
PAYOUT_DATE_RAW = "payout_date_raw"  # MM/DD/YYYY from CSV before quicken_date()

DATE_TIME_FORMAT = '%m/%d/%Y'

COUNT = "count"