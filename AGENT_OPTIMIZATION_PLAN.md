# Pythinker Agent Optimization Plan
## Reducing Hallucinations, Task Decomposition, Speed & Efficiency

**Research Date:** January 2026
**Based on:** Latest 2025 research from Emergent Mind, Microsoft Azure AI, LangChain, Stanford, and industry best practices

---

## Executive Summary

This plan outlines specific, actionable improvements to reduce agent hallucinations, decompose prompts into smaller tasks, enhance speed, and improve overall efficiency while ensuring the agent stays focused on user prompts.

---

## Part 1: Hallucination Reduction (Priority: Critical)

### Current State Analysis
Your codebase already has `ToolHallucinationDetector` for tool-call hallucinations. The following enhancements target **content hallucinations** and **factual accuracy**.

### 1.1 Implement Contextual Grounding Check
**Research Finding:** AWS Bedrock's contextual grounding check reduces hallucinations by verifying outputs against source context.

**Implementation Tasks:**
```
[ ] Task 1.1.1: Create GroundingValidator service
    Location: backend/app/domain/services/agents/grounding_validator.py
    - Accept grounding_source (context), query (user request), and response
    - Compute grounding score using semantic similarity
    - Flag responses with grounding_score < 0.7

[ ] Task 1.1.2: Integrate into reflection_node
    Location: backend/app/domain/services/langgraph/nodes/reflection.py
    - Add grounding check before approving execution results
    - Require re-execution if grounding fails

[ ] Task 1.1.3: Add span-level verification for RAG outputs
    - Verify each claim/span in generated text against retrieved context
    - Track provenance: which source supported which claim
```

### 1.2 Multi-Agent Cross-Verification
**Research Finding:** Multi-agent frameworks reduce hallucinations by 96% vs baseline (Stanford 2024).

**Implementation Tasks:**
```
[ ] Task 1.2.1: Add VerifierAgent to workflow
    Location: backend/app/domain/services/agents/verifier.py (exists)
    - Expand to verify factual claims, not just plan validity
    - Use "devil's advocate" prompt to challenge assertions

[ ] Task 1.2.2: Implement confidence scoring
    - LLM outputs confidence with each claim
    - Low-confidence claims trigger retrieval augmentation
    - Add to execution.py response parsing

[ ] Task 1.2.3: Create hallucination feedback loop
    - Store hallucination events in memory_service
    - Use past hallucinations as negative examples in prompts
```

### 1.3 Input/Output Guardrails
**Research Finding:** Layered guardrails (input validation + output moderation) prevent 80%+ of problematic outputs.

**Implementation Tasks:**
```
[ ] Task 1.3.1: Create InputGuardrails service
    Location: backend/app/domain/services/agents/input_guardrails.py
    - Detect prompt injection attempts
    - Identify ambiguous or underspecified requests
    - Request clarification before proceeding

[ ] Task 1.3.2: Create OutputGuardrails service
    Location: backend/app/domain/services/agents/output_guardrails.py
    - Validate factual consistency
    - Check for contradictions with prior context
    - Enforce topic relevance to user request

[ ] Task 1.3.3: Integrate guardrails into LangGraph flow
    - Add as pre-processing step before planning_node
    - Add as post-processing after execution_node
```

### 1.4 Preference Optimization for Faithfulness
**Research Finding:** Preference optimization (training on faithful vs unfaithful pairs) reduces hallucinations by 90-96% (NAACL 2025).

**Implementation Tasks:**
```
[ ] Task 1.4.1: Create hallucination dataset from logs
    - Extract failed executions with hallucination flags
    - Pair with corrected/successful versions
    - Store in structured format for future fine-tuning

[ ] Task 1.4.2: Implement few-shot anti-hallucination examples
    - Add 2-3 examples of faithful responses to system prompts
    - Include examples showing "I don't know" when appropriate
```

---

## Part 2: Prompt Decomposition into Smaller Tasks (Priority: High)

### Current State Analysis
Your `PlannerAgent` has basic complexity detection. The following enhancements improve task splitting.

### 2.1 Recursive Task Decomposition
**Research Finding:** TDAG (2025) shows dynamic decomposition with specialized subagents reduces error propagation.

**Implementation Tasks:**
```
[ ] Task 2.1.1: Enhance get_task_complexity()
    Location: backend/app/domain/services/agents/planner.py
    - Add semantic complexity analysis (not just keyword matching)
    - Detect multi-part requests requiring parallel work
    - Identify dependency chains

[ ] Task 2.1.2: Implement hierarchical task tree
    New file: backend/app/domain/models/task_tree.py
    - Tree structure: Task -> SubTasks -> Atomic Actions
    - Each node has: description, dependencies, estimated_complexity
    - Support for parallel-safe subtask identification

[ ] Task 2.1.3: Add atomic task validation
    - Ensure each decomposed task is "single LLM call" actionable
    - Max 30 seconds execution time per atomic task
    - Clear input/output specification per subtask
```

### 2.2 Decomposed Prompting (DecomP) Pattern
**Research Finding:** DecomP framework shows 2-3x accuracy improvement on complex reasoning tasks.

**Implementation Tasks:**
```
[ ] Task 2.2.1: Create TaskDecomposer service
    Location: backend/app/domain/services/agents/task_decomposer.py
    Functions:
    - decompose(task) -> List[SubTask]
    - is_atomic(task) -> bool
    - merge_results(subtask_results) -> FinalResult

[ ] Task 2.2.2: Implement sub-task handlers
    - Route subtasks to specialized tools/prompts
    - Maintain conversation history across subtask solutions
    - Support recursive decomposition for nested complexity

[ ] Task 2.2.3: Add decomposition to planning_node
    Location: backend/app/domain/services/langgraph/nodes/planning.py
    - Before plan creation, run task decomposition
    - Create plan steps from decomposed subtasks
    - Preserve subtask dependencies in step metadata
```

### 2.3 Vertical vs Horizontal Decomposition
**Research Finding:** Vertical for sequential tasks, horizontal for parallel work.

**Implementation Tasks:**
```
[ ] Task 2.3.1: Detect decomposition strategy
    - Analyze task for independent vs dependent components
    - Tag subtasks as "parallel-safe" or "sequential"

[ ] Task 2.3.2: Implement parallel subtask execution
    Location: backend/app/domain/services/langgraph/nodes/execution.py
    - Use asyncio.gather for parallel-safe subtasks
    - Batch independent tool calls
    - Reduce LLM roundtrips

[ ] Task 2.3.3: Add dependency graph to plan state
    Location: backend/app/domain/services/langgraph/state.py
    - Track which steps block which
    - Enable out-of-order completion when safe
```

---

## Part 3: Speed Enhancement (Priority: High)

### Current State Analysis
Current workflow is sequential. Research shows 54% latency reduction possible with parallelization.

### 3.1 LLM Call Optimization
**Research Finding:** Caching delivers 8x speedup on repeated queries; smaller models reduce latency significantly.

**Implementation Tasks:**
```
[ ] Task 3.1.1: Implement semantic LLM response caching
    Location: backend/app/domain/services/agents/prompt_cache_manager.py (exists)
    - Hash prompts by semantic similarity, not exact match
    - Cache embeddings for common query patterns
    - 15-minute TTL with LRU eviction

[ ] Task 3.1.2: Add model routing by task complexity
    - Simple tasks -> GPT-4o-mini / Claude Haiku
    - Complex reasoning -> GPT-4o / Claude Sonnet
    - Save 60-70% latency on simple tasks

[ ] Task 3.1.3: Implement streaming for all LLM calls
    - Stream plan creation (already partial support)
    - Stream execution results
    - Reduce perceived latency
```

### 3.2 Parallel Execution Architecture
**Research Finding:** LangGraph parallelization can slash latency by 54%.

**Implementation Tasks:**
```
[ ] Task 3.2.1: Add parallel node support to graph
    Location: backend/app/domain/services/langgraph/graph.py
    - Use LangGraph's parallel execution for independent nodes
    - Run verification checks in parallel with non-blocking work

[ ] Task 3.2.2: Batch tool calls
    Location: backend/app/domain/services/agents/execution.py
    - Identify tools that can be called simultaneously
    - Use asyncio.gather for parallel MCP calls
    - Reduce sandbox round-trips

[ ] Task 3.2.3: Implement speculative execution
    - Pre-fetch likely needed resources during planning
    - Cache file contents before execution
    - Warm up browser/sandbox connections
```

### 3.3 Reduce LLM Calls
**Research Finding:** Hybrid code+LLM approach (LangGraph philosophy) reduces calls by 40-60%.

**Implementation Tasks:**
```
[ ] Task 3.3.1: Replace LLM calls with code where possible
    - Simple routing decisions -> Python conditionals
    - Format validation -> Pydantic models
    - Template responses -> String formatting

[ ] Task 3.3.2: Combine multi-step prompts
    - Merge related prompts into single call
    - Use structured output for multiple answers
    - Reduce reflection/update cycles

[ ] Task 3.3.3: Implement early termination
    - Detect when task is complete before all steps run
    - Skip verification for low-risk operations
    - Add "fast path" for simple queries
```

---

## Part 4: Efficiency Improvements (Priority: Medium)

### 4.1 Token Management
**Implementation Tasks:**
```
[ ] Task 4.1.1: Enhance context compression
    Location: backend/app/domain/services/agents/context_manager.py
    - Summarize long tool outputs before adding to context
    - Drop low-relevance messages from history
    - Implement sliding window with smart truncation

[ ] Task 4.1.2: Add cost tracking per request
    - Track tokens used per node in workflow
    - Identify expensive operations
    - Set per-request token budgets

[ ] Task 4.1.3: Implement prompt compression
    - Remove redundant instructions
    - Use abbreviations for repeated concepts
    - Dynamic prompt length based on task complexity
```

### 4.2 Memory Efficiency
**Implementation Tasks:**
```
[ ] Task 4.2.1: Optimize Qdrant memory queries
    - Batch similarity searches
    - Cache frequent memory retrievals
    - Implement memory importance decay

[ ] Task 4.2.2: Add selective memory injection
    - Only inject relevant memories (not all similar ones)
    - Rank by recency + relevance + outcome success
    - Limit to 2-3 most useful memories
```

---

## Part 5: User Prompt Adherence (Priority: Critical)

### 5.1 Prompt Grounding
**Research Finding:** Agents drift from user intent without explicit grounding checks.

**Implementation Tasks:**
```
[ ] Task 5.1.1: Create UserIntentTracker service
    Location: backend/app/domain/services/agents/intent_tracker.py
    - Extract explicit user requirements at planning
    - Track which requirements are addressed by which steps
    - Flag unaddressed requirements

[ ] Task 5.1.2: Add intent verification to reflection
    - Compare execution results against original user request
    - Score "requirement coverage" percentage
    - Force replan if coverage < 80%

[ ] Task 5.1.3: Implement scope drift detection
    - Detect when agent adds unrequested features
    - Detect when agent skips requested features
    - Alert and correct before completion
```

### 5.2 Explicit Requirement Extraction
**Implementation Tasks:**
```
[ ] Task 5.2.1: Parse user prompt for explicit requirements
    - Extract numbered items, bullet points
    - Identify "must have" vs "nice to have" language
    - Create requirement checklist

[ ] Task 5.2.2: Add requirement checkpoints to plan
    - Each major requirement maps to plan step(s)
    - Verification checks requirement completion
    - Final summary lists addressed requirements

[ ] Task 5.2.3: Implement "did you mean" clarification
    - For ambiguous prompts, ask before proceeding
    - Offer 2-3 interpretations with confidence scores
    - Use AskUserQuestion pattern from Claude Code
```

---

## Implementation Priority Matrix

| Task Group | Impact | Effort | Priority |
|------------|--------|--------|----------|
| 1.1 Grounding Validator | High | Medium | P0 |
| 1.3 Input/Output Guardrails | High | Medium | P0 |
| 2.1 Recursive Decomposition | High | High | P0 |
| 3.1 LLM Call Optimization | High | Low | P1 |
| 3.2 Parallel Execution | High | Medium | P1 |
| 5.1 Prompt Grounding | Critical | Medium | P0 |
| 1.2 Multi-Agent Verification | Medium | High | P2 |
| 2.2 DecomP Pattern | Medium | Medium | P1 |
| 3.3 Reduce LLM Calls | Medium | Low | P1 |
| 4.1 Token Management | Medium | Low | P2 |

---

## Quick Wins (Implement This Week)

1. **Add model routing** - Use faster model for simple tasks (1.5.2)
2. **Batch parallel tool calls** - Use asyncio.gather in execution (3.2.2)
3. **Enhance few-shot examples** - Add anti-hallucination examples to system prompts (1.4.2)
4. **Extract user requirements** - Parse bullets/numbered items from prompts (5.2.1)
5. **Cache common queries** - Enable semantic caching in prompt_cache_manager (3.1.1)

---

## Metrics to Track

| Metric | Current Baseline | Target | Measurement |
|--------|------------------|--------|-------------|
| Hallucination Rate | TBD | <5% | Manual review sample |
| Task Completion Accuracy | TBD | >90% | User requirement coverage |
| Average Response Time | TBD | <5s simple, <30s complex | Latency tracking |
| LLM Calls per Task | TBD | -40% | Count API calls |
| User Prompt Adherence | TBD | >95% | Requirement checklist coverage |

---

## References

1. Emergent Mind - Hallucination Mitigation Techniques (2025)
2. Microsoft Azure AI Foundry - Best Practices for LLM Hallucinations (Apr 2025)
3. LangChain Blog - How to Speed Up AI Agents (2025)
4. Amazon Science - Task Decomposition with Smaller LLMs (2025)
5. Stanford Study - Multi-Strategy Hallucination Reduction (2024)
6. NAACL 2025 - Preference Optimization for Faithful Outputs
7. Akira AI - Real-Time Guardrails for Agentic Systems (2025)
8. Continue.dev - Task Decomposition for Coding Agents (2025)
