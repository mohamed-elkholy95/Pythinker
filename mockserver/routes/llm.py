"""Mock OpenAI-compatible /v1/chat/completions endpoint.

The backend's LLM client (openai_llm.py) sends requests here when
API_BASE points to the mockserver. We return canned responses in
the OpenAI API format so the agent workflow can complete.

Response detection logic:
  1. Explicit response_format (json_schema / json_object) -> return plan JSON
  2. Tools present + last message is "user" -> return a tool call (varied tool name + args)
  3. Tools present + last message is "tool" -> return text (step complete, varied)
  4. Prompt-based JSON request (no tools, but "respond with valid JSON" in prompt) -> return JSON
  5. Default -> text response

Key design decisions for stuck-detection avoidance:
  - Tool calls cycle through DIFFERENT tool names (not just varied args) to prevent
    the action-pattern detector from firing on consecutive same-name calls.
  - Available tools are read from the request body so only valid tools are returned.
  - Last-message-role heuristic replaces global role=tool scan, so steps 2+ correctly
    get tool_call (not step_complete) even when previous steps had tool results.
  - Separate sequential counters per response type prevent index collisions.
  - 10 step-complete responses with diverse vocabulary/structure avoid semantic similarity.
  - Both streaming and non-streaming paths share the same detection logic.
"""

from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/v1")

# ── Sequential counters — separate per response type to avoid collision ──
_tool_call_seq = 0
_step_seq = 0
_text_seq = 0


def _next_tool_seq() -> int:
    global _tool_call_seq
    _tool_call_seq += 1
    return _tool_call_seq


def _next_step_seq() -> int:
    global _step_seq
    _step_seq += 1
    return _step_seq


def _next_text_seq() -> int:
    global _text_seq
    _text_seq += 1
    return _text_seq


def _chat_id() -> str:
    return f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"


def _ts() -> int:
    return int(time.time())


# ── Canned JSON responses ────────────────────────────────────────────

_MOCK_PLAN = {
    "title": "Task Execution Plan",
    "goal": "Complete the requested task",
    "language": "en",
    "steps": [
        {
            "description": "Analyze the request and gather information",
            "status": "pending",
        },
        {"description": "Execute the task based on analysis", "status": "pending"},
        {"description": "Summarize findings and present results", "status": "pending"},
    ],
    "message": "I've created a plan to address your request. Let me work through it step by step.",
}

_MOCK_REFLECTION = {
    "decision": "complete",
    "confidence": 0.85,
    "reasoning": "The task has been completed successfully based on the gathered information.",
    "suggestion": None,
}

_MOCK_VERIFICATION = {
    "is_valid": True,
    "issues": [],
    "score": 0.9,
    "summary": "All steps completed successfully.",
}

# ── Tool argument templates per tool name ─────────────────────────────
# Each tool has multiple argument variants so consecutive calls to the
# same tool still produce different hashes.

_TOOL_ARGS: dict[str, list[dict]] = {
    "info_search_web": [
        {
            "query": "latest developments and breakthroughs in AI agent frameworks",
            "date_range": "past_year",
        },
        {
            "query": "technical analysis comparing autonomous agent architectures",
            "date_range": "past_month",
        },
        {
            "query": "emerging patterns in multi-agent orchestration systems",
            "date_range": "past_week",
        },
        {"query": "benchmark results for tool-using language model agents 2025"},
        {
            "query": "production deployment strategies for LLM-powered automation",
            "date_range": "past_month",
        },
    ],
    "search": [
        {"query": "comprehensive overview of autonomous agent capabilities"},
        {"query": "detailed comparison of agent framework features"},
        {"query": "real-world case studies of AI agent deployments"},
    ],
    "file_read": [
        {"file": "/home/ubuntu/workspace/README.md"},
        {"file": "/home/ubuntu/workspace/package.json"},
        {"file": "/home/ubuntu/workspace/requirements.txt"},
    ],
    "shell_exec": [
        {"command": "ls -la /home/ubuntu/workspace"},
        {"command": "python3 -c \"import sys; print(f'Python {sys.version}')\""},
        {
            "command": "find /home/ubuntu/workspace -maxdepth 2 -type f 2>/dev/null | head -20"
        },
    ],
    "browser_navigate": [
        {"url": "https://example.com/research"},
        {"url": "https://example.com/documentation"},
    ],
    "browser_view": [{}],
    "code_execute_python": [
        {"code": "data = {'status': 'complete', 'findings': 3}; print(data)"},
        {"code": "import os; print(os.listdir('/home/ubuntu/workspace'))"},
    ],
    "git_status": [{}],
    "git_log": [{}],
    "code_list_artifacts": [{}],
}

# Preferred order for tool cycling — safe/read-only tools first
_PREFERRED_TOOLS = [
    "info_search_web",
    "file_read",
    "shell_exec",
    "search",
    "browser_navigate",
    "code_execute_python",
    "browser_view",
    "git_status",
    "git_log",
    "code_list_artifacts",
]

# ── Step complete responses — deliberately diverse vocabulary + structure ──
# 10 entries with maximum trigram diversity to avoid semantic similarity detection

_STEP_COMPLETE_RESPONSES = [
    (
        "I've completed the initial research phase. The search results contain "
        "several relevant data points about current frameworks and their capabilities. "
        "Let me proceed to the next analysis step."
    ),
    (
        "Data collection finished. Key takeaways from this round:\n"
        "- Multiple sources confirm the approach is viable\n"
        "- Three promising patterns were identified\n"
        "- Further investigation of implementation details is warranted"
    ),
    (
        "Done with the technical review segment. Important architectural "
        "considerations were uncovered that will shape the final recommendations. "
        "Moving on to synthesize these findings now."
    ),
    (
        "Step complete. The workspace examination reveals the project structure "
        "and core dependencies. I now have sufficient context to deliver a "
        "well-informed assessment of the technical landscape."
    ),
    (
        "Execution finished for this phase. Cross-referencing the gathered materials "
        "shows strong consensus among expert sources regarding best practices. The "
        "evidence base is solid enough to draw preliminary conclusions."
    ),
    (
        "This investigation wraps up with productive results. Both theoretical "
        "foundations and practical implementation strategies were covered. "
        "Ready for the consolidation stage."
    ),
    (
        "Analysis checkpoint reached. I've processed all available data and "
        "extracted the most relevant insights. The observed patterns align "
        "with established industry knowledge. Advancing to finalization."
    ),
    (
        "Research subtask concluded. Notable observation: the ecosystem has "
        "matured significantly, with several new paradigms emerging in recent "
        "months. This context enriches the overall assessment."
    ),
    (
        "File and command output review complete. The concrete artifacts provide "
        "supporting evidence for the analysis direction chosen. Transitioning "
        "to the next phase of the workflow."
    ),
    (
        "Browser and search exploration done. A comprehensive picture of the "
        "current state of the art has been assembled. All prerequisite "
        "information is gathered — summary preparation begins."
    ),
]

# ── Summarize responses — final output variety ──

_SUMMARIZE_RESPONSES = [
    (
        "Based on my analysis, here's what I found:\n\n"
        "This is a demonstration response from the Pythinker mock server. "
        "In production, this would be a real AI-generated response based on "
        "the tools executed during the session.\n\n"
        "The mock server simulates the full agent workflow — planning, execution, "
        "and summarization — without requiring a real LLM provider."
    ),
    (
        "Here's a summary of the completed work:\n\n"
        "I analyzed the request and gathered relevant information through multiple "
        "tools including web search, file reading, and code execution. "
        "The results were processed and key insights were extracted.\n\n"
        "In a production environment, this response would contain the actual "
        "analysis results tailored to your specific query."
    ),
    (
        "After thorough investigation, here are the key findings:\n\n"
        "Multiple sources were consulted to ensure comprehensive coverage of the topic. "
        "The analysis revealed several important patterns and trends.\n\n"
        "This mock response demonstrates the complete agent pipeline from "
        "planning through execution to final summarization."
    ),
    (
        "The research has been completed and consolidated:\n\n"
        "Several approaches were evaluated during the execution phase. "
        "The evidence gathered supports clear recommendations for next steps.\n\n"
        "In the production system, this would contain detailed findings "
        "with citations and actionable guidance."
    ),
    (
        "Task finalized. Here is the consolidated output:\n\n"
        "Throughout the workflow, information was gathered from web searches, "
        "file analysis, and code execution. The combined data provides "
        "a well-rounded perspective on the topic.\n\n"
        "This completes the mock demonstration of Pythinker's agent capabilities."
    ),
]


# ── Helper functions ─────────────────────────────────────────────────


def _get_last_content(messages: list[dict], role: str) -> str:
    """Get the content of the last message with the given role."""
    for m in reversed(messages):
        if m.get("role") == role:
            content = m.get("content") or ""
            if isinstance(content, list):
                return " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            return content
    return ""


def _prompt_requests_json(messages: list[dict]) -> bool:
    """Check if any message asks for JSON output via prompt text.

    The backend injects JSON instructions when the model doesn't support
    response_format natively (e.g., mock-model falls through to prompt-based).
    """
    for m in messages:
        content = m.get("content") or ""
        if (
            isinstance(content, str)
            and "respond with" in content.lower()
            and "json" in content.lower()
        ):
            return True
    return False


def _extract_json_schema_name(messages: list[dict]) -> str | None:
    """Try to detect which schema the backend is asking for from the prompt."""
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, str):
            lower = content.lower()
            if "plan" in lower and "steps" in lower:
                return "plan"
            if "reflection" in lower or "decision" in lower:
                return "reflection"
            if "verif" in lower or "is_valid" in lower:
                return "verification"
    return None


def _select_tool_call(body: dict) -> dict:
    """Select a varied tool call from the request's available tools.

    Cycles through DIFFERENT tool names to prevent stuck detection's
    action-pattern detector from firing on consecutive same-name calls.
    Reads the tools array from the request so only valid tools are returned.
    """
    tools = body.get("tools", [])
    seq = _next_tool_seq()

    # Extract available tool names from request
    available_names: set[str] = set()
    for t in tools:
        func = t.get("function", {})
        name = func.get("name", "")
        if name:
            available_names.add(name)

    if not available_names:
        # Fallback when no tools in request
        templates = _TOOL_ARGS.get("info_search_web", [{}])
        return {"name": "info_search_web", "arguments": templates[seq % len(templates)]}

    # Build ordered list: preferred tools that are available, then remaining
    ordered: list[str] = []
    for name in _PREFERRED_TOOLS:
        if name in available_names:
            ordered.append(name)
    for name in sorted(available_names):
        if name not in ordered:
            ordered.append(name)

    # Select tool name — cycle through different names
    selected = ordered[seq % len(ordered)]

    # Generate arguments appropriate for the selected tool
    templates = _TOOL_ARGS.get(selected)
    if templates:
        args = templates[seq % len(templates)]
    else:
        args = {}

    return {"name": selected, "arguments": args}


def _detect_request_type(body: dict) -> str:
    """Detect what kind of response the backend expects.

    Returns one of: 'plan_json', 'generic_json', 'tool_call', 'step_complete', 'text'

    Priority order:
      1. Explicit response_format (json_schema/json_object) → plan or generic JSON
      2. Tools present → tool_call or step_complete (MUST come before prompt-based JSON
         check because the backend injects "respond with valid JSON" into the system
         prompt for models that don't support response_format natively, and we need
         tool execution to take priority over that prompt-based JSON detection)
      3. Prompt-based JSON fallback → generic_json
      4. Default → text
    """
    messages = body.get("messages", [])
    response_format = body.get("response_format") or {}
    rf_type = response_format.get("type", "")

    # 1. Explicit structured output via response_format
    if rf_type in ("json_schema", "json_object"):
        json_schema = response_format.get("json_schema", {})
        schema_name = (json_schema.get("name") or "").lower()
        if "plan" in schema_name:
            return "plan_json"
        return "generic_json"

    # 2. Tools present — use last message role for state detection
    #    This MUST come before prompt-based JSON check (step 3) because the
    #    backend injects JSON instructions into the system prompt for mock-model,
    #    which would otherwise cause _prompt_requests_json() to match and bypass
    #    tool execution entirely.
    if body.get("tools"):
        last_role = messages[-1].get("role", "") if messages else ""

        if last_role == "tool":
            # Tool results just arrived for the current step
            return "step_complete"

        # last_role is "user" (new step prompt), "system", or "assistant"
        # All indicate we should start tool execution for this step
        return "tool_call"

    # 3. Prompt-based JSON fallback (no tools, but prompt asks for JSON)
    if _prompt_requests_json(messages):
        return "generic_json"

    return "text"


def _build_json_content(body: dict) -> str:
    """Build an appropriate JSON response based on the detected schema."""
    messages = body.get("messages", [])
    response_format = body.get("response_format") or {}

    json_schema = response_format.get("json_schema", {})
    schema_name = (json_schema.get("name") or "").lower()

    if "plan" in schema_name:
        return json.dumps(_MOCK_PLAN)

    inferred = _extract_json_schema_name(messages)
    if inferred == "plan":
        return json.dumps(_MOCK_PLAN)
    if inferred == "reflection":
        return json.dumps(_MOCK_REFLECTION)
    if inferred == "verification":
        return json.dumps(_MOCK_VERIFICATION)

    return json.dumps(_MOCK_PLAN)


# ── Non-streaming response ───────────────────────────────────────────


def _non_streaming_response(body: dict) -> dict:
    """Build a non-streaming OpenAI chat completion response."""
    req_type = _detect_request_type(body)
    model = body.get("model", "mock-model")

    if req_type == "plan_json":
        content = json.dumps(_MOCK_PLAN)
        finish_reason = "stop"

    elif req_type == "generic_json":
        content = _build_json_content(body)
        finish_reason = "stop"

    elif req_type == "tool_call":
        tool_spec = _select_tool_call(body)
        tool_call_id = f"call_mock_{uuid.uuid4().hex[:8]}"
        return {
            "id": _chat_id(),
            "object": "chat.completion",
            "created": _ts(),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": tool_spec["name"],
                                    "arguments": json.dumps(tool_spec["arguments"]),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }

    elif req_type == "step_complete":
        seq = _next_step_seq()
        content = _STEP_COMPLETE_RESPONSES[seq % len(_STEP_COMPLETE_RESPONSES)]
        finish_reason = "stop"

    else:
        seq = _next_text_seq()
        content = _SUMMARIZE_RESPONSES[seq % len(_SUMMARIZE_RESPONSES)]
        finish_reason = "stop"

    return {
        "id": _chat_id(),
        "object": "chat.completion",
        "created": _ts(),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


# ── Streaming response ───────────────────────────────────────────────


async def _streaming_response(body: dict):
    """Yield SSE chunks in OpenAI streaming format.

    Uses the same _detect_request_type logic as non-streaming to ensure
    consistent behavior regardless of whether streaming is requested.
    """
    model = body.get("model", "mock-model")
    chat_id = _chat_id()
    created = _ts()

    # Detect content type (ignoring stream flag — caller already handled that)
    req_type = _detect_request_type(body)

    if req_type == "tool_call":
        # Stream a tool call with varied tool name + arguments
        tool_spec = _select_tool_call(body)
        tool_call_id = f"call_mock_{uuid.uuid4().hex[:8]}"
        func_name = tool_spec["name"]
        func_args = json.dumps(tool_spec["arguments"])

        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": tool_call_id,
                                "type": "function",
                                "function": {"name": func_name, "arguments": ""},
                            }
                        ],
                    },
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

        chunk["choices"][0]["delta"] = {
            "tool_calls": [{"index": 0, "function": {"arguments": func_args}}]
        }
        yield f"data: {json.dumps(chunk)}\n\n"

        chunk["choices"][0]["delta"] = {}
        chunk["choices"][0]["finish_reason"] = "tool_calls"
        yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Determine text content based on request type
    if req_type == "step_complete":
        seq = _next_step_seq()
        text = _STEP_COMPLETE_RESPONSES[seq % len(_STEP_COMPLETE_RESPONSES)]
    elif req_type in ("plan_json", "generic_json"):
        text = _build_json_content(body)
    else:
        seq = _next_text_seq()
        text = _SUMMARIZE_RESPONSES[seq % len(_SUMMARIZE_RESPONSES)]

    # Stream text word-by-word
    words = text.split(" ")

    chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    for i, word in enumerate(words):
        token = word if i == 0 else f" {word}"
        chunk["choices"][0]["delta"] = {"content": token}
        yield f"data: {json.dumps(chunk)}\n\n"

    chunk["choices"][0]["delta"] = {}
    chunk["choices"][0]["finish_reason"] = "stop"
    chunk["usage"] = {
        "prompt_tokens": 100,
        "completion_tokens": len(words),
        "total_tokens": 100 + len(words),
    }
    yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"


# ── Routes ────────────────────────────────────────────────────────────


@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()

    if body.get("stream"):
        return StreamingResponse(
            _streaming_response(body),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return _non_streaming_response(body)


# ── Models endpoint (some clients check this) ──


@router.get("/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "mock-model",
                "object": "model",
                "created": 1700000000,
                "owned_by": "pythinker-mock",
            }
        ],
    }
