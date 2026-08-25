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
  "./.github/scripts/semantic_release_notes.cjs",
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
  plugins: [
    analyzer,
    notes,
    "./.github/scripts/semantic_release_bundle.cjs",
    [
      "@semantic-release/github",
      {
        assets: [
          { path: "dist/marketplace/zzzops-plugin-v*.zip", label: "OpenAI portal skills bundle" },
          { path: "dist/marketplace/zzzops-openai-submission-v*.zip", label: "OpenAI submission packet" },
          { path: "dist/marketplace/zzzops-claude-plugin-v*.zip", label: "Claude Code plugin bundle" }
        ]
      }
    ]
  ]
};
