# Incidental entropy observations

This is guidance for evidence discovered during ordinary phase work, not a separate
audit, scheduler, or backlog. Never pause the current assignment to inspect adjacent
code for decay.

The mandatory implementation-review phase owns entropy review. Its immutable review
artifact and submission must state either concrete findings or the inspected scope
supporting `no_findings`. Handle each observed fact as follows:

- For in-scope decay, request correction through the review evidence and let the
  public workflow return work to the assigned executor. Submit `fixed` only after
  independently reviewing replacement evidence and the affected verification.
- For out-of-scope decay, preserve one bounded fact with repository-relative paths
  and observed evidence. Return it to the root coordinator so a linked follow-up goal
  can be created through the public capture workflow. Submit `follow_up` only with
  those durable goal identifiers.
- When inspection of the assigned implementation and its direct verification finds
  no decay, submit `no_findings` with that inspected scope. Do not call the repository
  broadly clean.

Do not include secrets, raw sensitive data, speculative solutions, invented
acceptance criteria, or unsupported priority. In-scope defects remain part of the
current goal. Test-discovered out-of-scope bugs still follow PROJECT test-bug policy.

Suggestion/refill may independently validate current repository evidence through
its public workflow. It does not start another entropy-review pass, and neither a
review finding nor a suggestion grants authority to create a goal without the
returned capture and approval contract.
