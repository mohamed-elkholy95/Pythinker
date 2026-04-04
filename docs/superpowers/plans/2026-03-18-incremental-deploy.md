# Historical: Incremental Deploy Migration — Implementation Plan

> **Historical context only.** This plan reflects the earlier Dokploy/GHCR migration path and is no longer the current deployment workflow. The live `docker-compose-deploy.yml` now runs a watch-free dev-style stack directly.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from Dokploy (builds-from-source) to CI-built GHCR images deployed via SSH, with zero data loss and < 30 seconds downtime.

**Architecture:** CI builds changed images on push to `main`, pushes to ghcr.io. Deploy job SSHs to VPS, pulls images, restarts services. Dokploy remains for monitoring only.

**Tech Stack:** GitHub Actions, Docker Compose, ghcr.io, SSH deploy, appleboy/ssh-action

**Spec:** `docs/superpowers/specs/2026-03-18-incremental-deploy-design.md`

---

### Task 1: Commit Code Changes (Local)

All code fixes from the incident and spec review are already applied but uncommitted. Commit them as atomic changes.

**Files:**
- Modified: `docker-compose-deploy.yml` (container_name removal, external:true removal)
- Modified: `.github/workflows/deploy.yml` (sandbox health check, deploy_config filter)
- Modified: `docs/superpowers/specs/2026-03-18-incremental-deploy-design.md` (lessons learned)

- [ ] **Step 1: Stage and commit compose fixes**

```bash
git add docker-compose-deploy.yml
git commit -m "fix(deploy): remove container_name and external:true from deploy compose

Removes hardcoded container_name: pythinker-qdrant (caused name conflicts
with Dokploy stack) and external: true from all volumes and network
(prevented auto-creation on first deploy)."
```

- [ ] **Step 2: Stage and commit workflow fixes**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat(ci): add sandbox health check and deploy_config path filter

Adds sandbox health verification (localhost:8083/health) alongside backend
check in deploy step. Adds docker-compose-deploy.yml to path filter so
compose-only changes trigger a deploy."
```

- [ ] **Step 3: Stage and commit spec update**

```bash
git add docs/superpowers/specs/2026-03-18-incremental-deploy-design.md
git commit -m "docs(spec): add lessons learned from 2026-03-18 deploy incident"
```

- [ ] **Step 4: Push all commits**

```bash
git push
```

Expected: Pre-push hooks pass (frontend lint, TypeScript check, backend ruff). CI Build & Deploy workflow triggers but deploy step skips (no VPS secrets yet).

---

### Task 2: Generate VPS SSH Key Pair

Create a dedicated SSH key for CI deploy access. This key will be added as a GitHub Secret and authorized on the VPS.

- [ ] **Step 1: Generate ed25519 key pair**

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy@pythinker" -f ~/.ssh/pythinker_deploy -N ""
```

Expected: Creates `~/.ssh/pythinker_deploy` (private) and `~/.ssh/pythinker_deploy.pub` (public).

- [ ] **Step 2: Add public key to VPS authorized_keys**

```bash
cat ~/.ssh/pythinker_deploy.pub | ssh vps "cat >> ~/.ssh/authorized_keys"
```

- [ ] **Step 3: Test SSH with the new key**

```bash
ssh -i ~/.ssh/pythinker_deploy vps "echo 'CI deploy key works'"
```

Expected: Prints "CI deploy key works" without password prompt.

---

### Task 3: Add GitHub Secrets and Configure GHCR Access

Add the required secrets and ensure the VPS can pull private images from ghcr.io.

- [ ] **Step 1: Get VPS host IP**

```bash
ssh vps "hostname -I | awk '{print \$1}'"
```

Note the IP for the next step.

- [ ] **Step 2: Add VPS_SSH_KEY secret**

```bash
gh secret set VPS_SSH_KEY --repo mohamed-elkholy95/Pythinker < ~/.ssh/pythinker_deploy
```

- [ ] **Step 3: Add VPS_HOST secret**

```bash
gh secret set VPS_HOST --repo mohamed-elkholy95/Pythinker --body "<VPS_IP_FROM_STEP_1>"
```

- [ ] **Step 4: Add VPS_USER secret**

```bash
gh secret set VPS_USER --repo mohamed-elkholy95/Pythinker --body "root"
```

- [ ] **Step 5: Create GitHub environment (required by workflow)**

```bash
gh api repos/mohamed-elkholy95/Pythinker/environments/production -X PUT --input /dev/null
```

- [ ] **Step 6: Verify secrets are set**

```bash
gh secret list --repo mohamed-elkholy95/Pythinker
```

Expected: Shows `VPS_SSH_KEY`, `VPS_HOST`, `VPS_USER`.

- [ ] **Step 7: Make GHCR packages public (or set up VPS auth)**

The CI workflow passes `GITHUB_TOKEN` to the VPS SSH session for `docker login ghcr.io`. For the manual cutover (Task 6), you also need VPS auth. Easiest: make the 3 packages public (repo is open-source):

```bash
# For each package, visit:
# https://github.com/users/mohamed-elkholy95/packages/container/pythinker-backend/settings
# https://github.com/users/mohamed-elkholy95/packages/container/pythinker-frontend/settings
# https://github.com/users/mohamed-elkholy95/packages/container/pythinker-sandbox/settings
# → Change visibility → Public
```

Alternative (private packages): Create a GitHub PAT with `read:packages` scope and log in on VPS:

```bash
ssh vps "echo '<PAT>' | docker login ghcr.io -u mohamed-elkholy95 --password-stdin"
```

---

### Task 4: Provision Deploy Directory on VPS

Create `/opt/pythinker-deploy/` with the repo clone and production `.env`.

- [ ] **Step 1: Clone repo to deploy directory**

```bash
ssh vps "mkdir -p /opt/pythinker-deploy && cd /opt/pythinker-deploy && git clone https://github.com/mohamed-elkholy95/Pythinker.git . 2>&1 | tail -3"
```

Expected: Clones successfully. If already cloned, run `git pull origin main --ff-only` instead.

- [ ] **Step 2: Copy production .env from Dokploy**

First find the Dokploy compose dir:

```bash
ssh vps "docker inspect pythinker-pythinker-akwnya-backend-1 --format '{{index .Config.Labels \"com.docker.compose.project.working_dir\"}}' 2>/dev/null || echo 'Backend not running under Dokploy'"
```

Then copy:

```bash
ssh vps "cp /etc/dokploy/compose/pythinker-pythinker-akwnya/code/.env /opt/pythinker-deploy/.env"
```

- [ ] **Step 3: Verify deploy directory contents**

```bash
ssh vps "ls -la /opt/pythinker-deploy/{docker-compose-deploy.yml,.env,sandbox/seccomp-sandbox.hardened.json} 2>&1"
```

Expected: All three files exist. The seccomp profile is referenced in the compose file as `./sandbox/seccomp-sandbox.hardened.json`.

---

### Task 5: Seed GHCR Images (Force Build All)

Trigger a full CI build to push all 3 images to ghcr.io so `docker compose pull` works on first deploy.

- [ ] **Step 1: Trigger force build via workflow_dispatch**

```bash
gh workflow run "Build & Deploy" --repo mohamed-elkholy95/Pythinker --ref main -f force_build_all=true
```

- [ ] **Step 2: Wait for builds to complete**

```bash
gh run list --repo mohamed-elkholy95/Pythinker --workflow "Build & Deploy" --limit 1
```

Monitor until status shows `completed`. The deploy step will fail (expected — Dokploy containers still own the ports), but the build jobs should all pass.

- [ ] **Step 3: Verify images exist on ghcr.io**

```bash
gh api user/packages/container/pythinker-backend/versions --jq '.[0].metadata.container.tags' 2>/dev/null || echo "Check ghcr.io manually"
gh api user/packages/container/pythinker-frontend/versions --jq '.[0].metadata.container.tags' 2>/dev/null || echo "Check ghcr.io manually"
gh api user/packages/container/pythinker-sandbox/versions --jq '.[0].metadata.container.tags' 2>/dev/null || echo "Check ghcr.io manually"
```

Expected: Each shows `["latest", "sha-XXXXXXX"]`.

---

### Task 6: Cutover — Stop Dokploy, Start CI Stack

This is the actual migration. Downtime: < 30 seconds.

- [ ] **Step 1: Disable Dokploy auto-deploy**

Open Dokploy dashboard → Pythinker project → Settings → disable "Auto Deploy" / "Autodeploy on push".

- [ ] **Step 2: Pull images on VPS**

```bash
ssh vps "cd /opt/pythinker-deploy && docker compose -f docker-compose-deploy.yml pull 2>&1 | tail -10"
```

Expected: Pulls all 3 app images from ghcr.io. Infrastructure images are upstream and already cached.

- [ ] **Step 3: Stop Dokploy-managed containers (DOWNTIME STARTS)**

```bash
ssh vps "cd /etc/dokploy/compose/pythinker-pythinker-akwnya/code && docker compose down 2>&1"
```

Expected: All pythinker containers stop. Volumes persist (named volumes are not removed by `down`).

- [ ] **Step 4: Also stop the manually-started sandbox if still running**

```bash
ssh vps "docker stop code-sandbox-1 2>/dev/null; docker rm code-sandbox-1 2>/dev/null; echo 'Cleaned up'"
```

- [ ] **Step 5: Start CI-managed stack (DOWNTIME ENDS)**

```bash
ssh vps "cd /opt/pythinker-deploy && docker compose -f docker-compose-deploy.yml up -d 2>&1"
```

Expected: All services start. Named volumes are reused (data preserved). Network auto-created.

- [ ] **Step 6: Verify all services healthy**

```bash
ssh vps "sleep 15 && docker ps --format '{{.Names}} {{.Status}}' | sort"
```

Expected: All 8 services show "Up" with "(healthy)" for backend, mongodb, redis, qdrant, minio.

- [ ] **Step 7: Verify backend and sandbox health endpoints**

```bash
ssh vps "curl -fsS http://localhost:8000/api/v1/health && echo '' && curl -fsS http://localhost:8083/health"
```

Expected: Both return healthy JSON.

- [ ] **Step 8: Verify frontend serves the app**

```bash
ssh vps "curl -fsS -o /dev/null -w '%{http_code}' http://localhost:5174/"
```

Expected: `200`.

---

### Task 7: End-to-End Verification

Push a trivial change and verify the full CI → deploy pipeline works.

- [ ] **Step 1: Make a trivial backend change**

Add a comment to `backend/app/main.py`:

```python
# Deployment pipeline: CI build → ghcr.io → SSH deploy (2026-03-18)
```

- [ ] **Step 2: Commit and push**

```bash
git add backend/app/main.py
git commit -m "chore: verify CI deploy pipeline"
git push
```

- [ ] **Step 3: Monitor CI run**

```bash
gh run watch --repo mohamed-elkholy95/Pythinker
```

Expected: `changes` → detects backend change → `build` → builds backend only (frontend/sandbox skipped) → `deploy` → SSH pull + restart → health checks pass → green.

- [ ] **Step 4: Verify on VPS**

```bash
ssh vps "docker ps --format '{{.Names}} {{.Status}}' | sort"
```

Expected: All healthy. Backend container restarted with new image.

- [ ] **Step 5: Test the app in browser**

Open `https://pythinker.com` and verify the app loads, create a session, confirm sandbox screencast connects.

---

### Task 8: Cleanup

- [ ] **Step 1: Remove stale Dokploy containers/images**

```bash
ssh vps "docker system prune -f 2>&1 | tail -3"
```

- [ ] **Step 2: Verify Dokploy dashboard still shows containers**

Open Dokploy dashboard — it should still see the running containers via Docker API, even though they were started by a different compose project.

- [ ] **Step 3: Update MEMORY.md with deployment info**

Record the new deployment workflow in project memory for future sessions.
