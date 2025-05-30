import datetime
import os

# Data Paths 
SMARD_DATA_PATH = "data/SMARD_data.csv"
BESS_EXCEL_PATH = "data/BESS_Data.xlsx"

OUTPUT_FOLDER = "output"
OPTIMIZATION_RESULT_FILE = f"{OUTPUT_FOLDER}/Result.xlsx"
PLOT_RESULT_FILE = f"{OUTPUT_FOLDER}/SOC_MarketPrice_Plot.png" # 

# SMARD API Settings 
SMARD_BASE_URL = 'https://www.smard.de/nip-download-manager/nip/download/market-data'
# Module IDs for SMARD API:
# 1004067: Wind offshore
# 1004068: Wind onshore
# 1001225: Solar
# 8004169: Market Price (Day-ahead)
# 5000410: Load
SMARD_BASE_URL = 'https://www.smard.de/nip-download-manager/nip/download/market-data'
SMARD_MODULE_IDS_ENERGY = [1004067, 1004068, 1001225]
SMARD_MODULE_IDS_PRICE = [8004169]
SMARD_MODULE_IDS_LOAD = [5000410]
SMARD_REGION = "DE"
SMARD_TYPE = "discrete"
SMARD_LANGUAGE = "de"

# Set DEFAULT END DATE to the beginning of the current day & START DATE to the beginning of the day before
now = datetime.datetime.now()
DEFAULT_SMARD_END_DATE = now.replace(hour=0, minute=0, second=0, microsecond=0)
DEFAULT_SMARD_START_DATE = DEFAULT_SMARD_END_DATE - datetime.timedelta(days=1)

try:
    SMARD_START_DATE = datetime.datetime.strptime(os.environ.get('SMARD_START_DATE', DEFAULT_SMARD_START_DATE.strftime('%Y-%m-%d %H:%M:%S')),'%Y-%m-%d %H:%M:%S')
except ValueError:
    print(f"Warning: Invalid SMARD_START_DATE environment variable. Using default: {DEFAULT_SMARD_START_DATE}")
    SMARD_START_DATE = DEFAULT_SMARD_START_DATE

try:
    SMARD_END_DATE = datetime.datetime.strptime(os.environ.get('SMARD_END_DATE', DEFAULT_SMARD_END_DATE.strftime('%Y-%m-%d %H:%M:%S')),'%Y-%m-%d %H:%M:%S')
except ValueError:
    print(f"Warning: Invalid SMARD_END_DATE environment variable. Using default: {DEFAULT_SMARD_END_DATE}")
    SMARD_END_DATE = DEFAULT_SMARD_END_DATE