# Sandbox and agent cursor

## Single source of truth

**Canonical cursor artwork:** `frontend/src/assets/cursors/apple_cursor-main/svg/`

**Chroma → display mapping (web + docs):** `frontend/src/assets/cursors/apple_cursor-main/chroma-render.json` (`macOS.colors`). The Vite plugin `recolorAppleCursorSvgForWeb` in `frontend/vite.config.ts` reads that file so the Konva overlay stays in sync with the JSON.

Do not maintain a second copy under `sandbox/` — a full upstream `apple_cursor` checkout is only needed locally if you build **X11 cursor binaries** with `cbmp`/`ctgen` (see below).

## What you see in the UI

Live browser view uses **CDP `Page.startScreencast`**, which streams the Chrome window. Pythinker no longer draws a separate moving agent cursor on top during autonomous browsing.

Passive autonomous browsing hides the local viewer cursor and avoids browser-side cursor overlays. Manual takeover still uses the normal pointer cursor presented by the viewer/runtime.

## Why the cursor looked green and blue

The SVG pack uses chroma colors `#00FF00` and `#0000FF` so tooling can substitute final colors. Importing those SVGs **directly** as image URLs showed the chroma colors in the browser until the Vite plugin applied the same rules as `chroma-render.json`.

## Linux cursor inside the sandbox (optional)

The runtime image installs **`dmz-cursor-theme`** and `supervisord.conf` sets:

- `XCURSOR_THEME=DMZ-White`
- `XCURSOR_SIZE=24`

for Openbox and Chrome. That affects the **real** pointer on `:99` (visible in X11/VNC capture mode), not the Konva overlay.

To install a **macOS-style X cursor theme** built from the same SVGs:

1. Clone [ful1e5/apple_cursor](https://github.com/ful1e5/apple_cursor) (or use its `package.json` / `build.sh` layout).
2. Point `cbmp` at this repo’s SVG directory: `frontend/src/assets/cursors/apple_cursor-main/svg` (align `render.json` / chroma rules with `chroma-render.json`’s `macOS` entry).
3. Run `ctgen` to produce `themes/macOS`, copy into the sandbox image under e.g. `/usr/share/icons/macOS`.
4. Set `XCURSOR_THEME=macOS` (and optionally `XCURSOR_SIZE=32`) in `sandbox/supervisord.conf` for `openbox` and `chrome_cdp_only`, then rebuild the sandbox image.

## Coordinate accuracy

The CSS pointer hotspot used by the viewer is defined in `frontend/src/utils/appleCursorStyle.ts`. If the takeover pointer looks offset, tune the hotspot constants there for the scaled artwork.
