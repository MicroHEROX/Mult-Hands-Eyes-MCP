/**
 * Bundles the Python server source into python/multhands and copies the
 * LICENSE, so the npm tarball is self-contained. Runs before npm pack /
 * npm publish (prepack) and on git installs (prepare).
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const npmDir = path.join(__dirname, "..");
const repoRoot = path.join(npmDir, "..", "..");
const srcDir = path.join(repoRoot, "src", "multhands");
const destDir = path.join(npmDir, "python", "multhands");

if (!fs.existsSync(srcDir)) {
  console.error(`prepack: source directory not found: ${srcDir}`);
  process.exit(1);
}

fs.rmSync(destDir, { recursive: true, force: true });
fs.cpSync(srcDir, destDir, {
  recursive: true,
  filter: (src) => {
    const base = path.basename(src);
    return base !== "__pycache__" && !base.endsWith(".pyc");
  },
});
fs.copyFileSync(path.join(repoRoot, "LICENSE"), path.join(npmDir, "LICENSE"));
console.log("prepack: bundled python source -> python/multhands");