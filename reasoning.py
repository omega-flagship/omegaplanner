"""Inert snapshot and derivation prototype. No MeTTa evaluator or Hive effects.

Authorization callbacks are supplied by the host; synthetic callbacks do not
establish production authentication or evaluator custody.
"""
from collections import deque
from dataclasses import dataclass
import hashlib
import json


ARITIES = {"Step": 1, "DependsOn": 2, "ChangedStep": 1, "OpenFinding": 2, "GlobalChange": 1, "ObservedSource": 1}
MAX_FACTS = 1000


class ProjectionRefused(ValueError):
    pass


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class Fact:
    predicate: str
    args: tuple[str, ...]
    source_id: str
    source_version: str

    def __post_init__(self):
        if type(self.predicate) is not str or self.predicate not in ARITIES or type(self.args) is not tuple or len(self.args) != ARITIES[self.predicate]:
            raise ProjectionRefused("invalid fact shape")
        if any(type(v) is not str or not v or len(v) > 256 for v in (*self.args, self.source_id, self.source_version)):
            raise ProjectionRefused("invalid fact identity")


@dataclass(frozen=True)
class Snapshot:
    principal: str
    scope: str
    artifact_digest: str
    observed_at: int
    expires_at: int
    facts: tuple[Fact, ...]
    binding: str


def _body(principal, scope, artifact_digest, observed_at, expires_at, facts):
    return {"schema": "planner-inert-facts-v1", "principal": principal, "scope": scope,
            "artifact_digest": artifact_digest, "observed_at": observed_at, "expires_at": expires_at,
            "facts": [{"predicate": f.predicate, "args": f.args, "source_id": f.source_id,
                       "source_version": f.source_version} for f in facts]}


def snapshot(*, principal, scope, artifact_digest, observed_at, expires_at, facts, authorize):
    for value in (principal, scope, artifact_digest):
        if type(value) is not str or not value or len(value) > 256:
            raise ProjectionRefused("invalid snapshot identity")
    if type(observed_at) is not int or type(expires_at) is not int or not 0 <= observed_at < expires_at:
        raise ProjectionRefused("invalid snapshot lifetime")
    if type(facts) not in (list, tuple) or len(facts) > MAX_FACTS or any(type(f) is not Fact for f in facts):
        raise ProjectionRefused("invalid or oversized projection")
    frozen = tuple(sorted(set(facts), key=lambda f: (f.predicate, f.args, f.source_id, f.source_version)))
    versions = {}
    for f in frozen:
        if f.source_id in versions and versions[f.source_id] != f.source_version:
            raise ProjectionRefused("incoherent source versions")
        versions[f.source_id] = f.source_version
        if authorize(principal, scope, f.source_id) is not True:
            raise ProjectionRefused("source not authorized")
    steps = {f.args[0] for f in frozen if f.predicate == "Step"}
    edges = [f.args for f in frozen if f.predicate == "DependsOn"]
    if any(step not in steps for edge in edges for step in edge) or any(f.args[-1] not in steps for f in frozen if f.predicate in {"ChangedStep", "OpenFinding"}):
        raise ProjectionRefused("dangling step reference")
    # Cycle checking covers the whole graph, including disconnected components.
    prerequisites = {step: set() for step in steps}
    dependants = {step: set() for step in steps}
    for dependent, predecessor in edges:
        prerequisites[dependent].add(predecessor)
        dependants[predecessor].add(dependent)
    ready = deque(sorted(s for s in steps if not prerequisites[s]))
    visited = 0
    while ready:
        step = ready.popleft()
        visited += 1
        for dependent in sorted(dependants[step]):
            prerequisites[dependent].discard(step)
            if not prerequisites[dependent]:
                ready.append(dependent)
    if visited != len(steps):
        raise ProjectionRefused("dependency cycle")
    body = _body(principal, scope, artifact_digest, observed_at, expires_at, frozen)
    return Snapshot(principal, scope, artifact_digest, observed_at, expires_at, frozen, digest(body))


def check_current(snap, *, now, artifact_digest, source_versions, authorize):
    """Reject stale data before result use; this does not authorize execution."""
    if type(snap) is not Snapshot or digest(_body(snap.principal, snap.scope, snap.artifact_digest, snap.observed_at, snap.expires_at, snap.facts)) != snap.binding:
        raise ProjectionRefused("snapshot binding mismatch")
    if type(now) is not int or not snap.observed_at <= now < snap.expires_at:
        raise ProjectionRefused("snapshot expired or not yet valid")
    if artifact_digest != snap.artifact_digest:
        raise ProjectionRefused("artifact changed")
    for f in snap.facts:
        if source_versions.get(f.source_id) != f.source_version:
            raise ProjectionRefused("source changed")
        if authorize(snap.principal, snap.scope, f.source_id) is not True:
            raise ProjectionRefused("source access revoked")


def review_scope(snap, *, now, artifact_digest, source_versions, authorize):
    """Bounded transitive review closure with a justification for every step."""
    check_current(snap, now=now, artifact_digest=artifact_digest, source_versions=source_versions, authorize=authorize)
    reasons = {}
    global_changes = [f for f in snap.facts if f.predicate == "GlobalChange"]
    if global_changes:
        for f in snap.facts:
            if f.predicate == "Step":
                reasons[f.args[0]] = [{"rule": "global-change-v1", "premise": g.source_id, "changed_context": g.args[0]} for g in global_changes]
    for f in snap.facts:
        if f.predicate == "ChangedStep":
            reasons.setdefault(f.args[0], []).append({"rule": "changed-step-v1", "premise": f.source_id})
        if f.predicate == "OpenFinding":
            reasons.setdefault(f.args[1], []).append({"rule": "open-objection-v1", "finding": f.args[0], "premise": f.source_id})
    # Open objections are review seeds too. Closure may conservatively include
    # their dependants, but never silently drops an unchanged open objection.
    while True:
        new = {}
        for f in snap.facts:
            if f.predicate == "DependsOn":
                dependent, predecessor = f.args
                if predecessor in reasons and dependent not in reasons:
                    new.setdefault(dependent, []).append({"rule": "dependent-review-v1", "predecessor": predecessor, "premise": f.source_id})
        if not new:
            break
        reasons.update(new)
    return {"snapshot_binding": snap.binding, "artifact_digest": snap.artifact_digest,
            "rule_set": "review-closure-v1", "steps": sorted(reasons),
            "derivations": {k: reasons[k] for k in sorted(reasons)},
            "execution_authorized": False, "status": "proposed-review-scope"}
