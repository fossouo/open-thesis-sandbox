#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "=========================================================="
echo "Financial Thesis Sandbox - Top 10 Semiconductors & US AI"
echo "=========================================================="

# ---- Q-012 mirror: strip Anthropic/OpenAI keys so they cannot leak to subprocesses ----
unset ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN
unset OPENAI_API_KEY OPENAI_BASE_URL OPENAI_ORG_ID

# ---- Load .env if present ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

if [ -f "$ENV_FILE" ]; then
  echo "Loading environment from $ENV_FILE ..."
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo ""
  echo "ERROR / ERREUR"
  echo "  .env file not found. The server cannot start without LiteLLM configuration."
  echo "  Le fichier .env est introuvable. Le serveur ne peut pas démarrer sans configuration LiteLLM."
  echo ""
  echo "  Fix / Correction :"
  echo "    cp $ENV_EXAMPLE $ENV_FILE"
  echo "    # then edit $ENV_FILE and set LITELLM_URL, LITELLM_MODEL, LITELLM_API_KEY"
  echo ""
  exit 1
fi

# ---- Re-strip Anthropic/OpenAI keys in case .env accidentally contained them ----
unset ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN
unset OPENAI_API_KEY OPENAI_BASE_URL OPENAI_ORG_ID

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
