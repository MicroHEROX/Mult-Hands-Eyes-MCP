#!/usr/bin/env node
/**
 * npm wrapper bootstrap for Mult Hands Eyes MCP.
 *
 * On first run this creates a PRIVATE Python venv under a cache directory
 * and installs the two runtime deps (mcp, httpx) into it; the bundled
 * Python source in ../python/ is used via PYTHONPATH. Nothing is written
 * outside the cache dir and the npm package itself.
 */
"use strict";

const { spawnSync, spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const PYDIR = path.join(ROOT, "python");
const CACHE =
  process.env.MULTHANDS_CACHE_DIR || path.join(os.tmpdir(), "multhands-npm");
const VENV = path.join(CACHE, "venv");

function fail(message) {
  console.error(`[mult-hands-eyes-mcp] ${message}`);
  process.exit(1);
}

function findPython() {
  if (process.env.PYTHON) return process.env.PYTHON;
  const candidates =
    process.platform === "win32" ? ["python", "py", "python3"] : ["python3", "python"];
  for (const candidate of candidates) {
    const probe = spawnSync(candidate, ["--version"], { stdio: "ignore" });
    if (probe.status === 0) return candidate;
  }
  return null;
}

function venvPython() {
  const candidates =
    process.platform === "win32"
      ? [path.join(VENV, "Scripts", "python.exe")]
      : [path.join(VENV, "bin", "python")];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function ensureVenv() {
  const existing = venvPython();
  if (existing) return existing;

  const python = findPython();
  if (!python) {
    fail(
      "Python 3.10+ is required but not found. Install it from https://python.org or set the PYTHON env var."
    );
  }
  const version = spawnSync(python, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"], {
    stdio: "ignore",
  });
  if (version.status !== 0) {
    fail("Python 3.10+ is required; the detected interpreter is too old.");
  }

  fs.mkdirSync(CACHE, { recursive: true });
  console.error(`[mult-hands-eyes-mcp] creating private venv at ${VENV} (first run only)`);
  const create = spawnSync(python, ["-m", "venv", VENV], { stdio: "inherit" });
  if (create.status !== 0) fail("failed to create the Python venv");

  const vp = venvPython();
  if (!vp) fail("venv created but its interpreter was not found");
  console.error("[mult-hands-eyes-mcp] installing runtime deps (mcp, httpx) — one time");
  const install = spawnSync(
    vp,
    [
      "-m",
      "pip",
      "install",
      "--quiet",
      "--disable-pip-version-check",
      "mcp>=2.0.0",
      "httpx>=0.27.0",
    ],
    { stdio: "inherit" }
  );
  if (install.status !== 0) fail("failed to install runtime deps into the venv");
  return vp;
}

const python = ensureVenv();
const env = {
  ...process.env,
  PYTHONPATH: PYDIR + path.delimiter + (process.env.PYTHONPATH || ""),
};
const child = spawn(python, ["-m", "multhands", ...process.argv.slice(2)], {
  stdio: "inherit",
  env,
});
child.on("exit", (code, signal) => {
  process.exit(code !== null ? code : signal ? 1 : 0);
});
child.on("error", (error) => fail(`failed to launch the server: ${error.message}`));