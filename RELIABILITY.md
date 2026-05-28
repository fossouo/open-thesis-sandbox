# Reliability — preventative hardening notes

## 2026-05-28 — bind-mount startup race on `thesis-orchestrator`

### Symptom (observed)

Container `thesis-orchestrator` (videomaker, docker-compose service in
`/home/fossod/talki-services/docker-compose.yml`) crash-looped with:

```
FileNotFoundError: backend prompt manquant : /app/agents/backend.md
```

at `orchestrator/roles/backend.py` `_load_prompt()`. By the time the
incident was diagnosed, the container had self-recovered (`RestartCount=0`,
healthy 5-min polling cycle), confirming the race-condition hypothesis
rather than a permanent missing-file bug.

### Root cause

`docker-compose.yml` stacks two bind mounts on the container's `/app`:

1. `/home/fossod/open-thesis-sandbox → /app` (rw, base)
2. `/home/fossod/kola-team/agents → /app/agents:ro` (overlay)

During container boot, there is a brief window where mount #2 is not yet
visible to the Python process started by the entrypoint. Any role module
that calls `_load_prompt()` at import time hits `path.exists() == False`
and raises, crashing the orchestrator. Docker restarts it, by which time
the overlay is ready, and the next boot succeeds.

The window is short enough that most boots succeed, but observed
`RestartCount=15` confirms it has fired in production.

### Fix (preventative, not reactive)

Closed the class permanently by routing all prompt loaders through a
single retry helper at
`orchestrator/prompt_loader.py::load_prompt_with_retry`:

- 5 attempts × 2s delay (configurable)
- logs each retry at WARNING
- on permanent miss, raises `FileNotFoundError` with full diagnostic
  (role, expected path, `TEAM_ROOT`, agents-dir existence, safe listing)
  — or returns a provided `fallback` string when the caller supplies one
  (used by `roles/triage.py` which already had an inline fallback prompt).

Callers patched:
- `orchestrator/roles/backend.py::_load_prompt` (raises on permanent miss)
- `orchestrator/roles/triage.py::_load_prompt` (falls back to inline prompt)

`roles/ceo.py` and `roles/researcher.py` do not load `.md` prompt files
and were not touched.

### Tests

`tests/test_prompt_loader.py`:

- `test_prompt_present_immediate_success` — happy path, no sleeps
- `test_prompt_appears_after_retry` — file materialises mid-retry
- `test_prompt_never_appears_raises` — diagnostic message contents
- `test_prompt_never_appears_with_fallback` — fallback path
- `test_all_role_prompts_load_with_current_mounts` — integration against
  the real on-disk `/app/agents/{backend,triage}.md`

All 5 passing on the container Python (`3.12.3`, pytest 9.0.3).

### Verification

```
docker restart thesis-orchestrator
sleep 15
docker inspect thesis-orchestrator --format \
  '{{.RestartCount}} {{.State.Status}} {{.State.ExitCode}}'
# → 0 running 0
```

Logs show the normal 5-min GitHub polling cycle resumed immediately.

### Non-changes

- `docker-compose.yml` was **not** modified. The mount-ordering issue is a
  Docker behaviour we cannot reorder portably; in-process retry is the
  durable fix.
- Prompt paths (`PROMPT_PATH = TEAM_ROOT / "agents" / "<role>.md"`) were
  preserved verbatim.
