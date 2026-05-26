"""
Auto-Research Worker — Dynamic S&P 500 Market Discovery Engine.

Scans the full S&P 500 universe, computes market signals (momentum, abnormal volume,
sector growth), builds Top 10 Global and Top 10 Sectoral baskets, and persists
results as immutable DAG nodes. Uses an LLM adversarial review for failing baskets.

NO HARDCODED TICKER LISTS. Everything is discovered dynamically.
"""

import os
import json
import logging
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import io
import re

import httpx
import numpy as np
import pandas as pd
import requests

from core.dag_store import (
    init_db, insert_node, promote_to_canonical,
    get_latest_canonical, update_audio_file
)

logger = logging.getLogger("financial_thesis_sandbox.auto_research")

# Configuration
LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:8000/v1/chat/completions")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "gpt-4o-mini")

def _llm_headers() -> dict:
    h = {"Content-Type": "application/json"}
    if LITELLM_API_KEY:
        h["Authorization"] = f"Bearer {LITELLM_API_KEY}"
    return h

TTS_API_URL = os.getenv("TTS_API_URL", "http://localhost:8880/v1/audio/speech")
TTS_MODEL = os.getenv("TTS_MODEL", "kokoro")
UNIVERSE_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sp500_universe.json")
UNIVERSE_CACHE_MAX_AGE_HOURS = 24

# Sector mapping: GICS Sector → our simplified sector categories
# Maps GICS sectors and sub-industries to our target sector groups
SECTOR_GROUPS = {
    "ai_semiconductors": {
        "label": {"fr": "IA & Semi-conducteurs", "en": "AI & Semiconductors"},
        "emoji": "🔬",
        "gics_sectors": ["Information Technology"],
        "sub_industry_keywords": [
            "semiconductor", "gpu", "chip", "integrated circuit",
            "electronic component", "electronic equipment"
        ]
    },
    "cloud_software": {
        "label": {"fr": "Cloud & Logiciel", "en": "Cloud & Software"},
        "emoji": "☁️",
        "gics_sectors": ["Information Technology", "Communication Services"],
        "sub_industry_keywords": [
            "software", "cloud", "saas", "internet", "data processing",
            "application software", "systems software", "interactive media"
        ]
    },
    "healthcare_biotech": {
        "label": {"fr": "Santé & Biotech", "en": "Healthcare & Biotech"},
        "emoji": "🧬",
        "gics_sectors": ["Health Care"],
        "sub_industry_keywords": []  # All Health Care tickers qualify
    },
    "energy_materials": {
        "label": {"fr": "Énergie & Matériaux", "en": "Energy & Materials"},
        "emoji": "⚡",
        "gics_sectors": ["Energy", "Materials"],
        "sub_industry_keywords": []
    },
    "financials": {
        "label": {"fr": "Finance", "en": "Financials"},
        "emoji": "🏦",
        "gics_sectors": ["Financials"],
        "sub_industry_keywords": []
    }
}

# Signal weights for composite scoring
MOMENTUM_WEIGHT = 0.40
VOLUME_WEIGHT = 0.30
SECTOR_GROWTH_WEIGHT = 0.30

# Adversarial review thresholds
MAX_DRAWDOWN_THRESHOLD = -0.35  # -35%
UNDERPERFORM_THRESHOLD = -0.25  # -25% (single stock 60d return)
MAX_ADVERSARIAL_DEPTH = 3


def fetch_sp500_universe(force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch the S&P 500 constituent list from Wikipedia.
    Caches locally for UNIVERSE_CACHE_MAX_AGE_HOURS.
    
    Returns DataFrame with columns: Symbol, Security, GICS Sector, GICS Sub-Industry
    """
    # Check cache
    if not force_refresh and os.path.exists(UNIVERSE_CACHE_PATH):
        try:
            cache_age = time.time() - os.path.getmtime(UNIVERSE_CACHE_PATH)
            if cache_age < UNIVERSE_CACHE_MAX_AGE_HOURS * 3600:
                with open(UNIVERSE_CACHE_PATH, "r") as f:
                    cached = json.load(f)
                df = pd.DataFrame(cached)
                logger.info(f"Loaded S&P 500 universe from cache ({len(df)} tickers, age: {cache_age/3600:.1f}h)")
                return df
        except Exception as e:
            logger.warning(f"Failed to load universe cache: {e}")
    
    # Fetch from Wikipedia
    logger.info("Fetching S&P 500 universe from Wikipedia...")
    _WP_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        try:
            # Prefer requests so we control the User-Agent (avoids Wikipedia 403)
            resp = requests.get(url, headers={"User-Agent": _WP_UA}, timeout=30)
            resp.raise_for_status()
            tables = pd.read_html(io.StringIO(resp.text))
        except Exception:
            # Fallback: let pandas fetch directly with UA override if supported
            tables = pd.read_html(
                url,
                storage_options={"User-Agent": _WP_UA},
            )
        df = tables[0]
        
        # Normalize columns
        df = df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
        
        # Clean ticker symbols (Wikipedia uses dots, Yahoo uses dashes)
        df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
        
        # Remove any duplicates
        df = df.drop_duplicates(subset=["Symbol"])
        
        logger.info(f"Fetched {len(df)} S&P 500 constituents")
        
        # Cache to disk
        os.makedirs(os.path.dirname(UNIVERSE_CACHE_PATH), exist_ok=True)
        with open(UNIVERSE_CACHE_PATH, "w") as f:
            json.dump(df.to_dict(orient="records"), f)
        
        return df
        
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500 universe: {e}")
        # Try loading stale cache as fallback
        if os.path.exists(UNIVERSE_CACHE_PATH):
            with open(UNIVERSE_CACHE_PATH, "r") as f:
                return pd.DataFrame(json.load(f))
        raise


def compute_market_signals(
    tickers: list[str],
    sector_map: dict[str, str],
    lookback_days: int = 90
) -> pd.DataFrame:
    """
    Download price+volume history and compute three market signals per ticker.
    
    Returns DataFrame indexed by Symbol with columns:
    - momentum_score, volume_score, sector_score, composite_score
    - return_5d, return_20d, return_60d, avg_volume_5d, avg_volume_60d
    - gics_sector
    """
    import yfinance as yf
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days + 30)  # Extra buffer for moving averages
    
    logger.info(f"Downloading price data for {len(tickers)} tickers ({start_date.date()} to {end_date.date()})...")
    
    # Download in batches to avoid Yahoo rate limits
    batch_size = 50
    all_close = []
    all_volume = []
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(
                batch,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                progress=False,
                threads=True
            )
            
            if len(batch) == 1:
                # Single ticker: yfinance returns flat DataFrame
                close = data[["Close"]].copy()
                close.columns = batch
                vol = data[["Volume"]].copy()
                vol.columns = batch
            else:
                close = data["Close"] if "Close" in data.columns.get_level_values(0) else data
                vol = data["Volume"] if "Volume" in data.columns.get_level_values(0) else pd.DataFrame()
            
            all_close.append(close)
            if not vol.empty:
                all_volume.append(vol)
                
        except Exception as e:
            logger.warning(f"Failed to download batch {i//batch_size + 1}: {e}")
            continue
    
    if not all_close:
        raise RuntimeError("Failed to download any price data")
    
    prices = pd.concat(all_close, axis=1)
    volumes = pd.concat(all_volume, axis=1) if all_volume else pd.DataFrame()
    
    # Clean: forward fill, then drop tickers with too many NaNs (>30%)
    prices = prices.ffill().bfill()
    valid_tickers = prices.columns[prices.isna().mean() < 0.3].tolist()
    prices = prices[valid_tickers]
    
    if volumes.empty:
        volumes = pd.DataFrame(1.0, index=prices.index, columns=prices.columns)
    else:
        volumes = volumes.reindex(columns=valid_tickers).ffill().bfill().fillna(1.0)
    
    logger.info(f"Valid tickers after cleaning: {len(valid_tickers)}")
    
    # Compute signals
    signals = []
    
    for ticker in valid_tickers:
        try:
            p = prices[ticker].dropna()
            v = volumes[ticker].dropna() if ticker in volumes.columns else pd.Series([1.0])
            
            if len(p) < 20:
                continue
            
            # Momentum: weighted average of 5d, 20d, 60d returns
            ret_5d = (p.iloc[-1] / p.iloc[-6] - 1) if len(p) >= 6 else 0
            ret_20d = (p.iloc[-1] / p.iloc[-21] - 1) if len(p) >= 21 else 0
            ret_60d = (p.iloc[-1] / p.iloc[-61] - 1) if len(p) >= 61 else 0
            
            momentum = 0.5 * ret_5d + 0.3 * ret_20d + 0.2 * ret_60d
            
            # Volume anomaly: 5d avg / 60d avg
            avg_vol_5d = v.tail(5).mean() if len(v) >= 5 else v.mean()
            avg_vol_60d = v.tail(60).mean() if len(v) >= 60 else v.mean()
            volume_ratio = (avg_vol_5d / avg_vol_60d) if avg_vol_60d > 0 else 1.0
            # Normalize: ratio > 1 = abnormal activity = positive signal
            volume_score = min(max(volume_ratio - 1.0, -0.5), 2.0)  # Clamp [-0.5, 2.0]
            
            signals.append({
                "Symbol": ticker,
                "momentum_score": momentum,
                "volume_score": volume_score,
                "return_5d": ret_5d,
                "return_20d": ret_20d,
                "return_60d": ret_60d,
                "avg_volume_5d": float(avg_vol_5d),
                "avg_volume_60d": float(avg_vol_60d),
                "gics_sector": sector_map.get(ticker, "Unknown"),
                "last_price": float(p.iloc[-1])
            })
            
        except Exception as e:
            logger.debug(f"Skipping {ticker}: {e}")
            continue
    
    signals_df = pd.DataFrame(signals).set_index("Symbol")
    
    # Sector growth score: average momentum of peers in same sector
    sector_avg_momentum = signals_df.groupby("gics_sector")["momentum_score"].mean()
    signals_df["sector_score"] = signals_df["gics_sector"].map(sector_avg_momentum).fillna(0)
    
    # Composite score
    signals_df["composite_score"] = (
        MOMENTUM_WEIGHT * signals_df["momentum_score"] +
        VOLUME_WEIGHT * signals_df["volume_score"] +
        SECTOR_GROWTH_WEIGHT * signals_df["sector_score"]
    )
    
    # Rank
    signals_df = signals_df.sort_values("composite_score", ascending=False)
    
    logger.info(f"Computed signals for {len(signals_df)} tickers. Top 5: {list(signals_df.head().index)}")
    
    return signals_df


def build_top10_global(signals_df: pd.DataFrame) -> list[str]:
    """Rank all tickers by composite score and return the top 10."""
    return list(signals_df.head(10).index)


def build_top10_sectoral(
    signals_df: pd.DataFrame,
    universe_df: pd.DataFrame
) -> dict[str, list[str]]:
    """
    Build Top 10 lists per sector group.
    Only emits sectors with at least 5 qualifying tickers.
    """
    # Build sub-industry lookup
    sub_industry_map = dict(zip(
        universe_df["Symbol"],
        universe_df["GICS Sub-Industry"].str.lower().fillna("")
    ))
    
    sectoral_results = {}
    
    for sector_key, sector_config in SECTOR_GROUPS.items():
        # Filter tickers belonging to this sector group
        gics_sectors = sector_config["gics_sectors"]
        sub_keywords = sector_config["sub_industry_keywords"]
        
        mask = signals_df["gics_sector"].isin(gics_sectors)
        sector_tickers = signals_df[mask].copy()
        
        # If sub-industry keywords are specified, further filter
        if sub_keywords:
            def matches_sub_industry(ticker):
                sub = sub_industry_map.get(ticker, "")
                return any(kw in sub for kw in sub_keywords)
            
            matching = [t for t in sector_tickers.index if matches_sub_industry(t)]
            if len(matching) >= 5:
                sector_tickers = sector_tickers.loc[matching]
        
        # Only emit if enough tickers
        if len(sector_tickers) >= 5:
            top10 = list(sector_tickers.head(10).index)
            sectoral_results[sector_key] = top10
            logger.info(f"Sector '{sector_key}': {len(sector_tickers)} candidates, Top 10: {top10}")
        else:
            logger.info(f"Sector '{sector_key}': only {len(sector_tickers)} candidates, skipping")
    
    return sectoral_results


def backtest_basket(
    tickers: list[str],
    lookback_days: int = 90,
    equal_weight: bool = True
) -> dict:
    """
    Compute Base-100 performance, CAGR, cumulative return, and max drawdown.
    
    Returns: {cumulative_return, cagr, max_drawdown, values, dates}
    """
    import yfinance as yf
    
    if not tickers:
        return {
            "cumulative_return": 0.0,
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "values": [],
            "dates": []
        }
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days + 10)
    
    data = yf.download(tickers, start=start_date, end=end_date, auto_adjust=True, progress=False)
    
    if len(tickers) == 1:
        close = data[["Close"]].copy()
        close.columns = tickers
    else:
        close = data["Close"] if "Close" in data.columns.get_level_values(0) else data
    
    close = close[tickers].ffill().bfill().dropna()
    
    if close.empty or len(close) < 5:
        return {
            "cumulative_return": 0.0,
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "values": [],
            "dates": []
        }
    
    # Compute weighted portfolio value (Base 100)
    if equal_weight:
        weights = {t: 1.0 / len(tickers) for t in tickers}
    else:
        weights = {t: 1.0 / len(tickers) for t in tickers}
    
    base_prices = close.iloc[0]
    portfolio_values = []
    
    for idx in range(len(close)):
        val = sum(weights[t] * (close[t].iloc[idx] / base_prices[t]) for t in tickers) * 100
        portfolio_values.append(val)
    
    values = np.array(portfolio_values)
    
    # Cumulative return
    cumul = (values[-1] / values[0] - 1) * 100  # In percent
    
    # CAGR
    years = len(close) / 252  # Trading days per year
    if years > 0 and values[0] > 0:
        cagr = ((values[-1] / values[0]) ** (1 / years) - 1) * 100
    else:
        cagr = 0.0
    
    # Max Drawdown
    peak = np.maximum.accumulate(values)
    drawdown = (values - peak) / peak
    max_dd = float(np.min(drawdown)) * 100  # In percent (negative)
    
    dates = [d.strftime("%Y-%m-%d") for d in close.index]
    
    return {
        "cumulative_return": round(cumul, 2),
        "cagr": round(cagr, 2),
        "max_drawdown": round(max_dd, 2),
        "values": [round(v, 2) for v in values.tolist()],
        "dates": dates
    }


async def generate_hypothesis(
    tickers: list[str],
    signals_df: pd.DataFrame,
    lang: str,
    sector_label: str = "Global"
) -> str:
    """
    Call the configured LLM to generate a 2-3 sentence investment hypothesis.
    """
    # Build signal summary for the selected tickers
    selected = signals_df.loc[signals_df.index.isin(tickers)]
    signal_summary = []
    for t in tickers:
        if t in selected.index:
            row = selected.loc[t]
            signal_summary.append(
                f"- {t}: momentum={row['momentum_score']:.3f}, "
                f"volume_anomaly={row['volume_score']:.3f}, "
                f"5d_return={row['return_5d']*100:.1f}%"
            )
    
    signals_text = "\n".join(signal_summary[:10])
    
    if lang == "fr":
        prompt = (
            f"Tu es un stratège quantitatif de haut niveau. Voici le Top 10 '{sector_label}' "
            f"identifié par notre algorithme de scoring (momentum + volume anormal + croissance sectorielle) :\n\n"
            f"{signals_text}\n\n"
            f"Génère une hypothèse d'investissement en EXACTEMENT 2-3 phrases expliquant pourquoi ce panier "
            f"a été sélectionné et quel catalyseur de marché il capture. Sois précis et analytique. "
            f"Pas d'introduction ni de salutation."
        )
    else:
        prompt = (
            f"You are an elite quantitative strategist. Here is the Top 10 '{sector_label}' "
            f"identified by our signal scoring algorithm (momentum + abnormal volume + sector growth):\n\n"
            f"{signals_text}\n\n"
            f"Generate an investment hypothesis in EXACTLY 2-3 sentences explaining why this basket "
            f"was selected and what market catalyst it captures. Be precise and analytical. "
            f"No introduction or greeting."
        )
    
    timeout = httpx.Timeout(20.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                LITELLM_URL,
                headers=_llm_headers(),
                json={
                    "model": LITELLM_MODEL,
                    # R-501: Gemma4 has thinking=1 by default — disable to get real content
                    "chat_template_kwargs": {"enable_thinking": False},
                    "messages": [
                        {"role": "system", "content": "You are a financial analyst."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 512
                }
            )

            if resp.status_code != 200:
                logger.error(f"LiteLLM hypothesis generation failed: {resp.status_code}")
                return f"[Auto-generated] Top 10 {sector_label} basket selected by composite signal scoring."

            content = resp.json()["choices"][0]["message"]["content"] or ""
            content = content.strip()

            # Strip think tags (R-501 defensive: model may still emit them)
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()

            # Defensive fallback: never store empty hypothesis
            if not content:
                logger.warning("generate_hypothesis: empty content after stripping think tags — using fallback")
                return f"[Auto-generated] Top 10 {sector_label} basket selected by composite signal scoring."

            return content
            
        except Exception as e:
            logger.error(f"Hypothesis generation failed: {e}")
            return f"[Auto-generated] Top 10 {sector_label} basket selected by composite signal scoring."


async def adversarial_review(
    parent_node_id: str,
    tickers: list[str],
    quant_report: dict,
    signals_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    lang: str,
    sector_key: str,
    db_conn,
    depth: int = 0,
    force_adversarial: bool = False
) -> Optional[str]:
    """
    Adversarial LLM review: analyze a failing basket and propose replacements.
    
    Triggers when:
    - max_drawdown < MAX_DRAWDOWN_THRESHOLD (-35%)
    - Any single ticker has a 60d return < UNDERPERFORM_THRESHOLD (-25%)
    - force_adversarial is True (Deep Audit)
    
    Returns the child node ID if a new node was created, None otherwise.
    """
    if depth >= MAX_ADVERSARIAL_DEPTH:
        logger.info(f"Adversarial review depth limit ({MAX_ADVERSARIAL_DEPTH}) reached. Stopping.")
        return None
    
    max_dd = quant_report.get("max_drawdown", 0)
    
    # Check for underperforming individual tickers
    underperformers = []
    for t in tickers:
        if t in signals_df.index:
            ret_60d = signals_df.loc[t, "return_60d"]
            if ret_60d < UNDERPERFORM_THRESHOLD:
                underperformers.append((t, ret_60d))
    
    should_review = force_adversarial or max_dd / 100 < MAX_DRAWDOWN_THRESHOLD or len(underperformers) > 0
    
    if not should_review:
        logger.info(f"No adversarial review needed (DD={max_dd}%, underperformers={len(underperformers)})")
        return None
    
    logger.info(f"Triggering adversarial review (depth={depth}, DD={max_dd}%, forced={force_adversarial}, DD={max_dd}%, underperformers={underperformers})")
    
    # Build the adversarial prompt
    underperf_text = "\n".join([f"- {t}: {r*100:.1f}% return (60d)" for t, r in underperformers])
    
    # Get available replacements from the universe
    available = [t for t in signals_df.head(50).index if t not in tickers]
    replacements_text = ", ".join(available[:15])
    
    if lang == "fr":
        prompt = (
            f"Tu es un analyste de risque contrarian. Ce portefeuille a ÉCHOUÉ.\n\n"
            f"Composition actuelle : {', '.join(tickers)}\n"
            f"Drawdown max : {max_dd}%\n"
            f"Actions sous-performantes :\n{underperf_text or 'Aucune isolée, mais le drawdown global est critique.'}\n\n"
            f"Candidats de remplacement disponibles (classés par score de signal) : {replacements_text}\n\n"
            f"Instructions :\n"
            f"1. Identifie les 1-3 actions les plus faibles à exclure\n"
            f"2. Propose des remplacements parmi les candidats disponibles\n"
            f"3. Formule une contre-hypothèse en 2 phrases\n\n"
            f"Réponds UNIQUEMENT au format JSON (pas de markdown) :\n"
            f'{{"exclude": ["TICKER1"], "include": ["TICKER2"], "counter_hypothesis": "..."}}'
        )
    else:
        prompt = (
            f"You are a contrarian risk analyst. This portfolio has FAILED.\n\n"
            f"Current composition: {', '.join(tickers)}\n"
            f"Max drawdown: {max_dd}%\n"
            f"Underperforming stocks:\n{underperf_text or 'None isolated, but the overall drawdown is critical.'}\n\n"
            f"Available replacement candidates (ranked by signal score): {replacements_text}\n\n"
            f"Instructions:\n"
            f"1. Identify the 1-3 weakest stocks to exclude\n"
            f"2. Propose replacements from the available candidates\n"
            f"3. Formulate a counter-hypothesis in 2 sentences\n\n"
            f"Respond ONLY in JSON format (no markdown):\n"
            f'{{"exclude": ["TICKER1"], "include": ["TICKER2"], "counter_hypothesis": "..."}}'
        )
    
    timeout = httpx.Timeout(25.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                LITELLM_URL,
                headers=_llm_headers(),
                json={
                    "model": LITELLM_MODEL,
                    # R-501: Gemma4 has thinking=1 by default — disable to get real content
                    "chat_template_kwargs": {"enable_thinking": False},
                    "messages": [
                        {"role": "system", "content": "You are a risk analyst. Respond only in valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.4,
                    "max_tokens": 800
                }
            )

            if resp.status_code != 200:
                logger.error(f"Adversarial review LLM call failed: {resp.status_code}")
                return None

            content = resp.json()["choices"][0]["message"]["content"] or ""
            content = content.strip()

            # Strip think tags (R-501 defensive)
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()

            # Strip markdown code blocks
            content = re.sub(r"^```(?:json)?", "", content, flags=re.IGNORECASE)
            content = re.sub(r"```$", "", content, flags=re.IGNORECASE).strip()
            
            review = json.loads(content)
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse adversarial review response: {e}")
            # Fallback: simple exclusion of worst performer
            if underperformers:
                worst = underperformers[0][0]
                replacement = available[0] if available else None
                review = {
                    "exclude": [worst],
                    "include": [replacement] if replacement else [],
                    "counter_hypothesis": f"Excluded {worst} due to severe underperformance."
                }
            else:
                return None
    
    # Build new basket
    exclude = set(review.get("exclude", []))
    include = review.get("include", [])
    counter_hyp = review.get("counter_hypothesis", "Adversarial review adjustment.")
    
    new_tickers = [t for t in tickers if t not in exclude]
    for t in include:
        if t not in new_tickers and t in signals_df.index:
            new_tickers.append(t)
    
    # Ensure we have exactly 10 tickers
    while len(new_tickers) < 10 and available:
        candidate = available.pop(0)
        if candidate not in new_tickers:
            new_tickers.append(candidate)
    new_tickers = new_tickers[:10]
    
    # Backtest the new basket
    new_quant = backtest_basket(new_tickers)
    new_weights = {t: round(100.0 / len(new_tickers), 2) for t in new_tickers}
    
    # Create child node
    child_id = insert_node(
        conn=db_conn,
        node_type=sector_key,
        lang=lang,
        hypothesis=counter_hyp,
        tickers=new_tickers,
        weights=new_weights,
        quant_report=new_quant,
        parent_id=parent_node_id,
        is_canonical=False
    )
    
    logger.info(f"Created adversarial child node {child_id} (excluded: {exclude}, included: {include[:3]})")
    
    # Recursively check the child node
    deeper_child = await adversarial_review(
        parent_node_id=child_id,
        tickers=new_tickers,
        quant_report=new_quant,
        signals_df=signals_df,
        universe_df=universe_df,
        lang=lang,
        sector_key=sector_key,
        db_conn=db_conn,
        depth=depth + 1
    )
    
    return deeper_child or child_id


async def run_full_research_cycle(
    lang: str = "fr",
    db_path: Optional[str] = None,
    force_adversarial: bool = False
) -> dict[str, str]:
    """
    Orchestrator: runs a full auto-research cycle.
    
    1. Fetch S&P 500 universe
    2. Compute market signals
    3. Build global + sectoral Top 10s
    4. Backtest each basket
    5. Generate AI hypotheses
    6. Run adversarial reviews on failing baskets (or forced)
    7. Persist all nodes to DAG
    8. Promote best nodes to canonical
    
    Returns dict mapping sector_key → node_id of the canonical node.
    """
    logger.info(f"=== Starting Full Research Cycle (lang={lang}, forced={force_adversarial}) ===")
    
    # 1. Init DB
    conn = init_db(db_path)
    
    # 2. Fetch universe
    universe_df = fetch_sp500_universe()
    all_tickers = universe_df["Symbol"].tolist()
    sector_map = dict(zip(universe_df["Symbol"], universe_df["GICS Sector"]))
    
    # 3. Compute signals
    signals_df = compute_market_signals(all_tickers, sector_map)
    
    # 4. Build baskets
    global_top10 = build_top10_global(signals_df)
    sectoral_top10s = build_top10_sectoral(signals_df, universe_df)
    
    # Merge: add global as a "sector"
    all_baskets = {"global": global_top10}
    all_baskets.update(sectoral_top10s)
    
    canonical_nodes = {}
    
    for sector_key, tickers in all_baskets.items():
        logger.info(f"\n--- Processing sector: {sector_key} ({len(tickers)} tickers) ---")
        
        # 5. Backtest
        quant = backtest_basket(tickers)
        weights = {t: round(100.0 / len(tickers), 2) for t in tickers}
        
        # 6. Generate hypothesis
        sector_label = "Global Top 10"
        if sector_key in SECTOR_GROUPS:
            sector_label = SECTOR_GROUPS[sector_key]["label"].get(lang, sector_key)
        
        hypothesis = await generate_hypothesis(tickers, signals_df, lang, sector_label)
        
        # 7. Insert root node
        node_id = insert_node(
            conn=conn,
            node_type=sector_key,
            lang=lang,
            hypothesis=hypothesis,
            tickers=tickers,
            weights=weights,
            quant_report=quant,
            is_canonical=False
        )
        
        # 8. Adversarial review
        final_node_id = await adversarial_review(
            parent_node_id=node_id,
            tickers=tickers,
            quant_report=quant,
            signals_df=signals_df,
            universe_df=universe_df,
            lang=lang,
            sector_key=sector_key,
            db_conn=conn,
            depth=0,
            force_adversarial=force_adversarial
        )
        
        # The best node is the final one (deepest adversarial child, or root if no review needed)
        best_node_id = final_node_id or node_id
        promote_to_canonical(conn, best_node_id)
        canonical_nodes[sector_key] = best_node_id
        
        logger.info(f"Sector {sector_key}: canonical node = {best_node_id}")
    
    conn.close()
    logger.info(f"=== Research Cycle Complete. Canonical nodes: {len(canonical_nodes)} ===")
    
    return canonical_nodes
