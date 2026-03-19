# Sandbox and agent cursor

## What you see in the UI

Live browser view uses **CDP `Page.startScreencast`**, which streams the Chrome window (often without a crisp hardware pointer in the JPEG). Pythinker draws a **separate agent cursor** on top (Konva overlay) driven by browser tool events (`useAgentCursor` + `agentCursorAssets.ts`).

That overlay is **not** the X11 cursor inside the container; it is a second layer aligned to sandbox coordinates (1280×1024).

## Why the cursor looked green and blue

The SVG pack under `frontend/src/assets/cursors/apple_cursor-main/svg/` is the **authoring** format from the [apple_cursor](https://github.com/ful1e5/apple_cursor) workflow: fills and strokes use chroma colors `#00FF00` and `#0000FF` so `cbmp` can substitute real colors when generating bitmaps (see `sandbox/apple_cursor/render.json`).

Importing those SVGs **directly** as image URLs showed the chroma colors in the browser. The Vite plugin `recolorAppleCursorSvgForWeb` in `frontend/vite.config.ts` applies the same replacements as the `macOS` entry in `render.json` so the overlay matches the intended black/white pointer.

## Linux cursor inside the sandbox (optional)

The runtime image installs **`dmz-cursor-theme`** and `supervisord.conf` sets:

- `XCURSOR_THEME=DMZ-White`
- `XCURSOR_SIZE=24`

for Openbox and Chrome. That affects the **real** pointer on `:99` (visible in X11/VNC capture mode or if you RDP/VNC in), not the Konva overlay.

To use the built **macOS-style X cursor theme** from `sandbox/apple_cursor/`:

1. On a machine with [cbmp](https://www.npmjs.com/package/cbmp) and [ctgen](https://github.com/ful1e5/apple_cursor#dependencies) installed, run in `sandbox/apple_cursor/`: `yarn install && yarn generate` (see `package.json` / `build.sh`).
2. Copy the generated `themes/macOS` directory into the image under e.g. `/usr/share/icons/macOS` (and an `index.theme` if required by your ctgen output).
3. Set `XCURSOR_THEME=macOS` (and optionally `XCURSOR_SIZE=32`) in `sandbox/supervisord.conf` for the `openbox` and `chrome_cdp_only` programs.

Rebuild the sandbox image after changing the theme.

## Coordinate accuracy

Overlay position comes from tool args (`x` / `y` or `coordinate_x` / `coordinate_y`). If the pointer looks offset after fixing colors, tune `CURSOR_HOTSPOT_X` / `CURSOR_HOTSPOT_Y` and `CURSOR_RENDER_SIZE` in `useAgentCursor.ts` for the scaled 256×256 artwork.
