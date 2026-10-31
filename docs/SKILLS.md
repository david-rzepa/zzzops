# Skills

ZzzOps ships three skills. Each drives the `zzzops` CLI ([reference](../plugins/zzzops/zzzops/references/CLI_USAGE.md)).

| Skill | Use it to |
|---|---|
| `$bootstrap-zzzops-repository` | Initialize a repository: policy, workflow, prompts, harness and GitHub settings ([Initialization](INITIALIZATION.md)). |
| `$add-zzzops-goal` | Capture a goal's spec with you and start its design at once. |
| `$execute-zzzops` | Work through all ready phases: dispatch workers, run the Git and GitHub operations, and present your decisions in batches. In unattended runs it sleeps until the next time something can change (`wake_at`). |

Everything else is a CLI verb: holding or cancelling a goal, adding a dependency or a skip, reopening a node, or answering a decision.
