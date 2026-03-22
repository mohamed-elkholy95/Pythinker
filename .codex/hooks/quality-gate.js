#!/usr/bin/env node

const { execSync } = require("node:child_process");

function safe(command) {
  try {
    return execSync(command, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

const changed = safe("git status --short").split("\n").filter(Boolean);
const files = changed.map((line) => line.replace(/^\s*[A-Z?]{1,2}\s+/, ""));
const touchedBackend = files.some((file) => file.startsWith("backend/"));
const touchedFrontend = files.some((file) => file.startsWith("frontend/"));
const harnessPrefixes = [
  ".codex/",
  ".opencode/",
  ".cursor/",
  "skills/",
  "docs/",
  "scripts/",
  "tests/",
];
const touchedHarnessOnly =
  files.length > 0 &&
  files.every(
    (file) =>
      harnessPrefixes.some((prefix) => file.startsWith(prefix)) ||
      file === "AGENTS.md" ||
      file === "instructions.md" ||
      file === "opencode.json",
  );

process.stdout.write("[quality-gate] recommended verification:\n");

if (touchedBackend) {
  process.stdout.write("- cd backend && ruff check . && ruff format --check . && pytest tests/\n");
}
if (touchedFrontend) {
  process.stdout.write("- cd frontend && bun run lint:check && bun run type-check\n");
}
if (touchedHarnessOnly || files.length === 0) {
  process.stdout.write("- targeted file/script checks for docs and harness-only changes\n");
}
