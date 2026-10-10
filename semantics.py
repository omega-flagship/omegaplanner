"""Stored-plan validation with opt-in canonical review-return completeness."""
import hashlib
import json
from .protocol import Refused, validate_plan, canonical


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
