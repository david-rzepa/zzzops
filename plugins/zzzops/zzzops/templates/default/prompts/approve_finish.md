# Finish G{id} ({title}) at {sync}?

Guidance for the agent presenting this decision:
- Finishing merges the line branch, at the synced tip shown above, into the production branch and back into the integration branch (a hotfix also goes into the open release branch). The line branch is kept. Tags, versions and deployment are the project's own steps.
- Any later merge into the line moves its tip and asks this question again. Record the human's words verbatim in `quote`.
