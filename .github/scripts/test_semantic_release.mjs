import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { PassThrough } from "node:stream";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { analyzeCommits } from "@semantic-release/commit-analyzer";
import { generateNotes } from "@semantic-release/release-notes-generator";
import semanticRelease from "semantic-release";

const require = createRequire(import.meta.url);
const releaseConfig = require("../../release.config.cjs");
const bundlePlugin = require("./semantic_release_bundle.cjs");
const releaseTestConfig = { ...releaseConfig, plugins: releaseConfig.plugins.slice(0, 2) };
const [analyzerName, analyzerOptions] = releaseTestConfig.plugins[0];
const [notesName, notesOptions] = releaseTestConfig.plugins[1];
const logger = { log() {}, error() {} };

assert.equal(analyzerName, "@semantic-release/commit-analyzer");
assert.equal(notesName, "@semantic-release/release-notes-generator");

test("marketplace bundles gate publication and become GitHub release assets", () => {
  assert.equal(releaseConfig.plugins[2], "./.github/scripts/semantic_release_bundle.cjs");
  const [githubPlugin, githubOptions] = releaseConfig.plugins[3];
  assert.equal(githubPlugin, "@semantic-release/github");
  assert.deepEqual(githubOptions.assets.map(({ path }) => path), [
    "dist/marketplace/zzzops-plugin-v*.zip",
    "dist/marketplace/zzzops-openai-submission-v*.zip",
    "dist/marketplace/zzzops-claude-plugin-v*.zip"
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
  const notes = await generateNotes(notesOptions, {
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
