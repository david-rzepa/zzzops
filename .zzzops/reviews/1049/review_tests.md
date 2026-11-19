# G1049 transaction-guard test review

Approved. The added regression uses the existing real `Session.write_goals` extra-ref update seam to attempt an otherwise-unlisted combined goal/work transaction without a gate. It checks structured refusal and verifies both actual remote refs remain unchanged. The registered base operation is a positive control that advances the work ref through a valid gated public route. Existing lifecycle and barrier coverage remains intact.

I independently ran the unlisted transaction case (1.031 s). As expected on the old engine, it fails earlier with `engine_too_old` because the new capability is absent; implementation validation must run it to the gate assertion. The author measured the two changed tests at 2.204 s and the full real-Git suite at 158.122 s red. That cost warrants a green measurement, while realistic ref transactions and fencing justify integration coverage.
