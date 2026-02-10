# Integration Plan: Phased Reflective Research Workflow

## Executive Summary

This plan outlines how to integrate a structured, phased research methodology into the existing agent system. The design introduces explicit Phase 1/2/3 checkpointing, reflective micro-summaries after each action, and proper event schema updates to surface research progress in the UI.

**Goal:** Transform the current `deep_research=true` path from an undifferentiated search-and-summarize flow into a disciplined ReAct loop with visible phase transitions, intermediate note-saving, and explicit replanning steps.

---

## Phase 1: Domain Model & Event Schema Enhancements

### 1.1 Extend Event Schema to Support Research Phases

**Problem:** `StreamEvent` has phase in domain but SSE transport drops it.

**Solution:**

```python
# backend/app/interfaces/schemas/event.py

class StreamEventData(BaseModel):
    content: str
    phase: Optional[str] = None  # ADD THIS: "planning", "executing", "summarizing", "phase_1", "phase_2", "phase_3"
    phase_metadata: Optional[Dict[str, Any]] = None  # NEW: phase-specific context
```

**Files to modify:**
- `backend/app/interfaces/schemas/event.py:272` - Add `phase` and `phase_metadata` fields
- `backend/app/domain/models/event.py:549` - Ensure domain `StreamEvent` properly maps to schema

**Acceptance criteria:**
- SSE events now carry phase information to frontend
- No breaking changes to existing event consumers

---

### 1.2 Create Research Phase State Model

**New file:** `backend/app/domain/models/research_phase.py`

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel

class ResearchPhase(str, Enum):
    PHASE_1_FUNDAMENTALS = "phase_1_fundamentals"
    PHASE_2_USE_CASES = "phase_2_use_cases"
    PHASE_3_BEST_PRACTICES = "phase_3_best_practices"
    COMPILATION = "compilation"

class ResearchCheckpoint(BaseModel):
    """Saved research notes from a completed phase"""
    phase: ResearchPhase
    notes: str
    sources: List[str]
    timestamp: str
    query_context: str  # What question this phase answered

class ResearchState(BaseModel):
    """Tracks progress through phased research"""
    current_phase: ResearchPhase
    checkpoints: List[ResearchCheckpoint] = []
    action_count: int = 0
    last_reflection: Optional[str] = None
    next_step: Optional[str] = None
```

**Purpose:** First-class representation of research workflow state, enabling:
- Phase transitions as explicit events
- Checkpoint persistence
- Progress tracking across long-running research tasks

---

## Phase 2: Agent Execution Layer - Reflective Action Loop

### 2.1 Implement Reflective Execution Wrapper

**Problem:** No enforced micro-summary + "Next, I will..." after each action.

**New file:** `backend/app/domain/services/agents/reflective_executor.py`

```python
class ReflectiveExecutor:
    """
    Wraps tool execution with mandatory reflection cycle:
    1. Execute action
    2. Generate micro-summary of what was learned
    3. Generate explicit next-step statement
    4. Emit reflection event to UI
    """
    
    async def execute_with_reflection(
        self,
        action: ToolCall,
        context: ExecutionContext,
        phase: ResearchPhase
    ) -> ReflectionResult:
        # Execute the tool
        result = await self._execute_tool(action)
        
        # Generate reflection using LLM
        reflection_prompt = f"""
        You just executed: {action.tool_name} with {action.parameters}
        
        Result: {result.output}
        
        Provide:
        1. A one-sentence summary of what you learned
        2. A one-sentence statement of what you'll do next
        
        Format:
        LEARNED: <summary>
        NEXT: <next action>
        """
        
        reflection = await self._llm_call(reflection_prompt, max_tokens=150)
        
        # Parse and emit
        learned, next_step = self._parse_reflection(reflection)
        
        await self._emit_reflection_event(
            phase=phase,
            learned=learned,
            next_step=next_step
        )
        
        return ReflectionResult(
            action_result=result,
            learned=learned,
            next_step=next_step
        )
```

**Integration point:** `backend/app/domain/services/agents/execution.py:414`
- Wrap existing tool execution with `ReflectiveExecutor`
- Each action now produces: result + reflection + next-step

**UI benefit:** Frontend can show "💡 Learned: ..." and "⏭️ Next: ..." after each action

---

### 2.2 Build Phase Checkpoint Manager

**New file:** `backend/app/domain/services/research/checkpoint_manager.py`

```python
class CheckpointManager:
    """
    Manages saving and retrieving research notes per phase.
    Implements the "Save research notes from Phase N" pattern.
    """
    
    async def save_checkpoint(
        self,
        session_id: str,
        phase: ResearchPhase,
        notes: str,
        sources: List[str]
    ):
        checkpoint = ResearchCheckpoint(
            phase=phase,
            notes=notes,
            sources=sources,
            timestamp=datetime.utcnow().isoformat(),
            query_context=self._infer_context(phase)
        )
        
        # Persist to database
        await self.repo.save_checkpoint(session_id, checkpoint)
        
        # Emit checkpoint event to UI
        await self.event_emitter.emit(CheckpointEvent(
            phase=phase.value,
            notes_preview=notes[:200] + "...",
            source_count=len(sources)
        ))
    
    async def retrieve_all_checkpoints(self, session_id: str) -> List[ResearchCheckpoint]:
        """Used during compilation phase to gather all notes"""
        return await self.repo.get_checkpoints(session_id)
    
    def _infer_context(self, phase: ResearchPhase) -> str:
        """Map phase to research question it answers"""
        mapping = {
            ResearchPhase.PHASE_1_FUNDAMENTALS: "What is the tool and how does it work?",
            ResearchPhase.PHASE_2_USE_CASES: "How is it used in practice?",
            ResearchPhase.PHASE_3_BEST_PRACTICES: "What are advanced patterns and best practices?"
        }
        return mapping.get(phase, "General research")
```

**Database schema addition:**

```sql
-- backend/app/infrastructure/database/migrations/add_research_checkpoints.sql

CREATE TABLE research_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    phase VARCHAR(50) NOT NULL,
    notes TEXT NOT NULL,
    sources JSONB NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    query_context TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_checkpoints_session ON research_checkpoints(session_id);
```

---

## Phase 3: Flow Orchestration - Phased Research Workflow

### 3.1 Create PhasedResearchFlow

**New file:** `backend/app/domain/services/flows/phased_research.py`

```python
class PhasedResearchFlow:
    """
    Implements the three-phase research methodology:
    - Phase 1: Fundamentals & Setup
    - Phase 2: Use Cases & Applications  
    - Phase 3: Best Practices & Advanced Features
    - Compilation: Synthesize all checkpoints into final report
    """
    
    def __init__(
        self,
        planner: Planner,
        executor: ReflectiveExecutor,
        checkpoint_manager: CheckpointManager,
        llm_service: LLMService
    ):
        self.planner = planner
        self.executor = executor
        self.checkpoint_manager = checkpoint_manager
        self.llm = llm_service
        
        self.phases = [
            ResearchPhase.PHASE_1_FUNDAMENTALS,
            ResearchPhase.PHASE_2_USE_CASES,
            ResearchPhase.PHASE_3_BEST_PRACTICES
        ]
    
    async def execute(self, query: str, session_id: str) -> ResearchReport:
        """Main entry point for phased research"""
        
        # Emit research start event
        await self._emit_phase_transition(ResearchPhase.PHASE_1_FUNDAMENTALS)
        
        for phase in self.phases:
            await self._execute_phase(phase, query, session_id)
        
        # Compilation phase
        return await self._compile_report(session_id, query)
    
    async def _execute_phase(
        self,
        phase: ResearchPhase,
        query: str,
        session_id: str
    ):
        """Execute a single research phase with reflection loop"""
        
        # Generate phase-specific plan
        phase_goal = self._get_phase_goal(phase, query)
        plan = await self.planner.plan(phase_goal)
        
        # Execute plan with reflective loop
        collected_notes = []
        collected_sources = []
        
        for action in plan.actions:
            # Execute with reflection
            result = await self.executor.execute_with_reflection(
                action=action,
                context=self._build_context(collected_notes),
                phase=phase
            )
            
            # Accumulate learnings
            collected_notes.append(result.learned)
            if result.action_result.sources:
                collected_sources.extend(result.action_result.sources)
            
            # Check if phase goal is satisfied
            if await self._is_phase_complete(phase, collected_notes, phase_goal):
                break
        
        # Save checkpoint for this phase
        phase_summary = await self._summarize_phase(collected_notes)
        await self.checkpoint_manager.save_checkpoint(
            session_id=session_id,
            phase=phase,
            notes=phase_summary,
            sources=collected_sources
        )
        
        # Emit phase completion
        await self._emit_phase_complete(phase, len(collected_notes))
        
        # Transition to next phase
        next_phase = self._get_next_phase(phase)
        if next_phase:
            await self._emit_phase_transition(next_phase)
    
    async def _compile_report(self, session_id: str, query: str) -> ResearchReport:
        """Final compilation phase: read all checkpoints and synthesize"""
        
        await self._emit_phase_transition(ResearchPhase.COMPILATION)
        
        # Retrieve all saved checkpoints
        checkpoints = await self.checkpoint_manager.retrieve_all_checkpoints(session_id)
        
        # Build compilation context
        compilation_prompt = f"""
        Original query: {query}
        
        You have completed a three-phase research investigation. Here are your notes:
        
        {self._format_checkpoints(checkpoints)}
        
        Now write a comprehensive, well-structured research report that synthesizes 
        all findings. Include:
        1. Executive summary
        2. Key findings organized by theme
        3. Detailed analysis
        4. Sources and citations
        """
        
        # Stream the report generation
        report_text = ""
        async for chunk in self.llm.stream_completion(compilation_prompt):
            report_text += chunk
            await self._emit_stream_event(chunk, phase="compilation")
        
        return ResearchReport(
            query=query,
            content=report_text,
            checkpoints=checkpoints,
            total_sources=self._count_unique_sources(checkpoints)
        )
    
    def _get_phase_goal(self, phase: ResearchPhase, query: str) -> str:
        """Map phase to specific research goal"""
        templates = {
            ResearchPhase.PHASE_1_FUNDAMENTALS: 
                f"Research fundamentals: What is {query}? How does it work? How is it set up?",
            ResearchPhase.PHASE_2_USE_CASES: 
                f"Research applications: How is {query} used in practice? What are real-world examples?",
            ResearchPhase.PHASE_3_BEST_PRACTICES: 
                f"Research advanced usage: What are best practices, advanced features, and architecture patterns for {query}?"
        }
        return templates[phase]
    
    async def _is_phase_complete(
        self,
        phase: ResearchPhase,
        collected_notes: List[str],
        phase_goal: str
    ) -> bool:
        """Use LLM to judge if phase goal has been satisfied"""
        
        # Heuristic: minimum 5 actions per phase
        if len(collected_notes) < 5:
            return False
        
        # LLM judgment
        judgment_prompt = f"""
        Phase goal: {phase_goal}
        
        Notes collected so far:
        {chr(10).join(collected_notes)}
        
        Has this phase goal been adequately satisfied? Answer YES or NO.
        """
        
        response = await self.llm.complete(judgment_prompt, max_tokens=10)
        return "YES" in response.upper()
```

---

### 3.2 Integrate with DeepResearchFlow

**Problem:** Deep research approval infrastructure exists but is bypassed.

**Modification:** `backend/app/domain/services/flows/plan_act.py:1904`

```python
# Current (bypasses manager):
if deep_research:
    return await self._wide_research_path(...)

# New (uses proper flow):
if deep_research:
    # Route to phased research flow
    phased_flow = PhasedResearchFlow(
        planner=self.planner,
        executor=ReflectiveExecutor(self.tool_executor),
        checkpoint_manager=CheckpointManager(self.repo),
        llm_service=self.llm
    )
    return await phased_flow.execute(query, session_id)
```

**Integration with existing DeepResearchFlow:**

```python
# backend/app/core/deep_research_manager.py:40

class DeepResearchManager:
    async def execute_approved_research(self, session_id: str, query: str):
        # Use PhasedResearchFlow as the execution engine
        flow = PhasedResearchFlow(...)
        return await flow.execute(query, session_id)
```

---

## Phase 4: Frontend Integration

### 4.1 Phase Progress Component

**New file:** `frontend/src/components/ResearchPhaseIndicator.vue`

```vue
<template>
  <div class="research-phases">
    <div 
      v-for="phase in phases" 
      :key="phase.id"
      :class="['phase', phaseStatus(phase)]"
    >
      <div class="phase-icon">{{ phase.icon }}</div>
      <div class="phase-label">{{ phase.label }}</div>
      <div v-if="phase.id === currentPhase" class="phase-progress">
        <span class="action-count">{{ actionCount }} actions</span>
      </div>
      <div v-if="isComplete(phase)" class="checkpoint-indicator">
        ✓ Notes saved
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const phases = [
  { id: 'phase_1_fundamentals', label: 'Fundamentals', icon: '📚' },
  { id: 'phase_2_use_cases', label: 'Use Cases', icon: '🔍' },
  { id: 'phase_3_best_practices', label: 'Best Practices', icon: '⚡' },
  { id: 'compilation', label: 'Compilation', icon: '📝' }
]

const phaseStatus = (phase) => {
  if (phase.id === currentPhase.value) return 'active'
  if (completedPhases.value.includes(phase.id)) return 'complete'
  return 'pending'
}
</script>
```

**Integration point:** `frontend/src/pages/ChatPage.vue:1435`
- Add `<ResearchPhaseIndicator />` to deep research UI
- Subscribe to phase transition events

---

### 4.2 Reflection Stream Display

**Modification:** `frontend/src/components/WideResearchOverlay.vue:200`

```vue
<template>
  <div class="research-overlay">
    <!-- Existing phase indicator -->
    <ResearchPhaseIndicator 
      :current-phase="currentPhase"
      :completed-phases="completedPhases"
      :action-count="actionCount"
    />
    
    <!-- NEW: Reflection stream -->
    <div class="reflection-stream">
      <div 
        v-for="reflection in recentReflections" 
        :key="reflection.id"
        class="reflection-card"
      >
        <div class="learned">💡 {{ reflection.learned }}</div>
        <div class="next-step">⏭️ {{ reflection.nextStep }}</div>
      </div>
    </div>
    
    <!-- Existing aggregation animation -->
    <WideResearchAnimation :status="status" />
  </div>
</template>
```

---

### 4.3 Event Handlers for New Events

**Modification:** `frontend/src/composables/useWideResearch.ts:47`

```typescript
// Add new event types
type ResearchEvent = 
  | { type: 'phase_transition', phase: string }
  | { type: 'reflection', learned: string, nextStep: string }
  | { type: 'checkpoint_saved', phase: string, noteCount: number }
  | { type: 'stream', content: string, phase: string }

const handleResearchEvent = (event: ResearchEvent) => {
  switch (event.type) {
    case 'phase_transition':
      currentPhase.value = event.phase
      break
      
    case 'reflection':
      recentReflections.value.push({
        id: crypto.randomUUID(),
        learned: event.learned,
        nextStep: event.nextStep,
        timestamp: Date.now()
      })
      // Keep only last 5 reflections visible
      if (recentReflections.value.length > 5) {
        recentReflections.value.shift()
      }
      break
      
    case 'checkpoint_saved':
      completedPhases.value.push(event.phase)
      showCheckpointToast(event.phase, event.noteCount)
      break
      
    case 'stream':
      // Update phase-specific stream content
      streamContent.value += event.content
      break
  }
}
```

---

## Phase 5: Skill System Integration

### 5.1 Update Research Skill with Phase Instructions

**Modification:** `backend/app/infrastructure/seeds/skills_seed.py:86`

```python
RESEARCH_SKILL_INSTRUCTIONS = """
You are conducting structured, phased research. Follow this workflow:

PHASE 1 - FUNDAMENTALS (5-8 actions):
- Search for official documentation and introductions
- Read getting started guides
- Examine basic configuration and setup
- Reflect after each action: "LEARNED: ... NEXT: ..."
- When fundamentals are clear, execute: save_checkpoint(phase=1, notes="...")

PHASE 2 - USE CASES (5-8 actions):  
- Search for real-world examples and case studies
- Visit specific implementations
- Read blog posts and user experiences
- Reflect after each action
- When use cases are understood, execute: save_checkpoint(phase=2, notes="...")

PHASE 3 - BEST PRACTICES (5-8 actions):
- Explore advanced features and architecture
- Read best practices documentation
- Examine edge cases and limitations
- Reflect after each action
- When advanced knowledge is captured, execute: save_checkpoint(phase=3, notes="...")

COMPILATION PHASE:
- Read all saved checkpoints
- Synthesize into comprehensive report
- Include citations and sources

CRITICAL RULES:
1. After EVERY action, emit a reflection: what you learned + what you'll do next
2. Save checkpoint at the end of each phase
3. Do not skip phases
4. Minimum 5 actions per phase before checkpoint
"""
```

---

### 5.2 Add Checkpoint Tool to Research Skill

**New tool definition:**

```python
# backend/app/domain/services/tools/research_tools.py

class SaveCheckpointTool(BaseTool):
    name = "save_checkpoint"
    description = "Save research notes from completed phase"
    
    parameters = {
        "type": "object",
        "properties": {
            "phase": {
                "type": "integer",
                "enum": [1, 2, 3],
                "description": "Phase number (1=Fundamentals, 2=Use Cases, 3=Best Practices)"
            },
            "notes": {
                "type": "string",
                "description": "Summary of key learnings from this phase"
            }
        },
        "required": ["phase", "notes"]
    }
    
    async def execute(self, phase: int, notes: str, context: ToolContext):
        phase_enum = {
            1: ResearchPhase.PHASE_1_FUNDAMENTALS,
            2: ResearchPhase.PHASE_2_USE_CASES,
            3: ResearchPhase.PHASE_3_BEST_PRACTICES
        }[phase]
        
        await context.checkpoint_manager.save_checkpoint(
            session_id=context.session_id,
            phase=phase_enum,
            notes=notes,
            sources=context.collected_sources
        )
        
        return {
            "status": "checkpoint_saved",
            "phase": phase,
            "note_length": len(notes)
        }
```

---

## Phase 6: Testing & Validation

### 6.1 Unit Tests

**New test files:**

```python
# tests/unit/test_reflective_executor.py
async def test_execute_with_reflection():
    executor = ReflectiveExecutor(mock_llm)
    result = await executor.execute_with_reflection(
        action=ToolCall(tool="web_search", params={"query": "test"}),
        context=ExecutionContext(),
        phase=ResearchPhase.PHASE_1_FUNDAMENTALS
    )
    
    assert result.learned is not None
    assert result.next_step is not None
    assert "LEARNED:" in result.learned

# tests/unit/test_checkpoint_manager.py
async def test_save_and_retrieve_checkpoints():
    manager = CheckpointManager(mock_repo)
    
    await manager.save_checkpoint(
        session_id="test-123",
        phase=ResearchPhase.PHASE_1_FUNDAMENTALS,
        notes="Test notes",
        sources=["https://example.com"]
    )
    
    checkpoints = await manager.retrieve_all_checkpoints("test-123")
    assert len(checkpoints) == 1
    assert checkpoints[0].phase == ResearchPhase.PHASE_1_FUNDAMENTALS
```

---

### 6.2 Integration Tests

```python
# tests/integration/test_phased_research_flow.py
async def test_full_research_workflow():
    """Test complete three-phase research with compilation"""
    
    flow = PhasedResearchFlow(
        planner=TestPlanner(),
        executor=TestReflectiveExecutor(),
        checkpoint_manager=TestCheckpointManager(),
        llm_service=TestLLM()
    )
    
    report = await flow.execute(
        query="research CodeRabbit",
        session_id="test-session"
    )
    
    # Verify all phases completed
    assert len(flow.checkpoint_manager.checkpoints) == 3
    
    # Verify phases in order
    phases = [cp.phase for cp in flow.checkpoint_manager.checkpoints]
    assert phases == [
        ResearchPhase.PHASE_1_FUNDAMENTALS,
        ResearchPhase.PHASE_2_USE_CASES,
        ResearchPhase.PHASE_3_BEST_PRACTICES
    ]
    
    # Verify compilation includes all checkpoints
    assert "fundamentals" in report.content.lower()
    assert "use cases" in report.content.lower()
    assert "best practices" in report.content.lower()
```

---

### 6.3 End-to-End Tests

```typescript
// tests/e2e/research_workflow.spec.ts
test('phased research shows progress indicators', async ({ page }) => {
  await page.goto('/chat')
  
  // Trigger deep research
  await page.fill('[data-testid="chat-input"]', 'research CodeRabbit')
  await page.click('[data-testid="deep-research-toggle"]')
  await page.click('[data-testid="send-button"]')
  
  // Verify phase 1 indicator appears
  await expect(page.locator('.phase.active')).toContainText('Fundamentals')
  
  // Wait for reflection events
  await expect(page.locator('.reflection-card').first()).toBeVisible()
  const reflection = await page.locator('.learned').first().textContent()
  expect(reflection).toContain('💡')
  
  // Verify checkpoint saved
  await expect(page.locator('.checkpoint-indicator')).toContainText('✓ Notes saved')
  
  // Verify phase transition
  await expect(page.locator('.phase.active')).toContainText('Use Cases')
  
  // Verify final compilation
  await expect(page.locator('.phase.active')).toContainText('Compilation')
  await expect(page.locator('.research-report')).toBeVisible()
})
```

---

## Phase 7: Rollout Strategy

### 7.1 Feature Flag

```python
# backend/app/core/config.py

class Settings(BaseSettings):
    # Existing settings...
    
    # New feature flags
    ENABLE_PHASED_RESEARCH: bool = False  # Start disabled
    PHASED_RESEARCH_MIN_ACTIONS_PER_PHASE: int = 5
    PHASED_RESEARCH_MAX_ACTIONS_PER_PHASE: int = 12
```

**Usage:**

```python
# backend/app/domain/services/flows/plan_act.py

if deep_research:
    if settings.ENABLE_PHASED_RESEARCH:
        # New phased flow
        return await PhasedResearchFlow(...).execute(...)
    else:
        # Legacy wide research path
        return await self._wide_research_path(...)
```

---

### 7.2 Gradual Rollout Plan

**Week 1-2: Internal Testing**
- Enable `ENABLE_PHASED_RESEARCH=true` for development environment
- Team tests with real research queries
- Collect feedback on phase definitions and transition smoothness

**Week 3: Beta Users**
- Enable for 5% of users via feature flag
- Monitor metrics:
  - Average actions per phase
  - Checkpoint save success rate
  - Time to completion vs legacy flow
  - User satisfaction (thumbs up/down)

**Week 4: Expanded Beta**
- Increase to 25% of users
- Analyze qualitative feedback on UI clarity
- Iterate on reflection prompt quality

**Week 5-6: Full Rollout**
- Enable for 100% of users
- Make phased research the default `deep_research` implementation
- Deprecate legacy wide research path

---

### 7.3 Monitoring & Observability

**Key metrics to track:**

```python
# backend/app/domain/services/flows/phased_research.py

class PhasedResearchFlow:
    async def _emit_metrics(self, event_type: str, metadata: dict):
        await self.metrics.track(
            event="phased_research",
            properties={
                "event_type": event_type,  # phase_start, phase_complete, checkpoint_saved, etc.
                "session_id": self.session_id,
                "phase": metadata.get("phase"),
                "action_count": metadata.get("action_count"),
                "duration_seconds": metadata.get("duration"),
                "checkpoint_size_bytes": metadata.get("checkpoint_size")
            }
        )
```

**Dashboard queries:**

- Average actions per phase (target: 5-8)
- Phase completion rates (should be ~100%)
- Checkpoint retrieval success rate during compilation (should be 100%)
- User satisfaction by flow type (phased vs legacy)

---

## Phase 8: Documentation & Training

### 8.1 Developer Documentation

**New file:** `docs/architecture/phased_research_flow.md`

```markdown
# Phased Research Flow Architecture

## Overview
The phased research flow implements a structured three-phase methodology for deep research tasks...

## Components
- `PhasedResearchFlow`: Main orchestrator
- `ReflectiveExecutor`: Wraps actions with reflection
- `CheckpointManager`: Persists intermediate research notes
- `ResearchPhaseIndicator.vue`: Frontend progress UI

## Event Flow
[Sequence diagram showing SSE events from backend to frontend]

## Adding New Phases
To add a new research phase:
1. Add enum value to `ResearchPhase`
2. Update `_get_phase_goal()` mapping
3. Update frontend phase indicator
4. Update skill instructions

## Debugging
Common issues and solutions...
```

---

### 8.2 User-Facing Documentation

**Help Center Article:**

> **Understanding Research Phases**
> 
> When you enable deep research, Claude now follows a structured three-phase approach:
> 
> 1. **Fundamentals** 📚 - Claude first learns what the topic is and how it works
> 2. **Use Cases** 🔍 - Claude explores real-world examples and applications  
> 3. **Best Practices** ⚡ - Claude investigates advanced features and expert recommendations
> 
> After each phase, Claude saves its research notes as a checkpoint. You'll see a ✓ indicator when each phase completes. Finally, Claude compiles all findings into a comprehensive report.
> 
> **Why phases?** This prevents information overload and ensures systematic coverage of the topic from basic to advanced.

---

## Success Criteria

### Technical Metrics
- [ ] All phases complete successfully for 95%+ of research tasks
- [ ] Checkpoint save success rate > 99%
- [ ] Average time per phase: 2-4 minutes
- [ ] Zero data loss during checkpoint retrieval
- [ ] SSE events carry phase information correctly

### User Experience Metrics
- [ ] Users can clearly see which phase is active
- [ ] Reflections appear within 5 seconds of action completion
- [ ] Phase transitions are visually obvious
- [ ] Final reports reference all three phases

### Code Quality Metrics
- [ ] 90%+ test coverage for new components
- [ ] All integration tests passing
- [ ] No performance regression vs legacy flow
- [ ] Zero critical bugs in production after 2 weeks

---

## Risk Mitigation

### Risk: LLM hallucination in reflection generation
**Mitigation:** 
- Use short max_tokens (100-150) for reflection prompts
- Parse and validate reflection structure before emitting
- Fall back to generic reflection if parsing fails

### Risk: Phase gets stuck (never completes)
**Mitigation:**
- Hard limit on actions per phase (max 12)
- Timeout after 10 minutes per phase
- Emit warning event and auto-transition to next phase

### Risk: Checkpoint persistence failure
**Mitigation:**
- Retry logic with exponential backoff
- Log failures to monitoring system
- Fall back to in-memory storage if DB unavailable
- Surface error to user if all retries fail

### Risk: Breaking changes to existing deep research users
**Mitigation:**
- Feature flag allows rollback
- Legacy flow remains available during transition
- A/B test with small percentage before full rollout

---

## Appendix: Sample Event Sequence

```
User sends: "research CodeRabbit"

SSE Event Stream:
1. { type: "phase_transition", phase: "phase_1_fundamentals" }
2. { type: "stream", content: "Searching for CodeRabbit documentation", phase: "phase_1" }
3. { type: "reflection", learned: "CodeRabbit is an AI code review tool", nextStep: "I'll examine its GitHub integration" }
4. { type: "stream", content: "Fetching GitHub integration docs", phase: "phase_1" }
5. { type: "reflection", learned: "Integrates via YAML config file", nextStep: "I'll review example configurations" }
6. ...
7. { type: "checkpoint_saved", phase: "phase_1_fundamentals", noteCount: 847 }
8. { type: "phase_transition", phase: "phase_2_use_cases" }
9. { type: "stream", content: "Searching for case studies", phase: "phase_2" }
10. ...
[continues through all phases]
28. { type: "phase_transition", phase: "compilation" }
29. { type: "stream", content: "# CodeRabbit Research Report\n\n## Executive Summary...", phase: "compilation" }
30. { type: "research_complete", total_sources: 47, total_actions: 23 }
```

---

## Next Steps

1. **Immediate (Week 1):**
   - Implement `ResearchPhase` domain model
   - Fix SSE schema to include phase field
   - Create `CheckpointManager` skeleton

2. **Short-term (Week 2-3):**
   - Build `ReflectiveExecutor`
   - Implement `PhasedResearchFlow` core logic
   - Add database migration for checkpoints table

3. **Medium-term (Week 4-6):**
   - Build frontend components
   - Wire up SSE event handlers
   - Write comprehensive tests

4. **Long-term (Week 7-8):**
   - Beta rollout with monitoring
   - Iterate based on user feedback
   - Full production deployment

---

**Estimated Total Effort:** 6-8 weeks (2 engineers)

**Key Dependencies:**
- Database migration approval
- UX design review for phase indicator UI
- Product approval for breaking changes to deep research UX

**Blockers to Address:**
- Confirm LLM token budget for reflection generation
- Decide on checkpoint retention policy (30 days? 90 days?)
- Align with existing DeepResearchFlow team on merger strategy
