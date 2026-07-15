from __future__ import annotations

import os
import sys
from pathlib import Path


# Tests import the backend package as `app.*`. Ensure `backend/` is on sys.path
# regardless of the working directory pytest is invoked from.
backend_dir = Path(__file__).resolve().parents[1]
backend_str = str(backend_dir)
if backend_str not in sys.path:
    sys.path.insert(0, backend_str)

# Default to an in-memory SQLite database for unit tests so importing `app.*`
# doesn't require external drivers (e.g., psycopg2).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "unit-test-secret-key")
os.environ.setdefault("ALLOW_INSECURE_DEV", "1")
