"""Read-only Hive projection adapter; never evaluates or dispatches plan text.

Client identity is an opaque local binding, not an asserted Hive principal.
Token authentication and read scope are enforced by the existing Hive APIs.
"""
import hashlib
import json
from uuid import uuid4
from .hive_adapter import HiveError
from .protocol import validate_plan
from .reasoning import Fact, ProjectionRefused, digest, snapshot, review_scope


class HiveReasoning:
    def __init__(self, planner):
        self._planner = planner
        self._client_binding = "client:" + uuid4().hex

    def _load(self, artifact_id, n):
        if type(artifact_id) is not str or not artifact_id or '/' in artifact_id or '?' in artifact_id or '#' in artifact_id:
            raise ProjectionRefused("invalid artifact identifier")
        if type(n) is not int or n < 1:
            raise ProjectionRefused("invalid revision")
        revision = self._planner.revision(artifact_id, n)
        body = revision["body"]
        if revision["artifact_id"] != artifact_id or revision["n"] != n or ("sha256:" + hashlib.sha256(body.encode()).hexdigest()) != revision["digest"]:
            raise ProjectionRefused("revision digest mismatch")
        plan = json.loads(body)
        validate_plan(plan)
        findings = self._planner.findings(artifact_id)
        previous = None
        if n > 1:
            try:
                previous_revision = self._planner.revision(artifact_id, n - 1)
                if ('sha256:' + hashlib.sha256(previous_revision['body'].encode()).hexdigest()) != previous_revision['digest']:
                    raise ProjectionRefused("parent digest mismatch")
                previous = json.loads(previous_revision['body'])
            except HiveError as exc:
                if exc.status != 403:
                    raise
        rev_source = artifact_id + ":revision:" + str(n)
        finding_source = artifact_id + ":findings"
        versions = {rev_source: digest(revision), finding_source: digest(findings)}
        facts = [Fact('ObservedSource', ('revision',), rev_source, versions[rev_source]),
                 Fact('ObservedSource', ('findings',), finding_source, versions[finding_source])]
        steps = {s['id']: s for s in plan['steps']}
        for step in plan['steps']:
            facts.append(Fact('Step', (step['id'],), rev_source, versions[rev_source]))
            for dependency in step['depends_on']:
                facts.append(Fact('DependsOn', (step['id'], dependency), rev_source, versions[rev_source]))
        global_change = previous is None
        if previous is not None:
            parent_source = artifact_id + ':revision:' + str(n - 1)
            versions[parent_source] = digest(previous_revision)
            facts.append(Fact('ObservedSource', ('parent',), parent_source, versions[parent_source]))
            global_change = {k:v for k,v in plan.items() if k != 'steps'} != {k:v for k,v in previous.items() if k != 'steps'}
            old_steps = {s['id']:s for s in previous['steps']}
            # Removed steps may affect references beyond the surviving graph.
            global_change |= bool(set(old_steps) - set(steps))
            for step_id in steps:
                if steps[step_id] != old_steps.get(step_id):
                    facts.append(Fact('ChangedStep', (step_id,), rev_source, versions[rev_source]))
        for finding in findings:
            disposition = finding.get('disposition') or {}
            if disposition.get('revision') == n and disposition.get('verdict') in {'confirmed-resolved', 'withdrawn'}:
                continue
            target = (finding.get('target') or {}).get('step')
            if target in steps:
                facts.append(Fact('OpenFinding', (finding['id'], target), finding_source, versions[finding_source]))
            else:
                global_change = True
        if global_change:
            facts.append(Fact('GlobalChange', ('global-or-unavailable-delta-context',), rev_source, versions[rev_source]))
        return revision['digest'], facts, versions

    def project(self, artifact_id, n, *, now, ttl=60):
        if type(ttl) is not int or not 0 < ttl <= 300:
            raise ProjectionRefused('invalid projection lifetime')
        artifact_digest, facts, versions = self._load(artifact_id, n)
        scope = artifact_id + ':revision:' + str(n)
        snap = snapshot(principal=self._client_binding, scope=scope, artifact_digest=artifact_digest,
                        observed_at=now, expires_at=now + ttl, facts=facts,
                        authorize=lambda principal, scope, source: source in versions)
        return snap

    def derive(self, snap, artifact_id, n, *, now):
        if snap.principal != self._client_binding or snap.scope != artifact_id + ':revision:' + str(n):
            raise ProjectionRefused('snapshot belongs to another client or scope')
        current_digest, _, versions = self._load(artifact_id, n)
        return review_scope(snap, now=now, artifact_digest=current_digest, source_versions=versions,
                            authorize=lambda principal, scope, source: source in versions)
