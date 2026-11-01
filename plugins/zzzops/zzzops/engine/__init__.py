"""ZzzOps engine: per-goal state branches, a pure frontier and four operations (docs/design/DESIGN.md, docs/design/SPEC.md)."""

ENGINE_VERSION = "1.2.0"
FOLLOWS_SINCE = "1.2.0"         # the engine that reads the finding key `follows` (G1028; G1027 maps it to finding_follows)
REQUIRES_MIN = "0.0.0"          # SPEC §4.5: the oldest engine whose semantics this one coexists with
GOAL_SCHEMAS = (1,)             # goal schemas this engine reads; it writes the last
WORKFLOW_SCHEMA = 1
POLICY_SCHEMA = 2
FP_VERSION = "v1"
