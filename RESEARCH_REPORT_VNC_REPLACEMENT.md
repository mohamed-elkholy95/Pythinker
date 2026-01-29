# Technical Research Report: Remote Desktop Solution Migration & Service Integration

**Project:** Pythinker AI Agent System
**Date:** January 27, 2026
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Architecture Analysis](#current-architecture-analysis)
3. [Remote Desktop Solution Research](#remote-desktop-solution-research)
4. [RustDesk Evaluation](#rustdesk-evaluation)
5. [Recommended Alternative Solutions](#recommended-alternative-solutions)
6. [Context7 MCP Integration](#context7-mcp-integration)
7. [Tavily Service Integration](#tavily-service-integration)
8. [Recommended Implementation Plan](#recommended-implementation-plan)
9. [Architecture Diagrams](#architecture-diagrams)
10. [Package Versions & Vue 3 Compatibility](#package-versions--vue-3-compatibility)
11. [Testing Strategy](#testing-strategy)
12. [Rollback Procedures](#rollback-procedures)
13. [Conclusion & Recommendations](#conclusion--recommendations)

---

## Executive Summary

After comprehensive research, **RustDesk is NOT recommended** as a VNC/NoVNC replacement for the Pythinker sandbox environment due to critical limitations:

- **No JavaScript/TypeScript SDK** - Cannot programmatically integrate with Vue 3
- **No npm package** available for web integration
- **No native HTML5 web client** - Flutter-based only, requiring iframe embedding
- **Complex infrastructure** - Requires hbbs/hbbr relay servers

### Recommended Alternatives

| Solution | Recommendation | Use Case |
|----------|---------------|----------|
| **Selkies-GStreamer** | **TOP CHOICE** | WebRTC-based, 60fps, GPU acceleration, purpose-built for containers |
| **KasmVNC** | Recommended | Enhanced VNC with modern web client, simpler migration |
| **NoVNC (Current)** | Maintain | Stable, proven, well-integrated |

### Service Integration Status

| Service | Status | Package Available |
|---------|--------|-------------------|
| Context7 MCP | Ready | `@upstash/context7-mcp@^1.0.0` |
| Tavily | Ready | `@tavily/core@^0.7.1` (JS) / `tavily-python@^0.7.19` (Python) |

---

## Current Architecture Analysis

### VNC Implementation Overview

The current Pythinker implementation uses a **proven VNC streaming architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Vue 3)                          │
├─────────────────────────────────────────────────────────────┤
│  VNCViewer.vue                                               │
│  ├─ @novnc/novnc@^1.5.0 (RFB protocol)                      │
│  ├─ Dynamic module loading (npm + CDN fallback)              │
│  └─ WebSocket connection with signed URL authentication      │
└─────────────────────────────────────────────────────────────┘
                          ↓↑
         WebSocket (Binary Protocol)
         ws://host/api/v1/sessions/{id}/vnc?signature=...
                          ↓↑
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND (FastAPI)                           │
├─────────────────────────────────────────────────────────────┤
│  session_routes.py                                           │
│  ├─ /vnc WebSocket endpoint (bidirectional tunneling)       │
│  ├─ /vnc/signed-url endpoint (HMAC token generation)        │
│  └─ Signature validation with 15-minute expiration          │
└─────────────────────────────────────────────────────────────┘
                          ↓↑
         WebSocket (Binary Data)
         ws://sandbox-ip:5901
                          ↓↑
┌─────────────────────────────────────────────────────────────┐
│              SANDBOX CONTAINER (Ubuntu 22.04)                │
├─────────────────────────────────────────────────────────────┤
│  Supervisor Managed Services                                 │
│  ├─ Xvfb (:1 display, 1280x1029x24)                         │
│  ├─ Chromium (renders to Xvfb)                              │
│  ├─ x11vnc (port 5900, no password, shared)                 │
│  └─ websockify (port 5901 → 5900 tunnel)                    │
└─────────────────────────────────────────────────────────────┘
```

### Current Dependencies

**Frontend:**
- `@novnc/novnc@^1.5.0` - RFB protocol implementation
- `vite-plugin-commonjs@^0.10.4` - ESM transformation for NoVNC

**Sandbox:**
- `x11vnc` - VNC server for X11
- `websockify` - WebSocket to VNC tunnel
- `xvfb` - Virtual X11 display

### Security Model

The current implementation uses **signature-based authentication**:
1. Frontend requests signed URL via REST API (authenticated)
2. Backend generates HMAC-signed URL with 15-minute expiration
3. WebSocket connection includes signature in query string
4. Invalid/expired signatures rejected at handshake

**This is a well-designed security model** that should be preserved in any migration.

---

## Remote Desktop Solution Research

### Evaluation Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Web Client | Critical | Native HTML5/JavaScript integration capability |
| Docker Integration | High | Container-friendly, minimal overhead |
| Performance | High | FPS, latency, compression efficiency |
| Security | High | Encryption, authentication options |
| Vue 3 Compatibility | Critical | npm packages, TypeScript support |
| Community Support | Medium | Active development, documentation |
| Resource Usage | Medium | CPU, memory footprint |

### Comparison Matrix

| Solution | Web Client | Docker | Performance | Security | npm Package | Verdict |
|----------|-----------|--------|-------------|----------|-------------|---------|
| **RustDesk** | None | Moderate | Good | Excellent | **None** | ❌ Not suitable |
| **Selkies-GStreamer** | Excellent | Excellent | Excellent | Good | Custom | ✅ Top choice |
| **KasmVNC** | Excellent | Excellent | Good | Good | None (embed) | ✅ Recommended |
| **Apache Guacamole** | Excellent | Excellent | Good | Excellent | `guacamole-common-js` | ⚠️ Overkill |
| **Xpra** | Good | Good | Good | Good | None | ⚠️ Alternative |
| **NoVNC (Current)** | Good | Excellent | Moderate | Good | `@novnc/novnc` | ✅ Current |
| **XRDP** | Limited | Good | Good | Good | None | ❌ Requires gateway |
| **NoMachine** | Limited | Poor | Excellent | Good | None | ❌ Commercial |
| **Broadway** | Native | Good | Limited | Basic | None | ❌ GTK3 only |

---

## RustDesk Evaluation

### Overview

RustDesk is an open-source remote desktop solution written in Rust, positioned as a self-hosted alternative to TeamViewer. It has 106k+ GitHub stars and active development.

**Repository:** https://github.com/rustdesk/rustdesk
**Current Version:** 1.4.5
**License:** AGPL-3.0

### Architecture

RustDesk consists of two server components:

1. **hbbs (ID/Rendezvous Server)**
   - Client registration and ID management
   - NAT traversal and hole punching
   - Ports: TCP 21114-21116, 21118 (WebSocket), UDP 21116

2. **hbbr (Relay Server)**
   - Handles relayed connections when P2P fails
   - Ports: TCP 21117, 21119 (WebSocket)

### Docker Deployment

```yaml
version: '3'
services:
  hbbs:
    image: rustdesk/rustdesk-server:latest
    command: hbbs
    ports:
      - 21115:21115
      - 21116:21116
      - 21116:21116/udp
      - 21118:21118
    volumes:
      - ./data:/root

  hbbr:
    image: rustdesk/rustdesk-server:latest
    command: hbbr
    ports:
      - 21117:21117
      - 21119:21119
    volumes:
      - ./data:/root
```

### Critical Limitations for Pythinker

#### 1. No JavaScript/TypeScript SDK

**Finding:** After extensive research, there are **NO official or community npm packages** for RustDesk integration.

The web client is built with **Flutter Web** (compiled to WebAssembly/JavaScript), not a proper JavaScript library. This means:
- Cannot programmatically control connections from Vue 3
- Cannot integrate RFB-like events into the application
- Cannot handle reconnection logic in JavaScript

#### 2. No Native HTML5 Client Library

Unlike NoVNC which provides `@novnc/novnc`, RustDesk has no equivalent:

```javascript
// NoVNC - Easy integration
import RFB from '@novnc/novnc/lib/rfb';
const rfb = new RFB(container, 'ws://...');
rfb.addEventListener('connect', () => { /* ... */ });

// RustDesk - No equivalent
// Must use iframe embedding only
```

#### 3. Iframe-Only Integration

The only web integration option is iframe embedding:

```vue
<template>
  <iframe
    :src="`${rustdeskWebUrl}?id=${deviceId}`"
    allow="clipboard-read; clipboard-write"
  />
</template>
```

**Limitations:**
- Loss of programmatic control
- No event callbacks
- Limited styling options
- Security concerns with cross-origin communication

#### 4. Complex Infrastructure Requirements

RustDesk requires:
- Running hbbs and hbbr servers
- Firewall configuration for 6+ ports
- Client configuration with server address and public key
- Device ID management for each sandbox

### RustDesk Verdict: NOT RECOMMENDED

| Factor | Assessment |
|--------|------------|
| Vue 3 Integration | ❌ Impossible without iframe |
| npm Package | ❌ None available |
| API Control | ❌ No JavaScript API |
| Infrastructure | ⚠️ Complex (multiple servers) |
| Security | ✅ Excellent (E2E encryption) |
| Performance | ✅ Good (P2P optimized) |

**Recommendation:** Do not proceed with RustDesk migration. The lack of JavaScript integration makes it unsuitable for the Pythinker Vue 3 frontend.

---

## Recommended Alternative Solutions

### Option 1: Selkies-GStreamer (TOP CHOICE)

**Overview:** Open-source low-latency GPU-accelerated WebRTC HTML5 remote desktop, started by Google engineers.

**Repository:** https://github.com/selkies-project/selkies-gstreamer
**Stars:** 1.3k+
**License:** MPL-2.0

#### Key Features

- **WebRTC-based:** Native browser support, minimal latency
- **60fps at 1080p** with software encoding, better with GPU
- **Codec Support:** H.264, H.265, VP8, VP9, AV1
- **Hardware Acceleration:** NVIDIA NVENC, Intel/AMD VA-API
- **Audio Streaming:** Opus codec support
- **Kubernetes-Ready:** Designed for container orchestration

#### Performance Comparison

| Metric | NoVNC (Current) | Selkies-GStreamer |
|--------|-----------------|-------------------|
| Protocol | VNC/RFB | WebRTC |
| Max FPS | ~30 practical | 60+ |
| Latency | 50-150ms | 10-50ms |
| Audio | None | Full support |
| GPU Accel | None | NVENC, VA-API |

#### Integration Approach

Selkies-GStreamer provides an HTML5 interface that can be:
1. **Embedded via iframe** (simpler)
2. **Integrated via JavaScript client** (advanced)

```dockerfile
# Sandbox Dockerfile additions
RUN apt-get install -y \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-x \
    gstreamer1.0-pulseaudio

RUN pip install selkies-gstreamer
```

#### TURN Server Requirement

For production WebRTC deployment, a TURN server (coturn) is required:

```yaml
services:
  coturn:
    image: coturn/coturn:latest
    ports:
      - "3478:3478"
      - "3478:3478/udp"
    environment:
      - TURN_USER=pythinker
      - TURN_PASSWORD=secure_password
```

### Option 2: KasmVNC (SIMPLER MIGRATION)

**Overview:** Enhanced VNC implementation with modern web technologies, used by Kasm Workspaces.

**Repository:** https://github.com/kasmtech/KasmVNC
**License:** GPLv2

#### Key Features

- **Drop-in replacement** for x11vnc
- **Built-in web server** (no websockify needed)
- **Modern HTML5 client** with responsive design
- **WebCodecs support** for hardware encoding
- **Per-user ACL** and JWT authentication

#### Migration Path

Replace x11vnc + websockify with KasmVNC in `supervisord.conf`:

```ini
[program:kasmvnc]
command=/opt/KasmVNC/bin/kasmvncserver \
    :1 \
    -websocketPort 5901 \
    -SecurityTypes None \
    -geometry 1280x1029 \
    -depth 24
```

#### Comparison

| Factor | Current (x11vnc) | KasmVNC |
|--------|------------------|---------|
| Performance | Moderate | Good |
| Built-in Web | No (needs websockify) | Yes |
| WebCodecs | No | Yes |
| Migration Effort | Baseline | Low |

### Option 3: Apache Guacamole (ENTERPRISE)

**Overview:** HTML5 clientless remote desktop gateway supporting VNC, RDP, SSH.

**Repository:** https://guacamole.apache.org/
**License:** Apache 2.0

#### When to Choose

- Multi-protocol requirements (VNC + RDP + SSH)
- Enterprise security requirements
- Session recording/auditing needs
- Centralized connection management

#### Why NOT for Pythinker

- **Overkill:** Requires 3+ containers (guacd, guacamole web, database)
- **Higher latency:** Protocol translation overhead
- **Complex setup:** Significant infrastructure changes

---

## Context7 MCP Integration

### Overview

Context7 is an MCP (Model Context Protocol) server by **Upstash** that provides up-to-date, version-specific documentation and code examples for programming libraries.

**Website:** https://context7.com
**npm Package:** `@upstash/context7-mcp`

### How It Works

1. AI receives coding question
2. `use context7` trigger fetches current documentation
3. Documentation injected into context window
4. LLM generates code with current APIs

### Installation

#### npm Package
```bash
npm install @upstash/context7-mcp
# or run directly
npx -y @upstash/context7-mcp --api-key YOUR_API_KEY
```

#### Claude Code Integration
```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp --api-key YOUR_API_KEY
```

#### MCP Configuration (`mcp.json`)
```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp", "--api-key", "YOUR_API_KEY"]
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `resolve-library-id` | Resolves package name to Context7 library ID |
| `query-docs` | Retrieves documentation and code examples |
| `get_code_examples` | Get specific code examples |
| `compare_libraries` | Compare multiple libraries |
| `troubleshoot_error` | Debug errors with library context |

### Pricing

| Plan | Price | API Calls |
|------|-------|-----------|
| Free | $0/month | 1,000/month |
| Pro | $10/seat/month | 5,000/seat/month |
| Enterprise | Custom | Custom |

### Backend Integration (Python)

Since Context7 is MCP-based, integrate through LangChain's MCP support:

```python
# backend/app/infrastructure/external/mcp/context7_client.py
from mcp import ClientSession, StdioServerParameters

class Context7Client:
    async def query_docs(self, library: str, query: str) -> str:
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@upstash/context7-mcp", "--api-key", self.api_key]
        )
        async with ClientSession(server_params) as session:
            result = await session.call_tool(
                "query-docs",
                {"libraryId": library, "query": query}
            )
            return result.content
```

---

## Tavily Service Integration

### Overview

Tavily is an AI-native search and web content API designed for AI agents and LLM applications. It provides real-time web search, content extraction, website crawling, and deep research capabilities.

**Website:** https://tavily.com
**npm Package:** `@tavily/core@^0.7.1`
**Python Package:** `tavily-python@^0.7.19`

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Search** | Real-time web search optimized for AI/LLM |
| **Extract** | Raw content retrieval from URLs |
| **Crawl** | Multi-page content extraction |
| **Map** | Website structure discovery |
| **Research** | Deep research with comprehensive results |

### Python SDK Installation

```bash
pip install tavily-python==0.7.19
```

### Python Integration

```python
# backend/app/infrastructure/external/search/tavily_client.py
from tavily import TavilyClient

class TavilySearchClient:
    def __init__(self, api_key: str):
        self.client = TavilyClient(api_key=api_key)

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Real-time web search."""
        response = self.client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results
        )
        return response.get("results", [])

    async def extract(self, urls: list[str]) -> list[dict]:
        """Extract content from URLs."""
        response = self.client.extract(
            urls=urls[:20],  # Max 20 URLs
            extract_depth="advanced"
        )
        return response.get("results", [])

    async def crawl(self, url: str, max_depth: int = 2) -> list[dict]:
        """Crawl website for content."""
        response = self.client.crawl(
            url=url,
            max_depth=max_depth,
            limit=50
        )
        return response.get("results", [])
```

### JavaScript SDK Installation

```bash
npm install @tavily/core@^0.7.1
```

### JavaScript Integration (for tools or Node.js services)

```typescript
// If needed for Node.js services
import { tavily } from "@tavily/core";

const tvly = tavily({ apiKey: process.env.TAVILY_API_KEY });

const searchResults = await tvly.search("query");
const extractedContent = await tvly.extract(["https://example.com"]);
```

### Pricing

| Plan | Price | Credits |
|------|-------|---------|
| Researcher (Free) | $0/month | 1,000 credits/month |
| Pay As You Go | $0.008/credit | Pay per use |
| Project | $30/month | 4,000 credits/month |
| Enterprise | Custom | Custom |

### Agent Tool Integration

Add Tavily as a tool for the AI agent:

```python
# backend/app/domain/services/tools/tavily_search_tool.py
from app.domain.services.tools.base import BaseTool
from app.infrastructure.external.search.tavily_client import TavilySearchClient

class TavilySearchTool(BaseTool):
    name = "tavily_search"
    description = "Search the web for real-time information"

    def __init__(self, api_key: str):
        self.client = TavilySearchClient(api_key)

    async def execute(self, query: str, max_results: int = 5) -> dict:
        results = await self.client.search(query, max_results)
        return {
            "success": True,
            "results": results
        }
```

---

## Recommended Implementation Plan

Based on research findings, here is the recommended phased implementation:

### Phase 1: Service Integration (Week 1)

**Goal:** Integrate Context7 MCP and Tavily without changing VNC.

#### Step 1.1: Install Python Packages

```bash
cd backend
pip install tavily-python==0.7.19
# Add to requirements.txt
echo "tavily-python==0.7.19" >> requirements.txt
```

#### Step 1.2: Create Tavily Client

```python
# backend/app/infrastructure/external/search/tavily_client.py
from tavily import TavilyClient
from app.core.config import settings

class TavilySearchService:
    def __init__(self):
        self.client = TavilyClient(api_key=settings.tavily_api_key)

    async def search(self, query: str, **kwargs) -> dict:
        return self.client.search(query, **kwargs)

    async def extract(self, urls: list[str], **kwargs) -> dict:
        return self.client.extract(urls=urls, **kwargs)
```

#### Step 1.3: Create Tavily Tool

```python
# backend/app/domain/services/tools/web_search_tavily.py
from app.domain.services.tools.base import BaseTool

class TavilyWebSearchTool(BaseTool):
    """Web search using Tavily API"""

    name = "tavily_search"
    description = "Search the web for real-time information using Tavily"

    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
```

#### Step 1.4: Add Environment Variables

```bash
# .env additions
TAVILY_API_KEY=tvly-your-api-key
CONTEXT7_API_KEY=your-context7-key
```

### Phase 2: VNC Performance Improvement (Week 2)

**Goal:** Upgrade to KasmVNC for better performance without major architecture changes.

#### Step 2.1: Update Sandbox Dockerfile

```dockerfile
# Replace x11vnc with KasmVNC
RUN wget https://github.com/kasmtech/KasmVNC/releases/download/v1.3.3/kasmvncserver_jammy_1.3.3_amd64.deb && \
    apt-get install -y ./kasmvncserver_jammy_1.3.3_amd64.deb && \
    rm kasmvncserver_jammy_1.3.3_amd64.deb
```

#### Step 2.2: Update supervisord.conf

```ini
# Remove x11vnc and websockify, add KasmVNC
[program:kasmvnc]
command=/opt/KasmVNC/bin/kasmvncserver :1 \
    -websocketPort 5901 \
    -SecurityTypes None \
    -geometry 1280x1029 \
    -depth 24 \
    -interface 0.0.0.0
autorestart=true
priority=40
```

#### Step 2.3: Test Frontend Compatibility

KasmVNC is VNC-compatible; the existing NoVNC frontend should work with minimal changes.

### Phase 3: WebRTC Migration (Week 3-4, Optional)

**Goal:** Migrate to Selkies-GStreamer for optimal performance.

**Note:** This is a more significant change and should only be pursued if Phase 2 performance is insufficient.

#### Step 3.1: Set Up TURN Server

```yaml
# docker-compose.yml addition
services:
  coturn:
    image: coturn/coturn:4.6.2
    ports:
      - "3478:3478"
      - "3478:3478/udp"
      - "5349:5349"
    environment:
      - TURN_USER=pythinker
      - TURN_PASSWORD=${TURN_PASSWORD}
      - TURN_REALM=pythinker.local
```

#### Step 3.2: Update Sandbox for Selkies

```dockerfile
# Install GStreamer dependencies
RUN apt-get install -y \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-x \
    python3-gst-1.0

# Install Selkies-GStreamer
RUN pip install selkies-gstreamer
```

#### Step 3.3: Create WebRTC Vue Component

```vue
<!-- frontend/src/components/WebRTCViewer.vue -->
<template>
  <div ref="container" class="webrtc-container">
    <video ref="video" autoplay playsinline></video>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  sessionId: string
  signalUrl: string
}>()

// WebRTC implementation using Selkies client
</script>
```

---

## Architecture Diagrams

### Current Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                              │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Vue 3 Frontend                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │    │
│  │  │ ChatPage    │  │ ToolPanel   │  │ VNCViewer   │       │    │
│  │  └─────────────┘  └─────────────┘  └──────┬──────┘       │    │
│  │                                            │              │    │
│  │                           @novnc/novnc (RFB over WebSocket)   │
│  └──────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ HTTPS/WSS
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │ Chat Endpoints  │  │ VNC WS Tunnel   │  │ Agent Service   │   │
│  │ /sessions/chat  │  │ /sessions/vnc   │  │ Tool Execution  │   │
│  └─────────────────┘  └────────┬────────┘  └─────────────────┘   │
│                                │                                  │
└────────────────────────────────┼─────────────────────────────────┘
                                 │ WebSocket
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                    SANDBOX CONTAINER                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │    Xvfb    │→ │  Chromium  │  │   x11vnc   │→ │ websockify │  │
│  │  :1 1280x  │  │ --display=:1  │:5900       │  │   :5901    │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Proposed Architecture (Phase 2: KasmVNC)

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                              │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Vue 3 Frontend                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │    │
│  │  │ ChatPage    │  │ ToolPanel   │  │ VNCViewer   │       │    │
│  │  │ + Tavily    │  │ + Context7  │  │ (unchanged) │       │    │
│  │  └─────────────┘  └─────────────┘  └──────┬──────┘       │    │
│  │                                            │              │    │
│  │                           @novnc/novnc (compatible with KasmVNC)
│  └──────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ HTTPS/WSS
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │ Chat + Tavily   │  │ VNC WS Tunnel   │  │ Agent Service   │   │
│  │ TavilySearchTool│  │ (unchanged)     │  │ + Context7 MCP  │   │
│  └─────────────────┘  └────────┬────────┘  └─────────────────┘   │
│                                │                                  │
└────────────────────────────────┼─────────────────────────────────┘
                                 │ WebSocket
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                    SANDBOX CONTAINER                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────────┐  │
│  │    Xvfb    │→ │  Chromium  │  │        KasmVNC            │  │
│  │  :1 1280x  │  │ --display=:1  │:5901 (built-in WebSocket) │  │
│  └────────────┘  └────────────┘  └────────────────────────────┘  │
│                                                                   │
│  ✓ Removed: x11vnc, websockify (replaced by KasmVNC)             │
└──────────────────────────────────────────────────────────────────┘
```

### Proposed Architecture (Phase 3: Selkies-GStreamer)

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                              │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Vue 3 Frontend                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │    │
│  │  │ ChatPage    │  │ ToolPanel   │  │ WebRTCViewer    │   │    │
│  │  │ + Tavily    │  │ + Context7  │  │ (new component) │   │    │
│  │  └─────────────┘  └─────────────┘  └────────┬────────┘   │    │
│  │                                              │            │    │
│  │                               WebRTC (DataChannel + MediaStream)
│  └──────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ HTTPS + WebRTC Signaling
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │ Chat + Tavily   │  │ WebRTC Signal   │  │ Agent Service   │   │
│  │ TavilySearchTool│  │ /sessions/rtc   │  │ + Context7 MCP  │   │
│  └─────────────────┘  └────────┬────────┘  └─────────────────┘   │
└────────────────────────────────┼─────────────────────────────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            ▼                                         ▼
┌─────────────────────┐                 ┌──────────────────────────┐
│    COTURN SERVER    │                 │    SANDBOX CONTAINER     │
│  TURN/STUN :3478    │◄────────────────│  ┌────────────────────┐  │
│  NAT Traversal      │                 │  │ Selkies-GStreamer  │  │
└─────────────────────┘                 │  │ WebRTC Encoder     │  │
                                        │  │ H.264/VP8/VP9      │  │
                                        │  └────────────────────┘  │
                                        │  ┌────────────────────┐  │
                                        │  │ Xvfb + Chromium    │  │
                                        │  └────────────────────┘  │
                                        └──────────────────────────┘
```

---

## Package Versions & Vue 3 Compatibility

### Current Vue 3 Stack

```json
{
  "vue": "^3.5.27",
  "vue-router": "^4.6.4",
  "vite": "^7.3.1",
  "typescript": "^5.9.3"
}
```

### Recommended Package Additions

#### Frontend (package.json)

```json
{
  "dependencies": {
    "@novnc/novnc": "^1.5.0",       // Current - KEEP
    "@tavily/core": "^0.7.1"         // NEW - for potential frontend search
  },
  "devDependencies": {
    "vite-plugin-commonjs": "^0.10.4"  // Current - KEEP
  }
}
```

**Note:** Context7 MCP is backend-only (MCP server), no frontend package needed.

#### Backend (requirements.txt)

```txt
# Existing dependencies...

# NEW: Service integrations
tavily-python==0.7.19              # Tavily search API
mcp==1.0.0                         # MCP protocol for Context7

# For Selkies (Phase 3 only)
# selkies-gstreamer==1.0.0         # WebRTC streaming
```

### Compatibility Matrix

| Package | Version | Vue 3 Compatible | Notes |
|---------|---------|------------------|-------|
| `@novnc/novnc` | ^1.5.0 | ✅ | Works via vite-plugin-commonjs |
| `@tavily/core` | ^0.7.1 | ✅ | Native ESM, TypeScript types |
| `@upstash/context7-mcp` | ^1.0.0 | N/A | Backend MCP server |
| `tavily-python` | ^0.7.19 | N/A | Python backend only |

### TypeScript Types

```typescript
// frontend/src/types/tavily.d.ts (if using @tavily/core in frontend)
declare module '@tavily/core' {
  interface TavilyOptions {
    apiKey: string;
  }

  interface SearchResult {
    title: string;
    url: string;
    content: string;
    score: number;
  }

  interface TavilyClient {
    search(query: string): Promise<{ results: SearchResult[] }>;
    extract(urls: string[]): Promise<{ results: any[] }>;
  }

  export function tavily(options: TavilyOptions): TavilyClient;
}
```

---

## Testing Strategy

### Phase 1: Unit Tests

#### Tavily Client Tests

```python
# backend/tests/infrastructure/external/test_tavily_client.py
import pytest
from unittest.mock import Mock, patch
from app.infrastructure.external.search.tavily_client import TavilySearchService

class TestTavilySearchService:
    @patch('tavily.TavilyClient')
    def test_search_returns_results(self, mock_client):
        mock_client.return_value.search.return_value = {
            "results": [{"title": "Test", "url": "https://test.com"}]
        }

        service = TavilySearchService()
        results = service.search("test query")

        assert len(results["results"]) == 1
        mock_client.return_value.search.assert_called_once_with("test query")

    @patch('tavily.TavilyClient')
    def test_extract_with_max_urls(self, mock_client):
        service = TavilySearchService()
        urls = [f"https://example{i}.com" for i in range(25)]

        service.extract(urls)

        # Should limit to 20 URLs
        call_args = mock_client.return_value.extract.call_args
        assert len(call_args.kwargs['urls']) <= 20
```

#### Tavily Tool Tests

```python
# backend/tests/domain/services/tools/test_tavily_tool.py
import pytest
from app.domain.services.tools.web_search_tavily import TavilyWebSearchTool

class TestTavilyWebSearchTool:
    def test_tool_parameters(self):
        tool = TavilyWebSearchTool()

        assert tool.name == "tavily_search"
        assert "query" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["query"]
```

### Phase 2: Integration Tests

#### VNC Connection Tests

```python
# backend/tests/integration/test_vnc_connection.py
import pytest
import asyncio
import websockets

@pytest.mark.integration
async def test_vnc_websocket_connection(sandbox_container):
    """Test VNC WebSocket connection to sandbox."""
    vnc_url = f"ws://{sandbox_container.ip}:5901"

    async with websockets.connect(vnc_url, subprotocols=["binary"]) as ws:
        # RFB handshake
        version = await ws.recv()
        assert version.startswith(b"RFB ")
```

#### KasmVNC Migration Test

```python
# backend/tests/integration/test_kasmvnc.py
@pytest.mark.integration
async def test_kasmvnc_compatibility(kasmvnc_sandbox):
    """Verify KasmVNC works with existing NoVNC frontend."""
    vnc_url = f"ws://{kasmvnc_sandbox.ip}:5901"

    async with websockets.connect(vnc_url, subprotocols=["binary"]) as ws:
        # Should receive RFB version
        version = await ws.recv()
        assert b"RFB" in version

        # Send client version
        await ws.send(b"RFB 003.008\n")

        # Should receive security types
        security = await ws.recv()
        assert len(security) > 0
```

### Phase 3: End-to-End Tests

#### Frontend VNC E2E Test

```typescript
// frontend/tests/e2e/vnc-viewer.spec.ts
import { test, expect } from '@playwright/test'

test.describe('VNC Viewer', () => {
  test('should connect to sandbox VNC', async ({ page }) => {
    await page.goto('/session/test-session')

    // Wait for VNC viewer to initialize
    const vncContainer = page.locator('[data-testid="vnc-viewer"]')
    await expect(vncContainer).toBeVisible()

    // Wait for connection
    await expect(page.locator('.vnc-connected')).toBeVisible({ timeout: 10000 })
  })

  test('should handle reconnection', async ({ page }) => {
    await page.goto('/session/test-session')

    // Simulate disconnect
    await page.evaluate(() => {
      (window as any).rfb?.disconnect()
    })

    // Should auto-reconnect
    await expect(page.locator('.vnc-connected')).toBeVisible({ timeout: 15000 })
  })
})
```

#### Tavily Tool E2E Test

```python
# backend/tests/e2e/test_tavily_agent_tool.py
@pytest.mark.e2e
async def test_agent_uses_tavily_search(agent_session):
    """Test agent can use Tavily search tool."""
    response = await agent_session.chat(
        "Search the web for the latest Python 3.12 features"
    )

    # Check tool was called
    assert any(
        event.tool == "tavily_search"
        for event in response.events
        if event.type == "tool_call"
    )

    # Check results included
    assert "Python 3.12" in response.final_message
```

### Performance Benchmarks

```python
# backend/tests/performance/test_vnc_performance.py
import pytest
import time
import statistics

@pytest.mark.performance
async def test_vnc_frame_latency(vnc_connection):
    """Measure VNC frame delivery latency."""
    latencies = []

    for _ in range(100):
        start = time.perf_counter()
        frame = await vnc_connection.receive_frame()
        latency = (time.perf_counter() - start) * 1000  # ms
        latencies.append(latency)

    avg_latency = statistics.mean(latencies)
    p99_latency = statistics.quantiles(latencies, n=100)[98]

    print(f"Average latency: {avg_latency:.2f}ms")
    print(f"P99 latency: {p99_latency:.2f}ms")

    # Performance targets
    assert avg_latency < 100  # 100ms average
    assert p99_latency < 200  # 200ms P99
```

### Security Tests

```python
# backend/tests/security/test_vnc_auth.py
@pytest.mark.security
async def test_vnc_requires_valid_signature():
    """VNC endpoint should reject invalid signatures."""
    async with aiohttp.ClientSession() as session:
        # Attempt connection without signature
        with pytest.raises(aiohttp.WSServerHandshakeError):
            async with session.ws_connect(
                "ws://localhost:8000/api/v1/sessions/test/vnc"
            ):
                pass

@pytest.mark.security
async def test_vnc_rejects_expired_signature(expired_token):
    """VNC endpoint should reject expired signatures."""
    url = f"ws://localhost:8000/api/v1/sessions/test/vnc?signature={expired_token}"

    async with aiohttp.ClientSession() as session:
        with pytest.raises(aiohttp.WSServerHandshakeError):
            async with session.ws_connect(url):
                pass
```

---

## Rollback Procedures

### Phase 1 Rollback (Service Integration)

**Risk Level:** Low - No infrastructure changes

```bash
# Rollback Tavily integration
cd backend

# Remove package
pip uninstall tavily-python

# Remove from requirements.txt
sed -i '/tavily-python/d' requirements.txt

# Remove tool files
rm app/infrastructure/external/search/tavily_client.py
rm app/domain/services/tools/web_search_tavily.py

# Restart backend
docker-compose restart backend
```

### Phase 2 Rollback (KasmVNC)

**Risk Level:** Medium - Requires sandbox rebuild

#### Pre-Migration Backup

```bash
# Before migration, tag current image
docker tag pythinker-sandbox:latest pythinker-sandbox:pre-kasmvnc

# Backup Dockerfile
cp sandbox/Dockerfile sandbox/Dockerfile.backup
cp sandbox/supervisord.conf sandbox/supervisord.conf.backup
```

#### Rollback Steps

```bash
# 1. Restore Dockerfile
cd sandbox
cp Dockerfile.backup Dockerfile
cp supervisord.conf.backup supervisord.conf

# 2. Rebuild sandbox image
docker build -t pythinker-sandbox:latest .

# 3. Or use pre-tagged image
docker tag pythinker-sandbox:pre-kasmvnc pythinker-sandbox:latest

# 4. Restart services
docker-compose down
docker-compose up -d

# 5. Verify VNC works
curl -s http://localhost:8000/api/v1/health | jq .vnc_status
```

### Phase 3 Rollback (Selkies-GStreamer)

**Risk Level:** High - Major architecture change

#### Pre-Migration Steps

```bash
# Create full backup
docker-compose down
tar -czvf pythinker-backup-$(date +%Y%m%d).tar.gz \
  docker-compose.yml \
  sandbox/ \
  frontend/src/components/VNCViewer.vue \
  backend/app/interfaces/api/session_routes.py

# Tag all images
docker tag pythinker-backend:latest pythinker-backend:pre-webrtc
docker tag pythinker-sandbox:latest pythinker-sandbox:pre-webrtc
docker tag pythinker-frontend:latest pythinker-frontend:pre-webrtc
```

#### Rollback Steps

```bash
# 1. Stop services
docker-compose down

# 2. Restore from backup
tar -xzvf pythinker-backup-YYYYMMDD.tar.gz

# 3. Restore images
docker tag pythinker-backend:pre-webrtc pythinker-backend:latest
docker tag pythinker-sandbox:pre-webrtc pythinker-sandbox:latest
docker tag pythinker-frontend:pre-webrtc pythinker-frontend:latest

# 4. Remove TURN server if added
docker-compose rm -f coturn

# 5. Start services
docker-compose up -d

# 6. Verify all services
./dev.sh logs -f
```

### Rollback Verification Checklist

```markdown
[ ] Backend API responds: curl http://localhost:8000/api/v1/health
[ ] Frontend loads: curl http://localhost:5173
[ ] VNC connection works: Test in browser
[ ] Agent can execute tools: Run test session
[ ] All tests pass: pytest tests/
[ ] No error logs: docker-compose logs | grep -i error
```

---

## Conclusion & Recommendations

### Summary of Findings

| Component | Recommendation | Priority |
|-----------|---------------|----------|
| RustDesk Migration | **DO NOT PROCEED** | N/A |
| Tavily Integration | Proceed immediately | High |
| Context7 MCP Integration | Proceed immediately | High |
| KasmVNC Upgrade | Recommended | Medium |
| Selkies-GStreamer | Optional, evaluate after KasmVNC | Low |

### Why Not RustDesk

1. **No JavaScript SDK** - Cannot integrate with Vue 3 frontend
2. **No npm package** - No TypeScript types or programmatic control
3. **No native web client** - Flutter-only, requires iframe
4. **Complex infrastructure** - Requires relay servers

### Recommended Path Forward

1. **Immediate (Week 1):** Integrate Tavily and Context7 MCP for enhanced agent capabilities
2. **Short-term (Week 2):** Upgrade to KasmVNC for improved performance while maintaining NoVNC compatibility
3. **Long-term (Month 2+):** Evaluate Selkies-GStreamer if KasmVNC performance is insufficient

### Final Technology Stack

```
Current:     x11vnc + websockify + @novnc/novnc
Recommended: KasmVNC + @novnc/novnc (Phase 2)
Future:      Selkies-GStreamer + custom WebRTC client (Phase 3, if needed)
```

### Budget Considerations

| Service | Free Tier | Estimated Cost |
|---------|-----------|----------------|
| Tavily | 1,000 credits/month | $0 (start free) |
| Context7 | 1,000 calls/month | $0 (start free) |
| KasmVNC | Open source | $0 |
| Selkies | Open source | $0 (compute costs for TURN) |

---

**Report prepared by:** Claude AI Assistant
**Date:** January 27, 2026
**Version:** 1.0
