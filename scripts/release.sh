#!/usr/bin/env bash
# =============================================================================
# Pythinker Release Script
# =============================================================================
# Usage:
#   ./scripts/release.sh 1.0.1          # Create and push release v1.0.1
#   ./scripts/release.sh 1.0.1 --dry-run # Show what would happen without doing it
#
# What it does:
#   1. Validates clean main branch, synced with remote
#   2. Syncs version into pyproject.toml and package.json
#   3. Runs lint checks (backend + frontend)
#   4. Commits version bump, creates annotated tag
#   5. Pushes to origin (triggers CI: Docker build + GitHub Release)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRY_RUN=false

# --- Helpers ---

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# Portable in-place sed (handles GNU vs BSD)
sedi() {
    if sed --version 2>/dev/null | grep -q 'GNU sed'; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}

usage() {
    echo "Usage: $0 <VERSION> [--dry-run]"
    echo ""
    echo "  VERSION    Semver version without 'v' prefix (e.g. 1.0.1)"
    echo "  --dry-run  Show what would happen without making changes"
    echo ""
    echo "Examples:"
    echo "  $0 1.0.1"
    echo "  $0 2.0.0 --dry-run"
    exit 1
}

# --- Parse args ---

VERSION=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h) usage ;;
        *)
            if [ -z "$VERSION" ]; then
                VERSION="$arg"
            else
                error "Unexpected argument: $arg"
            fi
            ;;
    esac
done

[ -z "$VERSION" ] && usage

TAG="v${VERSION}"

# --- Validate semver ---

if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
    error "Invalid semver: $VERSION (expected format: X.Y.Z or X.Y.Z-pre.1)"
fi

info "Preparing release ${TAG}"

# --- Validate git state ---

cd "$REPO_ROOT"

BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    error "Must be on 'main' branch (currently on '${BRANCH}')"
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    error "Working tree is dirty. Commit or stash changes first."
fi

git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
    error "Local main ($LOCAL) differs from origin/main ($REMOTE). Pull or push first."
fi

ok "On main branch, clean tree, synced with remote"

# --- Check tag doesn't exist ---

if git tag -l "$TAG" | grep -q "$TAG"; then
    error "Tag ${TAG} already exists"
fi

ok "Tag ${TAG} is available"

# --- Sync version into source files ---

info "Syncing version ${VERSION} into source files..."

if [ "$DRY_RUN" = true ]; then
    info "[DRY RUN] Would update backend/pyproject.toml version to ${VERSION}"
    info "[DRY RUN] Would update frontend/package.json version to ${VERSION}"
else
    # Update pyproject.toml
    sedi "s/^version = \".*\"/version = \"${VERSION}\"/" "$REPO_ROOT/backend/pyproject.toml"
    ok "Updated backend/pyproject.toml"

    # Update package.json (match the top-level "version" field only)
    cd "$REPO_ROOT/frontend"
    npm pkg set version="$VERSION" 2>/dev/null || \
        sedi "s/\"version\": \".*\"/\"version\": \"${VERSION}\"/" package.json
    cd "$REPO_ROOT"
    ok "Updated frontend/package.json"
fi

# --- Run lint checks ---

info "Running pre-release lint checks..."

if [ "$DRY_RUN" = true ]; then
    info "[DRY RUN] Would run: ruff check + ruff format --check (backend)"
    info "[DRY RUN] Would run: bun run lint:check + bun run type-check (frontend)"
else
    info "Backend: ruff check..."
    cd "$REPO_ROOT/backend"
    if command -v ruff &>/dev/null; then
        ruff check . || error "Backend lint failed"
        ruff format --check . || error "Backend format check failed"
        ok "Backend lint passed"
    else
        warn "ruff not found, skipping backend lint (ensure CI catches issues)"
    fi

    info "Frontend: lint + type-check..."
    cd "$REPO_ROOT/frontend"
    if command -v bun &>/dev/null; then
        bun run lint:check || error "Frontend lint failed"
        bun run type-check || error "Frontend type-check failed"
        ok "Frontend checks passed"
    else
        warn "bun not found, skipping frontend checks (ensure CI catches issues)"
    fi

    cd "$REPO_ROOT"
fi

# --- Commit version bump ---

info "Creating version bump commit..."

if [ "$DRY_RUN" = true ]; then
    info "[DRY RUN] Would commit: chore(release): ${TAG}"
    info "[DRY RUN] Would create annotated tag: ${TAG}"
else
    git add backend/pyproject.toml frontend/package.json
    git commit -m "$(cat <<EOF
chore(release): ${TAG}

Sync version to ${VERSION} in pyproject.toml and package.json.
EOF
)"
    ok "Version bump committed"

    git tag -a "$TAG" -m "Release ${TAG}"
    ok "Created annotated tag ${TAG}"
fi

# --- Push ---

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  Ready to push ${TAG} to origin${NC}"
echo -e "${YELLOW}  This will trigger:${NC}"
echo -e "${YELLOW}    - Docker image builds (frontend, backend, sandbox)${NC}"
echo -e "${YELLOW}    - GitHub Release creation${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$DRY_RUN" = true ]; then
    info "[DRY RUN] Would push commit + tag to origin"
    info "[DRY RUN] Complete. No changes were made."
    exit 0
fi

read -rp "Push to origin? [y/N] " CONFIRM
if [[ "$CONFIRM" != [yY] ]]; then
    warn "Aborted. The commit and tag are local — you can push later with:"
    echo "  git push origin main && git push origin ${TAG}"
    exit 0
fi

git push origin main
git push origin "$TAG"

echo ""
ok "Release ${TAG} pushed successfully!"
echo ""
info "CI pipelines triggered:"
echo "  - Docker build: https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/docker-build-and-push.yml"
echo "  - GitHub Release: https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/create-release.yml"
echo ""
info "Docker images (once CI completes):"
echo "  docker pull pythinker/pythinker-frontend:${VERSION}"
echo "  docker pull pythinker/pythinker-backend:${VERSION}"
echo "  docker pull pythinker/pythinker-sandbox:${VERSION}"
