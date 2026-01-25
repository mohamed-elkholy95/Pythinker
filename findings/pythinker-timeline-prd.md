# Pythinker Computer: Timeline Replay System

## Feature Specification & Implementation Prompt

---

## 1. Executive Summary

Build a comprehensive **Timeline Replay System** for Pythinker Computer that provides full transparency into agent operations. This system enables users to scrub through the agent's work history, observe actions in real-time, and audit every operation performed during a session.

---

## 2. Core Feature Requirements

### 2.1 Timeline Scrubber Component

**Primary Elements:**
- Horizontal timeline bar with draggable playhead
- Real-time position indicator ("● live" badge)
- Timestamp display (format: `MM/DD/YYYY, HH:MM:SS AM/PM`)
- Progress visualization showing completed vs. remaining session time
- Step navigation controls (previous/next action buttons)

**Interaction Modes:**
- **Live Mode**: Real-time streaming of agent actions
- **Replay Mode**: Historical playback of completed actions
- **Paused Mode**: Frozen state for detailed inspection

### 2.2 Action Recording System

**Captured Events:**
```typescript
interface AgentAction {
  id: string;
  timestamp: Date;
  actionType: ActionType;
  tool: string;
  input: Record<string, any>;
  output: Record<string, any>;
  duration: number; // milliseconds
  status: 'pending' | 'executing' | 'completed' | 'failed';
  metadata: {
    fileChanges?: FileChange[];
    browserActions?: BrowserAction[];
    terminalCommands?: TerminalCommand[];
    reasoning?: string;
  };
}

enum ActionType {
  FILE_CREATE = 'file_create',
  FILE_EDIT = 'file_edit',
  FILE_DELETE = 'file_delete',
  BROWSER_NAVIGATE = 'browser_navigate',
  BROWSER_INTERACT = 'browser_interact',
  TERMINAL_EXECUTE = 'terminal_execute',
  CODE_EXECUTE = 'code_execute',
  API_CALL = 'api_call',
  TOOL_USE = 'tool_use',
  THINKING = 'thinking',
  PLANNING = 'planning'
}
```

### 2.3 Visual State Reconstruction

The system must reconstruct visual state at any point in the timeline:
- File system state (which files existed, their contents)
- Browser state (screenshots, DOM snapshots)
- Terminal output history
- Editor state with syntax highlighting
- Agent reasoning/thinking display

---

## 3. UI/UX Specifications

### 3.1 Header Bar Component

```
┌─────────────────────────────────────────────────────────────┐
│ 🖥️ Pythinker's Computer                          [−] [□] [×]│
├─────────────────────────────────────────────────────────────┤
│ ✏️ Agent is using Edit... │ Creating file src/components... │
└─────────────────────────────────────────────────────────────┘
```

**Status Indicators:**
- Current tool icon + "Agent is using [Tool]..."
- Active file/resource being modified
- Window controls (minimize, maximize, close)

### 3.2 Content Viewport

```
┌─────────────────────────────────────────────────────────────┐
│                    [FILENAME.ext]                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  # File Content Display                                     │
│                                                             │
│  - Syntax highlighted code/markdown                         │
│  - Real-time typing animation in live mode                  │
│  - Diff highlighting for edits                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Timeline Control Bar

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  │◁  ▷│     ════════════════●══════════     ● live         │
│                                                             │
│         ▷ Jump to live                                      │
│         1/24/2026, 9:28:43 PM                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Control Elements:**
| Element | Function |
|---------|----------|
| `│◁` | Step to previous action |
| `▷│` | Step to next action |
| `═══●═══` | Draggable timeline scrubber |
| `● live` | Live status indicator (green when live) |
| `▷ Jump to live` | Button to return to real-time |
| Timestamp | Current playhead position time |

### 3.4 Task Progress Footer

```
┌─────────────────────────────────────────────────────────────┐
│ ✓ Current task description                        4 / 6  ∧ │
└─────────────────────────────────────────────────────────────┘
```

- Checkmark indicates completed steps
- Progress counter (current/total)
- Expandable task list (∧ toggle)

---

## 4. Technical Architecture

### 4.1 State Management

```typescript
interface TimelineState {
  session: {
    id: string;
    startTime: Date;
    endTime?: Date;
    status: 'active' | 'completed' | 'paused';
  };
  actions: AgentAction[];
  currentIndex: number;
  isLive: boolean;
  playbackSpeed: number;
  viewport: {
    type: 'file' | 'browser' | 'terminal' | 'split';
    activeResource: string;
    content: string;
  };
  tasks: {
    description: string;
    completed: boolean;
  }[];
}
```

### 4.2 Event Streaming Architecture

```
┌──────────────┐    WebSocket    ┌──────────────┐
│   Agent      │ ──────────────► │   Timeline   │
│   Runtime    │                 │   Service    │
└──────────────┘                 └──────────────┘
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │   IndexedDB  │
                                 │   Storage    │
                                 └──────────────┘
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │   React UI   │
                                 │   Component  │
                                 └──────────────┘
```

### 4.3 Database Schema

```sql
-- Sessions table
CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  started_at TIMESTAMP NOT NULL,
  ended_at TIMESTAMP,
  status VARCHAR(20) NOT NULL,
  task_description TEXT,
  metadata JSONB
);

-- Actions table
CREATE TABLE actions (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  sequence_number INTEGER NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  action_type VARCHAR(50) NOT NULL,
  tool_name VARCHAR(100),
  input JSONB,
  output JSONB,
  duration_ms INTEGER,
  status VARCHAR(20) NOT NULL,
  metadata JSONB,
  UNIQUE(session_id, sequence_number)
);

-- Snapshots table (for state reconstruction)
CREATE TABLE snapshots (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  action_id UUID REFERENCES actions(id),
  snapshot_type VARCHAR(50) NOT NULL,
  resource_path TEXT,
  content TEXT,
  created_at TIMESTAMP NOT NULL
);

-- Indexes
CREATE INDEX idx_actions_session ON actions(session_id, sequence_number);
CREATE INDEX idx_actions_timestamp ON actions(timestamp);
CREATE INDEX idx_snapshots_session ON snapshots(session_id);
```

---

## 5. Component Implementation

### 5.1 React Component Structure

```
src/components/timeline/
├── TimelineContainer.tsx       # Main wrapper component
├── TimelineHeader.tsx          # Status bar with tool indicator
├── TimelineViewport.tsx        # Content display area
├── TimelineScrubber.tsx        # Timeline control bar
├── TimelineControls.tsx        # Navigation buttons
├── TimelineProgress.tsx        # Task progress footer
├── hooks/
│   ├── useTimeline.ts          # Timeline state management
│   ├── usePlayback.ts          # Playback controls
│   ├── useActionStream.ts      # WebSocket connection
│   └── useStateReconstruction.ts
├── utils/
│   ├── actionSerializer.ts     # Action serialization
│   ├── stateReconstructor.ts   # State at point-in-time
│   └── timeFormatter.ts        # Timestamp formatting
└── types/
    └── timeline.types.ts       # TypeScript definitions
```

### 5.2 Core Hook Implementation

```typescript
// useTimeline.ts
export function useTimeline(sessionId: string) {
  const [state, dispatch] = useReducer(timelineReducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);

  // Connect to action stream
  useEffect(() => {
    wsRef.current = new WebSocket(
      `${WS_URL}/sessions/${sessionId}/stream`
    );
    
    wsRef.current.onmessage = (event) => {
      const action = JSON.parse(event.data);
      dispatch({ type: 'ADD_ACTION', payload: action });
    };

    return () => wsRef.current?.close();
  }, [sessionId]);

  // Playback controls
  const jumpToLive = useCallback(() => {
    dispatch({ type: 'JUMP_TO_LIVE' });
  }, []);

  const seekTo = useCallback((index: number) => {
    dispatch({ type: 'SEEK_TO', payload: index });
  }, []);

  const stepForward = useCallback(() => {
    dispatch({ type: 'STEP_FORWARD' });
  }, []);

  const stepBackward = useCallback(() => {
    dispatch({ type: 'STEP_BACKWARD' });
  }, []);

  return {
    ...state,
    jumpToLive,
    seekTo,
    stepForward,
    stepBackward,
  };
}
```

---

## 6. Animation & Visual Effects

### 6.1 Live Typing Effect

```typescript
// Simulate real-time typing for file edits
const useTypingAnimation = (content: string, isLive: boolean) => {
  const [displayed, setDisplayed] = useState('');
  
  useEffect(() => {
    if (!isLive) {
      setDisplayed(content);
      return;
    }
    
    let index = 0;
    const interval = setInterval(() => {
      if (index < content.length) {
        setDisplayed(content.slice(0, index + 1));
        index++;
      } else {
        clearInterval(interval);
      }
    }, 15); // Typing speed
    
    return () => clearInterval(interval);
  }, [content, isLive]);
  
  return displayed;
};
```

### 6.2 Timeline Scrubber Styling

```css
.timeline-scrubber {
  --track-height: 4px;
  --thumb-size: 14px;
  --primary-color: #3b82f6;
  --live-color: #22c55e;
}

.timeline-track {
  height: var(--track-height);
  background: linear-gradient(
    to right,
    var(--primary-color) var(--progress),
    #e5e7eb var(--progress)
  );
  border-radius: 2px;
  cursor: pointer;
}

.timeline-thumb {
  width: var(--thumb-size);
  height: var(--thumb-size);
  background: var(--primary-color);
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.1s ease;
}

.timeline-thumb:hover {
  transform: scale(1.2);
}

.live-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--live-color);
  font-weight: 500;
}

.live-indicator::before {
  content: '';
  width: 8px;
  height: 8px;
  background: var(--live-color);
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

---

## 7. API Endpoints

### 7.1 REST Endpoints

```typescript
// GET /api/sessions/:sessionId
// Returns session metadata and action count

// GET /api/sessions/:sessionId/actions
// Query params: ?from=0&to=100&includeSnapshots=true
// Returns paginated actions with optional snapshots

// GET /api/sessions/:sessionId/actions/:actionId
// Returns single action with full details

// GET /api/sessions/:sessionId/state?at=<timestamp>
// Returns reconstructed state at specific timestamp

// POST /api/sessions/:sessionId/export
// Exports full session for sharing/archival
```

### 7.2 WebSocket Events

```typescript
// Client -> Server
interface ClientMessage {
  type: 'subscribe' | 'unsubscribe' | 'request_state';
  sessionId: string;
  timestamp?: string;
}

// Server -> Client
interface ServerMessage {
  type: 'action' | 'state_update' | 'session_end' | 'error';
  payload: AgentAction | TimelineState | Error;
}
```

---

## 8. Performance Optimizations

### 8.1 Virtual Scrolling for Actions

For sessions with thousands of actions, implement virtual scrolling to render only visible timeline segments.

### 8.2 Snapshot Intervals

Store full state snapshots every N actions (e.g., 50) to enable fast reconstruction without replaying all actions.

### 8.3 Content Diffing

Store only diffs for file changes rather than full content to reduce storage and transmission costs.

### 8.4 IndexedDB Caching

Cache session data in IndexedDB for offline replay and faster subsequent loads.

---

## 9. Acceptance Criteria

- [ ] Timeline scrubber accurately reflects session duration
- [ ] Dragging playhead reconstructs state at that point
- [ ] Live indicator pulses green during active sessions
- [ ] "Jump to live" returns to real-time view within 100ms
- [ ] Step controls navigate between individual actions
- [ ] Timestamp updates in real-time during live mode
- [ ] Task progress reflects completed workflow steps
- [ ] File content displays with syntax highlighting
- [ ] Browser screenshots display at appropriate resolution
- [ ] Terminal output scrolls to relevant position
- [ ] Mobile responsive design functions correctly
- [ ] Session export produces shareable format

---

## 10. Future Enhancements

- **Branching Timelines**: Visualize alternate paths when agent retries
- **Collaborative Viewing**: Multiple users watch same session
- **Annotation System**: Add comments at specific timestamps
- **Playback Speed Control**: 0.5x, 1x, 2x, 4x speeds
- **Action Filtering**: Show only specific action types
- **Search Within Session**: Find specific content/actions
- **Session Comparison**: Side-by-side session comparison
- **Analytics Dashboard**: Session metrics and patterns
