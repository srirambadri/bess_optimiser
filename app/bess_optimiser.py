import pandas as pd
import datetime
import os
import timeit
from ortools.linear_solver import pywraplp
from app import config
import matplotlib.pyplot as plt 

def run_bess_optimization(market_data_path, bess_excel_path, output_excel_path, plot_output_path): 
    
    print("Starting BESS optimization...")
    try:
        # Read Excel file
        workbook = pd.ExcelFile(bess_excel_path)

        # Load market data (SMARD_data.csv)
        marketDF = pd.read_csv(market_data_path, sep='\t')
        marketDF.columns = ["time", "market_price_1", "load", "wind", "solar"]
        marketDF['time'] = pd.to_datetime(marketDF['time'])

        marketDF = marketDF.iloc[:,:5]
        marketDF = marketDF[~pd.isnull(marketDF["time"])].fillna(0)

        market1DF = marketDF.copy()
        market1DF.sort_values(by=["time"], inplace=True)

        marketDF_for_plot = marketDF.copy() 

        marketDF = marketDF.iloc[:,:5]
        marketDF.columns = ["time", "market_price_1", "load", "wind", "solar"]

        market1DF["time_string"] = market1DF.apply(lambda x:(x["time"]+ datetime.timedelta(seconds=0.002)).strftime("%d/%m/%Y %H:%M"), axis=1)
        market1DF.set_index("time_string", inplace=True)
        marketDF = market1DF

        # Load grid & battery data (BESS_data.csv)
        gridDF = workbook.parse("Grid")
        gridDF = gridDF.iloc[:,:4]
        gridDF.columns = ["max_buy_power", "max_sell_power", "max_import_power", "max_export_power"]
        battDF = workbook.parse("Battery")
        battDF = battDF.iloc[:,:8]
        battDF.columns = ["max_charge_rate", "max_discharge_rate", "capacity", "charge_eff", "discharge_eff", "min_soc", "max_soc", "initial_soc"]

        marketDict = marketDF.to_dict()
        gridDict = gridDF.to_dict()
        battDict = battDF.to_dict()

        if len(marketDF) < 2:
            print("ERROR: Not enough market data points to determine time interval. Optimization aborted.")
            return

        timeInterval = marketDF.iloc[1]["time"] - marketDF.iloc[0]["time"]

        input_data = type("input", (dict,), {})()
        input_data.update({
            "simData": {
                "startTime": datetime.datetime.strptime(marketDF.index[0], "%d/%m/%Y %H:%M"),
                "dt": int(round(timeInterval.total_seconds())) / (60 * 60), #in hour
                "tIndex": marketDF.shape[0]
                },
            "market": {
                key: {
                    sub_key: sub_item for sub_key, sub_item in marketDict[key].items()
                    } for key in marketDict.keys() if key != "time"
                },
            "grid": {
                key: item[0] for key, item in gridDict.items()
                },
            "batt": {
                key: item[0] for key, item in battDict.items()
                }
            })
        print("Data loaded and prepared for optimization.")

    except FileNotFoundError as e:
        print(f"Error: Required data file not found: {e}. Please ensure 'SMARD_data.csv' and 'BESS_Data.xlsx' are in the correct 'data/' directory.")
        return
    except Exception as e:
        print(f"An error occurred during data loading/preprocessing: {e}")
        return
    # Create the mip solver with the CBC backend.
    solver = pywraplp.Solver.CreateSolver("CBC")
    if not solver:
        print("ERROR: Failed to create OR-Tools solver. Ensure 'CBC' backend is available.")
        return

    inf = solver.infinity()
    print("OR-Tools solver initialized.")

    tIndex = input_data["simData"]["tIndex"] # number of timeslots
    dt = input_data["simData"]["dt"] # time interval in hour

    startTime = input_data["simData"]["startTime"].strftime("%d/%m/%Y %H:%M")
    timestamp = pd.date_range(startTime, periods=tIndex, freq=str(int(round(dt * 60))) + "min")
    time_index_list = [timestamp[i].strftime("%d/%m/%Y %H:%M") for i in range(len(timestamp))]

    # Define Optimization Variables
    time_s = timeit.default_timer()
    # Add timeseries variables
    vGrid = [solver.NumVar(lb=-inf, ub=inf, name="") for _ in range(tIndex)]
    vBattPower = [solver.NumVar(lb=-inf, ub=inf, name="") for _ in range(tIndex)]
    vCharge = [solver.NumVar(lb=-inf, ub=0, name="") for _ in range(tIndex)]
    vDischarge = [solver.NumVar(lb=0, ub=inf, name="") for _ in range(tIndex)]
    vChargeStatus = [solver.BoolVar(name="") for _ in range(tIndex)]
    vSOC = [solver.NumVar(lb=0, ub=1, name="") for _ in range(tIndex)]

    print(f"Defined {solver.NumVariables()} optimization variables.")

   # Add constraints
    for i in range(tIndex):
        t = time_index_list[i]

        solver.Add(vGrid[i] == input_data["market"]["load"][t] - input_data["market"]["solar"][t] - input_data["market"]["wind"][t] - vBattPower[i]) # Eqn. 1
        solver.Add(vGrid[i] <= input_data["grid"]["max_buy_power"]) # Eqn. 2
        solver.Add(vGrid[i] >= -input_data["grid"]["max_sell_power"]) # Eqn. 2
        
        total_plant_power = input_data["market"]["load"][t] - input_data["market"]["solar"][t] - input_data["market"]["wind"][t] + vDischarge[i] + vCharge[i]
        solver.Add(total_plant_power <= input_data["grid"]["max_import_power"]) # Eqn. 3
        solver.Add(total_plant_power >= -input_data["grid"]["max_export_power"]) # Eqn. 3
        
        solver.Add(vBattPower[i] == vCharge[i] + vDischarge[i]) # Eqn. 4
        solver.Add(vCharge[i] >= -input_data["batt"]["max_charge_rate"] * vChargeStatus[i]) # Eqn. 5(a)
        solver.Add(vDischarge[i] <= input_data["batt"]["max_discharge_rate"] * (1-vChargeStatus[i])) # Eqn. 5(b)
        
        if i == 0:
            solver.Add(vSOC[i] == input_data["batt"]["initial_soc"] - dt / input_data["batt"]["capacity"] * (vCharge[i] * (1-input_data["batt"]["charge_eff"]) + vDischarge[i] / (1-input_data["batt"]["discharge_eff"]))) # Eqn. 6
        else:
            solver.Add(vSOC[i] == vSOC[i-1] - dt / input_data["batt"]["capacity"] * (vCharge[i] * (1-input_data["batt"]["charge_eff"]) + vDischarge[i] / (1-input_data["batt"]["discharge_eff"]))) # Eqn. 6
            
        solver.Add(vSOC[i] >= input_data["batt"]["min_soc"]) # Eqn. 7
        solver.Add(vSOC[i] <= input_data["batt"]["max_soc"]) # Eqn. 7
    print(f"Defined {solver.NumConstraints()} optimization constraints.")

    # Add Objective Function 
    obj = 0
    obj += sum([vGrid[i] * input_data["market"]["market_price_1"][time_index_list[i]] * dt for i in range(tIndex)])
    solver.Minimize(obj)
    print("Objective function defined (Minimizing total cost/maximizing revenue).")

    # Solve the optimization model 
    status = solver.Solve()

    time_e = timeit.default_timer()
    runTime = round(time_e - time_s, 4)

    # Extract and Save Results 
    output_dir = os.path.dirname(output_excel_path)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    if status == solver.OPTIMAL or status == solver.FEASIBLE:
        print("Solution is found.")
        print("Number of variables =", solver.NumVariables())
        print("Number of constraints =", solver.NumConstraints())
        print("Computation time = ", runTime)
        
        excelWriter = pd.ExcelWriter(output_excel_path, engine='xlsxwriter')
        
        try:
            objValue = round(solver.Objective().Value() / 100, 2)
        except Exception as e:
            print(f"WARNING: Could not retrieve objective value: {e}. Setting to N/A.")
            objValue = "N/A"

        objValueDF = pd.DataFrame.from_dict({"obj_value": objValue}, orient="index", columns=["Total Cost of Importing Power ($)"])
        
        result_data = []
        for i in range(tIndex):
            try:
                result_data.append((
                    round(vGrid[i].solution_value(), 4),
                    round(vBattPower[i].solution_value(), 4),
                    round(vCharge[i].solution_value(), 4),
                    round(vDischarge[i].solution_value(), 4),
                    round(vSOC[i].solution_value(), 4),
                    int(vChargeStatus[i].solution_value())
                ))
            except Exception as e:
                print(f"WARNING: Could not extract solution for time step {time_index_list[i]}: {e}. Filling with NaN.")
                result_data.append((float('nan'), float('nan'), float('nan'), float('nan'), float('nan'), float('nan')))

        resultDF = pd.DataFrame(result_data, index=time_index_list,
                                columns=["Grid Power Flow (kW)", "Battery Output (kW)",
                                         "Charging Power (kW)", "Discharging Power (kW)",
                                         "State-of-charge (SOC)", "Charge Status"])
        
        objValueDF.to_excel(excelWriter, sheet_name='Cost')
        resultDF.to_excel(excelWriter, sheet_name='Operation')
        
        try:
            excelWriter.close()
            print(f"Optimization results saved to {output_excel_path}")
        except Exception as e:
            print(f"ERROR: Error saving Excel file: {e}")

        print("Generating plot...")
        try:
            resultDF['Time'] = pd.to_datetime(resultDF.index, format='%d/%m/%Y %H:%M').strftime('%H:%M')

            marketDF_for_plot['time'] = pd.to_datetime(marketDF_for_plot['time'])
            marketDF_for_plot['Time'] = marketDF_for_plot['time'].dt.strftime('%H:%M')

            fig, ax1 = plt.subplots(figsize=(15, 7))

            plt.grid(True, linestyle='--', alpha=0.7)
            plt.xticks(rotation=45, ha='right', fontsize=10) 

            ax2 = ax1.twinx()
            
            ax1.plot(resultDF["Time"], resultDF["State-of-charge (SOC)"], marker='o', linestyle='-', color='g', markersize=3, linewidth=1)
            ax2.plot(marketDF_for_plot["Time"], marketDF_for_plot["market_price_1"], marker='o', linestyle='-', color='b', markersize=3, linewidth=1)

            ax1.set_xlabel('Time', fontsize=8)
            ax1.set_ylabel('SoC', fontsize=12, color='g')
            ax2.set_ylabel('Market price', fontsize=12, color='b')

            plt.tight_layout() 
            plt.savefig(plot_output_path) 
            print(f"Plot saved to {plot_output_path}")
            plt.close(fig) 

        except Exception as e:
            print(f"ERROR: An error occurred while generating or saving the plot: {e}")
            plt.close('all') 
    else:
        print(f"Solution cannot be found. Solver status: {solver.status()}")