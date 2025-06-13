###########################################
# AIRBNB TO QIF FILE CONVERTER
###########################################
# Date: 6/11/2025
# Python 3.0
# Version 1.0
###########################################


# Imported Libraries
import csv
import os
import time
import sys
from datetime import datetime
import pandas as pd
from tkinter import messagebox
from header import *


###########################################
# INPUTS
###########################################
# Accounts
accounts = [CH_CHK_1687, BOFA_CHK_0149]  # CH_CHK_1687, BOFA_CHK_0149
# Date filter in format "MM/DD/YYYY", filter will include the following dates
start_date = "05/01/2025"
end_date = "05/31/2025"
###########################################




all_acounts = [CH_CHK_1687, BOFA_CHK_0149]
airbnb_keys = [DATE, TYPE, ARRIVE, DEPART, CONF_CODE, NIGHTS, GUEST, LISTING, DETAILS, PAYOUT, AMOUNT]
quicken_keys = [DATE, ARRIVE, DEPART, CONF_CODE, NIGHTS, GUEST, LISTING, DETAILS, PAYOUT, AMOUNT]
transactions = []


# Dictionaries
account_numbers = {CH_CHK_1687:'1687',
                   BOFA_CHK_0149:'0149'}

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

def create_memo(row_dict):
    memo = row_dict[GUEST] + ", " +\
    shorter_date(row_dict[ARRIVE]) +\
    "-" + shorter_date(row_dict[DEPART]) +\
    " ({} Nights) [{}]".format(int(row_dict[NIGHTS]),row_dict[CONF_CODE])
    return memo






# Setup
print(f"\nLoading Airbnb transactions...")

main_folder = os.getcwd()
if AIRBNB_FOLDER not in os.listdir(main_folder):
    messagebox.showinfo("WARNING","Cannot find " + AIRBNB_FOLDER)
    quit()
if QIF_FOLDER not in os.listdir(main_folder):
    messagebox.showinfo("WARNING","Cannot find " + QIF_FOLDER)
    quit()

airbnb_path = main_folder +"\\"+ AIRBNB_FOLDER
quif_path = main_folder +"\\"+ QIF_FOLDER

records_file = main_folder + "\\records.txt"

qif_file = quif_path + "\\qifstar_"+start_date+"_"+end_date+".QIF"
qif_file = qif_file.replace("/","-")
# qif_file = quif_path + "\\qifstar.QIF"




records_editor = open(records_file,'r')
#TODO: check if month is done

airbnb_data = pd.read_csv(airbnb_path+"\\"+os.listdir(airbnb_path)[0])
airbnb_data = airbnb_data[airbnb_keys]

in_splits = False

# Create data packets for transactions

num_payments = 0
for row in airbnb_data.iterrows(): 
    row = row[1]
    if row[TYPE] == TYPE_PAYOUT:
        if in_splits == True:
            transactions.append(transaction_dict.copy())
            in_splits = False
        transaction_dict = {}
        transaction_dict[DATE] = quicken_date(row[DATE])
        transaction_dict[DATE_FILTER] = datetime.strptime(row[DATE], DATE_TIME_FORMAT).timestamp()
        transaction_dict[TOTAL] = row[PAYOUT]
        for account in all_acounts:
            if account_numbers[account] in row[DETAILS]:
                transaction_dict[ACCOUNT] = account
        transaction_dict[SPLITS] = []
    else:
        in_splits = True
        num_payments += 1
        split_dict = {}
        split_dict[PAYEE] = row[GUEST]
        split_dict[MEMO] = create_memo(row)
        if row[LISTING] in airbnb_to_quicken_properties:
            split_dict[CATEGORY] = airbnb_to_quicken_properties[row[LISTING]]
        else:
            print('ISSUE')
        split_dict[AMOUNT] = row[AMOUNT]
        transaction_dict[SPLITS].append(split_dict.copy())
if in_splits == True:
    transactions.append(transaction_dict.copy())
    in_splits = False


num_lines = len(airbnb_data)
num_transactions = len(transactions)

print(f"Rows of data: {num_lines}")
print(f"Number of payments: {num_payments}")
print(f"Number of transactions: {num_transactions}")

# Verify each transactions
valid_transactions = []
for item in transactions:
    if len(item[SPLITS]) < 1:
        continue 
    sum_of_splits = 0
    for split in item[SPLITS]:
        sum_of_splits += split[AMOUNT]
    if round(sum_of_splits,2) != item[TOTAL]:
        continue 
    valid_transactions.append(item)

num_transactions = len(valid_transactions)
print(f"Number of valid transactions: {num_transactions}")
    
# Filter by date
filtered_transactions = []
for item in valid_transactions:
    if item[DATE_FILTER] < datetime.strptime(start_date, DATE_TIME_FORMAT).timestamp():
        continue 
    if item[DATE_FILTER] > datetime.strptime(end_date, DATE_TIME_FORMAT).timestamp():
        continue 
    filtered_transactions.append(item)

num_transactions = len(filtered_transactions)
print(f"Number of transactions in date range: {num_transactions}")


# Write file
print(f"\nWriting QIF file for {len(accounts)} accounts...")
num_transactions = dict.fromkeys(accounts)
with open(qif_file, 'w+') as f:
    for account in accounts:
        num_transactions[account] = 0
        f.write("!Account\n")
        f.write(f"N{account}\n")
        f.write("TBank\n")
        f.write("^\n")
        f.write("!Type:Bank\n")
        for entry in filtered_transactions:
            if entry[ACCOUNT] == account:
                num_transactions[account] += 1
                f.write(f"D{entry[DATE]}\n")
                f.write(f"U{entry[TOTAL]}\n")
                f.write(f"T{entry[TOTAL]}\n")
                f.write("C*\n")
                f.write("NAirbnb\n")
                if len(entry[SPLITS]) == 1:
                    split = entry[SPLITS][0]
                    f.write(f"P{split[PAYEE]}\n")
                    f.write(f"M{split[MEMO]}\n")
                    f.write(f"L{split[CATEGORY]}\n")
                else:
                    f.write(f"P{entry[SPLITS][0][PAYEE]}\n")
                    f.write(f"M{entry[SPLITS][0][MEMO]}\n")
                    f.write("L--Split--\n")
                    for split in entry[SPLITS]:
                        f.write(f"S{split[CATEGORY]}\n")
                        f.write(f"E{split[MEMO]}\n")
                        f.write(f"${split[AMOUNT]}\n")
                f.write("^\n")
        f.write("\n")

for account in accounts:
    print(f"Wrote {num_transactions[account]} transactions into account {account}")









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

# records_editor = open(records_file,'a')
# #TODO: Enter month into editor



