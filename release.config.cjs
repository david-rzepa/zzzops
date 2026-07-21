const analyzer = [
  "@semantic-release/commit-analyzer",
  {
    preset: "conventionalcommits",
    releaseRules: [
      { breaking: true, release: "major" },
      { type: "feat", release: "minor" },
      { type: "fix", release: "patch" },
      { type: "perf", release: "patch" },
      { type: "revert", release: "patch" },
      { type: "docs", release: false },
      { type: "style", release: false },
      { type: "chore", release: false },
      { type: "refactor", release: false },
      { type: "test", release: false },
      { type: "build", release: false },
      { type: "ci", release: false }
    ],
    presetConfig: {}
  }
];

const notes = [
  "@semantic-release/release-notes-generator",
  {
    preset: "conventionalcommits",
    presetConfig: {},
    writerOpts: {
      commitsSort: ["subject", "scope"]
    }
  }
];

module.exports = {
  branches: ["main"],
  tagFormat: "v${version}",
  plugins: [analyzer, notes, "@semantic-release/github"]
};
