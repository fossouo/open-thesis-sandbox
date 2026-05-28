"""Tests for ``orchestrator.prompt_loader``.

Covers the bind-mount startup race: a prompt file that is briefly missing
must be retried, and a permanently-missing file must produce a diagnostic
error (or a fallback when the caller provides one).
"""
from __future__ import annotations

import pytest
from pathlib import Path

from orchestrator.prompt_loader import load_prompt_with_retry


class _FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, s: float) -> None:
        self.calls.append(s)


def test_prompt_present_immediate_success(tmp_path: Path) -> None:
    p = tmp_path / "agents" / "backend.md"
    p.parent.mkdir()
    p.write_text("hello backend")
    sleep = _FakeSleep()

    out = load_prompt_with_retry("backend", p, tmp_path, sleep=sleep)

    assert out == "hello backend"
    assert sleep.calls == []  # no retries needed


def test_prompt_appears_after_retry(tmp_path: Path) -> None:
    p = tmp_path / "agents" / "backend.md"
    p.parent.mkdir()
    appear_after = 3  # show up before attempt 3

    class _SleepThenCreate:
        def __init__(self) -> None:
            self.calls: list[float] = []

        def __call__(self, s: float) -> None:
            self.calls.append(s)
            if len(self.calls) == appear_after - 1:
                p.write_text("late-arriving prompt")

    sleep = _SleepThenCreate()
    out = load_prompt_with_retry("backend", p, tmp_path, delay_s=0.01, sleep=sleep)

    assert out == "late-arriving prompt"
    assert len(sleep.calls) == appear_after - 1


def test_prompt_never_appears_raises(tmp_path: Path) -> None:
    p = tmp_path / "agents" / "backend.md"
    p.parent.mkdir()
    (p.parent / "ceo.md").write_text("x")  # sibling for listing diag
    sleep = _FakeSleep()

    with pytest.raises(FileNotFoundError) as exc:
        load_prompt_with_retry(
            "backend", p, tmp_path, attempts=3, delay_s=0.01, sleep=sleep,
        )

    msg = str(exc.value)
    assert "backend" in msg
    assert str(p) in msg
    assert str(tmp_path) in msg
    assert "ceo.md" in msg  # diagnostic listing
    assert len(sleep.calls) == 2  # attempts-1 sleeps


def test_prompt_never_appears_with_fallback(tmp_path: Path) -> None:
    p = tmp_path / "agents" / "triage.md"
    p.parent.mkdir()
    sleep = _FakeSleep()

    out = load_prompt_with_retry(
        "triage",
        p,
        tmp_path,
        attempts=2,
        delay_s=0.01,
        fallback="FALLBACK CONTENT",
        sleep=sleep,
    )

    assert out == "FALLBACK CONTENT"


def test_all_role_prompts_load_with_current_mounts() -> None:
    """Integration smoke: backend + triage prompts must load from the real
    ``/app/agents`` mount the container sees. Skips if the file isn't on the
    machine running the test (e.g. host dev shell)."""
    from orchestrator.config import TEAM_ROOT
    from orchestrator.roles import backend as backend_mod
    from orchestrator.roles import triage as triage_mod

    for mod, name in [(backend_mod, "backend"), (triage_mod, "triage")]:
        if not mod.PROMPT_PATH.exists():
            pytest.skip(f"{name}.md not present at {mod.PROMPT_PATH}")
        out = mod._load_prompt()
        assert out and len(out) > 10, f"{name} prompt too short: {out!r}"
