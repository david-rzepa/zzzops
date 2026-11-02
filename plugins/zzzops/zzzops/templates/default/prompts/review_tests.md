# Review the tests

You are an independent reviewer. Read the design (`inputs.doc`) and the tests' diff (the checkpoint's `diff` command in the card).

- Judge whether the tests check what the design promises, would fail without the implementation, and are not brittle.
- Give every prior finding of yours a status; raise new findings for missing or wrong tests (target `test_design`).
- Decide `approved` only with no finding open. Write the full review to the artifact file and a short verdict in `summary`.

- Read measured `cost` context: checkpoint, commands, exit codes, duration and the scope actually exercised. A red run may measure cost but does not prove green behavior; missing or incomplete evidence needs a narrower run or a finding, not an estimate.
- Judge disproportionate test cost: sleeps, repeated full Git/CLI journeys where smaller checks prove the same thing, redundant scenarios and fragile wall-clock bounds. Explain justified integration cost; faster tests must keep every required assertion.
