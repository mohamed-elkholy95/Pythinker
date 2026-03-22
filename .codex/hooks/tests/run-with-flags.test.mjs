import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const repoRoot = join(import.meta.dirname, "..", "..", "..");
const runnerPath = join(repoRoot, ".codex", "hooks", "run-with-flags.js");

function makeTempHook() {
  const dir = mkdtempSync(join(tmpdir(), "pythinker-hook-"));
  const markerPath = join(dir, "marker.txt");
  const hookPath = join(dir, "hook.js");
  writeFileSync(
    hookPath,
    [
      "const fs = require('node:fs');",
      "const path = process.argv[2];",
      "fs.writeFileSync(path, 'ran', 'utf8');",
      "process.stdout.write('hook-ran');",
    ].join("\n"),
    "utf8",
  );
  return { dir, hookPath, markerPath };
}

test("runs hook when profile is allowed", () => {
  const { dir, hookPath, markerPath } = makeTempHook();
  try {
    execFileSync(
      process.execPath,
      [runnerPath, "demo-hook", hookPath, "minimal,standard", markerPath],
      {
        env: { ...process.env, PYTHINKER_HOOK_PROFILE: "minimal" },
        stdio: "pipe",
      },
    );
    assert.equal(readFileSync(markerPath, "utf8"), "ran");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("skips hook when disabled via env", () => {
  const { dir, hookPath, markerPath } = makeTempHook();
  try {
    const output = execFileSync(
      process.execPath,
      [runnerPath, "demo-hook", hookPath, "minimal,standard,strict", markerPath],
      {
        env: {
          ...process.env,
          PYTHINKER_HOOK_PROFILE: "minimal",
          PYTHINKER_DISABLED_HOOKS: "demo-hook",
        },
        stdio: "pipe",
      },
    ).toString("utf8");
    assert.match(output, /disabled/);
    assert.equal(existsSync(markerPath), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("falls back to standard for unknown profile", () => {
  const { dir, hookPath, markerPath } = makeTempHook();
  try {
    execFileSync(
      process.execPath,
      [runnerPath, "demo-hook", hookPath, "standard", markerPath],
      {
        env: { ...process.env, PYTHINKER_HOOK_PROFILE: "weird-profile" },
        stdio: "pipe",
      },
    );
    assert.equal(readFileSync(markerPath, "utf8"), "ran");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
