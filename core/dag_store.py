"""
DAG Store — SQLite-backed immutable Directed Acyclic Graph for analysis nodes.

Each node represents a point-in-time market research result (Top 10 basket,
quant report, AI hypothesis). Nodes are append-only and never modified.
Child nodes are created via adversarial review when a basket fails validation.
"""

import os
import json
import uuid
import hashlib
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("financial_thesis_sandbox.dag")

# Default DB location
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "research.db")


def _get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode for concurrent reads."""
    path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    # Autocommit: prevents the shared reader connection from pinning a WAL
    # snapshot taken at its first SELECT, which would hide nodes that the
    # writer connection commits sector-by-sector during a research cycle.
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Initialize the database schema. Safe to call multiple times (IF NOT EXISTS)."""
    conn = _get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analysis_nodes (
            id TEXT PRIMARY KEY,
            parent_id TEXT,
            created_at TEXT NOT NULL,
            node_type TEXT NOT NULL,
            lang TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            tickers TEXT NOT NULL,
            weights TEXT NOT NULL,
            prices_snapshot TEXT,
            quant_report TEXT NOT NULL,
            audio_file TEXT,
            is_canonical INTEGER DEFAULT 0,
            data_hash TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES analysis_nodes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_node_type ON analysis_nodes(node_type);
        CREATE INDEX IF NOT EXISTS idx_created_at ON analysis_nodes(created_at);
        CREATE INDEX IF NOT EXISTS idx_canonical ON analysis_nodes(is_canonical);
        CREATE INDEX IF NOT EXISTS idx_node_type_lang ON analysis_nodes(node_type, lang);
    """)
    conn.commit()
    logger.info(f"DAG store initialized at {db_path or DEFAULT_DB_PATH}")
    return conn


def _compute_hash(tickers: list, weights: dict, created_at: str) -> str:
    """Compute SHA-256 integrity hash for a node."""
    payload = json.dumps({
        "tickers": sorted(tickers),
        "weights": {k: weights[k] for k in sorted(weights.keys())},
        "created_at": created_at
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def insert_node(
    conn: sqlite3.Connection,
    node_type: str,
    lang: str,
    hypothesis: str,
    tickers: list[str],
    weights: dict[str, float],
    quant_report: dict,
    parent_id: Optional[str] = None,
    prices_snapshot: Optional[dict] = None,
    audio_file: Optional[str] = None,
    is_canonical: bool = False
) -> str:
    """
    Insert an immutable analysis node into the DAG.
    
    Returns the UUID of the newly created node.
    """
    node_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    data_hash = _compute_hash(tickers, weights, created_at)
    
    conn.execute(
        """INSERT INTO analysis_nodes 
           (id, parent_id, created_at, node_type, lang, hypothesis, tickers, weights,
            prices_snapshot, quant_report, audio_file, is_canonical, data_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            node_id,
            parent_id,
            created_at,
            node_type,
            lang,
            hypothesis,
            json.dumps(tickers),
            json.dumps(weights),
            json.dumps(prices_snapshot) if prices_snapshot else None,
            json.dumps(quant_report),
            audio_file,
            1 if is_canonical else 0,
            data_hash
        )
    )
    conn.commit()
    logger.info(f"Inserted DAG node {node_id} (type={node_type}, lang={lang}, canonical={is_canonical})")
    return node_id


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict with JSON fields parsed."""
    d = dict(row)
    for json_field in ("tickers", "weights", "quant_report", "prices_snapshot"):
        if d.get(json_field):
            try:
                d[json_field] = json.loads(d[json_field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_node(conn: sqlite3.Connection, node_id: str) -> Optional[dict]:
    """Retrieve a single node by ID."""
    row = conn.execute("SELECT * FROM analysis_nodes WHERE id = ?", (node_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_latest_canonical(conn: sqlite3.Connection, node_type: str, lang: str) -> Optional[dict]:
    """Get the most recent canonical (blessed) node for a given type and language."""
    row = conn.execute(
        """SELECT * FROM analysis_nodes 
           WHERE node_type = ? AND lang = ? AND is_canonical = 1
           ORDER BY created_at DESC LIMIT 1""",
        (node_type, lang)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_latest_node(conn: sqlite3.Connection, node_type: str, lang: str) -> Optional[dict]:
    """Get the most recent node (canonical or not) for a given type and language."""
    row = conn.execute(
        """SELECT * FROM analysis_nodes 
           WHERE node_type = ? AND lang = ?
           ORDER BY created_at DESC LIMIT 1""",
        (node_type, lang)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_frontier(conn: sqlite3.Connection, node_type: str) -> list[dict]:
    """
    Get leaf nodes (nodes with no children) for a given type.
    These represent the current "frontier" of research.
    """
    rows = conn.execute(
        """SELECT n.* FROM analysis_nodes n
           LEFT JOIN analysis_nodes c ON c.parent_id = n.id
           WHERE n.node_type = ? AND c.id IS NULL
           ORDER BY n.created_at DESC""",
        (node_type,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_node_tree(conn: sqlite3.Connection, node_id: str) -> list[dict]:
    """
    Traverse the ancestor chain for a node using recursive CTE.
    Returns nodes from root → current node.
    """
    rows = conn.execute(
        """WITH RECURSIVE ancestors(id, parent_id, created_at, node_type, lang,
              hypothesis, tickers, weights, prices_snapshot, quant_report,
              audio_file, is_canonical, data_hash, depth) AS (
            SELECT *, 0 FROM analysis_nodes WHERE id = ?
            UNION ALL
            SELECT n.*, a.depth + 1
            FROM analysis_nodes n
            JOIN ancestors a ON n.id = a.parent_id
        )
        SELECT id, parent_id, created_at, node_type, lang, hypothesis, tickers,
               weights, prices_snapshot, quant_report, audio_file, is_canonical,
               data_hash
        FROM ancestors
        ORDER BY depth DESC""",
        (node_id,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_children(conn: sqlite3.Connection, node_id: str) -> list[dict]:
    """Get all direct children of a node."""
    rows = conn.execute(
        "SELECT * FROM analysis_nodes WHERE parent_id = ? ORDER BY created_at ASC",
        (node_id,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def promote_to_canonical(conn: sqlite3.Connection, node_id: str) -> bool:
    """
    Mark a node as the canonical (blessed) version.
    Demotes any existing canonical node of the same type+lang.
    """
    node = get_node(conn, node_id)
    if not node:
        return False
    
    # Demote existing canonical nodes for same type+lang
    conn.execute(
        """UPDATE analysis_nodes SET is_canonical = 0
           WHERE node_type = ? AND lang = ? AND is_canonical = 1""",
        (node["node_type"], node["lang"])
    )
    
    # Promote the target node
    conn.execute(
        "UPDATE analysis_nodes SET is_canonical = 1 WHERE id = ?",
        (node_id,)
    )
    conn.commit()
    logger.info(f"Promoted node {node_id} to canonical for {node['node_type']}/{node['lang']}")
    return True


def update_audio_file(conn: sqlite3.Connection, node_id: str, audio_file: str) -> bool:
    """Update the audio_file field for a node (only this field is mutable, for lazy audio gen)."""
    result = conn.execute(
        "UPDATE analysis_nodes SET audio_file = ? WHERE id = ?",
        (audio_file, node_id)
    )
    conn.commit()
    return result.rowcount > 0


def get_nodes_by_freshness(
    conn: sqlite3.Connection,
    node_type: str,
    lang: str,
    max_age_hours: float
) -> list[dict]:
    """Get nodes within a time window (max_age_hours from now)."""
    cutoff = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        """SELECT * FROM analysis_nodes
           WHERE node_type = ? AND lang = ?
             AND datetime(created_at) >= datetime(?, '-' || ? || ' hours')
           ORDER BY created_at DESC""",
        (node_type, lang, cutoff, str(max_age_hours))
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_available_sectors(conn: sqlite3.Connection, lang: str) -> list[dict]:
    """
    Get a summary of all available sector types with their latest node metadata.
    Returns a list of dicts with node_type, latest created_at, ticker_count, is_canonical.
    """
    rows = conn.execute(
        """SELECT node_type, 
                  MAX(created_at) as latest_created_at,
                  COUNT(*) as total_nodes
           FROM analysis_nodes
           WHERE lang = ?
           GROUP BY node_type
           ORDER BY node_type""",
        (lang,)
    ).fetchall()
    
    results = []
    for row in rows:
        d = dict(row)
        # Get the latest node to extract ticker count
        latest = get_latest_node(conn, d["node_type"], lang)
        if latest:
            d["ticker_count"] = len(latest.get("tickers", []))
            d["is_canonical"] = bool(latest.get("is_canonical", 0))
            d["latest_hypothesis"] = latest.get("hypothesis", "")[:100]
        results.append(d)
    
    return results


def count_nodes(conn: sqlite3.Connection) -> int:
    """Count total nodes in the DAG."""
    row = conn.execute("SELECT COUNT(*) as cnt FROM analysis_nodes").fetchone()
    return row["cnt"] if row else 0
