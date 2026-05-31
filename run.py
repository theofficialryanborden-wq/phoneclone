#!/usr/bin/env python3
"""PhoneClone launcher."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from phoneclone.main import run

if __name__ == "__main__":
    raise SystemExit(run())
