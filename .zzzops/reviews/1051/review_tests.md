# G1051 earlier-PR recovery test review

The new real local-Git/fake-provider journeys distinguish an older merged PR from a newly approved descendant: one requires an actual later merge and verifies its distinct PR and source content, while the other puts the old PR first in the provider result and requires recovery to record the exact approved head's already-observed merge without a second production merge. The existing two externally merged unapproved-head scenarios remain in the focused run and check that actual evidence is retained and automatic forwarding pauses.

I independently ran all four cases at exact checkpoint `1053e5f`; all passed in 23.957 seconds, consistent with the reported 24.022 seconds. The repeated genuine local release setup accounts for the cost; no fixed long sleep was introduced. These are local bare Git and fake-provider results, not evidence of hosted GitHub protected-branch behavior, which remains a separate staging gate. No new material test findings.
