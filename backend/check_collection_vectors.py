#!/usr/bin/env python3
"""Check Qdrant collection vector configuration."""

import requests

response = requests.get("http://qdrant:6333/collections/user_knowledge", timeout=10)
response.raise_for_status()
data = response.json()

vectors_config = data["result"]["config"]["params"]["vectors"]
sparse_vectors_config = data["result"]["config"]["params"].get("sparse_vectors")

print("=" * 60)
print("user_knowledge collection configuration:")
print("=" * 60)

if isinstance(vectors_config, dict):
    print("\n✅ Named dense vectors found:")
    for name, config in vectors_config.items():
        print(f"  - {name}: size={config.get('size')}, distance={config.get('distance')}")
else:
    print("\n❌ Unnamed dense vector (legacy schema)")
    print(f"  size={vectors_config.get('size')}, distance={vectors_config.get('distance')}")

if sparse_vectors_config:
    print("\n✅ Sparse vectors found:")
    for name, config in sparse_vectors_config.items():
        print(f"  - {name}: {config}")
else:
    print("\n❌ No sparse vectors configured")

print(f"\nPoints count: {data['result']['points_count']}")
print("=" * 60)
