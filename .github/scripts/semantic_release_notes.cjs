const { execFileSync } = require("node:child_process");

const generatorPackage = "@semantic-release/release-notes-generator";
const releasePullRequest = /^(?:feat|fix|perf|revert)(?:\([^)]+\))?!?: .+ \(#\d+\)$/;
const breakingHeader = /^[a-z]+(?:\([^)]+\))?!:/i;
const breakingFooter = /^BREAKING[ -]CHANGES?:/im;

function git(cwd, ...args) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"]
  }).trim();
}

function subject(message) {
  return message.split(/\r?\n/, 1)[0].trim();
}

function isBreaking(message) {
  return breakingHeader.test(subject(message)) || breakingFooter.test(message);
}

function canonicalReleaseCommits(commits, { cwd = process.cwd(), runGit = git } = {}) {
  const byHash = new Map(commits.map(commit => [commit.hash, commit]));
  const omitted = new Set();

  for (const merge of commits) {
    if (!releasePullRequest.test(subject(merge.message))) continue;

    const parents = runGit(cwd, "show", "-s", "--format=%P", merge.hash).split(/\s+/).filter(Boolean);
    if (parents.length !== 2) continue;

    const introduced = runGit(cwd, "rev-list", parents[1], `^${parents[0]}`)
      .split(/\s+/)
      .filter(hash => byHash.has(hash));
    if (introduced.length === 0) continue;

    if (!isBreaking(merge.message) && introduced.some(hash => isBreaking(byHash.get(hash).message))) continue;
    for (const hash of introduced) omitted.add(hash);
  }

  return commits.filter(commit => !omitted.has(commit.hash));
}

async function generateNotes(pluginConfig, context) {
  const generator = await import(generatorPackage);
  const commits = canonicalReleaseCommits(context.commits, { cwd: context.cwd });
  return generator.generateNotes(pluginConfig, { ...context, commits });
}

module.exports = { canonicalReleaseCommits, generateNotes, generatorPackage };
