#!/usr/bin/env python
"""Export prompt optimization dataset from MongoDB session events.

Usage:
    conda activate pythinker
    cd backend
    python scripts/export_prompt_optimization_dataset.py \
        --output /tmp/opt_dataset.json \
        [--max-sessions 500] \
        [--min-quality 0.0]

The exported JSON is compatible with the curated dataset schema and can be
merged with ``tests/evals/datasets/prompt_optimization_cases.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import pathlib
import sys

# Add backend to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_export(output_path: pathlib.Path, max_sessions: int, min_quality: float) -> None:
    """Run the dataset export."""
    from app.domain.services.prompt_optimization.dataset_builder import DatasetBuilder
    from app.infrastructure.models.documents import SessionDocument
    from app.infrastructure.storage.mongodb import get_mongodb, initialize_beanie

    await get_mongodb().initialize()
    await initialize_beanie([SessionDocument])

    logger.info("Fetching up to %d completed sessions from MongoDB...", max_sessions)
    sessions = (
        await SessionDocument.find({"status": "completed"})
        .sort(-SessionDocument.created_at)
        .limit(max_sessions)
        .to_list()
    )
    logger.info("Fetched %d sessions.", len(sessions))

    # Extract raw event lists from each session
    all_session_events: list[list[dict]] = []
    for session in sessions:
        events_raw = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in session.events]
        all_session_events.append(events_raw)

    builder = DatasetBuilder()
    cases = builder.build_from_sessions(all_session_events)
    logger.info("Extracted %d cases from session events.", len(cases))

    # Apply minimum quality filter if specified
    if min_quality > 0.0:
        before = len(cases)
        cases = [c for c in cases if (c.labels.get("quality_score") or 0.0) >= min_quality]
        logger.info("Quality filter (min=%.2f): %d → %d cases", min_quality, before, len(cases))

    # Serialize
    output = {
        "name": "session_derived_cases",
        "version": "1.0.0",
        "description": f"Cases extracted from {len(sessions)} completed sessions",
        "cases": [
            {
                "id": c.id,
                "target": c.target.value,
                "input": c.input.model_dump(),
                "expected": c.expected.model_dump(),
                "labels": c.labels,
                "metadata": c.metadata,
            }
            for c in cases
        ],
    }
    output_path.write_text(json.dumps(output, indent=2, default=str))
    logger.info("Exported %d cases to %s", len(cases), output_path)

    await get_mongodb().shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export prompt optimization dataset")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("/tmp/opt_dataset.json"))
    parser.add_argument("--max-sessions", type=int, default=500)
    parser.add_argument("--min-quality", type=float, default=0.0)
    args = parser.parse_args()

    asyncio.run(run_export(args.output, args.max_sessions, args.min_quality))


if __name__ == "__main__":
    main()
