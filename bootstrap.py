#!/usr/bin/env python3
"""One-time bootstrap. Run this once after cloning:

    python3 bootstrap.py

Creates .venv, installs the project + dev dependencies (including taskipy).
After this, all workflows go through taskipy:

    .venv/bin/task setup    # re-sync deps
    .venv/bin/task dev      # run the API with reload
    .venv/bin/task test     # run the test suite

Cross-platform: uses the stdlib `venv` module and resolves the venv's
python/task binaries correctly on Windows and POSIX.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
VENV_DIR = ROOT / ".venv"
IS_WINDOWS = os.name == "nt"
BIN = VENV_DIR / ("Scripts" if IS_WINDOWS else "bin")
PY = BIN / ("python.exe" if IS_WINDOWS else "python")


def main() -> int:
    if not VENV_DIR.exists():
        print(f"Creating virtual environment in {VENV_DIR} ...")
        venv.create(VENV_DIR, with_pip=True, upgrade_deps=False)

    print("Upgrading pip ...")
    subprocess.check_call([str(PY), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])

    print("Installing project and dev dependencies ...")
    subprocess.check_call([str(PY), "-m", "pip", "install", "--quiet", "-e", ".[dev]"])

    task_bin = BIN / ("task.exe" if IS_WINDOWS else "task")
    print()
    print("Done. Available tasks:")
    print(f"  {task_bin} setup   # re-install dependencies")
    print(f"  {task_bin} dev     # run uvicorn with reload")
    print(f"  {task_bin} test    # run pytest")
    print()
    print("Tip: `source .venv/bin/activate` then just `task <name>`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
