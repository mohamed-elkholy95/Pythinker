# Thinking Indicator Visual Refresh (Warm/Loading)

## Goal
Enhance the existing thinking indicator to read as a warm, active loading state. Keep the same component API. Rays should be black, even in dark mode. Increase the indicator size slightly across all instances.

## Scope
- Frontend only.
- CSS/visual changes localized to the indicator component (including small SVG additions for rays), plus a small size override update where the indicator is explicitly sized.
- No behavioral, layout, or data-flow changes.

## Proposed Approach (Selected)
**Color/animation retune** of the existing `ThinkingIndicator`:
- Warm, lighter bulb gradient (light amber/gold) with slightly higher opacity.
- Outline/filament tones adjusted for clarity against the warmer fill.
- Rays set to solid black with a smooth, rhythmic pulse to read as loading.
- Add additional short horizontal rays that progress from left to right (staggered pulse).
- Slightly increase the lamp size for better readability across all uses.
- Energy ring and scan-line remain but are slightly de-emphasized.
- Dark mode keeps rays black per requirement.

## Architecture / Components
- Target component: `frontend/src/components/ui/ThinkingIndicator.vue`.
- No new components or props.
- Minor SVG additions for the new left-to-right rays.

## Data Flow
Unchanged. The component remains presentational and controlled solely by `showText`.

## Error Handling
Not applicable; static rendering only. Primary risk is visual contrast/regression.

## Testing / Verification
- Manual visual check in light and dark themes.
- Verify `showText=true` and `showText=false` in:
  - Chat header indicator
  - Planning progress indicator
  - Streaming thinking indicator
- Confirm rays read as a loading pulse and bulb remains warm/light.

## Out of Scope
- Any API, state, or logic changes.
- New animations outside the indicator.
- Any refactor of `ChatPage.vue` or message rendering.
