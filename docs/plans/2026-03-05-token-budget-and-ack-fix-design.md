# Token Budget Enforcement & Acknowledgment Professionalism Fix

**Date:** 2026-03-05
**Status:** Implemented & Deployed

## Problem

Two issues discovered via Telegram research session monitoring:

1. **Token budget exhaustion**: Planning phase consumed 92%+ of the 500K token budget, leaving nothing for execution. Root cause: `feature_token_budget_manager=False` — the phase-level budget was never enforced.

2. **Unprofessional acknowledgments**: LLM-generated first replies mentioned specific search sites ("including searching Reddit and other sources") and expanded vague references. The system prompt in `FastAcknowledgmentRefiner` lacked restrictions on source mentions.

## Solution

### A. Token Budget (3 changes)

**1. Enable feature flags** (`config_features.py`):
- `feature_token_budget_manager`: `False` → `True`
- `feature_fast_draft_plan`: `False` → `True`
- New: `token_budget_planning_cap: float = 0.30`

**2. Research-mode allocation profiles** (`token_budget_manager.py`):

| Phase | Default | deep/wide_research | fast_search |
|-------|---------|-------------------|-------------|
| System | 15% | 10% | 10% |
| Planning | 15% | 10% | 8% |
| Execution | 45% | 50% | 52% |
| Memory | 10% | 10% | 10% |
| Summarization | 15% | 20% | 20% |

**3. Hard planning cap**: `MAX_PLANNING_FRACTION = 0.30` — no profile can exceed 30% planning. Excess redistributed to execution.

**4. Wiring** (`plan_act.py`): `_initialize_token_budget()` passes `research_mode` and `planning_cap` to `TokenBudgetManager`.

### B. Acknowledgment Fix (1 change)

**`fast_ack_refiner.py`**:
- System prompt: added rule prohibiting source/site mentions, added rule allowing time estimates
- Sanitizer: regex safety net strips source mentions (Reddit, Google, Stack Overflow, GitHub, Wikipedia, etc.) from LLM output even if prompt instruction is ignored
- Handles comma-separated lists ("Reddit, Stack Overflow, and GitHub")

## Impact

- Research sessions get 50% execution budget (was unconstrained → 92% planning)
- Planning hard-capped at 30% prevents runaway token consumption
- Telegram acks are clean: "Got it! I'll research codex 5.4 vs GLM 5. This should take about 5-10 minutes."

## Files Changed

- `backend/app/core/config_features.py` — enable flags, add planning cap setting
- `backend/app/domain/services/agents/token_budget_manager.py` — research profiles, hard cap
- `backend/app/domain/services/flows/fast_ack_refiner.py` — prompt + sanitizer
- `backend/app/domain/services/flows/plan_act.py` — wire research_mode into budget init

## Commits

- `33351775` fix(ack): strip source-site mentions from Telegram acknowledgments
- `d3d0a05f` feat(budget): add research-mode allocation profiles and hard planning cap
- `8d39101f` feat(budget): enable token budget manager and wire research-mode profiles
