from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

DATA_DIR.mkdir(parents=True, exist_ok=True)
