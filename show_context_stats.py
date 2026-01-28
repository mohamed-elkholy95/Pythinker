#!/usr/bin/env python3
"""Display sandbox context statistics"""
import json
import sys

with open('/app/sandbox_context.json') as f:
    data = json.load(f)

print("Context Metadata:")
print(f"  Version: {data['version']}")
print(f"  Generated: {data['generated_at']}")
print(f"  Checksum: {data['checksum']}")
print(f"  Python packages: {data['environment']['python'].get('package_count', 0)}")
print(f"  Node packages: {data['environment']['nodejs'].get('package_count', 0)}")
print(f"  Python version: {data['environment']['python']['version']}")
print(f"  Node version: {data['environment']['nodejs']['version']}")
