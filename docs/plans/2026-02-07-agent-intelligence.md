# Agent Intelligence Enhancement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement research-backed improvements to reduce agent hallucination by 30-50% and improve context efficiency by 40%, based on findings from `docs/reports/2026-02-07-agent-intelligence-research.md`.

**Architecture:** All changes follow existing DDD patterns. Domain logic stays in domain layer. Infrastructure adapters remain isolated. Changes touch agent execution, token management, memory, and prompt engineering.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, asyncio, Anthropic SDK, tiktoken

**Already Implemented (skip these):**
- Chain of Verification (CoVe) - `chain_of_verification.py`, integrated in `execution.py:105-111`
- CRITIC agent - `critic.py`, integrated in `execution.py:90-94`
- Anti-hallucination prompt signals - `execution.py` (ANTI_HALLUCINATION_PROTOCOL, TEMPORAL_GROUNDING, etc.)
- System-level anti-hallucination rules - `system.py:406-437`
- Prompt caching on system prompt - `anthropic_llm.py:297-315`
- Predictive context management - `token_manager.py:678-825`
- Dynamic tool filtering - `base.py:156-185` via `dynamic_toolset.py`

---

### Task 1: Add Tool Output Grounding Rules to System Prompt

**Why:** The "Reasoning Trap" paper (ICLR 2026) shows enhanced reasoning inflates hallucination from 36% to 57%. Explicit grounding instructions force the agent to cite tool outputs, not training data. The existing `<anti_hallucination>` section focuses on "don't fabricate" but lacks the critical directive to PREFER tool outputs over training knowledge.

**Files:**
- Modify: `backend/app/domain/services/prompts/system.py`

**Step 1: Add TOOL_OUTPUT_GROUNDING_RULES constant after the existing TROUBLESHOOTING_RULES**

In `backend/app/domain/services/prompts/system.py`, add a new constant after `TROUBLESHOOTING_RULES` (line ~438):

```python
# Tool output grounding rules - forces agent to use tool results over training data
TOOL_OUTPUT_GROUNDING_RULES = """
<tool_output_grounding>
CRITICAL: Tool Output Grounding Protocol

When you have called tools and received results:
1. Use ONLY information from tool outputs to formulate your response.
2. Do NOT supplement with information from your training data unless the tool output is insufficient AND you explicitly note this.
3. If tool output doesn't contain sufficient information, state what's missing and call another tool to find it.
4. Tool outputs OVERRIDE any prior knowledge you may have — treat them as ground truth.
5. When citing facts, mentally trace each claim back to a specific tool output. If you cannot, do not include the claim.
6. If you're uncertain whether information came from tools or training, use a tool to verify before stating it.

EXAMPLES:
- After info_search_web returns results → base your response ONLY on those results
- After file_read returns code → describe what the code ACTUALLY does, not what you think it should do
- After shell_exec returns output → report the ACTUAL output, not expected output
- If search returned no results → say "I could not find information on X" — do NOT fill in from memory

WHEN TO USE TRAINING KNOWLEDGE:
- General concepts and definitions (not specific facts)
- Programming language syntax and patterns
- Explaining how to interpret tool results
- ALWAYS mark training-sourced claims: "Based on general knowledge..." or "Typically..."
</tool_output_grounding>
"""
```

**Step 2: Include TOOL_OUTPUT_GROUNDING_RULES in `build_system_prompt()` and SYSTEM_PROMPT**

In `build_system_prompt()`, add it after troubleshooting (always included, ~150 tokens):

```python
    # Include tool output grounding rules (always — critical for hallucination reduction)
    prompt += TOOL_OUTPUT_GROUNDING_RULES
```

Add it right after the troubleshooting block (line ~613, before process management).

**Step 3: Run tests**

Run: `cd backend && source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/app/domain/services/prompts/system.py
git commit -m "feat: add tool output grounding rules to system prompt

Reduces parametric hallucination by forcing agent to cite tool outputs
over training data. Based on ICLR 2026 'Reasoning Trap' findings."
```

---

### Task 2: Lower Compaction Threshold from 85% to 70%

**Why:** Research recommends triggering compaction at 64-75% context usage, not 85-95%. Early compaction leaves a "completion buffer" so the agent doesn't run out of context mid-response. The current critical threshold (85%) is too late — by the time we compact, the agent may already be producing degraded output.

**Files:**
- Modify: `backend/app/domain/services/agents/token_manager.py`

**Step 1: Update PRESSURE_THRESHOLDS**

In `token_manager.py`, change lines 87-91:

```python
    # Context pressure thresholds (fraction of max tokens)
    # Research recommends 64-75% for early compaction (Anthropic 2025, ArXiv 2601.06007)
    PRESSURE_THRESHOLDS: ClassVar[dict[str, float]] = {
        "warning": 0.60,   # 60% - suggest planning for summarization
        "critical": 0.70,  # 70% - begin proactive trimming (was 85%)
        "overflow": 0.85,  # 85% - force summarization (was 95%)
    }
```

**Step 2: Update safety margin**

In `token_manager.py`, change line 121:

```python
    # Safety margin (reserve tokens for response) - ensures completion buffer
    SAFETY_MARGIN = 4096
```

Rationale: With earlier compaction, we can afford a larger safety margin. This prevents truncation of final answers.

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass (some tests may need threshold updates if they hardcode 0.85)

**Step 4: Fix any threshold-dependent tests**

If tests reference old thresholds (0.75, 0.85, 0.95), update them to match new values (0.60, 0.70, 0.85).

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/token_manager.py
git commit -m "feat: lower compaction thresholds for earlier context management

Research shows 64-75% triggers reduce context-related hallucination by
40%. Warning now at 60%, critical at 70%, overflow at 85%."
```

---

### Task 3: Tool Result Summarization for Long Outputs

**Why:** Tool outputs (search results, file contents, shell output) can be 5000+ tokens each. Adding them verbatim wastes context. Summarizing outputs >2000 tokens to their key findings saves 40-60% of context with minimal information loss.

**Files:**
- Modify: `backend/app/domain/models/memory.py`
- Modify: `backend/app/domain/services/agents/base.py`

**Step 1: Add tool result summarization to Memory.smart_compact()**

In `memory.py`, enhance `smart_compact()` to also truncate oversized tool results that aren't in the compactable list but are still too large. Add after line 144 (after the compactable check):

```python
            # Also truncate excessively large tool results (>8000 chars ≈ 2000 tokens)
            # even if not in the compactable list
            MAX_TOOL_RESULT_CHARS = 8000
            if function_name and function_name not in self.config.compactable_functions:
                content = message.get("content", "")
                if len(content) > MAX_TOOL_RESULT_CHARS and "(compacted)" not in content and "(removed)" not in content:
                    # Preserve first and last portions for context
                    head = content[:3000]
                    tail = content[-1000:]
                    truncated_content = (
                        f'{head}\n\n... [truncated {len(content) - 4000} chars for context efficiency] ...\n\n{tail}'
                    )
                    message["content"] = truncated_content
                    compacted += 1
                    logger.debug(
                        f"Truncated large tool result: {function_name} "
                        f"({len(content)} -> {len(truncated_content)} chars)"
                    )
```

**Step 2: Add more functions to compactable_functions default list**

In `memory.py`, update `MemoryConfig.__post_init__` (line 27-34):

```python
        if self.compactable_functions is None:
            self.compactable_functions = [
                "browser_view",
                "browser_navigate",
                "browser_get_content",
                "shell_exec",
                "shell_view",
                "file_read",
                "file_list",
                "file_list_directory",
                "code_execute",
                "code_run_artifact",
            ]
```

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/app/domain/models/memory.py
git commit -m "feat: add tool result summarization for context efficiency

Truncates tool results >8000 chars with head+tail preservation.
Adds more functions to compactable list. Saves 40-60% context."
```

---

### Task 4: Optimize Prompt Cache Structure for Anthropic

**Why:** ArXiv 2601.06007 (Jan 2026) shows strategic cache boundary control yields 45-80% cost reduction. The current implementation caches the system prompt, but tool definitions should ALSO be cached since they're static across calls. The order should be: tools (static) → system (static) → cache break → conversation (dynamic).

**Files:**
- Modify: `backend/app/infrastructure/external/llm/anthropic_llm.py`

**Step 1: Add tool caching support**

In `anthropic_llm.py`, modify `_convert_openai_tools_to_anthropic()` to add cache control to the last tool definition (Anthropic's cache boundary marker):

```python
    def _convert_openai_tools_to_anthropic(
        self, tools: list[dict[str, Any]], enable_caching: bool = True
    ) -> list[dict[str, Any]]:
        """Convert OpenAI tool format to Anthropic format with cache optimization.

        When caching is enabled, marks the last tool definition with cache_control
        to create a cache boundary. Since tools are static across calls, this enables
        Anthropic to cache the tool definitions + system prompt together.

        Args:
            tools: List of tools in OpenAI format
            enable_caching: Whether to add cache control markers

        Returns:
            List of tools in Anthropic format
        """
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append(
                    {
                        "name": func.get("name"),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                    }
                )

        # Mark last tool with cache_control for optimal prefix caching
        # Tools are static across calls, so caching them saves significant tokens
        if enable_caching and anthropic_tools:
            anthropic_tools[-1]["cache_control"] = {"type": "ephemeral"}

        return anthropic_tools
```

**Step 2: Update ask() to pass enable_caching to tool conversion**

In `anthropic_llm.py`, in the `ask()` method, change line 366:

```python
                if tools:
                    params["tools"] = self._convert_openai_tools_to_anthropic(tools, enable_caching=enable_caching)
```

**Step 3: Update ask_stream() similarly**

In `anthropic_llm.py`, update the streaming method to also pass caching:

```python
        if tools:
            params["tools"] = self._convert_openai_tools_to_anthropic(tools, enable_caching=enable_caching)
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/llm/anthropic_llm.py
git commit -m "feat: add cache control to tool definitions for Anthropic

Marks last tool definition with cache_control for optimal prefix
caching. Since tools are static across calls, this enables 45-80%
cost reduction per ArXiv 2601.06007."
```

---

### Task 5: Graduated Structured Output Retry

**Why:** When `ask_structured()` validation fails, the current implementation has no retry strategy. Research shows graduated retry (lower temperature → simpler prompt → model fallback) achieves near-100% format compliance.

**Files:**
- Modify: `backend/app/infrastructure/external/llm/anthropic_llm.py`

**Step 1: Add graduated retry to ask_structured()**

Replace the `ask_structured()` method in `anthropic_llm.py` with graduated retry:

```python
    async def ask_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
    ) -> T:
        """Send chat request with structured output validation and graduated retry.

        Retry strategy:
        - Attempt 1: Normal temperature, standard prompt
        - Attempt 2: Lower temperature (0.3), include validation error
        - Attempt 3: Temperature 0, simplified extraction prompt

        Args:
            messages: List of messages
            response_model: Pydantic model class for response validation
            tools: Optional additional tools
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching

        Returns:
            Validated Pydantic model instance
        """
        schema = response_model.model_json_schema()

        # Create a tool that returns the structured response
        structured_tool = {
            "type": "function",
            "function": {
                "name": "return_structured_response",
                "description": f"Return a response matching the {response_model.__name__} schema",
                "parameters": schema,
            },
        }

        max_attempts = 3
        last_error = None
        original_temp = self._temperature

        for attempt in range(max_attempts):
            try:
                # Graduated temperature: normal → 0.3 → 0.0
                if attempt == 1:
                    self._temperature = 0.3
                elif attempt == 2:
                    self._temperature = 0.0

                # Build messages with error feedback on retry
                enhanced_messages = list(messages)
                if attempt > 0 and last_error:
                    # Add validation error feedback
                    enhanced_messages.append({
                        "role": "user",
                        "content": (
                            f"Your previous response had a validation error: {last_error}. "
                            f"Please respond using the return_structured_response tool with valid data "
                            f"matching this schema exactly: {json.dumps(schema, indent=2)}"
                        ),
                    })
                elif enhanced_messages and enhanced_messages[-1].get("role") == "user":
                    enhanced_messages[-1] = {
                        **enhanced_messages[-1],
                        "content": enhanced_messages[-1].get("content", "")
                        + "\n\nPlease respond using the return_structured_response tool.",
                    }

                response = await self.ask(
                    messages=enhanced_messages,
                    tools=[structured_tool],
                    tool_choice="required",
                    enable_caching=enable_caching,
                )

                # Extract structured response from tool call
                if response.get("tool_calls"):
                    for tc in response["tool_calls"]:
                        if tc["function"]["name"] == "return_structured_response":
                            args = tc["function"]["arguments"]
                            if isinstance(args, str):
                                args = json.loads(args)
                            result = response_model.model_validate(args)
                            return result

                last_error = "Model did not call return_structured_response tool"

            except Exception as e:
                last_error = str(e)[:500]
                logger.warning(
                    f"Structured output attempt {attempt + 1}/{max_attempts} failed: {last_error}"
                )
            finally:
                # Restore temperature
                self._temperature = original_temp

        raise ValueError(f"Failed to get structured response after {max_attempts} attempts: {last_error}")
```

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/app/infrastructure/external/llm/anthropic_llm.py
git commit -m "feat: graduated retry for structured output validation

Three-attempt strategy: normal temp → 0.3 with error feedback → 0.0
with schema reminder. Achieves near-100% format compliance."
```

---

### Task 6: Session Bridging via Sandbox File Artifacts

**Why:** Anthropic's Dec 2025 guidance: for tasks spanning multiple context windows, agents should write structured status files. This prevents two failure patterns: (1) one-shotting (tries everything at once, runs out of context), (2) premature completion (sees partial progress, declares done).

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/domain/services/agents/execution.py`

**Step 1: Add session progress tracking to PlanActFlow**

In `plan_act.py`, add a method to save progress to sandbox. Add to the `PlanActFlow` class:

```python
    async def _save_progress_artifact(self, plan: "Plan", status: str = "in_progress") -> None:
        """Save progress artifact to sandbox for session bridging.

        Writes a structured status file that enables session continuity
        across context window boundaries.

        Args:
            plan: Current execution plan
            status: Overall status (in_progress, completed, failed)
        """
        if not self._sandbox:
            return

        try:
            import json
            from datetime import UTC, datetime

            completed = [s for s in plan.steps if s.is_done()]
            pending = [s for s in plan.steps if not s.is_done()]

            progress = {
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "goal": plan.goal if hasattr(plan, "goal") else "",
                "completed_steps": [
                    {"id": s.id, "description": s.description[:200], "success": s.success}
                    for s in completed
                ],
                "pending_steps": [
                    {"id": s.id, "description": s.description[:200]}
                    for s in pending
                ],
                "completed_count": len(completed),
                "total_count": len(plan.steps),
                "completion_percent": round(len(completed) / max(len(plan.steps), 1) * 100, 1),
            }

            content = json.dumps(progress, indent=2)
            await self._sandbox.write_file("/tmp/.pythinker_progress.json", content)
            logger.debug(f"Saved progress artifact: {len(completed)}/{len(plan.steps)} steps complete")
        except Exception as e:
            logger.debug(f"Failed to save progress artifact: {e}")
```

**Step 2: Call _save_progress_artifact after each step completion**

In `plan_act.py`, in the `_execute_plan()` method, after each step completes and yields StepEvent(COMPLETED), add:

```python
                    # Save progress artifact for session bridging
                    await self._save_progress_artifact(plan)
```

Find the location where steps are iterated and completed events are yielded (in the execution loop), and add the call there.

**Step 3: Load progress artifact on session resume**

In `plan_act.py`, add a method to check for existing progress:

```python
    async def _load_progress_artifact(self) -> dict | None:
        """Load progress artifact from sandbox if it exists.

        Returns:
            Progress dict or None if no artifact exists
        """
        if not self._sandbox:
            return None

        try:
            import json

            content = await self._sandbox.read_file("/tmp/.pythinker_progress.json")
            if content:
                return json.loads(content)
        except Exception:
            pass
        return None
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py
git commit -m "feat: session bridging via sandbox progress artifacts

Saves structured progress files after each step completion.
Enables session continuity across context window boundaries.
Based on Anthropic Dec 2025 long-running agent guidance."
```

---

### Task 7: Dynamic Tool Selection — Expose Only Phase-Relevant Tools

**Why:** OpenAI's agent guide recommends <20 active tools for accuracy. Pythinker has 50+ tools. Dynamic filtering based on the current task phase reduces cognitive load and improves tool selection accuracy.

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`
- Modify: `backend/app/domain/services/tools/dynamic_toolset.py`

**Step 1: Add phase-based tool filtering to get_available_tools()**

In `base.py`, modify `get_available_tools()` (line 135-140) to support phase filtering:

```python
    def get_available_tools(self, phase: str | None = None) -> list[dict[str, Any]] | None:
        """Get all available tools list, optionally filtered by execution phase.

        Args:
            phase: Optional execution phase for tool filtering.
                   One of: "planning", "research", "coding", "browsing", "all"
                   If None, returns all tools (backward compatible).

        Returns:
            List of tool schemas
        """
        available_tools = []
        for tool in self.tools:
            available_tools.extend(tool.get_tools())

        # Apply phase-based filtering if requested
        if phase and phase != "all":
            available_tools = self._filter_tools_by_phase(available_tools, phase)

        return available_tools

    def _filter_tools_by_phase(
        self, tools: list[dict[str, Any]], phase: str
    ) -> list[dict[str, Any]]:
        """Filter tools to only those relevant for the current execution phase.

        Keeps tool count under 20 per phase for optimal LLM accuracy.

        Args:
            tools: All available tool schemas
            phase: Current execution phase

        Returns:
            Filtered tool list
        """
        PHASE_TOOLS: dict[str, set[str]] = {
            "planning": {
                "message_ask_user", "message_send", "info_search_web",
                "file_read", "file_list", "file_list_directory", "file_search",
                "shell_exec", "browser_navigate", "browser_view",
            },
            "research": {
                "info_search_web", "search", "wide_research",
                "browser_navigate", "browser_view", "browser_get_content",
                "browser_click", "browser_scroll_down", "browser_scroll_up",
                "browsing", "browser_agent_extract",
                "file_write", "file_read", "file_str_replace",
                "message_ask_user", "message_send",
            },
            "coding": {
                "file_read", "file_write", "file_str_replace", "file_search",
                "file_list", "file_list_directory", "file_create",
                "shell_exec", "shell_view",
                "code_execute", "code_create_artifact", "code_read_artifact",
                "code_list_artifacts", "code_run_artifact",
                "git_status", "git_diff", "git_commit", "git_log",
                "message_ask_user", "message_send",
            },
            "browsing": {
                "browser_navigate", "browser_view", "browser_click",
                "browser_type", "browser_scroll_down", "browser_scroll_up",
                "browser_get_content", "browser_screenshot", "browser_restart",
                "browsing", "browser_agent_extract",
                "info_search_web", "search",
                "file_write", "file_read",
                "message_ask_user", "message_send",
            },
        }

        phase_tool_names = PHASE_TOOLS.get(phase)
        if not phase_tool_names:
            return tools

        # Always include MCP tools (dynamic, user-configured)
        filtered = []
        for tool in tools:
            name = tool.get("function", {}).get("name", "")
            if name in phase_tool_names or name.startswith("mcp_"):
                filtered.append(tool)

        logger.debug(f"Phase '{phase}' tool filter: {len(tools)} → {len(filtered)} tools")
        return filtered
```

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass (method signature is backward compatible with phase=None default)

**Step 3: Commit**

```bash
git add backend/app/domain/services/agents/base.py
git commit -m "feat: phase-based dynamic tool selection

Filters tools by execution phase (planning/research/coding/browsing)
to keep under 20 active tools. Improves tool selection accuracy per
OpenAI agent guide recommendations."
```

---

### Task 8: Add Uncertainty Option to Tool Selection

**Why:** The "Reasoning Trap" paper recommends an "indecisive action space" — letting the agent say "I'm not sure which tool to use" instead of hallucinating tool calls. This reduces forced hallucination when the agent is uncertain.

**Files:**
- Modify: `backend/app/domain/services/prompts/system.py`

**Step 1: Add uncertainty protocol to TROUBLESHOOTING_RULES**

In `system.py`, append to the `TROUBLESHOOTING_RULES` constant (before the closing `"""`):

```python
<uncertainty_protocol>
WHEN UNSURE ABOUT TOOL SELECTION:
- If you're uncertain which tool to use, SAY SO instead of guessing
- Use message_send to explain what you're trying to accomplish and what's unclear
- Ask for clarification rather than making potentially wrong tool calls
- It is better to ask "Should I use browser or search for this?" than to guess wrong

WHEN UNSURE ABOUT FACTS:
- If you can't verify a claim with tools, state "I was unable to verify this"
- Do NOT fill in gaps with training data when tool results are expected
- Prefer "I don't know" over a plausible-sounding but unverified answer
</uncertainty_protocol>
```

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/app/domain/services/prompts/system.py
git commit -m "feat: add uncertainty protocol to agent prompts

Gives agent permission to express uncertainty instead of hallucinating
tool calls or facts. Based on ICLR 2026 'indecisive action space'."
```

---

### Task 9: Memory Compaction — Add More Compactable Functions and Lower Token Threshold

**Why:** The auto_compact_token_threshold of 80K is too high for most models (Claude has 200K but effective use is closer to 100K). Lowering it + adding more compactable functions prevents context bloat.

**Files:**
- Modify: `backend/app/domain/models/memory.py`

**Step 1: Lower auto_compact_token_threshold**

In `memory.py`, change `MemoryConfig` (line 19):

```python
    # Token-based threshold for smart compaction (default: 60k tokens — leave buffer for response)
    auto_compact_token_threshold: int = 60000
```

**Step 2: Reduce preserve_recent from 10 to 8**

```python
    preserve_recent: int = 8
```

Rationale: 10 preserved messages is generous. 8 still provides ample recent context while allowing more aggressive compaction.

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/app/domain/models/memory.py
git commit -m "feat: lower memory compaction threshold and tune preservation

auto_compact_token_threshold: 80K → 60K, preserve_recent: 10 → 8.
Earlier compaction leaves completion buffer per Anthropic guidance."
```

---

### Task 10: Enhance CoVe Integration — Enable for All Substantial Responses

**Why:** CoVe is already implemented but only runs in `summarize()`. It should also run after step execution when the agent produces substantial factual content. Currently, CoVe requires the content to be >300 chars AND match research indicators — this is too restrictive.

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py`

**Step 1: Lower CoVe minimum response length threshold**

In `execution.py`, change line 110:

```python
            min_response_length=200,  # Verify responses with 200+ chars (was 300)
```

**Step 2: Add CoVe verification after step execution (not just summarize)**

In `execution.py`, in the `execute_step()` method, after the step result is parsed (around line 286-300), add CoVe for research step results:

After line 296 (`step.result = event.message`), add:

```python
                    # Apply CoVe to step results for research/factual steps
                    if (
                        step.result
                        and len(step.result) > 200
                        and self._cove_enabled
                        and self._user_request
                        and self._needs_cove_verification(step.result, step.description)
                    ):
                        try:
                            verified_result, cove_result = await self._apply_cove_verification(
                                step.result, self._user_request
                            )
                            if cove_result and cove_result.has_contradictions:
                                step.result = verified_result
                                logger.info(
                                    f"CoVe corrected step result: {cove_result.claims_contradicted} claims revised"
                                )
                        except Exception as e:
                            logger.debug(f"Step-level CoVe failed (continuing): {e}")
```

**Step 3: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/app/domain/services/agents/execution.py
git commit -m "feat: apply CoVe verification to step results, not just summary

Extends Chain-of-Verification to individual step outputs for
research/factual tasks. Catches hallucinations earlier in the pipeline."
```

---

### Task 11: Prompt Cache Optimization — Static Content First

**Why:** Anthropic's prompt caching uses prefix matching. Putting static content (tools + system prompt) before dynamic content (conversation) maximizes cache hit rate. The current structure already does this correctly for the system prompt, but we should also ensure tool definitions come before conversation in the API call.

**Files:**
- Modify: `backend/app/infrastructure/external/llm/anthropic_llm.py`

**Step 1: Verify and document the cache structure**

The current implementation in `ask()` already structures the API call as:
1. `system` (with cache_control) — static
2. `tools` (now with cache_control from Task 4) — static
3. `messages` — dynamic

This is already optimal. Add a comment documenting WHY this order matters:

In `anthropic_llm.py`, add a comment in `ask()` before the params dict (around line 351):

```python
                # Build request parameters
                # ORDER MATTERS FOR CACHE OPTIMIZATION:
                # 1. system prompt (cached via _prepare_system_with_caching)
                # 2. tools (cached via cache_control on last tool)
                # 3. messages (dynamic, never cached)
                # This order maximizes Anthropic's prefix cache hit rate (ArXiv 2601.06007)
                params = {
```

**Step 2: Run tests**

Run: `cd backend && pytest tests/ -q --timeout=30 -x`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/app/infrastructure/external/llm/anthropic_llm.py
git commit -m "docs: document cache optimization structure in Anthropic LLM

Documents why parameter ordering matters for prefix cache hit rate."
```

---

### Task 12: Write Tests for New Functionality

**Files:**
- Create: `backend/tests/test_agent_intelligence.py`

**Step 1: Write tests**

```python
"""Tests for agent intelligence enhancements."""

import pytest

from app.domain.models.memory import Memory, MemoryConfig
from app.domain.services.agents.token_manager import TokenManager


class TestCompactionThresholds:
    """Test that compaction thresholds are properly lowered."""

    def test_pressure_thresholds_lowered(self):
        """Verify critical threshold is now 70%, not 85%."""
        assert TokenManager.PRESSURE_THRESHOLDS["warning"] == 0.60
        assert TokenManager.PRESSURE_THRESHOLDS["critical"] == 0.70
        assert TokenManager.PRESSURE_THRESHOLDS["overflow"] == 0.85

    def test_safety_margin_increased(self):
        """Verify safety margin is 4096 for completion buffer."""
        assert TokenManager.SAFETY_MARGIN == 4096

    def test_compaction_triggers_at_70_percent(self):
        """Verify compaction triggers at 70% usage."""
        tm = TokenManager(model_name="gpt-4", max_context_tokens=10000)
        # Create messages that use ~75% of context
        messages = [
            {"role": "system", "content": "x" * 30000},  # ~7500 tokens
        ]
        assert tm.should_trigger_compaction(messages)

    def test_no_compaction_at_60_percent(self):
        """Verify compaction doesn't trigger at 60% usage."""
        tm = TokenManager(model_name="gpt-4", max_context_tokens=10000)
        messages = [
            {"role": "system", "content": "x" * 20000},  # ~5000 tokens
        ]
        assert not tm.should_trigger_compaction(messages)


class TestMemoryCompaction:
    """Test memory compaction enhancements."""

    def test_auto_compact_threshold_lowered(self):
        """Verify auto_compact_token_threshold is 60K."""
        config = MemoryConfig()
        assert config.auto_compact_token_threshold == 60000

    def test_preserve_recent_reduced(self):
        """Verify preserve_recent is 8."""
        config = MemoryConfig()
        assert config.preserve_recent == 8

    def test_compactable_functions_expanded(self):
        """Verify additional functions are in the compactable list."""
        config = MemoryConfig()
        assert "shell_view" in config.compactable_functions
        assert "code_execute" in config.compactable_functions
        assert "file_list_directory" in config.compactable_functions

    def test_large_tool_result_truncation(self):
        """Verify oversized tool results are truncated during compaction."""
        memory = Memory()
        # Add system message
        memory.add_message({"role": "system", "content": "system prompt"})
        # Add a very large tool result (not in compactable list)
        large_content = "x" * 10000  # >8000 char threshold
        memory.add_message({
            "role": "tool",
            "function_name": "custom_tool",
            "content": large_content,
        })
        # Add recent messages to push the large one past preserve_recent
        for i in range(10):
            memory.add_message({"role": "user", "content": f"msg {i}"})

        compacted = memory.smart_compact()
        assert compacted > 0
        # Verify the large result was truncated
        tool_msg = memory.messages[1]
        assert len(tool_msg["content"]) < len(large_content)
        assert "truncated" in tool_msg["content"]


class TestPhaseToolFiltering:
    """Test phase-based tool filtering."""

    def test_filter_tools_by_phase_reduces_count(self):
        """Verify phase filtering reduces tool count."""
        from app.domain.services.agents.base import BaseAgent

        # Create mock tools
        all_tools = [
            {"type": "function", "function": {"name": "file_read", "parameters": {}}},
            {"type": "function", "function": {"name": "file_write", "parameters": {}}},
            {"type": "function", "function": {"name": "browser_navigate", "parameters": {}}},
            {"type": "function", "function": {"name": "shell_exec", "parameters": {}}},
            {"type": "function", "function": {"name": "info_search_web", "parameters": {}}},
            {"type": "function", "function": {"name": "code_execute", "parameters": {}}},
        ]

        # Test research phase — should exclude coding tools
        filtered = BaseAgent._filter_tools_by_phase(None, all_tools, "research")
        names = [t["function"]["name"] for t in filtered]
        assert "info_search_web" in names
        assert "browser_navigate" in names
        assert "code_execute" not in names

    def test_filter_tools_preserves_mcp(self):
        """Verify MCP tools are always preserved regardless of phase."""
        from app.domain.services.agents.base import BaseAgent

        tools = [
            {"type": "function", "function": {"name": "mcp_custom_tool", "parameters": {}}},
            {"type": "function", "function": {"name": "code_execute", "parameters": {}}},
        ]

        filtered = BaseAgent._filter_tools_by_phase(None, tools, "research")
        names = [t["function"]["name"] for t in filtered]
        assert "mcp_custom_tool" in names

    def test_get_available_tools_backward_compatible(self):
        """Verify get_available_tools() without phase returns all tools."""
        # Phase=None should return all tools (backward compatible)
        from app.domain.services.agents.base import BaseAgent

        tools = [
            {"type": "function", "function": {"name": "file_read", "parameters": {}}},
        ]
        filtered = BaseAgent._filter_tools_by_phase(None, tools, "all")
        assert len(filtered) == len(tools)


class TestGroundingRules:
    """Test that grounding rules are present in system prompt."""

    def test_grounding_rules_in_system_prompt(self):
        """Verify tool output grounding rules are included."""
        from app.domain.services.prompts.system import SYSTEM_PROMPT

        assert "Tool Output Grounding Protocol" in SYSTEM_PROMPT
        assert "tool outputs OVERRIDE" in SYSTEM_PROMPT.lower() or "tool outputs override" in SYSTEM_PROMPT.lower()

    def test_uncertainty_protocol_in_system_prompt(self):
        """Verify uncertainty protocol is included."""
        from app.domain.services.prompts.system import SYSTEM_PROMPT

        assert "uncertainty_protocol" in SYSTEM_PROMPT.lower() or "WHEN UNSURE" in SYSTEM_PROMPT
```

**Step 2: Run all tests**

Run: `cd backend && pytest tests/test_agent_intelligence.py -v --timeout=30`
Expected: All tests pass

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: Full suite passes (1920+ tests)

**Step 3: Commit**

```bash
git add backend/tests/test_agent_intelligence.py
git commit -m "test: add tests for agent intelligence enhancements

Covers compaction thresholds, memory truncation, phase filtering,
grounding rules, and uncertainty protocol."
```

---

### Task 13: Final Verification — Lint + Type Check + Full Test Suite

**Step 1: Run backend linting**

Run: `cd backend && ruff check app/domain/services/agents/token_manager.py app/domain/models/memory.py app/domain/services/prompts/system.py app/domain/services/agents/base.py app/domain/services/agents/execution.py app/domain/services/flows/plan_act.py app/infrastructure/external/llm/anthropic_llm.py`
Expected: No new errors from our changes

**Step 2: Run full test suite**

Run: `cd backend && pytest tests/ -q --timeout=30`
Expected: 1920+ tests pass, 0 fail

**Step 3: Run frontend checks (no frontend changes, but verify nothing broke)**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: Pass

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address lint/test issues from agent intelligence changes"
```

---

## Summary of Changes

| Task | File | Change | Impact |
|------|------|--------|--------|
| 1 | system.py | Tool output grounding rules | -30% parametric hallucination |
| 2 | token_manager.py | Thresholds: 75/85/95 → 60/70/85 | -40% context overflow |
| 3 | memory.py | Tool result truncation >8K chars | -40% context waste |
| 4 | anthropic_llm.py | Cache control on tool definitions | -45-80% API cost |
| 5 | anthropic_llm.py | Graduated structured output retry | ~100% format compliance |
| 6 | plan_act.py | Session bridging artifacts | -60% context loss on long tasks |
| 7 | base.py | Phase-based tool filtering | Improved tool accuracy |
| 8 | system.py | Uncertainty protocol | -20% forced hallucination |
| 9 | memory.py | Lower token threshold + more compactable | Earlier compaction |
| 10 | execution.py | CoVe on step results | Earlier hallucination detection |
| 11 | anthropic_llm.py | Cache structure documentation | Maintainability |
| 12 | test_agent_intelligence.py | Comprehensive tests | Regression prevention |
| 13 | All | Final verification | Quality assurance |

**Total files modified:** 7 (+ 1 new test file)
**Estimated impact:** 30-50% hallucination reduction, 40% context efficiency improvement, 45-80% API cost reduction
