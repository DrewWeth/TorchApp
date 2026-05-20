#!/usr/bin/env python3
"""Cross-platform task runner. Replaces taskipy so the same commands work on
macOS, Linux, and Windows without activating the venv.

Usage:
    python3 run.py setup         # re-install project + dev dependencies
    python3 run.py dev           # uvicorn with --reload on :8000
    python3 run.py test          # pytest
    python3 run.py docker:build  # build the torch-events image
    python3 run.py docker:run    # run the image, bind-mounting the repo at /db

Python tasks resolve the venv's python (.venv/bin/python on POSIX,
.venv\\Scripts\\python.exe on Windows) and dispatch `python -m <module>`.
Docker tasks shell out to the docker CLI on PATH.
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

IMAGE = "torch-events"

# First element "@py" is a sentinel for "the project's venv python".
TASKS = {
    "setup": ["@py", "-m", "pip", "install", "-e", ".[dev]"],
    "dev": ["@py", "-m", "uvicorn", "app.main:app", "--reload"],
    "test": ["@py", "-m", "pytest"],
    "docker:build": ["docker", "build", "-t", IMAGE, "."],
    "docker:run": [
        "docker", "run", "--rm",
        "-p", "8000:8000",
        "-v", f"{ROOT}:/db",
        IMAGE,
    ],
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in TASKS:
        print(f"usage: python3 run.py [{' | '.join(TASKS)}] [extra args...]")
        return 2

    task = TASKS[argv[1]]
    if task[0] == "@py":
        if not PY.exists():
            print(
                f"venv python not found at {PY}.\n"
                "Run `python3 bootstrap.py` first.",
                file=sys.stderr,
            )
            return 1
        cmd = [str(PY), *task[1:], *argv[2:]]
    else:
        cmd = [*task, *argv[2:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
