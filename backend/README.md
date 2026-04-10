# Pythinker Backend Service

Pythinker is an intelligent conversation agent system based on FastAPI and OpenAI API. The backend adopts Domain-Driven Design (DDD) architecture, supporting intelligent dialogue, file operations, Shell command execution, and browser automation.

## Project Architecture

The project adopts Domain-Driven Design (DDD) architecture, clearly separating the responsibilities of each layer:

```
backend/
├── app/
│   ├── domain/          # Domain layer: contains core business logic
│   │   ├── models/      # Domain model definitions
│   │   ├── services/    # Domain services
│   │   ├── external/    # External service interfaces
│   │   └── prompts/     # Prompt templates
│   ├── application/     # Application layer: orchestrates business processes
│   │   ├── services/    # Application services
│   │   └── schemas/     # Data schema definitions
│   ├── interfaces/      # Interface layer: defines external system interfaces
│   │   └── api/
│   │       └── routes.py # API route definitions
│   ├── infrastructure/  # Infrastructure layer: provides technical implementation
│   └── main.py          # Application entry
├── Dockerfile           # Docker configuration file
├── run.sh               # Production environment startup script
├── dev.sh               # Development environment startup script
├── requirements.txt     # Project dependencies
└── README.md            # Project documentation
```

## Core Features

1. **Session Management**: Create and manage conversation session instances
2. **Real-time Conversation**: Implement real-time conversation through Server-Sent Events (SSE)
3. **Tool Invocation**: Support for various tool calls, including:
   - Browser automation operations (using Playwright)
   - Shell command execution and viewing
   - File read/write operations
   - Web search integration
4. **Sandbox Environment**: Use Docker containers to provide isolated execution environments
5. **Live Browser Preview**: CDP screencast streaming via authenticated WebSocket proxy

## Requirements

- Python 3.9+
- Docker 20.10+
- MongoDB 4.4+
- Redis 6.0+

## MongoDB Driver Boundary

Beanie is initialized through PyMongo's native async client path. Motor remains in place for GridFS and repository code that still depends on Motor-specific collection/database types. Keep new Beanie startup code on the shared `initialize_beanie(...)` helper in `app.infrastructure.storage.mongodb` so future Beanie upgrades only need one initialization boundary reviewed.

## Installation and Configuration

1. **Create a virtual environment**:
```bash
python -m venv .venv
source .venv/bin/activate
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Environment variable configuration**:
Create a `.env` file and set the following environment variables:
```
# Model provider configuration
API_KEY=your_api_key_here                # API key for OpenAI or other model providers
API_BASE=https://api.openai.com/v1       # Base URL for the model API, can be replaced with other model provider API addresses

# Model configuration
MODEL_NAME=gpt-4o                        # Model name to use
TEMPERATURE=0.7                          # Model temperature parameter
MAX_TOKENS=2000                          # Maximum output tokens per model request

# Google search configuration
GOOGLE_SEARCH_API_KEY=                   # Google Search API key for web search functionality (optional)
GOOGLE_SEARCH_ENGINE_ID=                 # Google custom search engine ID (optional)
TAVILY_API_KEY=                          # Tavily Search API key (optional)
SERPER_API_KEY=                          # Serper Search API key (optional)
JINA_API_KEY=                            # Jina Search/Reader API key (optional)

# Sandbox configuration
SANDBOX_IMAGE=pythinker/pythinker-sandbox       # Sandbox environment Docker image
SANDBOX_NAME_PREFIX=sandbox              # Sandbox container name prefix
SANDBOX_TTL_MINUTES=30                   # Sandbox container time-to-live (minutes)
SANDBOX_NETWORK=pythinker-network        # Docker network name for communication between sandbox containers

# Database configuration
MONGODB_URL=mongodb://localhost:27017    # MongoDB connection URL
MONGODB_DATABASE=pythinker               # MongoDB database name
REDIS_URL=redis://localhost:6379/0       # Redis connection URL

# Log configuration
LOG_LEVEL=INFO                           # Log level, options: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Running the Service

### Development Environment
```bash
# Start the development server (with hot reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The service will start at http://localhost:8000.

### Docker Deployment
```bash
# Build Docker image
docker build -t pythinker-backend .

# Run container
docker run -p 8000:8000 --env-file .env -v /var/run/docker.sock:/var/run/docker.sock pythinker-backend
```

> Note: If using Docker deployment, you need to mount the Docker socket so the backend can create sandbox containers.

## API Documentation

Base URL: `/api/v1`

### 1. Create Session

- **Endpoint**: `PUT /api/v1/sessions`
- **Description**: Create a new conversation session
- **Request Body**: None
- **Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": {
      "session_id": "string"
    }
  }
  ```

### 2. Get Session

- **Endpoint**: `GET /api/v1/sessions/{session_id}`
- **Description**: Get session information including conversation history
- **Path Parameters**:
  - `session_id`: Session ID
- **Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": {
      "session_id": "string",
      "title": "string",
      "events": []
    }
  }
  ```

### 3. List All Sessions

- **Endpoint**: `GET /api/v1/sessions`
- **Description**: Get list of all sessions
- **Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": {
      "sessions": [
        {
          "session_id": "string",
          "title": "string",
          "latest_message": "string",
          "latest_message_at": 1234567890,
          "status": "string",
          "unread_message_count": 0
        }
      ]
    }
  }
  ```

### 4. Delete Session

- **Endpoint**: `DELETE /api/v1/sessions/{session_id}`
- **Description**: Delete a session
- **Path Parameters**:
  - `session_id`: Session ID
- **Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": null
  }
  ```

### 5. Stop Session

- **Endpoint**: `POST /api/v1/sessions/{session_id}/stop`
- **Description**: Stop an active session
- **Path Parameters**:
  - `session_id`: Session ID
- **Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": null
  }
  ```

### 6. Chat with Session

- **Endpoint**: `POST /api/v1/sessions/{session_id}/chat`
- **Description**: Send a message to the session and receive streaming response
- **Path Parameters**:
  - `session_id`: Session ID
- **Request Body**:
  ```json
  {
    "message": "User message content",
    "timestamp": 1234567890,
    "event_id": "optional event ID"
  }
  ```
- **Response**: Server-Sent Events (SSE) stream
- **Event Types**:
  - `message`: Text message from assistant
  - `title`: Session title update
  - `plan`: Execution plan with steps
  - `step`: Step status update
  - `tool`: Tool invocation information
  - `error`: Error information
  - `done`: Conversation completion

### 7. View Shell Session Content

- **Endpoint**: `POST /api/v1/sessions/{session_id}/shell`
- **Description**: View shell session output in the sandbox environment
- **Path Parameters**:
  - `session_id`: Session ID
- **Request Body**:
  ```json
  {
    "session_id": "shell session ID"
  }
  ```
- **Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": {
      "output": "shell output content",
      "session_id": "shell session ID",
      "console": [
        {
          "ps1": "prompt string",
          "command": "executed command",
          "output": "command output"
        }
      ]
    }
  }
  ```

### 8. View File Content

- **Endpoint**: `POST /api/v1/sessions/{session_id}/file`
- **Description**: View file content in the sandbox environment
- **Path Parameters**:
  - `session_id`: Session ID
- **Request Body**:
  ```json
  {
    "file": "file path"
  }
  ```
- **Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": {
      "content": "file content",
      "file": "file path"
    }
  }
  ```

### 9. Browser Screencast Stream (CDP)

- **Endpoint**: `WebSocket /api/v1/sessions/{session_id}/screencast`
- **Description**: Stream live browser frames from the session sandbox to the client
- **Path Parameters**:
  - `session_id`: Session ID
- **Protocol**: WebSocket (binary mode)

## Error Handling

All APIs return responses in a unified format when errors occur:
```json
{
  "code": 400,
  "msg": "Error description",
  "data": null
}
```

Common error codes:
- `400`: Request parameter error
- `404`: Resource not found
- `500`: Server internal error

## Development Guide

### Adding New Tools

1. Define the tool interface in the `domain/external` directory
2. Implement the tool functionality in the `infrastructure` layer
3. Integrate the tool in `application/services`

## Deep Research Reliability

### Summarization Context Handoff

Before entering `AgentStatus.SUMMARIZING`, the flow runs two compaction passes:

1. **`_compact_prior_step_context`** — simple char-based truncation of old tool/assistant messages
2. **`ContextCompressionPipeline`** — token-aware three-stage pass (summarize → truncate → drop) targeting `effective_context_char_cap / 4` tokens

Workspace deliverables and tracked attachments are assembled into an explicit `summarization_context` string and passed directly into `ExecutionAgent.summarize()` instead of mutating `system_prompt` at runtime.

### Deep-Research Search Budgets

When `complexity_score >= 0.8`, `SearchTool._get_compaction_profile()` returns a `CompactionProfile` with expanded limits:

| Setting | Default | Deep-Research |
|---------|---------|---------------|
| `search_auto_enrich_top_k` | 5 | `search_auto_enrich_top_k_deep` (8) |
| `search_auto_enrich_snippet_chars` | 2000 | `search_auto_enrich_snippet_chars_deep` (3000) |
| `scraping_spider_top_k` | 5 | `scraping_spider_top_k_deep` (3) |
| `search_preview_count` | 5 | `search_preview_count_deep` (8) |

Configure via `.env` — all have sensible defaults and do not change non-research flow behavior.

### Summary Recovery from Cache

When `ExecutionAgent.summarize()` fails before yielding any streamed content, the summarization error path now attempts cache-backed recovery before emitting an error event:

1. **`_pre_trim_report_cache`** — report content captured immediately before context trimming began
2. **`_extract_fallback_summary()`** — memory-layer fallback if the pre-trim cache is empty

If a valid candidate (>200 chars) is found, a `ReportEvent` is emitted with title `[Partial] <extracted_title>` and a blockquote notice explaining the partial recovery. Only after all candidates are exhausted does the flow emit an `ErrorEvent`.

Related: `llm_stream_read_timeout` (default `150.0` s) and per-provider read timeouts (`openai`: 150 s, `glm`: 150 s) were also raised to reduce spurious mid-report `httpx.ReadTimeout` kills on large-context summarization.

### Report Verification Loop Guard

The deliverable workflow prompt enforces single-shot verification:
- Use the **exact path** returned by `file_write`
- Run **one** check; if `file_write` returned success the file exists — skip further shell probes

A flow-level state flag (`_report_verification_failed`) suppresses replanning when a report attachment is already tracked and one verification pass has already failed.

### Final Delivery Local-Only Mode

When a step is doing final review/delivery work and a report draft already exists in the execution caches, `ExecutionAgent.execute_step()` now removes remote research bundles before the LLM turn:

- Keeps local delivery bundles such as `file`, `message`, `chart`, `workspace`, `scratchpad`, and `export`
- Removes remote browsing/research bundles such as `search` and `browser`
- Adds a prompt nudge telling the agent to use existing local artifacts and ask the user if those artifacts are insufficient

This prevents final delivery from regressing into guessed-URL browsing or fresh web research after the report has already been written, which was previously inflating context and triggering stuck recovery during the last step.

Final delivery prompts also reuse the exact markdown artifact path when one is known from prior `file_write` / `file_create` calls:

- Reuses the cached report path instead of letting the model invent a new filename
- Falls back to a short "do not guess a report filename" prompt when a draft exists but the exact path is not cached yet

### Step Result Payload Recovery

`StepExecutor.apply_step_result_payload()` now treats partially structured step payloads as usable when the core fields can be recovered safely:

- Strict `ExecutionStepResult` validation still runs first
- If validation fails but `success`, `result`, or `attachments` can still be extracted, the step keeps that recovered state
- Only completely unusable payloads fall back to the generic step-failure path

This prevents tool-backed steps from being marked failed solely because of a non-critical schema defect such as malformed `attachments`, while still failing closed on non-JSON or structurally empty responses.

`ExecutionAgent.execute_step()` also preserves a deterministic partial result when:

- one or more tool calls succeeded
- no tool calls failed
- the only failure was final JSON packaging (`"did not return a valid JSON result"`, prose instead of JSON, or equivalent format-only failure)

In that case the step still remains **failed**, but it keeps a real partial summary instead of an empty result so downstream steps can continue from the successful tool activity without pretending the step fully succeeded.

### Partial-Result Unblocking Guard

`StepFailureHandler.handle_failure()` now unblocks dependents only when the failed step left something actionable behind:

- an existing `step.result`, or
- concrete file outputs in `attachments` / `artifacts`

When a failed step has no usable result and no files, the handler keeps dependents blocked instead of injecting a fake placeholder. This prevents zero-progress replans from treating empty contract failures as partial progress.

### Grounding Escalation Policy

Report grounding now uses one inclusive threshold policy in `OutputVerifier`:

- **>= 15% unsupported** → reliability notice
- **>= 30% unsupported** → escalated warning plus targeted re-research hints
- **>= 60% unsupported** → critical block path

Report grounding also fails closed when verification finds an escalated unsupported-claim ratio and the cleanup rewrite does not succeed:

- **Moderate ratio + successful rewrite** → deliver rewritten report with a reliability notice
- **Escalated ratio + failed or timed-out rewrite on report-like content** → block delivery as `hallucination_ratio_critical`
- **Above block threshold** → unchanged critical path

This keeps report-grounding severity owned by `OutputVerifier` instead of relying on the delivery gate to infer severity from warning strings, and avoids boundary drift at exact `15%`, `30%`, and `60%` scores.

Critical delivery-gate issues such as `hallucination_ratio_critical` now also log as `red` gate severity, so blocked critical outcomes are no longer reported as `yellow`.

### Plotly Chart Fallback Policy

`AgentTaskRunner._ensure_plotly_chart_files()` probes Plotly availability via `PlotlyCapabilityCheck` before launching the chart script:

- **Available** → Plotly HTML + PNG via `PlotlyChartOrchestrator`
- **Unavailable** → immediate SVG fallback (no subprocess spawned)
- **Probe cached** for 300 s per session to avoid repeated `exec_command` overhead
- **Probe parser ignores wrapper noise and treats import tracebacks as unavailable**, so logs no longer report false-positive Plotly capability
- **Plotly and SVG chart specs revalidated** so malformed specs or semantic mismatches such as `Inference Performance` charts built from `Parameters` are skipped before any chart artifact is written

**Deployment options:**

| Dockerfile | Plotly available | When to use |
|---|---|---|
| `sandbox/Dockerfile` (default) | Only when `ENABLE_SANDBOX_ADDONS=1` | Standard dev/prod |
| `sandbox/Dockerfile.plotly` | Always | When charts are always required |

Set `PLOTLY_RUNTIME_AVAILABLE=1` in `.env` when using the addons or Plotly image so the backend skips the probe.

## Author

Mohamed Elkholy
