import pandas as pd
import requests
from io import BytesIO
import logging
import os
from app import config 

logger = logging.getLogger(__name__)

def fetch_smard_data(start_timestamp_ms, end_timestamp_ms, module_ids, region, data_type, language):
   
    payload = {
        "request_form": [{
            "format": "CSV",
            "moduleIds": module_ids,
            "region": region,
            "timestamp_from": start_timestamp_ms,
            "timestamp_to": end_timestamp_ms,
            "type": data_type,
            "language": language
        }]
    }
    try:
        response = requests.post(config.SMARD_BASE_URL, json=payload)
        response.raise_for_status()  
        df = pd.read_csv(BytesIO(response.content), sep=';')
        logger.info(f"Successfully fetched data for module IDs: {module_ids}")
        return df
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data from SMARD API for module IDs {module_ids}: {e}")
        raise
    except pd.errors.EmptyDataError:
        logger.warning(f"No data returned from SMARD API for module IDs {module_ids} in the specified range.")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing SMARD data for module IDs {module_ids}: {e}")
        raise

def preprocess_smard_df(df, column_names, float_cols):
    
    if df.empty:
        return df

    df.columns = column_names
    
    for col in float_cols:
        if col in df.columns:
            # Handle German number format 
            df[col] = df[col].astype(str).str.replace('.', '', regex=False) 
            df[col] = df[col].str.replace(',', '.', regex=False) 
            df[col] = df[col].str.replace('-', '0', regex=False) 
            df[col] = pd.to_numeric(df[col], errors='coerce') 
        else:
            logger.warning(f"Column '{col}' not found in DataFrame for float conversion. Skipping.")
    return df

def get_smard_data(start_time, end_time, output_filepath=config.SMARD_DATA_PATH):

    start_timestamp_ms = int(start_time.timestamp()) * 1000
    end_timestamp_ms = int(end_time.timestamp()) * 1000

    # Fetch energy data
    df_energy = fetch_smard_data(
        start_timestamp_ms, end_timestamp_ms,
        config.SMARD_MODULE_IDS_ENERGY, config.SMARD_REGION, config.SMARD_TYPE, config.SMARD_LANGUAGE
    )
    df_energy = preprocess_smard_df(df_energy, ['Time_from', 'Time_to', 'Windoffshore', 'Windonshore', 'Solar'],
                                     ['Windoffshore', 'Windonshore', 'Solar'])

    # Fetch price data
    df_price = fetch_smard_data(
        start_timestamp_ms, end_timestamp_ms,
        config.SMARD_MODULE_IDS_PRICE, config.SMARD_REGION, config.SMARD_TYPE, config.SMARD_LANGUAGE
    )
    df_price = preprocess_smard_df(df_price, ['Time_from', 'Time_to', 'Market_price'], ['Market_price'])

    # Fetch load data
    df_load = fetch_smard_data(
        start_timestamp_ms, end_timestamp_ms,
        config.SMARD_MODULE_IDS_LOAD, config.SMARD_REGION, config.SMARD_TYPE, config.SMARD_LANGUAGE
    )
    df_load = preprocess_smard_df(df_load, ['Time_from', 'Time_to', 'Load'], ['Load'])

    if df_energy.empty or df_price.empty or df_load.empty:
        logger.error("One or more essential SMARD dataframes are empty.")
        return pd.DataFrame()


    df_inter = pd.merge(df_energy, df_load, on=['Time_from', 'Time_to'])
    df_merged = pd.merge(df_inter, df_price, on=['Time_from'], how='outer')

    df_merged = df_merged.drop(columns=[col for col in ['Time_to_x', 'Time_to_y', 'Time_to'] if col in df_merged.columns], errors='ignore')

    df_merged['Wind'] = df_merged['Windoffshore'] + df_merged['Windonshore']
    df_merged = df_merged.drop(columns=['Windoffshore', 'Windonshore'])

    df_merged['Market_price'] = df_merged['Market_price'].ffill()

    df_merged['Time_from'] = pd.to_datetime(df_merged['Time_from'], dayfirst=True)
    df_reordered = df_merged.loc[:, ['Time_from', 'Market_price', 'Load', 'Wind', 'Solar']]
    
    required_numeric_cols = ['Market_price', 'Load', 'Wind', 'Solar']
    missing_data_found = False
    for col in required_numeric_cols:
        if col not in df_reordered.columns:
            logger.error(f"Required column '{col}' not found in the final SMARD DataFrame. Optimization will likely fail.")
            missing_data_found = True
        elif df_reordered[col].isnull().any():
            # Check if any NaNs exist in the column
            logger.error(f"Column '{col}' in the final SMARD DataFrame contains NaN values after preprocessing. This indicates missing or unconvertible data.")
            missing_data_found = True
        elif not pd.api.types.is_numeric_dtype(df_reordered[col]):
            # Double check if the column is actually numeric
            logger.error(f"Column '{col}' in the final SMARD DataFrame is not entirely numeric. This indicates a preprocessing issue.")
            missing_data_found = True

    if missing_data_found:
        logger.error("SMARD data validation failed: Essential data is missing or invalid. Returning empty DataFrame.")
        return pd.DataFrame()

    output_dir = os.path.dirname(output_filepath)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    df_reordered.to_csv(output_filepath, sep='\t', index=False)
    logger.info(f"SMARD data successfully processed and saved to {output_filepath}")

    return df_reordered