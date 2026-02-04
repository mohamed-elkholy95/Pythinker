# Agent Logic Enhancement Plan

## Overview

This plan addresses three key areas:
1. **LangGraph-DDD Integration Conflicts** - Ensuring clean architecture boundaries
2. **Hallucination Prevention** - Strengthening detection and prevention mechanisms
3. **User Prompt Following** - Ensuring agent stays aligned with user intent

---

## Part 1: LangGraph-DDD Integration Review

### Current State Analysis

The LangGraph integration is well-structured with proper DDD compliance:
- Domain layer imports flow correctly (no violations)
- Repositories abstracted through constructor injection
- Agents composed and injected into state
- Tools built once, passed to all agents

### Minor Issues Identified

| Issue | Location | Severity |
|-------|----------|----------|
| Feature flags stored in workflow state | `langgraph/state.py:138` | Low |
| Agents not serialized in checkpoints (re-instantiation needed) | `langgraph/checkpointer.py:220` | Low |
| Routing evaluates feature flags in domain layer | `langgraph/routing.py` | Low |

### Recommended Actions

#### P3: Move Feature Flags to Configuration

**File**: `backend/app/domain/services/langgraph/state.py`

```python
# Instead of storing in state:
feature_flags: dict[str, bool]

# Pass via config at runtime:
config = {"configurable": {"feature_flags": get_feature_flags()}}
```

**Rationale**: Feature flags are system-level concerns, not domain state.

**Effort**: Low | **Impact**: Low | **Priority**: P3

---

## Part 2: Hallucination Prevention Enhancement

### Current Gaps Analysis

| Gap | Severity | Current Behavior |
|-----|----------|------------------|
| Hallucination detector not in execution loop | HIGH | Only called from critic |
| No semantic parameter validation | HIGH | Only syntactic validation |
| No cross-claim contradiction detection | MEDIUM | Contradictory outputs pass |
| Implicit requirement limit (~10) is arbitrary | LOW | May miss requirements |
| Content hallucination only flags patterns | MEDIUM | Plausible false claims pass |

### Phase 1: Integrate Hallucination Detection into Execution Loop (P0)

**Goal**: Detect tool hallucinations BEFORE execution, not just in critique.

**File**: `backend/app/domain/services/agents/base.py`

**Changes**:

```python
# In BaseAgent.invoke_tool() - Add pre-execution validation

async def invoke_tool(
    self,
    tool: BaseTool,
    function_name: str,
    arguments: dict[str, Any],
    skip_security: bool = False,
) -> ToolResult:
    # NEW: Pre-execution hallucination check
    validation_result = self._hallucination_detector.validate_tool_call(
        function_name=function_name,
        arguments=arguments,
        available_tools=self.get_available_tools(),
    )

    if not validation_result.is_valid:
        logger.warning(
            f"Tool hallucination detected: {validation_result.error_message}",
            extra={
                "function_name": function_name,
                "suggested_tool": validation_result.suggested_tool,
            }
        )
        # Return error with guidance instead of executing
        return ToolResult(
            success=False,
            message=validation_result.correction_message,
        )

    # Continue with existing security assessment and execution...
```

**Effort**: Medium | **Impact**: High | **Priority**: P0

### Phase 2: Add Semantic Parameter Validation (P1)

**Goal**: Detect parameters that are syntactically valid but semantically wrong.

**File**: `backend/app/domain/services/agents/hallucination_detector.py`

**New Method**:

```python
def validate_parameter_semantics(
    self,
    function_name: str,
    param_name: str,
    param_value: Any,
    context: str | None = None,
) -> ToolValidationResult:
    """Validate parameter values are semantically reasonable.

    Examples of semantic issues:
    - file_path="/etc/passwd" when task is about user files
    - query="how to hack" when task is about data analysis
    - url="http://localhost:admin" for external research

    Args:
        function_name: Tool function being called
        param_name: Parameter being validated
        param_value: Value to validate
        context: Optional task context for relevance checking

    Returns:
        ToolValidationResult with is_valid and optional correction
    """
    # Define high-risk parameter patterns per tool
    HIGH_RISK_PATTERNS = {
        "file_write": {
            "file": [
                r"^/etc/",  # System config files
                r"^/usr/",  # System binaries
                r"\.env$",  # Environment files without confirmation
            ],
        },
        "shell_exec": {
            "command": [
                r"rm\s+-rf\s+/",  # Dangerous rm
                r">\s*/dev/",  # Device writes
                r"sudo\s+",  # Privilege escalation
            ],
        },
        "browser_goto": {
            "url": [
                r"file://",  # Local file access
                r"localhost.*admin",  # Admin panels
            ],
        },
    }

    # Check against patterns
    patterns = HIGH_RISK_PATTERNS.get(function_name, {}).get(param_name, [])
    for pattern in patterns:
        if re.search(pattern, str(param_value), re.IGNORECASE):
            return ToolValidationResult(
                is_valid=False,
                error_type="semantic_violation",
                error_message=f"Parameter '{param_name}' value may be dangerous: {param_value}",
                suggested_correction=f"Please confirm this action is intended for the task: {context or 'unknown'}",
            )

    return ToolValidationResult(is_valid=True)
```

**Effort**: Medium | **Impact**: High | **Priority**: P1

### Phase 3: Add Cross-Claim Contradiction Detection (P1)

**Goal**: Detect when output contains contradictory claims.

**File**: `backend/app/domain/services/agents/content_hallucination_detector.py`

**New Method**:

```python
def detect_contradictions(self, text: str) -> list[ContradictionResult]:
    """Detect internally contradictory claims in text.

    Examples:
    - "The API returns JSON" ... "The response is XML"
    - "Performance improved 20%" ... "Speed decreased significantly"
    - "Supports Python 3.8+" ... "Requires Python 3.10 minimum"

    Returns:
        List of detected contradictions with source locations
    """
    contradictions = []

    # Extract claim pairs with entities
    claims = self._extract_claims_with_entities(text)

    # Group claims by entity/subject
    entity_claims: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        for entity in claim.entities:
            entity_claims[entity.lower()].append(claim)

    # Check for contradictions within entity groups
    for entity, entity_claim_list in entity_claims.items():
        if len(entity_claim_list) < 2:
            continue

        for i, claim1 in enumerate(entity_claim_list):
            for claim2 in entity_claim_list[i+1:]:
                if self._claims_contradict(claim1, claim2):
                    contradictions.append(ContradictionResult(
                        claim1=claim1.text,
                        claim2=claim2.text,
                        entity=entity,
                        confidence=self._contradiction_confidence(claim1, claim2),
                    ))

    return contradictions

def _claims_contradict(self, claim1: Claim, claim2: Claim) -> bool:
    """Check if two claims contradict each other."""
    # Numeric contradiction: different numbers for same metric
    if claim1.numeric_value and claim2.numeric_value:
        if claim1.metric == claim2.metric:
            # Same metric, significantly different values
            ratio = max(claim1.numeric_value, claim2.numeric_value) / \
                    min(claim1.numeric_value, claim2.numeric_value)
            if ratio > 1.5:  # 50% difference threshold
                return True

    # Polarity contradiction: opposite sentiments
    if claim1.polarity and claim2.polarity:
        if claim1.polarity * claim2.polarity < 0:  # Opposite signs
            return True

    # Negation contradiction: "supports X" vs "does not support X"
    negation_patterns = [
        (r"supports?\s+(\w+)", r"(?:does\s+)?not\s+support\s+\1"),
        (r"requires?\s+(\w+)", r"(?:does\s+)?not\s+require\s+\1"),
        (r"includes?\s+(\w+)", r"(?:does\s+)?not\s+include\s+\1"),
    ]
    for pos_pattern, neg_pattern in negation_patterns:
        if (re.search(pos_pattern, claim1.text, re.I) and
            re.search(neg_pattern, claim2.text, re.I)):
            return True
        if (re.search(neg_pattern, claim1.text, re.I) and
            re.search(pos_pattern, claim2.text, re.I)):
            return True

    return False
```

**Effort**: High | **Impact**: Medium | **Priority**: P1

### Phase 4: Enhance Chain-of-Verification (P2)

**Goal**: Strengthen CoVe to verify claims against actual tool outputs.

**File**: `backend/app/domain/services/langgraph/nodes/summarize.py`

**Enhancement**:

```python
async def verify_claims_against_sources(
    self,
    claims: list[str],
    tool_outputs: list[ToolResult],
) -> list[ClaimVerificationResult]:
    """Verify extracted claims against actual tool outputs.

    This closes the loop between what the agent claims and what
    the tools actually returned.
    """
    results = []

    for claim in claims:
        # Find relevant tool outputs for this claim
        relevant_outputs = self._find_relevant_outputs(claim, tool_outputs)

        if not relevant_outputs:
            results.append(ClaimVerificationResult(
                claim=claim,
                verified=False,
                reason="No supporting tool output found",
                confidence=0.2,
            ))
            continue

        # Check if any output supports the claim
        best_match = None
        best_confidence = 0.0

        for output in relevant_outputs:
            confidence = self._calculate_support_confidence(claim, output)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = output

        results.append(ClaimVerificationResult(
            claim=claim,
            verified=best_confidence >= 0.7,
            reason=f"Supported by {best_match.tool_name}" if best_match else "No match",
            confidence=best_confidence,
            source_output=best_match,
        ))

    return results
```

**Effort**: High | **Impact**: High | **Priority**: P2

---

## Part 3: User Prompt Following Enhancement

### Current Gaps Analysis

| Gap | Severity | Current Behavior |
|-----|----------|------------------|
| Text similarity (Jaccard) is shallow | MEDIUM | Synonyms not recognized |
| No constraint violation prevention | HIGH | Agent may violate "don't" instructions |
| No progress tracking against requirements | MEDIUM | May skip requirements |
| Follow-up context not preserved | MEDIUM | New messages may lose context |

### Phase 1: Enhanced Intent Extraction with Constraint Tracking (P0)

**Goal**: Extract and track "DO NOT" constraints throughout execution.

**File**: `backend/app/domain/services/agents/intent_tracker.py`

**Enhancement**:

```python
@dataclass
class UserIntent:
    # Existing fields...

    # NEW: Explicit constraints the user specified
    constraints: list[str] = field(default_factory=list)

    # NEW: Inferred constraints from context
    implicit_constraints: list[str] = field(default_factory=list)

def extract_intent(self, message: str) -> UserIntent:
    """Enhanced intent extraction with constraint detection."""

    # Existing extraction...

    # NEW: Extract explicit constraints (DO NOT, don't, avoid, never)
    constraint_patterns = [
        r"(?:do\s+not|don't|dont)\s+(.+?)(?:\.|$)",
        r"(?:never|avoid|skip)\s+(.+?)(?:\.|$)",
        r"(?:without|no)\s+(\w+(?:\s+\w+)?)",
        r"(?:except|excluding)\s+(.+?)(?:\.|$)",
    ]

    constraints = []
    for pattern in constraint_patterns:
        matches = re.findall(pattern, message, re.IGNORECASE)
        constraints.extend([m.strip() for m in matches if m.strip()])

    # NEW: Infer implicit constraints from task context
    implicit_constraints = self._infer_implicit_constraints(message)

    return UserIntent(
        # ... existing fields ...
        constraints=constraints,
        implicit_constraints=implicit_constraints,
    )

def _infer_implicit_constraints(self, message: str) -> list[str]:
    """Infer constraints that are implicit in the task."""
    implicit = []

    # If user asks for "simple" solution, don't over-engineer
    if re.search(r"\b(simple|basic|minimal|quick)\b", message, re.I):
        implicit.append("Keep solution simple, don't over-engineer")

    # If user specifies a language/framework, don't switch
    lang_match = re.search(
        r"\b(in\s+)?(python|javascript|typescript|rust|go|java)\b",
        message, re.I
    )
    if lang_match:
        lang = lang_match.group(2)
        implicit.append(f"Use {lang}, don't switch to another language")

    # If user mentions "existing" code, don't create new files unnecessarily
    if re.search(r"\b(existing|current|this)\s+(code|file|project)\b", message, re.I):
        implicit.append("Modify existing code, don't create new files unnecessarily")

    return implicit
```

**Effort**: Medium | **Impact**: High | **Priority**: P0

### Phase 2: Constraint Violation Detection in Execution (P0)

**Goal**: Check constraints before and after each tool execution.

**File**: `backend/app/domain/services/langgraph/nodes/execution.py`

**Enhancement**:

```python
async def execute_step(state: PlanActState) -> dict[str, Any]:
    """Execute step with constraint violation checking."""

    # Get intent tracker and constraints
    intent_tracker = state.get("intent_tracker")
    user_intent = state.get("user_intent")

    # PRE-EXECUTION: Check if planned action violates constraints
    if user_intent and user_intent.constraints:
        current_step = state["current_step"]

        for constraint in user_intent.constraints + user_intent.implicit_constraints:
            violation = await _check_constraint_violation(
                constraint=constraint,
                step_description=current_step.description,
                planned_tools=current_step.expected_tools or [],
            )

            if violation.is_violated:
                logger.warning(
                    f"Constraint violation detected: {constraint}",
                    extra={"step": current_step.description, "reason": violation.reason}
                )

                # Emit warning event to user
                pending_events.append(ErrorEvent(
                    error=f"Warning: Action may violate constraint '{constraint}'. {violation.reason}",
                    severity="warning",
                ))

                # Request user confirmation for high-severity violations
                if violation.severity == "high":
                    state["needs_human_input"] = True
                    state["human_input_reason"] = (
                        f"Planned action may violate your constraint: '{constraint}'. "
                        f"Proceed anyway?"
                    )
                    return state

    # Continue with normal execution...

    # POST-EXECUTION: Verify constraint not violated by output
    if user_intent and tool_result.success:
        post_violations = await _check_output_constraints(
            output=tool_result.data,
            constraints=user_intent.constraints,
        )

        for violation in post_violations:
            pending_events.append(ErrorEvent(
                error=f"Output may have violated constraint: {violation.constraint}",
                severity="warning",
            ))
```

**Effort**: High | **Impact**: High | **Priority**: P0

### Phase 3: Semantic Requirement Matching (P1)

**Goal**: Use embeddings for requirement matching instead of word overlap.

**File**: `backend/app/domain/services/agents/intent_tracker.py`

**Enhancement**:

```python
class IntentTracker:
    def __init__(self):
        # Use lightweight sentence embeddings
        self._embedding_cache: dict[str, list[float]] = {}

    def _compute_semantic_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """Compute semantic similarity using embeddings.

        Falls back to Jaccard if embeddings unavailable.
        """
        try:
            # Use trigram embeddings (same as stuck_detector)
            from app.domain.services.agents.stuck_detector import compute_trigram_embedding

            emb1 = self._get_or_compute_embedding(text1)
            emb2 = self._get_or_compute_embedding(text2)

            # Cosine similarity
            dot = sum(a * b for a, b in zip(emb1, emb2))
            norm1 = sum(a * a for a in emb1) ** 0.5
            norm2 = sum(b * b for b in emb2) ** 0.5

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot / (norm1 * norm2)

        except Exception:
            # Fallback to Jaccard
            return self._compute_text_similarity(text1, text2)

    def _get_or_compute_embedding(self, text: str) -> list[float]:
        """Get cached embedding or compute new one."""
        cache_key = text[:200]  # Truncate for cache key

        if cache_key not in self._embedding_cache:
            from app.domain.services.agents.stuck_detector import compute_trigram_embedding
            self._embedding_cache[cache_key] = compute_trigram_embedding(text)

            # Limit cache size
            if len(self._embedding_cache) > 500:
                # Remove oldest entries
                keys_to_remove = list(self._embedding_cache.keys())[:100]
                for key in keys_to_remove:
                    del self._embedding_cache[key]

        return self._embedding_cache[cache_key]

    def check_requirement_addressed(
        self,
        requirement: str,
        work_done: str,
        threshold: float = 0.7,
    ) -> bool:
        """Check if requirement is addressed using semantic matching."""
        similarity = self._compute_semantic_similarity(requirement, work_done)
        return similarity >= threshold
```

**Effort**: Medium | **Impact**: Medium | **Priority**: P1

### Phase 4: Progress Tracking Dashboard in State (P2)

**Goal**: Track requirement completion throughout execution.

**File**: `backend/app/domain/services/langgraph/state.py`

**Enhancement**:

```python
@dataclass
class RequirementProgress:
    """Track progress on a single requirement."""
    requirement: str
    is_addressed: bool = False
    confidence: float = 0.0
    addressed_by_step: str | None = None
    evidence: str | None = None

class PlanActState(TypedDict):
    # Existing fields...

    # NEW: Requirement tracking
    requirement_progress: list[RequirementProgress]
    constraint_violations: list[str]
    intent_alignment_score: float  # 0.0 to 1.0
```

**File**: `backend/app/domain/services/langgraph/nodes/update.py`

**Enhancement**:

```python
async def update_plan(state: PlanActState) -> dict[str, Any]:
    """Update plan with requirement progress tracking."""

    # Existing logic...

    # NEW: Update requirement progress after step completion
    intent_tracker = state.get("intent_tracker")
    user_intent = state.get("user_intent")
    completed_step = state.get("current_step")

    if intent_tracker and user_intent and completed_step:
        # Get step output
        step_output = _get_step_output(state)

        # Update progress for each requirement
        updated_progress = []
        for req_progress in state.get("requirement_progress", []):
            if not req_progress.is_addressed:
                # Check if this step addressed the requirement
                is_addressed = intent_tracker.check_requirement_addressed(
                    requirement=req_progress.requirement,
                    work_done=f"{completed_step.description}\n{step_output}",
                )

                if is_addressed:
                    req_progress.is_addressed = True
                    req_progress.addressed_by_step = completed_step.id
                    req_progress.confidence = 0.8  # From semantic matching
                    req_progress.evidence = step_output[:200]

            updated_progress.append(req_progress)

        # Calculate overall alignment score
        addressed_count = sum(1 for r in updated_progress if r.is_addressed)
        total_count = len(updated_progress) or 1
        alignment_score = addressed_count / total_count

        return {
            **state,
            "requirement_progress": updated_progress,
            "intent_alignment_score": alignment_score,
        }
```

**Effort**: High | **Impact**: Medium | **Priority**: P2

---

## Implementation Phases

### Phase 1: Critical Safety (Week 1)
- [ ] P0: Integrate hallucination detection into execution loop
- [ ] P0: Enhanced intent extraction with constraint tracking
- [ ] P0: Constraint violation detection in execution

### Phase 2: Core Enhancement (Week 2)
- [ ] P1: Add semantic parameter validation
- [ ] P1: Add cross-claim contradiction detection
- [ ] P1: Semantic requirement matching

### Phase 3: Advanced Features (Week 3)
- [ ] P2: Enhanced Chain-of-Verification
- [ ] P2: Progress tracking dashboard in state
- [ ] P3: Move feature flags to configuration

---

## Testing Strategy

### Unit Tests

```python
# test_hallucination_integration.py
class TestHallucinationInExecutionLoop:
    async def test_detects_nonexistent_tool_before_execution(self):
        agent = create_test_agent()
        result = await agent.invoke_tool(
            tool=None,  # Will trigger detection
            function_name="fake_tool_123",
            arguments={},
        )
        assert not result.success
        assert "Unknown tool" in result.message

    async def test_suggests_similar_tool_on_typo(self):
        agent = create_test_agent()
        result = await agent.invoke_tool(
            tool=None,
            function_name="file_raed",  # Typo of file_read
            arguments={"file": "/test.txt"},
        )
        assert "file_read" in result.message

# test_constraint_violation.py
class TestConstraintViolation:
    async def test_detects_constraint_violation(self):
        intent = UserIntent(
            constraints=["don't use external APIs"],
        )
        step = Step(description="Call external weather API")

        violation = await check_constraint_violation(
            constraint=intent.constraints[0],
            step_description=step.description,
        )

        assert violation.is_violated

    async def test_implicit_constraint_language(self):
        intent = extract_intent("Write a Python script to process data")

        assert any(
            "python" in c.lower() and "switch" in c.lower()
            for c in intent.implicit_constraints
        )
```

### Integration Tests

```python
# test_langgraph_hallucination_flow.py
class TestLangGraphHallucinationPrevention:
    async def test_full_flow_catches_hallucinated_tool(self):
        flow = LangGraphPlanActFlow(...)

        # Inject a plan that references non-existent tool
        message = Message(message="Use the super_tool to analyze data")

        events = []
        async for event in flow.run(message):
            events.append(event)

        # Should have error event about unknown tool
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert any("unknown tool" in e.error.lower() for e in error_events)
```

---

## Rollout Plan

1. **Feature Flag**: All changes behind `feature_hallucination_prevention_v2`
2. **Shadow Mode**: Log violations without blocking for 1 week
3. **Gradual Rollout**: Enable blocking for 10% -> 50% -> 100% of sessions
4. **Monitoring**: Track false positive rate, user satisfaction

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Tool hallucination rate | Unknown | < 1% |
| Constraint violation rate | Unknown | < 5% |
| Requirement coverage | ~70% | > 90% |
| Intent drift detection | Manual | Automated |
| Cross-claim contradictions | Not detected | < 2% |

---

## Dependencies

- `app.domain.services.agents.hallucination_detector` - Extend for parameter validation
- `app.domain.services.agents.intent_tracker` - Extend for constraints
- `app.domain.services.langgraph.nodes.execution` - Add pre/post validation
- `app.domain.services.langgraph.state` - Add progress tracking fields

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| False positives block valid actions | Shadow mode + configurable thresholds |
| Performance impact from validation | LRU caching + async validation |
| User frustration from too many warnings | Severity-based filtering |
| Breaking existing flows | Feature flag + gradual rollout |
