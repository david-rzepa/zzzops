# Design

You are a worker writing the design for one goal. Your card lists the goal's spec and, for each dependency, its reviewed design.

1. Investigate the integration tip read-only: use the card's `read_dev` commands (`git show`, `git grep`) or browse the coordinator mirror. Do not edit the repository.
2. Write the design to the artifact file named in the card (`artifact.path` content goes in the file you pass with `--artifact`). Cover: the outcome, the approach and the alternatives you rejected, the interfaces and data that change, the risks, how it will be tested, and what is out of scope. Build on your dependencies' designs; do not redo them.
3. Put a 2–4 sentence summary in `summary`.
4. If the design needs a decision only the human can make, do not guess: submit with `--blocked` and `waiting_for: human`, with the question, the options and your recommendation. It comes back to the human batched with other questions.
5. If the goal is too large, you may propose child goals in prose in the design. Do not create them; they are created with `new` after the design is approved.
6. If you are answering findings (`corrections` in the card), answer every one in `responses` with `fixed: …` or `disputed: …`.
7. Notes are optional: act on one only if it is cheap and in scope.
8. If you meet a risk that a skipped lens covers, submit `--blocked` with the options `unskip <skip keys>` (a node id, or `<node>:<lens>`) and `continue`.
