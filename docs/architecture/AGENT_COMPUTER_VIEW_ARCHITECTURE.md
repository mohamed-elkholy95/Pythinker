# Agent Computer View - Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      PYTHINKER FRONTEND                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              ChatPage.vue                              │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │          ToolPanel.vue                           │ │ │
│  │  │  ┌────────────────────────────────────────────┐ │ │ │
│  │  │  │     ToolPanelContent.vue                   │ │ │ │
│  │  │  │                                            │ │ │ │
│  │  │  │  ┌──────────────┐                         │ │ │ │
│  │  │  │  │ [MonitorPlay]│ ◄─── Click             │ │ │ │
│  │  │  │  └──────┬───────┘                         │ │ │ │
│  │  │  │         │                                 │ │ │ │
│  │  │  │         ▼                                 │ │ │ │
│  │  │  │  showComputerView = true                 │ │ │ │
│  │  │  └────────────────────────────────────────────┘ │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │        AgentComputerModal.vue (Teleport to body)      │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │                                                  │ │ │
│  │  │      ╔═══════════════════════════════════╗      │ │ │
│  │  │      ║   AgentComputerView.vue          ║      │ │ │
│  │  │      ║                                   ║      │ │ │
│  │  │      ║  ┌─────────────────────────────┐ ║      │ │ │
│  │  │      ║  │ Header: "Agent's Computer" │ ║      │ │ │
│  │  │      ║  └─────────────────────────────┘ ║      │ │ │
│  │  │      ║  ┌─────────────────────────────┐ ║      │ │ │
│  │  │      ║  │ Status: "Agent using Tool" │ ║      │ │ │
│  │  │      ║  └─────────────────────────────┘ ║      │ │ │
│  │  │      ║  ┌─────────────────────────────┐ ║      │ │ │
│  │  │      ║  │ Address: "https://..."      │ ║      │ │ │
│  │  │      ║  └─────────────────────────────┘ ║      │ │ │
│  │  │      ║  ┌─────────────────────────────┐ ║      │ │ │
│  │  │      ║  │                             │ ║      │ │ │
│  │  │      ║  │    LiveViewer.vue           │ ║      │ │ │
│  │  │      ║  │    (CDP primary, VNC fallback)│ ║    │ │ │
│  │  │      ║  │                             │ ║      │ │ │
│  │  │      ║  └─────────────────────────────┘ ║      │ │ │
│  │  │      ║  ┌─────────────────────────────┐ ║      │ │ │
│  │  │      ║  │ Timeline: [◀][▶]──●── live │ ║      │ │ │
│  │  │      ║  └─────────────────────────────┘ ║      │ │ │
│  │  │      ║  ┌─────────────────────────────┐ ║      │ │ │
│  │  │      ║  │ Task: "Research..." 2/8    │ ║      │ │ │
│  │  │      ║  └─────────────────────────────┘ ║      │ │ │
│  │  │      ╚═══════════════════════════════════╝      │ │ │
│  │  │                                                  │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│                      EVENT FLOW                              │
└──────────────────────────────────────────────────────────────┘

Agent Execution
    │
    ├─► browser_navigate(url="https://...")
    │       │
    │       ▼
    │   Backend Tool Execution
    │       │
    │       ▼
    │   SSE Event to Frontend
    │       │
    │       ▼
    ├─► ToolContent received
    │       │
    │       ├─► ToolPanelContent updates
    │       │       │
    │       │       ├─► Shows browser tool
    │       │       └─► MonitorPlay button visible
    │       │
    │       └─► useBrowserState.updateBrowserState()
    │               │
    │               ├─► currentBrowserUrl.value = url
    │               ├─► currentBrowserAction.value = "Browsing"
    │               └─► browserHistory.push({ url, timestamp })
    │
    └─► User clicks MonitorPlay button
            │
            ▼
        showComputerView = true
            │
            ▼
        AgentComputerModal opens
            │
            ▼
        AgentComputerView renders
            │
            ├─► Displays agent name
            ├─► Shows current tool icon
            ├─► Displays status: "Agent using Browser | Browsing"
            ├─► Shows address bar with URL
            ├─► LiveViewer connects through backend (CDP screencast)
            │       │
            │       ├─► Signed URL: POST /sessions/{id}/sandbox/signed-url?target=screencast&quality=...&max_fps=...
            │       │       │
            │       │       └─► WS /sessions/{id}/screencast?...signature=...
            │       │               │
            │       │               └─► Backend proxy to sandbox CDP stream
            │       │               │
            │       │               └─► Sandbox CDP Screencast
            │       │                       │
            │       │                       └─► Live canvas frames
            │       │
            │       └─► Fallback: WebSocket /sessions/{id}/vnc (if CDP fails)
            │               │
            │               └─► Backend VNC tunnel → Sandbox VNC Server (5901)
            │
            └─► Displays task progress
```

## Component Hierarchy

```
ChatPage
  └── ToolPanel
      └── ToolPanelContent
          ├── [Existing tool views]
          │   ├── BrowserToolView
          │   ├── TerminalContentView
          │   └── LiveViewer
          │
          └── AgentComputerModal (Teleport)
              └── AgentComputerView
                  ├── Window Header
                  │   ├── Title: "{Agent}'s Computer"
                  │   └── Controls: [PIP][Maximize][Close]
                  │
                  ├── Status Bar
                  │   ├── Tool Icon
                  │   ├── Agent Name
                  │   ├── Tool Name
                  │   ├── Action
                  │   └── URL
                  │
                  ├── Address Bar (conditional)
                  │   ├── Lock Icon (HTTPS)
                  │   └── URL Display
                  │
                  ├── Display Area
                  │   ├── LiveViewer
                  │   │   ├── SandboxViewer (CDP canvas)
                  │   │   └── VNCViewer (fallback)
                  │   │
                  │   ├── Loading State
                  │   │   ├── Spinner
                  │   │   └── "Connecting..."
                  │   │
                  │   └── Jump to Live Button
                  │       └── [▶ Jump to live]
                  │
                  ├── Timeline Controls
                  │   ├── Play/Pause Button
                  │   ├── Skip Back Button
                  │   ├── Seek Slider
                  │   ├── Skip Forward Button
                  │   └── Live Indicator
                  │       ├── Red Dot (pulsing)
                  │       └── "live" text
                  │
                  └── Task Progress
                      ├── Color Indicator
                      ├── Task Title
                      ├── Task Time
                      ├── Task Status
                      ├── Task Steps
                      └── Expand Toggle
```

## State Management

```
┌────────────────────────────────────────────────────────┐
│           useBrowserState Composable (Global)          │
├────────────────────────────────────────────────────────┤
│                                                         │
│  State:                                                 │
│    • currentBrowserUrl: ref<string>                    │
│    • currentBrowserAction: ref<string>                 │
│    • browserHistory: ref<Array>                        │
│                                                         │
│  Computed:                                              │
│    • latestUrl: string                                 │
│    • isBrowsing: boolean                               │
│                                                         │
│  Methods:                                               │
│    • updateBrowserState(toolContent)                   │
│    • clearBrowserState()                               │
│                                                         │
└────────────────────────────────────────────────────────┘
         ▲                              │
         │                              │
         │ Watch ToolContent            │ Read State
         │                              ▼
┌────────────────────┐        ┌────────────────────┐
│ ToolPanelContent   │        │ AgentComputerView  │
│                    │        │                    │
│ watch(toolContent) │        │ Display URL        │
│   updateBrowserState()      │ Display Action     │
└────────────────────┘        └────────────────────┘
```

## Live View Connection Flow

Primary: CDP Screencast

```
AgentComputerView
    │
    ├─► Props: sessionId = "abc123"
    │
    ▼
LiveViewer Component
    │
    ├─► Select renderer (default: CDP)
    │
    ▼
SandboxViewer
    │
    ├─► Call: getScreencastUrl(sessionId, quality, maxFps)
    │       │
    │       └─► API: POST /sessions/abc123/sandbox/signed-url?target=screencast&quality=70&max_fps=15
    │               │
    │               └─► Returns: "ws://localhost:8000/api/v1/sessions/abc123/screencast?quality=70&max_fps=15&signature=..."
    │
    └─► WebSocket stream (backend proxy) → JPEG frames → Canvas
```

```
┌─────────────────────────────────────────────────────────────┐
│                VNC Connection Pipeline (Fallback)            │
└─────────────────────────────────────────────────────────────┘

AgentComputerView
    │
    ├─► Props: sessionId = "abc123"
    │
    ▼
VNCViewer Component
    │
    ├─► onMounted() or props change
    │
    ▼
initVNCConnection()
    │
    ├─► Call: getVNCUrl(sessionId)
    │       │
    │       └─► API: POST /sessions/abc123/vnc/signed-url
    │               │
    │               └─► Returns: "ws://localhost:8000/api/v1/sessions/abc123/vnc?signature=xyz"
    │
    ├─► Import: @novnc/novnc/lib/rfb
    │
    ├─► Create: new RFB(container, wsUrl, options)
    │       │
    │       └─► Options:
    │           • credentials: { password: '' }
    │           • shared: true
    │           • wsProtocols: ['binary']
    │           • scaleViewport: true
    │           • clipViewport: true
    │           • viewOnly: true
    │
    ▼
WebSocket Connection
    │
    ├─► ws://backend:8000/api/v1/sessions/abc123/vnc
    │       │
    │       └─► Backend: session_routes.py::vnc_websocket()
    │               │
    │               ├─► Verify signature
    │               ├─► Get sandbox from session
    │               ├─► Get VNC URL: ws://sandbox:5901
    │               │
    │               └─► Bidirectional Tunnel:
    │                       │
    │                       ├─► Frontend → Sandbox (keyboard, mouse)
    │                       └─► Sandbox → Frontend (screen updates)
    │
    ▼
Sandbox VNC Server
    │
    ├─► Port: 5900 (RFB via x11vnc)
    ├─► Port: 5901 (WebSocket via websockify)
    ├─► Display: :1 (Xvfb)
    │
    └─► Streams desktop to frontend
            │
            └─► VNC viewer renders in canvas
                    │
                    └─► User sees live sandbox desktop
```

## File Structure

```
pythinker/
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── AgentComputerView.vue       ★ NEW (Main component)
│       │   ├── AgentComputerModal.vue      ★ NEW (Modal wrapper)
│       │   ├── LiveViewer.vue              (CDP primary, VNC fallback)
│       │   ├── SandboxViewer.vue           (CDP canvas)
│       │   ├── VNCViewer.vue               (Fallback)
│       │   ├── ToolPanel.vue               (Existing)
│       │   └── ToolPanelContent.vue        (Modified)
│       │
│       └── composables/
│           └── useBrowserState.ts          ★ NEW (State management)
│
├── backend/
│   └── app/
│       ├── interfaces/api/
│       │   └── session_routes.py           (VNC + sandbox signed-url endpoints)
│       │
│       ├── infrastructure/external/
│       │   ├── browser/
│       │   │   └── playwright_browser.py   (Existing)
│       │   └── sandbox/
│       │       └── docker_sandbox.py       (Existing)
│       │
│       └── domain/
│           ├── services/tools/
│           │   └── browser.py              (Existing)
│           └── models/
│               └── event.py                (Existing - ToolContent)
│
└── docs/
    ├── architecture/AGENT_COMPUTER_VIEW_ARCHITECTURE.md  (This file)
    ├── guides/QUICKSTART_AGENT_COMPUTER_VIEW.md          (Quick start)
    └── guides/OPENREPLAY.md                              (Live/replay details)
```

## Network Topology

```
┌──────────────────────────────────────────────────────────┐
│                     USER BROWSER                         │
│  http://localhost:5174                                   │
└───────────────────────┬──────────────────────────────────┘
                        │
                        │ HTTP/WS
                        │
┌───────────────────────▼──────────────────────────────────┐
│                 FRONTEND (Vite Dev Server)               │
│  Port: 5174                                              │
│  • Vue 3 SPA                                             │
│  • AgentComputerView component                           │
│  • LiveViewer (CDP primary, VNC fallback)                │
└───────────────────────┬──────────────────────────────────┘
                        │
                        │ API Calls
                        │ WebSocket (VNC)
                        │
┌───────────────────────▼──────────────────────────────────┐
│                 BACKEND (FastAPI)                        │
│  Port: 8000                                              │
│  • POST /sessions/{id}/sandbox/signed-url (CDP stream)  │
│  • WS /sessions/{id}/screencast (CDP proxy)             │
│  • WS /sessions/{id}/input (takeover input proxy)       │
│  • POST /sessions/{id}/vnc/signed-url (VNC fallback)    │
│  • WS /sessions/{id}/vnc (VNC tunnel)                   │
│  • Session management                                    │
└───────────────────────┬──────────────────────────────────┘
                        │
                        │ Docker network
                        │
┌───────────────────────▼──────────────────────────────────┐
│                 SANDBOX CONTAINER                        │
│  Network: pythinker_sandbox_network                      │
│  • VNC Server (x11vnc): Port 5900 (RFB)                 │
│  • VNC WS proxy (websockify): Port 5901                │
│  • Screencast API: Port 8080 (/api/v1/screencast/stream)│
│  • Chrome DevTools: Port 9222                            │
│  • Xvfb Display: :1                                      │
│  • Chromium browser running                              │
└──────────────────────────────────────────────────────────┘
```

## Security Model

```
┌────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                         │
└────────────────────────────────────────────────────────────┘

1. Signed URL Generation
   ┌─────────────────────────────────────────────────────┐
   │ POST /sessions/{id}/sandbox/signed-url (CDP)        │
   │ POST /sessions/{id}/vnc/signed-url (fallback)       │
   │ • Requires authentication (session ownership)       │
   │ • Generates time-limited signature (15 min TTL)      │
   │ • CDP quality/max_fps are included in signed path    │
   │ • Returns: ws://...?signature=<token>               │
   └─────────────────────────────────────────────────────┘

2. WebSocket Signature Verification
   ┌─────────────────────────────────────────────────────┐
   │ WS /sessions/{id}/screencast?quality=...&max_fps=...&signature=<token> │
   │ WS /sessions/{id}/vnc?signature=<token>             │
   │ • Verifies signature before connecting              │
   │ • Checks expiration time                            │
   │ • Validates session ownership                       │
   └─────────────────────────────────────────────────────┘

3. View-Only Mode
   ┌─────────────────────────────────────────────────────┐
   │ RFB Connection                                      │
   │ • viewOnly: true (no keyboard/mouse control)        │
   │ • Prevents accidental interference                  │
   │ • Read-only monitoring                              │
   └─────────────────────────────────────────────────────┘

4. Container Isolation
   ┌─────────────────────────────────────────────────────┐
   │ Docker Sandbox                                      │
   │ • Isolated network namespace                        │
   │ • Limited capabilities                              │
   │ • Resource limits (CPU, memory)                     │
   │ • Ephemeral file system                             │
   └─────────────────────────────────────────────────────┘
```

## Performance Characteristics

```
┌────────────────────────────────────────────────────────────┐
│                     PERFORMANCE METRICS                     │
└────────────────────────────────────────────────────────────┘

Component Rendering
├─ AgentComputerView mount: <100ms
├─ Modal animation: 300ms
└─ Teleport overhead: <10ms

CDP Connection (Primary)
├─ WebSocket handshake: 50-150ms
├─ First frame render: 100-500ms
└─ Frame decode: 1-3% (GPU accelerated)

VNC Connection (Fallback)
├─ Signed URL generation: 50-100ms
├─ WebSocket handshake: 100-300ms
├─ VNC protocol negotiation: 200-500ms
└─ First frame render: 500-1500ms

Network Bandwidth
├─ VNC stream: 500kbps - 2Mbps (adaptive)
├─ Control overhead: <50kbps
└─ Screenshot: ~100KB (when used)

Memory Usage
├─ Component: ~2MB
├─ VNC canvas buffer: 20-50MB
├─ WebSocket overhead: ~1MB
└─ Total: ~25-55MB

CPU Usage
├─ VNC decoding: 2-5% (1 core)
├─ Canvas rendering: 1-3% (GPU accelerated)
└─ Total: 3-8% (mostly GPU)
```

## Scaling Considerations

```
┌────────────────────────────────────────────────────────────┐
│                    SCALING SCENARIOS                        │
└────────────────────────────────────────────────────────────┘

Single User
  • 1 session → 1 sandbox → 1 live view connection (CDP primary)
  • Resources: ~100MB RAM, ~10% CPU
  • Bandwidth: ~1Mbps
  • Works: ✅ Perfect

Multiple Sessions (Same User)
  • 5 sessions → 5 sandboxes → 5 live view connections (CDP/VNC)
  • Resources: ~500MB RAM, ~30% CPU
  • Bandwidth: ~5Mbps
  • Works: ✅ Good (if opened sequentially)

Concurrent Viewers (Same Session)
  • 1 session → 1 sandbox → N live view connections (CDP/VNC)
  • Resources: Scales with viewers (N × 25MB)
  • Bandwidth: Scales with viewers (N × 1Mbps)
  • Works: ✅ Supported (shared: true)

Load Balancing
  • Use multiple sandbox hosts
  • Route by session affinity
  • Scale horizontally
  • Works: ✅ Supported
```

---

## Summary

The Agent Computer View is a **self-contained, modular system** that uses CDP screencast as the primary live view, with VNC as a fallback, while providing a polished, Claude Code-style interface for monitoring agent activities.

**Key Architectural Decisions:**
- ✅ CDP primary with VNC fallback
- ✅ Modal pattern for non-intrusive UX
- ✅ Composable state management (no Vuex/Pinia)
- ✅ View-only mode for safe monitoring
- ✅ Signed URLs for security
- ✅ Scoped styles for isolation

**Integration Points:**
- Minimal changes to existing code
- Drop-in component pattern
- Event-driven updates
- Reactive data flow

**Performance:**
- Lightweight components
- Efficient CDP stream with fallback VNC
- GPU-accelerated rendering
- Scales to multiple viewers
