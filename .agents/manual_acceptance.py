"""Small cross-platform shim for the tracked human acceptance plan."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

START = "<!-- zzzops-acceptance-plan\n"
END = "\nzzzops-acceptance-plan -->"


def digest(repo: Path, paths: list[str]) -> str:
    value = hashlib.sha256()
    for relative in sorted(paths):
        path = repo / relative
        value.update(relative.encode())
        value.update(b"\0")
        value.update(path.read_bytes() if path.is_file() else b"<missing>")
        value.update(b"\0")
    return value.hexdigest()


def load(plan_path: Path) -> tuple[str, dict, int, int]:
    text = plan_path.read_text(encoding="utf-8")
    start = text.index(START) + len(START)
    end = text.index(END, start)
    return text, json.loads(text[start:end]), start, end


def save(plan_path: Path, text: str, data: dict, start: int, end: int) -> None:
    plan_path.write_text(text[:start] + json.dumps(data, separators=(",", ":")) + text[end:], encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("next", "check", "audit", "coverage"))
    parser.add_argument("item", nargs="?")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--plan", type=Path, default=Path("docs/ACCEPTANCE_TEST_PLAN.md"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    plan = (repo / args.plan).resolve()
    text, data, start, end = load(plan)
    items = data["items"]
    if args.command == "coverage":
        required = [
            "plugins/zzzops/plugin.json", ".agents/plugins/marketplace.json",
            "plugins/zzzops/skills/add-zzzops-goal", "plugins/zzzops/skills/bootstrap-zzzops-repository",
            "plugins/zzzops/skills/migrate-to-zzzops",
            "plugins/zzzops/skills/review-zzzops-policy", "plugins/zzzops/skills/suggest-zzzops-work",
            "plugins/zzzops/skills/execute-zzzops", "plugins/zzzops/skills/review-agentic-engineering",
            "plugins/zzzops/skills/send-zzzops-feedback",
            "plugins/zzzops/skills/validate-zzzops-installation",
        ]
        mapped = {
            surface
            for item in items
            for surface in item.get("surfaces", item["paths"])
        }
        automated_without_evidence = []
        for contract in data.get("automated_surfaces", []):
            evidence = contract.get("evidence", [])
            missing_evidence = [
                path for path in evidence if not (repo / path).is_file()
            ]
            if not evidence or missing_evidence:
                automated_without_evidence.append({
                    "surface": contract["surface"],
                    "missing": missing_evidence,
                })
            else:
                mapped.add(contract["surface"])
        missing = [path for path in required if not any(entry == path or entry.startswith(path + "/") for entry in mapped)]
        print(json.dumps({
            "unmapped_required_surfaces": missing,
            "automated_surfaces_without_evidence": automated_without_evidence,
        }))
        return 1 if missing or automated_without_evidence else 0
    if args.command == "audit":
        changed = []
        for item in items:
            current = digest(repo, item["paths"])
            if item["status"] == "checked" and item["fingerprint"] != current:
                item["status"], item["fingerprint"] = "unchecked", None
                changed.append(item["id"])
        save(plan, text, data, start, end)
        print(json.dumps({"stale": changed}))
        return 0
    if args.command == "next":
        item = next((entry for entry in items if entry["status"] != "checked"), None)
        print(json.dumps(item))
        return 0 if item else 1
    item = next((entry for entry in items if entry["id"] == args.item), None)
    if not item:
        raise SystemExit("unknown item")
    item["status"], item["fingerprint"] = "checked", digest(repo, item["paths"])
    save(plan, text, data, start, end)
    print(json.dumps({"checked": item["id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
