"""Strict, current GitHub GraphQL observation of an exact label node."""

import json


MANAGEMENT_PERMISSIONS = frozenset({"TRIAGE", "WRITE", "MAINTAIN", "ADMIN"})
LABEL_QUERY = ("query($id:ID!,$owner:String!,$name:String!){"
               "repository(owner:$owner,name:$name){id nameWithOwner hasIssuesEnabled viewerPermission}"
               "node(id:$id){__typename ... on Label{id name description repository{nameWithOwner}}}}")


def query_arguments(repository, node_id):
    if not isinstance(repository, str) or repository.count("/") != 1 or not isinstance(node_id, str) or not node_id:
        raise ValueError("Invalid exact label observation target")
    owner, name = repository.split("/", 1)
    if not owner or not name:
        raise ValueError("Invalid repository identity")
    return ["api", "graphql", "-F", f"id={node_id}", "-F", f"owner={owner}",
            "-F", f"name={name}", "-f", f"query={LABEL_QUERY}"]


def classify(result, repository, node_id):
    """Return ('absent', None), ('live', label) or ('unknown', None)."""
    try:
        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate GitHub observation key")
                value[key] = item
            return value

        body = json.loads(result.stdout, object_pairs_hook=unique_object)
        if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
            return "unknown", None
        data = body["data"]
        facts = data.get("repository")
        if (not isinstance(facts, dict) or not isinstance(facts.get("id"), str) or not facts["id"]
                or facts.get("nameWithOwner") != repository
                or facts.get("hasIssuesEnabled") is not True
                or facts.get("viewerPermission") not in MANAGEMENT_PERMISSIONS
                or "node" not in data):
            return "unknown", None
        errors = body.get("errors", [])
        if not isinstance(errors, list):
            return "unknown", None
        node = data["node"]
        if node is None:
            if not errors and result.returncode == 0:
                return "absent", None
            expected = f"Could not resolve to a node with the global id of '{node_id}'."
            if (result.returncode == 1 and len(errors) == 1 and isinstance(errors[0], dict)
                    and errors[0].get("type") == "NOT_FOUND" and errors[0].get("path") == ["node"]
                    and errors[0].get("message") == expected):
                return "absent", None
            return "unknown", None
        if errors or result.returncode != 0 or not isinstance(node, dict):
            return "unknown", None
        node_repo = node.get("repository")
        if (node.get("__typename") != "Label" or node.get("id") != node_id
                or not isinstance(node.get("name"), str) or not node["name"]
                or "description" not in node
                or not isinstance(node.get("description"), (str, type(None)))
                or not isinstance(node_repo, dict)
                or node_repo.get("nameWithOwner") != repository):
            return "unknown", None
        return "live", {"node_id": node_id, "name": node["name"],
                        "description": node["description"]}
    except (ValueError, TypeError, AttributeError):
        return "unknown", None
