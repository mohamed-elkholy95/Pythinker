# backend/tests/domain/services/langgraph/conftest.py
"""Conftest for langgraph tests.

This conftest ensures proper module resolution to avoid conflicts
with the installed langgraph package.
"""

import sys
from pathlib import Path

# Ensure the backend directory is at the front of sys.path
backend_path = Path(__file__).parent.parent.parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
