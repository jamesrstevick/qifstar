# Walnut Apartment Processes

Source: Google Doc [Walnut Apartment Processes](https://docs.google.com/document/d/1ojXKhdyf38UGzvqIyHeuWxdb0w6A8ZmFvPT7NbtyzI8/edit) (read-only snapshot for qifstar / Quicken automation context).

This repo automates Quicken QIF imports. The sections below map **data sources → accounts**, reconciliation targets, categories, and manual processes that the scripts support or replace.

---

## Finances

### Quicken

#### Settings

Two settings to ensure are set (already set) in Edit > Preferences:

- Mobile & Web: Keep Quicken Mobile & Web Sync off
- Backup: Automatic saves after running Quicken 1 time

#### Sync Accounts

- Tools > One Step Update
- Select accounts (only select one for a faster sync)

#### Amazon

Allot 1 hour to power through all Amazon transactions of the month. May need to check both Amazon accounts.

- Pull up Quicken and download transactions from credit cards
- Pull up Amazon and go to Transactions
  - Account > Your Payments > Transactions
- Use Quicken transaction values to search through Amazon transactions and pull up the order to find information

**Rules**

- Clear subscriptions occasionally
- Use Amazon Prime Credit Card for Walnut Properties
- Use Capital One for personal
- JB and MC CCs for those properties

#### Accounting

- As a sole-proprietorship, we use cash-basis reporting (reporting when cash exchanges hands) which includes credit card transactions.
  - We previously thought credit card transactions needed to be reported when the credit card statement was paid off for cash basis reporting, so accounting through 2023 was done this way — transaction at the beginning and end of the year moved to match the year in which the credit card payment occurred. It turns out that credit card transactions count as cash exchanging hands, so 2024 and onward will be done this way.
- All transactions will be left at their transacted date. This means balances will not come to 0 since credit card payments are usually a month after the last transaction on their statement. And December transactions will still be written off even if not reconciled, to file taxes before statements come in, which could be as late as February 15th.
  - Through December 2024, credit card payments are dated at the end of the period of transactions and this will continue, so that the last 0 in the balance for credit cards is Nov 15 or Nov 31. After this, the balance may not match, but reconciliation will account for the running balance as credit card bills are paid usually one month after the last transaction on the statement.
  - Refunds on future statements associated with transactions from a previous statement are moved to the end of the period of transactions of the previous statement
  - E.g. Transactions between 8/15 and 9/15 result in a balance paid on 10/15 with a few refunds around 10/5. Quicken should have all of the transactions from 8/15 to 9/15, followed by the refunds, followed by the credit card payment so that the running balance is zero-summed

#### Cash

- Create a split on a Cash & ATM Quicken entry (ATM Withdrawal) in either Checking Main BofA or Checking Schwab account
- File receipt in ATM Cash folder with category and date of Quicken entry (ATM withdrawal)

#### Airbnb

- Find transaction paid out
  - Account - Menu - Earnings - View all paid
- Use python script to add Airbnb transactions
  - Run downloading transactions to avoid duplicates
  - Go to transactions and hit Get CSV report and download with all fields
  - Place in airbnb_files folder (only one file)
  - NOTE: Don’t *(incomplete note in source doc)*

#### VRBO

- Find transaction paid out
  - Reservation Manager - Financial Reporting
- Use python script to add Airbnb transactions before downloading transactions to avoid duplicates

#### Account to Reconcile

- Main BofA Checking 0149 - Cal Debit 8726 - Cash
- Main BofA Savings 6862
- Chase Prime 5144 (15th)
- Chase United 0291 (15th)
- JetBlue 7492
- CH BofA 4900 (15th)
- CH BofA Checking
- Capital One
- Schwab Savings 157
- Schwab Checking 045 - Schwab Debit 8566 - Cash
- Schwab Corporate 580 (HOA) - TODO
- Schwab One 9593
  - Cannot download
  - Enter Change in Market Value from Positions - Summary
  - Enter Dividends (not reinvested), Interest, Transfers
  - Do not enter purchase or sale of stocks
- CASH / ATM

#### Categories

- General
  - CC for Coral Cove now for most categories
    - Will be split between CC2, CC3, CC4, CC5, CC6, and CC7 pro rata
    - Association dues are split under a breakdown in bylaws
  - Income is categorized by unit for all properties
  - 1636 utilities are business expense as Walnut 1722: Utilities
- Categories
  - Transfers
    - Cleaning Fees - to be sent to cleaner, extra from deposit
  - Properties Schedule E
    - Advertising
    - \* Association Dues (Assessments)
    - Auto and travel
    - \* Bookkeeping
    - Cleaning and maintenance
      - Pest Control
    - \* Gardening
    - Insurance
    - Legal and other professional fees
      - \* Rent board fees
    - \* Licenses and permits
      - Business Licenses
    - Management fees
      - Food
    - Mortgage interest
    - \* Office space
    - \* Plumbing and Electrical
    - Repairs
      - Painting
    - Supplies
      - Furnishings
      - Appliances
      - Decorating
      - Postage
    - Taxes
      - Property Tax
      - Tourist Tax (pro-rata)
      - Sales Tax
    - Utilities
      - Water
      - Garbage
      - Electric
      - Cable
      - Wifi
      - Wifi and Cable
      - Gas and Electric
      - Sewer
  - Non Schedule E
    - Improvements - to be capitalized

#### Changes for 2025

- Removing Google Sheet tracking for rents
  - Quicken will track rents in subcategories
- New general categories like WP (Walnut Properties) for CC, VSV, and W even split and BP (Berkeley Properties) for VSV and W even split
- Wisteria and Guest Room will be placed under 1722 Walnut (Walnut)
- All Quicken transaction dated by their actual transaction date
- No category for the Den at all - Den is number 7
- Receipt uploading
  - Receipts will be written on and added to Google Drive in folders based on Credit Card (only Chase and JetBlue)
  - Must write category and description (especially if food)
  - Helpful information optional - date, card number, etc
- Personal accounting will not be tracked, Capital One and Schwab can be removed or at least not reconciled
- John’s apt category should have one payment and two deposits from JB and MC
- Amazon card separated, John can own and use one

#### Changes for 2026

- Reconcile 15th accounts between 15th and 22nd of each month
- Reconcile 1st accounts between 1st and 7th of each month
- Reimburse accounts immediately when transactions are paid from the wrong account
- Rules on food is changing, cannot write off food, so no more Management Fees: Food
- Pay HOA out of the HOA account only
- Categories have been reset

### Credit Cards

- **4900** - Carriage House
  - John
- **6938 (0291) (0182)** - United Chase - Business (VSV, W, CC, OB)
  - Liz (6938) and Glen (6938)
  - Paid for by BofA 0149
  - Use receipts for information
  - OB Quicken documented by room breakdown, or change breakdown?
  - Add all OB expenses
- **5144** - Chase Amazon Prime - Business (VSV, W, CC, OB)
  - Connected through John’s Chase
  - Mid month dates
  - Only for VSV, W, CC, OB
  - Use points on personal, so that transaction is a write off
- **7492 (2281)** - JetBlue Barclays (VSV, W, CC, OB)
  - Liz (7492) and John (2281)
  - Paid by BofA 0149
  - Billpay, subscriptions
  - Flights
  - John’s CC for Walnut Properties in FL
- **7763** - Capital One - Personal
  - Liz (1783 8262) Glen (3053) James (1296 6275)
  - Paid by BofA 0149
- **Cal Debit** - Business (VSV, W, CC, OB)
  - 8000 (8726)
  - Linked to BofA 0149
- **8566 Schwab Debit** - Business (VSV, W, CC, OB)
  - Linked to Schwab Checking 045
  - 3629 - Glen Schwab Debit
  - 8566 - Liz Schwab Debit
- **Health Savings Account (HSA)**
  - Mom - 0980 (2589)
  - Dad - 4188
- **Jungle Book**
  - 1657 - Capital One CC
  - 5110 - Debit
- **BEAR 2590**

### Accounts (utility / vendor account numbers)

#### PG&E ✓

- Account number not in BofA transactions, must use statements
- BofA Checking 0149 - Walnut 1722 - 2440413422-3
- BofA Checking 0149 - VSV - 5490567696-8
- BofA Checking 0149 - Walnut 1722 (Walnut 1636) - 4263729532-2
- BofA CH Checking 1687 - 1716 Rose St - 1981476497-3

#### Comcast

- Chase 0291 - $130 VSV
- Chase 0291 - $440 1722
- JetBlue 2281 - Coral Cove bill for each Condo August 2024 and earlier
- Comcast Business - CC0291 - 1722 WALNUT ST - 8155400502081209
- Comcast Business - CC0291 - 1446 ML KING JR - 8155400502081191
- Comcast Business - CC2281 - 88 S OCEAN BLVD - 8535114201249329 (started July)
- Comcast Business - CC4900 - 1716 Rose St - 8155400501575524
- Comcast Business - CC8341 - MC - 301 NE 6TH AVE - 8535114200889943
- (what is this) Comcast Business - CC8341 - 301 NE 6TH AVE - 8535114200889950

#### FPL ✓

- Can use BofA 0149 transactions to track account number
- BofA Checking 0149
- Pay with 7492?
- BofA Checking 0149 - CC2 - 3911563520
- BofA Checking 0149 - CC3 - 8888318253
- BofA Checking 0149 - CC4 - 9403890347
- BofA Checking 0149 - CC5 - 8699348499
- BofA Checking 0149 - CC6 - 8522998353
- BofA Checking 0149 - CC7 - 5264846444

#### EBMUD

- Billpay every 2 months
- John’s passwords
- BofA Checking 0149 - Walnut 1722 (Walnut 1636) - 17825200001
- BofA Checking 0149 - Walnut 1722 - 17848500001
- BofA Checking 0149 - VSV - 85040194784
- BofA Checking 0149 - VSV - 56639679882 (Sprinklers - CANCEL)
- Carriage House - 99540853108

#### Berkeley Recology

- Billpay every 3 months
- BofA Checking 0149 - Walnut 1722 - 25417-14108
- BofA Checking 0149 - Walnut 1722 (Walnut 1636) -
- BofA Checking 0149 - City of Berkeley - VSV - 5729
- BofA CH Checking 1687 - City of Berkeley - Carriage House - 6103

#### Tourist Tax

- Palm Beach County Tourist Development Tax (TDT) - 6% (6 months or less) - paid to Palm Beach County Tax Collector (Constitutional Tourist Tax)
- Paid once per month, split per apartment, plus processing fee
- Email family with breakdown upon payment
- This tax is in addition to state sales tax (7% in Palm Beach County)

#### Florida Public Utilities

- BofA Checking 0149 - CC6 - 200000361549
- BofA Checking 0149 - CC7 - 200000362026

#### Other vendors

- Ephta cleaning
- Business License
  - Once per year, arrive in November, due Jan 1, penalties start March 1
  - BofA Checking 0149 - Walnut 1722 - BL-012525 (due Jan 1)
  - BofA Checking 0149 - VSV - BL-002057 (due Jan 1)
  - BofA Checking 1687 - CH - BL-008600 (due Jan 1)
- Rent Stabilization Rent Board
  - John to pay all online - W, VSV using 0149, and CH using 1687
  - Bills arrive in April, due July 2
- Property Taxes Berkeley
- Property Taxes Coral Cove

### Subscriptions

- **7492 (2281)** - JetBlue Barclays
  - Sonic - Walnut 1722:Utilities:Wifi
  - Google One ($2) - Walnut 1722:Management Fees:Office Work
  - Water Coffee Delivery - Walnut 1722:Supplies
  - Comcast - CC:Utilities:Wifi And Cable
  - Google TV ($83) - CC:Utilities:Cable
  - Ring Annual - ?
  - Miss Mops ($130) - VSV:Cleaning & Maint
  - Spectrum - MH:Utilities:Wifi And Cable

### Processes

#### Capital Improvements

Not necessarily depreciating assets, but larger expenses in order to have records for when larger items were last replaced (e.g. refrigerator, couches, stove, etc.)

#### Soledad Salary

- Currently $3000 divided as $2250 for Berkeley Properties (BP) and $750 for Carriage House, two separate checks written
- Could consider work part time (1000 hours) which is 83.3 hrs/month, and $40/hour for $3300 pay

#### Uploading Receipts

When making a Walnut Property expense, write the category on the receipt and any other useful information and upload the receipt to the Google Drive.

- Receipts should be placed into the right folder depending on the card used:
  - United Chase [0291]
  - JetBlue [7492] [2281]
- Must write category and description (especially if it is a meal)
- Add any helpful information - date, card number, etc

#### Johns Apt

- Apartment payment from 0149
- $1000 from Jungle Book and $1000 from Mango Cove
  - $12000 / year from both properties to cover rent, untaxed assuming it is a write off
  - Considered management benefit for John

#### Coral Cove HOA

Schwab 580 Corporate Brokerage

**Types of payments**

- Checks to pay for expenses
- FPL Direct Debit
- CODB Funding UT (water?)
- Assessments
- SNA/OXX dividends

**HOA assessments**

- Made quarterly
- Written off from personal accounts in Schedule E category Other:Assessments / Category CCX:Assessments
- Percentage breakdown:

| Condo   | Share   | Normalized |
|---------|---------|------------|
| Condo #2 | 10.90% | 12.25%    |
| Condo #3 | 11.40% | 12.81%    |
| Condo #4 | 11.40% | 12.81%    |
| Condo #5 | 14.50% | 16.29%    |
| Condo #6 | 17.60% | 19.78%    |
| Condo #7 | 23.20% | 26.07%    |

**Personal expenses**

- Ideally we don’t have any, but the only method to pay expenses from 580 is checkbook which isn’t always convenient
- We can make personal expenses, at which point we have a few options
  - Categorize them as CC:HOA:Assessments and sum them up, then…
    - Take full write off without involving Matt
    - Sum them up and ask Matt for direct payment (assuming he will ask us to use HOA account)
  - Categorize them as HOA expenses, sum them up and reimburse ourselves from 580 — each reimbursement creating 3 transactions in Quicken
    - The two occurring from the reimbursement will be categorized as CC:HOA:Reimbursements and cancel to 0
    - The one paying the expense will be categorized appropriately and used when filing 580 account

**Questions**

- How to file taxes on 580 HOA account?
- What records are needed, memos sufficient?

### Transfers

#### Venmo

Transfer cash to BofA Checking in amounts according to payments from tenants

#### Paypal

- Need account info from John

---

## Management

### Payment Methods

#### Venmo

- `[Rental Period] [CC/VSV/W] [Unit]`

### Vine Street Villas

#### Utilities

- Wifi - Comcast Business

#### Management

- Cleaning (once per week?)
- Ordering supplies to house
  - TP and PT
  - Trashbags
  - Cleaning supplies (handled by cleaners?)
- Check out list
  - Check cleaning
  - Check damage
  - Purchase needed items
  - Clean fridge
- Trash
- Hire someone to manage with discount
- Offer discount finders fee

#### Questions

- How do tenants pay?
- What responsibilities do Tenants have?
- Who takes out trash and when?
- When do cleaners come?
- How is it currently advertised?
- Leases?

### Coral Cove

#### Utilities

- Florida Public Utilities (FPU) - Gas for CC6 and CC7 only
- Wifi - Comcast Business (split)
- Cable - YouTube TV (split)
- Electricity - FPL (bill for each unit)

---

## Advertising

Talk to John about *(incomplete note in source doc)*

---

## Quicken Quarterly reports

- HOA reimbursement
- CH reimbursement
- Income and expense report

---

## Questions

- Assessments for CC HOA
  - In 2024, 3 assessments paid to HOA, only 1 in taxes filed
    - Throw in 2 assessments into next year (off Quicken)
  - 2025 Categorize by condo by percentage based on size, written in the bylaws
- Match Taxes to condo for CC
  - Property tax -> directly to condo
  - Tourist taxes -> pro rata by rental income
- Cancel Nauticed (Glen)
- 1K from JB and MC stopped early this year on 1K
  - Accounts merged and payments stopped
  - Going forward, $1K total (starting now)
- Corporate 580 account, new management with cards?
- Reimburse some CC payments
- Schwab HOA, can it have a debit card?
- Category adjustments gardening
- 2 ceiling fans to CC7, where did they go?
- Water delivery VSV doubled, toilet paper, paper towels
- Is YouTube TV CC for all apartments
- How many doors
- Appfolio used or needed?
- Which category for Johns apt, CC?
- OB expenses Amazon, sent to CC7?
  - $40 handles
  - $100 mirror
- Shoelaces Amazon $5.34 7/8/24 0182
- Amazon laundry detergent 2x to CC
- Amazon subscriptions?
- How is tourist tax paid? Online payments

Misc notes from source:

- HOA
- Mom - Small Amazon things
- Mom - Dryer and lift for CC
- Washer Dryer from John personal - $1501.57
- Amazon account: `john@thestarboardgroup.com` *(password omitted from this repo copy)*

---

## Filing Taxes 2025 (Meeting with Woodul)

- Missed 2 out of 3 CC HOA assessments in filing taxes in 2024, adding them to 2025:
  - 2× $16,617.80 from 1/10/2024 and 5/10/2024 totaling:
    - 4070.40 (CC2)
    - 4257.16 (CC3)
    - 4257.16 (CC4)
    - 5414.80 (CC5)
    - 6572.42 (CC6)
    - 8663.66 (CC7)

### Notes 2/4

- Market base sourcing - self employed
- W2 - record and withhold
- State sourced income

### Categories

- Keep categories as they were in the past, let PEK create Schedule E
- Lower amounts in each category as much as possible
- Mortgage Interest
- Business License -> Licenses and permits
- Garbage in utilities
- Assessments -> Association dues
- John Salary -> Management Fees:
- James Bookkeeping -> Correct location
- John’s office space -> Pull out to Office Space
- Bitsy Books - itemize
- Peckler Fee -> Bookkeeping

### Amendments

- If large, file amendment (90K)
- Add last assessments to this year?

### Ocean Breeze

- Capital loss (doesn’t go away, can keep using them against gains)
- If we sell a new property, could write against it

### Accountant needs

- Purchase Statement of Ocean Breeze
- 1095B from BEAR medical coverage
- New breakdown of categories
- Glen’s IRA, shouldn’t have withheld money, call ZION, could be wrong ID, mixed up data
- 1098 form from Rocket Mortgage for interest in Feb? If not, use year to date
- Go through depreciating items and remove ones at zero

QCB - gross distribution of IRA with Schwab, can donate and get rid of taxes

### Todo 2026

- Business License for 1722 reported as CH in 2025 Taxes
