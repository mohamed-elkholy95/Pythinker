#!/usr/bin/env python3
"""Test SparseVectorParams creation."""

import traceback

from qdrant_client import models

try:
    vectors_config = {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
        "sparse": models.SparseVectorParams(),
    }
    print("✅ vectors_config created successfully")
    print(f"dense: {vectors_config['dense']}")
    print(f"sparse: {vectors_config['sparse']}")
    print(f"sparse hasattr 'size': {hasattr(vectors_config['sparse'], 'size')}")
except Exception as exc:
    print(f"Error: {exc}")
    print("❌ Error creating vectors_config:")
    traceback.print_exc()
