"""Generated stored-plan checker. Regenerate with tools/package_checker.py.
No planning worker or dispatch. Canonical completeness is opt-in host policy.
"""
import hashlib
import json


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

def validate_result(ctx, goal, proposal):
    def refused(message):
        return {'ok': False, 'errors': [message]}
    if type(proposal) is not dict or proposal.get('execution_authorized') is not False:
        return refused('$.execution_authorized: must explicitly remain false')
    context_fn = getattr(ctx, 'validation_context', None)
    lookup = getattr(ctx, 'artifact_revision', None)
    if not callable(context_fn) or not callable(lookup):
        return refused('$: host custody context unavailable')
    context = context_fn(goal)
    request = context.get('request') if type(context) is dict else None
    if type(request) is not dict or request.get('kind') != 'plan' or request.get('receiving_goal') != goal.get('id') or request.get('to_swarm') != goal.get('swarm_id'):
        return refused('$: not the receiving goal of a native planning request')
    if context.get('request_state') != 'working' or goal.get('status') != 'claimed':
        return refused('$: planning request is not held and working')
    ref = proposal.get('plan')
    if type(ref) is not dict or type(ref.get('artifact_id')) is not str or type(ref.get('n')) is not int or ref['n'] < 1:
        return refused('$.plan: exact artifact revision required')
    stored = lookup(ref['artifact_id'], ref['n'])
    if type(stored) is not dict or stored.get('kind') != 'plan' or stored.get('owner_swarm') != goal.get('swarm_id'):
        return refused('$.plan: stored plan is absent or outside planner custody')
    if stored.get('artifact_id') != ref['artifact_id'] or stored.get('revision') != ref['n'] or stored.get('digest') != ref.get('digest'):
        return refused('$.plan: revision identity or digest differs from Hive')
    body = stored.get('body')
    if type(body) is not str or len(body.encode()) > 256 * 1024 or 'sha256:' + hashlib.sha256(body.encode()).hexdigest() != stored['digest']:
        return refused('$.plan: stored body digest invalid')
    if 'body' in ref and ref['body'] != body:
        return refused('$.plan.body: returned copy differs from stored body')
    try:
        validate_plan(json.loads(body))
    except (Refused, ValueError, TypeError, RecursionError):
        return refused('$.plan.body: stored plan structure invalid')
    constraints = request.get('constraints') or {}
    strict = constraints.get('require_review_complete', False)
    if type(strict) is not bool:
        return refused('$: require_review_complete must be a host policy boolean')
    if strict:
        findings_fn = getattr(ctx, 'findings', None)
        if not callable(findings_fn):
            return refused('$: canonical review context unavailable')
        review = findings_fn(request['id'], ref['artifact_id'], ref['n'])
        subject = {'artifact_id': ref['artifact_id'], 'revision': ref['n'], 'digest': ref['digest']}
        if type(review) is not dict or review.get('request_id') != request['id'] or review.get('subject') != subject or review.get('authority') != 'none':
            return refused('$: canonical review context refused or mismatched')
        if review.get('latest_revision') != ref['n']:
            return refused('$.plan: strict return requires latest stored revision')
        # Exact records retain original dissent, responses, dispositions and QC notes.
        for field, identity in [('findings', 'id'), ('reviews', 'request_id')]:
            returned, stored_rows = proposal.get(field), review.get(field)
            if type(returned) is not list or type(stored_rows) is not list:
                return refused('$.' + field + ': complete canonical records required')
            if any(type(row) is not dict or type(row.get(identity)) is not str for row in returned + stored_rows):
                return refused('$.' + field + ': invalid record identity')
            supplied = {row[identity]: row for row in returned}
            authoritative = {row[identity]: row for row in stored_rows}
            if len(supplied) != len(returned) or len(authoritative) != len(stored_rows) or canonical(supplied) != canonical(authoritative):
                return refused('$.' + field + ': records differ from canonical review context')
        mandates = constraints.get('required_review_mandates')
        if type(mandates) is not list or not mandates or len(mandates) > 50 or any(type(m) is not dict or type(m.get('id')) is not str or type(m.get('version')) is not str for m in mandates):
            return refused('$: versioned required_review_mandates must come from host request policy')
        required = {(m['id'], m['version']) for m in mandates}
        if len(required) != len(mandates):
            return refused('$: duplicate required review mandate')
        covered = set()
        for row in review['reviews']:
            if row.get('subject') != subject:
                continue  # Historical reviews remain returned but cannot cover this revision.
            if row.get('state') in {'queued', 'working', 'needs-approval', 'in-review'}:
                return refused('$.reviews: current revision review is unfinished')
            if row.get('state') != 'completed':
                continue
            receipt = row.get('receipt')
            if type(receipt) is not dict or receipt.get('subject') != subject or receipt.get('authority') != 'none':
                return refused('$.reviews: completed review lacks its exact receipt')
            mandate = receipt.get('mandate') or {}
            if type(mandate.get('id')) is not str or type(mandate.get('version')) is not str:
                return refused('$.reviews: invalid receipt mandate')
            covered.add((mandate['id'], mandate['version']))
        if required - covered:
            return refused('$.reviews: required mandates not completed on latest revision')
    return {'ok': True, 'errors': []}

def describe():
    return {"contract": "0.1", "kinds": [{"id": "plan", "label": "Plan", "role": "other"}], "relations": [], "actions": []}


def home_swarms():
    # Explicit enrolment configuration; this advertises homes, not authority. No default: unset means no homes.
    import os
    return sorted(set(s.strip() for s in os.environ.get("OMEGAPLANNER_SWARMS", "").split(",") if s.strip()))


def view(ctx, focus=None, stage=None):
    return {"revision": "planner-checker-home-1", "title": "OmegaPlanner", "focus": "planner-checker",
            "items": [{"id": "planner-checker", "kind": "plan", "label": "Stored-plan checker",
                       "status": "current", "flags": [], "sources": [],
                       "summary": "Checks stored plans and canonical review return. Learning candidates remain proposals."}],
            "links": []}


def act(ctx, action, items, params):
    return {"ok": False, "status": "refused", "message": "This package checks stored plans; it has no actions."}

