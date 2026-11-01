"""Structural validation of every ZzzOps file format (SPEC §3), and the parsed graph shared by the frontier."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine import POLICY_SCHEMA, WORKFLOW_SCHEMA, GOAL_SCHEMAS
from engine.canon import find_floats, goal_bytes, parse_iso, version_tuple

NODE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
HOLDER = re.compile(r"^[a-z][a-z0-9-]*:[A-Za-z0-9._/-]{1,96}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
FINDING_ID = re.compile(r"^[^.\[\]=\s]+$")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
OUTPUT_TYPES = {"text", "string", "sha", "int", "bool", "strings", "object", "list", "checkpoint", "artifact"}
KEYED_TYPES = {"object", "checkpoint", "artifact"}
CHECKPOINT_KEYS = {"commit", "base", "tree", "change"}
ARTIFACT_KEYS = {"path", "blob", "commit"}
GOAL_FIELDS = {"title", "spec", "priority", "release", "links"}
START_REASONS = {"new", "stale", "reopened", "retry", "not_ok"}
RESERVED_OUTPUT = "responses"
REVIEW_PATH = ".zzzops/reviews"
DOC_LIMIT = 65536
TEXT_LIMIT = 4096
SPEC_LIMIT = 16384

NODE_FIELDS = {
    # field: (kinds allowed)
    "kind": {"agent", "human", "op"}, "stage": {"agent", "human", "op"}, "description": {"agent", "human", "op"},
    "prompt": {"agent", "human"}, "root": {"agent"}, "capability": {"agent"}, "op": {"op"},
    "workspace": {"agent", "op"}, "inputs": {"agent", "human", "op"}, "outputs": {"agent", "op"},
    "review": {"agent", "human"}, "policy": {"agent", "human", "op"}, "instructions": {"agent", "human"},
    "preserve": {"agent"}, "release_gate": {"agent", "human", "op"}, "rev": {"agent", "human", "op"},
    "timeout": {"agent", "op"},
}
INPUT_FIELDS = {"from", "optional", "context", "pending"}


# ----------------------------------------------------------------------------------------------- helpers


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_str(v) -> bool:
    return isinstance(v, str)


def _one_line(v) -> bool:
    return isinstance(v, str) and "\n" not in v and "\r" not in v


def _is_iso(v) -> bool:
    if not isinstance(v, str) or not ISO.match(v):
        return False
    try:
        parse_iso(v)
    except ValueError:
        return False
    return True


def _strings(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


class Errors(list):
    def add(self, where: str, message: str):
        self.append(f"{where}: {message}")

    def unknown(self, where: str, obj: dict, allowed):
        for k in obj:
            if k not in allowed:
                self.add(where, f"unknown key {k!r}")


# ----------------------------------------------------------------------------------------------- selectors


@dataclass(frozen=True)
class Selector:
    kind: str                  # "goal" | "node" | "deps"
    node: str | None           # producer node (node and deps kinds)
    output: str | None         # the producer's output name
    path: tuple = ()           # key path (goal: the field path; node/deps: keys inside the output)
    text: str = ""

    @property
    def producer(self) -> str | None:
        """The same-goal producer, or None for goal. and deps. selectors."""
        return self.node if self.kind == "node" else None


def parse_selector(text) -> Selector | None:
    if not isinstance(text, str) or not text:
        return None
    parts = text.split(".")
    if any(not p for p in parts):
        return None
    if parts[0] == "goal":
        if len(parts) < 2 or parts[1] not in GOAL_FIELDS:
            return None
        if len(parts) > 2 and parts[1] != "links":
            return None
        return Selector("goal", None, None, tuple(parts[1:]), text)
    if parts[0] == "deps":
        if len(parts) < 3:
            return None
        return Selector("deps", parts[1], parts[2], tuple(parts[3:]), text)
    if len(parts) < 2:
        return None
    return Selector("node", parts[0], parts[1], tuple(parts[2:]), text)


# ----------------------------------------------------------------------------------------------- graph


@dataclass
class Graph:
    name: str
    nodes: dict                     # node id -> node definition (as authored)
    terminal: list
    topo: list = field(default_factory=list)
    selectors: dict = field(default_factory=dict)   # node -> {input name: Selector}
    output_types: dict = field(default_factory=dict)  # node -> {output: type}, implicit outputs included

    def producers(self, n: str) -> list:
        """Same-goal producers of n: its input selectors without goal./deps., plus review.subject."""
        out = []
        for sel in self.selectors.get(n, {}).values():
            if sel and sel.producer and sel.producer not in out:
                out.append(sel.producer)
        subject = (self.nodes[n].get("review") or {}).get("subject")
        if subject and subject not in out:
            out.append(subject)
        return out

    def subject(self, n: str) -> str | None:
        return (self.nodes[n].get("review") or {}).get("subject")

    def is_review(self, n: str) -> bool:
        return bool(self.nodes[n].get("review"))

    def checkpoint_outputs(self, n: str) -> list:
        return [k for k, t in self.output_types.get(n, {}).items() if t == "checkpoint"]

    def artifact_outputs(self, n: str) -> list:
        return [k for k, t in self.output_types.get(n, {}).items() if t == "artifact"]

    def ancestors(self, n: str) -> set:
        seen, stack = set(), list(self.producers(n))
        while stack:
            p = stack.pop()
            if p in seen or p not in self.nodes:
                continue
            seen.add(p)
            stack.extend(self.producers(p))
        return seen

    def selector_type(self, sel: Selector) -> str:
        """The fingerprint type of a selector's value (SPEC §3.1 selector table)."""
        if sel.kind == "goal":
            return "plain"
        if sel.kind == "deps":
            return "map"
        if sel.path:
            return "plain"
        return self.output_types.get(sel.node, {}).get(sel.output, "plain")

    def element_type(self, sel: Selector) -> str:
        """For deps. selectors: the type of each dependency's value."""
        if sel.path:
            return "plain"
        return self.output_types.get(sel.node, {}).get(sel.output, "plain")


def implicit_outputs(node: dict) -> dict:
    if not node.get("review"):
        return {}
    out = {"decision": "string", "summary": "text"}
    if node.get("kind") == "agent":
        out["report"] = "artifact"
    if node.get("kind") == "human":
        out.update({"decided_by": "string", "quote": "text", "decided_at": "string"})
    return out


def node_output_types(node: dict) -> dict:
    out = dict(node.get("outputs") or {}) if isinstance(node.get("outputs"), dict) else {}
    out.update(implicit_outputs(node))
    return out


def build_graph(name: str, gdef: dict, order: bool = True) -> Graph:
    """Parse a graph that already passed validate_workflow (`order=False` skips the topological sort)."""
    nodes = gdef["nodes"]
    g = Graph(name, nodes, list(gdef["terminal"]))
    for n, nd in nodes.items():
        g.selectors[n] = {k: parse_selector(s.get("from")) for k, s in (nd.get("inputs") or {}).items()}
        g.output_types[n] = node_output_types(nd)
    if order:
        g.topo = _topo(g)
    return g


def _topo(g: Graph) -> list:
    """Topological order of producers before consumers; ties by declaration order (SPEC §3.1 rule 4)."""
    names = list(g.nodes)
    prods = {n: [p for p in g.producers(n) if p in g.nodes] for n in names}
    order, placed = [], set()
    while len(order) < len(names):
        ready = [n for n in names if n not in placed and all(p in placed for p in prods[n])]
        if not ready:
            stuck = [n for n in names if n not in placed]
            raise ValueError("cycle: " + " -> ".join(stuck))
        order.append(ready[0])
        placed.add(ready[0])
    return order


# ----------------------------------------------------------------------------------------------- workflow (§3.1)


def validate_workflow(wf, policy: dict | None = None, prompt_exists=None, ops: dict | None = None) -> list:
    """Every graph rule of SPEC §3.1. `policy` and `prompt_exists` enable rule 6; `ops` (name -> spec) rule 11."""
    e = Errors()
    if not isinstance(wf, dict):
        e.add("workflow", "must be an object")
        return e
    e.unknown("workflow", wf, {"schema", "graphs"})
    if wf.get("schema") != WORKFLOW_SCHEMA or not _is_int(wf.get("schema")):
        e.add("workflow.schema", f"must be {WORKFLOW_SCHEMA}")
    floats = find_floats(wf)
    for p in floats:
        e.add(p, "floats are not allowed")
    graphs = wf.get("graphs")
    if not isinstance(graphs, dict) or "default" not in graphs:
        e.add("workflow.graphs", "must be an object containing \"default\"")
        return e
    for gname, gdef in graphs.items():
        _validate_graph(e, gname, gdef, policy, prompt_exists, ops)
    return e


def _validate_graph(e: Errors, gname, gdef, policy, prompt_exists, ops):
    where = f"graphs.{gname}"
    if not isinstance(gdef, dict):
        e.add(where, "must be an object")
        return
    e.unknown(where, gdef, {"terminal", "nodes"})
    nodes = gdef.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        e.add(f"{where}.nodes", "must be a non-empty object")
        return
    settings = (policy or {}).get("settings") if isinstance(policy, dict) else None
    instructions = (policy or {}).get("instructions") if isinstance(policy, dict) else None
    before = len(e)
    for n, nd in nodes.items():
        _validate_node(e, f"{where}.nodes.{n}", n, nd, nodes, settings, instructions, prompt_exists, ops)
    terminal = gdef.get("terminal")
    if not isinstance(terminal, list) or not terminal or not all(isinstance(t, str) for t in terminal):
        e.add(f"{where}.terminal", "must be a non-empty array of node ids")
        terminal = []
    for t in terminal:
        if t not in nodes:
            e.add(f"{where}.terminal", f"names unknown node {t!r}")
    if len(e) > before:
        return
    g = build_graph(gname, {"nodes": nodes, "terminal": terminal}, order=False)
    # rule 4: acyclic producers, never its own producer
    try:
        g.topo = _topo(g)
    except ValueError as exc:
        e.add(where, str(exc))
        return
    for n in nodes:
        if n in g.producers(n):
            e.add(f"{where}.nodes.{n}", "a node is never its own producer")
    # rule 7: stage rule, including through deps. selectors
    for n, nd in nodes.items():
        if nd.get("stage") != "discovery":
            continue
        prods = set(g.producers(n)) | {s.node for s in g.selectors[n].values() if s and s.kind == "deps"}
        for p in sorted(prods):
            if p in nodes and nodes[p].get("stage") == "delivery":
                e.add(f"{where}.nodes.{n}", f"discovery node has delivery producer {p!r}")
    # rule 8: checkpoint nodes have exactly one checkpoint output and a sha-valued `base` input
    for n, nd in nodes.items():
        cps = g.checkpoint_outputs(n)
        if not cps:
            continue
        if len(cps) != 1:
            e.add(f"{where}.nodes.{n}.outputs", "a node has at most one checkpoint output")
        base = g.selectors[n].get("base")
        if base is None or not _yields_sha(g, base):
            e.add(f"{where}.nodes.{n}.inputs", "a checkpoint node declares an input `base` whose selector yields a sha")
    # rule 9: one artifact output, counting the implicit report
    for n in nodes:
        if len(g.artifact_outputs(n)) > 1:
            e.add(f"{where}.nodes.{n}.outputs", "at most one artifact output (counting the implicit report)")
    # rule 10: preserve
    for n, nd in nodes.items():
        p = nd.get("preserve")
        if p is None:
            continue
        if p not in g.ancestors(n):
            e.add(f"{where}.nodes.{n}.preserve", f"{p!r} is not a transitive producer")
        elif len(g.checkpoint_outputs(p)) != 1:
            e.add(f"{where}.nodes.{n}.preserve", f"{p!r} must have exactly one checkpoint output")
        if len(g.checkpoint_outputs(n)) != 1:
            e.add(f"{where}.nodes.{n}.preserve", "the preserving node must have exactly one checkpoint output")
    # rule 13: every node is terminal or a transitive producer of one
    useful = set(terminal)
    for t in terminal:
        useful |= g.ancestors(t)
    for n in nodes:
        if n not in useful:
            e.add(f"{where}.nodes.{n}", "neither terminal nor a transitive producer of a terminal node")


def _yields_sha(g: Graph, sel: Selector) -> bool:
    if sel.kind != "node":
        return False
    t = g.output_types.get(sel.node, {}).get(sel.output)
    if not sel.path:
        return t == "sha"
    return t in ("checkpoint", "artifact") and sel.path == ("commit",)


def _validate_node(e: Errors, where, n, nd, nodes, settings, instructions, prompt_exists, ops):
    if not NODE_ID.match(n):
        e.add(where, "node ids match ^[a-z][a-z0-9_]*$")
    if not isinstance(nd, dict):
        e.add(where, "must be an object")
        return
    kind = nd.get("kind")
    if kind not in ("agent", "human", "op"):
        e.add(f"{where}.kind", "must be agent, human or op")
        return
    for k in nd:
        if k not in NODE_FIELDS:
            e.add(where, f"unknown field {k!r}")
        elif kind not in NODE_FIELDS[k]:
            e.add(where, f"field {k!r} is not allowed on {kind} nodes")
    if nd.get("stage") not in ("discovery", "delivery"):
        e.add(f"{where}.stage", "must be discovery or delivery")
    if "description" in nd and not _is_str(nd["description"]):
        e.add(f"{where}.description", "must be a string")
    if kind in ("agent", "human"):
        if not _is_str(nd.get("prompt")) or not nd.get("prompt"):
            e.add(f"{where}.prompt", "required for agent and human nodes")
        elif prompt_exists is not None and not prompt_exists(nd["prompt"]):
            e.add(f"{where}.prompt", f"prompt file .zzzops/prompts/{nd['prompt']} does not exist")
    if kind == "op":
        if not _is_str(nd.get("op")):
            e.add(f"{where}.op", "required on op nodes")
        elif ops is not None:
            spec = ops.get(nd["op"])
            if spec is None:
                e.add(f"{where}.op", f"unknown op {nd['op']!r}")
            else:
                for msg in spec.validate(nd):
                    e.add(f"{where}", f"op {nd['op']}: {msg}")
    for b in ("root", "workspace", "release_gate"):
        if b in nd and not isinstance(nd[b], bool):
            e.add(f"{where}.{b}", "must be a boolean")
    if "capability" in nd:
        if not _is_str(nd["capability"]):
            e.add(f"{where}.capability", "must be a string")
        elif settings is not None and nd["capability"] not in (((settings.get("routing") or {}).get("tiers")) or {}):
            e.add(f"{where}.capability", f"{nd['capability']!r} is not a routing.tiers key")
    elif kind == "agent" and settings is not None and "bounded" not in (((settings.get("routing") or {}).get("tiers")) or {}):
        e.add(f"{where}.capability", "the default capability 'bounded' is not a routing.tiers key")
    if "rev" in nd and (not _is_int(nd["rev"]) or nd["rev"] < 0):
        e.add(f"{where}.rev", "must be an integer >= 0")
    if "timeout" in nd:
        lo, hi = (10, 1440) if kind == "agent" else (2, 240)
        if not _is_int(nd["timeout"]) or not lo <= nd["timeout"] <= hi:
            e.add(f"{where}.timeout", f"must be an integer {lo}-{hi} (minutes)")
    if kind == "human" and not nd.get("review"):
        e.add(f"{where}.review", "required on human nodes")
    review = nd.get("review")
    if review is not None:
        if not isinstance(review, dict) or set(review) != {"subject"} or not _is_str(review.get("subject")):
            e.add(f"{where}.review", "must be {\"subject\": \"<node>\"}")
        elif review["subject"] == n:
            e.add(f"{where}.review", "a review's subject is another node")
        elif review["subject"] not in nodes:
            e.add(f"{where}.review", f"unknown subject {review['subject']!r}")
        if "outputs" in nd:
            e.add(f"{where}.outputs", "review nodes have implicit outputs only")
    outputs = nd.get("outputs", {})
    if not isinstance(outputs, dict):
        e.add(f"{where}.outputs", "must be an object")
    else:
        for k, t in outputs.items():
            if k == RESERVED_OUTPUT:
                e.add(f"{where}.outputs", "`responses` is engine-reserved")
            elif not NODE_ID.match(k):
                e.add(f"{where}.outputs.{k}", "output names match ^[a-z][a-z0-9_]*$")
            if t not in OUTPUT_TYPES:
                e.add(f"{where}.outputs.{k}", f"unknown output type {t!r}")
    for listed, check in (("policy", None), ("instructions", None)):
        v = nd.get(listed, [])
        if not _strings(v):
            e.add(f"{where}.{listed}", "must be an array of strings")
            continue
        for key in v:
            if listed == "policy" and settings is not None and not _has_dotted(settings, key):
                e.add(f"{where}.policy", f"settings has no key {key!r}")
            if listed == "instructions" and instructions is not None and key not in instructions:
                e.add(f"{where}.instructions", f"POLICY instructions has no key {key!r}")
    if "preserve" in nd and not _is_str(nd["preserve"]):
        e.add(f"{where}.preserve", "must be a node id")
    inputs = nd.get("inputs", {})
    if not isinstance(inputs, dict):
        e.add(f"{where}.inputs", "must be an object")
        return
    for k, spec in inputs.items():
        iw = f"{where}.inputs.{k}"
        if not NODE_ID.match(k):
            e.add(iw, "input names match ^[a-z][a-z0-9_]*$")
        if not isinstance(spec, dict):
            e.add(iw, "must be an object")
            continue
        e.unknown(iw, spec, INPUT_FIELDS)
        for b in ("optional", "context", "pending"):
            if b in spec and not isinstance(spec[b], bool):
                e.add(f"{iw}.{b}", "must be a boolean")
        sel = parse_selector(spec.get("from"))
        if sel is None:
            e.add(f"{iw}.from", f"does not parse: {spec.get('from')!r}")
            continue
        if spec.get("pending") and sel.kind != "deps":
            e.add(f"{iw}.pending", "only on deps. selectors")
        if sel.kind == "goal":
            continue
        if sel.node not in nodes:
            e.add(f"{iw}.from", f"unknown node {sel.node!r}")
            continue
        types = node_output_types(nodes[sel.node]) if isinstance(nodes[sel.node], dict) else {}
        if sel.output == RESERVED_OUTPUT or sel.output not in types:
            e.add(f"{iw}.from", f"{sel.node!r} has no output {sel.output!r}")
            continue
        t = types[sel.output]
        if sel.path:
            if t not in KEYED_TYPES:
                e.add(f"{iw}.from", f"key paths are allowed only into object, checkpoint and artifact outputs")
            elif t == "checkpoint" and (len(sel.path) != 1 or sel.path[0] not in CHECKPOINT_KEYS):
                e.add(f"{iw}.from", f"checkpoint keys are {sorted(CHECKPOINT_KEYS)}")
            elif t == "artifact" and (len(sel.path) != 1 or sel.path[0] not in ARTIFACT_KEYS):
                e.add(f"{iw}.from", f"artifact keys are {sorted(ARTIFACT_KEYS)}")


def _has_dotted(obj, dotted: str) -> bool:
    for part in dotted.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return False
        obj = obj[part]
    return True


def get_dotted(obj, dotted: str):
    for part in dotted.split("."):
        obj = obj[part]
    return obj


# ----------------------------------------------------------------------------------------------- policy (§3.2)

SETTINGS_SHAPE = {
    "engine": {"min": "version"},
    "integration_branch": "branch",
    "verification": {"commands": "strings", "required_ci": "strings", "timeout_minutes": (1, 240),
                     "ci_timeout_minutes": (10, 1440)},
    "releases": {"current": (1, None)},
    "leases": {"ttl_minutes": (10, 1440)},
    "parallelism": {"max_workers": (1, 50)},
    "scheduling": {"order": ("stage_first", "goal_first")},
    "goals": {"first_id": (1, None)},
    "merge": {"method": ("merge", "squash", "rebase")},
    "routing": {"tiers": "tiers"},
}


def policy_floor(raw) -> tuple:
    """Tolerant pre-read (SPEC §4.5): (schema_version, engine.min) or (None, None) when unreadable."""
    if not isinstance(raw, dict):
        return None, None
    sv = raw.get("schema_version")
    try:
        mn = raw["settings"]["engine"]["min"]
    except (KeyError, TypeError):
        mn = None
    return (sv if _is_int(sv) else None), (mn if isinstance(mn, str) else None)


def validate_policy(p) -> list:
    e = Errors()
    if not isinstance(p, dict):
        e.add("POLICY", "must be an object")
        return e
    e.unknown("POLICY", p, {"schema_version", "settings", "instructions"})
    sv = p.get("schema_version")
    if sv == 1:
        e.add("POLICY.schema_version", "1 is the pre-reset policy format; see MIGRATING.md")
    elif sv != POLICY_SCHEMA or not _is_int(sv):
        e.add("POLICY.schema_version", f"must be {POLICY_SCHEMA}")
    for path in find_floats(p):
        e.add(path, "floats are not allowed")
    _check_shape(e, "settings", p.get("settings"), SETTINGS_SHAPE)
    ins = p.get("instructions")
    if not isinstance(ins, dict):
        e.add("instructions", "must be an object")
    else:
        for k, v in ins.items():
            if not NODE_ID.match(k):
                e.add(f"instructions.{k}", "keys match ^[a-z][a-z0-9_]*$")
            if not isinstance(v, str) or not v.strip():
                e.add(f"instructions.{k}", "must be non-empty text")
    return e


def _check_shape(e: Errors, where, value, shape):
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            e.add(where, "must be an object")
            return
        for k in shape:
            if k not in value:
                e.add(where, f"missing key {k!r}")
        e.unknown(where, value, shape)
        for k, sub in shape.items():
            if k in value:
                _check_shape(e, f"{where}.{k}", value[k], sub)
        return
    if shape == "version":
        try:
            version_tuple(value) if isinstance(value, str) else (_ for _ in ()).throw(ValueError())
        except ValueError:
            e.add(where, "must be a MAJOR.MINOR.PATCH version string")
    elif shape == "branch":
        if not _one_line(value) or not value:
            e.add(where, "must be a branch name")
    elif shape == "strings":
        if not _strings(value):
            e.add(where, "must be an array of strings")
    elif shape == "tiers":
        if not isinstance(value, dict) or not all(isinstance(k, str) and _strings(v) for k, v in value.items()):
            e.add(where, "must be {\"<tier>\": [\"<model id>\", ...]}")
    elif isinstance(shape, tuple) and shape and isinstance(shape[0], str):
        if value not in shape:
            e.add(where, f"must be one of {list(shape)}")
    elif isinstance(shape, tuple):
        lo, hi = shape
        if not _is_int(value) or value < lo or (hi is not None and value > hi):
            e.add(where, f"must be an integer {lo}-{hi}" if hi is not None else f"must be an integer >= {lo}")


# ----------------------------------------------------------------------------------------------- goal (§3.3)

GOAL_KEYS = {"schema", "id", "title", "graph", "state", "closed", "spec", "priority", "release", "depends_on",
             "skip", "links", "budget", "records"}


def validate_goal(doc, old=None, all_docs: dict | None = None, workflow: dict | None = None,
                  closed_done_ok=None) -> tuple:
    """SPEC §3.3 rules 1-8. Returns (errors, warnings).

    `all_docs` maps id -> document (for rule 4); `workflow` is the parsed workflow.json; `closed_done_ok(doc)` is the
    frontier callback for rule 8 (every terminal node current in the new document)."""
    e, warnings = Errors(), []
    if not isinstance(doc, dict):
        e.add("goal", "must be an object")
        return e, warnings
    e.unknown("goal", doc, GOAL_KEYS)
    for k in GOAL_KEYS:
        if k not in doc:
            e.add("goal", f"missing key {k!r}")
    if e:
        return e, warnings
    if doc["schema"] not in GOAL_SCHEMAS or not _is_int(doc["schema"]):
        e.add("goal.schema", f"unknown goal schema {doc['schema']!r}")
    if not _is_int(doc["id"]) or doc["id"] < 1:
        e.add("goal.id", "must be an integer >= 1")
    if not _one_line(doc["title"]) or not 1 <= len(doc["title"]) <= 200:
        e.add("goal.title", "1-200 characters, one line")
    if not isinstance(doc["spec"], str) or not 1 <= len(doc["spec"].encode("utf-8")) <= SPEC_LIMIT:
        e.add("goal.spec", f"1-{SPEC_LIMIT} bytes of text")
    if doc["priority"] not in ("P0", "P1", "P2", "P3"):
        e.add("goal.priority", "must be P0, P1, P2 or P3")
    if not _is_int(doc["release"]) or doc["release"] < 1:
        e.add("goal.release", "must be an integer >= 1")
    deps = doc["depends_on"]
    if not isinstance(deps, list) or not all(_is_int(d) for d in deps) or len(set(deps)) != len(deps):
        e.add("goal.depends_on", "must be an array of unique integers")
        deps = []
    elif doc["id"] in deps:
        e.add("goal.depends_on", "a goal cannot depend on itself")
    if not isinstance(doc["skip"], dict) or not all(isinstance(v, str) and v.strip() for v in doc["skip"].values()):
        e.add("goal.skip", "must map node ids to non-empty reasons")
    links = doc["links"]
    if not isinstance(links, dict) or set(links) != {"issue"} or not (links["issue"] is None or _is_int(links["issue"])):
        e.add("goal.links", "must be {\"issue\": null | int}")
    if not (doc["budget"] is None or (_is_int(doc["budget"]) and doc["budget"] >= 0)):
        e.add("goal.budget", "must be null or an integer >= 0")
    # rule 1: state and closed
    state, closed = doc["state"], doc["closed"]
    if state not in ("open", "held", "closed"):
        e.add("goal.state", "must be open, held or closed")
    if (state == "closed") != isinstance(closed, dict):
        e.add("goal.closed", "an object exactly when state is closed")
    if isinstance(closed, dict):
        e.unknown("goal.closed", closed, {"reason", "note", "by", "at"})
        if closed.get("reason") not in ("done", "cancelled", "superseded"):
            e.add("goal.closed.reason", "must be done, cancelled or superseded")
        if not isinstance(closed.get("note"), str) or not closed.get("note").strip():
            e.add("goal.closed.note", "must be non-empty")
        if not isinstance(closed.get("by"), str):
            e.add("goal.closed.by", "must be a string")
        if not _is_iso(closed.get("at")):
            e.add("goal.closed.at", "must be an ISO time")
    elif closed is not None:
        e.add("goal.closed", "must be null or an object")
    # records
    records = doc["records"]
    if not isinstance(records, dict):
        e.add("goal.records", "must be an object")
        records = {}
    for n, r in records.items():
        for msg in validate_record(r):
            e.add(f"goal.records.{n}", msg)
    # rule 2/3: graph, skip and records keys
    if workflow is not None:
        gdef = (workflow.get("graphs") or {}).get(doc["graph"])
        if gdef is None:
            e.add("goal.graph", f"unknown graph {doc['graph']!r}")
        else:
            nodes = gdef["nodes"]
            for n in list(doc["skip"]) if isinstance(doc["skip"], dict) else []:
                if n not in nodes:
                    warnings.append({"kind": "orphan_record", "message": f"G{doc['id']}: skip of removed node {n!r} is ignored"})
                elif n in gdef["terminal"]:
                    e.add(f"goal.skip.{n}", "a terminal node cannot be skipped")
            for n in records:
                if n not in nodes:
                    warnings.append({"kind": "orphan_record", "message": f"G{doc['id']}: record of removed node {n!r} is ignored"})
    # rule 4: dependencies exist, acyclic, release order
    if all_docs is not None:
        for d in deps:
            if d not in all_docs:
                e.add("goal.depends_on", f"G{d} does not exist")
            elif _is_int(doc["release"]) and _is_int(all_docs[d].get("release")) and all_docs[d]["release"] > doc["release"]:
                e.add("goal.depends_on", f"G{d} is in release {all_docs[d]['release']}, after this goal's release {doc['release']}")
        merged = dict(all_docs)
        merged[doc["id"]] = doc
        cycle = find_cycle(merged, doc["id"])
        if cycle:
            e.add("goal.depends_on", "dependency cycle: " + " -> ".join(f"G{c}" for c in cycle))
    # rule 5: a done goal stays closed
    if old is not None and isinstance(old.get("closed"), dict) and old["closed"].get("reason") == "done" and state != "closed":
        e.add("goal.state", "a goal closed as done stays closed; open a follow-up goal")
    # rule 6: size
    size = len(goal_bytes(doc))
    if size > DOC_LIMIT:
        e.add("goal", f"too_large: {size} bytes > {DOC_LIMIT}; largest paths: " + ", ".join(
            f"{p} ({b} bytes)" for p, b in largest_paths(doc)))
    # rule 7: floats
    for p in find_floats(doc):
        e.add(p, "floats are not allowed")
    # rule 8: closed done means delivered
    was_done = old is not None and isinstance(old.get("closed"), dict) and old["closed"].get("reason") == "done"
    if (isinstance(closed, dict) and closed.get("reason") == "done" and not was_done and closed_done_ok is not None
            and not e and not closed_done_ok(doc)):
        e.add("goal.closed.reason", "done requires every terminal node to be current; use superseded or cancelled")
    return e, warnings


def find_cycle(docs: dict, start: int):
    """A dependency cycle through `start`, as a list of ids, or None."""
    trail, onpath = [], set()

    def visit(i):
        if i in onpath:
            return trail[trail.index(i):] + [i]
        if i not in docs:
            return None
        onpath.add(i)
        trail.append(i)
        for d in docs[i].get("depends_on") or []:
            if isinstance(d, int):
                c = visit(d)
                if c:
                    return c
        trail.pop()
        onpath.discard(i)
        return None

    return visit(start)


def largest_paths(doc, k=5):
    sizes = []

    def walk(v, path):
        if isinstance(v, dict):
            for key, x in v.items():
                walk(x, f"{path}.{key}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")
        sizes.append((path, len(goal_bytes(v)) - 1))

    for key, v in doc.items():
        walk(v, key)
    leafish = sorted(sizes, key=lambda x: -x[1])
    return leafish[:k]


# ----------------------------------------------------------------------------------------------- record (§3.4–§3.7)

RECORD_KEYS = {"status", "ok", "attempt", "holder", "reason", "correction_runs", "input_fp", "fp_parts", "output",
               "findings", "blocked", "answer", "reviewed", "frozen", "carried_by", "prompt", "finished_at"}


def validate_record(r) -> list:
    e = Errors()
    if not isinstance(r, dict):
        return ["must be an object"]
    e.unknown("record", r, RECORD_KEYS)
    for k in ("status", "ok", "attempt", "holder", "reason", "correction_runs", "input_fp", "fp_parts", "output",
              "findings", "finished_at"):
        if k not in r:
            e.add("record", f"missing key {k!r}")
    if e:
        return e
    if r["status"] not in ("done", "blocked"):
        e.add("record.status", "must be done or blocked")
    if not isinstance(r["ok"], bool):
        e.add("record.ok", "must be a boolean")
    if not _is_int(r["attempt"]) or r["attempt"] < 1:
        e.add("record.attempt", "must be an integer >= 1")
    if r["holder"] != "human" and not (isinstance(r["holder"], str) and HOLDER.match(r["holder"])):
        e.add("record.holder", "must be a holder label or \"human\"")
    if r["reason"] not in START_REASONS:
        e.add("record.reason", f"must be one of {sorted(START_REASONS)}")
    if not _is_int(r["correction_runs"]) or r["correction_runs"] < 0:
        e.add("record.correction_runs", "must be an integer >= 0")
    if not isinstance(r["input_fp"], str):
        e.add("record.input_fp", "must be a string")
    fp = r["fp_parts"]
    if not isinstance(fp, dict) or not {"def", "inputs", "policy"} <= set(fp) or not set(fp) <= {"def", "inputs", "policy", "subject"}:
        e.add("record.fp_parts", "must hold def, inputs, policy and optionally subject")
    if r["status"] == "blocked":
        if r["ok"] is not False:
            e.add("record.ok", "a blocked record is never ok")
        if r["output"] is not None:
            e.add("record.output", "null when blocked")
        if "blocked" not in r:
            e.add("record.blocked", "required when status is blocked")
        else:
            for msg in validate_blocked(r["blocked"]):
                e.add("record.blocked", msg)
    else:
        if not isinstance(r["output"], dict):
            e.add("record.output", "must be an object")
        if "blocked" in r:
            e.add("record.blocked", "present only when status is blocked")
    if not isinstance(r["findings"], list):
        e.add("record.findings", "must be an array")
    else:
        for i, f in enumerate(r["findings"]):
            for msg in validate_finding(f):
                e.add(f"record.findings[{i}]", msg)
    if "answer" in r:
        a = r["answer"]
        if not isinstance(a, dict) or not {"text", "quote", "decided_by", "decided_at"} >= set(a) or "text" not in a:
            e.add("record.answer", "must be {text, quote, decided_by, decided_at}")
    if "frozen" in r and not _strings(r["frozen"]):
        e.add("record.frozen", "must be an array of paths")
    if "carried_by" in r and not isinstance(r["carried_by"], str):
        e.add("record.carried_by", "must be a string")
    if "prompt" in r and not (r["prompt"] is None or isinstance(r["prompt"], str)):
        e.add("record.prompt", "must be a blob id")
    if not _is_iso(r["finished_at"]):
        e.add("record.finished_at", "must be an ISO time")
    return e


FINDING_KEYS = {"id", "target", "target_fp", "target_attempt", "text", "status", "response", "rounds", "upheld",
                "note", "repeats", "carrier_fp"}


def validate_finding(f) -> list:
    e = Errors()
    if not isinstance(f, dict):
        return ["must be an object"]
    e.unknown("finding", f, FINDING_KEYS)
    for k in ("id", "target", "target_fp", "target_attempt", "text", "status", "response", "rounds", "upheld", "note"):
        if k not in f:
            e.add("finding", f"missing key {k!r}")
    if e:
        return e
    if not isinstance(f["id"], str) or not FINDING_ID.match(f["id"]):
        e.add("finding.id", "contains no '.', '[', ']', '=' or whitespace")
    if not isinstance(f["target"], str) or not NODE_ID.match(f["target"]):
        e.add("finding.target", "must be a node id")
    if (f["target_fp"] is None) != (f["target_attempt"] is None):
        e.add("finding.target_attempt", "null exactly when target_fp is null")
    if f["target_fp"] is not None and not isinstance(f["target_fp"], str):
        e.add("finding.target_fp", "must be a fingerprint or null")
    if f["target_attempt"] is not None and (not _is_int(f["target_attempt"]) or f["target_attempt"] < 1):
        e.add("finding.target_attempt", "must be an integer >= 1 or null")
    if not isinstance(f["text"], str) or not f["text"].strip():
        e.add("finding.text", "must be non-empty")
    if f["status"] not in ("open", "resolved", "waived"):
        e.add("finding.status", "must be open, resolved or waived")
    if not (f["response"] is None or isinstance(f["response"], str)):
        e.add("finding.response", "must be a string or null")
    if not _is_int(f["rounds"]) or f["rounds"] < 1:
        e.add("finding.rounds", "must be an integer >= 1")
    if not isinstance(f["upheld"], bool):
        e.add("finding.upheld", "must be a boolean")
    if not (f["note"] is None or isinstance(f["note"], str)):
        e.add("finding.note", "must be a string or null")
    if "repeats" in f and (not _is_int(f["repeats"]) or f["repeats"] < 1):
        e.add("finding.repeats", "must be an integer >= 1")
    if "carrier_fp" in f and not isinstance(f["carrier_fp"], str):
        e.add("finding.carrier_fp", "must be a fingerprint")
    return e


BLOCKED_KEYS = {"category", "waiting_for", "reason", "instructions", "question", "options", "commands",
                "recommendation", "retry_after", "repeats", "op_state"}


def validate_blocked(b) -> list:
    e = Errors()
    if not isinstance(b, dict):
        return ["must be an object"]
    e.unknown("blocked", b, BLOCKED_KEYS)
    if b.get("category") not in ("conflict", "external", "decision", "dependency", "capability"):
        e.add("blocked.category", "unknown category")
    wf = b.get("waiting_for")
    if wf not in ("agent", "human", "time", "dependency"):
        e.add("blocked.waiting_for", "must be agent, human, time or dependency")
    if not _is_str(b.get("reason")):
        e.add("blocked.reason", "must be a string")
    if wf == "agent" and not _is_str(b.get("instructions")):
        e.add("blocked.instructions", "required when waiting for an agent")
    if wf == "human" and not _is_str(b.get("question")):
        e.add("blocked.question", "required when waiting for a human")
    if wf == "time" and not _is_iso(b.get("retry_after")):
        e.add("blocked.retry_after", "required when waiting for time")
    if "options" in b and not _strings(b["options"]):
        e.add("blocked.options", "must be an array of strings")
    if "commands" in b and not (isinstance(b["commands"], dict) and all(_strings(v) for v in b["commands"].values())):
        e.add("blocked.commands", "must map labels to argv arrays")
    if not _is_int(b.get("repeats")) or b.get("repeats", 0) < 1:
        e.add("blocked.repeats", "must be an integer >= 1")
    if "op_state" in b and not isinstance(b["op_state"], dict):
        e.add("blocked.op_state", "must be an object")
    return e


# ----------------------------------------------------------------------------------------------- input files (§3.10–§3.13)


def _check_responses(e: Errors, responses):
    if not isinstance(responses, dict):
        e.add("responses", "must be an object")
        return
    for k, v in responses.items():
        if not isinstance(v, str) or not re.match(r"^(fixed|disputed): \S", v):
            e.add(f"responses.{k}", "must start with 'fixed: ' or 'disputed: ' followed by text")


def _check_new_findings(e: Errors, findings, review: bool):
    if not isinstance(findings, list):
        e.add("findings", "must be an array")
        return
    for i, f in enumerate(findings):
        w = f"findings[{i}]"
        if not isinstance(f, dict):
            e.add(w, "must be an object")
            continue
        if "id" in f:
            if not review:
                e.add(w, "only review nodes give prior findings a status")
            e.unknown(w, f, {"id", "status"})
            if f.get("status") not in ("open", "resolved"):
                e.add(f"{w}.status", "must be open or resolved")
        else:
            e.unknown(w, f, {"target", "text"})
            if "target" in f and not (isinstance(f["target"], str) and NODE_ID.match(f["target"])):
                e.add(f"{w}.target", "must be a node id")
            if not isinstance(f.get("text"), str) or not f["text"].strip():
                e.add(f"{w}.text", "must be non-empty")
            elif len(f["text"].encode("utf-8")) > TEXT_LIMIT:
                e.add(f"{w}.text", "too_large: put long text in the artifact")
            if not review and "target" not in f:
                e.add(f"{w}.target", "required for findings from a non-review node")


def validate_submit_output(graph: Graph, node: str, out) -> list:
    """SPEC §3.10 shape; content checks (responses coverage, review coverage) are done by submit (§4.14)."""
    e = Errors()
    if not isinstance(out, dict):
        e.add("output", "must be an object")
        return e
    nd = graph.nodes[node]
    if graph.is_review(node):
        e.unknown("output", out, {"decision", "summary", "findings", "responses"})
        if out.get("decision") not in ("approved", "changes_requested"):
            e.add("output.decision", "must be approved or changes_requested")
        if not isinstance(out.get("summary"), str) or not out["summary"].strip():
            e.add("output.summary", "required")
        _check_new_findings(e, out.get("findings", []), review=True)
    else:
        types = graph.output_types[node]
        allowed = set(types) | {"findings", "responses"}
        e.unknown("output", out, allowed)
        for k, t in types.items():
            if t == "artifact":
                if k in out:
                    e.add(f"output.{k}", "artifact outputs come from --artifact")
                continue
            if t == "checkpoint":
                if k in out:
                    v = out[k]
                    if not isinstance(v, dict) or set(v) != {"commit"} or not isinstance(v["commit"], str):
                        e.add(f"output.{k}", "a checkpoint override is {\"commit\": \"<sha>\"}")
                continue
            if k not in out:
                e.add("output", f"missing output {k!r}")
                continue
            msg = check_value_type(out[k], t)
            if msg:
                e.add(f"output.{k}", msg)
        _check_new_findings(e, out.get("findings", []), review=False)
    if "responses" in out:
        _check_responses(e, out["responses"])
    for p in find_floats(out):
        e.add(p, "floats are not allowed")
    return e


def check_value_type(v, t: str) -> str | None:
    if t == "text":
        if not isinstance(v, str):
            return "must be text"
        if len(v.encode("utf-8")) > TEXT_LIMIT:
            return "too_large: put long text in the artifact"
    elif t == "string":
        if not _one_line(v):
            return "must be a one-line string"
        if len(v.encode("utf-8")) > TEXT_LIMIT:
            return "too_large: put long text in the artifact"
    elif t == "sha":
        if not (isinstance(v, str) and SHA.match(v)):
            return "must be a 40-hex sha"
    elif t == "int":
        if not _is_int(v):
            return "must be an integer"
    elif t == "bool":
        if not isinstance(v, bool):
            return "must be a boolean"
    elif t == "strings":
        if not _strings(v):
            return "must be an array of strings"
    elif t == "object":
        if not isinstance(v, dict):
            return "must be an object"
    elif t == "list":
        if not isinstance(v, list):
            return "must be an array"
    return None


def validate_blocked_file(b) -> list:
    e = Errors()
    if not isinstance(b, dict):
        e.add("blocked", "must be an object")
        return e
    e.unknown("blocked", b, {"waiting_for", "question", "instructions", "options", "recommendation", "reason", "category"})
    wf = b.get("waiting_for")
    if wf not in ("human", "agent"):
        e.add("blocked.waiting_for", "must be human or agent")
    if wf == "human" and (not isinstance(b.get("question"), str) or not b["question"].strip()):
        e.add("blocked.question", "required when waiting for a human")
    if wf == "agent" and (not isinstance(b.get("instructions"), str) or not b["instructions"].strip()):
        e.add("blocked.instructions", "required when waiting for an agent")
    if "options" in b and not _strings(b["options"]):
        e.add("blocked.options", "must be an array of strings")
    if "category" in b and b["category"] not in ("conflict", "external", "decision", "dependency", "capability"):
        e.add("blocked.category", "unknown category")
    if "reason" in b and not _one_line(b["reason"]):
        e.add("blocked.reason", "one line")
    for k in ("question", "instructions", "recommendation"):
        if isinstance(b.get(k), str) and len(b[k].encode("utf-8")) > TEXT_LIMIT:
            e.add(f"blocked.{k}", "too_large")
    return e


def validate_answer_file(kind: str, a) -> list:
    """kind: "approve" (human review node), "blocked" (a blocked record waiting for a human) or "dispute"."""
    e = Errors()
    if not isinstance(a, dict):
        e.add("answer", "must be an object")
        return e
    if kind == "approve":
        e.unknown("answer", a, {"decision", "summary", "quote", "decided_by", "decided_at", "findings"})
        if a.get("decision") not in ("approved", "changes_requested"):
            e.add("answer.decision", "must be approved or changes_requested")
        need = ("summary", "quote", "decided_by")
        if "findings" in a:
            _check_new_findings(e, a["findings"], review=True)
            for i, f in enumerate(a["findings"] if isinstance(a["findings"], list) else []):
                if isinstance(f, dict) and "id" in f:
                    e.add(f"answer.findings[{i}]", "human answers add findings; they do not give prior ones a status")
    elif kind == "blocked":
        e.unknown("answer", a, {"text", "quote", "decided_by", "decided_at"})
        need = ("text", "quote", "decided_by")
    elif kind == "dispute":
        e.unknown("answer", a, {"finding", "decision", "quote", "decided_by"})
        if a.get("decision") not in ("uphold", "waive"):
            e.add("answer.decision", "must be uphold or waive")
        need = ("finding", "quote", "decided_by")
    else:
        raise ValueError(kind)
    for k in need:
        if not isinstance(a.get(k), str) or not a[k].strip():
            e.add(f"answer.{k}", "required, non-empty")
    if "decided_at" in a and not _is_iso(a["decided_at"]):
        e.add("answer.decided_at", "must be an ISO time")
    for k, v in a.items():
        if isinstance(v, str) and len(v.encode("utf-8")) > TEXT_LIMIT:
            e.add(f"answer.{k}", "too_large")
    return e


def validate_new_file(n) -> list:
    e = Errors()
    if not isinstance(n, dict):
        e.add("new", "must be an object")
        return e
    e.unknown("new", n, {"title", "spec", "priority", "release", "depends_on", "skip", "links", "graph", "state"})
    if not _one_line(n.get("title")) or not 1 <= len(n.get("title") or "") <= 200:
        e.add("new.title", "required: 1-200 characters, one line")
    if not isinstance(n.get("spec"), str) or not n["spec"].strip():
        e.add("new.spec", "required")
    if "state" in n and n["state"] not in ("open", "held"):
        e.add("new.state", "must be open or held")
    return e
