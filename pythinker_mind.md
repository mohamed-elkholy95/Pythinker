# Pythinker Mind — Complete File Map

> Every Python file that forms Pythinker's cognitive architecture, organized by layer and responsibility.
> All paths are relative to `backend/app/`.

---

## 1. Domain Models (`domain/models/`)

| File | Purpose |
|------|---------|
| `domain/models/__init__.py` | Package init |
| `domain/models/agent.py` | Agent entity |
| `domain/models/agent_capability.py` | Agent capability definitions |
| `domain/models/agent_message.py` | Agent message model |
| `domain/models/agent_response.py` | Agent response model |
| `domain/models/auth.py` | Authentication models |
| `domain/models/benchmark.py` | Benchmark models |
| `domain/models/canvas.py` | Canvas/whiteboard model |
| `domain/models/citation_discipline.py` | Citation discipline rules |
| `domain/models/claim_provenance.py` | Claim provenance tracking |
| `domain/models/connector.py` | External connector model |
| `domain/models/context_memory.py` | Context memory model |
| `domain/models/deep_research.py` | Deep research session model |
| `domain/models/event.py` | Domain event model |
| `domain/models/failure_snapshot.py` | Failure snapshot model |
| `domain/models/file.py` | File model |
| `domain/models/flow_state.py` | Flow state machine model |
| `domain/models/knowledge_gap.py` | Knowledge gap identification |
| `domain/models/long_term_memory.py` | Long-term memory model |
| `domain/models/mcp_config.py` | MCP configuration model |
| `domain/models/mcp_resource.py` | MCP resource model |
| `domain/models/memory.py` | Memory entity |
| `domain/models/memory_evidence.py` | Memory evidence/grounding |
| `domain/models/message.py` | Chat message model |
| `domain/models/multi_task.py` | Multi-task model |
| `domain/models/path_state.py` | Execution path state |
| `domain/models/plan.py` | Plan model |
| `domain/models/pressure.py` | Resource pressure model |
| `domain/models/recovery.py` | Recovery model |
| `domain/models/reflection.py` | Reflection model |
| `domain/models/repo_map.py` | Repository map model |
| `domain/models/report.py` | Report model |
| `domain/models/research_phase.py` | Research phase model |
| `domain/models/research_task.py` | Research task model |
| `domain/models/sandbox/file.py` | Sandbox file model |
| `domain/models/sandbox/shell.py` | Sandbox shell model |
| `domain/models/sandbox/supervisor.py` | Sandbox supervisor model |
| `domain/models/scheduled_task.py` | Scheduled task model |
| `domain/models/screenshot.py` | Screenshot model |
| `domain/models/search.py` | Search model |
| `domain/models/session.py` | Session entity |
| `domain/models/skill.py` | Skill model |
| `domain/models/skill_package.py` | Skill package model |
| `domain/models/snapshot.py` | State snapshot model |
| `domain/models/source_attribution.py` | Source attribution model |
| `domain/models/source_citation.py` | Source citation model |
| `domain/models/source_quality.py` | Source quality scoring |
| `domain/models/state_manifest.py` | State manifest model |
| `domain/models/state_model.py` | Generic state model |
| `domain/models/structured_outputs.py` | Structured output schemas |
| `domain/models/supervisor.py` | Supervisor model |
| `domain/models/sync_outbox.py` | Sync outbox model |
| `domain/models/thought.py` | Thought/reasoning model |
| `domain/models/timeline.py` | Timeline model |
| `domain/models/tool_call.py` | Tool call model |
| `domain/models/tool_result.py` | Tool result model |
| `domain/models/url_verification.py` | URL verification model |
| `domain/models/usage.py` | Usage tracking model |
| `domain/models/user.py` | User entity |
| `domain/models/user_preference.py` | User preference model |
| `domain/models/user_settings.py` | User settings model |
| `domain/models/visited_source.py` | Visited source tracking |

---

## 2. Domain Repositories (Abstractions) (`domain/repositories/`)

| File | Purpose |
|------|---------|
| `domain/repositories/agent_repository.py` | Agent persistence interface |
| `domain/repositories/analytics_repository.py` | Analytics persistence interface |
| `domain/repositories/canvas_repository.py` | Canvas persistence interface |
| `domain/repositories/connector_repository.py` | Connector persistence interface |
| `domain/repositories/mcp_repository.py` | MCP persistence interface |
| `domain/repositories/memory_repository.py` | Memory persistence interface |
| `domain/repositories/provenance_repository.py` | Provenance persistence interface |
| `domain/repositories/screenshot_repository.py` | Screenshot persistence interface |
| `domain/repositories/session_repository.py` | Session persistence interface |
| `domain/repositories/skill_repository.py` | Skill persistence interface |
| `domain/repositories/snapshot_repository.py` | Snapshot persistence interface |
| `domain/repositories/user_repository.py` | User persistence interface |
| `domain/repositories/vector_memory_repository.py` | Vector memory interface |
| `domain/repositories/vector_repos.py` | Vector repository abstractions |

---

## 3. Agent Services — Core (`domain/services/agents/`)

### 3.1 Execution & Lifecycle

| File | Purpose |
|------|---------|
| `agents/__init__.py` | Package init |
| `agents/base.py` | Base agent class |
| `agents/execution.py` | Main execution loop (step runner) |
| `agents/reflective_executor.py` | Execution with built-in reflection |
| `agents/planner.py` | Planning phase logic |
| `agents/critic.py` | Plan critique logic |
| `agents/critic_agent.py` | Dedicated critic sub-agent |
| `agents/reflection.py` | Reflection phase logic |
| `agents/verifier.py` | Verification phase logic |
| `agents/research_agent.py` | Research sub-agent |
| `agents/spawner.py` | Sub-agent spawning |

### 3.2 Intent & Task Understanding

| File | Purpose |
|------|---------|
| `agents/intent_classifier.py` | Classify user intent |
| `agents/intent_tracker.py` | Track intent across steps |
| `agents/requirement_extractor.py` | Extract requirements from input |
| `agents/task_decomposer.py` | Decompose tasks into subtasks |
| `agents/task_state_manager.py` | Track task state transitions |
| `agents/complexity_assessor.py` | Assess task complexity |
| `agents/duplicate_query_policy.py` | Detect duplicate queries |

### 3.3 Reasoning (`agents/reasoning/`)

| File | Purpose |
|------|---------|
| `agents/reasoning/__init__.py` | Package init |
| `agents/reasoning/engine.py` | Core reasoning engine |
| `agents/reasoning/thought_chain.py` | Chain-of-thought reasoning |
| `agents/reasoning/thought_tree.py` | Tree-of-thought reasoning |
| `agents/reasoning/confidence.py` | Confidence scoring |
| `agents/reasoning/self_consistency.py` | Self-consistency validation |
| `agents/reasoning/meta_cognition.py` | Meta-cognitive awareness |

### 3.4 Safety & Guardrails

| File | Purpose |
|------|---------|
| `agents/guardrails.py` | Safety guardrails |
| `agents/hallucination_detector.py` | Hallucination detection |
| `agents/content_hallucination_detector.py` | Content-level hallucination |
| `agents/grounding_validator.py` | Grounding validation |
| `agents/chain_of_verification.py` | Chain-of-verification |
| `agents/url_verification.py` | URL verification |
| `agents/security_assessor.py` | Security risk assessment |
| `agents/security_critic.py` | Security critique |
| `agents/compliance_gates.py` | Compliance gate checks |
| `agents/gaming_detector.py` | Gaming/abuse detection |
| `agents/self_consistency.py` | Self-consistency checks |
| `agents/output_coverage_validator.py` | Output completeness validation |
| `agents/response_policy.py` | Response policy enforcement |

### 3.5 Error Handling & Recovery

| File | Purpose |
|------|---------|
| `agents/error_handler.py` | Error handling logic |
| `agents/error_integration.py` | Error integration layer |
| `agents/error_pattern_analyzer.py` | Error pattern analysis |
| `agents/stuck_detector.py` | Stuck loop detection |
| `agents/self_healing_loop.py` | Self-healing recovery |
| `agents/response_recovery.py` | Response recovery |
| `agents/failure_snapshot_service.py` | Failure snapshot capture |

### 3.6 Memory (`agents/memory/`)

| File | Purpose |
|------|---------|
| `agents/memory/__init__.py` | Package init |
| `agents/memory/importance_analyzer.py` | Memory importance scoring |
| `agents/memory/semantic_compressor.py` | Semantic memory compression |
| `agents/memory/temporal_compressor.py` | Temporal memory compression |
| `agents/memory_manager.py` | Memory orchestration |

### 3.7 Context & Token Management

| File | Purpose |
|------|---------|
| `agents/context_manager.py` | Context window management |
| `agents/token_manager.py` | Token budget management |
| `agents/prompt_compressor.py` | Prompt compression |
| `agents/prompt_adapter.py` | Prompt adaptation per model |
| `agents/prompt_cache_manager.py` | Prompt caching |
| `agents/response_compressor.py` | Response compression |

### 3.8 Routing & Optimization

| File | Purpose |
|------|---------|
| `agents/smart_router.py` | Smart model routing |
| `agents/model_router.py` | Model selection logic |
| `agents/parallel_executor.py` | Parallel tool execution |
| `agents/reward_scoring.py` | Reward/scoring logic |
| `agents/benchmarks.py` | Benchmark evaluation |
| `agents/metrics.py` | Agent metrics collection |
| `agents/usage_context.py` | Usage context tracking |
| `agents/autonomy_config.py` | Autonomy level config |

### 3.9 Learning (`agents/learning/`)

| File | Purpose |
|------|---------|
| `agents/learning/__init__.py` | Package init |
| `agents/learning/pattern_learner.py` | Pattern learning |
| `agents/learning/prompt_optimizer.py` | Prompt optimization |
| `agents/learning/knowledge_transfer.py` | Knowledge transfer |

### 3.10 Multi-Agent Collaboration

| File | Purpose |
|------|---------|
| `agents/collaboration/__init__.py` | Package init |
| `agents/collaboration/patterns.py` | Collaboration patterns |
| `agents/communication/__init__.py` | Package init |
| `agents/communication/protocol.py` | Inter-agent communication |
| `agents/scheduling/__init__.py` | Package init |
| `agents/scheduling/resource_scheduler.py` | Resource scheduling |
| `agents/registry/__init__.py` | Package init |
| `agents/registry/capability_registry.py` | Capability registry |

### 3.11 Speculative Execution

| File | Purpose |
|------|---------|
| `agents/speculative/__init__.py` | Package init |
| `agents/speculative/executor.py` | Speculative execution |

### 3.12 Caching (`agents/caching/`)

| File | Purpose |
|------|---------|
| `agents/caching/__init__.py` | Package init |
| `agents/caching/reasoning_cache.py` | Reasoning result caching |
| `agents/caching/result_cache.py` | General result caching |

### 3.13 Planning (`agents/planning/`)

| File | Purpose |
|------|---------|
| `agents/planning/__init__.py` | Package init |
| `agents/planning/lazy_planner.py` | Lazy/deferred planning |

---

## 4. Flow Services (`domain/services/flows/`)

| File | Purpose |
|------|---------|
| `flows/__init__.py` | Package init |
| `flows/base.py` | Base flow class |
| `flows/plan_act.py` | Plan-Act flow (primary) |
| `flows/plan_act_graph.py` | Graph-based plan-act |
| `flows/workflow_graph.py` | Workflow graph engine |
| `flows/fast_path.py` | Fast-path flow (simple tasks) |
| `flows/discuss.py` | Discussion/chat flow |
| `flows/deep_research.py` | Deep research flow |
| `flows/enhanced_research.py` | Enhanced research flow |
| `flows/wide_research.py` | Wide research flow |
| `flows/phased_research.py` | Phased research flow |
| `flows/tree_of_thoughts_flow.py` | Tree-of-thoughts flow |
| `flows/parallel_executor.py` | Parallel flow executor |
| `flows/path_explorer.py` | Path exploration |
| `flows/path_scorer.py` | Path scoring |
| `flows/path_aggregator.py` | Path aggregation |
| `flows/complexity_analyzer.py` | Flow complexity analysis |
| `flows/task_orchestrator.py` | Task orchestration |
| `flows/checkpoint_manager.py` | Checkpoint management |
| `flows/graph_checkpoint_manager.py` | Graph checkpoint management |
| `flows/step_failure.py` | Step failure handling |
| `flows/acknowledgment.py` | Fast acknowledgment |
| `flows/fast_ack_refiner.py` | Fast ack refinement |
| `flows/prompt_quick_validator.py` | Prompt quick validation |
| `flows/enhanced_prompt_quick_validator.py` | Enhanced prompt validation |
| `flows/phase_registry.py` | Phase registry |

---

## 5. Tool Services (`domain/services/tools/`)

| File | Purpose |
|------|---------|
| `tools/__init__.py` | Package init |
| `tools/schemas.py` | Tool schemas |
| `tools/agent_mode.py` | Agent mode tool |
| `tools/code_dev.py` | Code development tool |
| `tools/export.py` | Export tool |
| `tools/git.py` | Git tool |
| `tools/idle.py` | Idle/wait tool |
| `tools/map_tool.py` | Map tool |
| `tools/message.py` | Message tool |
| `tools/paywall_detector.py` | Paywall detection tool |
| `tools/plan.py` | Plan tool |
| `tools/repo_map.py` | Repository map tool |
| `tools/result_analyzer.py` | Tool result analyzer |
| `tools/tool_profiler.py` | Tool profiling |
| `tools/workspace.py` | Workspace tool |

---

## 6. Prompt Templates (`domain/services/prompts/`)

| File | Purpose |
|------|---------|
| `prompts/__init__.py` | Package init |
| `prompts/critic.py` | Critic prompt templates |
| `prompts/reflection.py` | Reflection prompt templates |
| `prompts/skill_creator.py` | Skill creator prompts |
| `prompts/verifier.py` | Verifier prompt templates |

---

## 7. Orchestration (`domain/services/orchestration/`)

| File | Purpose |
|------|---------|
| `orchestration/__init__.py` | Package init |
| `orchestration/agent_factory.py` | Agent factory |
| `orchestration/agent_types.py` | Agent type definitions |
| `orchestration/coordinator_flow.py` | Coordinator flow |
| `orchestration/research_agent.py` | Research agent orchestration |

---

## 8. Analyzers (`domain/services/analyzers/`)

| File | Purpose |
|------|---------|
| `analyzers/__init__.py` | Package init |
| `analyzers/dependency_analyzer.py` | Dependency analysis |
| `analyzers/pattern_detector.py` | Pattern detection |
| `analyzers/quality_analyzer.py` | Quality analysis |

---

## 9. Prediction (`domain/services/prediction/`)

| File | Purpose |
|------|---------|
| `prediction/__init__.py` | Package init |
| `prediction/failure_predictor.py` | Failure prediction |
| `prediction/feature_extractor.py` | Feature extraction |
| `prediction/interventions.py` | Intervention strategies |
| `prediction/threshold_calibrator.py` | Threshold calibration |

---

## 10. Validation (`domain/services/validation/`)

| File | Purpose |
|------|---------|
| `validation/__init__.py` | Package init |
| `validation/dependency_analyzer.py` | Dependency validation |
| `validation/plan_validator.py` | Plan validation |
| `validation/resource_validator.py` | Resource validation |

---

## 11. Concurrency (`domain/services/concurrency/`)

| File | Purpose |
|------|---------|
| `concurrency/__init__.py` | Package init |
| `concurrency/token_budget.py` | Token budget concurrency |

---

## 12. Workspace (`domain/services/workspace/`)

| File | Purpose |
|------|---------|
| `workspace/__init__.py` | Package init |
| `workspace/session_workspace_initializer.py` | Session workspace init |
| `workspace/workspace_organizer.py` | Workspace organization |
| `workspace/workspace_selector.py` | Workspace selection |
| `workspace/workspace_templates.py` | Workspace templates |

---

## 13. Skills (`domain/services/skills/`)

| File | Purpose |
|------|---------|
| `skills/__init__.py` | Package init |
| `skills/excel_generator.py` | Excel generation skill |
| `skills/init_skill.py` | Skill initialization |
| `skills/skill_validator.py` | Skill validation |

---

## 14. Embeddings (`domain/services/embeddings/`)

| File | Purpose |
|------|---------|
| `embeddings/__init__.py` | Package init |
| `embeddings/bm25_encoder.py` | BM25 sparse vector encoder |

---

## 15. Evaluation (`domain/services/evaluation/`)

| File | Purpose |
|------|---------|
| `evaluation/__init__.py` | Package init |

---

## 16. Top-Level Domain Services (`domain/services/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Package init |
| `agent_domain_service.py` | Agent domain service |
| `agent_factory.py` | Agent factory |
| `agent_task_runner.py` | Agent task runner |
| `attention_injector.py` | Attention injection |
| `benchmark_extractor.py` | Benchmark extraction |
| `citation_validator.py` | Citation validation |
| `command_registry.py` | Command registry |
| `context_manager.py` | Global context management |
| `datasource.py` | Data source service |
| `hmas_orchestrator.py` | HMAS orchestrator |
| `knowledge.py` | Knowledge service |
| `memory_service.py` | Memory service |
| `reconciliation_job.py` | Data reconciliation |
| `report_generator.py` | Report generation |
| `role_scoped_memory.py` | Role-scoped memory |
| `skill_activation_framework.py` | Skill activation |
| `skill_loader.py` | Skill loader |
| `skill_packager.py` | Skill packager |
| `skill_registry.py` | Skill registry |
| `skill_trigger_matcher.py` | Skill trigger matching |
| `skill_validator.py` | Skill validation |
| `source_filter.py` | Source filtering |
| `sync_worker.py` | Sync worker |
| `task_templates.py` | Task templates |
| `tool_event_handler.py` | Tool event handling |

---

## 17. Core Infrastructure (`core/`)

| File | Purpose |
|------|---------|
| `core/config.py` | Application configuration (Settings) |
| `core/async_utils.py` | Async utilities |
| `core/retry.py` | Retry logic |
| `core/sandbox_manager.py` | Sandbox lifecycle management |
| `core/sandbox_pool.py` | Sandbox connection pooling |
| `core/feature_flags.py` | Feature flag system |
| `core/health_monitor.py` | Health monitoring |
| `core/resource_manager.py` | Resource management |
| `core/resource_monitor.py` | Resource monitoring |
| `core/alert_manager.py` | Alert management |
| `core/circuit_breaker_registry.py` | Circuit breaker registry |
| `core/circuit_breaker_adaptive.py` | Adaptive circuit breaker |
| `core/error_manager.py` | Error management |
| `core/failure_tracker.py` | Failure tracking |
| `core/recovery_monitor.py` | Recovery monitoring |
| `core/system_integrator.py` | System integration |
| `core/deep_research_manager.py` | Deep research management |

---

## 18. Application Services (`application/services/`)

| File | Purpose |
|------|---------|
| `application/services/__init__.py` | Package init |
| `application/services/agent_service.py` | Agent lifecycle orchestration |
| `application/services/analytics_service.py` | Analytics service |
| `application/services/auth_service.py` | Authentication service |
| `application/services/canvas_service.py` | Canvas service |
| `application/services/connector_service.py` | Connector service |
| `application/services/email_service.py` | Email service |
| `application/services/file_service.py` | File service |
| `application/services/maintenance_service.py` | Maintenance service |
| `application/services/rating_service.py` | Rating service |
| `application/services/screenshot_service.py` | Screenshot service |
| `application/services/settings_service.py` | Settings service |
| `application/services/skill_service.py` | Skill service |
| `application/services/token_service.py` | Token service |
| `application/services/typo_correction_service.py` | Typo correction service |
| `application/services/usage_service.py` | Usage tracking service |

---

## 19. Application Schemas (`application/schemas/`)

| File | Purpose |
|------|---------|
| `application/schemas/__init__.py` | Package init |
| `application/schemas/file.py` | File DTOs |
| `application/schemas/session.py` | Session DTOs |
| `application/schemas/workspace.py` | Workspace DTOs |

---

## Summary

| Category | File Count |
|----------|-----------|
| Domain Models | 62 |
| Domain Repositories | 14 |
| Agent Services | 82 |
| Flow Services | 26 |
| Tool Services | 15 |
| Prompt Templates | 5 |
| Orchestration | 5 |
| Analyzers | 4 |
| Prediction | 5 |
| Validation | 4 |
| Concurrency | 2 |
| Workspace | 5 |
| Skills | 4 |
| Embeddings | 2 |
| Top-Level Domain Services | 27 |
| Core Infrastructure | 17 |
| Application Services | 16 |
| Application Schemas | 4 |
| **Total** | **~299** |
