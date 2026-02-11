# Phase 1 Migration Guide: Hybrid Retrieval Foundation

**Date**: February 11, 2026
**Status**: ✅ Complete
**Mode**: Development (aggressive changes, no backward compatibility)

---

## Overview

Phase 1 implements the foundation for production-grade memory retrieval:
- **Named-vector schema**: Qdrant collections with dense + sparse vectors
- **Hybrid search**: RRF fusion of semantic (OpenAI) + keyword (BM25) retrieval
- **Sync state tracking**: MongoDB fields for Phase 2 reliability infrastructure
- **Self-hosted stack**: BM25 runs locally via `rank-bm25`, zero external deps

---

## What Changed

### 1. Dependencies

**Added**: `rank-bm25>=0.2.2` in `backend/requirements.txt`

**Install**:
```bash
cd backend
pip install rank-bm25
```

### 2. Qdrant Schema (Breaking Change)

**Before** (single unnamed vector):
```python
{
    "user_knowledge": VectorParams(size=1536, distance=COSINE)
}
```

**After** (named dense + sparse):
```python
{
    "user_knowledge": {
        "dense": VectorParams(size=1536, distance=COSINE),
        "sparse": SparseVectorParams(modifier=IDF),
    }
}
```

**Migration**:
```bash
# Option 1: Drop and recreate (dev mode)
docker exec pythinker-qdrant-1 rm -rf /qdrant/storage
docker restart pythinker-qdrant-1

# Option 2: Use reset script
cd backend
conda activate pythinker
python scripts/reset_qdrant_collections.py
```

### 3. MongoDB Schema

**New fields in `MemoryEntry`**:
```python
# Sync state tracking (Phase 2 foundation)
sync_state: str = "pending"  # pending, synced, failed, dead_letter
sync_attempts: int = 0
last_sync_attempt: datetime | None = None
sync_error: str | None = None

# Embedding metadata
embedding_model: str | None = None  # "text-embedding-3-small"
embedding_provider: str | None = None  # "openai"
embedding_quality: float = 1.0  # 1.0 for API, 0.5 for fallback
```

**No migration needed**: New fields have defaults, existing documents work as-is.

### 4. New Modules

**Created**:
- `backend/app/domain/services/embeddings/__init__.py`
- `backend/app/domain/services/embeddings/bm25_encoder.py`
- `backend/tests/domain/services/test_bm25_encoder.py`
- `backend/tests/infrastructure/test_qdrant_hybrid_search.py`
- `backend/scripts/reset_qdrant_collections.py`

### 5. Modified Modules

**Infrastructure**:
- `backend/app/infrastructure/storage/qdrant.py` - Named-vector schema, optimizer config
- `backend/app/infrastructure/repositories/qdrant_memory_repository.py` - Hybrid search, sync tracking

**Domain**:
- `backend/app/domain/models/long_term_memory.py` - Sync state fields, embedding metadata
- `backend/app/domain/services/memory_service.py` - BM25 integration, sync state updates

**Config**:
- `backend/app/core/config.py` - Feature flags, collection defaults

**Docs**:
- `CLAUDE.md` - Memory system architecture section

---

## Configuration

### Feature Flags

**`backend/app/core/config.py`**:
```python
# Phase 1: Hybrid search
qdrant_use_hybrid_search: bool = True  # Enable RRF fusion
qdrant_sparse_vector_enabled: bool = True  # Generate BM25 vectors

# Collections
qdrant_user_knowledge_collection: str = "user_knowledge"  # Primary
qdrant_collection: str = "agent_memories"  # Legacy (deprecated)
```

### Environment Variables

**No new env vars required**. Existing config works:
```bash
QDRANT_URL=http://qdrant:6333
QDRANT_GRPC_PORT=6334
QDRANT_PREFER_GRPC=True
```

---

## Testing

### Unit Tests

**BM25 Encoder**:
```bash
cd backend
conda activate pythinker
pytest tests/domain/services/test_bm25_encoder.py -v
```

**Expected output**: 15+ tests passing (tokenization, encoding, scoring, batch operations)

### Integration Tests

**Hybrid Search**:
```bash
pytest tests/infrastructure/test_qdrant_hybrid_search.py -v
```

**Expected output**: 10+ tests passing (named vectors, RRF fusion, filtering)

### Manual Testing

**1. Reset Qdrant collections**:
```bash
python scripts/reset_qdrant_collections.py
```

**2. Start services**:
```bash
./dev.sh up -d
```

**3. Create test memory**:
```python
from app.domain.services.memory_service import MemoryService
from app.domain.models.long_term_memory import MemoryType, MemoryImportance

memory = await memory_service.store_memory(
    user_id="test-user",
    content="User prefers dark mode for all applications",
    memory_type=MemoryType.PREFERENCE,
    importance=MemoryImportance.HIGH,
    generate_embedding=True,
)

print(f"Sync state: {memory.sync_state}")  # Should be "synced"
print(f"Embedding model: {memory.embedding_model}")  # "text-embedding-3-small"
```

**4. Test hybrid search**:
```python
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
from app.domain.services.embeddings.bm25_encoder import get_bm25_encoder

repo = QdrantMemoryRepository()
encoder = get_bm25_encoder()

# Fit BM25 on corpus
encoder.fit(["User prefers dark mode for all applications"])

# Hybrid search
results = await repo.search_hybrid(
    user_id="test-user",
    query_text="dark theme settings",
    dense_vector=[...],  # From OpenAI API
    sparse_vector=encoder.encode("dark theme settings"),
    limit=10,
)

print(f"Found {len(results)} results")
```

---

## Validation Checklist

- [ ] `rank-bm25` installed in Python environment
- [ ] Qdrant collections recreated with named-vector schema
- [ ] BM25 encoder tests pass (15+ tests)
- [ ] Hybrid search tests pass (10+ tests)
- [ ] New memories have `sync_state="synced"` in MongoDB
- [ ] New memories have `embedding_model="text-embedding-3-small"`
- [ ] Qdrant points have both `dense` and `sparse` vectors
- [ ] Backend linting passes: `ruff check . && ruff format --check .`
- [ ] CLAUDE.md updated with memory system architecture

---

## Troubleshooting

### Issue: Qdrant schema mismatch error

**Symptom**: `VectorParamsDiff validation error` when upserting memories

**Solution**: Drop and recreate collections (dev mode):
```bash
docker exec pythinker-qdrant-1 rm -rf /qdrant/storage
docker restart pythinker-qdrant-1
python scripts/reset_qdrant_collections.py
```

### Issue: BM25 encoder returns empty dict

**Symptom**: `sparse_vector={}` in all upserts

**Solution**: BM25 not fitted yet. Fit on startup:
```python
from app.domain.services.embeddings.bm25_encoder import initialize_bm25_from_memories

await initialize_bm25_from_memories(memory_repository)
```

### Issue: Memories stuck in `sync_state="pending"`

**Symptom**: MongoDB shows pending, but Qdrant has no points

**Solution**: Check Qdrant logs for errors:
```bash
docker logs pythinker-qdrant-1
```

Common causes:
- Qdrant not running
- Schema mismatch (recreate collections)
- Network issues (check `qdrant_url` config)

### Issue: Hybrid search returns no results

**Symptom**: `search_hybrid()` returns empty list

**Solution**: Verify:
1. BM25 encoder is fitted: `encoder.bm25 is not None`
2. Qdrant has points: `await repo.get_memory_count(user_id)`
3. Query vectors are correct dimensions (dense=1536, sparse=top-100)

---

## Next Steps (Phase 2+)

Phase 1 complete! Ready for:

**Phase 2** (Sync Reliability): Outbox pattern, reconciliation, retry workers
**Phase 3** (Retrieval Quality): Reranking, MMR diversification, flow wiring
**Phase 4** (Grounding Safety): Evidence blocks, contradiction resolver, CoVe integration
**Phase 5** (Long Context): Pressure-aware budgeting, incremental checkpoints
**Phase 6** (Ops): Monitoring dashboards, semantic cache rollout

---

## References

- **Plan**: `/qdrant_plan.md` (full implementation plan)
- **Architecture**: `CLAUDE.md` (memory system patterns)
- **Tests**: `tests/domain/services/test_bm25_encoder.py`, `tests/infrastructure/test_qdrant_hybrid_search.py`
- **BM25 Library**: https://github.com/dorianbrown/rank_bm25
- **Qdrant Docs**: https://qdrant.tech/documentation/concepts/hybrid-queries/
