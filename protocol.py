"""Synthetic application-side planning contract; no Hive routes or live minds."""
import hashlib
import json
from copy import deepcopy


class Refused(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


MAX_PLAN_BYTES = 256 * 1024
MAX_STEPS = 256
MAX_EDGES = 512


def validate_plan(body):
    """Bounded structural validation, not evidence or execution qualification."""
    from collections import deque
    if type(body) is not dict:
        raise Refused("invalid_plan_object")
    # Check nested data iteratively before JSON encoding to bound depth and size.
    pending = [(body, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 32 or count > 20000:
            raise Refused("plan_structure_limit")
        if type(value) is dict:
            if count + len(pending) + len(value) > 20000:
                raise Refused("plan_structure_limit")
            if any(type(k) is not str for k in value):
                raise Refused("invalid_json_key")
            pending.extend((v, depth + 1) for v in value.values())
        elif type(value) is list:
            if count + len(pending) + len(value) > 20000:
                raise Refused("plan_structure_limit")
            pending.extend((v, depth + 1) for v in value)
        elif type(value) is str and len(value) > MAX_PLAN_BYTES:
            raise Refused("plan_size_limit")
        elif type(value) not in (str, int, float, bool, type(None)):
            raise Refused("invalid_json_value")
    try:
        encoded = canonical(body)
    except (ValueError, TypeError, RecursionError) as exc:
        raise Refused("invalid_json_value") from exc
    if len(encoded.encode()) > MAX_PLAN_BYTES:
        raise Refused("plan_size_limit")
    for field in ("goal", "acceptance", "steps", "constraints", "unknowns"):
        if field not in body:
            raise Refused("missing_" + field)

    def text(value, limit=4000):
        return type(value) is str and bool(value.strip()) and len(value) <= limit

    def texts(value, allow_empty=True):
        return type(value) is list and len(value) <= 256 and (allow_empty or bool(value)) and all(text(v) for v in value)

    if not text(body["goal"]) or not texts(body["acceptance"], False) or not texts(body["unknowns"]):
        raise Refused("invalid_plan_text")
    if type(body["constraints"]) is not dict:
        raise Refused("invalid_constraints")
    steps = body["steps"]
    if type(steps) is not list or not 0 < len(steps) <= MAX_STEPS:
        raise Refused("step_count_limit")
    graph = {}
    for step in steps:
        if type(step) is not dict:
            raise Refused("invalid_step")
        for field in ("id", "depends_on", "output", "completion_check", "owner_proposal", "capabilities_required", "resources", "fallback"):
            if field not in step:
                raise Refused("missing_" + field)
        if not text(step["id"], 256):
            raise Refused("invalid_step_id")
        if step["id"] in graph:
            raise Refused("duplicate_step")
        if not texts(step["depends_on"]) or len(set(step["depends_on"])) != len(step["depends_on"]):
            raise Refused("invalid_dependencies")
        if not all(text(step[f]) for f in ("output", "completion_check", "owner_proposal", "fallback")):
            raise Refused("invalid_step_text")
        if not texts(step["capabilities_required"]) or type(step["resources"]) is not dict:
            raise Refused("invalid_step_resources")
        graph[step["id"]] = set(step["depends_on"])
    if sum(len(deps) for deps in graph.values()) > MAX_EDGES:
        raise Refused("edge_count_limit")
    if any(dep not in graph for deps in graph.values() for dep in deps):
        raise Refused("unknown_dependency")
    dependants = {node: [] for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            dependants[dep].append(node)
    ready = deque(node for node, deps in graph.items() if not deps)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for dependent in dependants[node]:
            graph[dependent].remove(node)
            if not graph[dependent]:
                ready.append(dependent)
    if visited != len(graph):
        raise Refused("dependency_cycle")


class PlanningHarness:
    """Explicit test actors and in-memory state, never production authentication."""

    def __init__(self, requester="requester", planner="planner", reviewer="reviewer"):
        if len({requester, planner, reviewer}) != 3:
            raise Refused("independence_required")
        self.requester, self.planner, self.reviewer = requester, planner, reviewer
        self._revisions = []
        self._findings = {}
        self._reviews = {}
        self.cancelled = False

    def _active(self):
        if self.cancelled:
            raise Refused("request_cancelled")

    def revision(self, n, actor):
        self._active()
        if actor not in {self.requester, self.planner, self.reviewer}:
            raise Refused("foreign_swarm")
        return json.loads(self._revisions[n - 1])

    def publish(self, actor, body, base_revision):
        self._active()
        if actor != self.planner:
            raise Refused("planner_only")
        if base_revision != len(self._revisions):
            raise Refused("stale_revision")
        validate_plan(body)
        n = len(self._revisions) + 1
        previous = json.loads(self._revisions[-1]) if self._revisions else None
        old = {s["id"]: s for s in previous["body"]["steps"]} if previous else {}
        new = {s["id"]: s for s in body["steps"]}
        changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        # Non-step changes require the whole plan to be reconsidered.
        global_change = previous is not None and {k: v for k, v in previous["body"].items() if k != "steps"} != {k: v for k, v in body.items() if k != "steps"}
        affected = set(new) if global_change else set(changed)
        # Include dependencies from both versions, including removed edges.
        while True:
            expanded = affected | {s["id"] for s in list(old.values()) + list(new.values()) if set(s["depends_on"]) & affected}
            if expanded == affected:
                break
            affected = expanded
        revision = {"artifact_id": "synthetic-plan", "revision": n, "parent_digest": previous["digest"] if previous else None, "body": deepcopy(body), "changed_steps": changed, "review_steps": sorted(affected)}
        revision["digest"] = "sha256:" + hashlib.sha256(canonical(revision).encode()).hexdigest()
        self._revisions.append(canonical(revision))
        for finding in self._findings.values():
            finding["applicability"].append({"revision": n, "state": "unverified"})
        return deepcopy(revision)

    def request_review(self, actor, n, mandates):
        self._active()
        if actor != self.planner:
            raise Refused("planner_only")
        revision = self.revision(n, actor)
        if n != len(self._revisions):
            raise Refused("stale_revision")
        if not mandates or any(not m.get("id") or not m.get("version") for m in mandates):
            raise Refused("invalid_mandate")
        binding = {k: revision[k] for k in ("artifact_id", "revision", "digest")}
        request_id = "synthetic-review-" + str(len(self._reviews) + 1)
        self._reviews[request_id] = {"subject": binding, "mandates": deepcopy(mandates), "completed": False}
        return {"request_id": request_id, "subject": deepcopy(binding), "mandates": deepcopy(mandates)}

    def submit_review(self, actor, result):
        self._active()
        if actor != self.reviewer:
            raise Refused("reviewer_only")
        request = self._reviews[result["request_id"]]
        if request["completed"]:
            raise Refused("review_already_completed")
        if result["subject"] != request["subject"] or result["mandates"] != request["mandates"]:
            raise Refused("binding_mismatch")
        if result["subject"]["revision"] != len(self._revisions):
            raise Refused("stale_review")
        pending = {}
        targets = {s["id"] for s in self.revision(len(self._revisions), actor)["body"]["steps"]}
        for finding in result["findings"]:
            if finding["id"] in self._findings or finding["id"] in pending:
                raise Refused("duplicate_finding")
            if finding["mandate"] not in request["mandates"] or finding["step"] not in targets:
                raise Refused("invalid_finding_target_or_mandate")
            if any(k in finding for k in ("planner_response", "disposition", "raised_on", "applicability")):
                raise Refused("reserved_finding_fields")
            for key in ("severity", "evidence_refs", "recommendation"):
                if key not in finding:
                    raise Refused("missing_" + key)
            pending[finding["id"]] = {**deepcopy(finding), "raised_on": deepcopy(request["subject"]), "planner_response": None, "disposition": None, "applicability": [{"revision": len(self._revisions), "state": "applies"}]}
        self._findings.update(pending)
        request["completed"] = True

    def respond(self, actor, finding_id, revision, stance, note):
        self._active()
        if actor != self.planner:
            raise Refused("planner_only")
        if revision != len(self._revisions):
            raise Refused("stale_revision")
        if stance not in {"addressed", "partly", "disputed"}:
            raise Refused("invalid_stance")
        self._findings[finding_id]["planner_response"] = {"revision": revision, "stance": stance, "note": note}

    def disposition(self, actor, finding_id, review_id, subject, verdict):
        self._active()
        if actor != self.reviewer:
            raise Refused("reviewer_only")
        request = self._reviews[review_id]
        if subject != request["subject"] or subject["revision"] != len(self._revisions):
            raise Refused("stale_or_mismatched_review")
        finding = self._findings[finding_id]
        if finding["mandate"] not in request["mandates"]:
            raise Refused("mandate_not_requested")
        if verdict not in {"confirmed-resolved", "still-open", "withdrawn"}:
            raise Refused("invalid_verdict")
        finding["disposition"] = {"revision": subject["revision"], "verdict": verdict, "by": actor}

    def return_plan(self, actor):
        self._active()
        if actor != self.requester:
            raise Refused("requester_only")
        return {"plan": self.revision(len(self._revisions), actor), "findings": deepcopy(list(self._findings.values())), "execution_authorized": False}

    def cancel(self, actor):
        if actor != self.requester:
            raise Refused("requester_only")
        self.cancelled = True
