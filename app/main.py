# app/main.py
import os
import sys
from app import config
from app.smard_client import get_smard_data
from app.bess_optimiser import run_bess_optimization

def main():

    print("Starting the BESS Optimization Pipeline.")

    if not os.path.exists(config.OUTPUT_FOLDER):
        os.makedirs(config.OUTPUT_FOLDER)
        print(f"Created output directory: {config.OUTPUT_FOLDER}")

    data_dir = os.path.dirname(config.SMARD_DATA_PATH)

    print("Step 1: Fetching and preprocessing SMARD data...")
    try:
        smard_df = get_smard_data(
            start_time=config.SMARD_START_DATE,
            end_time=config.SMARD_END_DATE,
            output_filepath=config.SMARD_DATA_PATH
        )
        if smard_df.empty:
            print("ERROR: SMARD data could not be fetched. Exiting.")
            sys.exit(1)
        print("Step 1 Complete: SMARD data ready.")
    except Exception as e:
        print(f"ERROR: Failed to fetch or preprocess SMARD data: {e}. Exiting.")
        sys.exit(1)

    # Step 2: Run BESS Optimization
    print("Step 2: Running BESS optimization...")
    try:
        run_bess_optimization(
            market_data_path=config.SMARD_DATA_PATH,
            bess_excel_path=config.BESS_EXCEL_PATH,
            output_excel_path=config.OPTIMIZATION_RESULT_FILE,
            plot_output_path=config.PLOT_RESULT_FILE
        )
        print("Step 2 Complete: BESS optimization attempted.")
    except Exception as e:
        print(f"ERROR: An error occurred during BESS optimization: {e}. Exiting.")
        sys.exit(1)

    print("BESS Optimization Pipeline Finished.")

if __name__ == "__main__":
    main()