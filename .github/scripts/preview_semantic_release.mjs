import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, sep } from "node:path";
import { pathToFileURL } from "node:url";

import semanticRelease from "semantic-release";

const require = createRequire(import.meta.url);
const releaseConfig = require("../../release.config.cjs");
const repository = process.cwd();
const branch = execFileSync("git", ["branch", "--show-current"], {
  cwd: repository,
  encoding: "utf8"
}).trim();
const canonicalRemote = execFileSync("git", ["remote", "get-url", "origin"], {
  cwd: repository,
  encoding: "utf8"
}).trim();
const remoteUrl = new URL(canonicalRemote);
if (!remoteUrl.protocol.startsWith("http")) {
  throw new Error("Semantic release preview requires an HTTP(S) origin URL.");
}
const remotePath = remoteUrl.pathname.replace(/^\/+/, "");
const remotePrefix = `${remoteUrl.protocol}//${remoteUrl.host}/`;

if (!branch) {
  throw new Error("Semantic release preview requires a checked-out branch.");
}

const isolatedEnv = { ...process.env };
for (const name of [
    "CI",
    "BB_TOKEN",
    "BB_TOKEN_BASIC_AUTH",
    "BITBUCKET_TOKEN",
    "GIT_CREDENTIALS",
    "GITHUB_ACTION",
    "GITHUB_ACTIONS",
  "GITHUB_EVENT_NAME",
  "GITHUB_EVENT_PATH",
  "GITHUB_REF",
  "GITHUB_REPOSITORY",
  "GITHUB_RUN_ID",
  "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_TOKEN",
    "GITHUB_WORKSPACE",
    "GH_TOKEN",
    "GITLAB_TOKEN",
    "GL_TOKEN"
]) {
  delete isolatedEnv[name];
}

const previewRoot = mkdtempSync(join(tmpdir(), "zzzops-release-preview-"));
const localRemote = join(previewRoot, ...remotePath.split("/"));
let processGitConfig;

try {
  mkdirSync(dirname(localRemote), { recursive: true });
  execFileSync("git", [
    "-c",
    `safe.directory=${join(repository, ".git")}`,
    "clone",
    "--bare",
    repository,
    localRemote
  ], {
    stdio: ["ignore", "ignore", "inherit"]
  });
  const configuredCount = Number.parseInt(isolatedEnv.GIT_CONFIG_COUNT || "0", 10);
  const gitConfigIndex = Number.isNaN(configuredCount) ? 0 : configuredCount;
  isolatedEnv.GIT_CONFIG_COUNT = String(gitConfigIndex + 1);
  isolatedEnv[`GIT_CONFIG_KEY_${gitConfigIndex}`] = `url.${pathToFileURL(`${previewRoot}${sep}`).href}.insteadOf`;
  isolatedEnv[`GIT_CONFIG_VALUE_${gitConfigIndex}`] = remotePrefix;
  processGitConfig = {
    GIT_CONFIG_COUNT: process.env.GIT_CONFIG_COUNT,
    [`GIT_CONFIG_KEY_${gitConfigIndex}`]: process.env[`GIT_CONFIG_KEY_${gitConfigIndex}`],
    [`GIT_CONFIG_VALUE_${gitConfigIndex}`]: process.env[`GIT_CONFIG_VALUE_${gitConfigIndex}`]
  };
  process.env.GIT_CONFIG_COUNT = isolatedEnv.GIT_CONFIG_COUNT;
  process.env[`GIT_CONFIG_KEY_${gitConfigIndex}`] = isolatedEnv[`GIT_CONFIG_KEY_${gitConfigIndex}`];
  process.env[`GIT_CONFIG_VALUE_${gitConfigIndex}`] = isolatedEnv[`GIT_CONFIG_VALUE_${gitConfigIndex}`];
  const mirroredHeads = execFileSync("git", ["ls-remote", "--heads", canonicalRemote], {
    encoding: "utf8",
    env: isolatedEnv
  });
  if (!mirroredHeads.includes(`refs/heads/${branch}`)) {
    throw new Error(`Local semantic release mirror is missing branch ${branch}.`);
  }
  const result = await semanticRelease(
    {
      ...releaseConfig,
      branches: [branch],
      ci: false,
      dryRun: true,
      plugins: releaseConfig.plugins.slice(0, 2),
      repositoryUrl: canonicalRemote
    },
    {
      cwd: repository,
      env: isolatedEnv,
      stderr: process.stderr,
      stdout: process.stdout
    }
  );

  if (!result) {
    console.log("No semantic release is currently required.");
  }
} finally {
  if (processGitConfig) {
    for (const [name, value] of Object.entries(processGitConfig)) {
      if (value === undefined) {
        delete process.env[name];
      } else {
        process.env[name] = value;
      }
    }
  }
  rmSync(previewRoot, { recursive: true, force: true });
}
