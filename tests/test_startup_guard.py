"""
tests/test_startup_guard.py

Unit tests for the _validate_environment() startup guard in main.py.

Strategy: invoke _validate_environment() via a thin helper script
(tests/_guard_runner.py) that imports only that function — without
triggering FastAPI / uvicorn / DAG module-level side effects.

Scenarios:
  1. LITELLM_URL missing          -> exit 1, "LITELLM_URL" in stderr
  2. http://localhost:8000/...    -> exit 1, self-loop message
  3. http://127.0.0.1:8000/...   -> exit 1, self-loop message
  4. http://xeon...:4000/...     -> exit 0 (guard accepts it)
"""

import os
import sys
import subprocess
import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent.resolve()
RUNNER_SCRIPT = pathlib.Path(__file__).parent / "_guard_runner.py"


def _run_guard(litellm_url):
    """Run _validate_environment() in isolation via _guard_runner.py."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(REPO_ROOT),
        "REPO_ROOT": str(REPO_ROOT),
    }
    if litellm_url is not None:
        env["LITELLM_URL"] = litellm_url

    return subprocess.run(
        [sys.executable, str(RUNNER_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


class TestStartupGuard:

    def test_missing_litellm_url_exits_nonzero(self):
        """When LITELLM_URL is not set, the guard must exit 1."""
        result = _run_guard(litellm_url=None)
        assert result.returncode != 0, (
            "Expected non-zero exit when LITELLM_URL is missing. "
            "stderr=" + result.stderr[:400]
        )
        combined = result.stderr + result.stdout
        assert "LITELLM_URL" in combined, (
            "Error should mention LITELLM_URL. Got: " + combined[:400]
        )

    def test_self_loop_localhost_8000_rejected(self):
        """http://localhost:8000/v1/... must be rejected with a self-loop error."""
        result = _run_guard("http://localhost:8000/v1/chat/completions")
        assert result.returncode != 0, (
            "Expected non-zero exit for localhost:8000. "
            "stderr=" + result.stderr[:400]
        )
        combined = result.stderr + result.stdout
        assert any(kw in combined for kw in ("self-loop", "boucle", "loop")), (
            "Error should mention self-loop. Got: " + combined[:400]
        )

    def test_self_loop_127_0_0_1_8000_rejected(self):
        """http://127.0.0.1:8000/... must also be rejected."""
        result = _run_guard("http://127.0.0.1:8000/v1/chat/completions")
        assert result.returncode != 0, (
            "Expected non-zero exit for 127.0.0.1:8000. "
            "stderr=" + result.stderr[:400]
        )
        combined = result.stderr + result.stdout
        assert any(kw in combined for kw in ("self-loop", "boucle", "loop")), (
            "Error should mention self-loop. Got: " + combined[:400]
        )

    def test_placeholder_host_rejected(self):
        """http://your-litellm-host/... must be rejected as a placeholder."""
        result = _run_guard("http://your-litellm-host:4000/v1/chat/completions")
        assert result.returncode != 0, (
            "Expected non-zero exit for placeholder host. "
            "stderr=" + result.stderr[:400]
        )
        combined = result.stderr + result.stdout
        assert "placeholder" in combined, (
            "Error should mention placeholder. Got: " + combined[:400]
        )

    def test_valid_external_url_accepted(self):
        """A valid non-local URL must pass all hard checks (exit 0)."""
        result = _run_guard(
            "http://inference-gateway.example.com:4000/v1/chat/completions"
        )
        assert result.returncode == 0, (
            "Expected exit 0 for a valid external LITELLM_URL. "
            "returncode=" + str(result.returncode) + " stderr=" + result.stderr[:400]
        )
