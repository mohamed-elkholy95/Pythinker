# Pythinker Skill System Architecture

## Professional Skill System Design & Enhancement Pipeline

This document outlines the comprehensive skill system architecture for Pythinker, incorporating industry best practices from LangGraph, LangChain, and Swarms frameworks.

---

## Table of Contents

1. [Current Architecture Analysis](#1-current-architecture-analysis)
2. [Industry Best Practices](#2-industry-best-practices)
3. [Enhanced Architecture Design](#3-enhanced-architecture-design)
4. [Skill Lifecycle Pipeline](#4-skill-lifecycle-pipeline)
5. [Agent Workflow Integration](#5-agent-workflow-integration)
6. [Implementation Roadmap](#6-implementation-roadmap)

---

## 1. Current Architecture Analysis

### 1.1 Domain Model

```
┌─────────────────────────────────────────────────────────────────┐
│                         Skill Entity                            │
├─────────────────────────────────────────────────────────────────┤
│ id: str (slug-based, e.g., "research", "custom-xyz-abc123")     │
│ name: str                                                       │
│ description: str                                                │
│ category: SkillCategory                                         │
│ source: SkillSource (OFFICIAL | COMMUNITY | CUSTOM)             │
│ icon: str (Lucide icon name)                                    │
│ required_tools: list[str]                                       │
│ optional_tools: list[str]                                       │
│ system_prompt_addition: str (core skill instructions)           │
│ invocation_type: SkillInvocationType (USER | AI | BOTH)         │
│ allowed_tools: list[str] | None (tool restrictions)             │
│ supports_dynamic_context: bool (enables !command syntax)        │
│ trigger_patterns: list[str] (regex for auto-activation)         │
│ owner_id: str | None (custom skill ownership)                   │
│ is_public: bool (community sharing)                             │
│ parent_skill_id: str | None (forked skills)                     │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Current Layer Structure

```
backend/app/
├── domain/
│   ├── models/
│   │   ├── skill.py              # Skill, SkillCategory, SkillSource enums
│   │   └── skill_package.py      # SkillPackage, SkillPackageFile
│   ├── repositories/
│   │   └── skill_repository.py   # Abstract interface (Protocol)
│   └── services/
│       ├── skill_validator.py    # Security validation (20+ patterns)
│       ├── skill_packager.py     # ZIP package creation
│       ├── prompts/
│       │   ├── skill_context.py  # Context building & injection
│       │   └── skill_creator.py  # Guided creation prompts
│       └── tools/
│           ├── skill_invoke.py   # Meta-tool for AI invocation
│           └── skill_creator.py  # CRUD tools for custom skills
├── application/
│   └── services/
│       └── skill_service.py      # Application layer CRUD
├── infrastructure/
│   └── repositories/
│       └── mongo_skill_repository.py  # MongoDB implementation
└── interfaces/
    ├── api/
    │   └── skills_routes.py      # REST API endpoints
    └── schemas/
        └── skill.py              # Request/Response Pydantic models
```

### 1.3 Current Strengths

| Area | Assessment | Notes |
|------|------------|-------|
| Domain Model | ✅ Excellent | Clean enums, comprehensive fields |
| Security Validation | ✅ Excellent | 20+ injection patterns blocked |
| CRUD Pipeline | ✅ Complete | Full lifecycle support |
| Package System | ✅ Good | ZIP-based .skill format |
| MongoDB Persistence | ✅ Good | Owner-based queries |
| Type Safety | ✅ Excellent | Full type hints throughout |

### 1.4 Identified Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| Trigger Pattern System | Medium | Auto-activation not implemented |
| Tool Binding at Runtime | High | Static tool lists, no dynamic binding |
| Skill Composition | Medium | No skill-to-skill dependencies |
| Community Discovery | Low | No browse/search for public skills |
| Skill Versioning | Medium | No version history/rollback |
| Performance Caching | Low | API called on every skill load |

---

## 2. Industry Best Practices

### 2.1 LangGraph Dynamic Tool Selection

LangGraph provides runtime context-based tool binding via `configure_model`:

```python
# LangGraph Pattern: Dynamic Tool Binding
from langgraph.prebuilt import create_react_agent
from langgraph.runtime import Runtime

@dataclass
class SkillContext:
    allowed_tools: list[str]
    skill_prompts: list[str]

def configure_model(state: AgentState, runtime: Runtime[SkillContext]):
    """Configure model with tools based on runtime context."""
    selected_tools = [
        tool for tool in all_tools
        if tool.name in runtime.context.allowed_tools
    ]
    return model.bind_tools(selected_tools)

agent = create_react_agent(configure_model, tools=all_tools)
```

**Pythinker Application**: Implement dynamic tool binding based on skill `allowed_tools` field at agent creation time.

### 2.2 LangChain Tool Decorator Pattern

LangChain uses the `@tool` decorator for clean tool definitions:

```python
# LangChain Pattern: Tool Definition
from langchain.tools import tool

@tool
def search_database(query: str, limit: int = 10) -> str:
    """Search the customer database for records matching the query.

    Args:
        query: Search terms to look for
        limit: Maximum number of results to return
    """
    return f"Found {limit} results for '{query}'"
```

**Pythinker Application**: Allow skills to define inline tool implementations for skill-specific operations.

### 2.3 LangGraph Swarm Handoff Pattern

Multi-agent handoff with task context propagation:

```python
# LangGraph Swarm Pattern: Agent Handoff
from langgraph_swarm import create_handoff_tool

def create_custom_handoff_tool(agent_name: str, description: str):
    @tool(name, description=description)
    def handoff_to_agent(
        task_description: Annotated[str, "Detailed task for next agent"],
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        return Command(
            goto=agent_name,
            graph=Command.PARENT,
            update={
                "messages": messages + [tool_message],
                "active_agent": agent_name,
                "task_description": task_description,
            },
        )
    return handoff_to_agent
```

**Pythinker Application**: Skills can define agent handoffs to specialized sub-agents.

### 2.4 Dynamic System Prompt Middleware

LangChain's middleware pattern for runtime prompt modification:

```python
# LangChain Pattern: Dynamic Prompt
from langchain.agents.middleware import dynamic_prompt, ModelRequest

@dynamic_prompt
def skill_prompt_middleware(request: ModelRequest) -> str:
    user_context = request.runtime.context
    base_prompt = "You are a helpful assistant."

    if user_context.get("skill_id"):
        skill_additions = get_skill_prompt(user_context["skill_id"])
        return f"{base_prompt}\n\n{skill_additions}"

    return base_prompt
```

**Pythinker Application**: Current `build_skill_context()` aligns with this pattern; enhance with caching.

### 2.5 Swarms YAML-Based Agent Creation

Swarms enables declarative agent/skill definitions:

```yaml
# Swarms Pattern: YAML Agent Definition
agents:
  - name: researcher
    system_prompt: "You are a research specialist..."
    model_name: gpt-4o
    tools:
      - web_search
      - document_reader

  - name: writer
    system_prompt: "You are a content writer..."
    model_name: gpt-4o
    depends_on: researcher
```

**Pythinker Application**: Support YAML-based skill definitions for power users.

---

## 3. Enhanced Architecture Design

### 3.1 Skill System Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Skill System Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Frontend   │───▶│   REST API   │───▶│   Skill      │                   │
│  │  Components  │    │   /skills/*  │    │   Service    │                   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘                   │
│                                                  │                           │
│  ┌───────────────────────────────────────────────┼──────────────────────┐   │
│  │                      Domain Layer             ▼                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │   │
│  │  │   Skill     │  │   Skill     │  │     Skill Context Builder   │  │   │
│  │  │  Validator  │  │  Packager   │  │  ┌─────────────────────────┐│  │   │
│  │  │             │  │             │  │  │ • Dynamic Expansion     ││  │   │
│  │  │ • Security  │  │ • ZIP Pack  │  │  │ • Argument Substitution ││  │   │
│  │  │ • Tool List │  │ • SKILL.md  │  │  │ • Tool Restrictions     ││  │   │
│  │  │ • Length    │  │ • File Tree │  │  │ • XML Encapsulation     ││  │   │
│  │  └─────────────┘  └─────────────┘  │  └─────────────────────────┘│  │   │
│  │                                    └─────────────┬───────────────┘  │   │
│  │  ┌─────────────────────────────────────────────┐ │                  │   │
│  │  │              Skill Tools                    │ │                  │   │
│  │  │  ┌──────────────┐  ┌──────────────────────┐│ │                  │   │
│  │  │  │ skill_invoke │  │ skill_create/delete  ││ │                  │   │
│  │  │  │ (Meta-tool)  │  │ (CRUD tools)         ││ │                  │   │
│  │  │  └──────────────┘  └──────────────────────┘│ │                  │   │
│  │  └────────────────────────────────────────────┘ │                  │   │
│  └─────────────────────────────────────────────────┼──────────────────┘   │
│                                                    │                       │
│  ┌─────────────────────────────────────────────────▼──────────────────┐   │
│  │                     Agent Execution Layer                          │   │
│  │  ┌─────────────────────────────────────────────────────────────┐  │   │
│  │  │               ExecutionAgent._setup()                       │  │   │
│  │  │  • Load skills from message.skills                          │  │   │
│  │  │  • Call build_skill_context_from_ids()                      │  │   │
│  │  │  • Inject into system_prompt                                │  │   │
│  │  │  • Apply tool restrictions via get_allowed_tools_from_skills│  │   │
│  │  └─────────────────────────────────────────────────────────────┘  │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Enhanced Skill Model

```python
# Enhanced Skill Model with Industry Patterns
@dataclass
class EnhancedSkill:
    # Core Fields (existing)
    id: str
    name: str
    description: str
    category: SkillCategory
    source: SkillSource
    system_prompt_addition: str

    # Tool Configuration (enhanced)
    required_tools: list[str]
    optional_tools: list[str]
    allowed_tools: list[str] | None
    tool_overrides: dict[str, ToolOverride] | None  # NEW: Custom tool behavior

    # Invocation Control (existing)
    invocation_type: SkillInvocationType
    trigger_patterns: list[str]

    # Composition (NEW)
    dependencies: list[str]  # Other skill IDs this depends on
    conflicts_with: list[str]  # Skills that cannot be used together
    extends: str | None  # Parent skill ID for inheritance

    # Agent Handoff (NEW - from LangGraph Swarm)
    handoff_targets: list[HandoffTarget] | None

    # Versioning (NEW)
    version: str
    changelog: list[ChangelogEntry]

    # Runtime Hooks (NEW)
    on_activate: str | None  # Python code to run on skill activation
    on_deactivate: str | None  # Python code to run on deactivation

    # Metadata
    owner_id: str | None
    is_public: bool
    created_at: datetime
    updated_at: datetime

@dataclass
class ToolOverride:
    """Override default tool behavior for skill context."""
    tool_name: str
    description_override: str | None
    parameter_defaults: dict[str, Any]
    validation_rules: list[str]

@dataclass
class HandoffTarget:
    """Agent handoff configuration (LangGraph Swarm pattern)."""
    agent_type: str  # e.g., "research", "coding", "data-analysis"
    description: str  # When to handoff
    context_fields: list[str]  # State fields to pass
```

### 3.3 Skill Registry Pattern

```python
# Skill Registry with Caching and Dynamic Loading
class SkillRegistry:
    """Centralized skill registry with caching and lazy loading."""

    _instance: ClassVar["SkillRegistry | None"] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._tool_cache: dict[str, set[str]] = {}
        self._context_cache: dict[str, str] = {}
        self._last_refresh: datetime | None = None
        self._ttl = timedelta(minutes=5)

    @classmethod
    async def get_instance(cls) -> "SkillRegistry":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._load_skills()
        return cls._instance

    async def get_skill(self, skill_id: str) -> Skill | None:
        """Get skill with cache refresh."""
        await self._ensure_fresh()
        return self._skills.get(skill_id)

    async def get_skills_for_context(
        self,
        skill_ids: list[str],
        expand_dependencies: bool = True,
    ) -> list[Skill]:
        """Get skills with dependency resolution."""
        skills = []
        resolved = set()

        async def resolve(sid: str):
            if sid in resolved:
                return
            resolved.add(sid)

            skill = await self.get_skill(sid)
            if not skill:
                return

            # Resolve dependencies first (topological sort)
            if expand_dependencies and skill.dependencies:
                for dep_id in skill.dependencies:
                    await resolve(dep_id)

            skills.append(skill)

        for skill_id in skill_ids:
            await resolve(skill_id)

        return skills

    async def build_context(
        self,
        skill_ids: list[str],
        arguments: str = "",
    ) -> SkillContextResult:
        """Build complete skill context with caching."""
        cache_key = f"{':'.join(sorted(skill_ids))}:{hash(arguments)}"

        if cache_key in self._context_cache:
            return self._context_cache[cache_key]

        skills = await self.get_skills_for_context(skill_ids)

        result = SkillContextResult(
            prompt_addition=await self._build_prompt(skills, arguments),
            allowed_tools=self._compute_allowed_tools(skills),
            required_tools=self._compute_required_tools(skills),
            handoff_targets=self._collect_handoff_targets(skills),
        )

        self._context_cache[cache_key] = result
        return result

@dataclass
class SkillContextResult:
    """Complete skill context for agent execution."""
    prompt_addition: str
    allowed_tools: set[str] | None
    required_tools: set[str]
    handoff_targets: list[HandoffTarget]
```

---

## 4. Skill Lifecycle Pipeline

### 4.1 Skill Creation Pipeline

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Skill Creation Pipeline                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. INPUT                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • User provides skill definition (UI, API, or YAML)             │    │
│  │ • Optional: Fork from existing skill (parent_skill_id)          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  2. VALIDATION                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ SkillValidator                                                  │    │
│  │ ├── Security: Prompt injection patterns (20+ regex)             │    │
│  │ ├── Tool Whitelist: Verify all tools are allowed                │    │
│  │ ├── Length: Max 4000 chars prompt, 15 tools                     │    │
│  │ ├── Syntax: Valid trigger patterns (regex)                      │    │
│  │ ├── Dependencies: Check referenced skills exist                 │    │
│  │ └── Conflicts: Verify no circular dependencies                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  3. ENRICHMENT                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • Generate unique skill_id: custom-{slug}-{uuid[:8]}            │    │
│  │ • Inherit from parent skill if forking                          │    │
│  │ • Set default tool requirements based on category               │    │
│  │ • Compute initial version: "1.0.0"                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  4. PERSISTENCE                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ MongoSkillRepository                                            │    │
│  │ ├── Save skill document                                         │    │
│  │ ├── Create initial version entry                                │    │
│  │ └── Index for owner_id, category, is_public                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  5. PACKAGING (Optional)                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ SkillPackager                                                   │    │
│  │ ├── Generate SKILL.md with YAML frontmatter                     │    │
│  │ ├── Include supporting files (scripts/, templates/)             │    │
│  │ ├── Build file tree for UI                                      │    │
│  │ └── Create downloadable .skill ZIP                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  6. EVENT EMISSION                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • Emit SkillDeliveryEvent via SSE                               │    │
│  │ • Frontend displays SkillDeliveryCard                           │    │
│  │ • User can install/download/view package                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Skill Invocation Pipeline

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       Skill Invocation Pipeline                           │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  TRIGGER PHASE                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Trigger Sources:                                                │    │
│  │ ├── User explicit: /skill-name in chat                          │    │
│  │ ├── User selection: SkillsPopover in UI                         │    │
│  │ ├── AI invocation: skill_invoke tool call                       │    │
│  │ └── Auto-trigger: Message matches trigger_patterns (NEW)        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  RESOLUTION PHASE                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ SkillRegistry.get_skills_for_context()                          │    │
│  │ ├── Fetch requested skills                                      │    │
│  │ ├── Resolve dependencies (topological sort)                     │    │
│  │ ├── Check for conflicts                                         │    │
│  │ └── Verify invocation permissions                               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  EXPANSION PHASE                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ build_skill_content()                                           │    │
│  │ ├── substitute_arguments(): $ARGUMENTS, $1, $2...               │    │
│  │ ├── expand_dynamic_context(): !`command` execution              │    │
│  │ └── merge_inherited_content(): From parent skills               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  INJECTION PHASE                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ ExecutionAgent._setup()                                         │    │
│  │ ├── Append to system_prompt in <enabled_skills> block           │    │
│  │ ├── Filter available tools via allowed_tools                    │    │
│  │ ├── Register handoff tools if handoff_targets defined           │    │
│  │ └── Activate runtime hooks (on_activate)                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│                              ▼                                           │
│  EXECUTION PHASE                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Agent executes with skill context active:                       │    │
│  │ ├── Skill instructions guide behavior                           │    │
│  │ ├── Tool calls restricted to allowed_tools                      │    │
│  │ ├── Handoffs to specialized agents available                    │    │
│  │ └── skill_invoke tool can load additional skills mid-execution  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Trigger Pattern System (NEW)

```python
# Trigger Pattern Implementation
class SkillTriggerMatcher:
    """Match incoming messages against skill trigger patterns."""

    def __init__(self, registry: SkillRegistry):
        self._registry = registry
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}

    async def find_matching_skills(
        self,
        message: str,
        max_matches: int = 3,
    ) -> list[SkillMatch]:
        """Find skills whose trigger patterns match the message.

        Args:
            message: User message to match
            max_matches: Maximum skills to return

        Returns:
            List of matching skills with confidence scores
        """
        matches = []

        for skill_id, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(message)
                if match:
                    skill = await self._registry.get_skill(skill_id)
                    if skill and skill.invocation_type != SkillInvocationType.USER:
                        matches.append(SkillMatch(
                            skill=skill,
                            pattern=pattern.pattern,
                            matched_text=match.group(),
                            confidence=self._compute_confidence(match, message),
                        ))
                        break  # One match per skill

        # Sort by confidence and return top matches
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches[:max_matches]

    def _compute_confidence(self, match: re.Match, message: str) -> float:
        """Compute confidence score for a pattern match."""
        # Higher confidence for longer matches
        match_ratio = len(match.group()) / len(message)
        # Higher confidence for matches at message start
        position_score = 1.0 - (match.start() / len(message))
        return (match_ratio * 0.6) + (position_score * 0.4)

@dataclass
class SkillMatch:
    skill: Skill
    pattern: str
    matched_text: str
    confidence: float
```

---

## 5. Agent Workflow Integration

### 5.1 Dynamic Tool Binding (LangGraph Pattern)

```python
# Enhanced Agent Creation with Dynamic Tool Binding
class SkillAwareAgentFactory:
    """Factory for creating agents with skill-based tool configuration."""

    def __init__(
        self,
        registry: SkillRegistry,
        tool_registry: ToolRegistry,
    ):
        self._skill_registry = registry
        self._tool_registry = tool_registry

    async def create_agent(
        self,
        agent_type: str,
        skill_ids: list[str],
        base_tools: list[str] | None = None,
    ) -> Agent:
        """Create an agent with skill-aware tool binding.

        Implements LangGraph's dynamic tool selection pattern.
        """
        # Get skill context
        context = await self._skill_registry.build_context(skill_ids)

        # Determine available tools
        if context.allowed_tools is not None:
            # Skills restrict available tools
            tool_names = context.allowed_tools
        elif base_tools:
            tool_names = set(base_tools)
        else:
            tool_names = self._tool_registry.get_default_tools(agent_type)

        # Ensure required tools are included
        tool_names = tool_names.union(context.required_tools)

        # Bind tools to model
        tools = [
            self._tool_registry.get_tool(name)
            for name in tool_names
            if self._tool_registry.has_tool(name)
        ]

        # Add handoff tools if configured
        for target in context.handoff_targets:
            tools.append(self._create_handoff_tool(target))

        # Create agent with skill-enhanced prompt
        return self._create_agent_instance(
            agent_type=agent_type,
            tools=tools,
            system_prompt_addition=context.prompt_addition,
        )

    def _create_handoff_tool(self, target: HandoffTarget) -> BaseTool:
        """Create a handoff tool for agent-to-agent transfer."""

        class HandoffTool(BaseTool):
            name = f"transfer_to_{target.agent_type}"
            description = target.description

            async def execute(self, task_description: str, **kwargs):
                return {
                    "action": "handoff",
                    "target_agent": target.agent_type,
                    "task_description": task_description,
                    "context_fields": target.context_fields,
                }

        return HandoffTool()
```

### 5.2 Execution Flow with Skills

```python
# Enhanced ExecutionAgent with Full Skill Integration
class ExecutionAgent:
    """Execution agent with comprehensive skill support."""

    async def _setup(self, message: AgentMessage) -> None:
        """Setup agent with skill context."""

        # 1. Auto-detect skills from message if not specified
        if not message.skills:
            trigger_matcher = SkillTriggerMatcher(self._skill_registry)
            matches = await trigger_matcher.find_matching_skills(
                message.message,
                max_matches=2,
            )
            if matches:
                message.skills = [m.skill.id for m in matches]
                logger.info(f"Auto-detected skills: {message.skills}")

        # 2. Build skill context
        if message.skills:
            context = await self._skill_registry.build_context(
                message.skills,
                arguments=message.skill_arguments or "",
            )

            # Inject prompt
            self.system_prompt = self._base_prompt + context.prompt_addition

            # Apply tool restrictions
            if context.allowed_tools is not None:
                self._available_tools = self._filter_tools(context.allowed_tools)

            # Register handoff tools
            for target in context.handoff_targets:
                self._register_handoff(target)

            # Run activation hooks
            for skill in await self._skill_registry.get_skills_for_context(message.skills):
                if skill.on_activate:
                    await self._run_hook(skill.on_activate)

            logger.info(
                f"Skills activated: {message.skills}, "
                f"tools: {len(self._available_tools)}, "
                f"prompt: +{len(context.prompt_addition)} chars"
            )
```

### 5.3 Skill Context in System Prompt

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        System Prompt Structure                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  CORE_PROMPT (base instructions)                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  <enabled_skills>                                                        │
│  The following skills are enabled for this session.                      │
│  Follow their instructions when relevant to the task:                    │
│                                                                          │
│  ### Research Skill                                                      │
│  You are an expert researcher. When gathering information:               │
│  - Use web_search tool to find current information                       │
│  - Cite sources with [Source: URL]                                       │
│  - Cross-reference multiple sources for accuracy                         │
│  ...                                                                     │
│                                                                          │
│  ### Code Review Skill                                                   │
│  You are a senior code reviewer. When reviewing code:                    │
│  - Check for security vulnerabilities (OWASP Top 10)                     │
│  - Evaluate performance implications                                     │
│  - Suggest improvements with code examples                               │
│  ...                                                                     │
│                                                                          │
│  </enabled_skills>                                                       │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  EXECUTION_SYSTEM_PROMPT (task execution rules)                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  TOOL_CONTEXT (available tools documentation)                            │
│  ─────────────────────────────────────────────────────────────────────  │
│  SANDBOX_CONTEXT (environment information)                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Implementation Roadmap

### Phase 1: Core Enhancements (Priority: High)

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 Skill Registry | Implement centralized registry with caching | 3 days |
| 1.2 Trigger System | Auto-activation via regex patterns | 2 days |
| 1.3 Dynamic Tool Binding | Runtime tool filtering based on allowed_tools | 2 days |
| 1.4 Integration Verification | Ensure skill context flows to all agent types | 1 day |

### Phase 2: Advanced Features (Priority: Medium)

| Task | Description | Effort |
|------|-------------|--------|
| 2.1 Skill Dependencies | Topological resolution of skill deps | 2 days |
| 2.2 Conflict Detection | Prevent incompatible skill combinations | 1 day |
| 2.3 Agent Handoffs | Implement LangGraph Swarm handoff pattern | 3 days |
| 2.4 Skill Versioning | Version history and rollback | 2 days |

### Phase 3: Community & Scale (Priority: Low)

| Task | Description | Effort |
|------|-------------|--------|
| 3.1 Community Discovery | Browse/search public skills | 3 days |
| 3.2 YAML Import/Export | Declarative skill definitions | 2 days |
| 3.3 Skill Analytics | Usage tracking and recommendations | 2 days |
| 3.4 Performance Optimization | Redis caching, batch loading | 2 days |

### Phase 4: Advanced Composition (Priority: Future)

| Task | Description | Effort |
|------|-------------|--------|
| 4.1 Skill Inheritance | Extend existing skills with overrides | 3 days |
| 4.2 Runtime Hooks | on_activate/on_deactivate Python execution | 2 days |
| 4.3 Tool Overrides | Per-skill tool behavior customization | 3 days |
| 4.4 Skill Marketplace | Full marketplace with ratings/reviews | 5 days |

---

## Appendix A: Tool Whitelist

Current allowed tools for custom skills (29 total):

```python
ALLOWED_TOOLS = {
    # Browser tools
    "web_search", "browser_navigate", "browser_click", "browser_type",
    "browser_scroll", "browser_screenshot", "browser_read_page",

    # File tools
    "file_read", "file_write", "file_list", "file_delete", "file_search",

    # Shell tools
    "shell_execute", "shell_background",

    # Code tools
    "code_execute", "code_analyze",

    # Communication tools
    "message_user", "message_ask_user",

    # Data tools
    "data_analyze", "data_visualize",

    # Search tools
    "search_web", "search_academic", "search_news",

    # Export tools
    "export_pdf", "export_markdown",

    # Git tools
    "git_status", "git_commit", "git_diff",
}
```

---

## Appendix B: Security Validation Patterns

Blocked prompt injection patterns (excerpt):

```python
BLOCKED_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|above|prior)",
    r"disregard\s+(all\s+)?(previous|above|prior)",
    r"forget\s+(all\s+)?(previous|above|prior)",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*",
    r"<\|?system\|?>",
    r"\[INST\]",
    r"<\|im_start\|>",
    r"act\s+as\s+(if\s+)?you\s+(are|were)",
    r"pretend\s+(that\s+)?you\s+(are|were)",
    r"you\s+are\s+now\s+a",
    r"roleplay\s+as",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    # ... 15+ more patterns
]
```

---

## Appendix C: Example Skill Definitions

### Research Skill (Official)

```yaml
id: research
name: Research Assistant
description: Expert researcher for comprehensive information gathering
category: research
source: official
invocation_type: both

required_tools:
  - web_search
  - browser_read_page
optional_tools:
  - search_academic
  - search_news

system_prompt_addition: |
  You are an expert researcher with the following capabilities:

  ## Research Process
  1. **Query Formulation**: Break complex questions into searchable queries
  2. **Source Diversity**: Use multiple search engines and sources
  3. **Verification**: Cross-reference facts across 2+ sources
  4. **Citation**: Always cite sources with [Source: URL]

  ## Quality Standards
  - Prefer primary sources over secondary
  - Note publication dates for time-sensitive info
  - Distinguish facts from opinions
  - Acknowledge uncertainty when present

  ## Output Format
  Present findings in structured format:
  - Executive summary (2-3 sentences)
  - Key findings (bullet points)
  - Supporting details (numbered)
  - Sources (linked)
```

### Custom Code Reviewer Skill

```yaml
id: custom-code-reviewer-abc123
name: Security-Focused Code Reviewer
description: Reviews code with emphasis on security vulnerabilities
category: coding
source: custom
owner_id: user-123
invocation_type: user

required_tools:
  - file_read
  - code_analyze
allowed_tools:
  - file_read
  - file_write
  - code_analyze
  - message_user

trigger_patterns:
  - "review.*security"
  - "check.*vulnerabilities"
  - "audit.*code"

system_prompt_addition: |
  You are a security-focused code reviewer. When reviewing code:

  ## Security Checklist
  - [ ] SQL Injection (parameterized queries?)
  - [ ] XSS (output encoding?)
  - [ ] CSRF (token validation?)
  - [ ] Auth bypass (proper checks?)
  - [ ] Sensitive data exposure (encryption?)

  ## Review Format
  ```
  ## Security Review: {filename}

  ### Critical Issues
  [List any critical security vulnerabilities]

  ### Warnings
  [List potential security concerns]

  ### Recommendations
  [List security improvements]
  ```

  Always explain WHY something is a vulnerability, not just what.
```

---

*Document Version: 1.0.0*
*Last Updated: 2026-01-31*
*Authors: Pythinker Team + Claude*
