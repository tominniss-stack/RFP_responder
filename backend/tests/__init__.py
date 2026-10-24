"""Backend unit and integration tests."""

import sys
from pathlib import Path

# Ensure backend root is always on sys.path for both pytest and unittest runners
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
