#!/usr/bin/env node

const { existsSync } = require("node:fs");
const { resolve } = require("node:path");

const repoRoot = resolve(__dirname, "..", "..");
const expected = ["mcp.json", "mcp.json.example"];

for (const file of expected) {
  const fullPath = resolve(repoRoot, file);
  process.stdout.write(`[mcp-health] ${file}: ${existsSync(fullPath) ? "present" : "missing"}\n`);
}
