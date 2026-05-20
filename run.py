#!/usr/bin/env python3
"""Cross-platform task runner. Replaces taskipy so the same commands work on
macOS, Linux, and Windows without activating the venv.

Usage:
    python3 run.py setup      # re-install project + dev dependencies
    python3 run.py dev        # uvicorn with --reload on :8000
    python3 run.py test       # pytest

Each task resolves the venv's python (.venv/bin/python on POSIX,
.venv\\Scripts\\python.exe on Windows) and dispatches `python -m <module>`.
Extra args after the task name are forwarded, e.g.:

    python3 run.py test -k entity -v
    python3 run.py dev --port 9000
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
VENV = ROOT / ".venv"
IS_WINDOWS = os.name == "nt"
PY = VENV / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")

TASKS = {
    "setup": ["-m", "pip", "install", "-e", ".[dev]"],
    "dev": ["-m", "uvicorn", "app.main:app", "--reload"],
    "test": ["-m", "pytest"],
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in TASKS:
        print(f"usage: python3 run.py [{' | '.join(TASKS)}] [extra args...]")
        return 2

    if not PY.exists():
        print(
            f"venv python not found at {PY}.\n"
            "Run `python3 bootstrap.py` first.",
            file=sys.stderr,
        )
        return 1

    cmd = [str(PY), *TASKS[argv[1]], *argv[2:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
