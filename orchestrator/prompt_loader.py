"""Robust prompt loading with retry on missing file.

Hardens against the bind-mount startup race observed on
``thesis-orchestrator`` (videomaker), where ``/app/agents`` (overlay mount
from ``kola-team/agents``) may not be visible to the container during the
first second of process boot. Without retry, a single ``stat`` miss bubbles
up as ``FileNotFoundError`` and crashes the orchestrator on import of any
role module that calls ``_load_prompt()``.

The helper is intentionally tiny and dependency-free; it is imported at
module top level by role files.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_ATTEMPTS = 5
DEFAULT_DELAY_S = 2.0


def _safe_listdir(p: Path) -> list[str]:
    try:
        return sorted(os.listdir(p))[:50]
    except OSError as e:
        return [f"<listdir failed: {e!r}>"]


def _diagnostic(role: str, path: Path, team_root: Path) -> str:
    agents_dir = path.parent
    return (
        f"prompt manquant pour le role {role!r}\n"
        f"  expected path : {path}\n"
        f"  TEAM_ROOT     : {team_root}\n"
        f"  agents_dir    : {agents_dir} (exists={agents_dir.exists()})\n"
        f"  listing       : {_safe_listdir(agents_dir) if agents_dir.exists() else '<missing>'}"
    )


def load_prompt_with_retry(
    role: str,
    path: Path,
    team_root: Path,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay_s: float = DEFAULT_DELAY_S,
    fallback: str | None = None,
    sleep=time.sleep,
) -> str:
    """Read ``path`` with retry-on-missing.

    Returns the file content as soon as it is visible. If ``attempts`` pass
    without success, returns ``fallback`` when provided, otherwise raises a
    diagnostic ``FileNotFoundError``.
    """
    for i in range(1, attempts + 1):
        if path.exists():
            if i > 1:
                log.info("prompt %s loaded on attempt %d/%d", role, i, attempts)
            return path.read_text()
        if i < attempts:
            log.warning(
                "prompt %s missing at %s (attempt %d/%d), retrying in %.1fs",
                role, path, i, attempts, delay_s,
            )
            sleep(delay_s)

    diag = _diagnostic(role, path, team_root)
    if fallback is not None:
        log.error("prompt %s never appeared after %d attempts; using fallback\n%s",
                  role, attempts, diag)
        return fallback
    raise FileNotFoundError(diag)
