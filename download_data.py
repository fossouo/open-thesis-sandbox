import os
import json
import datetime
import yfinance as yf
import pandas as pd

def download_and_clean_data():
    tickers = ["NVDA", "AMD", "AVGO", "MU", "QCOM", "INTC", "MSFT", "GOOGL", "META", "AMZN"]
    print(f"Starting data download for tickers: {', '.join(tickers)}")
    
    # Calculate date range (last 10 years)
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=10 * 365 + 3) # 10 years + leap days
    
    print(f"Date range: {start_date} to {end_date}")
    
    try:
        # Download historical adjusted close prices
        # We set auto_adjust=False to retrieve the 'Adj Close' column explicitly
        df = yf.download(tickers, start=start_date, end=end_date, auto_adjust=False, progress=False)
        
        if 'Adj Close' not in df:
            if 'Close' in df:
                print("Using 'Close' column (as fallback).")
                adj_close = df['Close']
            else:
                raise ValueError("Failed to retrieve price columns from Yahoo Finance.")
        else:
            adj_close = df['Adj Close']
        
        # Log download status
        print(f"Downloaded raw data. Shape: {adj_close.shape}")
        
        # Check for missing values and clean them
        nan_counts = adj_close.isna().sum()
        for ticker, count in nan_counts.items():
            if count > 0:
                print(f"Ticker {ticker} has {count} missing values. Cleaning...")
        
        # Forward fill first (propagate last valid price), then backward fill (for pre-IPO or early missing data)
        # This resolves missing days and ensures no NaNs remain.
        # Backward filling pre-IPO makes the return before IPO 0%, avoiding survivorship bias and NaN errors.
        adj_close_clean = adj_close.ffill().bfill()
        
        # Check if there are still any NaNs
        remaining_nans = adj_close_clean.isna().sum().sum()
        if remaining_nans > 0:
            raise ValueError(f"Data cleaning failed. Remaining NaN count: {remaining_nans}")
            
        print("Data cleaning successful. No NaN values remaining.")
        
        # Optimize JSON size by rounding prices to 4 decimal places
        adj_close_clean = adj_close_clean.round(4)
        
        # Prepare compact JSON structure
        # Column-oriented layout: list of dates, list of tickers, and dictionary of prices per ticker
        dates_list = [date.strftime('%Y-%m-%d') for date in adj_close_clean.index]
        tickers_list = list(adj_close_clean.columns)
        prices_dict = {}
        for ticker in tickers_list:
            prices_dict[ticker] = adj_close_clean[ticker].tolist()
            
        output_data = {
            "dates": dates_list,
            "tickers": tickers_list,
            "prices": prices_dict
        }
        
        # Ensure target directory exists
        os.makedirs("data", exist_ok=True)
        output_path = os.path.join("data", "prices_top10.json")
        
        # Write compact JSON (no extra indentation to keep it optimized)
        with open(output_path, "w") as f:
            json.dump(output_data, f)
            
        print(f"Data pipeline finished successfully. Exported to {output_path}")
        print(f"Total trading days: {len(dates_list)}")
        print(f"File size: {os.path.getsize(output_path) / 1024:.2f} KB")
        
    except Exception as e:
        print(f"Error during data pipeline execution: {e}")
        raise e

if __name__ == "__main__":
    download_and_clean_data()
