###########################################
# MINT TO QUICKEN FILE CONVERTER
###########################################
# Date: 1/10/2019
# Python 3.0
# Version 1.0
###########################################

# Inputs
year = 2018
month = 12

# Imported Libraries
import csv
import os
import time
import pandas as pd
from tkinter import messagebox

# Dictionaries
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
def add_transaction(date, amount, check, payee, memo, category):
    #TODO: Write transaction function
    pass

# Setup
print("\nFinding Mint files\n")

main_folder = os.getcwd()
mint_folder = "mint_files"
qif_folder = "qif_files"
mint_path = main_folder +"\\"+ mint_folder
quif_path = main_folder +"\\"+ qif_folder
records_file = main_folder + "\\records.txt"
qif_file = main_folder + "\\" + qif_folder + "\\qif_"+str(month)+"_"+str(year)+".QIF"

if mint_folder not in os.listdir(main_folder):
    messagebox.showinfo("WARNING","Cannot find Mint folder")
    quit()
if qif_folder not in os.listdir(main_folder):
    messagebox.showinfo("WARNING","Cannot find Quicken folder")
    quit()

records_editor = open(records_file,'r')
#TODO: check if month is done

mint_data = pd.read_csv(mint_path+"\\"+os.listdir(mint_folder)[0])
tmp_year = []
tmp_month = []
tmp_day = []
for row in mint_data.iterrows(): 
    tmp_date = row[1]['Date'].split('/')
    tmp_year.append(tmp_date[2])
    tmp_month.append(tmp_date[0])
    tmp_day.append(tmp_date[1])
mint_data['year'] = pd.Series(tmp_year)
mint_data['month'] = pd.Series(tmp_month)
mint_data['day'] = pd.Series(tmp_day)

mint_data = mint_data[(mint_data['year']==str(year)) & (mint_data['month']==str(month))]
print("Found {} transaction in {}, {}\n".format(len(mint_data),months[str(month)],year))

qif_editor = open(qif_file,'w')

for row in mint_data.iterrows(): 
    tmp_date = row[1]['Date'][:-5] + '\'' + row[1]['Date'][-4:]
    tmp_amount = row[1]['Amount']
    tmp_memo = row[1]['Notes']
    tmp_category = row[1]['Category']
    tmp_payee = row[1]['Description']
    tmp_check = 'DEP' #TODO
    add_transaction(tmp_date, tmp_amount, tmp_check, tmp_payee, tmp_memo, tmp_category)

records_editor = open(records_file,'a')
#TODO: Enter month into editor



