#!/usr/bin/env python3
"""Quick script to check Qdrant collection schema."""

import requests

response = requests.get("http://qdrant:6333/collections/user_knowledge", timeout=10)
response.raise_for_status()
data = response.json()

vectors = data["result"]["config"]["params"]["vectors"]

if isinstance(vectors, dict):
    for _name in vectors:
        pass
else:
    pass
