#!/usr/bin/env node

const { relative, resolve } = require("node:path");

const repoRoot = resolve(__dirname, "..", "..");
const target = process.argv[2];

if (!target) {
  process.stdout.write("[doc-write-warning] no target path provided\n");
  process.exit(0);
}

const relativePath = relative(repoRoot, resolve(target));
const allowed =
  relativePath.startsWith("docs/") ||
  relativePath === "README.md" ||
  relativePath === "AGENTS.md" ||
  relativePath === "instructions.md";

if (!allowed && relativePath.endsWith(".md")) {
  process.stdout.write(`[doc-write-warning] ${relativePath} is outside the expected docs locations\n`);
}
