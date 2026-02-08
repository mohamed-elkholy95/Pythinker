# Log Fixes Design

## Summary
This design targets current log errors and warnings across frontend, backend, sandbox, and infrastructure services. The goal is to eliminate real failures first, then quiet known-noisy runtime warnings through small, controlled changes that do not alter core behavior.

## Root Causes Observed
- Frontend dev server crashes due to a missing canvas component import during Vite pre-transform. The file exists in the repo, so the most likely cause is inconsistent file path casing or a transient mount/startup mismatch in the container.
- Backend structured output calls to Moonshot fail because the generated JSON schema includes `default` at the same level as `anyOf` (Moonshot rejects this schema format).
- Sandbox file writes fail because `/home/user` does not exist in the container, causing `file_write` to throw a permission/ENOENT error.
- Sandbox containers emit noisy DBus, Vulkan, GCM, and on-device model warnings due to headless Chrome defaults and missing desktop services.
- Redis warns about missing config because it is started without a config file.

## Fix Strategy
- Frontend: validate the canvas import path and add a dev-time preflight check to fail fast if required files are missing. If casing mismatch exists, fix import paths.
- Backend: sanitize generated JSON schemas to remove `default` when `anyOf` or `oneOf` is present at the same level for non-OpenAI endpoints. This keeps strict schemas for OpenAI but avoids Moonshot incompatibility.
- Sandbox: change plan progress artifact path to a guaranteed writable location such as `/home/ubuntu/.agent_progress.json`.
- Sandbox noise: add Chrome flags that disable DBus, Vulkan, and on-device-model services; ensure `/tmp/.X11-unix` exists with correct permissions; add `numpy` to sandbox requirements to remove websockify warning.
- Redis: add a minimal `redis.conf` and update compose files to launch Redis with it to remove the warning.

## Testing & Verification
- Frontend: run the dev server and verify no Vite import resolution errors.
- Backend: add/adjust unit test(s) for schema sanitization and verify Moonshot no longer logs 400s.
- Sandbox: add a test that checks the plan progress file path and confirm `file_write` succeeds.
- Infra: restart affected containers and confirm warnings are removed from logs.
