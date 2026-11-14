import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { PassThrough } from "node:stream";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

import { analyzeCommits } from "@semantic-release/commit-analyzer";
import semanticRelease from "semantic-release";

const require = createRequire(import.meta.url);
const notesPluginPath = fileURLToPath(new URL("./semantic_release_notes.cjs", import.meta.url));
const releaseConfig = require("../../release.config.cjs");
const bundlePlugin = require("./semantic_release_bundle.cjs");
const notesPlugin = require("./semantic_release_notes.cjs");
const { reconcileLatest } = require("./sync_latest_release_branch.cjs");
const releaseTestConfig = { ...releaseConfig, plugins: releaseConfig.plugins.slice(0, 2) };
const [analyzerName, analyzerOptions] = releaseTestConfig.plugins[0];
const [notesName, notesOptions] = releaseTestConfig.plugins[1];
const logger = { log() {}, error() {} };

assert.equal(analyzerName, "@semantic-release/commit-analyzer");
assert.equal(notesName, "./.github/scripts/semantic_release_notes.cjs");
assert.equal(notesPlugin.generatorPackage, "@semantic-release/release-notes-generator");

test("the required OpenAI bundle gates publication and becomes a release asset", () => {
  assert.equal(releaseConfig.plugins[2], "./.github/scripts/semantic_release_bundle.cjs");
  const [githubPlugin, githubOptions] = releaseConfig.plugins[3];
  assert.equal(githubPlugin, "@semantic-release/github");
  assert.deepEqual(githubOptions.assets.map(({ path }) => path), [
    "dist/marketplace/zzzops-plugin-v*.zip"
  ]);
});

test("marketplace preparation failure aborts semantic release", async () => {
  await assert.rejects(
    bundlePlugin.prepare({}, {
      cwd: process.cwd(),
      logger,
      nextRelease: { version: "not-a-version", notes: "Release notes" }
    }),
    /Marketplace bundle preparation failed/
  );
});

function commits(...messages) {
  return messages.map((message, index) => ({
    hash: String(index + 1).repeat(40),
    message
  }));
}

test("semantic commits select the highest release type", async () => {
  assert.equal(await analyzeCommits(analyzerOptions, { commits: commits("docs: explain"), logger }), null);
  assert.equal(await analyzeCommits(analyzerOptions, { commits: commits("fix: repair"), logger }), "patch");
  assert.equal(await analyzeCommits(analyzerOptions, { commits: commits("fix: repair", "feat: add queue"), logger }), "minor");
  assert.equal(
    await analyzeCommits(analyzerOptions, {
      commits: commits("feat: add queue", "fix!: remove legacy API"),
      logger
    }),
    "major"
  );
  assert.equal(
    await analyzeCommits(analyzerOptions, {
      commits: commits("fix: alter protocol\n\nBREAKING CHANGE: clients must reconnect"),
      logger
    }),
    "major"
  );
});

test("release notes distinguish breaking changes, features, fixes, and performance", async () => {
  const notes = await notesPlugin.generateNotes(notesOptions, {
    branch: { name: "main" },
    commits: commits(
      "fix!: remove legacy API",
      "feat: zebra queue",
      "feat: add queue",
      "fix: repair timeout",
      "perf: reduce scans",
      "docs: explain releases"
    ),
    lastRelease: { gitTag: "v1.0.0", gitHead: "0".repeat(40), version: "1.0.0" },
    logger,
    nextRelease: { gitTag: "v2.0.0", gitHead: "f".repeat(40), version: "2.0.0" },
    options: { repositoryUrl: "https://github.com/david-rzepa/zzzops" }
  });

  for (const text of ["BREAKING CHANGES", "Features", "Bug Fixes", "Performance Improvements", "remove legacy API", "add queue", "zebra queue", "repair timeout", "reduce scans"]) {
    assert.match(notes, new RegExp(text));
  }
  assert.doesNotMatch(notes, /Documentation|explain releases/);
  assert.doesNotMatch(notes, /Reverts/);
  assert.ok(notes.indexOf("Features") < notes.indexOf("Bug Fixes"));
  assert.ok(notes.indexOf("Bug Fixes") < notes.indexOf("Performance Improvements"));
  assert.ok(notes.indexOf("add queue") < notes.indexOf("zebra queue"));
});

test("release notes collapse structurally introduced commits into canonical PR merges", async () => {
  const root = mkdtempSync(join(tmpdir(), "zzzops-release-notes-"));
  const work = join(root, "work");
  const git = (...args) => execFileSync("git", args, {
    cwd: work,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"]
  }).trim();
  const commit = message => git("commit", "--allow-empty", "-m", message);
  const mergePullRequest = (branch, messages, title) => {
    git("switch", "-c", branch);
    for (const message of messages) commit(message);
    git("switch", "main");
    git("merge", "--no-ff", branch, "-m", title);
  };

  execFileSync("git", ["init", "--initial-branch=main", work], { stdio: "ignore" });
  git("config", "user.name", "ZzzOps test");
  git("config", "user.email", "test@zzzops.invalid");
  commit("chore: release baseline");
  git("tag", "v1.0.0");
  mergePullRequest("feature", ["feat: add queue", "fix: repair internal queue"], "feat: add queue (#42)");
  mergePullRequest("fix", ["fix: repair timeout"], "fix: repair timeout (#43)");
  mergePullRequest("performance", ["perf: reduce scans"], "perf: reduce scans (#44)");
  commit("feat: add queue");

  const fields = execFileSync(
    "git",
    ["log", "v1.0.0..HEAD", "--format=%H%x00%B%x00"],
    { cwd: work, encoding: "utf8" }
  ).split("\0").map(value => value.trim()).filter(Boolean);
  const history = [];
  for (let index = 0; index < fields.length; index += 2) {
    history.push({ hash: fields[index], message: fields[index + 1] });
  }

  const notes = await notesPlugin.generateNotes(notesOptions, {
    branch: { name: "main" },
    commits: history,
    cwd: work,
    lastRelease: { gitTag: "v1.0.0", gitHead: "0".repeat(40), version: "1.0.0" },
    logger,
    nextRelease: { gitTag: "v1.1.0", gitHead: "f".repeat(40), version: "1.1.0" },
    options: { repositoryUrl: "https://github.com/david-rzepa/zzzops" }
  });

  assert.equal(notes.match(/add queue/g)?.length, 2, "keep the PR merge and unrelated direct commit");
  assert.equal(notes.match(/repair timeout/g)?.length, 1);
  assert.equal(notes.match(/reduce scans/g)?.length, 1);
  assert.doesNotMatch(notes, /repair internal queue/);
  for (const pull of [42, 43, 44]) assert.match(notes, new RegExp(`issues/${pull}`));
});

test("release-note canonicalization never hides an unrepresented breaking change", () => {
  const commits = [
    { hash: "m".repeat(40), message: "fix: summarize protocol work (#45)" },
    { hash: "b".repeat(40), message: "fix: alter protocol\n\nBREAKING CHANGE: clients must reconnect" }
  ];
  const runGit = (_cwd, command, ...args) => {
    if (command === "show") return `${"1".repeat(40)} ${"2".repeat(40)}`;
    if (command === "rev-list") return commits[1].hash;
    throw new Error(`Unexpected git command: ${[command, ...args].join(" ")}`);
  };

  assert.deepEqual(notesPlugin.canonicalReleaseCommits(commits, { cwd: ".", runGit }), commits);
});

test("release-note canonicalization ignores non-releasing and single-parent commits", () => {
  const commits = [
    { hash: "c".repeat(40), message: "chore: integrate feature (#46)" },
    { hash: "f".repeat(40), message: "feat: retain visible feature" },
    { hash: "d".repeat(40), message: "fix: direct correction (#47)" }
  ];
  const runGit = (_cwd, command, ...args) => {
    if (command === "show") return "1".repeat(40);
    throw new Error(`Unexpected git command: ${[command, ...args].join(" ")}`);
  };

  assert.deepEqual(notesPlugin.canonicalReleaseCommits(commits, { cwd: ".", runGit }), commits);
});

test("semantic-release dry-run honors the latest tag boundary and does not publish", async () => {
  const root = mkdtempSync(join(tmpdir(), "zzzops-semantic-release-"));
  const remote = join(root, "remote.git");
  const work = join(root, "work");
  const git = (cwd, ...args) => execFileSync("git", args, { cwd, stdio: "ignore" });

  execFileSync("git", ["init", "--bare", "--initial-branch=main", remote], { stdio: "ignore" });
  execFileSync("git", ["clone", remote, work], { stdio: "ignore" });
  git(work, "config", "user.name", "ZzzOps test");
  git(work, "config", "user.email", "test@zzzops.invalid");
  git(work, "commit", "--allow-empty", "-m", "feat: before boundary");
  git(work, "tag", "v1.0.0");
  git(work, "commit", "--allow-empty", "-m", "docs: ignored after boundary");
  git(work, "commit", "--allow-empty", "-m", "fix: included after boundary");
  git(work, "push", "--follow-tags", "origin", "main");

  const isolatedEnv = { ...process.env };
  for (const name of [
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_REF",
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
    "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_WORKSPACE"
  ]) {
    delete isolatedEnv[name];
  }

  const result = await semanticRelease(
    {
      ...releaseTestConfig,
      plugins: [releaseTestConfig.plugins[0], [notesPluginPath, notesOptions]],
      ci: false,
      dryRun: true,
      repositoryUrl: pathToFileURL(remote).href
    },
    {
      cwd: work,
      env: isolatedEnv,
      stderr: new PassThrough(),
      stdout: new PassThrough()
    }
  );

  assert.equal(result.lastRelease.gitTag, "v1.0.0");
  assert.equal(result.nextRelease.type, "patch");
  assert.equal(result.nextRelease.version, "1.0.1");
  assert.deepEqual(result.commits.map(({ subject }) => subject), [
    "fix: included after boundary",
    "docs: ignored after boundary"
  ]);
  assert.match(result.nextRelease.notes, /included after boundary/);
  assert.doesNotMatch(result.nextRelease.notes, /before boundary|ignored after boundary/);
  const unpublishedTag = spawnSync(
    "git",
    ["--git-dir", remote, "show-ref", "--verify", "refs/tags/v1.0.1"],
    { stdio: "ignore" }
  );
  assert.notEqual(unpublishedTag.status, 0);
});

test("main release workflow reconciles latest after semantic-release succeeds", () => {
  const workflow = readFileSync(".github/workflows/release.yml", "utf8");
  const publish = workflow.indexOf("run: npx semantic-release");
  const reconcile = workflow.indexOf("run: node .github/scripts/sync_latest_release_branch.cjs");
  assert.ok(publish >= 0);
  assert.ok(reconcile > publish);
});

test("latest branch advances only to the current published release and retries safely", async () => {
  const root = mkdtempSync(join(tmpdir(), "zzzops-latest-release-"));
  const remote = join(root, "remote.git");
  const work = join(root, "work");
  const git = (cwd, ...args) => execFileSync("git", args, { cwd, encoding: "utf8" }).trim();

  execFileSync("git", ["init", "--bare", "--initial-branch=main", remote], { stdio: "ignore" });
  execFileSync("git", ["clone", remote, work], { stdio: "ignore" });
  git(work, "config", "user.name", "ZzzOps test");
  git(work, "config", "user.email", "test@zzzops.invalid");
  git(work, "commit", "--allow-empty", "-m", "feat: first release");
  git(work, "tag", "v1.0.0");
  git(work, "push", "--follow-tags", "origin", "main");

  const first = await reconcileLatest({ cwd: work, isLatestPublished: async tag => tag === "v1.0.0" });
  assert.deepEqual(first, { outcome: "updated", tag: "v1.0.0", head: git(work, "rev-parse", "HEAD") });
  assert.equal(git(remote, "rev-parse", "refs/heads/latest"), git(work, "rev-parse", "HEAD"));

  const retry = await reconcileLatest({ cwd: work, isLatestPublished: async () => true });
  assert.deepEqual(retry, { outcome: "unchanged", tag: "v1.0.0", head: git(work, "rev-parse", "HEAD") });

  git(work, "commit", "--allow-empty", "-m", "feat: second release");
  git(work, "tag", "v2.0.0");
  git(work, "push", "--follow-tags", "origin", "main");
  const secondHead = git(work, "rev-parse", "HEAD");

  const unpublished = await reconcileLatest({ cwd: work, isLatestPublished: async () => false });
  assert.deepEqual(unpublished, { outcome: "not-latest-release", tag: "v2.0.0", head: secondHead });
  assert.notEqual(git(remote, "rev-parse", "refs/heads/latest"), secondHead);

  const second = await reconcileLatest({ cwd: work, isLatestPublished: async tag => tag === "v2.0.0" });
  assert.deepEqual(second, { outcome: "updated", tag: "v2.0.0", head: secondHead });
  assert.equal(git(remote, "rev-parse", "refs/heads/latest"), secondHead);
});

test("latest reconciliation is a no-op when the workflow commit has no release tag", async () => {
  const root = mkdtempSync(join(tmpdir(), "zzzops-latest-no-release-"));
  const remote = join(root, "remote.git");
  const work = join(root, "work");
  const git = (cwd, ...args) => execFileSync("git", args, { cwd, encoding: "utf8" }).trim();

  execFileSync("git", ["init", "--bare", "--initial-branch=main", remote], { stdio: "ignore" });
  execFileSync("git", ["clone", remote, work], { stdio: "ignore" });
  git(work, "config", "user.name", "ZzzOps test");
  git(work, "config", "user.email", "test@zzzops.invalid");
  git(work, "commit", "--allow-empty", "-m", "docs: no release");
  git(work, "push", "origin", "main");

  let queried = false;
  const result = await reconcileLatest({
    cwd: work,
    isLatestPublished: async () => {
      queried = true;
      return true;
    }
  });

  assert.deepEqual(result, { outcome: "no-release-tag", tag: null, head: git(work, "rev-parse", "HEAD") });
  assert.equal(queried, false);
  const latest = spawnSync("git", ["--git-dir", remote, "show-ref", "--verify", "refs/heads/latest"]);
  assert.notEqual(latest.status, 0);
});
