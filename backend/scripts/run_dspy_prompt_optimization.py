#!/usr/bin/env python
"""Run a DSPy/GEPA prompt optimization offline and publish the result.

Usage:
    conda activate pythinker
    cd backend
    pip install dspy-ai  # Only in optimization environment
    python scripts/run_dspy_prompt_optimization.py \
        --target planner \
        --optimizer miprov2 \
        [--auto light|medium|heavy] \
        [--dry-run]

The script:
  1. Loads and merges curated + session-mined datasets.
  2. Runs the optimizer (MIPROv2 or GEPA).
  3. Saves the artifact to GridFS.
  4. Creates an OptimizationRun record in MongoDB.
  5. Optionally creates and activates a PromptProfile from the result.

Environment variables:
    API_KEY      — LLM API key for DSPy calls
    API_BASE     — LLM API base URL (default: https://openrouter.ai/api/v1)
    MODEL_NAME   — LLM model name (default: settings.model_name)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import pathlib
import sys
import uuid

# Add backend to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _extract_patch_text_from_artifact(artifact_bytes: bytes) -> str:
    """Extract the optimized prompt instructions from a DSPy artifact.

    DSPy's ``.save()`` produces JSON structured as::

        {
            "generate": {"signature": {"instructions": "...", "prefix": "..."}, "demos": [...], "lm": null},
            "metadata": {"dependency_versions": {...}},
        }

    We extract ``signature.instructions`` which is the optimized prompt text.
    Falls back to the raw decoded artifact if parsing fails.
    """
    raw = artifact_bytes.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
        # Walk top-level keys looking for signature.instructions
        # DSPy programs may have different module names (e.g., "generate", "predict")
        for module_name, module_data in data.items():
            if module_name == "metadata" or not isinstance(module_data, dict):
                continue
            # Primary path: signature.instructions (DSPy >=2.4 save format)
            signature = module_data.get("signature", {})
            if isinstance(signature, dict) and "instructions" in signature:
                instructions = signature["instructions"]
                if isinstance(instructions, str) and instructions.strip():
                    logger.info(
                        "Extracted instructions from artifact module '%s' (%d chars)",
                        module_name,
                        len(instructions),
                    )
                    return instructions
            # Fallback: instructions at module level (older DSPy versions)
            if "instructions" in module_data:
                instructions = module_data["instructions"]
                if isinstance(instructions, str) and instructions.strip():
                    logger.info(
                        "Extracted instructions (legacy format) from module '%s' (%d chars)",
                        module_name,
                        len(instructions),
                    )
                    return instructions
        # If no instructions found, fall back to raw
        logger.warning("No 'instructions' key found in artifact — using raw artifact as patch text")
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse artifact JSON (%s) — using raw artifact as patch text", exc)
    return raw


async def run_and_publish(
    target_str: str,
    optimizer_str: str,
    auto: str,
    dry_run: bool,
    publish: bool,
    max_sessions: int,
) -> None:
    from beanie import init_beanie

    from app.core.config import get_settings
    from app.domain.models.prompt_optimization import OptimizationRun, OptimizerType
    from app.domain.models.prompt_profile import PromptPatch, PromptProfile, PromptTarget
    from app.domain.services.prompt_optimization.optimizer_orchestrator import run_optimization
    from app.infrastructure.models.documents import SessionDocument
    from app.infrastructure.models.prompt_optimization_documents import (
        OptimizationRunDocument,
        PromptProfileDocument,
    )
    from app.infrastructure.repositories.gridfs_prompt_artifact_repository import (
        GridFSPromptArtifactRepository,
    )
    from app.infrastructure.repositories.mongo_prompt_profile_repository import (
        MongoPromptProfileRepository,
    )
    from app.infrastructure.storage.mongodb import get_mongodb

    settings = get_settings()
    target = PromptTarget(target_str)
    optimizer_type = OptimizerType(optimizer_str)

    # LLM config
    api_key = os.environ.get("API_KEY", settings.api_key or "")
    api_base = os.environ.get("API_BASE", settings.api_base or "https://openrouter.ai/api/v1")
    model_name = os.environ.get("MODEL_NAME", settings.model_name or "gpt-4o-mini")

    if not api_key:
        raise ValueError("API_KEY environment variable (or settings.api_key) is required.")

    # Initialize MongoDB
    await get_mongodb().initialize()
    await init_beanie(
        database=get_mongodb().client[settings.mongodb_database],
        document_models=[
            SessionDocument,
            OptimizationRunDocument,
            PromptProfileDocument,
        ],
    )

    # Create run record
    run = OptimizationRun(
        target=target,
        optimizer=optimizer_type,
        config={"auto": auto, "model": model_name, "api_base": api_base},
    )
    profile_repo = MongoPromptProfileRepository()
    artifact_repo = GridFSPromptArtifactRepository()

    if not dry_run:
        await profile_repo.save_run(run)

    # Mine session events
    all_session_events: list[list[dict]] = []
    if max_sessions > 0:
        sessions = (
            await SessionDocument.find({"status": "completed"})
            .sort(-SessionDocument.created_at)
            .limit(max_sessions)
            .to_list()
        )
        for session in sessions:
            events_raw = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in session.events]
            all_session_events.append(events_raw)
        logger.info("Using %d session event streams for dataset.", len(all_session_events))

    # Run optimization
    run.mark_started()
    if not dry_run:
        await profile_repo.update_run_status(run)

    try:
        result = run_optimization(
            target=target,
            optimizer_type=optimizer_type,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            all_session_events=all_session_events or None,
            miprov2_auto=auto,
        )
        logger.info(
            "Optimization complete: baseline=%.4f optimized=%.4f improvement=%+.4f",
            result.baseline_score,
            result.optimized_score,
            result.improvement,
        )

        if dry_run:
            logger.info("[DRY RUN] Would save artifact (%d bytes) and create profile.", len(result.artifact_bytes))
            await get_mongodb().shutdown()
            return

        # Save artifact
        artifact_id = await artifact_repo.save_artifact(run.id, result.artifact_bytes)

        run.mark_completed(
            baseline_score=result.baseline_score,
            optimized_score=result.optimized_score,
            artifact_id=artifact_id,
        )
        run.train_cases = result.train_count
        run.val_cases = result.val_count
        run.test_cases = result.test_count
        await profile_repo.update_run_status(run)
        logger.info("Run record updated: %s", run.id)

        # Optionally publish as PromptProfile
        if publish:
            patch_text = _extract_patch_text_from_artifact(result.artifact_bytes)
            # Generate profile ID first so patches can reference it at construction
            profile_id = str(uuid.uuid4())
            profile = PromptProfile(
                id=profile_id,
                name=f"dspy-{optimizer_type.value}-{target.value}-{run.id[:8]}",
                version="1.0.0",
                source_run_id=run.id,
                patches=[
                    PromptPatch(
                        target=target,
                        profile_id=profile_id,
                        variant_id=f"{optimizer_type.value}-{target.value}",
                        patch_text=patch_text,
                        metadata={
                            "baseline_score": result.baseline_score,
                            "optimized_score": result.optimized_score,
                        },
                    )
                ],
                validation_summary={
                    f"{target.value}_baseline": result.baseline_score,
                    f"{target.value}_optimized": result.optimized_score,
                },
            )

            run.profile_id = profile.id
            await profile_repo.save_run(run)
            await profile_repo.save_profile(profile)
            logger.info("Published PromptProfile: %s", profile.id)

    except Exception as exc:
        logger.error("Optimization failed: %s", exc, exc_info=True)
        run.mark_failed(str(exc))
        if not dry_run:
            await profile_repo.update_run_status(run)
        raise
    finally:
        await get_mongodb().shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DSPy/GEPA prompt optimization")
    parser.add_argument(
        "--target",
        choices=["planner", "execution", "system"],
        default="execution",
        help="Which prompt surface to optimize",
    )
    parser.add_argument(
        "--optimizer",
        choices=["miprov2", "miprov2_light", "gepa"],
        default="miprov2_light",
        help="Optimizer algorithm to use",
    )
    parser.add_argument(
        "--auto",
        choices=["light", "medium", "heavy"],
        default="light",
        help="MIPROv2 search depth",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=100,
        help="Max session event streams to mine for training data",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run without saving results")
    parser.add_argument("--publish", action="store_true", help="Publish result as a PromptProfile")
    args = parser.parse_args()

    asyncio.run(
        run_and_publish(
            target_str=args.target,
            optimizer_str=args.optimizer,
            auto=args.auto,
            dry_run=args.dry_run,
            publish=args.publish,
            max_sessions=args.max_sessions,
        )
    )


if __name__ == "__main__":
    main()
