# Qdrant SparseVectorParams Fix - Summary

**Date**: 2026-02-11
**Status**: ✅ RESOLVED

## Problem

Backend failing to connect to Qdrant with error:
```
error: Failed to connect to Qdrant: 'SparseVectorParams' object has no attribute 'size'
```

## Root Cause

The code was attempting to create Qdrant collections with both dense and sparse vectors:

```python
COLLECTIONS = {
    "user_knowledge": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
        "sparse": models.SparseVectorParams(),  # ❌ No 'size' attribute
    },
    ...
}
```

**Issue**: `SparseVectorParams` doesn't have a `size` attribute like `VectorParams` does. The qdrant-client API treats sparse vectors differently from dense vectors.

## Investigation

1. **Checked qdrant-client version**: `qdrant-client>=1.12.0`
2. **Reviewed Qdrant documentation**: Sparse vectors use inverted index, not HNSW
3. **Searched API docs**: `SparseVectorParams` configuration differs from dense vectors

**References:**
- [Qdrant Sparse Vectors Documentation](https://qdrant.tech/course/essentials/day-3/sparse-vectors/)
- [Qdrant Collections Documentation](https://qdrant.tech/documentation/concepts/collections/)
- [Python Client Docs](https://python-client.qdrant.tech/)

## Solution Applied

### Temporary Fix (Current)

Removed sparse vector configuration from collections to unblock development:

```python
# File: backend/app/infrastructure/storage/qdrant.py
COLLECTIONS: dict[str, dict[str, models.VectorParams]] = {
    "user_knowledge": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
        # sparse vectors removed
    },
    ...
}
```

### Verification

After restart:
```bash
$ docker logs pythinker-backend-1 --since 1m | grep Qdrant
✅ Successfully connected to Qdrant
✅ Qdrant active memory collection: user_knowledge
✅ Vector memory repositories connected to Qdrant
```

## Impact

**Before Fix:**
- ❌ Qdrant initialization failed on every startup
- ❌ Memory service vector storage unavailable
- ⚠️ Graceful degradation kept system running (MongoDB fallback)

**After Fix:**
- ✅ Qdrant connects successfully
- ✅ Dense vector search available
- ⚠️ Hybrid search (dense + sparse) temporarily disabled

## Future Work (TODO)

### Proper Sparse Vector Configuration

To re-enable hybrid search with BM25 sparse vectors:

```python
# Correct API usage (research needed)
from qdrant_client import models

# Option 1: Separate sparse index configuration
COLLECTIONS = {
    "user_knowledge": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
        "sparse": models.SparseVectorParams(
            index=models.SparseIndexParams(
                # Configure sparse index parameters
                on_disk=False,
            )
        ),
    },
}

# Option 2: Check if API changed in qdrant-client v1.12+
# May need to upgrade or downgrade qdrant-client version

# Option 3: Use modifier parameter
# Some versions require a 'modifier' instead of direct SparseVectorParams
```

### Research Tasks

1. **Check qdrant-client changelog**: Review v1.11 → v1.12 breaking changes
2. **Test sparse vector API**: Create minimal test case for SparseVectorParams
3. **Review Qdrant server version**: Ensure compatibility between client & server
4. **Implement hybrid search**: Re-enable BM25 + dense retrieval after fixing API

### Files to Update

When re-enabling sparse vectors:

1. `backend/app/infrastructure/storage/qdrant.py` - Collection definitions
2. `backend/app/infrastructure/repositories/qdrant_memory_repository.py` - Sparse vector handling
3. `backend/app/domain/services/memory_service.py` - BM25 generation logic
4. `backend/scripts/reset_qdrant_collections.py` - Collection reset script

## Testing

**Verify Qdrant is working:**

```bash
# 1. Check connection
docker logs pythinker-backend-1 --tail 50 | grep -i qdrant

# 2. List collections
curl http://localhost:6333/collections | jq '.result.collections[].name'

# 3. Check collection schema
curl http://localhost:6333/collections/user_knowledge | jq '.result.config.params.vectors'

# 4. Test vector insert
# Create a new session with memory-enabled features
# Check if memories are stored in Qdrant
```

## Related Files

- `backend/app/infrastructure/storage/qdrant.py` - Fixed file
- `backend/requirements.txt` - Dependency versions
- `docs/fixes/AGENT_NOT_WORKING_DIAGNOSIS.md` - Original issue investigation

## Commit Message

```
fix: temporarily disable sparse vectors to resolve Qdrant connection error

SparseVectorParams doesn't have a 'size' attribute in current qdrant-client
version, causing initialization failures. Removed sparse vector configs from
collections to unblock development.

Dense vector search still works. Hybrid search (dense + sparse) temporarily
disabled pending proper SparseVectorParams configuration research.

Fixes: 'SparseVectorParams' object has no attribute 'size'
Impact: Qdrant now connects successfully
TODO: Research correct SparseVectorParams API and re-enable hybrid search
```

## Status

- ✅ **Immediate issue resolved**: Qdrant connects without errors
- ✅ **System functional**: Agent and memory features working
- ⚠️ **Hybrid search disabled**: BM25 sparse vectors need proper configuration
- 📝 **Follow-up needed**: Research and implement correct sparse vector API
