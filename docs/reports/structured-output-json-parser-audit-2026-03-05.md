# Structured Output JSON Parser Callsite Audit

Date: 2026-03-05
Scope: `backend/app` remaining `json_parser.parse(...)` and `parse_json_response(...)` usage

## Classification

| File | Line | Call | Tier | Notes |
|---|---:|---|---|---|
| `domain/services/agents/verifier.py` | 211 | `json_parser.parse(..., tier=tier)` | A | Fallback path behind tier-aware structured call routing. |
| `domain/services/agents/verifier.py` | 639 | `json_parser.parse(..., tier="A")` | A | Legacy parser fallback remains typed and tier-constrained. |
| `domain/services/agents/chain_of_verification.py` | 344 | `json_parser.parse(..., tier="A")` | A | Explicitly tier-tagged verification parsing. |
| `domain/services/agents/chain_of_verification.py` | 384 | `json_parser.parse(..., tier="A")` | A | Explicitly tier-tagged verification parsing. |
| `domain/services/agents/critic.py` | 584 | `json_parser.parse(..., tier="B")` | B | Explicit tiered parse fallback. |
| `domain/services/agents/critic.py` | 869 | `json_parser.parse(..., tier="B")` | B | Explicit tiered parse fallback. |
| `domain/services/agents/critic.py` | 983 | `json_parser.parse(..., tier="B")` | B | Explicit tiered parse fallback. |
| `domain/services/agents/critic.py` | 1047 | `json_parser.parse(..., tier="B")` | B | Explicit tiered parse fallback. |
| `domain/services/agents/critic.py` | 1180 | `json_parser.parse(..., tier="B")` | B | Explicit tiered parse fallback. |
| `domain/services/agents/execution.py` | 400 | `json_parser.parse(..., tier="B")` | B | Structured execution fallback parsing with tier gate. |
| `domain/services/agents/execution.py` | 403 | `parse_json_response(...)` | C | Lenient repair fallback for resilient execution. |
| `domain/services/agents/execution.py` | 1684 | `parse_json_response(...)` | C | Lenient correction path (non-decision-critical). |
| `domain/services/agents/reflection.py` | 337 | `json_parser.parse(..., tier="B")` | B | Reflection quality path with explicit tier gate. |
| `domain/services/agents/reflection.py` | 489 | `json_parser.parse(..., tier="B")` | B | Reflection quality path with explicit tier gate. |
| `domain/services/agents/self_consistency.py` | 344 | `json_parser.parse(..., tier="B")` | B | Self-consistency synthesis path with explicit tier gate. |
| `domain/services/flows/path_scorer.py` | 197 | `json_parser.parse(..., tier="B")` | B | Path scoring influences ranking decisions. |
| `domain/services/flows/complexity_analyzer.py` | 235 | `json_parser.parse(..., tier="C")` | C | Advisory analysis output, non-blocking. |
| `domain/services/orchestration/agent_factory.py` | 149 | `json_parser.parse(..., tier="B")` | B | Event parsing in orchestration path. |
| `domain/services/orchestration/research_agent.py` | 190 | `json_parser.parse(..., tier="B")` | B | Query generation path; now properly awaited. |
| `domain/services/orchestration/research_agent.py` | 271 | `json_parser.parse(..., tier="B")` | B | Synthesis extraction path; now properly awaited. |
| `infrastructure/external/llm/universal_llm.py` | 594 | `parse_json_response(...)` | C | Lenient helper API, intentionally permissive. |
| `infrastructure/external/llm/json_repair.py` | 45 | `parse_json_response(...)` | C | Shared repair utility (domain-agnostic). |

## Summary

- `json_parser.parse(...)` callsites are fully tier-tagged (no untagged parser callsites remain).
- Verifier critical path now prefers tier-aware structured policy execution with parser fallback retained.
- Remaining permissive `parse_json_response(...)` usage is limited to Tier C fallback paths by design.
