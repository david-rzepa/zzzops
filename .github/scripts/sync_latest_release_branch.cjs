const { spawnSync } = require("node:child_process");

function run(command, args, { cwd, env = process.env } = {}) {
  const result = spawnSync(command, args, { cwd, env, encoding: "utf8" });
  if (!result.error && result.status === 0) {
    return result.stdout.trim();
  }
  const detail = result.error?.message || result.stderr.trim() || result.stdout.trim() || `exit ${result.status}`;
  throw new Error(`${command} ${args.join(" ")} failed: ${detail}`);
}

function releaseTagAtHead(cwd) {
  const tags = run("git", ["tag", "--points-at", "HEAD", "--sort=-v:refname", "--list", "v[0-9]*"], { cwd });
  return tags.split(/\r?\n/).find(tag => /^v\d+\.\d+\.\d+$/.test(tag)) || null;
}

async function githubLatestMatches(tag, { cwd, env }) {
  const repository = env.GITHUB_REPOSITORY;
  if (!repository) {
    throw new Error("GITHUB_REPOSITORY is required to verify the latest published release.");
  }
  const latest = run("gh", ["api", `repos/${repository}/releases/latest`, "--jq", ".tag_name"], { cwd, env });
  return latest === tag;
}

async function reconcileLatest({
  cwd = process.cwd(),
  env = process.env,
  isLatestPublished = tag => githubLatestMatches(tag, { cwd, env })
} = {}) {
  const head = run("git", ["rev-parse", "HEAD"], { cwd, env });
  const tag = releaseTagAtHead(cwd);
  if (!tag) {
    return { outcome: "no-release-tag", tag: null, head };
  }

  const tagHead = run("git", ["rev-parse", `${tag}^{commit}`], { cwd, env });
  if (tagHead !== head) {
    throw new Error(`Release tag ${tag} does not identify workflow HEAD ${head}.`);
  }
  if (!(await isLatestPublished(tag))) {
    return { outcome: "not-latest-release", tag, head };
  }

  const remote = run("git", ["ls-remote", "--heads", "origin", "refs/heads/latest"], { cwd, env });
  const remoteHead = remote ? remote.split(/\s+/)[0] : null;
  if (remoteHead === head) {
    return { outcome: "unchanged", tag, head };
  }

  const lease = `--force-with-lease=refs/heads/latest:${remoteHead || ""}`;
  run("git", ["push", lease, "origin", `${head}:refs/heads/latest`], { cwd, env });
  return { outcome: "updated", tag, head };
}

if (require.main === module) {
  reconcileLatest()
    .then(result => {
      if (result.outcome === "updated") {
        console.log(`Updated latest to ${result.tag} (${result.head}).`);
      } else if (result.outcome === "unchanged") {
        console.log(`latest already identifies ${result.tag} (${result.head}).`);
      } else {
        console.log(`Did not update latest: ${result.outcome}.`);
      }
    })
    .catch(error => {
      console.error(error.message);
      process.exitCode = 1;
    });
}

module.exports = { reconcileLatest };
