###########################################
# MINT TO QUICKEN FILE CONVERTER
###########################################
# Date: 1/10/2019
# Python 3.0
# Version 1.0
###########################################

# Imported Libraries
import csv
import os
import time
import pandas as pd
from tkinter import messagebox

# Helper Functions
def convert_mint()

def add_transaction(date, amount, check, payee, memo, category):


# Setup
print("\nFinding Mint files")

main_folder = os.getcwd()
mint_folder = "mint_files"
qif_folder = "qif_files"
mint_path = main_folder +"\\"+ mint_folder
quif_path = main_folder +"\\"+ qif_folder
records_file = main_folder + "\\records.txt"

if mint_folder not in os.listdir(main_folder):
    messagebox.showinfo("WARNING","Cannot find Mint folder")
    quit()
if qif_folder not in os.listdir(main_folder):
    messagebox.showinfo("WARNING","Cannot find Quicken folder")
    quit()

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

text_file = open(records_file,'a+')
