# Research Report: Agent Memory Design

## Summary

This architecture improves retrieval quality and context discipline [1][2].

## Recommendation Matrix

| Component | Choice | Why |
|---|---|---|
| Vector DB | **Qdrant** | Fast ANN retrieval with filtering [1] |
| API | [FastAPI](https://fastapi.tiangolo.com/) | Async-first service layer [2] |

## References

1. Qdrant docs — https://qdrant.tech/documentation/
2. FastAPI docs — https://fastapi.tiangolo.com/
