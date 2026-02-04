# Tool Visualization Map - Complete Reference

> **Purpose**: Standardize how all agent tool calls are visualized in the main VNC preview and mini VNC preview cards, so users can see everything the agent does.

---

## Table of Contents

1. [Tool Inventory](#1-tool-inventory)
2. [Tool-to-Preview Mapping](#2-tool-to-preview-mapping)
3. [Event Flow Architecture](#3-event-flow-architecture)
4. [Preview Component Specifications](#4-preview-component-specifications)
5. [Standardization Guidelines](#5-standardization-guidelines)
6. [Implementation Checklist](#6-implementation-checklist)

---

## 1. Tool Inventory

### Complete Tool List (25 Tools)

| Tool Class | File | Functions | Preview Type |
|------------|------|-----------|--------------|
| **ShellTool** | `domain/services/tools/shell.py` | `shell_exec`, `shell_view`, `shell_wait`, `shell_write_to_process`, `shell_kill_process` | Terminal |
| **FileTool** | `domain/services/tools/file.py` | `file_read`, `file_write`, `file_str_replace`, `file_find_in_content`, `file_find_by_name`, `file_view` | Editor |
| **BrowserTool** | `domain/services/tools/browser.py` | `browser_navigate`, `browser_view`, `browser_get_content`, `browser_click`, `browser_input`, `browser_scroll`, `browser_wait`, `browser_back`, `browser_forward` | VNC (Browser) |
| **PlaywrightTool** | `domain/services/tools/playwright_tool.py` | `playwright_navigate`, `playwright_click`, `playwright_fill`, `playwright_select`, `playwright_screenshot`, `playwright_pdf`, `playwright_get_content`, `playwright_wait_for`, `playwright_get_cookies`, `playwright_set_cookies` | VNC (Browser) |
| **BrowserAgentTool** | `domain/services/tools/browser_agent.py` | `browser_agent_extract` | VNC (Browser) |
| **SearchTool** | `domain/services/tools/search.py` | `info_search_web` | Search Results |
| **CodeExecutorTool** | `domain/services/tools/code_executor.py` | `code_execute`, `code_run_file`, `code_install_packages`, `code_list_artifacts`, `code_read_artifact` | Terminal + Output |
| **GitTool** | `domain/services/tools/git.py` | `git_clone`, `git_status`, `git_diff`, `git_log`, `git_branches` | Terminal |
| **MCPTool** | `domain/services/tools/mcp.py` | `mcp_call_tool`, `mcp_list_resources`, `mcp_read_resource`, `mcp_server_status` | Generic/MCP |
| **MessageTool** | `domain/services/tools/message.py` | `message_notify_user`, `message_ask_user` | Message Card |
| **IdleTool** | `domain/services/tools/idle.py` | `idle` | Idle State |
| **CodeDevTool** | `domain/services/tools/code_dev.py` | Various dev utilities | Editor |
| **SkillInvokeTool** | `domain/services/tools/skill_invoke.py` | `skill_invoke` | Skill Card |
| **SkillCreatorTool** | `domain/services/tools/skill_creator.py` | `skill_create` | Skill Card |
| **SkillListTool** | `domain/services/tools/skill_list.py` | `skill_list` | Generic |
| **ExportTool** | `domain/services/tools/export.py` | Export functions | Generic |
| **SlidesTool** | `domain/services/tools/slides.py` | Presentation functions | Generic |
| **TestRunnerTool** | `domain/services/tools/test_runner.py` | Test execution | Terminal |
| **WorkspaceTool** | `domain/services/tools/workspace.py` | Workspace management | Generic |
| **ScheduleTool** | `domain/services/tools/schedule.py` | Scheduling | Generic |
| **DeepScanAnalyzerTool** | `domain/services/tools/deep_scan_analyzer.py` | Deep analysis | Generic |
| **AgentModeTool** | `domain/services/tools/agent_mode.py` | Mode switching | Generic |

---

## 2. Tool-to-Preview Mapping

### Preview Type Categories

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           MAIN VNC PREVIEW                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  CDP Screencast Stream (1280x1024 @ 15fps, JPEG quality 70)         │   │
│  │  - Shows real-time sandbox desktop                                   │   │
│  │  - Interactive mode for user takeover                                │   │
│  │  - Canvas rendering with OpenReplay capture                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                        MINI VNC PREVIEW CARDS                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│  │ VNC     │  │Terminal │  │ Search  │  │ Editor  │  │ Generic │          │
│  │ View    │  │ View    │  │ View    │  │ View    │  │ View    │          │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘          │
└────────────────────────────────────────────────────────────────────────────┘
```

### Tool → Preview Type Mapping Table

| Tool Name | Function | Preview Type | Visual Content |
|-----------|----------|--------------|----------------|
| `shell` | `shell_exec` | **Terminal** | Command + output in green terminal style |
| `shell` | `shell_view` | **Terminal** | Current shell session state |
| `shell` | `shell_wait` | **Terminal** | Waiting indicator with spinner |
| `shell` | `shell_write_to_process` | **Terminal** | Input being sent |
| `shell` | `shell_kill_process` | **Terminal** | Process termination |
| `file` | `file_read` | **Editor** | File content with syntax highlighting |
| `file` | `file_write` | **Editor** | File being written + diff preview |
| `file` | `file_str_replace` | **Editor** | Before/after diff |
| `file` | `file_find_in_content` | **Editor** | Search results with line numbers |
| `file` | `file_find_by_name` | **Editor** | File tree results |
| `file` | `file_view` | **Editor** | Image/PDF thumbnail |
| `browser` | `browser_navigate` | **VNC** | Live browser view |
| `browser` | `browser_view` | **VNC** | Current page screenshot |
| `browser` | `browser_get_content` | **Content Fetched** | Green checkmark + URL |
| `browser` | `browser_click` | **VNC** | Click animation overlay |
| `browser` | `browser_input` | **VNC** | Typing indicator |
| `browser` | `browser_scroll` | **VNC** | Scroll direction indicator |
| `browser` | `browser_wait` | **VNC** | Loading spinner |
| `playwright` | All functions | **VNC** | Browser automation view |
| `browser_agent` | `browser_agent_extract` | **VNC** | AI browser with step counter |
| `search` | `info_search_web` | **Search** | Top 3 results with favicons |
| `code_executor` | `code_execute` | **Terminal** | Code + output |
| `code_executor` | `code_run_file` | **Terminal** | File execution output |
| `git` | All functions | **Terminal** | Git command output |
| `mcp` | All functions | **Generic** | MCP tool icon + result |
| `message` | `message_notify_user` | **Message** | Notification card |
| `message` | `message_ask_user` | **Message** | Question with input field |
| `idle` | `idle` | **Idle** | Idle state indicator |
| `skill_*` | All functions | **Skill** | Skill card with icon |

---

## 3. Event Flow Architecture

### SSE Event → Preview Update Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND                                         │
│                                                                              │
│  ┌────────────┐    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Tool Call  │───▶│ ToolEvent   │───▶│ EventMapper  │───▶│ SSE Stream   │  │
│  │ Execution  │    │ (CALLING)   │    │ to_sse()     │    │ /chat        │  │
│  └────────────┘    └─────────────┘    └──────────────┘    └──────┬───────┘  │
│        │                                                          │          │
│        ▼                                                          │          │
│  ┌────────────┐    ┌─────────────┐                                │          │
│  │ Tool       │───▶│ ToolEvent   │────────────────────────────────┤          │
│  │ Completes  │    │ (CALLED)    │                                │          │
│  └────────────┘    └─────────────┘                                │          │
│                                                                   │          │
└───────────────────────────────────────────────────────────────────┼──────────┘
                                                                    │
                                    ┌───────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                        │
│                                                                              │
│  ┌────────────┐    ┌─────────────────┐    ┌────────────────────────────────┐│
│  │ SSE        │───▶│ useAgentEvents  │───▶│ Component Updates              ││
│  │ Listener   │    │ composable      │    │ ┌─────────────────────────────┐││
│  └────────────┘    └─────────────────┘    │ │ SandboxViewer (Main VNC)    │││
│                                            │ └─────────────────────────────┘││
│                                            │ ┌─────────────────────────────┐││
│                                            │ │ VncMiniPreview (Cards)      │││
│                                            │ └─────────────────────────────┘││
│                                            │ ┌─────────────────────────────┐││
│                                            │ │ ToolPanel (Tool Timeline)   │││
│                                            │ └─────────────────────────────┘││
│                                            └────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Event Types for Visualization

| Event Type | SSE Event | Preview Update |
|------------|-----------|----------------|
| `tool` (CALLING) | `ToolEventData` | Start loading state, show tool icon |
| `tool` (CALLED) | `ToolEventData` | Update with result, show content |
| `tool_progress` | `ToolProgressEventData` | Update progress bar, step indicator |
| `step` | `StepEventData` | Update step status in timeline |
| `plan` | `PlanEventData` | Show plan steps overview |
| `stream` | `StreamEventData` | Real-time text streaming |
| `deep_research` | `DeepResearchEventData` | Research progress overlay |
| `wide_research` | `WideResearchEventData` | Multi-source search progress |

---

## 4. Preview Component Specifications

### 4.1 Main VNC Preview (SandboxViewer)

**Component**: `frontend/src/components/SandboxViewer.vue`

```typescript
interface SandboxViewerProps {
  sessionId: string;
  interactive?: boolean;  // Enable user input
  showStats?: boolean;    // Show FPS/bandwidth
}

// CDP Screencast Configuration
const SCREENCAST_CONFIG = {
  quality: 70,           // JPEG quality (1-100)
  maxFps: 15,            // Maximum frames per second
  width: 1280,           // Viewport width
  height: 1024,          // Viewport height
};
```

**Features**:
- Real-time CDP screencast (WebSocket binary stream)
- Interactive mode with input forwarding
- OpenReplay canvas capture (`data-openreplay-canvas="true"`)
- Auto-reconnect with exponential backoff
- Performance stats overlay (FPS, bandwidth, frame count)

### 4.2 Mini VNC Preview Cards (VncMiniPreview)

**Component**: `frontend/src/components/VncMiniPreview.vue`

```typescript
interface MiniPreviewProps {
  toolEvent: ToolEventData;
  size?: 'sm' | 'md' | 'lg';  // Card size
}

// Size configurations
const SIZES = {
  sm: { width: 120, height: 90 },
  md: { width: 144, height: 108 },  // Default
  lg: { width: 192, height: 144 },
};
```

**View Types** (determined by `useContentConfig`):

| View Type | Trigger Conditions | Visual |
|-----------|-------------------|--------|
| **VNC** | `browser`, `browser_agent`, `playwright` tools | Live mini screencast |
| **Terminal** | `shell`, `code_executor`, `git` tools | Green terminal output |
| **Search** | `search`, `info_search_web` function | Top 3 results + favicons |
| **Editor** | `file` tools | File content + filename header |
| **Generic** | `mcp`, unknown tools | Tool icon + truncated result |
| **Initialization** | Tool starting | Animated boot sequence |
| **Content Fetched** | `browser_get_content` complete | Green checkmark + URL |
| **Wide Research** | `wide_research` event | Progress ring + sources |

### 4.3 Tool Timeline Panel

**Component**: `frontend/src/components/ToolPanel.vue`

```typescript
interface ToolPanelProps {
  events: ToolEventData[];
  onSelectTool?: (toolCallId: string) => void;
}
```

**Features**:
- Chronological list of tool calls
- Status badges (calling → called)
- Duration display
- Expandable details
- Click to focus main preview

---

## 5. Standardization Guidelines

### 5.1 Tool Event Data Structure

Every tool call MUST emit standardized `ToolEvent`:

```typescript
interface ToolEventData {
  // Identity
  event_id: string;           // Unique event ID
  tool_call_id: string;       // Links calling/called events
  timestamp: number;          // Unix timestamp

  // Tool info
  name: string;               // Tool class name (e.g., "browser")
  function: string;           // Function name (e.g., "browser_navigate")
  args: Record<string, any>;  // Function arguments

  // Status
  status: 'calling' | 'called';
  runtime_status?: 'success' | 'error' | 'timeout';

  // Results (when status = 'called')
  content?: ToolContent;      // Typed content for preview
  stdout?: string;            // Standard output
  stderr?: string;            // Standard error
  exit_code?: number;         // Exit code

  // Display
  display_command: string;    // Human-readable command
  command_category: string;   // Category for icon selection
  command_summary: string;    // Short summary for badges

  // Timing
  started_at?: string;        // ISO timestamp
  completed_at?: string;      // ISO timestamp
  duration_ms?: number;       // Execution duration

  // Security
  security_risk?: 'low' | 'medium' | 'high';
  security_reason?: string;
  confirmation_state?: 'pending' | 'confirmed' | 'denied';
}
```

### 5.2 Tool Content Types

```typescript
// Search results
interface SearchToolContent {
  results: Array<{
    title: string;
    url: string;
    snippet: string;
    favicon?: string;
  }>;
}

// Browser content
interface BrowserToolContent {
  content?: string;       // Page text
  screenshot?: string;    // Base64 image
  url?: string;           // Current URL
  title?: string;         // Page title
}

// File content
interface FileToolContent {
  content: string;        // File text
  filename: string;       // File path
  language?: string;      // For syntax highlighting
  diff?: string;          // Diff for write/replace
}

// Shell content
interface ShellToolContent {
  command: string;        // Executed command
  output: string;         // Combined stdout/stderr
  exit_code: number;      // Exit code
  cwd?: string;           // Working directory
}

// MCP content
interface McpToolContent {
  server_name: string;
  tool_name: string;
  result: any;
}

// Browser agent content
interface BrowserAgentToolContent {
  result: any;
  steps_taken: number;
  final_url?: string;
}
```

### 5.3 Preview Selection Logic

```typescript
// useContentConfig.ts
function getPreviewType(event: ToolEventData): PreviewType {
  const { name, function: fn, status } = event;

  // VNC view for browser tools
  if (['browser', 'browser_agent', 'playwright'].includes(name)) {
    if (fn === 'browser_get_content' && status === 'called') {
      return 'content-fetched';
    }
    return 'vnc';
  }

  // Terminal view for shell/code/git
  if (['shell', 'code_executor', 'git', 'test_runner'].includes(name)) {
    return 'terminal';
  }

  // Search view for search tools
  if (name === 'search' || fn === 'info_search_web') {
    return 'search';
  }

  // Editor view for file tools
  if (name === 'file' || name === 'code_dev') {
    return 'editor';
  }

  // Skill view for skill tools
  if (name.startsWith('skill_')) {
    return 'skill';
  }

  // Message view for message tools
  if (name === 'message') {
    return 'message';
  }

  // Wide research overlay
  if (event.wide_research) {
    return 'wide-research';
  }

  // Default generic view
  return 'generic';
}
```

### 5.4 Command Category Icons

```typescript
const CATEGORY_ICONS: Record<string, string> = {
  'browse': 'Globe',           // Browser tools
  'search': 'Search',          // Search tools
  'file': 'FileText',          // File tools
  'shell': 'Terminal',         // Shell tools
  'code': 'Code',              // Code executor
  'git': 'GitBranch',          // Git tools
  'mcp': 'Puzzle',             // MCP tools
  'message': 'MessageCircle',  // Message tools
  'skill': 'Wand',             // Skill tools
  'other': 'Box',              // Generic
};
```

---

## 6. Implementation Checklist

### 6.1 Backend Requirements

- [ ] **All tools emit ToolEvent with CALLING status** before execution
- [ ] **All tools emit ToolEvent with CALLED status** after completion
- [ ] **ToolContent is correctly typed** per tool category
- [ ] **display_command is human-readable** (e.g., "Searching 'machine learning'")
- [ ] **command_category is set** for icon selection
- [ ] **duration_ms is calculated** from started_at to completed_at
- [ ] **ToolProgressEvent emitted** for long-running operations (>2s)

### 6.2 Frontend Requirements

- [ ] **SandboxViewer shows main VNC** for all browser tools
- [ ] **VncMiniPreview switches view type** based on useContentConfig
- [ ] **All tool events appear in timeline** with correct icons
- [ ] **Click on mini preview** expands to main view
- [ ] **Progress indicators shown** during CALLING status
- [ ] **Results shown** when CALLED status received
- [ ] **Error states handled** with retry option

### 6.3 New Tool Onboarding

When adding a new tool:

1. **Define tool content type** in `ToolContent` union
2. **Add to preview type mapping** in `useContentConfig.ts`
3. **Add icon mapping** in `CATEGORY_ICONS`
4. **Create mini preview variant** if needed
5. **Test event emission** (CALLING → progress → CALLED)
6. **Verify display_command** is descriptive
7. **Document in this map**

---

## Appendix A: Event Type Reference

### SSE Events for Visualization

| Event | Purpose | Preview Impact |
|-------|---------|----------------|
| `tool` | Tool call start/complete | Primary preview update |
| `tool_progress` | Long-running progress | Progress bar update |
| `step` | Plan step status | Timeline step highlight |
| `plan` | Plan created/updated | Show plan overview |
| `stream` | LLM token stream | Message streaming |
| `message` | Complete message | Final message display |
| `deep_research` | Research progress | Research overlay |
| `wide_research` | Multi-search progress | Sources progress ring |
| `report` | Report generation | Report preview |
| `thought` | Chain-of-thought | Reasoning display |

### WebSocket Streams

| Stream | Purpose | Endpoint |
|--------|---------|----------|
| CDP Screencast | Live browser frames | `ws://{sandbox}:8080/api/v1/screencast/stream` |
| VNC (fallback) | RFB protocol stream | `ws://{backend}/sessions/{id}/vnc` |
| Input Forward | User input to sandbox | `ws://{sandbox}:8080/api/v1/input/stream` |

---

## Appendix B: File Reference

| Purpose | Path |
|---------|------|
| Tool definitions | `backend/app/domain/services/tools/*.py` |
| Event models | `backend/app/domain/models/event.py` |
| SSE mapper | `backend/app/interfaces/schemas/event.py` |
| Main VNC viewer | `frontend/src/components/SandboxViewer.vue` |
| Mini previews | `frontend/src/components/VncMiniPreview.vue` |
| VNC client | `frontend/src/components/VNCViewer.vue` |
| Content config | `frontend/src/composables/useContentConfig.ts` |
| Agent events | `frontend/src/composables/useAgentEvents.ts` |
| Event types | `frontend/src/types/event.ts` |

---

---

## Appendix C: Implementation Status ✅

### All Tools Now Have Dedicated Preview Views

| Tool | View Type | Status |
|------|-----------|--------|
| `git` | Git (branch badge, diff output) | ✅ Implemented |
| `code_dev` | Editor | ✅ Implemented |
| `test_runner` | Test (pass/fail badges) | ✅ Implemented |
| `export` | Export (filename, format) | ✅ Implemented |
| `slides` | Slides (title, count) | ✅ Implemented |
| `workspace` | Workspace (file tree) | ✅ Implemented |
| `schedule` | Schedule (time display) | ✅ Implemented |
| `deep_scan_analyzer` | Scan (findings count) | ✅ Implemented |
| `agent_mode` | Generic | ✅ Implemented |
| `playwright` | VNC | ✅ Implemented |
| `skill_invoke` | Skill card | ✅ Implemented |
| `skill_creator` | Skill card | ✅ Implemented |
| `plan` | Generic | ✅ Implemented |
| `repo_map` | Workspace | ✅ Implemented |
| `mcp` | Generic | ✅ Implemented |
| `message` | Generic | ✅ Implemented |

### Backend Tool Content Types Added

All tool content types now defined in `backend/app/domain/models/event.py`:
- ✅ `GitToolContent` - operation, branch, commits, diff
- ✅ `CodeExecutorToolContent` - language, code, output, artifacts
- ✅ `PlaywrightToolContent` - browser_type, url, screenshot
- ✅ `TestRunnerToolContent` - total, passed, failed, skipped
- ✅ `SkillToolContent` - skill_id, name, operation, status
- ✅ `ExportToolContent` - format, filename, size
- ✅ `SlidesToToolContent` - title, slide_count, format
- ✅ `WorkspaceToolContent` - action, workspace_type, files
- ✅ `ScheduleToolContent` - action, schedule_id, time
- ✅ `DeepScanToolContent` - scan_type, findings_count, details
- ✅ `AgentModeToolContent` - mode, previous_mode, reason
- ✅ `CodeDevToolContent` - operation, file_path, suggestions
- ✅ `PlanToolContent` - operation, plan_id, steps_count
- ✅ `RepoMapToolContent` - repo_path, files_count, structure

### Frontend Tool Configurations Added

All tools configured in `frontend/src/constants/tool.ts`:
- ✅ All 70+ functions mapped in `TOOL_FUNCTION_MAP`
- ✅ All parameter mappings in `TOOL_FUNCTION_ARG_MAP`
- ✅ All tool names in `TOOL_NAME_MAP`
- ✅ All tool icons in `TOOL_ICON_MAP`
- ✅ All content configs in `TOOL_CONTENT_CONFIG`

### Mini Preview Views Implemented

New view types in `VncMiniPreview.vue`:
- ✅ **Git view**: Branch badge, colored accent, diff output
- ✅ **Test view**: Pass/fail/skip badges with icons
- ✅ **Skill view**: Skill name, status indicator
- ✅ **Export view**: Filename, format badge
- ✅ **Slides view**: Title, slide count
- ✅ **Workspace view**: Type, file count
- ✅ **Schedule view**: Time display
- ✅ **Scan view**: Findings count

---

## Appendix D: Remaining Enhancements (Optional)

### Phase 1: Progress Tracking (Future)
- [ ] Add `ToolProgressEvent` emission to long-running tools
- [ ] Show progress bars in mini previews
- [ ] Add estimated time remaining display

### Phase 2: Interactive Features (Future)
- [ ] Click mini preview to focus main VNC
- [ ] Add replay capability from tool timeline
- [ ] Add tool output copy-to-clipboard

---

*Last Updated: 2026-02-03*
