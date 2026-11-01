"""ZzzOps engine: per-goal state branches, a pure frontier and four operations (DESIGN.md, SPEC.md)."""

ENGINE_VERSION = "1.0.0"
REQUIRES_MIN = "0.0.0"          # SPEC §4.5: the oldest engine whose semantics this one coexists with
GOAL_SCHEMAS = (1,)             # goal schemas this engine reads; it writes the last
WORKFLOW_SCHEMA = 1
POLICY_SCHEMA = 2
FP_VERSION = "v1"
