#!/usr/bin/env python3
"""Test SparseVectorParams creation."""

import traceback

from qdrant_client import models

try:
    vectors_config = {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
        "sparse": models.SparseVectorParams(),
    }
except Exception:
    traceback.print_exc()
