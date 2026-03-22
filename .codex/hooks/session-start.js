#!/usr/bin/env node

const { execSync } = require("node:child_process");
const { mkdirSync, writeFileSync } = require("node:fs");
const { join, resolve } = require("node:path");

function safe(command) {
  try {
    return execSync(command, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

const repoRoot = resolve(__dirname, "..", "..");
const sessionDir = join(repoRoot, ".codex", "session");
mkdirSync(sessionDir, { recursive: true });

const snapshot = {
  started_at: new Date().toISOString(),
  branch: safe("git branch --show-current"),
  head: safe("git rev-parse --short HEAD"),
  modified_files: safe("git status --short").split("\n").filter(Boolean),
};

writeFileSync(join(sessionDir, "latest-session.json"), `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
process.stdout.write(`[session-start] ${snapshot.branch || "unknown-branch"} ${snapshot.head || "unknown-head"}\n`);
