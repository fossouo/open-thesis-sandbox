# Open Thesis Sandbox

A self-hostable research sandbox that turns a portfolio idea into a backtested,
LLM-reviewed investment thesis — with an immutable DAG of every analysis along
the way.

It scans the S&P 500, computes momentum / volume / sector-growth signals, builds
Top-10 sectoral baskets, runs a 5-year backtest, and asks a configurable
OpenAI-compatible LLM to write (and adversarially critique) a thesis for each
basket. Every node is persisted to a local SQLite DAG so you can replay or fork
any analysis later.

> Bring your own LLM. Defaults assume a server on `http://localhost:8000/v1`
> exposing the OpenAI Chat Completions shape (OpenAI itself, Ollama, vLLM,
> llama.cpp, LiteLLM, LM Studio, etc.).

## Getting Started

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env to set LITELLM_URL, LITELLM_MODEL, etc.
   ```
   > **Note**: The server requires an OpenAI-compatible endpoint. The startup guard
   > will reject a missing or self-pointing `LITELLM_URL` (e.g. `localhost:8000`
   > which is the app's own port).

3. **Download market data**:
   ```bash
   # Downloads S&P 500 price snapshots for the backtester
   python3 download_data.py
   ```

4. **Run the server**:
   ```bash
   ./run_local.sh
   ```
   Open <http://localhost:8000> in your browser.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LITELLM_URL` | `http://localhost:8000/v1/chat/completions` | OpenAI-compatible Chat Completions endpoint |
| `LITELLM_MODEL` | `gpt-4o-mini` | Model name routed by your endpoint |
| `LITELLM_API_KEY` | *(empty)* | Bearer token, sent only if non-empty |
| `TTS_API_URL` | `http://localhost:8880/v1/audio/speech` | OpenAI-compatible TTS endpoint (for audio overviews) |
| `TTS_MODEL` | `kokoro` | TTS model/voice name |
| `AUDIO_CACHE_DIR` | `./data/audio-cache` | Where rendered audio is cached |

## Optional: local TTS via Kokoro

`start_tts.sh` runs the public [`kokoro-fastapi`](https://github.com/remsky/kokoro-fastapi)
Docker image on your machine. It tries the AMD ROCm GPU variant first, then
falls back to CPU. By default it exposes `http://localhost:8880`.

## Architecture

```
┌──────────────────────────┐
│  FastAPI (main.py)       │  ← /api/research/{sectors,top10,graph,trigger}
└────────────┬─────────────┘
             │
   ┌─────────▼──────────┐         ┌────────────────────────┐
   │ core/auto_research │ ─────▶ │ OpenAI-compatible LLM   │
   │   (signals + LLM)  │         │ (LITELLM_URL)           │
   └─────────┬──────────┘         └────────────────────────┘
             │
   ┌─────────▼──────────┐
   │ core/dag_store     │  ← SQLite WAL, autocommit, append-only nodes
   └────────────────────┘
```

`core/dag_store.py` is intentionally tiny: every analysis node is a row, child
nodes carry a `parent_id`, and canonical (blessed) nodes are flagged for cheap
retrieval. Connections open in autocommit mode so a long-lived reader is never
pinned to a stale WAL snapshot while a research cycle is mid-ingest.

## Tests

```bash
python3 -m pytest tests/test_auto_research.py      # DAG + signal logic (no network)
python3 -m pytest tests/test_robustness.py         # error-path mocks
python3 -m pytest                                  # full suite (needs data/prices_top10.json)
```

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This software is provided for educational and research purposes only. Nothing
in this repository constitutes investment advice. Backtests are not predictive
of future returns. Do your own research.
