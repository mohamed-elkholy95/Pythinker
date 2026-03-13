---
name: memory-system
description: Hybrid retrieval memory architecture — MongoDB document storage, Qdrant vector search with named vectors, BM25 sparse search, RRF fusion
---

# Memory System Skill

## When to Use
When working with the memory/knowledge storage system, vector search, or embedding code.

## Architecture

### Dual-Store Design
- **MongoDB**: Document storage, sync state tracking
- **Qdrant**: Vector search with named vectors (`dense` + `sparse`)

### Named-Vector Schema
- `dense`: OpenAI `text-embedding-3-small` (1536 dimensions)
- `sparse`: BM25 keyword vectors via `rank-bm25` library
- Primary collection: `user_knowledge`

### Hybrid Search (RRF)
1. Dense semantic search → ranked results
2. Sparse BM25 keyword search → ranked results
3. Reciprocal Rank Fusion combines both lists

### Sync State Tracking
MongoDB fields: `sync_state` (pending/synced/failed), `sync_attempts`, `last_sync_attempt`, `sync_error`

### Feature Flags
- `qdrant_use_hybrid_search: bool = True`
- `qdrant_sparse_vector_enabled: bool = True`
- `qdrant_user_knowledge_collection: str = "user_knowledge"`

## Key Files
- `backend/app/domain/services/embeddings/` — Embedding generation
- `backend/app/domain/services/embeddings/bm25_encoder.py` — BM25 sparse vectors
- `backend/app/infrastructure/repositories/qdrant_memory_repository.py` — Qdrant adapter
- `backend/app/infrastructure/repositories/mongodb_memory_repository.py` — MongoDB adapter

## Usage Patterns
```python
# Store with hybrid vectors
await memory_service.store_memory(user_id="...", content="...", generate_embedding=True)

# Hybrid search
results = await repo.search_hybrid(user_id="...", query_text="...", dense_vector=vec, sparse_vector=bm25)
```
