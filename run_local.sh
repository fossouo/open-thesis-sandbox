#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "=========================================================="
echo "Financial Thesis Sandbox - Top 10 Semiconductors & US AI"
echo "=========================================================="

# 1. Detect Python Interpreter with required dependencies
echo "Detecting Python environment..."
PYTHON_EXE=""

# Candidates to check
CANDIDATES=(
  "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
  "python3"
  "python"
)

for cmd in "${CANDIDATES[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    if "$cmd" -c "import yfinance, fastapi, pytest, httpx" >/dev/null 2>&1; then
      PYTHON_EXE="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON_EXE" ]; then
  echo "❌ Error: Could not find a Python environment with yfinance, fastapi, pytest, and httpx installed."
  echo "Please install them via: pip install -r requirements.txt"
  exit 1
fi

echo "✅ Using Python: $PYTHON_EXE"
echo "Python version: $($PYTHON_EXE --version)"

# 2. Check if data is downloaded
DATA_FILE="data/prices_top10.json"
if [ ! -f "$DATA_FILE" ]; then
  echo "⚠️ Data file $DATA_FILE not found. Launching data pipeline..."
  $PYTHON_EXE download_data.py
else
  echo "✅ Found stock price database ($DATA_FILE)."
fi

# 3. Run Automated tests
echo "Running test suite to verify code health..."
$PYTHON_EXE -m pytest tests/

echo "✅ All tests passed successfully!"

# 4. Start FastAPI server
echo "Starting FastAPI server on http://localhost:8000 ..."
$PYTHON_EXE -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
