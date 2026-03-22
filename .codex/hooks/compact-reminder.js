#!/usr/bin/env node

const { mkdirSync, readFileSync, writeFileSync } = require("node:fs");
const { join, resolve } = require("node:path");

const repoRoot = resolve(__dirname, "..", "..");
const sessionDir = join(repoRoot, ".codex", "session");
const counterPath = join(sessionDir, "compact-counter.json");
const threshold = Number(process.env.PYTHINKER_COMPACT_THRESHOLD || "25");

mkdirSync(sessionDir, { recursive: true });

let count = 0;
try {
  count = JSON.parse(readFileSync(counterPath, "utf8")).count || 0;
} catch {
  count = 0;
}

count += 1;
writeFileSync(counterPath, `${JSON.stringify({ count }, null, 2)}\n`, "utf8");

if (count >= threshold && count % threshold === 0) {
  process.stdout.write("[compact-reminder] Consider compacting at the next phase boundary.\n");
}
