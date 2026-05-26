"""Researcher Agent — Handles scheduled daily and weekly research batches.

This agent monitors the time and triggers full research cycles based on the
configured schedule (Daily 02:00 UTC, Weekly Sunday 04:00 UTC).
It persists its state in the research.db scheduler_metadata table.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, time
from core.auto_research import run_full_research_cycle
from core.dag_store import _get_connection, get_metadata, set_metadata, init_db
from ..audit import log_event
from ..config import role

log = logging.getLogger(__name__)

# Schedule configuration
DAILY_BATCH_TIME = time(2, 0)      # 02:00 UTC
WEEKLY_BATCH_TIME = time(4, 0)     # 04:00 UTC
WEEKLY_BATCH_DAY = 6               # Sunday (0=Monday, 6=Sunday)


class ResearcherAgent:
    def __init__(self, gh=None) -> None:
        # gh is passed for consistency with other roles, though not used here yet
        self.gh = gh
        self.role = role("researcher")
        init_db()  # Ensure database and metadata tables exist

    async def heartbeat(self) -> None:
        """Called by the orchestrator loop. Checks if any batch needs to run."""
        now = datetime.now(timezone.utc)
        
        # 1. Daily Batch
        if self._should_run_daily(now):
            await self._run_daily()
            
        # 2. Weekly Batch (Deep Audit)
        if self._should_run_weekly(now):
            await self._run_weekly()

    def _should_run_daily(self, now: datetime) -> bool:
        """Returns True if a daily batch should be triggered now."""
        # Check if it's already the scheduled time (or later) for today
        if now.time() < DAILY_BATCH_TIME:
            return False
            
        conn = _get_connection()
        try:
            last_run_str = get_metadata(conn, "last_daily_run")
            if not last_run_str:
                return True
            
            last_run = datetime.fromisoformat(last_run_str)
            # Run if the last daily run was on a previous day
            return last_run.date() < now.date()
        finally:
            conn.close()

    def _should_run_weekly(self, now: datetime) -> bool:
        """Returns True if a weekly deep audit should be triggered now."""
        # Must be Sunday
        if now.weekday() != WEEKLY_BATCH_DAY:
            return False
            
        # Must be at or after the scheduled weekly time
        if now.time() < WEEKLY_BATCH_TIME:
            return False
            
        conn = _get_connection()
        try:
            last_run_str = get_metadata(conn, "last_weekly_run")
            if not last_run_str:
                return True
            
            last_run = datetime.fromisoformat(last_run_str)
            # Run if last weekly run was more than 6 days ago
            # (Ensures we don't run multiple times on the same Sunday if restarted)
            return (now - last_run).days >= 6
        finally:
            conn.close()

    async def _run_daily(self) -> None:
        """Executes a standard daily research cycle."""
        log.info("ResearcherAgent: Starting Daily Research Batch...")
        await log_event("researcher", "daily-batch-start")
        try:
            # Standard cycle: adversarial review only if failing
            results = await run_full_research_cycle(lang="fr")
            
            conn = _get_connection()
            try:
                set_metadata(conn, "last_daily_run", datetime.now(timezone.utc).isoformat())
            finally:
                conn.close()
                
            await log_event("researcher", "daily-batch-success", sectors=list(results.keys()))
            log.info(f"ResearcherAgent: Daily Batch complete. Canonical nodes: {len(results)}")
        except Exception as e:
            log.exception("ResearcherAgent: Daily Research Batch failed")
            await log_event("researcher", "daily-batch-fail", error=str(e))

    async def _run_weekly(self) -> None:
        """Executes a deep audit research cycle (forced adversarial review)."""
        log.info("ResearcherAgent: Starting Weekly Deep Audit Batch...")
        await log_event("researcher", "weekly-batch-start")
        try:
            # Deep Audit: force adversarial review on all sectors
            results = await run_full_research_cycle(lang="fr", force_adversarial=True)
            
            conn = _get_connection()
            try:
                set_metadata(conn, "last_weekly_run", datetime.now(timezone.utc).isoformat())
            finally:
                conn.close()
                
            await log_event("researcher", "weekly-batch-success", sectors=list(results.keys()))
            log.info(f"ResearcherAgent: Weekly Deep Audit complete. Canonical nodes: {len(results)}")
        except Exception as e:
            log.exception("ResearcherAgent: Weekly Research Batch failed")
            await log_event("researcher", "weekly-batch-fail", error=str(e))
