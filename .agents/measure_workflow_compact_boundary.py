#!/usr/bin/env python3
"""Measure complete visible full/compact synthetic public workflow journeys."""

import json
from pathlib import Path
import sys

try:
    import tiktoken
except ImportError as exc:
    raise SystemExit("Install tiktoken in a temporary environment to run this measurement") from exc

sys.path.insert(0, str(Path(__file__).parent))
from test_evidence_dag_journeys import EvidenceDagPublicTests


def journey(mode):
    case = EvidenceDagPublicTests("test_compact_minimal_execute_review_and_root_approval_journey")
    case.setUp()
    visible = []
    try:
        session = case.session

        def call(payload=None):
            response = session.call(100, payload, response=mode)
            visible.append({"input": payload, "output": response})
            return response

        def execute(name, value, actor):
            ready = next(row for row in call()["next_steps"] if row.get("node", {}).get("node") == name)
            policy_text = Path(ready["policy"]["path"]).read_text(encoding="utf-8")
            visible.append({"selective_read": {"path": ready["policy"]["path"], "content": policy_text}})
            receipt = json.loads(policy_text)["policy_receipt"]
            if mode == "compact":
                start = {"context": ready["context"], "operation": "start", "node": ready["node"],
                         "policy_receipt": receipt, "request_id": "measure-start-" + name}
            else:
                start = {**ready["start"], "policy_receipt": receipt, "request_id": "measure-start-" + name}
            acquired = next(row for row in call(start)["next_steps"] if row.get("node", {}).get("node") == name)
            if acquired["lease"]["worker"] is None:
                if mode == "compact":
                    bind = {"context": acquired["context"], "operation": "bind", "node": acquired["node"],
                            "actor": actor, "policy_receipt": receipt, "request_id": "measure-bind-" + name}
                else:
                    bind = {**acquired["bind"], "actor": actor, "policy_receipt": receipt,
                            "request_id": "measure-bind-" + name}
                call(bind)
            if mode == "compact":
                submit = {"context": acquired["context"], "operation": "submit", "node": acquired["node"],
                          "actor": actor, "request_id": "measure-submit-" + name,
                          "outputs": {"value": value}}
            else:
                submit = {**acquired["submission"], "lease": acquired["lease"]["token"], "actor": actor,
                          "request_id": "measure-submit-" + name, "outputs": {"value": value}}
            call(submit)
            return submit

        for arguments in (("produce", "subject", "producer"), ("review_a", "approved-a", "reviewer-a"),
                          ("review_b", "approved-b", "reviewer-b"), ("finish", "approved", "root-thread")):
            last_input = execute(*arguments)
        visible.append({"input": last_input, "output": session.call(100, last_input, response=mode)})
        return visible
    finally:
        case.tearDown()
        case.doCleanups()


def main():
    encoding = tiktoken.get_encoding("o200k_base")
    report = {"tokenizer": f"tiktoken/{tiktoken.__version__}", "encoding": "o200k_base", "modes": {}}
    for mode in ("full", "compact"):
        visible = journey(mode)
        raw = json.dumps(visible, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        report["modes"][mode] = {
            "events": len(visible), "visible_bytes": len(raw.encode("utf-8")),
            "visible_tokens": len(encoding.encode(raw)),
        }
    full, compact = report["modes"]["full"], report["modes"]["compact"]
    report["token_reduction_percent"] = round(
        (1 - compact["visible_tokens"] / full["visible_tokens"]) * 100, 1,
    )
    report["budgets"] = {"minimum_token_reduction_percent": 10.0, "maximum_extra_events": 0}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    if compact["events"] > full["events"]:
        raise SystemExit("compact journey added a mandatory invocation/read event")
    if report["token_reduction_percent"] < 10.0:
        raise SystemExit("compact journey token reduction fell below the justified 10% floor")


if __name__ == "__main__":
    main()
