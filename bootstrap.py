#!/usr/bin/env python3
"""One-time bootstrap. Run this once after cloning:

    python3 bootstrap.py

Creates .venv and installs the project + dev dependencies. After this, all
workflows go through run.py (cross-platform — same commands on macOS, Linux,
and Windows, no venv activation required):

    python run.py setup     # re-sync deps
    python run.py dev       # run the API with reload
    python run.py test      # run the test suite
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

    print()
    print("Done. Next steps:")
    print("  python run.py dev     # run uvicorn with reload")
    print("  python run.py test    # run pytest")
    print("  python run.py setup   # re-install dependencies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
