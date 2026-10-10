"""Boundary tests use explicit fake Learn callbacks; no Learn runtime claim."""
from copy import deepcopy
from hashlib import sha256
import pytest
from omegaplanner.learning import PlannerLearning, compare_prerequisite_checks
from omegaplanner.protocol import Refused, canonical
from omegaplanner.tests.test_protocol import plan


def package(version='1', refs=None):
    return {'id': 'prerequisite-check', 'version': version, 'kind': 'skill',
            'content': {'rules': ['(Needs deploy build)'],
                        'procedure': {'id': 'check', 'steps': ['inspect'], 'prerequisites': []},
                        'track_record_refs': []}, 'evidence_refs': refs or ['finding:1']}


def consumer():
    def inspect(p):
        return {'eligible': True, 'dependency_refs': p['evidence_refs']}
    return PlannerLearning(lambda e: {'status': 'fake-test-admitted'}, inspect)


def episode():
    body = plan(); raw = canonical({'plan': body}).encode()
    subject = {'id': 'plan:1', 'revision': '1', 'digest': sha256(raw).hexdigest()}
    return dict(event_id='episode:1', caller='planner', scope='synthetic',
                subject=subject, current_subject=deepcopy(subject), export_bytes=raw,
                plan=body, evidence_refs=['finding:1'], predictions=[], assumptions=[],
                review_findings=['finding:1'], outcome_refs=[], corrections=[],
                permissions={'audiences': ['learn'], 'derive': True, 'redistribute': False},
                payload={'kind': 'experience', 'data': {'outcome': 'unknown'}})


def test_export_keeps_open_findings_missing_outcome_and_inert_text():
    args=episode(); args['payload']['data']['text']='!(run-effect)'
    r=consumer().export_episode(**args)
    assert r['identity_status']=='caller-supplied-unauthenticated'
    assert r['event']['review_findings']==['finding:1']
    assert r['event']['outcome_refs']==[]
    assert r['event']['payload']['data']['text']=='!(run-effect)'
    args['review_findings'].clear()
    assert r['event']['review_findings']==['finding:1']


@pytest.mark.parametrize('change,reason',[
    ('stale','stale_plan_subject'), ('digest','source_digest_mismatch'),
    ('plan','plan_export_mismatch')])
def test_stale_or_mismatched_source_refused_before_admission(change,reason):
    args=episode(); calls=[]
    c=PlannerLearning(lambda e:calls.append(e),lambda p:None)
    if change=='stale': args['current_subject']['revision']=2
    if change=='digest': args['subject']['digest']='0'*64;args['current_subject']=deepcopy(args['subject'])
    if change=='plan': args['plan']['goal']='changed'
    with pytest.raises(Refused,match=reason):c.export_episode(**args)
    assert not calls


def test_shared_learn_admission_errors_propagate():
    def refuse(e):raise Refused('learn-source-grant-refused')
    with pytest.raises(Refused,match='learn-source-grant-refused'):
        PlannerLearning(refuse,lambda p:None).export_episode(**episode())


def test_versions_immutable_and_receipt_cannot_adopt():
    c=consumer(); p=package(); entry=c.receive_candidate(p)
    assert not entry['attached'] and not entry['callable'] and not entry['execution_authorized']
    assert c.receive_candidate(p)==entry
    p['content']['rules'].append('(changed)')
    with pytest.raises(Refused,match='immutable_package_conflict'):c.receive_candidate(p)
    c.receive_candidate(package('2'))
    assert c.candidate('prerequisite-check','1')['package']['content']['rules']==['(Needs deploy build)']


def test_retraction_invalidates_only_dependent_versions_and_future_receipts():
    c=consumer(); c.receive_candidate(package());c.receive_candidate(package('2',['other']))
    assert c.retract_source('finding:1')==[('prerequisite-check','1')]
    with pytest.raises(Refused,match='stale_learning_candidate'):c.candidate('prerequisite-check','1')
    assert c.candidate('prerequisite-check','2')['stale'] is False
    with pytest.raises(Refused,match='retracted_candidate_source'):c.receive_candidate(package('3'))


def test_shared_package_inspection_rejects_stale_or_missing_closure():
    for inspection in ({'eligible':False},{'eligible':True}):
        c=PlannerLearning(lambda e:None,lambda p:inspection)
        with pytest.raises(Refused):c.receive_candidate(package())


def test_comparison_retains_failures_false_alarms_and_denominator():
    cases=[{'id':'missing','input':['needs-build'],'missing':['build']},
           {'id':'ready','input':[],'missing':[]},
           {'id':'error','input':['crash'],'missing':['unknown']}]
    def learned(x):
        if 'crash' in x:raise RuntimeError('synthetic')
        return ['build'] if 'needs-build' in x else []
    result=compare_prerequisite_checks(cases,lambda x:[],learned)
    assert result['denominator']==3
    assert result['summary']=={'baseline':{'correct':1,'errors':0},'candidate':{'correct':2,'errors':1}}
    assert not result['task_success_measured'] and not result['adoption_authorized']
    assert result['cases'][0]['arms']['baseline']['missed']==['build']
    with pytest.raises(Refused,match='duplicate_evaluation_case'):
        compare_prerequisite_checks(cases+cases[:1],lambda x:[],learned)


def test_real_learn_ledger_dedup_grants_and_source_retraction():
    pytest.importorskip('omegalearn')  # separate, not yet published package
    from omegalearn import Ledger, Refused as LearnRefused, digest
    from omegaplanner.learning import from_learn_ledger
    ledger = Ledger()
    args = episode()
    def resolver(event):
        return {'current_subject': args['current_subject'], 'owner': 'planner',
                'scope': 'synthetic', 'permissions': args['permissions'],
                'visible_refs': ['finding:1'], 'references_valid': True}
    c = from_learn_ledger(ledger, resolver)
    assert c.export_episode(**args)['admission']['new_evidence'] is True
    assert c.export_episode(**args)['admission']['new_evidence'] is False
    alias = deepcopy(args); alias['event_id'] = 'episode:alias'
    with pytest.raises(LearnRefused, match='alias'): c.export_episode(**alias)
    p = package(); p.update(schema='omegalearn/package/1', owner='learn', scope='learn',
        source_events=['episode:1'], provenance_refs=[], evaluation_refs=[],
        runtime={'requires': ['metta'], 'entrypoint': 'declarative-only'}, rollback=None)
    p['digest'] = digest(p)
    assert c.receive_candidate(p)['attached'] is False
    ledger.invalidate('episode:1', lambda event: True)
    with pytest.raises(LearnRefused, match='stale'): c.candidate(p['id'], p['version'])


def test_learn_checkpoint_restore_preserves_source_staleness_and_independent_support():
    pytest.importorskip('omegalearn')  # separate, not yet published package
    from omegalearn import Ledger, Refused as LearnRefused, digest
    from omegaplanner.learning import from_learn_ledger
    ledger = Ledger(); args = episode()
    def resolver(event):
        return {'current_subject':event['subject'], 'owner':event['owner'],
                'scope':event['scope'], 'permissions':event['permissions'],
                'visible_refs':event['evidence_refs'], 'references_valid':True}
    c = from_learn_ledger(ledger, resolver)
    c.export_episode(**args)
    other = deepcopy(args); other['event_id']='episode:2';other['subject']['id']='plan:2'
    other['current_subject']=deepcopy(other['subject']);other['evidence_refs']=['finding:2']
    other['review_findings']=['finding:2'];c.export_episode(**other)
    def proposed(version,event,evidence):
        p=package(version,[evidence]);p.update(schema='omegalearn/package/1',owner='learn',scope='learn',
            source_events=[event],provenance_refs=[],evaluation_refs=[],
            runtime={'requires':['metta'],'entrypoint':'declarative-only'},rollback=None)
        p['digest']=digest(p);return p
    p1=proposed('1','episode:1','finding:1');p2=proposed('2','episode:2','finding:2')
    c.receive_candidate(p1);c.receive_candidate(p2)
    ledger.invalidate('episode:1',lambda event:True)
    restored=Ledger.restore(ledger.checkpoint()); receiver=from_learn_ledger(restored,resolver)
    with pytest.raises(LearnRefused,match='stale'):receiver.receive_candidate(p1)
    assert receiver.receive_candidate(p2)['stale'] is False


def test_bench_withdrawal_scorer_rejects_missing_planner_observation():
    pytest.importorskip('omegalearn')  # separate, not yet published package
    # Consume Bench's existing scorer, not a parallel Planner metric.
    from omegabench.correction import score_withdrawal
    oracle={'finding:1':[], 'episode:1':['finding:1'], 'skill:1':['episode:1'], 'independent':[]}
    complete={'finding:1':False,'episode:1':False,'skill:1':False,'independent':True}
    scored=score_withdrawal(oracle,'finding:1',complete,complete)
    assert scored['score']==1 and scored['capture_authentication']=='unverified'
    assert scored['capability_claim']=='unestablished'
    missing=dict(complete);del missing['skill:1']
    degraded=score_withdrawal(oracle,'finding:1',complete,missing)
    assert degraded['snapshots']['after_restart']['missing']==1
    assert degraded['score'] < 1


def test_actual_stored_plan_digest_and_noncanonical_bytes_survive_learn_admission():
    pytest.importorskip('omegalearn')  # separate, not yet published package
    import json
    from hive.core.collab import digest as hive_digest
    from omegalearn import Ledger
    from omegaplanner.learning import stored_plan_export, from_learn_ledger
    body=plan();body['goal']='Prepare café workshop'
    text=json.dumps(body,ensure_ascii=False,indent=2)+'\n'
    row={'artifact_id':'artifact:1','n':1,'digest':hive_digest(text),'body':text}
    bound=stored_plan_export(row,row)
    assert bound['export_bytes']==text.encode('utf-8')
    args=episode();args.update(bound)
    def resolver(event):
        return {'current_subject':bound['subject'],'owner':event['owner'],'scope':event['scope'],
                'permissions':event['permissions'],'visible_refs':['finding:1'],'references_valid':True}
    out=from_learn_ledger(Ledger(),resolver).export_episode(**args)
    assert out['admission']['new_evidence'] is True
    assert out['event']['subject']['digest']==row['digest'][7:]
    assert out['event']['subject']['revision']=='1'


@pytest.mark.parametrize('change,reason',[
    ('new-head','stale_plan_subject'),('body','source_digest_mismatch'),
    ('digest','invalid_stored_digest'),('bool-revision','invalid_stored_revision')])
def test_stored_revision_adapter_refuses_stale_corrupt_or_ambiguous_inputs(change,reason):
    from hive.core.collab import digest as hive_digest
    from omegaplanner.learning import stored_plan_export
    text=canonical(plan());row={'artifact_id':'artifact:1','n':1,'digest':hive_digest(text),'body':text}
    current=deepcopy(row)
    if change=='new-head':current['n']=2
    if change=='body':row['body']=text+' '
    if change=='digest':row['digest']='f'*64;current=deepcopy(row)
    if change=='bool-revision':row['n']=True;current=deepcopy(row)
    with pytest.raises(Refused,match=reason):stored_plan_export(row,current)
