import os
import json
import pytest

def get_prices_path():
    return os.path.join(os.path.dirname(__file__), "..", "data", "prices_top10.json")

def test_prices_file_exists():
    path = get_prices_path()
    assert os.path.exists(path), f"Database file not found at {path}. Run download_data.py first."

def test_prices_file_structure():
    path = get_prices_path()
    with open(path, "r") as f:
        data = json.load(f)
        
    # Check fields existence
    assert "dates" in data, "JSON missing 'dates' key"
    assert "tickers" in data, "JSON missing 'tickers' key"
    assert "prices" in data, "JSON missing 'prices' key"
    
    # Check field types
    assert isinstance(data["dates"], list), "'dates' must be a list"
    assert isinstance(data["tickers"], list), "'tickers' must be a list"
    assert isinstance(data["prices"], dict), "'prices' must be a dictionary"
    
    # Check ticker parity
    expected_tickers = {"NVDA", "AMD", "AVGO", "MU", "QCOM", "INTC", "MSFT", "GOOGL", "META", "AMZN"}
    assert set(data["tickers"]) == expected_tickers, "Tickers list mismatch"
    
    num_days = len(data["dates"])
    assert num_days > 2000, f"Expected ~2500 trading days for 10 years, found {num_days}"
    
    # Validate prices data completeness
    for ticker in expected_tickers:
        assert ticker in data["prices"], f"Prices dictionary missing ticker {ticker}"
        prices = data["prices"][ticker]
        assert isinstance(prices, list), f"Prices for {ticker} must be a list"
        assert len(prices) == num_days, f"Prices length for {ticker} ({len(prices)}) does not match dates length ({num_days})"
        
        # Ensure prices are valid positive numbers and no NaNs exist
        assert all(isinstance(p, (int, float)) for p in prices), f"Non-numeric price found in {ticker}"
        assert all(p > 0 for p in prices), f"Non-positive price found in {ticker}"

def test_backtest_math():
    path = get_prices_path()
    with open(path, "r") as f:
        data = json.load(f)
        
    tickers = data["tickers"]
    dates = data["dates"]
    N = len(dates)
    
    # Portfolio allocation: Equal weight
    weights = {ticker: 10.0 for ticker in tickers}
    total_w = sum(weights.values())
    norm_w = [weights[t] / total_w for t in tickers]
    
    portfolio_values = []
    starting_prices = [data["prices"][t][0] for t in tickers]
    
    for t in range(N):
        val = 0.0
        for i, ticker in enumerate(tickers):
            price_t = data["prices"][ticker][t]
            price_0 = starting_prices[i]
            val += norm_w[i] * (price_t / price_0)
        portfolio_values.append(val * 100)
        
    # Check properties of simulation
    assert portfolio_values[0] == pytest.approx(100.0), "Portfolio performance series must start at Base 100"
    assert all(v > 0 for v in portfolio_values), "Portfolio values cannot drop below 0"
    assert len(portfolio_values) == N, "Performance series length mismatch"
