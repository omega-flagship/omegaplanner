"""Offline Planner subject binding to the shared Bench/Learn contract.

No evaluator receipts, host artifact identities or custody are manufactured.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import time
from omegalearn.bench_adapter import PrerequisiteExecutor
from omegalearn.core import digest, Refused as LearnRefused
from .protocol import PlanningHarness, Refused


class PlannerExecutor:
    def __init__(self, consumer, package, episodes, mode, environment_pin,
                 configuration, registration_pin=None, plan_sink=None, capture_binding=None):
        self.consumer = consumer
        self.package = deepcopy(package)
        self.mode = mode
        self.environment_pin = environment_pin
        self.registration_pin = registration_pin
        self._plan_sink = plan_sink
        self._capture_binding = deepcopy(capture_binding)
        if plan_sink is not None and not capture_binding:
            raise Refused("capture_binding_required")
        self._captures = []
        self._plans = PlanningHarness()
        self._revision = 0
        def inspect(p):
            try:
                record = consumer.candidate(p['id'], p['version'])
            except Refused as error:
                raise LearnRefused(str(error)) from error
            return dict(record['package'], local_status='proposed')
        self._component = PrerequisiteExecutor(package, episodes, mode, environment_pin, inspect)
        self.subject_pin = digest({'component_pin': self._component.subject_pin,
            'controller': 'planner-prerequisite-proposal/1', 'configuration': configuration,
            'capture_binding':self._capture_binding,
            'sources': {name: sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ('bench_subject.py', 'learning.py', 'protocol.py')}})

    def captures(self):
        return deepcopy(self._captures)

    def execute(self, request):
        if request['subject_pin'] != self.subject_pin or request['environment_pin'] != self.environment_pin:
            raise Refused('execution_binding_mismatch')
        started = time.monotonic()
        forwarded = dict(deepcopy(request), subject_pin=self._component.subject_pin)
        result = self._component.execute(forwarded)
        local_plan = None
        artifact = None
        capture_error = None
        if result['status'] == 'ok':
            missing = result['response']
            actions = request['input']['case']['actions']
            def step(identifier, deps, output):
                return {'id': identifier, 'depends_on': deps, 'output': output,
                        'completion_check': 'independent owner evidence required',
                        'owner_proposal': 'unassigned', 'capabilities_required': [],
                        'resources': {}, 'fallback': 'return for replanning'}
            dependencies = ['prereq-'+p for p in missing]
            body = {'goal':'Resolve prerequisites before proposed actions',
                'acceptance':['prerequisite evidence independently checked'],
                'constraints':{'synthetic':True, 'execution_authorized':False},
                'unknowns':['actual execution and task outcome unobserved'],
                'steps':[step('prereq-'+p, [], p) for p in missing] +
                        [step('action-'+a, dependencies, a) for a in sorted(actions)]}
            try:
                local_plan = self._plans.publish('planner', body, self._revision)
                self._revision += 1
                if self._plan_sink is not None:
                    artifact = self._plan_sink(deepcopy(local_plan), deepcopy(request))
                    if type(artifact) is not dict or set(artifact) != {'artifact_id','revision','digest'}:
                        raise Refused('invalid_plan_capture_binding')
            except Exception as error:
                artifact = None
                capture_error = type(error).__name__
                result['status'], result['response'] = 'failed', None
        # Include consumer checking and plan construction, including failures.
        result['usage']['seconds'] = time.monotonic() - started
        self._captures.append({'task_id':request['task_id'], 'seed':request['seed'],
            'arm':self.mode, 'registration_pin':self.registration_pin,
            'subject_pin':self.subject_pin, 'environment_pin':self.environment_pin,
            'local_plan':local_plan, 'plan_artifact':artifact,
            'capture_error':capture_error,
            'package':{'kind':self.package['kind'], 'version':self.package['version'],
                       'digest':self.package['digest'], 'exposure':self.mode},
            'source_evidence_refs':deepcopy(self.package['evidence_refs']),
            'source_status':'simulated-development', 'outcome_refs':[],
            'usage':deepcopy(result['usage']), 'terminal_status':result['status'],
            'private_response_commitment':None, 'capture_receipt':None,
            'custody':'unverified', 'capability_acceptance_ready':False})
        return result


def host_plan_sink(ctx):
    """Explicit existing-host proposal capture, not evaluator custody or adoption.

    ctx must be host-created and actor-scoped; capabilities are checked by the
    host. This writes an artifact only when the caller explicitly selects it.
    """
    from .protocol import canonical
    def capture(local_plan, request):
        text = canonical(local_plan['body'])
        out = ctx.publish('plan', 'Synthetic prerequisite proposal', text)
        row = ctx.read_revision(out['artifact_id'], out['revision'])
        if row['body'] != text or row['digest'] != out['digest'] or row['n'] != out['revision']:
            raise Refused('plan_capture_readback_mismatch')
        if row['digest'] != 'sha256:'+sha256(text.encode()).hexdigest():
            raise Refused('plan_capture_digest_mismatch')
        return {k:out[k] for k in ('artifact_id','revision','digest')}
    return capture
