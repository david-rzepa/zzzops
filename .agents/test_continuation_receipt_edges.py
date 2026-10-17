"""Focused receipt-edge controls for deferred submission continuations."""

from __future__ import annotations

import copy
import unittest

import test_workflow_journey as old


z = old.z


class ContinuationReceiptEdgeTests(unittest.TestCase):
    def setUp(self):
        self.engine = z._workflow.Workflow.__new__(z._workflow.Workflow)
        self.engine.repository = "owner/repo"

    def ref(self, value, number=100):
        identity = z._comment_store.digest(value)
        return self.engine.node_ref(identity, number)

    def edge(self, source, *, reconciles=1, mutate=None, mutate_context=None):
        number = source["issue"]
        candidate = {"operational": {"receipts": []}, "value": source["revision"] + 1}
        entry = {"operational": {"receipts": []}, "entry": source["revision"] + 1}
        steps = [{"kind": "checkpoint", "goal": number}]
        bindings = []
        if reconciles:
            steps.append({"kind": "reconcile", "goal": number,
                          "submission": {"operation": "reconcile", "expected_digest": None}})
            bindings.append({"kind": "target_envelope_digest", "step": 1})
        wrapper = {
            "type": "submission_continuation", "version": 1,
            "source_envelope": copy.deepcopy(source),
            "target_metadata": {key: value for key, value in source.items() if key != "payload"}
                               | {"revision": source["revision"] + 1},
            "candidate_payload": self.ref(candidate, number),
            "entry_candidate_payload": self.ref(entry, number),
            "response": {"next_steps": steps}, "bindings": bindings,
        }
        canonical_candidate = copy.deepcopy(candidate)
        canonical_entry = copy.deepcopy(entry)
        canonical_target_metadata = copy.deepcopy(wrapper["target_metadata"])
        if mutate:
            mutate(wrapper, candidate, entry)
        wrapper_ref = self.ref(wrapper, number)
        request = f"continuation-{source['revision']}"
        receipt = {"request": request, "payload": "sha256:" + "a" * 64,
                   "result": wrapper_ref}
        committed_candidate = canonical_candidate
        committed_candidate["operational"]["receipts"].append(receipt)
        committed_entry = canonical_entry
        committed_entry["operational"]["receipts"].append(receipt)
        target = {**canonical_target_metadata, "payload": self.ref(committed_candidate, number)}
        context = {
            "request_id": request, "request_hash": receipt["payload"],
            "source_hash": "sha256:" + "b" * 64, "human_hash": "sha256:" + "c" * 64,
            "root": "root", "response": wrapper_ref, "ownership": {}, "acquisition": {},
            "payload": target["payload"], "proof": {}, "source_envelope": source,
            "target_envelope": target, "entry_payload": self.ref(committed_entry, number),
            "continuation": copy.deepcopy(wrapper),
        }
        if mutate_context:
            mutate_context(context)
        records = [z._comment_store.ArtifactIndex([]).record(value) for value in
                   (candidate, entry, wrapper, committed_candidate)]
        transaction = "sha256:" + format(source["revision"] + 1, "064x")
        bodies = z._comment_store.pack_envelopes(
            {"goal": number, "transaction": transaction, "context": context}, records)
        index = z._comment_store.ArtifactIndex(
            [{"id": 1000 + offset + source["revision"] * 10, "body": body}
             for offset, body in enumerate(bodies)])
        return self.engine.node_receipt_edge(number, index, receipt), wrapper

    def ordinary_edge(self, *, malformed=False):
        source = self.source()
        target = {**source, "revision": 2, "payload": self.ref({"ordinary": 2})}
        response = {"next_steps": []} if not malformed else {"next_steps": "invalid"}
        response_ref = self.ref(response)
        receipt = {"request": "ordinary", "payload": "sha256:" + "e" * 64,
                   "result": response_ref}
        context = {
            "request_id": receipt["request"], "request_hash": receipt["payload"],
            "source_hash": "sha256:" + "f" * 64, "human_hash": "sha256:" + "1" * 64,
            "root": "root", "response": response_ref, "ownership": {}, "acquisition": {},
            "payload": target["payload"], "proof": {}, "source_envelope": source,
            "target_envelope": target, "entry_payload": self.ref({"entry": 2}),
        }
        transaction = "sha256:" + "2" * 64
        records = [z._comment_store.ArtifactIndex([]).record(response)]
        bodies = z._comment_store.pack_envelopes(
            {"goal": 100, "transaction": transaction, "context": context}, records)
        index = z._comment_store.ArtifactIndex(
            [{"id": 9000 + offset, "body": body} for offset, body in enumerate(bodies)])
        return self.engine.node_receipt_edge(100, index, receipt), response

    def source(self, revision=1, payload=None, number=100):
        return {"schema_version": 2, "repository": self.engine.repository, "issue": number,
                "revision": revision, "state": "open", "parent": None,
                "payload": payload or self.ref({"source": revision}, number)}

    def test_authenticates_zero_and_one_binding_without_materializing_digest(self):
        for reconciles in (0, 1):
            with self.subTest(reconciles=reconciles):
                edge, wrapper = self.edge(self.source(), reconciles=reconciles)
                self.assertIsNotNone(edge)
                self.assertEqual(wrapper["response"], edge["response"])
                if reconciles:
                    self.assertIsNone(wrapper["response"]["next_steps"][1]
                                      ["submission"]["expected_digest"])

    def test_continuation_edges_form_an_exact_reconciliation_chain(self):
        first, _ = self.edge(self.source())
        second, _ = self.edge(first["target"])
        self.assertEqual(first["target"], second["source"])
        self.assertEqual(3, second["target"]["revision"])

    def test_referenced_continuation_authenticates_only_exact_same_goal_response(self):
        edge, wrapper = self.edge(self.source(), mutate_context=lambda context:
                                  context.__setitem__('continuation', copy.deepcopy(context['response'])))
        self.assertEqual(wrapper['response'], edge['response'])
        for change in (
            lambda ref: {**ref, 'hash': 'sha256:' + '0' * 64},
            lambda ref: {**ref, 'uri': ref['uri'].replace('goal:100:', 'goal:101:')},
            lambda ref: {**ref, 'extra': True},
        ):
            with self.subTest(change=change):
                edge, _ = self.edge(self.source(), mutate_context=lambda context:
                                    context.__setitem__('continuation', change(context['response'])))
                self.assertIsNone(edge)

    def test_ordinary_receipt_response_is_preserved_and_malformed_shape_rejected(self):
        edge, response = self.ordinary_edge()
        self.assertEqual(response, edge["response"])
        self.assertIsNone(self.ordinary_edge(malformed=True)[0])

    def test_malformed_continuations_fail_closed(self):
        mutations = {
            "extra_key": lambda wrapper, _candidate, _entry: wrapper.__setitem__("extra", True),
            "missing_key": lambda wrapper, _candidate, _entry: wrapper.pop("bindings"),
            "bool_version": lambda wrapper, _candidate, _entry: wrapper.__setitem__("version", True),
            "wrong_version": lambda wrapper, _candidate, _entry: wrapper.__setitem__("version", 2),
            "source": lambda wrapper, _candidate, _entry: wrapper.__setitem__(
                "source_envelope", {**wrapper["source_envelope"], "revision": 99}),
            "target_metadata": lambda wrapper, _candidate, _entry: wrapper["target_metadata"]
                .__setitem__("revision", 99),
            "candidate": lambda wrapper, _candidate, _entry: wrapper.__setitem__(
                "candidate_payload", self.ref({"wrong": "candidate"})),
            "entry": lambda wrapper, _candidate, _entry: wrapper.__setitem__(
                "entry_candidate_payload", self.ref({"wrong": "entry"})),
            "candidate_ref_shape": lambda wrapper, _candidate, _entry: wrapper.__setitem__(
                "candidate_payload", "not-a-ref"),
            "entry_ref_shape": lambda wrapper, _candidate, _entry: wrapper.__setitem__(
                "entry_candidate_payload", []),
            "candidate_receipts_shape": lambda wrapper, candidate, _entry: (
                candidate["operational"].__setitem__("receipts", {}),
                wrapper.__setitem__("candidate_payload", self.ref(candidate))),
            "entry_operational_shape": lambda wrapper, _candidate, entry: (
                entry.__setitem__("operational", []),
                wrapper.__setitem__("entry_candidate_payload", self.ref(entry))),
            "nested_response": lambda wrapper, _candidate, _entry: wrapper.__setitem__("response", []),
            "steps_type": lambda wrapper, _candidate, _entry: wrapper["response"]
                .__setitem__("next_steps", {}),
            "step_element": lambda wrapper, _candidate, _entry: wrapper["response"]
                .__setitem__("next_steps", [None]),
            "submission_type": lambda wrapper, _candidate, _entry: wrapper["response"]
                ["next_steps"][1].__setitem__("submission", []),
            "bindings": lambda wrapper, _candidate, _entry: wrapper.__setitem__("bindings", []),
            "binding_kind": lambda wrapper, _candidate, _entry: wrapper["bindings"][0]
                .__setitem__("kind", "wrong"),
            "binding_index": lambda wrapper, _candidate, _entry: wrapper["bindings"][0]
                .__setitem__("step", 0),
            "binding_bool_index": lambda wrapper, _candidate, _entry: wrapper["bindings"][0]
                .__setitem__("step", True),
            "binding_float_index": lambda wrapper, _candidate, _entry: wrapper["bindings"][0]
                .__setitem__("step", 1.0),
            "binding_duplicate": lambda wrapper, _candidate, _entry: wrapper["bindings"]
                .append(copy.deepcopy(wrapper["bindings"][0])),
            "binding_goal": lambda wrapper, _candidate, _entry: wrapper["response"]["next_steps"][1]
                .__setitem__("goal", 999),
            "binding_operation": lambda wrapper, _candidate, _entry: wrapper["response"]["next_steps"][1]
                ["submission"].__setitem__("operation", "wrong"),
            "materialized": lambda wrapper, _candidate, _entry: wrapper["response"]["next_steps"][1]
                ["submission"].__setitem__("expected_digest", "sha256:" + "d" * 64),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                edge, _ = self.edge(self.source(), mutate=mutation)
                self.assertIsNone(edge)
        edge, _ = self.edge(self.source(), mutate_context=lambda context: context["continuation"]
                            .__setitem__("version", 2))
        self.assertIsNone(edge, "A context/wrapper mismatch must fail closed")
        for name, mutation in {
            "context_payload": lambda context: context.__setitem__("payload", self.ref({"wrong": 1})),
            "context_entry": lambda context: context.__setitem__("entry_payload", self.ref({"wrong": 2})),
            "context_target": lambda context: context["target_envelope"].__setitem__("state", "closed"),
        }.items():
            with self.subTest(name=name):
                self.assertIsNone(self.edge(self.source(), mutate_context=mutation)[0])
        edge, _ = self.edge(
            self.source(number=1),
            mutate=lambda wrapper, _candidate, _entry: wrapper["response"]["next_steps"][1]
            .__setitem__("goal", True),
        )
        self.assertIsNone(edge, "Boolean goal identity must not authenticate as goal 1")


if __name__ == "__main__":
    unittest.main()
