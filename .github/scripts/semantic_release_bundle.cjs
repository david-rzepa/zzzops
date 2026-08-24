const { mkdtempSync, rmSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const { spawnSync } = require("node:child_process");

function pythonCandidates() {
  return process.env.PYTHON ? [process.env.PYTHON] : ["python3", "python"];
}

async function prepare(_pluginConfig, context) {
  const version = context.nextRelease && context.nextRelease.version;
  const notes = context.nextRelease && context.nextRelease.notes;
  if (!version || !notes) {
    throw new Error("Marketplace bundling requires semantic-release version and release notes.");
  }
  const temporary = mkdtempSync(join(tmpdir(), "zzzops-release-notes-"));
  const notesPath = join(temporary, "RELEASE_NOTES.md");
  writeFileSync(notesPath, notes, "utf8");
  try {
    let last;
    for (const python of pythonCandidates()) {
      const result = spawnSync(python, [
        ".github/scripts/build_marketplace_bundle.py",
        "--version", version,
        "--release-notes-file", notesPath,
        "--output", "dist/marketplace"
      ], { cwd: context.cwd, encoding: "utf8" });
      last = result;
      if (!result.error && result.status === 0) {
        context.logger.log(`Built validated OpenAI and Claude marketplace bundles for v${version}.`);
        return;
      }
      if (!result.error || result.error.code !== "ENOENT") {
        break;
      }
    }
    const detail = (last && (last.stderr || last.stdout || (last.error && last.error.message))) || "Python was unavailable";
    throw new Error(`Marketplace bundle preparation failed: ${String(detail).trim()}`);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

module.exports = { prepare };
