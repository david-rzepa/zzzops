# G1050 test re-review

The corrected checkpoint adds real CLI cases for live leases, waived/unreviewed and independently reviewed scaffold transitions, a real red-to-green behavior journey, child retry/restoration and unavailable objects, and policy-preview/adoption scenarios. Those materially address the earlier findings. The reported full red suite took 38 seconds, proportionate to its isolated Git/CLI scenarios; it does not yet prove green behavior.

I independently ran the unavailable child object database and old-review preview cases. Both fail on current code as expected: the first emits an unhandled Git traceback rather than an actionable provenance error, and the second has no shipped scaffold node to preview. Focused run: 2.881 seconds.

One preservation contract still lacks a discriminating assertion. A test-authoring rename/deletion must freeze absence at the former name as well as content at the new name; implementation-time rename of an existing test does not exercise that baseline. The ancestor-rewind test also changes protected contents, so it cannot distinguish a provenance check from ordinary entry equality. Cover those with real child repos before implementing.
