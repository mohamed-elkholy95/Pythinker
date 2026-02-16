# Automatic Browser Behavior

This document summarizes the current browser behavior used by the agent.

## Current Behavior

`browser_navigate` is optimized to reduce extra tool calls:

- Navigate to URL
- Trigger lightweight auto-scroll/loading behavior
- Return usable page state for the next decision step

The objective is fewer round-trips and faster response while preserving reliability.

## Expected Outcomes

- Reduced repeated `navigate/view/scroll/view` cycles
- Faster first meaningful answer
- More consistent live rendering in the computer panel

## Live Visibility

Browser actions are visible in the computer panel through:

- CDP screencast path (`LiveViewer` -> `SandboxViewer`)

## Operational Notes

- Keep browser flows deterministic where possible.
- Prefer robust selectors and clear navigation goals.
- Avoid unnecessary extractions when current state is sufficient.

## Verification

Use `docs/guides/TEST_GUIDE.md` for end-to-end validation of:

- CDP live rendering
- Replay behavior
