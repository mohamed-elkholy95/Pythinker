#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const { resolve, extname } = require("node:path");

const VALID_PROFILES = new Set(["minimal", "standard", "strict"]);

function normalizeProfile(rawProfile) {
  return VALID_PROFILES.has(rawProfile) ? rawProfile : "standard";
}

function parseDisabledHooks(rawDisabled) {
  if (!rawDisabled) return new Set();
  return new Set(
    rawDisabled
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
  );
}

function parseAllowedProfiles(rawProfiles) {
  if (!rawProfiles) return new Set(["minimal", "standard", "strict"]);
  return new Set(
    rawProfiles
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
  );
}

function main() {
  const [, , hookId, scriptPath, rawProfiles, ...scriptArgs] = process.argv;

  if (!hookId || !scriptPath) {
    process.stderr.write(
      "Usage: run-with-flags.js <hook-id> <script-path> [allowed-profiles] [script-args...]\n",
    );
    process.exit(2);
  }

  const profile = normalizeProfile(process.env.PYTHINKER_HOOK_PROFILE);
  const disabledHooks = parseDisabledHooks(process.env.PYTHINKER_DISABLED_HOOKS);
  const allowedProfiles = parseAllowedProfiles(rawProfiles);

  if (disabledHooks.has(hookId)) {
    process.stdout.write(`[skip] ${hookId} disabled\n`);
    return;
  }

  if (!allowedProfiles.has(profile)) {
    process.stdout.write(`[skip] ${hookId} not enabled for profile ${profile}\n`);
    return;
  }

  const absoluteScriptPath = resolve(scriptPath);
  const executable = extname(absoluteScriptPath) === ".js" || extname(absoluteScriptPath) === ".mjs"
    ? process.execPath
    : absoluteScriptPath;
  const args = executable === process.execPath ? [absoluteScriptPath, ...scriptArgs] : scriptArgs;

  const result = spawnSync(executable, args, {
    env: process.env,
    stdio: "inherit",
  });

  if (typeof result.status === "number") {
    process.exit(result.status);
  }

  process.exit(1);
}

main();
