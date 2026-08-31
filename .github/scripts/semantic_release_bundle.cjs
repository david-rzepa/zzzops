const { spawnSync } = require("node:child_process");

function pythonCandidates() {
  return process.env.PYTHON ? [process.env.PYTHON] : ["python3", "python"];
}

async function prepare(_pluginConfig, context) {
  const version = context.nextRelease && context.nextRelease.version;
  if (!version) {
    throw new Error("Marketplace bundling requires a semantic-release version.");
  }
  let last;
  for (const python of pythonCandidates()) {
    const result = spawnSync(python, [
      ".github/scripts/build_marketplace_bundle.py",
      "--version", version,
      "--output", "dist/marketplace"
    ], { cwd: context.cwd, encoding: "utf8" });
    last = result;
    if (!result.error && result.status === 0) {
      context.logger.log(`Built validated OpenAI portal skills bundle for v${version}.`);
      return;
    }
    if (!result.error || result.error.code !== "ENOENT") {
      break;
    }
  }
  const detail = (last && (last.stderr || last.stdout || (last.error && last.error.message))) || "Python was unavailable";
  throw new Error(`Marketplace bundle preparation failed: ${String(detail).trim()}`);
}

module.exports = { prepare };
