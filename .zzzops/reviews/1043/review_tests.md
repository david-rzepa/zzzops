# G1043 independent test review — AST portability

Decision: **approved**. No prior open findings and no new findings.

Read the complete task card and the exact two-file correction at tests checkpoint `932af741d3a7475c8ec63b8141549fa91330db30`, against prior approved tests `5907d057e5a713e015635acecf85a33658106f49`. Approved design revision 3 is unchanged. Product source remains reverted: checkpoint-vs-prior-tests diff contains only `.agents/test_engine_cost_context.py` and `.agents/fixtures/g1043_property_ast.json`, with no property algorithm or implementation paths.

The replacement guard is a structural serialization of AST node kinds, named fields, ordered list children and scalar values. It omits only unset None/default-empty list representation, with an explicit exception retaining Constant.value=None. False, empty string and zero are retained distinctly. It contains no Python-version branches, skips or opaque version-specific expected digests. This removes the parser/dump formatting dependency while preserving the audited semantic coverage.

Independently verified fixture provenance: `git rev-parse de5640d1c5909ea924450aeea6450497a78946f6:.agents/test_engine_property.py` is `ebfd8a8c52a62ba1580b7f7da04d5c3aa18068ae`; recomputing the new canonical hashes from that immutable blob exactly matches `semantics` in the fixture. The current property file is byte-identical to that immutable source. The new expected values are therefore anchored to the audited baseline rather than self-derived from an edited current algorithm.

The three negative controls actually replace present source text to weaken seeds (25 to 1), per-seed steps (80 to 1) and the next-output size assertion; each asserts that source changed and canonical hashes no longer match. Independently ran the guard and all subcontrols under Python 3.10 and 3.14: **two tests in 0.015 s on each interpreter**, both green (process wall 0.071/0.090 s). Additional tiny direct probes verify distinct serialization for literal None/False/empty string/zero, preservation of statement order and Expr-versus-Return node kinds, and equivalence only for missing versus default-empty Call.args/keywords representation.

The previously reviewed local runner, CPU/lane/timeout arithmetic, bounded same-source two-scope baselines, real measurement launcher, context/card plumbing and other substantive assertions remain unchanged. No full or broad suite was repeated and no performance claim is inferred from these focused guard timings. `git diff --check` passes.

## Dogfood notes

None.
