# Skills

ZzzOps ships four skills. Each drives the `zzzops` CLI ([reference](../plugins/zzzops/zzzops/references/CLI_USAGE.md)).

| Skill | Use it to |
|---|---|
| `$bootstrap-zzzops-repository` | Initialize a repository: policy, workflow, prompts, harness and GitHub settings ([Initialization](INITIALIZATION.md)). |
| `$add-zzzops-goal` | Capture a goal's spec with you and start its design at once. |
| `$migrate-zzzops-repository` | Move a repository that still has pre-reset ZzzOps state (an old policy, old goal issues or install files) to the new engine: inventory, triage, one go-ahead, then close or migrate each issue. `next` and `validate` point to it with their `legacy` item. |
| `$execute-zzzops` | Work through all ready phases: dispatch workers, run the Git and GitHub operations, and present your decisions in batches. In unattended runs it sleeps until the next time something can change (`wake_at`). |

Everything else is a CLI verb: holding or cancelling a goal, adding a dependency or a skip, reopening a node, or answering a decision.
