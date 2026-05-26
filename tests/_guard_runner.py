"""
tests/_guard_runner.py

Thin shim that extracts and runs ONLY _validate_environment() from main.py,
without importing FastAPI, uvicorn, DAG store, or any other heavy module.

This script is invoked by test_startup_guard.py via subprocess.run().
Exit code mirrors what _validate_environment() would cause:
  0  = guard passed
  1  = guard detected a fatal misconfiguration
  2  = internal shim error (guard could not be loaded)
"""

import os
import sys
import ast
import pathlib
import logging

REPO_ROOT = pathlib.Path(os.environ.get("REPO_ROOT", pathlib.Path(__file__).parent.parent))
MAIN_PY = REPO_ROOT / "main.py"

if not MAIN_PY.exists():
    print(f"[SHIM ERROR] main.py not found at {MAIN_PY}", file=sys.stderr)
    sys.exit(2)

# ── Parse main.py AST to extract _validate_environment source lines ─────────
src = MAIN_PY.read_text()
lines = src.splitlines(keepends=True)

tree = ast.parse(src)
fn_node = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_validate_environment":
        fn_node = node
        break

if fn_node is None:
    print("[SHIM ERROR] _validate_environment not found in main.py", file=sys.stderr)
    sys.exit(2)

fn_src = "".join(lines[fn_node.lineno - 1 : fn_node.end_lineno])

# ── Build minimal executable: imports + function + call ─────────────────────
minimal_module = (
    "import os\n"
    "import sys\n"
    "import urllib.parse\n"
    "import urllib.request\n"
    "import logging\n"
    "logger = logging.getLogger('guard_test')\n"
    "\n"
    + fn_src
    + "\n"
    "_validate_environment()\n"
)

# ── Run it in this process's namespace ──────────────────────────────────────
exec(compile(minimal_module, str(MAIN_PY), "exec"), {"__name__": "__main__"})
