# Plotly Migration Plan

## Objective

Replace the current comparison chart SVG pipeline with a full Plotly-based chart pipeline that runs in the sandbox, saves chart artifacts as task files, and makes those files visible and usable in the task file list.

## Scope

- Remove custom SVG chart generation for report comparisons.
- Generate Plotly charts inside sandbox execution.
- Save both interactive and preview artifacts into task files.
- Ensure chart files appear in report attachments and "All files in this task".
- Update UI behavior for interactive chart files.
- Add tests for backend, storage sync, and frontend behavior.

## Non-Goals

- No legacy fallback to old SVG renderer after migration.
- No partial migration where only some report paths use Plotly.
- No external SaaS chart dependency.

## Current-State Findings

1. Current chart generation is local backend SVG generation (`comparison_chart_generator.py`).
2. Chart attachments are created with SVG MIME at generation time.
3. Attachment sync path **drops MIME** when uploading to storage — `_sync_file_to_storage()` in `agent_task_runner.py` calls `upload_file(file_data, file_name, self._user_id)` without passing `content_type`, even though `GridFSFileStorage.upload_file()` accepts it. This is a confirmed bug affecting all file types.
4. File preview currently treats `.html` as code, not as interactive chart content.
5. Sandbox includes Chromium (xtradeb/apps PPA) and Plotly 6.3.1; **Kaleido is NOT installed** and must be added.
6. Kaleido v1 no longer bundles Chrome — it requires a system Chromium discoverable via `BROWSER_PATH` env var or standard paths.
7. The agent can also generate ad-hoc charts by writing Python scripts directly in the sandbox via `shell_exec`, since Plotly/matplotlib/seaborn are all pre-installed.

## Target State

For each comparison report event:

- `comparison-chart-<report_id>.html` is generated in sandbox (interactive Plotly).
- `comparison-chart-<report_id>.png` is generated in sandbox (preview image).
- Both files are attached to the report event and synced to storage with correct MIME.
- Both files are visible in task file list.
- `.png` previews inline; `.html` opens as interactive chart in browser.

## Artifact Contract

### Filenames

- `comparison-chart-<report_id>.html`
- `comparison-chart-<report_id>.png`

### MIME Types

- HTML: `text/html`
- PNG: `image/png`

### HTML Export Strategy

- Use `include_plotlyjs='cdn'` to keep HTML files small (~50KB instead of ~3-4MB).
- CDN source: `https://cdn.plot.ly/plotly-latest.min.js`
- Users view charts in a browser with internet access, so CDN is safe.
- Fallback: if CDN mode fails at generation time, fall back to `include_plotlyjs=True` (self-contained).

### Metadata

- `is_comparison_chart: true`
- `chart_engine: "plotly"`
- `chart_format: "plotly_html_png"`
- `source_report_id`
- `source_report_title`
- `data_points`
- `metric_name`
- `generation_mode` (`auto|force|regenerate`)
- `generated_at_unix_ms`

## Architecture Changes

### Backend Domain

- Remove SVG renderer dependency from report flow.
- Keep table/comparison detection logic (or extract/port it) for deciding when to generate chart.
- Replace chart render step with sandbox script execution.

### Sandbox Execution

- Generate chart artifacts using Plotly in sandbox Python runtime.
- Write both artifact files under `/home/ubuntu/`.
- Return deterministic output paths to backend.

### Storage Sync (MinIO S3 — Active Backend)

- **MinIO is the active file storage backend** (`file_storage_backend: "minio"` in config).
- MinIO's `upload_file()` correctly stores `content_type` in S3 metadata and passes it to `put_object()`.
- The bug: `_sync_file_to_storage()` in `agent_task_runner.py` never passes `content_type` to `upload_file()`.
- MinIO supports **presigned URLs** (`generate_download_url()`), which enables direct browser access for chart HTML files.
- GridFS implementation exists as fallback but is not the default. Both must be fixed for completeness.

### Frontend

- Keep image preview for `.png`.
- Add special handling for interactive chart `.html`:
  - label/type shown as Interactive Chart
  - open via signed URL in new tab from file panel/session file list
  - only allow HTML files with metadata `chart_engine: "plotly"` to open inline

### Chart Generation Modes

Two modes of chart generation coexist:

1. **Automatic pipeline** (comparison reports): Backend detects comparison data in report markdown, builds JSON payload, runs dedicated sandbox script. This is the pipeline being migrated.
2. **Agent-driven charts** (ad-hoc): The agent writes and executes Python scripts directly in sandbox via `shell_exec`. Plotly 6.3.1, matplotlib 3.10.7, seaborn 0.13.2, and pandas 2.3.3 are all pre-installed. This already works and requires no changes.

## Implementation Phases

## Phase 0: Prep and Decisions

1. Freeze artifact contract (`.html + .png`, `include_plotlyjs='cdn'`).
2. Confirm no remaining dependency on `.svg` chart name patterns.
3. Define final user behavior for opening `.html` charts.
4. Document dual chart generation modes (automatic pipeline vs agent-driven ad-hoc).

### Exit Criteria

- Contract finalized and documented.

## Phase 1: Storage Sync MIME Hardening (Prerequisite)

**Rationale**: This is a standalone bug fix that benefits the current SVG pipeline too. The current `_sync_file_to_storage()` in `agent_task_runner.py` never passes `content_type` to `upload_file()`, causing all files (including current SVGs) to be served without proper Content-Type headers. This is likely the root cause of the empty SVG rendering issue.

1. Update `_sync_file_to_storage()` to pass `content_type` from `FileInfo` metadata to `upload_file()`.
2. Add extension-based MIME fallback map if attachment MIME is missing:
   ```python
   EXTENSION_MIME_MAP = {
       ".html": "text/html",
       ".png": "image/png",
       ".svg": "image/svg+xml",
       ".pdf": "application/pdf",
       ".md": "text/markdown",
       ".json": "application/json",
       ".csv": "text/csv",
   }
   ```
3. Verify download route in GridFS serves `Content-Type` from stored metadata.
4. Add security headers for HTML chart files served via download route:
   ```
   Content-Security-Policy: default-src 'none'; script-src https://cdn.plot.ly; style-src 'unsafe-inline'; img-src data:;
   Content-Disposition: inline; filename="chart.html"
   X-Content-Type-Options: nosniff
   ```

### Candidate Files

- `backend/app/domain/services/agent_task_runner.py` (`_sync_file_to_storage` method — pass `content_type`)
- `backend/app/infrastructure/external/file/minios3storage.py` (verify presigned URL includes Content-Type)
- `backend/app/infrastructure/external/file/gridfsfile.py` (download route Content-Type — fallback backend)
- tests covering sync and media type round-trip for both MinIO and GridFS

### Exit Criteria

- Synced files keep correct content type end-to-end.
- Existing SVG charts render correctly after this fix (validates the fix independently).

## Phase 2: Sandbox Runtime Readiness

1. Add `kaleido>=1.0.0` to `sandbox/requirements.runtime.txt`.
   - **Important**: Pin to v1+ (not v0). Kaleido v1 uses system Chrome instead of bundling its own.
2. Add `BROWSER_PATH` environment variable to sandbox service in `docker-compose.yml`:
   ```yaml
   environment:
     - BROWSER_PATH=/usr/bin/chromium-browser
   ```
3. Verify Plotly 6.3.1 (already installed) is compatible with Kaleido v1.
4. Add smoke test script to validate both export paths:
   ```python
   import plotly.graph_objects as go
   fig = go.Figure(data=[go.Bar(x=["A", "B"], y=[1, 2])])
   fig.write_html("/tmp/smoke_test.html", include_plotlyjs='cdn')
   fig.write_image("/tmp/smoke_test.png", width=800, height=600)
   print("OK")
   ```
5. Configure Kaleido defaults in smoke test:
   ```python
   import plotly.io as pio
   pio.kaleido.template.default_width = 1200
   pio.kaleido.template.default_height = 800
   pio.kaleido.template.default_scale = 2  # High-res
   ```

### Files

- `sandbox/requirements.runtime.txt` (add `kaleido>=1.0.0`)
- `docker-compose.yml` (add `BROWSER_PATH` env var to sandbox services)
- `sandbox/scripts/plotly_smoke_test.py` (new)

### Exit Criteria

- Sandbox can generate both HTML and PNG artifacts successfully.
- `BROWSER_PATH` resolves to a working Chromium binary inside the container.

## Phase 3: Plotly Chart Generator in Sandbox

1. Add sandbox script to:
   - accept JSON input (title, metric, points) via stdin or file argument,
   - render Plotly figure,
   - write HTML (`include_plotlyjs='cdn'`) + PNG artifacts.
2. Add robust error output for backend logs.
3. Return output paths in machine-readable format (JSON stdout).
4. Set Kaleido defaults at script start for consistent output.

### Candidate Files

- `sandbox/scripts/generate_comparison_chart_plotly.py` (new)

### Exit Criteria

- Script is deterministic, validates inputs, and emits both files.
- HTML file is <100KB (CDN mode).
- PNG file is high-resolution (scale=2, 1200x800).

## Phase 4: Backend Integration in Report Flow

1. Replace `ComparisonChartGenerator` usage in `AgentTaskRunner`.
2. Add backend service/orchestration component that:
   - parses report markdown table (reuse existing `_extract_tables` / `_is_comparison_context` logic),
   - builds JSON payload,
   - runs sandbox script via `sandbox.shell_exec()`,
   - constructs `FileInfo` attachments for `.html` and `.png` with correct MIME types.
3. Preserve existing chart mode flags:
   - `chart=skip`
   - `chart=force`
   - `chart=regenerate`
4. Pass `content_type` when creating FileInfo (leveraging Phase 1 MIME fix).

### Candidate Files

- `backend/app/domain/services/agent_task_runner.py`
- `backend/app/domain/services/comparison_chart_generator.py` (remove/replace)
- `backend/app/domain/services/plotly_chart_orchestrator.py` (new)

### Exit Criteria

- Report events attach Plotly artifacts only (no SVG).
- MIME types are correctly set on both HTML and PNG FileInfo objects.

## Phase 5: Frontend Task-File UX

1. Add file type mapping for interactive chart HTML in `fileType.ts`.
2. Update preview/open behavior:
   - PNG -> existing image preview (already works)
   - HTML chart -> open signed URL in new tab (check metadata `chart_engine: "plotly"`)
3. Ensure chart files appear correctly in:
   - report attachments card
   - session file list ("All files in this task")
4. Only allow HTML files with `is_comparison_chart: true` metadata to open as interactive charts. Other HTML files continue using code preview.

### Candidate Files

- `frontend/src/utils/fileType.ts`
- `frontend/src/components/FilePanelContent.vue`
- `frontend/src/components/SessionFileList.vue`
- related composables/tests

### Exit Criteria

- User can open interactive chart from task files without manual steps.
- Non-chart HTML files are not affected.

## Phase 6: Remove Legacy SVG Pipeline

1. Remove old SVG chart generator module.
2. Remove SVG-specific metadata and filename assumptions.
3. Update tests and docs to Plotly artifacts.

### Candidate Files

- `backend/app/domain/services/comparison_chart_generator.py` (delete)
- `backend/tests/domain/services/test_comparison_chart_generator.py` (replace/delete)
- docs references

### Exit Criteria

- No active code path generates comparison-chart SVG files.

## Phase 7: Verification

Run required checks:

```bash
cd frontend && bun run lint && bun run type-check
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Recommended targeted checks:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_report_file_attachment.py
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_comparison_chart_*.py
cd frontend && bun test
```

### Exit Criteria

- All required lint/type/test commands pass.
- Manual validation confirms chart files are generated, attached, synced, and openable.

## Test Plan

## Backend

1. Generates `.html` and `.png` for valid comparison report.
2. No chart generated for non-comparison report unless forced.
3. `chart=skip|force|regenerate` behavior unchanged.
4. Synced files keep MIME and metadata through storage layer (GridFS and/or MinIO).
5. Download route returns expected media type (`text/html` for chart HTML, `image/png` for chart PNG).
6. HTML chart files are served with restrictive CSP headers.
7. MIME fallback map correctly resolves common extensions when metadata is missing.
8. `BROWSER_PATH` env var is validated at sandbox startup via smoke test.

## Frontend

1. Chart PNG uses image preview component.
2. Chart HTML with `chart_engine: "plotly"` metadata is recognized as interactive chart.
3. Non-chart HTML files are NOT treated as interactive charts.
4. Clicking chart HTML opens signed URL in new tab.
5. Files appear in both attachments and session file list.

## Risks and Mitigations

1. **Kaleido v1 cannot find Chromium in sandbox.**
   - Mitigation: Set `BROWSER_PATH=/usr/bin/chromium-browser` env var in docker-compose.yml. Smoke test validates this at startup.

2. **HTML chart opens with XSS potential from sandbox-generated content.**
   - Mitigation: Serve chart HTML with restrictive CSP headers (`script-src https://cdn.plot.ly` only). Only allow HTML files with `chart_engine: "plotly"` metadata to open as interactive charts.

3. **MIME regressions during sync produce unreadable files.**
   - Mitigation: Phase 1 (MIME hardening) is a standalone prerequisite — implemented and tested before any Plotly changes. Extension-based fallback map provides defense in depth.

4. **Breaking old report attachments.**
   - Mitigation: Preserve support for existing non-chart attachments and report markdown path. Phase 1 MIME fix also improves existing SVG rendering.

5. **CDN-dependent HTML files fail in offline/restricted environments.**
   - Mitigation: Default to `include_plotlyjs='cdn'`. If generation detects CDN is unreachable (e.g., air-gapped sandbox), fall back to `include_plotlyjs=True` (self-contained ~3-4MB).

6. **MinIO/S3 storage layer may handle MIME differently than GridFS.**
   - Mitigation: Verify MIME propagation through whichever storage backend is active (GridFS or MinIO). Both must accept and return `Content-Type` correctly.

## Rollout Strategy

1. Implement behind internal feature flag (`PLOTLY_CHARTS_ENABLED=true`) for quick rollback.
2. Test in development compose stack end-to-end.
3. Remove flag and legacy code after verification window.

## Rollback Plan

If critical issue appears:

1. Disable `PLOTLY_CHARTS_ENABLED`.
2. Re-enable legacy chart generation path temporarily.
3. Keep MIME sync hardening regardless (safe improvement).

## Definition of Done

1. Comparison reports no longer produce SVG chart attachments.
2. Plotly HTML and PNG artifacts are generated in sandbox and attached.
3. Chart artifacts are synced with correct MIME and metadata.
4. Chart artifacts are visible in "All files in this task".
5. Interactive chart file opens correctly from UI.
6. Required backend/frontend checks pass.

## Context7 Reference Notes

- **Plotly** (`/plotly/plotly.py`): Score 93.2/100, 2,696 code snippets, High reputation.
- **Kaleido v1**: Does NOT bundle Chrome. Requires system Chromium discoverable via `BROWSER_PATH` env var or standard paths. This is a breaking change from Kaleido v0.
- **Plotly 6.1+ migration**: The `engine` parameter on `write_image` is deprecated in 6.2 and will be removed. Use Kaleido v1 only.
- **HTML export**: `write_html(include_plotlyjs='cdn')` produces ~50KB files. `write_html()` (default) produces ~3-4MB self-contained files.
- **Static export**: `write_image(format="png", width=1200, height=800, scale=2)` produces high-res PNG via Kaleido + Chromium.
- **Kaleido defaults**: Use `pio.kaleido.template.default_width/height/scale` for consistent output.
- **Matplotlib**: Remains pre-installed in sandbox (3.10.7) for agent-driven ad-hoc charts; not used by the automatic pipeline.
- **Sandbox runtime**: Plotly 6.3.1, matplotlib 3.10.7, seaborn 0.13.2, pandas 2.3.3, numpy 2.3.3 — all pre-installed.
- **Sandbox environment**: Ubuntu 22.04, Python 3.11, Chromium (xtradeb/apps PPA), Xvfb display :1, 3GB memory limit, 1.5 CPU cores.
