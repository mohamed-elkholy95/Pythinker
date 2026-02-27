# Screenshot Vectorization Design

## Overview

Visual memory for agent sessions: embed CDP screenshots as vectors in Qdrant so the agent can semantically search its visual history ("find the page where the form had a red error banner").

## Architecture

```
CDP Screenshot → Thumbnail → CLIP Embedding → Qdrant (screenshot_vectors collection)
                                                  ↑
                                          Agent query: "error page" → CLIP text encoder → vector search
```

## Pipeline

### 1. Capture (Already Implemented)
- CDP screencast frames captured via `MinIOStorage.store_screenshot()`
- Thumbnails generated and stored in `thumbnails` bucket
- Metadata in `ScreenshotDocument` (MongoDB)

### 2. Embedding (New)
- **Model**: OpenAI CLIP (`ViT-B/32`) or SigLIP via `open_clip` library
  - Image: 512-dim vector from image encoder
  - Text: 512-dim vector from text encoder (for query-time)
- **Self-hosted**: Runs on CPU (4GB VRAM insufficient for GPU CLIP + Chrome)
- **Batch processing**: Embed on capture (async background task)
- **Fallback**: Skip vectorization if embedding fails (graceful degradation)

### 3. Storage (Qdrant)
```python
# New collection: screenshot_vectors
# Named vector: "clip" (512 dimensions, cosine similarity)
CLIP_VECTOR_CONFIG = models.VectorParams(
    size=512,
    distance=models.Distance.COSINE,
)

# Payload fields
{
    "session_id": str,
    "screenshot_id": str,
    "minio_key": str,        # For retrieval
    "timestamp": str,
    "url": str | None,       # Page URL at capture time
    "tool_name": str | None, # Tool that triggered capture
}
```

### 4. Query Interface
```python
# Agent tool: search_visual_history
async def search_visual_history(
    session_id: str,
    query: str,      # Natural language: "login form", "error message"
    limit: int = 5,
) -> list[ScreenshotMatch]:
    # Encode query text with CLIP text encoder
    text_vector = clip_model.encode_text(query)
    # Search Qdrant
    results = await qdrant.search(
        collection_name="screenshot_vectors",
        query_vector=("clip", text_vector),
        query_filter=Filter(must=[
            FieldCondition(key="session_id", match=MatchValue(value=session_id)),
        ]),
        limit=limit,
    )
    return [ScreenshotMatch(score=r.score, url=r.payload["url"], ...) for r in results]
```

## Configuration

```bash
# Feature flag (disabled by default — requires CLIP model download)
SCREENSHOT_VECTORIZATION_ENABLED=false
# CLIP model selection
CLIP_MODEL_NAME=ViT-B-32
CLIP_PRETRAINED=openai
# Embedding batch size (process N screenshots per cycle)
CLIP_BATCH_SIZE=8
```

## Resource Considerations

- **CPU inference**: ~50ms per image on modern CPU (batch of 8: ~200ms)
- **Memory**: CLIP ViT-B/32 model: ~350MB RAM
- **Storage**: 512 floats × 4 bytes = 2KB per screenshot vector
- **At 1000 screenshots/session**: ~2MB vector storage per session

## Implementation Phases

1. **Phase A**: CLIP model loader + image embedding function
2. **Phase B**: Qdrant collection setup + background embedding task
3. **Phase C**: `search_visual_history` agent tool
4. **Phase D**: Auto-cleanup (delete vectors when session screenshots are purged)

## Dependencies

```
open-clip-torch>=2.24.0  # CLIP model (CPU-only, no CUDA needed)
```

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| OpenAI CLIP API | No local model | Cost, latency, privacy |
| SigLIP (Google) | Better zero-shot | Larger model (~800MB) |
| Local ViT-B/32 | Fast, free, private | 350MB RAM overhead |
| OCR + text search | No model needed | Misses visual layout info |

**Decision**: Local ViT-B/32 — best balance of quality, cost (free), and privacy for self-hosted deployments.
