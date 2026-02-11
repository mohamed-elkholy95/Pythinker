#!/usr/bin/env python3
"""Test VectorsConfig class."""

import inspect

from qdrant_client import AsyncQdrantClient, models

# Check what's available in models
print("Checking for VectorsConfig...")
if hasattr(models, "VectorsConfig"):
    print("✅ VectorsConfig exists")
    print(f"Signature: {inspect.signature(models.VectorsConfig)}")
else:
    print("❌ VectorsConfig not found")

# List all classes starting with 'Vector'
vector_classes = [name for name in dir(models) if name.startswith("Vector")]
print(f"\nAvailable Vector* classes: {vector_classes}")

# Check for named vector support
if hasattr(models, "VectorParamsMap"):
    print("✅ VectorParamsMap exists")
elif hasattr(models, "NamedVectors"):
    print("✅ NamedVectors exists")

# Try to see what create_collection expects
try:
    sig = inspect.signature(AsyncQdrantClient.create_collection)
    print("\ncreate_collection signature:")
    for param_name, param in sig.parameters.items():
        if "vector" in param_name.lower():
            print(f"  {param_name}: {param.annotation}")
except Exception as e:
    print(f"Error inspecting: {e}")
