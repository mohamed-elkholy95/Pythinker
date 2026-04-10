# Chat Page Hierarchy And Sanitization Design

**Date:** 2026-04-04
**Status:** Approved (post spec-review)
**Scope:** Frontend chat timeline rendering, nested activity hierarchy, user-facing text sanitization

## Summary

Redesign the chat page execution view to emphasize clear parent/child hierarchy. Top-level steps should be the primary visual unit, while skill loads, searches, and short execution updates render as nested child activity inside the parent step instead of competing as peer timeline rows.

At the same time, formalize a sanitize-or-drop policy for leaked internal metadata. Raw backend artifacts such as `[Previously called info_search_web]`, leaked tool-call wrappers, and blank assistant placeholders must never render in the visible chat transcript.

This spec is intentionally narrow. It covers timeline hierarchy, nested activity presentation, and sanitization rules for the execution view. It does not redesign the broader page shell, composer, or tool panel.

## Problems In The Current UI

### 1. Weak Parent/Child Hierarchy

The current execution transcript mixes top-level steps, skill loads, tool rows, and assistant narration in a way that makes sibling and child relationships ambiguous. Even when items are technically nested, the visual treatment still makes them feel like separate peer rows.

### 2. Repeated Chrome

`Pythinker is working`, standalone skill pills, step dots, and floating thinking states all introduce repeated chrome. This increases noise without making state transitions clearer.

### 3. Internal Metadata Leakage

The frontend still allows internal orchestration text to leak into visible UI surfaces. The most visible example is bare markers such as `[Previously called info_search_web]`, but the broader class includes leaked tool wrappers and placeholder assistant rows with no useful text.

### 4. Running-State Ambiguity

The current view does not clearly distinguish:
- top-level execution progress
- child activity within the current step
- free-floating assistant narration
- fallback thinking state when no visible step exists

## Goals

1. Make parent steps the dominant unit of hierarchy.
2. Render skill loads, search actions, and short updates as clearly subordinate child activity.
3. Remove raw internal metadata from the visible transcript.
4. Keep active execution readable without stacking duplicate branding or status chrome.
5. Preserve existing execution behavior and event flow as much as possible.

## Non-Goals

1. Replacing the entire chat page layout.
2. Redesigning the composer, left navigation, or report cards.
3. Changing backend SSE schema or event semantics.
4. Moving execution details into a separate panel.

## Users And Primary Usage

This redesign serves users watching an active task execute in the main chat timeline. The core use cases are:

1. Understand what major step the agent is currently on.
2. Glance at subordinate activity without losing the high-level structure.
3. Expand a step to inspect what happened inside it.
4. Never see raw implementation details that do not help them understand progress.

## Design Direction

### Recommended Interaction Model

Use **grouped parent cards with child activity inside**.

Why this direction:
- it makes parent/child hierarchy explicit
- it reduces flat timeline clutter
- it gives a single container for nested execution details
- it gives sanitization a clear place in the render pipeline

## Parent Step Card Anatomy

Each top-level execution step becomes one stable parent block.

### Structure

- Left: one status node for the parent step only
- Center: parent title with the strongest contrast in the execution area
- Right: timestamp and expand/collapse chevron
- Below: nested child activity container

### Parent Header Rules

- Parent title uses stronger weight than any child row.
- Parent status node is the only large step-level node in the block.
- Parent rows get more vertical separation than child activity.
- The chevron controls expansion of the nested child activity container.

### Parent States

- `pending`: visible only where pending steps are already part of the current experience, collapsed by default, and lowest emphasis among visible parent states
- `started`: treated the same as `running` for active styling and default expansion behavior
- `running`: active emphasis and expanded by default
- `completed`: de-emphasized active treatment, collapsed unless user reopened it
- `failed` / `blocked`: error styling, preserve child activity for diagnosis
- `skipped`: completed-style de-emphasis while preserving skipped semantics in any existing icon or label treatment

### Collapsed Preview

Collapsed parent rows should summarize child activity instead of echoing raw child text. Examples:

- `2 skills loaded, 3 searches run`
- `3 searches completed`
- `Loaded research skills and compared retailer pricing`

## Nested Child Activity Anatomy

Child activity must read as subordinate to the parent step.

### Child Activity Types

- skill loads
- search actions
- short inline progress updates
- tool-result summaries when they are user-meaningful

### Child Row Structure

Each child row contains:
- a small icon
- one compact label
- optional light metadata at the trailing edge

### Child Row Rules

- No large step-level dots for child rows.
- Child rows sit inside a shared nested activity container.
- Child rows use smaller type and lower contrast than the parent title.
- Child rows use tighter spacing than parent rows.
- Child rows should feel like entries in one grouped stream, not separate standalone cards.

### Visual Grouping

Use **one inset grouped container with a subtle left rail** as the primary child-activity pattern.

Why this pattern:
- it is the clearest visual expression of parent/child hierarchy
- it avoids making child rows look like peer timeline steps
- it supports mixed child row types without requiring separate timeline nodes
- it keeps collapsed and expanded layouts structurally consistent

Required characteristics:
- the child activity container is visually inset from the parent header
- the container includes one subtle left rail
- child rows stack within that single container
- repeated skill loads remain inside that same container rather than creating standalone sub-groups

## Working Block For Skill Loading

The `Pythinker is working` section is a special grouped parent activity block.

### Required Behavior

- Render the heading once.
- Append consecutive skill loads underneath it as child activity.
- Keep repeated skill loads visually connected until the workflow advances.
- Do not show repeated assistant branding around that block.

### Required Outcome

Users should read:
- one work header
- several nested child activity rows

They should not read:
- several unrelated standalone pills
- repeated `Pythinker` brand chrome
- multiple visually competing step headers for the same work group

## Thinking State Rules

### Anchored Thinking

If there is a visible running parent step, thinking state belongs inside that parent block.

### Floating Thinking

Only show the standalone floating thinking indicator when:
- the task is active
- no tool call is active
- no running step is visible to anchor it

### Branding Rule

The floating thinking state must not introduce a separate assistant brand row or `Pythinker` logo above it.

## Sanitization Rules

Only render user-meaningful text in the chat timeline.

### Sanitize Or Drop Policy

For assistant placeholders, inline message tools, child activity rows, collapsed previews, and similar lightweight execution text:

1. sanitize internal markers
2. if meaningful text remains, render it
3. if nothing meaningful remains, drop the row entirely

### Internal Markers That Must Never Render

- `[Previously called ...]`
- leaked tool-call wrappers
- leaked function-call wrappers
- internal system-note orchestration markers
- blank assistant placeholders after cleanup

### Priority Order For Child Activity Labels

When deriving a user-facing label for a child row:

1. clean `display_command`
2. normalized tool label from repo tool metadata
3. short safe summary derived from arguments
4. drop the row if none of the above produce user-meaningful text

### Sanitization Boundaries

This sanitization policy applies to:
- assistant placeholder rendering in the transcript
- inline child activity labels
- inline message tool text
- collapsed previews
- replay/session-history transcript reconstruction
- shared transcript rendering where the same sanitized visible text is reused

This spec does not require redesigning the full expanded tool panel content beyond existing tool-panel behavior.

## Implementation Boundaries

### Likely Files

- `frontend/src/pages/ChatPage.vue`
  - transcript event intake
  - transcript grouping decisions
  - floating thinking fallback behavior
- `frontend/src/pages/SharePage.vue`
  - shared-session transcript rendering parity for sanitized execution text
- `frontend/src/components/ChatMessage.vue`
  - parent step rendering
  - child activity rendering
  - grouped skill-load presentation
- `frontend/src/components/ToolUse.vue`
  - compact activity chip/row labeling if child rows still reuse tool rendering
- `frontend/src/utils/assistantMessageLayout.ts`
  - assistant placeholder renderability rules
- `frontend/src/utils/messageSanitizer.ts`
  - shared cleanup helpers for leaked markers
- `frontend/src/utils/sessionHistory.ts`
  - replay/session-history normalization so completed sessions do not reintroduce leaked markers
- `frontend/src/components/report/reportContentNormalizer.ts`
  - existing `Previously called` normalization can be referenced or shared if helpful

### Preferred Change Strategy

1. centralize shared sanitize-or-drop helpers
2. normalize child-row labels before render
3. enforce parent/child grouping rules in the transcript
4. tune spacing, connectors, and visual grouping for child activity
5. improve collapsed preview summaries where needed

### Architectural Constraint

Do not rewrite the backend event model to achieve this. The redesign should be implemented in the current frontend transcript pipeline unless a small supporting backend fix is strictly necessary.

Replay and share views must reach the same sanitized visible output either by reusing shared chat rendering/sanitization paths or by explicitly applying the same cleanup rules in their transcript-preparation utilities.

## Acceptance Criteria

### Visual Acceptance

- parent steps are visually dominant over nested activity
- child activity is clearly subordinate to its parent
- consecutive skill loads appear under one parent work block
- no extra assistant branding appears above floating thinking state
- expanded execution view no longer feels like a flat stack of peer rows

### Content Acceptance

- `[Previously called info_search_web]` does not render anywhere in the visible chat timeline
- blank assistant placeholders do not render
- child rows do not display leaked raw orchestration metadata
- collapsed previews summarize child activity instead of exposing raw internal strings

### Behavioral Acceptance

- the running step expands by default
- child activity appends in place under its parent
- active work remains readable while tools update
- sanitization does not remove legitimate user-facing summaries

## Verification Requirements

### Required Regression Coverage

- sanitizer test for `[Previously called ...]`
- test that placeholder assistant rows with no visible content do not render
- test that repeated skill loads share one parent work header
- test that sanitized empty child rows are dropped
- test that child activity labels prefer clean user-facing text over raw control strings

### Manual Verification Targets

- active task with consecutive skill loads
- active step with nested search actions
- fallback floating thinking state with no running step
- completed transcript replay for a session that previously showed `[Previously called ...]`

## Risks And Edge Cases

### Risk: Over-Sanitizing Legitimate Text

If cleanup rules are too broad, the frontend could hide useful content. Sanitization must target clearly internal markers and only drop text when the remaining content is empty or non-user-facing.

### Risk: Mixed Message Ordering

Tool and assistant events can arrive in different orders. Grouping rules must tolerate:
- skill tool events before step transitions
- assistant placeholder events that contain no renderable text
- tool rows that later become nested under a step

### Risk: Visual Over-Correction

If child rows are too muted, the user may lose useful activity detail. The redesign should lower emphasis without hiding the work.

## Out Of Scope Follow-Ups

These may be worth doing later but are not part of this spec:

- broader page-shell redesign for the chat page
- new summary strip above the transcript
- deeper tool panel redesign
- richer step-preview aggregation logic for every tool family

## Recommendation

Proceed with a frontend-only implementation centered on:

1. grouped parent cards with child activity inside
2. strict sanitize-or-drop handling for leaked internal markers
3. one stable work-group header for consecutive skill loads
4. anchored thinking state inside the active parent step whenever possible
