"""
Tests for the Auto-Research DAG Engine.

Covers: DAG storage, signal computation, top-10 ranking, backtest math,
adversarial review triggers, and tier freshness logic.
"""

import os
import json
import sqlite3
import pytest
import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

import pandas as pd
import numpy as np

from core.dag_store import (
    init_db, insert_node, get_node, get_latest_canonical,
    get_latest_node, get_frontier, get_node_tree, get_children,
    promote_to_canonical, count_nodes, get_nodes_by_freshness,
    get_available_sectors, _compute_hash
)
from core.auto_research import (
    build_top10_global, build_top10_sectoral,
    SECTOR_GROUPS, MAX_DRAWDOWN_THRESHOLD, UNDERPERFORM_THRESHOLD
)


# ============================
# DAG Store Tests
# ============================

def test_dag_init_and_insert(tmp_path):
    """Test database initialization and node insertion."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    assert count_nodes(conn) == 0
    
    node_id = insert_node(
        conn=conn,
        node_type="global",
        lang="fr",
        hypothesis="Test hypothesis for the global basket.",
        tickers=["NVDA", "AMD", "MSFT"],
        weights={"NVDA": 40.0, "AMD": 30.0, "MSFT": 30.0},
        quant_report={"cumulative_return": 15.5, "cagr": 12.3, "max_drawdown": -8.2}
    )
    
    assert node_id is not None
    assert count_nodes(conn) == 1
    
    # Retrieve and verify
    node = get_node(conn, node_id)
    assert node is not None
    assert node["node_type"] == "global"
    assert node["lang"] == "fr"
    assert node["hypothesis"] == "Test hypothesis for the global basket."
    assert node["tickers"] == ["NVDA", "AMD", "MSFT"]
    assert node["weights"]["NVDA"] == 40.0
    assert node["quant_report"]["cagr"] == 12.3
    assert node["parent_id"] is None
    assert node["is_canonical"] == 0
    
    conn.close()


def test_dag_immutability_hash(tmp_path):
    """Verify that the data hash is computed correctly for integrity."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    node_id = insert_node(
        conn=conn,
        node_type="global",
        lang="en",
        hypothesis="Hash test",
        tickers=["AAPL", "GOOG"],
        weights={"AAPL": 50.0, "GOOG": 50.0},
        quant_report={"cumulative_return": 10.0, "cagr": 8.0, "max_drawdown": -5.0}
    )
    
    node = get_node(conn, node_id)
    
    # Recompute hash and verify match
    expected_hash = _compute_hash(["AAPL", "GOOG"], {"AAPL": 50.0, "GOOG": 50.0}, node["created_at"])
    assert node["data_hash"] == expected_hash
    
    conn.close()


def test_dag_parent_child_relationship(tmp_path):
    """Test DAG parent-child relationship and tree traversal."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    # Root node
    root_id = insert_node(
        conn=conn, node_type="global", lang="fr",
        hypothesis="Root hypothesis",
        tickers=["NVDA", "AMD"], weights={"NVDA": 50, "AMD": 50},
        quant_report={"cumulative_return": -40, "cagr": -15, "max_drawdown": -45}
    )
    
    # Child node (adversarial review result)
    child_id = insert_node(
        conn=conn, node_type="global", lang="fr",
        hypothesis="Adversarial child: excluded AMD",
        tickers=["NVDA", "MSFT"], weights={"NVDA": 50, "MSFT": 50},
        quant_report={"cumulative_return": 10, "cagr": 8, "max_drawdown": -12},
        parent_id=root_id
    )
    
    # Verify child
    child = get_node(conn, child_id)
    assert child["parent_id"] == root_id
    
    # Verify children lookup
    children = get_children(conn, root_id)
    assert len(children) == 1
    assert children[0]["id"] == child_id
    
    # Verify tree traversal (from child to root)
    tree = get_node_tree(conn, child_id)
    assert len(tree) == 2
    assert tree[0]["id"] == root_id  # Root first
    assert tree[1]["id"] == child_id  # Then child
    
    conn.close()


def test_dag_canonical_promotion(tmp_path):
    """Test promoting a node to canonical and demoting the previous one."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    node1_id = insert_node(
        conn=conn, node_type="ai_semiconductors", lang="fr",
        hypothesis="First",
        tickers=["NVDA"], weights={"NVDA": 100},
        quant_report={"cumulative_return": 5, "cagr": 4, "max_drawdown": -3},
        is_canonical=True
    )
    
    node2_id = insert_node(
        conn=conn, node_type="ai_semiconductors", lang="fr",
        hypothesis="Second (better)",
        tickers=["AMD"], weights={"AMD": 100},
        quant_report={"cumulative_return": 20, "cagr": 15, "max_drawdown": -5}
    )
    
    # Verify node1 is currently canonical
    canonical = get_latest_canonical(conn, "ai_semiconductors", "fr")
    assert canonical["id"] == node1_id
    
    # Promote node2
    promote_to_canonical(conn, node2_id)
    
    # Verify node2 is now canonical and node1 is demoted
    canonical = get_latest_canonical(conn, "ai_semiconductors", "fr")
    assert canonical["id"] == node2_id
    
    node1 = get_node(conn, node1_id)
    assert node1["is_canonical"] == 0
    
    conn.close()


def test_dag_frontier(tmp_path):
    """Test frontier query (leaf nodes with no children)."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    root_id = insert_node(
        conn=conn, node_type="global", lang="fr",
        hypothesis="Root", tickers=["A"], weights={"A": 100},
        quant_report={"cumulative_return": 1, "cagr": 1, "max_drawdown": -1}
    )
    
    child_id = insert_node(
        conn=conn, node_type="global", lang="fr",
        hypothesis="Child", tickers=["B"], weights={"B": 100},
        quant_report={"cumulative_return": 2, "cagr": 2, "max_drawdown": -2},
        parent_id=root_id
    )
    
    frontier = get_frontier(conn, "global")
    assert len(frontier) == 1
    assert frontier[0]["id"] == child_id  # Only leaf node
    
    conn.close()


def test_dag_available_sectors(tmp_path):
    """Test available sectors summary query."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    insert_node(
        conn=conn, node_type="global", lang="fr",
        hypothesis="Global", tickers=["A", "B", "C"], weights={"A": 33, "B": 33, "C": 34},
        quant_report={"cumulative_return": 10, "cagr": 8, "max_drawdown": -5}
    )
    insert_node(
        conn=conn, node_type="ai_semiconductors", lang="fr",
        hypothesis="AI", tickers=["X", "Y"], weights={"X": 50, "Y": 50},
        quant_report={"cumulative_return": 20, "cagr": 15, "max_drawdown": -8}
    )
    
    sectors = get_available_sectors(conn, "fr")
    assert len(sectors) == 2
    sector_types = {s["node_type"] for s in sectors}
    assert "global" in sector_types
    assert "ai_semiconductors" in sector_types
    
    conn.close()


# ============================
# Signal & Ranking Tests
# ============================

def test_top10_global_ranking():
    """Test that build_top10_global returns the top 10 by composite score."""
    # Create synthetic signals dataframe
    tickers = [f"TICK{i}" for i in range(20)]
    scores = list(range(20, 0, -1))  # Descending scores
    
    signals_df = pd.DataFrame({
        "composite_score": scores,
        "momentum_score": [s * 0.01 for s in scores],
        "volume_score": [0.1] * 20,
        "sector_score": [0.05] * 20,
        "return_5d": [0.01] * 20,
        "return_20d": [0.02] * 20,
        "return_60d": [0.03] * 20,
        "gics_sector": ["Information Technology"] * 20,
        "last_price": [100.0] * 20
    }, index=tickers)
    
    signals_df = signals_df.sort_values("composite_score", ascending=False)
    
    top10 = build_top10_global(signals_df)
    
    assert len(top10) == 10
    assert top10[0] == "TICK0"  # Highest score
    assert top10[9] == "TICK9"  # 10th highest


def test_top10_sectoral_filtering():
    """Test sectoral top-10 with GICS sector filtering."""
    tickers = ["NVDA", "AMD", "MSFT", "AAPL", "INTC", "QCOM", "AVGO", "MU", "TXN", "MRVL",
               "JNJ", "PFE", "UNH", "ABT", "LLY", "MRK", "BMY", "AMGN", "GILD", "TMO"]
    
    sectors = (["Information Technology"] * 10) + (["Health Care"] * 10)
    
    signals_df = pd.DataFrame({
        "composite_score": list(range(20, 0, -1)),
        "momentum_score": [0.1] * 20,
        "volume_score": [0.05] * 20,
        "sector_score": [0.03] * 20,
        "return_5d": [0.01] * 20,
        "return_20d": [0.02] * 20,
        "return_60d": [0.03] * 20,
        "gics_sector": sectors,
        "last_price": [100.0] * 20
    }, index=tickers)
    
    signals_df = signals_df.sort_values("composite_score", ascending=False)
    
    # Create universe dataframe
    universe_df = pd.DataFrame({
        "Symbol": tickers,
        "Security": tickers,
        "GICS Sector": sectors,
        "GICS Sub-Industry": ["Semiconductors"] * 10 + ["Pharmaceuticals"] * 10
    })
    
    sectoral = build_top10_sectoral(signals_df, universe_df)
    
    # Should have ai_semiconductors and healthcare_biotech (both have >= 5 tickers)
    assert "healthcare_biotech" in sectoral
    assert len(sectoral["healthcare_biotech"]) == 10
    # First healthcare ticker should be JNJ (highest composite in that group)
    assert sectoral["healthcare_biotech"][0] == "JNJ"


def test_backtest_math_synthetic():
    """Cross-validate backtest math with known synthetic data."""
    from core.auto_research import backtest_basket
    
    # yfinance is imported inside backtest_basket, so mock the module-level import
    with patch("yfinance.download") as mock_download:
        # Create synthetic price data: 2 tickers, 60 days, linear growth
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        
        # TICK_A: grows from 100 to 200 (100% return)
        # TICK_B: stays flat at 100 (0% return)
        prices_a = np.linspace(100, 200, 60)
        prices_b = np.full(60, 100.0)
        
        mock_df = pd.DataFrame({
            ("Close", "TICK_A"): prices_a,
            ("Close", "TICK_B"): prices_b,
        }, index=dates)
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        
        mock_download.return_value = mock_df
        
        result = backtest_basket(["TICK_A", "TICK_B"], lookback_days=60)
        
        # Equal weight: 50% × 100% + 50% × 0% = 50% cumulative
        assert result["cumulative_return"] == pytest.approx(50.0, abs=1.0)
        assert result["max_drawdown"] <= 0  # Should be 0 or slightly negative due to rounding
        assert len(result["values"]) == 60
        assert result["values"][0] == pytest.approx(100.0, abs=0.1)  # Starts at base 100



# ============================
# Adversarial Review Tests
# ============================

def test_adversarial_trigger_conditions():
    """Test that adversarial review is triggered by correct conditions."""
    # Case 1: High drawdown should trigger
    quant_failing = {"max_drawdown": -40.0}  # -40% < -35% threshold
    assert quant_failing["max_drawdown"] / 100 < MAX_DRAWDOWN_THRESHOLD
    
    # Case 2: Normal drawdown should NOT trigger
    quant_ok = {"max_drawdown": -20.0}  # -20% > -35% threshold
    assert quant_ok["max_drawdown"] / 100 >= MAX_DRAWDOWN_THRESHOLD
    
    # Case 3: Underperforming ticker should trigger
    assert -0.30 < UNDERPERFORM_THRESHOLD  # -30% < -25%
    assert -0.15 >= UNDERPERFORM_THRESHOLD  # -15% >= -25% (OK)


@pytest.mark.asyncio
async def test_adversarial_creates_child_node(tmp_path):
    """Test that adversarial review creates a child node when triggered."""
    from core.auto_research import adversarial_review
    
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    # Create a failing root node
    root_id = insert_node(
        conn=conn, node_type="global", lang="en",
        hypothesis="Root hypothesis",
        tickers=["BAD_STOCK", "OK_STOCK", "GOOD1", "GOOD2", "GOOD3",
                 "GOOD4", "GOOD5", "GOOD6", "GOOD7", "GOOD8"],
        weights={t: 10.0 for t in ["BAD_STOCK", "OK_STOCK", "GOOD1", "GOOD2", "GOOD3",
                                    "GOOD4", "GOOD5", "GOOD6", "GOOD7", "GOOD8"]},
        quant_report={"cumulative_return": -30, "cagr": -20, "max_drawdown": -42}
    )
    
    # Create signals with one severe underperformer
    tickers = ["BAD_STOCK", "OK_STOCK", "GOOD1", "GOOD2", "GOOD3",
               "GOOD4", "GOOD5", "GOOD6", "GOOD7", "GOOD8",
               "REPLACE1", "REPLACE2", "REPLACE3"]
    signals_df = pd.DataFrame({
        "composite_score": [0.01, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.20, 0.19, 0.18],
        "momentum_score": [0.01] * 13,
        "volume_score": [0.01] * 13,
        "sector_score": [0.01] * 13,
        "return_5d": [-0.10, 0.01, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.05, 0.04, 0.03],
        "return_20d": [-0.20, 0.02, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.06, 0.05, 0.04],
        "return_60d": [-0.30, 0.03, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.07, 0.06, 0.05],
        "gics_sector": ["IT"] * 13,
        "last_price": [50.0] * 13
    }, index=tickers)
    signals_df = signals_df.sort_values("composite_score", ascending=False)
    
    universe_df = pd.DataFrame({
        "Symbol": tickers,
        "Security": tickers,
        "GICS Sector": ["IT"] * 13,
        "GICS Sub-Industry": ["Software"] * 13
    })
    
    # Mock LiteLLM for adversarial review
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "exclude": ["BAD_STOCK"],
                    "include": ["REPLACE1"],
                    "counter_hypothesis": "Excluded BAD_STOCK due to -30% underperformance."
                })
            }
        }]
    }
    
    # Mock backtest to avoid network calls
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        with patch("core.auto_research.backtest_basket") as mock_bt:
            mock_bt.return_value = {
                "cumulative_return": 15.0, "cagr": 12.0, "max_drawdown": -10.0,
                "values": [100, 115], "dates": ["2024-01-01", "2024-03-01"]
            }
            
            child_id = await adversarial_review(
                parent_node_id=root_id,
                tickers=["BAD_STOCK", "OK_STOCK", "GOOD1", "GOOD2", "GOOD3",
                         "GOOD4", "GOOD5", "GOOD6", "GOOD7", "GOOD8"],
                quant_report={"cumulative_return": -30, "cagr": -20, "max_drawdown": -42},
                signals_df=signals_df,
                universe_df=universe_df,
                lang="en",
                sector_key="global",
                db_conn=conn,
                depth=0
            )
    
    # Verify child was created
    assert child_id is not None
    child = get_node(conn, child_id)
    assert child is not None
    assert child["parent_id"] == root_id
    assert "BAD_STOCK" not in child["tickers"]
    assert "REPLACE1" in child["tickers"]
    
    conn.close()


# ============================
# Tier Freshness Logic Tests
# ============================

def test_tier_free_freshness_enforcement(tmp_path):
    """Free tier should only serve canonical nodes older than 7 days."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    # Create a canonical node from 5 days ago
    node_id = insert_node(
        conn=conn, node_type="global", lang="fr",
        hypothesis="Recent node",
        tickers=["NVDA", "AMD"], weights={"NVDA": 50, "AMD": 50},
        quant_report={"cumulative_return": 10, "cagr": 8, "max_drawdown": -5},
        is_canonical=True
    )
    
    # Manually set created_at to 5 days ago
    five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    conn.execute("UPDATE analysis_nodes SET created_at = ? WHERE id = ?", (five_days_ago, node_id))
    conn.commit()
    
    # Free tier (7 day minimum age): should NOT be served (only 5 days old)
    canonical = get_latest_canonical(conn, "global", "fr")
    assert canonical is not None
    
    node_age = datetime.now(timezone.utc) - datetime.fromisoformat(canonical["created_at"])
    is_free_eligible = node_age >= timedelta(days=7)
    assert is_free_eligible is False  # 5 days < 7 days → NOT eligible for free
    
    # Now set it to 10 days ago
    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn.execute("UPDATE analysis_nodes SET created_at = ? WHERE id = ?", (ten_days_ago, node_id))
    conn.commit()
    
    canonical = get_latest_canonical(conn, "global", "fr")
    node_age = datetime.now(timezone.utc) - datetime.fromisoformat(canonical["created_at"])
    is_free_eligible = node_age >= timedelta(days=7)
    assert is_free_eligible is True  # 10 days >= 7 days → eligible for free
    
    conn.close()


def test_tier_premium_freshness_enforcement(tmp_path):
    """Premium tier should serve nodes younger than 24 hours."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    
    # Create a fresh canonical node (just now)
    node_id = insert_node(
        conn=conn, node_type="global", lang="fr",
        hypothesis="Fresh node",
        tickers=["NVDA"], weights={"NVDA": 100},
        quant_report={"cumulative_return": 10, "cagr": 8, "max_drawdown": -5},
        is_canonical=True
    )
    
    canonical = get_latest_canonical(conn, "global", "fr")
    node_age = datetime.now(timezone.utc) - datetime.fromisoformat(canonical["created_at"])
    is_premium_fresh = node_age < timedelta(hours=24)
    assert is_premium_fresh is True  # Just created → fresh for premium
    
    # Set to 30 hours ago → should trigger live research
    old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    conn.execute("UPDATE analysis_nodes SET created_at = ? WHERE id = ?", (old_time, node_id))
    conn.commit()
    
    canonical = get_latest_canonical(conn, "global", "fr")
    node_age = datetime.now(timezone.utc) - datetime.fromisoformat(canonical["created_at"])
    is_premium_fresh = node_age < timedelta(hours=24)
    assert is_premium_fresh is False  # 30h > 24h → needs live research
    
    conn.close()


def test_reader_observes_writer_commits_across_connections(tmp_path):
    """
    Regression: a long-lived reader connection (like main.py's shared `dag_conn`)
    MUST observe inserts committed by a separate writer connection
    (like the one opened inside run_full_research_cycle), sector by sector.

    Guards against a stale WAL snapshot being pinned on the reader, which
    would otherwise return node_count=0 while a cycle is mid-ingest. Note:
    this does not certify every possible timing race during ingest — a query
    that lands before the first sector commits will legitimately still see
    zero nodes.
    """
    db_path = str(tmp_path / "research.db")

    reader = init_db(db_path)
    # Prime the reader with at least one SELECT before any writes — this is
    # how main.py warms up `dag_conn` (count_nodes log line at import time).
    assert count_nodes(reader) == 0
    assert get_available_sectors(reader, "fr") == []

    writer = init_db(db_path)
    sectors = ["technology", "finance", "healthcare"]
    for i, sector in enumerate(sectors, start=1):
        insert_node(
            conn=writer,
            node_type=sector,
            lang="fr",
            hypothesis=f"thesis {i}",
            tickers=[f"T{i}"],
            weights={f"T{i}": 100.0},
            quant_report={"cagr": 0.1, "max_drawdown": -0.1},
        )
        # Cross-connection visibility must be immediate on the shared reader.
        assert count_nodes(reader) == i, (
            f"reader stale after writer commit #{i}: "
            f"expected {i}, got {count_nodes(reader)}"
        )
        observed_sectors = {s["node_type"] for s in get_available_sectors(reader, "fr")}
        assert observed_sectors == set(sectors[:i])

    writer.close()
    reader.close()
