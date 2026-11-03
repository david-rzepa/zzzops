# Approve the design for G{id} ({title})?

Guidance for the agent presenting this decision:
- Summarise the design in a few sentences in your own words. Then show the filter's summary (`filter`), each lens verdict, the findings that reopen the work, the notes grouped by lens, every skip with its reason, and any open finding recorded on a skipped node. Offer the design text (the `doc` artifact) for reading.
- Ask the question above and wait for the human's answer. Record the human's words verbatim in `quote`.
- If the human asks for changes, record them as findings on the design, in their words. A note that matters to the human is recorded as a finding in their words.
- Read the goal's spec (`zzzops show G --json`, `goal.spec`). If it ends with a `Project intent:` paragraph, show the paragraph verbatim next to the lens verdicts, and say that the owner accepted this departure from the project's intent at capture. The paragraph is only as good as the owner's quoted words in it: if approvals are delegated, the owner sees this item only when they answer or read it, so check that the paragraph quotes the owner.
