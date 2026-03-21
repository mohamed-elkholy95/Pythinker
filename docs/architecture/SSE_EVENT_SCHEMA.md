# SSE Event Schema Reference

Complete reference for all Server-Sent Events (SSE) emitted by the Pythinker backend.

## Wire Protocol

All SSE streams begin with a `retry:` directive before any data events:

```
retry: 1500

```

This tells native `EventSource` clients to wait 1500ms before auto-reconnecting on disconnect.

### Event ID (`id:` field)

- **Agent mode (Redis-backed):** Events use Redis stream IDs (`<milliseconds>-<sequence>`, e.g. `1772445693104-0`). These are emitted as the SSE `id:` field and can be sent back as `Last-Event-ID` for resume.
- **Discuss mode (in-process):** Events use UUID-format IDs internally. A monotonic sequence counter (`seq-1`, `seq-2`, ...) is emitted as the SSE `id:` field for basic reconnection tracking.

### Heartbeat

Heartbeat events are sent as SSE comments (`:\n\n`) or as `progress` events with `phase: "heartbeat"` at a configurable interval (default 30s) to prevent proxy/load-balancer timeouts.

---

## Event Types

All events share a common base envelope:

| Field       | Type     | Description                                      |
|-------------|----------|--------------------------------------------------|
| `event_id`  | `string` | Unique event identifier (UUID)                   |
| `timestamp` | `string` | ISO 8601 timestamp                               |
| `type`      | `string` | Event type discriminator (matches SSE `event:`)  |

---

### `progress`

Progress updates during planning, execution, and keep-alive phases.

| Field                       | Type      | Description                                             |
|-----------------------------|-----------|---------------------------------------------------------|
| `phase`                     | `string`  | One of: `received`, `analyzing`, `planning`, `finalizing`, `heartbeat`, `waiting`, `verifying`, `executing_setup` |
| `message`                   | `string`  | User-friendly status message                            |
| `estimated_steps`           | `int?`    | Estimated total steps (if known)                        |
| `progress_percent`          | `int?`    | 0-100 progress indicator                                |
| `estimated_duration_seconds`| `int?`    | Rough time estimate for the task                        |
| `complexity_category`       | `string?` | `simple`, `medium`, or `complex`                        |
| `wait_elapsed_seconds`      | `int?`    | Elapsed wait time for long-running execution            |
| `wait_stage`                | `string?` | `execution_wait`, `verification_wait`, `tool_wait`      |

---

### `stream`

Streaming LLM response content chunks.

| Field      | Type      | Description                                          |
|------------|-----------|------------------------------------------------------|
| `content`  | `string`  | Streamed content chunk                               |
| `is_final` | `boolean` | Whether this is the final chunk                      |
| `phase`    | `string`  | `thinking` (planning) or `summarizing` (report gen)  |
| `lane`     | `string`  | `answer` (main response) or `reasoning` (thinking)   |

---

### `plan`

Plan creation and update events.

| Field    | Type      | Description                                        |
|----------|-----------|----------------------------------------------------|
| `plan`   | `object`  | Full plan object with steps                        |
| `status` | `string`  | `created`, `updated`, or `completed`               |
| `step`   | `object?` | Current step (if applicable)                       |
| `phases` | `array?`  | Phase summaries for frontend display               |

---

### `step`

Step execution lifecycle events.

| Field         | Type      | Description                                    |
|---------------|-----------|------------------------------------------------|
| `step`        | `object`  | Step object with title, description, etc.      |
| `status`      | `string`  | `started`, `running`, `failed`, `completed`    |
| `phase_id`    | `string?` | Parent phase ID                                |
| `step_type`   | `string?` | Step type value                                |
| `duration_ms` | `float?`  | Step execution duration in milliseconds        |

---

### `tool`

Tool invocation events (calling and result).

| Field              | Type      | Description                                        |
|--------------------|-----------|----------------------------------------------------|
| `tool_call_id`     | `string`  | Unique tool call identifier                        |
| `tool_name`        | `string`  | Tool name                                          |
| `tool_content`     | `object?` | Tool-specific content (browser, search, shell, etc.) |
| `function_name`    | `string`  | Function being called                              |
| `function_args`    | `object`  | Function arguments                                 |
| `status`           | `string`  | `calling` or `called`                              |
| `function_result`  | `any?`    | Tool execution result                              |
| `action_type`      | `string?` | Action type (OpenHands-style)                      |
| `observation_type` | `string?` | Observation type                                   |
| `command`          | `string?` | Command executed (for shell tools)                 |
| `exit_code`        | `int?`    | Shell exit code                                    |
| `security_risk`    | `string?` | Risk level if security review triggered            |
| `call_status`      | `string?` | Granular status (pending, running, success, etc.)  |
| `sequence_number`  | `int?`    | Position in session timeline                       |
| `duration_ms`      | `float?`  | Execution duration in milliseconds                 |
| `display_command`   | `string?` | Human-readable command summary                    |
| `command_category`  | `string?` | `search`, `browse`, `file`, `shell`, `code`       |

---

### `tool_stream`

Streaming partial tool content during LLM generation.

| Field             | Type      | Description                                  |
|-------------------|-----------|----------------------------------------------|
| `tool_call_id`    | `string`  | Links to parent tool event                   |
| `tool_name`       | `string`  | Tool name                                    |
| `function_name`   | `string`  | Function name                                |
| `partial_content` | `string`  | Accumulated content extracted so far         |
| `content_type`    | `string`  | `text`, `code`, or `json`                    |
| `is_final`        | `boolean` | True when full content is available          |

---

### `tool_progress`

Progress updates for long-running tool operations.

| Field                    | Type      | Description                              |
|--------------------------|-----------|------------------------------------------|
| `tool_call_id`           | `string`  | Links to parent tool event               |
| `tool_name`              | `string`  | Tool name                                |
| `function_name`          | `string`  | Function name                            |
| `progress_percent`       | `int`     | 0-100 progress                           |
| `current_step`           | `string`  | Human-readable current action            |
| `steps_completed`        | `int`     | Steps completed                          |
| `steps_total`            | `int?`    | Total steps (null if unknown)            |
| `elapsed_ms`             | `float`   | Time elapsed                             |
| `estimated_remaining_ms` | `float?`  | Estimated remaining time                 |
| `checkpoint_id`          | `string?` | ID for resuming from this point          |

---

### `message`

Complete assistant or user messages.

| Field                | Type      | Description                                      |
|----------------------|-----------|--------------------------------------------------|
| `role`               | `string`  | `user` or `assistant`                            |
| `message`            | `string`  | Message text content                             |
| `attachments`        | `array?`  | List of attached files (FileInfo objects)         |
| `delivery_metadata`  | `object?` | Delivery tracking metadata                       |
| `skills`             | `array?`  | Skill IDs enabled for this message               |
| `thinking_mode`      | `string?` | Model tier override                              |

---

### `done`

Stream completion signal. Emitted as the final event in every stream.

| Field | Type | Description |
|-------|------|-------------|
| *(base fields only)* | | No additional fields beyond the base envelope |

Note: Some call sites attach dynamic `title` and `summary` attributes for convenience, but these are not part of the formal schema.

---

### `error`

Structured error events with recovery guidance.

| Field                 | Type      | Description                                        |
|-----------------------|-----------|----------------------------------------------------|
| `error`               | `string`  | Human-readable error message                       |
| `error_type`          | `string?` | e.g. `token_limit`, `timeout`, `tool_execution`    |
| `recoverable`         | `boolean` | Whether the user can retry/continue                |
| `retry_hint`          | `string?` | User-facing guidance                               |
| `error_code`          | `string?` | Machine-readable code for client retry policy      |
| `error_category`      | `string?` | `transport`, `timeout`, `validation`, `auth`, `upstream`, `domain` |
| `severity`            | `string`  | `info`, `warning`, `error`, `critical`             |
| `retry_after_ms`      | `int?`    | Suggested retry delay in milliseconds              |
| `can_resume`          | `boolean` | Whether reconnect with event_id resume works       |
| `checkpoint_event_id` | `string?` | Safe resume checkpoint                             |
| `details`             | `object?` | Optional structured diagnostics payload            |

---

### `flow_transition`

Workflow state transition events.

| Field        | Type      | Description                            |
|--------------|-----------|----------------------------------------|
| `from_state` | `string`  | Previous agent status value            |
| `to_state`   | `string`  | New agent status value                 |
| `reason`     | `string?` | Why the transition happened            |
| `step_id`    | `string?` | Current step ID if applicable          |
| `elapsed_ms` | `float?`  | Time spent in previous state           |

---

### `flow_selection`

Initial flow engine selection.

| Field        | Type      | Description                            |
|--------------|-----------|----------------------------------------|
| `flow_mode`  | `string`  | `plan_act` or `coordinator`            |
| `model`      | `string?` | LLM model identifier                  |
| `session_id` | `string?` | Session ID                             |
| `reason`     | `string?` | Selection reason                       |

---

### `workspace`

Workspace lifecycle events (primarily during Deep Research).

| Field               | Type      | Description                                        |
|---------------------|-----------|----------------------------------------------------|
| `action`            | `string`  | `initialized` or `deliverables_ready`              |
| `workspace_type`    | `string?` | `research`, `code_project`, `data_analysis`        |
| `workspace_path`    | `string?` | Absolute path in sandbox                           |
| `structure`         | `object?` | Folder name to purpose mapping                     |
| `files_organized`   | `int`     | Number of files organized                          |
| `deliverables_count`| `int`     | Number of deliverables                             |
| `manifest_path`     | `string?` | Path to workspace manifest                         |

---

### `title`

Session title updates.

| Field   | Type     | Description        |
|---------|----------|--------------------|
| `title` | `string` | New session title  |

---

### `research_mode`

Research mode activation signal.

| Field           | Type     | Description                                |
|-----------------|----------|--------------------------------------------|
| `research_mode` | `string` | `fast_search` or `deep_research`           |

---

### `reflection`

Verification/reflection events during execution.

| Field            | Type      | Description                                          |
|------------------|-----------|------------------------------------------------------|
| `status`         | `string`  | `triggered` or `completed`                           |
| `decision`       | `string?` | `continue`, `adjust`, `replan`, `escalate`, `abort`  |
| `confidence`     | `float?`  | 0.0 to 1.0                                          |
| `summary`        | `string?` | Reflection summary                                   |
| `trigger_reason` | `string?` | Why reflection was triggered                         |

---

### `verification`

Plan verification before execution.

| Field               | Type      | Description                           |
|---------------------|-----------|---------------------------------------|
| `status`            | `string`  | `started`, `passed`, `revision_needed`, `failed` |
| `verdict`           | `string?` | `pass`, `revise`, `fail`              |
| `confidence`        | `float?`  | Verification confidence               |
| `summary`           | `string?` | Verification summary                  |
| `revision_feedback` | `string?` | Feedback for replanning               |

---

### `partial_result`

Partial step results emitted after each step completes.

| Field           | Type     | Description                                        |
|-----------------|----------|----------------------------------------------------|
| `step_index`    | `int`    | Step index                                         |
| `step_title`    | `string` | Step title                                         |
| `headline`      | `string` | One-line summary of results found so far           |
| `sources_count` | `int`    | Number of sources found                            |

---

### `suggestion`

Follow-up suggestion events.

| Field            | Type      | Description                                    |
|------------------|-----------|------------------------------------------------|
| `suggestions`    | `array`   | List of 2-3 contextual suggestion strings      |
| `source`         | `string?` | Source: `completion` or `discuss`               |
| `anchor_event_id`| `string?` | Event ID to anchor context to                  |
| `anchor_excerpt` | `string?` | Brief excerpt from anchored content            |

---

### `confidence`

Confidence calibration events for decision transparency.

| Field                  | Type      | Description                            |
|------------------------|-----------|----------------------------------------|
| `decision`             | `string`  | The decision or action                 |
| `confidence`           | `float`   | Calibrated confidence 0.0-1.0         |
| `level`                | `string`  | `high`, `medium`, `low`               |
| `action_recommendation`| `string`  | `proceed`, `verify`, `ask_user`        |
| `supporting_factors`   | `array`   | List of supporting factors             |
| `risk_factors`         | `array`   | List of risk factors                   |

---

### `skill`

Skill activation events.

| Field           | Type      | Description                                    |
|-----------------|-----------|------------------------------------------------|
| `skill_id`      | `string`  | Skill identifier                               |
| `skill_name`    | `string`  | Human-readable name                            |
| `action`        | `string`  | `activated`, `deactivated`, `matched`          |
| `reason`        | `string`  | Reason for action                              |
| `tools_affected`| `array?`  | List of affected tool names                    |

---

### `skill_activation`

Detailed skill activation diagnostics.

| Field                 | Type      | Description                                    |
|-----------------------|-----------|------------------------------------------------|
| `skill_ids`           | `array`   | Active skill IDs                               |
| `skill_names`         | `array`   | Human-readable names                           |
| `tool_restrictions`   | `array?`  | Restricted tool list (if any)                  |
| `prompt_chars`        | `int`     | Size of injected skill context                 |
| `activation_sources`  | `object`  | skill_id to activation sources mapping         |
| `command_skill_id`    | `string?` | Skill activated via slash command              |
| `auto_trigger_enabled`| `boolean` | Whether auto-trigger was enabled               |

---

### `skill_delivery`

Skill package delivery events.

| Field         | Type      | Description                                    |
|---------------|-----------|------------------------------------------------|
| `package_id`  | `string`  | Unique package ID                              |
| `name`        | `string`  | Skill name                                     |
| `description` | `string`  | Skill description                              |
| `version`     | `string`  | Version string                                 |
| `icon`        | `string`  | Lucide icon name                               |
| `category`    | `string`  | Skill category                                 |
| `file_tree`   | `object`  | Hierarchical file structure for UI             |
| `files`       | `array`   | All files in package (path, content, size)     |
| `file_id`     | `string?` | GridFS file ID for download                    |
| `skill_id`    | `string?` | DB skill ID if saved to database               |

---

### `wait`

Waiting for user input (e.g. CAPTCHA, login, 2FA).

| Field                  | Type      | Description                                    |
|------------------------|-----------|------------------------------------------------|
| `wait_reason`          | `string?` | `user_input`, `captcha`, `login`, `2fa`, `payment`, `verification`, `other` |
| `suggest_user_takeover`| `string?` | `none` or `browser`                            |

---

### `mode_change`

Flow mode switch between discuss and agent modes.

| Field    | Type      | Description                        |
|----------|-----------|------------------------------------|
| `mode`   | `string`  | `discuss` or `agent`               |
| `reason` | `string?` | Reason for mode switch             |

---

### `report`

Task completion report in Notion-like markdown view.

| Field         | Type      | Description                                    |
|---------------|-----------|------------------------------------------------|
| `id`          | `string`  | Unique report ID                               |
| `title`       | `string`  | Report title                                   |
| `content`     | `string`  | Markdown content                               |
| `attachments` | `array?`  | Associated files                               |
| `sources`     | `array?`  | Bibliography/references (SourceCitation objects)|

---

### `thought`

Chain-of-Thought reasoning events.

| Field          | Type      | Description                                    |
|----------------|-----------|------------------------------------------------|
| `status`       | `string`  | `thinking`, `thought`, `chain_complete`        |
| `thought_type` | `string?` | `observation`, `analysis`, `hypothesis`, etc.  |
| `content`      | `string?` | The thought content                            |
| `confidence`   | `float?`  | 0.0 to 1.0                                    |
| `step_name`    | `string?` | Name of the reasoning step                     |
| `chain_id`     | `string?` | ID of the thought chain                        |
| `is_final`     | `boolean` | Whether this completes the chain               |

---

### `comprehension`

Emitted when agent comprehends a long/complex message.

| Field              | Type      | Description                            |
|--------------------|-----------|----------------------------------------|
| `original_length`  | `int`     | Length of original message              |
| `summary`          | `string`  | Agent's summarized understanding       |
| `key_requirements` | `array?`  | Extracted key requirements             |
| `complexity_score` | `float?`  | 0-1 complexity assessment              |

---

### `budget`

Budget threshold and exhaustion events.

| Field               | Type      | Description                            |
|---------------------|-----------|----------------------------------------|
| `action`            | `string`  | `warning`, `exhausted`, `resumed`      |
| `budget_limit`      | `float`   | Budget limit in USD                    |
| `consumed`          | `float`   | Amount consumed in USD                 |
| `remaining`         | `float`   | Amount remaining in USD                |
| `percentage_used`   | `float`   | Percentage of budget used              |
| `warning_threshold` | `float`   | Warning threshold (default 0.8)        |
| `session_paused`    | `boolean` | Whether session is paused              |

---

### `phase`

Phase lifecycle events for structured agent flow.

| Field          | Type      | Description                            |
|----------------|-----------|----------------------------------------|
| `phase_id`     | `string`  | Phase identifier                       |
| `phase_type`   | `string`  | Phase type value                       |
| `label`        | `string`  | Human-readable label                   |
| `status`       | `string`  | `started`, `completed`, `skipped`      |
| `order`        | `int`     | Phase order                            |
| `icon`         | `string`  | Icon identifier                        |
| `color`        | `string`  | Color identifier                       |
| `total_phases` | `int`     | Total number of phases                 |
| `skip_reason`  | `string?` | Reason for skipping (if skipped)       |

---

### `phase_transition`

Phased research progress transition.

| Field         | Type      | Description                            |
|---------------|-----------|----------------------------------------|
| `phase`       | `string`  | Phase name                             |
| `label`       | `string?` | Human-readable label                   |
| `research_id` | `string?` | Research session ID                    |
| `source`      | `string?` | `wide_research` or `session`           |

---

### `wide_research`

Wide research parallel multi-source search progress.

| Field              | Type      | Description                            |
|--------------------|-----------|----------------------------------------|
| `research_id`      | `string`  | Research session ID                    |
| `topic`            | `string`  | Research topic                         |
| `status`           | `string`  | `pending`, `searching`, `aggregating`, `completed`, `failed` |
| `total_queries`    | `int`     | Total search queries                   |
| `completed_queries`| `int`     | Completed search queries               |
| `sources_found`    | `int`     | Number of sources found                |
| `search_types`     | `array`   | Types of searches being run            |
| `current_query`    | `string?` | Currently executing query              |
| `errors`           | `array`   | Error messages                         |

---

### `canvas_update`

Canvas project modification events.

| Field                | Type      | Description                            |
|----------------------|-----------|----------------------------------------|
| `project_id`        | `string`  | Canvas project ID                      |
| `session_id`        | `string?` | Session ID                             |
| `operation`         | `string`  | `create_project`, `add_element`, `modify_element`, etc. |
| `element_count`     | `int`     | Current element count                  |
| `project_name`      | `string?` | Project name                           |
| `version`           | `int`     | Project version                        |
| `changed_element_ids`| `array?` | IDs of changed elements               |
| `source`            | `string?` | `agent`, `manual`, `system`            |

---

### `eval_metrics`

Quality evaluation metrics (Ragas-style).

| Field                | Type      | Description                            |
|----------------------|-----------|----------------------------------------|
| `metrics`            | `object`  | Serialized evaluation batch            |
| `hallucination_score`| `float`   | Hallucination rate for fast alerting   |
| `passed`             | `boolean` | True if no metric exceeded threshold   |

---

### `task_recreation`

Task recreation after comprehension or clarification.

| Field                | Type   | Description                            |
|----------------------|--------|----------------------------------------|
| `reason`             | `string` | Why tasks were recreated             |
| `previous_step_count`| `int`  | Steps before recreation                |
| `new_step_count`     | `int`  | Steps after recreation                 |
| `preserved_findings` | `int`  | Findings preserved from previous work  |

---

### `checkpoint_saved`

Phased research checkpoint persistence.

| Field           | Type      | Description                            |
|-----------------|-----------|----------------------------------------|
| `phase`         | `string`  | Phase name                             |
| `research_id`   | `string?` | Research session ID                    |
| `notes_preview` | `string?` | Preview of saved notes                 |
| `source_count`  | `int?`    | Number of sources saved                |

---

### `idle`

Agent entering standby state.

| Field    | Type      | Description                |
|----------|-----------|----------------------------|
| `reason` | `string?` | Reason for entering idle   |

---

### `mcp_health`

MCP server health status.

| Field             | Type      | Description                        |
|-------------------|-----------|------------------------------------|
| `server_name`     | `string`  | MCP server name                    |
| `healthy`         | `boolean` | Health status                      |
| `error`           | `string?` | Error message if unhealthy         |
| `tools_available` | `int`     | Number of available tools          |

---

### `knowledge`

Knowledge module events.

| Field     | Type     | Description                    |
|-----------|----------|--------------------------------|
| `scope`   | `string` | Knowledge scope                |
| `content` | `string` | Knowledge content              |

---

### `datasource`

Datasource module events.

| Field           | Type     | Description                    |
|-----------------|----------|--------------------------------|
| `api_name`      | `string` | API name                       |
| `documentation` | `string` | API documentation              |

---

### `path`

Tree-of-Thoughts multi-path exploration events.

| Field         | Type      | Description                                          |
|---------------|-----------|------------------------------------------------------|
| `path_id`     | `string`  | Path identifier                                      |
| `action`      | `string`  | `created`, `exploring`, `completed`, `abandoned`, `selected` |
| `score`       | `float?`  | Path score                                           |
| `description` | `string?` | Path description                                     |

---

### `multi_task`

Multi-task challenge progress events.

| Field                | Type      | Description                                    |
|----------------------|-----------|------------------------------------------------|
| `challenge_id`       | `string`  | Challenge identifier                           |
| `action`             | `string`  | `started`, `task_switching`, `task_completed`, `challenge_completed` |
| `current_task_index` | `int`     | Current task index                             |
| `total_tasks`        | `int`     | Total number of tasks                          |
| `current_task`       | `string?` | Current task description                       |
