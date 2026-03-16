#!/usr/bin/env python3
"""Test VectorsConfig class."""

import inspect
from contextlib import suppress

from qdrant_client import AsyncQdrantClient, models

# Check what's available in models
if hasattr(models, "VectorsConfig"):
    pass
else:
    pass

# List all classes starting with 'Vector'
vector_classes = [name for name in dir(models) if name.startswith("Vector")]

# Check for named vector support
if hasattr(models, "VectorParamsMap") or hasattr(models, "NamedVectors"):
    pass

# Try to see what create_collection expects
with suppress(Exception):
    sig = inspect.signature(AsyncQdrantClient.create_collection)
    for param_name in sig.parameters:
        if "vector" in param_name.lower():
            pass
