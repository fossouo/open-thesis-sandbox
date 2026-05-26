import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from core.auto_research import backtest_basket

def test_backtest_empty_basket():
    """Test that an empty ticker list returns a zeroed-out report instead of crashing."""
    result = backtest_basket([])
    assert result["cumulative_return"] == 0.0
    assert result["cagr"] == 0.0
    assert result["max_drawdown"] == 0.0
    assert result["values"] == []
    assert result["dates"] == []

@patch("yfinance.download")
def test_backtest_single_ticker(mock_download):
    """Test that a single-ticker basket is handled correctly."""
    dates = pd.date_range(end=datetime.now(), periods=10)
    prices = np.linspace(100, 110, 10)
    
    mock_df = pd.DataFrame({"Close": prices}, index=dates)
    mock_download.return_value = mock_df
    
    result = backtest_basket(["TICK1"], lookback_days=10)
    
    assert result["cumulative_return"] == pytest.approx(10.0)
    assert len(result["values"]) == 10
    assert result["values"][0] == 100.0
    assert result["values"][-1] == 110.0

@patch("yfinance.download")
def test_backtest_missing_some_prices(mock_download):
    """Test robustness when some tickers return NaNs."""
    dates = pd.date_range(end=datetime.now(), periods=10)
    # TICK1: +10%
    # TICK2: All NaNs (should be handled by ffill/bfill or dropped)
    prices_t1 = np.linspace(100, 110, 10)
    prices_t2 = np.full(10, np.nan)
    
    mock_df = pd.DataFrame({
        ("Close", "TICK1"): prices_t1,
        ("Close", "TICK2"): prices_t2,
    }, index=dates)
    mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
    
    mock_download.return_value = mock_df
    
    # TICK2 is all NaNs, ffill/bfill won't help if there's NO data.
    # The code does: close = close[tickers].ffill().bfill().dropna()
    # So TICK2 will be dropped by dropna() if it's all NaNs.
    # Wait, if one column is all NaNs, dropna() drops the ROWS where it is NaN.
    # If all rows for TICK2 are NaN, close becomes EMPTY.
    
    result = backtest_basket(["TICK1", "TICK2"], lookback_days=10)
    
    # If it becomes empty, it returns zeroed report
    assert result["cumulative_return"] == 0.0 or result["cumulative_return"] == pytest.approx(10.0)
    # Actually, let's see what the code does:
    # close = close[tickers].ffill().bfill().dropna()
    # if close.empty or len(close) < 5: return zeroed report
    
    # In this case, close[tickers] has NaNs in TICK2. dropna() will drop all rows.
    assert result["cumulative_return"] == 0.0

@patch("yfinance.download")
def test_backtest_short_history(mock_download):
    """Test that history shorter than 5 days returns a zeroed report."""
    dates = pd.date_range(end=datetime.now(), periods=3)
    prices = [100, 101, 102]
    
    mock_df = pd.DataFrame({"Close": prices}, index=dates)
    mock_download.return_value = mock_df
    
    result = backtest_basket(["TICK1"], lookback_days=3)
    assert result["cumulative_return"] == 0.0
    assert result["values"] == []
