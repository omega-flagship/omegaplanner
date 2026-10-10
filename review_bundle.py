"""Advisory aggregation of native review receipts. No finding closure or effects."""
from copy import deepcopy
from .protocol import Refused


def bundle(projection, subject, expected_mandates):
    if type(subject) is not dict or set(subject) != {'artifact_id','revision','digest'} or type(subject['artifact_id']) is not str or type(subject['digest']) is not str or type(subject['revision']) is not int or subject['revision'] < 1:
        raise Refused('exact_subject_required')
    if type(projection) is not dict or projection.get('subject_digest') != subject.get('digest') or type(projection.get('requests')) is not list:
        raise Refused('projection_subject_mismatch')
    if type(expected_mandates) is not list or not expected_mandates or len(expected_mandates) > 50 or any(type(m) is not dict or type(m.get('id')) is not str or type(m.get('version')) is not str for m in expected_mandates):
        raise Refused('expected_mandates_required')
    expected = {(m['id'],m['version']) for m in expected_mandates}
    if len(expected) != len(expected_mandates):
        raise Refused('duplicate_expected_mandate')
    rows = projection['requests']
    if len(rows) > 256 or projection.get('count') != len(rows):
        raise Refused('invalid_projection_count')
    ids, covered, pending, recommendations = set(), set(), [], []
    for row in rows:
        if type(row) is not dict or type(row.get('request_id')) is not str or row['request_id'] in ids:
            raise Refused('invalid_request_identity')
        ids.add(row['request_id'])
        receipt = row.get('receipt')
        if receipt is None:
            pending.append(row['request_id'])
            continue
        if type(receipt) is not dict or receipt.get('subject') != subject or receipt.get('request_id') != row['request_id'] or receipt.get('authority') != 'none':
            raise Refused('receipt_subject_or_authority_mismatch')
        mandate = receipt.get('mandate')
        if type(mandate) is not dict or (mandate.get('id'),mandate.get('version')) not in expected:
            raise Refused('unexpected_mandate')
        rec = receipt.get('recommendation')
        if rec not in {'proceed','revise','hold','unresolved'}:
            raise Refused('invalid_recommendation')
        recommendations.append(rec)
        # In-review is not accepted; failed/cancelled receipts cannot cover a mandate.
        if row.get('state') != 'completed':
            pending.append(row['request_id'])
        else:
            covered.add((mandate['id'],mandate['version']))
    missing = sorted(expected - covered)
    # Preserve severe dissent even when coverage is incomplete; both are reported.
    status = next((r for r in ['hold','revise','unresolved'] if r in recommendations), 'pending' if pending or missing else 'proceed-proposal')
    return {'subject':deepcopy(subject),'requests':deepcopy(rows),
            'missing_mandates':[{'id':i,'version':v} for i,v in missing],
            'pending_requests':pending,'coverage_complete':not missing and not pending,
            'status':status,'execution_authorized':False,
            'finding_completeness':'unverified','policy':'preserve-each-verdict-v1'}
