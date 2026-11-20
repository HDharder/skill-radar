#!/usr/bin/env node
// Thin shim so `npx github:HDharder/skill-radar` works without publishing to
// the npm registry. All the actual install logic lives in install.sh (bash);
// this just locates it and runs it, forwarding output and the exit code.
// Node is only needed for this one-time install step, never at runtime: the
// hook itself is plain Python with no Node dependency.
const { spawnSync } = require("child_process");
const path = require("path");

const installScript = path.join(__dirname, "..", "install.sh");

const result = spawnSync("bash", [installScript], { stdio: "inherit" });

if (result.error) {
  console.error(
    "skill-radar: could not run install.sh (is bash on PATH?):",
    result.error.message
  );
  process.exit(1);
}

process.exit(result.status ?? 1);
