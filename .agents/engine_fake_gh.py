"""A fake `gh` for the engine tests (IMPLEMENTATION_PLAN §1.2): the subset of SPEC §5.6, acting on the bare remote.

State lives in the JSON file named by ZZZOPS_FAKE_GH_STATE; every call is appended to <state>.calls.jsonl."""

from __future__ import annotations

import json
import os
import subprocess
import sys

STATE = os.environ.get("ZZZOPS_FAKE_GH_STATE", "")


def load():
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def git(st, *args, check=True):
    p = subprocess.run(["git", "--git-dir", st["remote"], *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"fake gh: git {' '.join(args)}: {p.stderr}")
    return p.stdout.strip()


def tip(st, branch):
    p = subprocess.run(["git", "--git-dir", st["remote"], "rev-parse", "--verify", "-q", f"refs/heads/{branch}"],
                       capture_output=True, text=True)
    return p.stdout.strip() or None


def die(msg, code=1):
    sys.stderr.write(msg + "\n")
    raise SystemExit(code)


def opts(argv):
    pos, o = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            name = a[2:]
            if name in ("draft", "merge", "squash", "rebase", "failed"):
                o[name] = True
            else:
                i += 1
                o[name] = argv[i]
        elif a == "-R":
            i += 1
        else:
            pos.append(a)
        i += 1
    return pos, o


def refresh(st, pr):
    """GitHub updates the PR head from its branch, and refs/pull/<n>/head with it."""
    if pr["state"] == "OPEN":
        h = tip(st, pr["headRefName"])
        if h:
            pr["headRefOid"] = h
            git(st, "update-ref", f"refs/pull/{pr['number']}/head", h)


def mergeability(st, pr):
    base = tip(st, pr["baseRefName"])
    if not base or not pr.get("headRefOid"):
        return "UNKNOWN", "UNKNOWN"
    p = subprocess.run(["git", "--git-dir", st["remote"], "merge-tree", "--write-tree", base, pr["headRefOid"]],
                       capture_output=True, text=True)
    if p.returncode == 1:
        return "CONFLICTING", "DIRTY"
    forced = (st.get("faults") or {}).get("merge_state", {}).get(str(pr["number"]))
    if forced:
        return "MERGEABLE", forced
    if st.get("require_up_to_date") and subprocess.run(
            ["git", "--git-dir", st["remote"], "merge-base", "--is-ancestor", base, pr["headRefOid"]]).returncode != 0:
        return "MERGEABLE", "BEHIND"
    return "MERGEABLE", "CLEAN"


def rollup(st, pr):
    seqs = (st.get("checks") or {}).get(pr["headRefOid"] or "", {})
    out = []
    for name, steps in sorted(seqs.items()):
        cur = steps[0] if steps else "pending"
        if len(steps) > 1:
            steps.pop(0)                                       # each view advances the script by one step
        status = "COMPLETED" if cur in ("pass", "fail") else "IN_PROGRESS"
        conclusion = {"pass": "SUCCESS", "fail": "FAILURE"}.get(cur, "")
        out.append({"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion,
                    "detailsUrl": f"https://github.com/{st['repo']}/actions/runs/{abs(hash(name)) % 100000}/job/1"})
    return out


def pr_json(st, pr, fields):
    refresh(st, pr)
    m, ms = mergeability(st, pr) if pr["state"] == "OPEN" else ("UNKNOWN", "UNKNOWN")
    full = {"number": pr["number"], "url": f"https://github.com/{st['repo']}/pull/{pr['number']}", "state": pr["state"],
            "headRefName": pr["headRefName"], "headRefOid": pr["headRefOid"], "baseRefName": pr["baseRefName"],
            "title": pr["title"], "body": pr["body"], "isDraft": pr["draft"], "mergeable": m, "mergeStateStatus": ms,
            "mergeCommit": {"oid": pr["mergeCommit"]} if pr.get("mergeCommit") else None,
            "mergedAt": pr.get("mergedAt"), "mergedBy": {"login": pr["mergedBy"]} if pr.get("mergedBy") else None,
            "autoMergeRequest": pr.get("autoMergeRequest"), "statusCheckRollup": rollup(st, pr)}
    return {k: full[k] for k in fields}


def do_merge(st, pr, method, by="zzzops"):
    base = tip(st, pr["baseRefName"])
    head = pr["headRefOid"]
    tree = git(st, "merge-tree", "--write-tree", base, head).splitlines()[0]
    env_msg = f"Merge pull request #{pr['number']}"
    if method == "squash":
        c = git(st, "commit-tree", tree, "-p", base, "-m", f"{pr['title']} (#{pr['number']})")
    else:
        c = git(st, "commit-tree", tree, "-p", base, "-p", head, "-m", env_msg)
    git(st, "update-ref", f"refs/heads/{pr['baseRefName']}", c, base)
    pr.update(state="MERGED", mergeCommit=c, mergedAt="2027-01-15T09:00:00Z", mergedBy=by)
    if st.get("auto_delete", True):
        old_head = pr["headRefName"]
        git(st, "update-ref", "-d", f"refs/heads/{old_head}", check=False)
        for other in st["prs"].values():                       # GitHub retargets PRs based on the deleted branch
            if other["state"] == "OPEN" and other["baseRefName"] == old_head:
                other["baseRefName"] = pr["baseRefName"]


def main(argv):
    if argv[:1] == ["--version"]:
        print("gh version 2.60.0 (fake)")
        return 0
    st = load()
    with open(STATE + ".calls.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\n")
    faults = st.setdefault("faults", {})
    if argv[:2] == ["auth", "status"]:
        return 1 if faults.get("auth") else 0
    if faults.get("transient", 0) > 0:
        faults["transient"] -= 1
        save(st)
        die("HTTP 502: Bad Gateway (https://api.github.com/graphql)")
    if argv[:1] == ["api"]:
        print("[]")
        return 0
    if argv[:1] == ["issue"] and argv[1] == "close":
        st.setdefault("closed_issues", []).append(int(argv[2]))
        save(st)
        return 0
    if argv[:2] == ["run", "rerun"]:
        st.setdefault("reruns", []).append(argv[2])
        save(st)
        return 0
    if argv[0] != "pr":
        die(f"fake gh: unsupported {argv}")
    sub, rest = argv[1], argv[2:]
    pos, o = opts(rest)
    prs = st.setdefault("prs", {})
    if sub == "list":
        out = []
        for pr in sorted(prs.values(), key=lambda p: -p["number"]):
            if "head" in o and pr["headRefName"] != o["head"]:
                continue
            if "base" in o and pr["baseRefName"] != o["base"]:
                continue
            if o.get("state", "open") == "open" and pr["state"] != "OPEN":
                continue
            out.append(pr_json(st, pr, o.get("json", "number").split(",")))
        save(st)
        print(json.dumps(out))
        return 0
    if sub == "create":
        if not tip(st, o["head"]):
            die(f"pull request create failed: head branch {o['head']} not found")
        n = st.get("next_number", 1)
        st["next_number"] = n + 1
        body = sys.stdin.read() if o.get("body-file") == "-" else o.get("body", "")
        prs[str(n)] = {"number": n, "headRefName": o["head"], "baseRefName": o["base"], "title": o.get("title", ""),
                       "body": body, "draft": bool(o.get("draft")), "state": "OPEN", "headRefOid": tip(st, o["head"])}
        refresh(st, prs[str(n)])
        save(st)
        print(f"https://github.com/{st['repo']}/pull/{n}")
        return 0
    pr = prs.get(pos[0]) if pos else None
    if pr is None:
        die(f"no pull requests found for {pos}")
    if sub == "view":
        out = pr_json(st, pr, o.get("json", "number").split(","))
        save(st)
        print(json.dumps(out))
        return 0
    if sub == "edit":
        if "base" in o:
            pr["baseRefName"] = o["base"]
        if "title" in o:
            pr["title"] = o["title"]
        if o.get("body-file") == "-":
            pr["body"] = sys.stdin.read()
        save(st)
        return 0
    if sub == "close":
        pr["state"] = "CLOSED"
        save(st)
        return 0
    if sub == "merge":
        refresh(st, pr)
        if faults.get("merge_refuse"):
            save(st)
            die(faults["merge_refuse"])
        if o.get("match-head-commit") and o["match-head-commit"] != pr["headRefOid"]:
            save(st)
            die("GraphQL: Head branch was modified. Review and try the merge again.")
        method = "squash" if o.get("squash") else ("rebase" if o.get("rebase") else "merge")
        st.setdefault("merge_methods_used", []).append(method)
        do_merge(st, pr, method)
        save(st)
        return 0
    die(f"fake gh: unsupported pr {sub}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
