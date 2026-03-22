# Docker Release Versioning Design

**Date:** 2026-03-17
**Status:** Approved
**Version:** v1.0.1 (first release under this system)

## Problem

Version numbers are scattered and inconsistent across the codebase:
- `backend/pyproject.toml`: `0.1.0`
- `frontend/package.json`: `0.0.0`
- `CHANGELOG.md`: `1.0.0`
- `backend/app/gateway/main.py`: hardcoded `1.0.0`

No single source of truth, no runtime version exposure, no GitHub Releases, no release automation.

## Design Decisions

### 1. Git Tags as Single Source of Truth

Git tags (`v1.0.1`) are the authoritative version. CI extracts semver from the tag ref. `pyproject.toml` and `package.json` are synced cosmetically but are not authoritative.

**Rationale:** Zero files to edit per release when using automation. Tag IS the version. No drift risk.

### 2. Version Injection into Docker Images

Build args baked at image build time:
- `GIT_VERSION` — semver from tag (e.g. `1.0.1`), defaults to `dev`
- `GIT_SHA` — full commit hash
- `BUILD_DATE` — ISO 8601 timestamp

These surface as:
- **OCI labels** on each image (`org.opencontainers.image.version`, `.revision`, `.created`)
- **Backend health endpoint** `/api/v1/health` returns version, git_sha, build_date
- **Sandbox** `SANDBOX_VERSION` env var (already exists, just wired consistently)
- **Frontend** version injected as env var available to nginx entrypoint

**Dockerfile changes (all 3):**
```dockerfile
ARG GIT_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.version=${GIT_VERSION}
LABEL org.opencontainers.image.revision=${GIT_SHA}
LABEL org.opencontainers.image.created=${BUILD_DATE}

ENV GIT_VERSION=${GIT_VERSION}
ENV GIT_SHA=${GIT_SHA}
ENV BUILD_DATE=${BUILD_DATE}
```

### 3. Release Script (`scripts/release.sh`)

Local script that orchestrates a release:

1. Validates: on `main`, clean tree, remote up to date
2. Takes version arg (`./scripts/release.sh 1.0.1`), validates semver
3. Checks tag doesn't already exist
4. Syncs version into `pyproject.toml` and `package.json` (cosmetic)
5. Runs pre-release checks: `ruff check` + `ruff format --check`, `bun run lint:check` + `bun run type-check`
6. Commits version bump: `chore(release): v1.0.1`
7. Creates annotated tag `v1.0.1`
8. Confirms before pushing (interactive prompt, `--dry-run` available)
9. Pushes commit + tag → triggers CI

### 4. GitHub Release Workflow (`.github/workflows/create-release.yml`)

Triggers on `push` tags `v*` (parallel with Docker build workflow):

1. Extracts version from tag ref
2. Extracts relevant `CHANGELOG.md` section for this version
3. Creates GitHub Release via `gh release create` with:
   - Changelog body
   - Docker pull commands for all 3 images
   - Marked as latest release

### 5. One-Time v1.0.1 Fixup

Commit strategy:
1. `chore(docker): add version build args to Dockerfiles` — ARG/LABEL/ENV in all 3 Dockerfiles
2. `feat(ci): add GitHub Release workflow` — new `.github/workflows/create-release.yml`
3. `feat(release): add release.sh script` — new `scripts/release.sh`
4. `feat(api): expose version in health endpoint` — backend health + gateway version from env
5. `chore(release): v1.0.1` — sync pyproject.toml, package.json, CHANGELOG.md, tag, push

## Files Changed

### New Files
- `scripts/release.sh`
- `.github/workflows/create-release.yml`

### Modified Files
- `backend/Dockerfile` — add ARG/LABEL/ENV
- `frontend/Dockerfile` — add ARG/LABEL/ENV
- `sandbox/Dockerfile` — add ARG/LABEL/ENV
- `.github/workflows/docker-build-and-push.yml` — pass build-args
- `backend/app/interfaces/api/routes/health.py` (or equivalent) — expose version
- `backend/app/gateway/main.py` — read version from env
- `backend/pyproject.toml` — version sync to 1.0.1
- `frontend/package.json` — version sync to 1.0.1
- `CHANGELOG.md` — add v1.0.1 section
