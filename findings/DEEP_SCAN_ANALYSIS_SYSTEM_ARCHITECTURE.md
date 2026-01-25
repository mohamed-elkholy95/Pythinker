# Pythinker Deep Scan Analysis System Architecture

## Executive Summary

This document outlines the comprehensive architecture for enhancing the Pythinker AI Agent system to achieve Manus-level autonomy with advanced code execution capabilities, Playwright browser automation, credential management, and bot protection bypass features within a secure Ubuntu sandbox environment.

---

## 1. System Overview

### 1.1 Current State Analysis

The existing Pythinker agent system provides a solid foundation with the following components:

| Component | Current State | Enhancement Priority |
|-----------|--------------|---------------------|
| **PlanAct Flow** | Functional with multi-agent dispatch | Medium - Add autonomy levels |
| **Memory Management** | Smart compaction with pressure levels | Low - Optimize for long sessions |
| **Error Handling** | Recovery mechanisms with stuck detection | Medium - Add self-healing |
| **Browser Tool** | Basic CDP-based automation | High - Playwright integration |
| **Shell Tool** | Command execution in sandbox | High - Code executor engine |
| **Multi-Agent Orchestration** | Swarm with handoff protocol | Medium - Enhance coordination |
| **Security** | Basic sandbox isolation | High - Credential management |

### 1.2 Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PYTHINKER DEEP SCAN ANALYSIS SYSTEM                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        AUTONOMOUS AGENT CORE                           │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │ │
│  │  │   PERCEIVE   │─▶│    PLAN      │─▶│   EXECUTE    │─▶│   VERIFY   │ │ │
│  │  │              │  │              │  │              │  │            │ │ │
│  │  │ • Context    │  │ • Strategy   │  │ • Tools      │  │ • Results  │ │ │
│  │  │ • Screen     │  │ • Decompose  │  │ • Code       │  │ • Quality  │ │ │
│  │  │ • Files      │  │ • Prioritize │  │ • Browser    │  │ • Security │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │ │
│  │         ▲                                    │                         │ │
│  │         └────────────── FEEDBACK ◀───────────┘                         │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         ENHANCED TOOL LAYER                            │ │
│  │                                                                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │ │
│  │  │   CODE      │  │ PLAYWRIGHT  │  │ CREDENTIAL  │  │   DEEP      │   │ │
│  │  │  EXECUTOR   │  │  BROWSER    │  │  MANAGER    │  │   SCAN      │   │ │
│  │  │             │  │             │  │             │  │  ANALYZER   │   │ │
│  │  │ • Python    │  │ • Stealth   │  │ • Encrypt   │  │ • AST       │   │ │
│  │  │ • Node.js   │  │ • Anti-bot  │  │ • Inject    │  │ • Security  │   │ │
│  │  │ • Bash      │  │ • Multi-tab │  │ • 2FA       │  │ • Quality   │   │ │
│  │  │ • SQL       │  │ • Recording │  │ • Sessions  │  │ • Metrics   │   │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                      MULTI-AGENT WORKFLOW ENGINE                       │ │
│  │                                                                        │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │ │
│  │  │COORDINATOR│  │RESEARCHER│  │  CODER   │  │ ANALYST  │  │ VERIFIER │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │ │
│  │                                                                        │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    TASK ORCHESTRATOR                             │  │ │
│  │  │  • Parallel Execution  • Dependency Graph  • Checkpoint/Resume  │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     ENHANCED SANDBOX ENVIRONMENT                       │ │
│  │                                                                        │ │
│  │  Ubuntu 22.04 + XFCE4 Desktop + VNC + Playwright + Security Hardening │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Module Specifications

### 2.1 Code Executor Engine

**Purpose:** Execute code in multiple languages with full package ecosystem support.

**File Location:** `backend/app/domain/services/tools/code_executor_tool.py`

```python
class CodeExecutorTool(BaseTool):
    """
    Multi-language code execution engine with:
    - Python with full ecosystem (pandas, numpy, requests, etc.)
    - JavaScript/Node.js execution
    - Bash scripting
    - SQL queries (SQLite, PostgreSQL)
    - Package installation on-demand
    - Execution timeout and resource limits
    """
    
    name = "code_executor"
    
    SUPPORTED_LANGUAGES = {
        "python": {
            "interpreter": "python3",
            "package_manager": "pip3",
            "file_extension": ".py"
        },
        "javascript": {
            "interpreter": "node",
            "package_manager": "npm",
            "file_extension": ".js"
        },
        "bash": {
            "interpreter": "bash",
            "package_manager": None,
            "file_extension": ".sh"
        },
        "sql": {
            "interpreter": "sqlite3",
            "package_manager": None,
            "file_extension": ".sql"
        }
    }
```

**Key Features:**
- Dynamic package installation before execution
- Isolated working directories per execution
- Environment variable injection
- Artifact collection (generated files)
- Execution timeout management
- Memory and CPU limits

### 2.2 Playwright Browser Automation

**Purpose:** Advanced browser automation with stealth capabilities and bot protection bypass.

**File Location:** `backend/app/domain/services/tools/playwright_tool.py`

```python
class PlaywrightTool(BaseTool):
    """
    Advanced browser automation with:
    - Multi-browser support (Chromium, Firefox, WebKit)
    - Stealth mode for bot detection bypass
    - Network interception and modification
    - Cookie and session management
    - Screenshot and video recording
    - Form automation with credential injection
    """
    
    name = "playwright_browser"
    
    STEALTH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-web-security",
        "--no-sandbox",
        "--disable-dev-shm-usage"
    ]
```

**Bot Protection Strategies:**
1. **Cloudflare Bypass:** Wait for challenge resolution, verify bypass
2. **reCAPTCHA Handling:** Service integration or user intervention
3. **hCaptcha Handling:** Similar to reCAPTCHA approach
4. **Fingerprint Evasion:** Realistic user agent, viewport, timezone

### 2.3 Deep Scan Code Analyzer

**Purpose:** Comprehensive code analysis for security, quality, and metrics.

**File Location:** `backend/app/domain/services/tools/deep_scan_analyzer.py`

```python
class DeepScanAnalyzer(BaseTool):
    """
    Comprehensive code analysis engine with:
    - AST-based code parsing
    - Security vulnerability detection
    - Code quality metrics
    - Dependency analysis
    - Complexity scoring
    - Pattern detection
    """
    
    name = "deep_scan"
    
    ANALYSIS_TYPES = {
        "security": SecurityAnalyzer,
        "quality": QualityAnalyzer,
        "complexity": ComplexityAnalyzer,
        "dependencies": DependencyAnalyzer,
        "patterns": PatternAnalyzer
    }
```

**Analysis Capabilities:**
- **Security Scan:** SQL injection, XSS, hardcoded secrets, insecure functions
- **Quality Metrics:** Cyclomatic complexity, maintainability index, code duplication
- **Dependency Analysis:** Outdated packages, vulnerability CVEs, license compliance
- **Pattern Detection:** Anti-patterns, code smells, best practice violations

### 2.4 Credential Manager

**Purpose:** Secure credential storage, encryption, and injection.

**File Location:** `backend/app/domain/services/tools/credential_manager.py`

```python
class CredentialManager:
    """
    Secure credential management with:
    - AES-256 encryption at rest
    - Scoped access control
    - Automatic form filling
    - 2FA/TOTP support
    - Session persistence
    - Audit logging
    """
    
    CREDENTIAL_TYPES = {
        "login": ["username", "password"],
        "api_key": ["key", "secret"],
        "oauth": ["client_id", "client_secret", "refresh_token"],
        "2fa": ["secret", "backup_codes"]
    }
```

---

## 3. Multi-Agent Workflow Architecture

### 3.1 Agent Types and Capabilities

| Agent Type | Primary Capability | Tools Access | Autonomy Level |
|------------|-------------------|--------------|----------------|
| **Coordinator** | Task decomposition, delegation | All | High |
| **Researcher** | Information gathering | Search, Browser | Medium |
| **Coder** | Code writing, debugging | Code Executor, File | High |
| **Analyst** | Data analysis, visualization | Code Executor, File | Medium |
| **Browser** | Web automation | Playwright, Browser | Medium |
| **Verifier** | Output validation | All (read-only) | Low |
| **Security** | Vulnerability scanning | Deep Scan, File | Medium |

### 3.2 Task Orchestration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    TASK ORCHESTRATION FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Request                                                    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────┐                                                │
│  │ COORDINATOR │ ──────────────────────────────────────────┐    │
│  └─────────────┘                                            │    │
│       │                                                     │    │
│       │ Decompose into subtasks                            │    │
│       ▼                                                     │    │
│  ┌─────────────────────────────────────────────────────┐   │    │
│  │              DEPENDENCY GRAPH                        │   │    │
│  │                                                      │   │    │
│  │   Task A ──┬──▶ Task C ──┬──▶ Task E               │   │    │
│  │            │             │                          │   │    │
│  │   Task B ──┘             └──▶ Task F               │   │    │
│  │                                                      │   │    │
│  └─────────────────────────────────────────────────────┘   │    │
│       │                                                     │    │
│       │ Parallel execution where possible                  │    │
│       ▼                                                     │    │
│  ┌─────────────────────────────────────────────────────┐   │    │
│  │              SPECIALIZED AGENTS                      │   │    │
│  │                                                      │   │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │    │
│  │  │RESEARCHER│  │  CODER   │  │ ANALYST  │          │   │    │
│  │  └──────────┘  └──────────┘  └──────────┘          │   │    │
│  │       │             │             │                 │   │    │
│  │       └─────────────┴─────────────┘                 │   │    │
│  │                     │                               │   │    │
│  └─────────────────────┼───────────────────────────────┘   │    │
│                        │                                    │    │
│                        ▼                                    │    │
│                  ┌──────────┐                               │    │
│                  │ VERIFIER │ ◀─────────────────────────────┘    │
│                  └──────────┘                                    │
│                        │                                         │
│                        ▼                                         │
│                  Final Result                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Handoff Protocol Enhancement

```python
class EnhancedHandoffProtocol:
    """
    Enhanced handoff protocol with:
    - Context preservation across agents
    - Progress tracking and checkpointing
    - Rollback capability on failure
    - Resource sharing between agents
    """
    
    async def handoff(
        self,
        source_agent: AgentType,
        target_agent: AgentType,
        context: HandoffContext,
        checkpoint: Optional[Checkpoint] = None
    ) -> HandoffResult:
        # Save checkpoint before handoff
        if checkpoint:
            await self.save_checkpoint(checkpoint)
        
        # Transfer context to target agent
        target = await self.get_agent(target_agent)
        result = await target.execute(context)
        
        # Verify result quality
        if not result.success:
            # Attempt recovery or rollback
            return await self.handle_failure(result, checkpoint)
        
        return result
```

---

## 4. Enhanced Sandbox Environment

### 4.1 Enhanced Dockerfile

```dockerfile
# Enhanced Sandbox Dockerfile
FROM ubuntu:22.04

# System dependencies
RUN apt-get update && apt-get install -y \
    # Desktop environment
    xfce4 xfce4-goodies \
    # VNC and display
    tigervnc-standalone-server novnc websockify \
    # Development tools
    build-essential git curl wget \
    python3 python3-pip python3-venv \
    nodejs npm \
    # Browser dependencies for Playwright
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    # Network tools
    net-tools iputils-ping dnsutils \
    # Security tools
    fail2ban ufw \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright with all browsers
RUN pip3 install playwright && \
    playwright install --with-deps chromium firefox webkit

# Install stealth packages
RUN pip3 install \
    playwright-stealth \
    undetected-chromedriver \
    selenium-stealth

# Security hardening
RUN useradd -m -s /bin/bash sandbox && \
    echo "sandbox ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/sandbox

# Resource limits
ENV SANDBOX_CPU_LIMIT=2
ENV SANDBOX_MEMORY_LIMIT=4G
ENV SANDBOX_DISK_LIMIT=10G
```

### 4.2 Security Configuration

```yaml
# Security configuration for sandbox
security:
  network:
    # Restrict outbound connections
    allowed_domains:
      - "*.github.com"
      - "*.npmjs.org"
      - "*.pypi.org"
    blocked_ports:
      - 22  # SSH
      - 23  # Telnet
  
  filesystem:
    # Restrict filesystem access
    read_only_paths:
      - /etc
      - /usr
    writable_paths:
      - /home/sandbox
      - /workspace
      - /tmp
  
  execution:
    # Execution limits
    max_process_time: 3600  # 1 hour
    max_memory_mb: 4096
    max_cpu_percent: 200  # 2 cores
```

---

## 5. Autonomy Configuration System

### 5.1 Autonomy Levels

```python
class AutonomyLevel(Enum):
    SUPERVISED = 1      # Confirm every action
    GUIDED = 2          # Confirm critical actions only
    AUTONOMOUS = 3      # Full autonomy with logging
    UNRESTRICTED = 4    # No restrictions (advanced users)

class AutonomyConfig:
    """Configuration for agent autonomy behavior"""
    
    level: AutonomyLevel = AutonomyLevel.AUTONOMOUS
    max_iterations: int = 50
    max_tool_calls: int = 100
    
    # Permission flags
    allow_credential_access: bool = True
    allow_external_requests: bool = True
    allow_file_system_write: bool = True
    allow_code_execution: bool = True
    allow_browser_takeover: bool = True
    
    # Safety limits
    max_file_size_mb: int = 100
    max_download_size_mb: int = 500
    max_execution_time_seconds: int = 3600
    
    # Actions requiring confirmation at each level
    CONFIRMATION_REQUIRED = {
        AutonomyLevel.SUPERVISED: ["all"],
        AutonomyLevel.GUIDED: [
            "credential_access",
            "external_payment",
            "file_delete",
            "system_modification"
        ],
        AutonomyLevel.AUTONOMOUS: [
            "external_payment",
            "irreversible_action"
        ],
        AutonomyLevel.UNRESTRICTED: []
    }
```

### 5.2 Self-Healing Agent Loop

```python
class SelfHealingAgentLoop:
    """
    Enhanced agent loop with automatic error recovery
    and strategy adaptation.
    """
    
    async def run(self, task: str) -> AgentResult:
        plan = await self.create_plan(task)
        recovery_attempts = 0
        max_recovery_attempts = 3
        
        while not self.is_complete(plan):
            step = self.get_next_step(plan)
            
            try:
                result = await self.execute_step(step)
                await self.update_plan(plan, result)
                recovery_attempts = 0  # Reset on success
                
            except RecoverableError as e:
                recovery_attempts += 1
                
                if recovery_attempts <= max_recovery_attempts:
                    # Attempt automatic recovery
                    recovery = await self.attempt_recovery(e, step)
                    
                    if recovery.success:
                        continue
                    
                    # Try alternative approach
                    alternative = await self.find_alternative(step, e)
                    if alternative:
                        plan = await self.replan_with_alternative(
                            plan, step, alternative
                        )
                        continue
                
                # Escalate to user after max attempts
                await self.escalate_to_user(e, step)
                break
                
            except CriticalError as e:
                # Immediate escalation for critical errors
                await self.escalate_to_user(e, step)
                break
            
            # Periodic self-reflection
            if self.should_reflect():
                await self.reflect_and_adjust(plan)
        
        return self.compile_results(plan)
```

---

## 6. API Specifications

### 6.1 Code Executor API

```python
@tool(
    name="code_execute",
    description="Execute code in isolated sandbox environment",
    parameters={
        "language": {
            "type": "string",
            "enum": ["python", "javascript", "bash", "sql"],
            "description": "Programming language"
        },
        "code": {
            "type": "string",
            "description": "Code to execute"
        },
        "timeout": {
            "type": "integer",
            "default": 300,
            "description": "Execution timeout in seconds"
        },
        "working_dir": {
            "type": "string",
            "default": "/workspace",
            "description": "Working directory"
        },
        "packages": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Packages to install before execution"
        },
        "env_vars": {
            "type": "object",
            "description": "Environment variables"
        }
    },
    required=["language", "code"]
)
async def code_execute(self, **params) -> ToolResult:
    pass
```

### 6.2 Playwright Browser API

```python
@tool(
    name="playwright_action",
    description="Execute Playwright browser automation action",
    parameters={
        "action": {
            "type": "string",
            "enum": [
                "launch", "goto", "click", "fill", "type",
                "screenshot", "pdf", "evaluate", "wait_for",
                "get_content", "set_cookies", "get_cookies",
                "intercept_request", "handle_dialog",
                "upload_file", "download", "close",
                "stealth_mode", "solve_captcha"
            ],
            "description": "Browser action to perform"
        },
        "params": {
            "type": "object",
            "description": "Action-specific parameters"
        }
    },
    required=["action"]
)
async def playwright_action(self, **params) -> ToolResult:
    pass
```

### 6.3 Deep Scan API

```python
@tool(
    name="deep_scan",
    description="Perform deep code analysis",
    parameters={
        "target": {
            "type": "string",
            "description": "File or directory path to analyze"
        },
        "scan_types": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["security", "quality", "complexity", "dependencies", "patterns"]
            },
            "description": "Types of analysis to perform"
        },
        "options": {
            "type": "object",
            "description": "Scan-specific options"
        }
    },
    required=["target"]
)
async def deep_scan(self, **params) -> ToolResult:
    pass
```

---

## 7. Integration Points

### 7.1 Existing System Integration

| Component | Integration Method | Data Flow |
|-----------|-------------------|-----------|
| PlanAct Flow | Direct import | Bidirectional |
| Memory Manager | Service injection | Read/Write |
| Error Handler | Event subscription | Write |
| Agent Repository | Repository pattern | Read/Write |
| Session Repository | Repository pattern | Read/Write |

### 7.2 External Service Integration

| Service | Purpose | Authentication |
|---------|---------|----------------|
| OpenAI API | LLM inference | API Key |
| Qdrant | Vector storage | API Key |
| MongoDB | Session storage | Connection string |
| Redis | Cache layer | Connection string |
| SearXNG | Web search | Local instance |

---

## 8. Testing Strategy

### 8.1 Unit Tests

```python
# tests/test_code_executor.py
class TestCodeExecutor:
    async def test_python_execution(self):
        executor = CodeExecutorTool(sandbox)
        result = await executor.execute({
            "language": "python",
            "code": "print('Hello, World!')"
        })
        assert result.success
        assert "Hello, World!" in result.output

    async def test_package_installation(self):
        executor = CodeExecutorTool(sandbox)
        result = await executor.execute({
            "language": "python",
            "code": "import pandas; print(pandas.__version__)",
            "packages": ["pandas"]
        })
        assert result.success
```

### 8.2 Integration Tests

```python
# tests/test_playwright_integration.py
class TestPlaywrightIntegration:
    async def test_stealth_navigation(self):
        browser = PlaywrightTool()
        result = await browser.execute({
            "action": "launch",
            "params": {"stealth": True}
        })
        assert result.success
        
        result = await browser.execute({
            "action": "goto",
            "params": {"url": "https://bot.sannysoft.com/"}
        })
        assert result.success
        # Verify no bot detection flags
```

### 8.3 Security Tests

```python
# tests/test_security.py
class TestSecurityFeatures:
    async def test_credential_encryption(self):
        manager = CredentialManager(encryption_key)
        await manager.store_credential(
            name="test",
            credential_type="login",
            data={"username": "test", "password": "secret"}
        )
        # Verify encryption at rest
        raw_data = await manager._get_raw_storage("test")
        assert "secret" not in raw_data
```

---

## 9. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      DOCKER COMPOSE                          ││
│  │                                                              ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    ││
│  │  │ Frontend │  │ Backend  │  │ Sandbox  │  │ Database │    ││
│  │  │  (Vue)   │  │(FastAPI) │  │ (Ubuntu) │  │(MongoDB) │    ││
│  │  │  :5173   │  │  :8000   │  │  :8080   │  │  :27017  │    ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    ││
│  │                                                              ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                   ││
│  │  │  Redis   │  │  Qdrant  │  │ SearXNG  │                   ││
│  │  │  :6379   │  │  :6333   │  │  :8888   │                   ││
│  │  └──────────┘  └──────────┘  └──────────┘                   ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Network: pythinker-network (bridge)                            │
│  Volumes: mongodb_data, qdrant_data, sandbox_workspace          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Task Completion Rate | >90% | Automated testing |
| Error Recovery Rate | >80% | Error handler logs |
| Bot Detection Bypass | >95% | Test suite against detection sites |
| Code Execution Success | >99% | Execution logs |
| Security Scan Coverage | 100% | OWASP checklist |
| Response Time (P95) | <5s | Performance monitoring |

---

*Document Version: 1.0.0*
*Last Updated: January 2026*
*Author: Pythinker Enhancement Team*
