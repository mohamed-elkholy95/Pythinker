# Timeline Replay System - Implementation Plan

## Overview

This document outlines the complete implementation plan for the Pythinker Timeline Replay System, enabling users to scrub through agent work history, observe actions in real-time, and audit every operation performed during a session.

**Based on:** `findings/pythinker-timeline-prd.md`

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Total Tasks | 69 |
| Backend Tasks | 20 |
| Frontend Tasks | 24 |
| Integration/Testing Tasks | 25 |
| Estimated Total Complexity | Large (multi-sprint effort) |

### Key Infrastructure Already Available
- ✅ Event model with 20+ event types and timestamps
- ✅ MongoDB event persistence per session
- ✅ SSE streaming infrastructure
- ✅ Basic `useTimeline.ts` composable with playback controls
- ✅ `TimelinePlayer.vue` and `TimelineMarker.vue` components
- ✅ Session retrieval API endpoints

---

## Phase 1: Foundation (Backend Core)

### 1.1 Domain Model Extensions

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| BE-1 | Create Timeline Action Domain Model (`timeline.py`) | M | - |
| BE-2 | Create State Snapshot Domain Model (`snapshot.py`) | S | - |
| BE-3 | Extend ToolEvent with action metadata (duration, sequence) | S | BE-1 |
| BE-20 | Add Timeline Configuration Settings to `config.py` | S | - |

### 1.2 Database & Repository Layer

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| BE-4 | Create Snapshot Beanie Document in `documents.py` | S | BE-2 |
| BE-5 | Create Snapshot Repository Interface | S | BE-2 |
| BE-6 | Implement MongoDB Snapshot Repository | M | BE-4, BE-5 |
| BE-7 | Extend Session Repository for timeline queries | M | - |

---

## Phase 2: State Reconstruction (Backend Services)

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| BE-8 | Create Timeline State Reconstruction Service | **L** | BE-6, BE-7 |
| BE-9 | Create File State Reconstructor | M | BE-8 |
| BE-10 | Create Browser State Reconstructor | M | BE-8 |
| BE-11 | Create Terminal State Reconstructor | S | BE-8 |
| BE-12 | Create Snapshot Capture Service | M | BE-6 |
| BE-13 | Integrate Snapshot Capture into AgentTaskRunner | M | BE-3, BE-12 |
| BE-14 | Enhance Tool Execution Tracking (file, browser, shell) | M | BE-13 |

---

## Phase 3: API Layer (Backend)

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| BE-15 | Create Timeline API Schemas (`timeline.py`) | S | BE-1, BE-2 |
| BE-16 | Create Timeline Routes (`timeline_routes.py`) | M | BE-8, BE-15 |
| BE-17 | Create Timeline Application Service | M | BE-8, BE-16 |
| BE-18 | Add Timeline SSE Endpoint for real-time updates | S | BE-16 |
| BE-19 | Register Timeline Dependencies | S | BE-6, BE-8, BE-12, BE-17 |

---

## Phase 4: Frontend Core Infrastructure

### 4.1 Composable Enhancements

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-1 | Enhance `useTimeline` with playback modes (live/replay/paused) | M | - |
| FE-2 | Create `useTimelineState` composable for state reconstruction | **L** | FE-1 |
| FE-3 | Add keyboard shortcuts (`useTimelineKeyboard`) | S | FE-1 |
| FE-5 | Create Frontend Timeline API Client | S | BE-16 |

### 4.2 Timeline Player Enhancements

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-4 | Implement draggable playhead with smooth scrubbing | M | FE-1 |
| FE-6 | Create `TimelineScrubberTooltip` component | S | FE-4 |
| FE-7 | Add mode indicator badge to TimelinePlayer | S | FE-1 |
| FE-8 | Enhance TimelineMarker with hover details | S | - |

---

## Phase 5: Frontend Animation & Replay Components

### 5.1 Typing Animation System

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-9 | Create `useTypingAnimation` composable | M | - |
| FE-10 | Create `TypedText.vue` component | S | FE-9 |
| FE-11 | Create `ReplayMessage.vue` wrapper | M | FE-9, FE-10 |

### 5.2 Visual State Reconstruction

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-12 | Create `ToolStateSnapshot.vue` component | M | FE-2 |
| FE-13 | Create `BrowserReplayView.vue` component | M | FE-12 |
| FE-14 | Create `FileReplayView.vue` component | M | FE-12 |
| FE-15 | Create `ShellReplayView.vue` component | M | FE-12, FE-9 |

---

## Phase 6: Frontend Page Integration

### 6.1 Task Progress Footer

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-16 | Enhance TaskProgressBar for timeline integration | M | FE-2 |
| FE-17 | Create `TimelineProgressFooter.vue` composite | M | FE-4, FE-16 |

### 6.2 Page Integration

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-18 | Integrate timeline replay into ChatPage | **L** | FE-1, FE-2, FE-11, FE-17 |
| FE-19 | Enhance SharePage with improved replay | **L** | FE-11, FE-12, FE-17, FE-18 |
| FE-20 | Add timeline state to URL for deep linking | S | FE-19 |

---

## Phase 7: Frontend Polish & Performance

### 7.1 UI/UX Polish

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-21 | Create `TimelineMinimap.vue` component | M | FE-4 |
| FE-22 | Add transition animations | M | FE-11, FE-12 |
| FE-23 | Add accessibility support (ARIA, keyboard nav) | S | FE-4, FE-7, FE-8 |

### 7.2 Performance

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| FE-24 | Implement event batching for state computation | M | FE-2 |
| FE-25 | Add virtual scrolling for message lists | M | FE-18, FE-19 |

---

## Phase 8: Integration & Caching

### 8.1 Caching Layer

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| INT-6 | Implement IndexedDB Storage Service | **L** | - |
| INT-7 | Create Cache Synchronization Logic | M | INT-6 |
| INT-8 | Add Cache-First Data Loading Strategy | S | INT-6, INT-7 |
| INT-9 | Implement Cache Eviction Policy | S | INT-6 |

### 8.2 Performance Optimization

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| INT-10 | Implement Virtual Scrolling for Action List | **L** | FE-4 |
| INT-11 | Add Snapshot Interval Configuration | M | BE-6 |
| INT-12 | Implement Content Diffing for File Changes | M | BE-6 |
| INT-13 | Optimize State Reconstruction Algorithm | S | INT-11, INT-12 |
| INT-14 | Add Debounced Scrubber Updates | S | - |

---

## Phase 9: Testing

### 9.1 Unit Tests

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| INT-15 | Unit Tests for Timeline Composable | M | FE-1 |
| INT-16 | Unit Tests for IndexedDB Cache Service | M | INT-6, INT-7 |
| INT-17 | Unit Tests for Diff Service | S | INT-12 |

### 9.2 Integration Tests

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| INT-18 | Backend API Integration Tests | M | BE-16 |
| INT-19 | Frontend Component Integration Tests | **L** | INT-10, INT-15 |
| INT-20 | E2E Timeline Replay Tests | **L** | All |
| INT-21 | Performance Benchmarks | M | INT-10, INT-11, INT-13 |

---

## Phase 10: Documentation

| ID | Task | Complexity | Dependencies |
|----|------|------------|--------------|
| INT-22 | API Documentation for Timeline Endpoints | S | BE-16 |
| INT-23 | ADR: SSE vs WebSocket Decision | S | - |
| INT-24 | Developer Guide for Timeline Components | S | INT-10, INT-15 |
| INT-25 | User Guide for Timeline Features | S | INT-20 |

---

## Critical Path

The following tasks are on the critical path and should be prioritized:

```
BE-1 (Timeline Model)
  └─► BE-3 (Extend ToolEvent)
       └─► BE-12 (Snapshot Capture Service)
            └─► BE-13 (Integrate into TaskRunner)
                 └─► BE-8 (State Reconstruction Service) [LARGE]
                      └─► BE-16 (Timeline Routes)
                           └─► FE-5 (API Client)
                                └─► FE-2 (useTimelineState) [LARGE]
                                     └─► FE-18 (ChatPage Integration) [LARGE]
                                          └─► INT-20 (E2E Tests) [LARGE]
```

---

## Acceptance Criteria Mapping

| Criterion | Tasks |
|-----------|-------|
| Timeline scrubber reflects session duration | FE-4, FE-21, INT-15 |
| Dragging playhead reconstructs state | BE-8, FE-2, FE-4, INT-13 |
| Live indicator pulses green | FE-7, FE-22 |
| "Jump to live" within 100ms | FE-1, FE-4, INT-14 |
| Step controls navigate actions | FE-1, FE-3, INT-15 |
| Timestamp updates in real-time | FE-4, BE-18 |
| Task progress reflects steps | FE-16, FE-17 |
| Syntax-highlighted file content | FE-14, INT-12 |
| Browser screenshots display | FE-13, BE-10 |
| Terminal output scrolls correctly | FE-15, BE-11 |
| Mobile responsive design | FE-23, INT-19 |
| Session export produces shareable format | BE-16, FE-5, INT-18 |

---

## File Structure (New Files)

### Backend
```
backend/app/
├── domain/
│   ├── models/
│   │   ├── timeline.py          # BE-1
│   │   └── snapshot.py          # BE-2
│   ├── repositories/
│   │   └── snapshot_repository.py  # BE-5
│   └── services/
│       ├── timeline_service.py     # BE-8
│       ├── snapshot_capture_service.py  # BE-12
│       ├── diff_service.py         # INT-12
│       └── reconstructors/
│           ├── file_reconstructor.py    # BE-9
│           ├── browser_reconstructor.py # BE-10
│           └── terminal_reconstructor.py # BE-11
├── infrastructure/
│   └── repositories/
│       └── mongo_snapshot_repository.py  # BE-6
├── application/
│   └── services/
│       └── timeline_application_service.py  # BE-17
└── interfaces/
    ├── api/
    │   └── timeline_routes.py    # BE-16
    └── schemas/
        └── timeline.py           # BE-15
```

### Frontend
```
frontend/src/
├── composables/
│   ├── useTimelineState.ts      # FE-2
│   ├── useTimelineKeyboard.ts   # FE-3
│   └── useTypingAnimation.ts    # FE-9
├── components/timeline/
│   ├── TimelineScrubberTooltip.vue  # FE-6
│   ├── TypedText.vue            # FE-10
│   ├── ReplayMessage.vue        # FE-11
│   ├── ToolStateSnapshot.vue    # FE-12
│   ├── BrowserReplayView.vue    # FE-13
│   ├── FileReplayView.vue       # FE-14
│   ├── ShellReplayView.vue      # FE-15
│   ├── TimelineProgressFooter.vue  # FE-17
│   ├── TimelineMinimap.vue      # FE-21
│   ├── VirtualTimelineList.vue  # INT-10
│   └── transitions.ts           # FE-22
├── services/
│   └── timelineCache.ts         # INT-6
├── types/
│   └── timeline.types.ts        # INT-6
└── utils/
    └── diff.ts                  # INT-12
```

---

## Recommended Sprint Planning

### Sprint 1: Foundation
- BE-1, BE-2, BE-3, BE-20 (Domain models + config)
- BE-4, BE-5, BE-6, BE-7 (Repository layer)
- FE-1, FE-3 (Core composable enhancements)

### Sprint 2: Recording & API
- BE-12, BE-13, BE-14 (Snapshot capture)
- BE-15, BE-16, BE-17, BE-18, BE-19 (API layer)
- FE-5 (API client)

### Sprint 3: State Reconstruction
- BE-8, BE-9, BE-10, BE-11 (Reconstruction services)
- FE-2 (useTimelineState)
- INT-11, INT-12, INT-13 (Performance)

### Sprint 4: Frontend UI
- FE-4, FE-6, FE-7, FE-8 (Timeline player)
- FE-9, FE-10, FE-11 (Typing animation)
- FE-12, FE-13, FE-14, FE-15 (Replay views)

### Sprint 5: Integration
- FE-16, FE-17 (Progress footer)
- FE-18, FE-19, FE-20 (Page integration)
- INT-6, INT-7, INT-8, INT-9 (Caching)

### Sprint 6: Polish & Testing
- FE-21, FE-22, FE-23, FE-24, FE-25 (UI polish)
- INT-10, INT-14 (Performance)
- INT-15 through INT-21 (Testing)
- INT-22 through INT-25 (Documentation)

---

## Notes

1. **Vue 3 vs React**: The PRD specifies React components but pythinker uses Vue 3. All frontend tasks are designed for Vue 3 with Composition API.

2. **SSE vs WebSocket**: Current system uses SSE. Recommend enhancing SSE rather than adding WebSocket complexity (see INT-23 for decision documentation).

3. **Existing Infrastructure**: Leverage existing `useTimeline.ts`, `TimelinePlayer.vue`, and `TimelineMarker.vue` rather than rebuilding.

4. **Backward Compatibility**: Ensure existing session functionality remains intact during implementation.
