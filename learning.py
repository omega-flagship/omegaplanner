"""Opt-in OmegaLearn consumer. Pure L0 library: no authentication or execution.

Learn owns envelope admission. Callbacks below must be its admission/inspection
adapter, not a permissive substitute. Caller identity is explicitly unauthenticated.
"""
from copy import deepcopy
from hashlib import sha256
from .protocol import Refused, canonical, validate_plan


def _bound(value):
    try:
        encoded = canonical(value).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as exc:
        raise Refused('invalid_learning_json') from exc
    if len(encoded) > 256 * 1024:
        raise Refused('learning_export_too_large')
    return encoded


class PlannerLearning:
    def __init__(self, admit_event, inspect_package):
        self._admit_event = admit_event
        self._inspect_package = inspect_package
        self._packages = {}
        self._retracted = set()

    def export_episode(self, *, event_id, caller, scope, subject, export_bytes,
                       plan, current_subject, evidence_refs, predictions,
                       assumptions, review_findings, outcome_refs, corrections,
                       permissions, payload):
        """Prepare Learn's event from an exact caller-owned source export.

        current_subject is caller-supplied, not authenticated host custody.
        The exact export must contain the same plan sent for validation.
        Learn admission independently resolves scope, sources and references.
        """
        import json
        if type(export_bytes) is not bytes or len(export_bytes) > 256 * 1024:
            raise Refused('invalid_source_export')
        try:
            source = json.loads(export_bytes)
        except (ValueError, UnicodeError) as exc:
            raise Refused('invalid_source_export') from exc
        if type(source) is not dict or (source != plan and source.get('plan') != plan):
            raise Refused('plan_export_mismatch')
        validate_plan(plan)
        if subject != current_subject:
            raise Refused('stale_plan_subject')
        if type(subject) is not dict or set(subject) != {'id', 'revision', 'digest'}:
            raise Refused('invalid_subject')
        if subject['digest'] != sha256(export_bytes).hexdigest():
            raise Refused('source_digest_mismatch')
        event = {'schema': 'omegalearn/event/1', 'id': event_id,
                 'owner': caller, 'scope': scope, 'subject': deepcopy(subject),
                 'evidence_refs': deepcopy(evidence_refs),
                 'predictions': deepcopy(predictions), 'assumptions': deepcopy(assumptions),
                 'review_findings': deepcopy(review_findings),
                 'outcome_refs': deepcopy(outcome_refs), 'corrections': deepcopy(corrections),
                 'permissions': deepcopy(permissions), 'payload': deepcopy(payload)}
        _bound(event)
        # Shared envelope validator/resolver owns admission and deduplication.
        result = self._admit_event(deepcopy(event))
        return {'event': event, 'admission': deepcopy(result),
                'identity_status': 'caller-supplied-unauthenticated'}

    def receive_candidate(self, package):
        """Inspect an inert candidate, preserving immutable versions.

        inspect_package must reject invalid/stale Learn packages. Its result
        carries the transitive source evidence closure as dependency_refs.
        Receipt is neither delivery, attachment, invocation nor adoption.
        """
        _bound(package)
        inspection = self._inspect_package(deepcopy(package))
        if type(inspection) is not dict or inspection.get('eligible') is not True:
            raise Refused('learn_candidate_ineligible')
        refs = inspection.get('dependency_refs')
        if type(refs) is not list or any(type(r) is not str or not r for r in refs):
            raise Refused('missing_dependency_closure')
        if package.get('kind') != 'skill':
            raise Refused('planner_first_slice_skill_only')
        content = package.get('content', {})
        if type(content) is not dict or not {'rules', 'procedure', 'track_record_refs'} <= set(content):
            raise Refused('missing_skill_procedure')
        key = (package['id'], package['version'])
        old = self._packages.get(key)
        if old is not None:
            if old['package'] != package:
                raise Refused('immutable_package_conflict')
            if old['stale']:
                raise Refused('stale_learning_candidate')
            return deepcopy(old)
        entry = {'package': deepcopy(package), 'dependency_refs': sorted(set(refs)),
                 'stale': bool(set(refs) & self._retracted),
                 'recipient_receipt': True, 'attached': False, 'callable': False,
                 'measured_useful': False, 'execution_authorized': False}
        if entry['stale']:
            raise Refused('retracted_candidate_source')
        self._packages[key] = entry
        return deepcopy(entry)

    def retract_source(self, evidence_id):
        """Caller-owned local projection update, not a host retraction primitive."""
        self._retracted.add(evidence_id)
        affected = []
        for key, entry in self._packages.items():
            if evidence_id in entry['dependency_refs']:
                entry['stale'] = True
                affected.append(key)
        return sorted(affected)

    def candidate(self, component_id, version):
        entry = self._packages[(component_id, version)]
        if entry['stale']:
            raise Refused('stale_learning_candidate')
        inspection = self._inspect_package(deepcopy(entry['package']))
        if inspection.get('eligible') is not True:
            raise Refused('learn_candidate_ineligible')
        return deepcopy(entry)


def from_learn_ledger(ledger, resolver):
    """Bind the real Learn API; resolver remains unauthenticated caller context."""
    def inspect(package):
        key = ledger.propose(package)
        checked = ledger.package(key)
        return {'eligible': checked['local_status'] == 'proposed',
                'dependency_refs': checked['evidence_refs'] + checked['source_events']}
    return PlannerLearning(lambda event: ledger.admit(event, resolver), inspect)


def compare_prerequisite_checks(cases, baseline, candidate):
    """Offline held-out comparison; does not load rules or infer task success.

    Callbacks are explicit caller-provided pure functions, not imported code.
    Missing prerequisites are independently supplied synthetic ground truth.
    All errors are scored and retained, rather than dropped from denominators.
    """
    rows = []
    seen = set()
    for case in cases:
        _bound(case)
        if case['id'] in seen:
            raise Refused('duplicate_evaluation_case')
        seen.add(case['id'])
        expected = set(case['missing'])
        row = {'id': case['id'], 'arms': {}}
        for name, checker in [('baseline', baseline), ('candidate', candidate)]:
            try:
                result = checker(deepcopy(case['input']))
                if type(result) is not list or any(type(v) is not str for v in result):
                    raise ValueError('invalid checker result')
                predicted = set(result)
                row['arms'][name] = {'missed': sorted(expected - predicted),
                                     'false_alarms': sorted(predicted - expected),
                                     'correct': predicted == expected, 'error': None}
            except Exception as exc:
                row['arms'][name] = {'correct': False, 'error': type(exc).__name__}
        rows.append(row)
    return {'level': 'L0', 'cases': rows, 'denominator': len(rows),
            'input_digest': sha256(_bound(cases)).hexdigest(),
            'task_success_measured': False, 'adoption_authorized': False,
            'summary': {arm: {'correct': sum(r['arms'][arm]['correct'] for r in rows),
                              'errors': sum(r['arms'][arm]['error'] is not None for r in rows)}
                        for arm in ('baseline', 'candidate')}}


def stored_plan_export(revision, current_revision):
    """Lossless existing Hive revision -> Learn export arguments.

    No read, authentication, grant or current-head lookup occurs here. Both
    records must come from a caller's appropriately scoped resolver. Hive's
    sha256 prefix and integer revision become Learn's hex and string encoding,
    with exact source bytes retained; the plan is never reserialized.
    """
    import json
    import re
    def subject(row):
        if type(row) is not dict or type(row.get('artifact_id')) is not str or not row['artifact_id']:
            raise Refused('invalid_stored_revision')
        if type(row.get('n')) is not int or row['n'] < 1:
            raise Refused('invalid_stored_revision')
        digest = row.get('digest')
        if type(digest) is not str or not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise Refused('invalid_stored_digest')
        return {'id': row['artifact_id'], 'revision': str(row['n']), 'digest': digest[7:]}
    bound = subject(revision); current = subject(current_revision)
    if bound != current:
        raise Refused('stale_plan_subject')
    if type(revision.get('body')) is not str:
        raise Refused('missing_stored_plan_body')
    try:
        raw = revision['body'].encode('utf-8')
        if len(raw) > 256 * 1024:
            raise Refused('invalid_source_export')
        body = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise Refused('invalid_stored_plan_body') from exc
    if sha256(raw).hexdigest() != bound['digest']:
        raise Refused('source_digest_mismatch')
    validate_plan(body)
    return {'subject': bound, 'current_subject': current,
            'export_bytes': raw, 'plan': body}


def from_host_exports(ledger, ctx, trusted_resolver):
    """Compose Learn's actual actor-scoped export adapter, without operator reads.

    ctx must be host-created. trusted_resolver supplies current subject, source
    grants and eligible refs; this library does not authenticate that callback.
    Host artifact access validates actor/capability/visibility independently.
    No package attachment, evidence publication or runtime use is performed.
    """
    from omegalearn.adapters import resolve_artifact_export
    def resolve(event):
        return resolve_artifact_export(ctx, event, trusted_resolver(deepcopy(event)))
    return from_learn_ledger(ledger, resolve)
