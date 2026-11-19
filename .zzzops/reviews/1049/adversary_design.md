# Adversarial design re-review

The revised design resolves the blocked-producer bypass: a preserved consumer cannot submit any checkpoint while its producer is blocked, including when `blocked_findings` is off and the changed work tip is already published. Its real-Git regression specifically covers the empty per-commit range and then checks both guards after producer acceptance. The additional attempt segments also address paths introduced during a blocked producer attempt without resorting to an unscoped base-to-tip diff.

The implementation review should verify that every checkpoint submission route actually enforces the refusal, and that pending segment objects and attribution survive record and lease lifecycle changes. No additional material finding is raised on the design.
