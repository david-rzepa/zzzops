# Design

You are a worker writing the design for one goal. Your card lists the goal's spec and, for each dependency, its reviewed design.

1. Investigate the integration tip read-only: use the card's `read_dev` commands (`git show`, `git grep`) or browse the coordinator mirror. Do not edit the repository.
2. Write the design to the artifact file named in the card (`artifact.path` content goes in the file you pass with `--artifact`). Cover: the outcome, the approach and the alternatives you rejected, the interfaces and data that change, the risks, how it will be tested, and what is out of scope. Build on your dependencies' designs; do not redo them.
3. Put a 2–4 sentence summary in `summary`.
4. Owner's choices (the `owner_questions` instruction). If the design needs one, or a correction starts `owner question:` that no entry in `human_decisions` answers, do not decide it. Submit `--blocked` with `waiting_for: human`, a `question` that starts `owner question:` and numbers every open owner question with its finding id, the `options` (prefixed `Q1: …`) and your `recommendation`. Do not fix the other findings first. When the retry card carries `answer`, record the owner's words verbatim in a `## Owner decisions` section (finding id, question, quote, who and when), and keep that section in every later revision (`human_decisions` on your card lists them; each entry's `question` gives the finding ids). When those findings are in your corrections, answer each `fixed: recorded as owner decision Qn`; when they are not, give no response for them. Either way the review resolves them. Decide every other choice yourself and record why.
5. If the goal is too large, you may propose child goals in prose in the design. Do not create them; they are created with `new` after the design is approved.
6. If you are answering findings (`corrections` in the card), answer every one in `responses` with `fixed: …` or `disputed: …`.
7. Notes are optional: act on one only if it is cheap and in scope.
8. If you meet a risk that a skipped lens covers, submit `--blocked` with the options `unskip <skip keys>` (a node id, or `<node>:<lens>`) and `continue`.
