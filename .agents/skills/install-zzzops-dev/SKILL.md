---
name: install-zzzops-dev
description: Install an unreleased ZzzOps checkout through its local Codex marketplace. Use for fake installs, development installs, local tests, or refreshing changed skills.
---

# Dev install

From the intended checkout run:

```sh
python .agents/skills/install-zzzops-dev/scripts/install_dev.py
```

It validates, cache-busts, installs, and restores the manifest. Ask before replacing another checkout's marketplace registration. Report the source and tell the user to start a new task.
