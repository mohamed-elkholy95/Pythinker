#!/usr/bin/env python3
"""Check Qdrant collection vector configuration."""

import requests

response = requests.get("http://qdrant:6333/collections/user_knowledge", timeout=10)
response.raise_for_status()
data = response.json()

vectors_config = data["result"]["config"]["params"]["vectors"]
sparse_vectors_config = data["result"]["config"]["params"].get("sparse_vectors")


if isinstance(vectors_config, dict):
    for _name, _config in vectors_config.items():
        pass
else:
    pass

if sparse_vectors_config:
    for _name, _config in sparse_vectors_config.items():
        pass
else:
    pass
