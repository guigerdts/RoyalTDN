"""Root conftest — ensures ``src/`` is on ``sys.path`` for test imports."""

import sys
from pathlib import Path

SRC = Path(__file__).parent / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
