"""A fake `gh` for the engine tests (IMPLEMENTATION_PLAN §1.2): the subset of SPEC §5.6, acting on the bare remote.

State lives in the JSON file named by ZZZOPS_FAKE_GH_STATE; every call is appended to <state>.calls.jsonl.
GitHub's lazy views (G1021) are default-off faults that only `pr view` sees: `mergeable_lag`, `head_lag` (an int for
every PR or {"<number>": int}) and `advance_before_view` ({"ref", "to"}, applied once)."""

from __future__ import annotations

import json
import os
import re
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


def fault_count(st, name, pr):
    """A per-PR count fault: an int applies to every PR, a {"<number>": int} map to the PRs it names."""
    v = (st.get("faults") or {}).get(name) or 0
    if isinstance(v, dict):
        v = v.get(str(pr["number"])) or 0
    return int(v)


def lagged_head(st, pr):
    """The `head_lag` fault (G1021): for the first N views after the PR branch moves, GitHub still shows the head an
    earlier view showed. Returns that old head while it should be shown, else None."""
    n = fault_count(st, "head_lag", pr)
    if not n or pr["state"] != "OPEN":
        return None
    lag = pr.setdefault("lag", {})
    h, old = pr.get("headRefOid"), lag.get("shown_head")
    if old is None or old == h:
        lag["shown_head"] = h
        return None
    if lag.get("head_tip") != h:
        lag.update(head_tip=h, head_left=n)
    if lag["head_left"] > 0:
        lag["head_left"] -= 1
        return old
    lag["shown_head"] = h
    return None


def lagged_mergeability(st, pr, head):
    """The `mergeable_lag` fault (G1021): GitHub computes mergeability lazily, so the first N views after the head or
    the base changes read UNKNOWN/UNKNOWN. Returns True while the view should read UNKNOWN."""
    n = fault_count(st, "mergeable_lag", pr)
    if not n:
        return False
    key = f"{head}:{tip(st, pr['baseRefName'])}"
    lag = pr.setdefault("lag", {})
    if lag.get("merge_key") != key:
        lag.update(merge_key=key, merge_left=n)
    if lag["merge_left"] > 0:
        lag["merge_left"] -= 1
        return True
    return False


def advance_before_view(st):
    """The `advance_before_view` fault (G1021): {"ref": branch, "to": sha} moves a branch on the remote just before the
    next `pr view` answers, as when the integration branch moves between an op's fetch and GitHub's computation."""
    adv = (st.get("faults") or {}).pop("advance_before_view", None)
    if adv:
        git(st, "update-ref", f"refs/heads/{adv['ref']}", adv["to"])


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


def pr_json(st, pr, fields, view=False):
    refresh(st, pr)
    old = lagged_head(st, pr) if view else None
    shown = dict(pr, headRefOid=old) if old else pr               # what GitHub shows; the stored PR is unchanged
    m, ms = mergeability(st, shown) if pr["state"] == "OPEN" else ("UNKNOWN", "UNKNOWN")
    if view and pr["state"] == "OPEN" and lagged_mergeability(st, pr, shown["headRefOid"]):
        m, ms = "UNKNOWN", "UNKNOWN"
    full = {"number": pr["number"], "url": f"https://github.com/{st['repo']}/pull/{pr['number']}", "state": pr["state"],
            "headRefName": pr["headRefName"], "headRefOid": shown["headRefOid"], "baseRefName": pr["baseRefName"],
            "title": pr["title"], "body": pr["body"], "isDraft": pr["draft"], "mergeable": m, "mergeStateStatus": ms,
            "mergeCommit": {"oid": pr["mergeCommit"]} if pr.get("mergeCommit") else None,
            "mergedAt": pr.get("mergedAt"), "mergedBy": {"login": pr["mergedBy"]} if pr.get("mergedBy") else None,
            "autoMergeRequest": pr.get("autoMergeRequest"), "statusCheckRollup": rollup(st, shown)}
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


# --------------------------------------------------------------------------------------------- legacy search (G1015)

SEARCH_TERM = re.compile(r'-?[\w.-]+:(?:"[^"]*"|[^\s"]+)|"[^"]*"|\S+')


def graphql_request(argv):
    """The GraphQL document and variables of `gh api graphql` (-f/-F/--raw-field/--field, or --input - JSON)."""
    fields, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a in ("-f", "-F", "--raw-field", "--field") and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            fields[k] = v
            i += 2
            continue
        if a == "--input" and i + 1 < len(argv):
            body = json.loads(sys.stdin.read() if argv[i + 1] == "-" else open(argv[i + 1], encoding="utf-8").read())
            fields.update(body.get("variables") or {})
            fields["query"] = body.get("query", "")
            i += 2
            continue
        if a in ("--jq", "-q", "--paginate", "--template", "-t"):
            die(f"fake gh: api graphql {a} is not supported by the fake")
        i += 1
    doc = fields.pop("query", "")
    return doc, fields


def search_matches(st, q, issue):
    """GitHub issue search over the subset the legacy check uses: repo:, is:issue, is:open, label:a,b (OR),
    -label:x, and a quoted phrase with in:body (matched by the issue's `body_marker`)."""
    phrase = False
    for t in SEARCH_TERM.findall(q):
        neg = t.startswith("-")
        key, _, val = t.lstrip("-").partition(":")
        if t.startswith('"'):
            phrase = True
            continue
        if not val:
            die(f"fake gh: unsupported search term {t!r}")
        val = val.strip('"')
        if key == "repo":
            ok = val == st["repo"]
        elif key == "is" and val == "issue":
            ok = True
        elif key == "is" and val == "open":
            ok = bool(issue.get("open", True))
        elif key == "label":
            ok = bool(set(val.split(",")) & set(issue.get("labels") or []))
        elif key == "in" and val == "body":
            continue
        else:
            die(f"fake gh: unsupported search term {t!r}")
        if ok == neg:
            return False
    return not phrase or bool(issue.get("body_marker"))


GQL_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|#[^\n]*|\.\.\.|[A-Za-z_]\w*|-?\d+|\S')
UNION = "Selections can't be made directly on unions (see selections on SearchResultItem)"
NO_SELECTION = ("Field must have selections (field 'search' returns SearchResultItemConnection but has no "
                "selections. Did you mean 'search { ... }'?)")


def gql_selection(toks, i):
    """Parse the selection set at toks[i] == '{'. Return (entries, next index). An entry is
    ("field", response key, name, argument tokens, sub-entries or None) or ("on", type name, sub-entries)."""
    i += 1
    out = []
    while toks[i] != "}":
        t = toks[i]
        if t == ",":
            i += 1
            continue
        if t == "...":
            if toks[i + 1] != "on":
                die("fake gh: api graphql named fragments are not supported by the fake")
            typ = toks[i + 2]
            sub, i = gql_selection(toks, i + 3)
            out.append(("on", typ, sub))
            continue
        key = name = t
        i += 1
        if toks[i] == ":":
            name, i = toks[i + 1], i + 2
        args = []
        if toks[i] == "(":
            j, depth = i, 0
            while True:
                depth += {"(": 1, ")": -1}.get(toks[i], 0)
                i += 1
                if depth == 0:
                    break
            args = toks[j + 1:i - 1]
        sub = None
        if toks[i] == "{":
            sub, i = gql_selection(toks, i)
        out.append(("field", key, name, args, sub))
    return out, i + 1


def gql_document(doc):
    """The top-level selection of a single anonymous or named query."""
    toks = [t for t in GQL_TOKEN.findall(doc) if not t.startswith("#")]
    try:
        top, end = gql_selection(toks, toks.index("{"))
    except (ValueError, IndexError):
        die("fake gh: api graphql document could not be parsed by the fake")
    if end != len(toks):
        die("fake gh: api graphql supports one operation per document")
    return top


def gql_args(toks, variables):
    """name: value pairs; a value is a string, a $variable, or an enum or number literal."""
    out, i = {}, 0
    while i < len(toks):
        if toks[i] == ",":
            i += 1
            continue
        name, v = toks[i], toks[i + 2]
        i += 3
        if v == "$":
            v, i = variables.get(toks[i]), i + 1
        elif v.startswith('"'):
            v = json.loads(v)
        out[name] = v
    return out


def gql_errors(top):
    """GitHub's validation of the subset the fake serves, as [(message, path)]."""
    errors = []
    for e in top:
        if e[0] != "field" or e[2] != "search":
            die("fake gh: api graphql supports only the legacy issue search")
        _, alias, _, args, sub = e
        missing = [n for n in ("query", "type") if n not in gql_args(args, {})]
        if missing:
            errors.append((f"Field 'search' is missing required arguments: {', '.join(missing)}", ["query", alias]))
        if sub is None:
            errors.append((NO_SELECTION, ["query", alias]))
            continue
        for f in sub:
            if f[0] == "field" and f[2] == "nodes" and f[4] is not None:
                for n in f[4]:
                    if n[0] == "field" and n[2] != "__typename":
                        errors.append((UNION, ["query", alias, f[1], n[1]]))
    return errors


def gql_issue(sub, number):
    out = {}
    for e in sub:
        if e[0] != "field" or e[2] not in ("number", "__typename"):
            die(f"fake gh: Issue selection {e[1]!r} is not supported by the fake")
        out[e[1]] = number if e[2] == "number" else "Issue"
    return out


def gql_connection(sub, hits, n):
    out = {}
    for e in sub:
        if e[0] != "field":
            die("fake gh: fragments on SearchResultItemConnection are not supported by the fake")
        _, key, name, _, fsub = e
        if name == "issueCount":
            out[key] = len(hits)
        elif name == "nodes" and fsub is not None:
            nodes = []
            for h in hits[:n]:
                item = {}
                for f in fsub:
                    if f[0] == "field":                         # __typename only, by gql_errors
                        item[f[1]] = "Issue"
                    elif f[1] == "Issue":
                        item.update(gql_issue(f[2], h))
                nodes.append(item)
            out[key] = nodes
        elif name == "pageInfo" and fsub is not None:
            info = {"hasNextPage": len(hits) > n, "endCursor": None}
            for f in fsub:
                if f[0] != "field" or f[2] not in info:
                    die(f"fake gh: pageInfo selection {f[1]!r} is not supported by the fake")
                out.setdefault(key, {})[f[1]] = info[f[2]]
        else:
            die(f"fake gh: search selection {key!r} is not supported by the fake")
    return out


def graphql(st, argv):
    if (st.get("faults") or {}).get("graphql_error"):
        die("GraphQL: Something went wrong while executing your query. (search)")
    doc, variables = graphql_request(argv)
    top = gql_document(doc)
    errors = gql_errors(top)
    if errors:                                                  # as gh 2.100 shows a rejected document
        print(json.dumps({"errors": [{"path": p, "message": m} for m, p in errors]}))
        die("gh: " + errors[0][0])
    data, received = {}, {}
    for _, alias, _, args, sub in top:
        a = gql_args(args, variables)
        if a["type"] != "ISSUE":
            die(f"fake gh: search type {a['type']!r} is not supported by the fake")
        q = a["query"] or ""
        received[alias] = q
        hits = sorted(i["number"] for i in st.get("legacy_issues") or [] if search_matches(st, q, i))
        n = min(int(a.get("first") or 100), 100)
        data[alias] = gql_connection(sub, hits, n)
    st.setdefault("graphql_searches", []).append(received)
    st.setdefault("graphql_documents", []).append(doc)
    save(st)
    print(json.dumps({"data": data}))
    return 0


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
    if argv[:1] == ["api"] and faults.get("auth"):
        die("To get started with GitHub CLI, please run: gh auth login", 4)
    if argv[:2] == ["api", "graphql"]:
        return graphql(st, argv[2:])
    if argv[:1] == ["api"] and faults.get("rules_403") and re.search(r"/(rules|rulesets|protection)(/|$|\?)", argv[1]):
        die("gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)", 1)
    if argv[:2] == ["api", "repos/" + st["repo"]]:
        if faults.get("repo_settings_error"):
            die("gh: repository settings unavailable (HTTP 403)")
        repository = st.get("repository", {})
        _, options = opts(argv[2:])
        if options.get("jq") == ".delete_branch_on_merge":
            print(json.dumps(repository.get("delete_branch_on_merge")))
        elif "jq" not in options:
            print(json.dumps(repository))
        else:
            die("fake gh: unsupported repository query")
        return 0
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
        advance_before_view(st)
        out = pr_json(st, pr, o.get("json", "number").split(","), view=True)
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
