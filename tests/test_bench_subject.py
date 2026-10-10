import json
from pathlib import Path
import time
import pytest
pytest.importorskip('omegalearn')  # OmegaLearn is a separate, not yet published package
from omegalearn import Ledger
from omegaplanner.learning import from_learn_ledger
from omegaplanner.bench_subject import PlannerExecutor
from omegaplanner.protocol import Refused

ROOT=Path(__file__).resolve().parents[2]


def setup(mode, plan_sink=None, capture_binding=None):
    source=json.loads((ROOT/'coordination/omegalearn/PREREQUISITE_SOURCE_DEVELOPMENT.json').read_text())
    package=json.loads((ROOT/'coordination/omegalearn/PREREQUISITE_PACKAGE_DEVELOPMENT.json').read_text())
    ledger=Ledger();e=source['event']
    def resolver(event):
        return {'current_subject':e['subject'],'owner':e['owner'],'scope':e['scope'],
                'permissions':e['permissions'],'visible_refs':e['evidence_refs'], 'references_valid':True}
    ledger.admit(e,resolver);consumer=from_learn_ledger(ledger,resolver);consumer.receive_candidate(package)
    executor=PlannerExecutor(consumer,package,source['episodes'],mode,'development-python',
                             {'baseline':'unchanged-exact-episode','provider':'none'},
                             plan_sink=plan_sink,capture_binding=capture_binding)
    return executor,ledger,e


def request(executor, available):
    return {'task_id':'public-development','seed':1,'subject_pin':executor.subject_pin,
        'environment_pin':executor.environment_pin,'remaining_budget':{'cost':0,'tokens':0,'seconds':1,'attempts':1},
        'deadline_monotonic':time.monotonic()+1,
        'input':{'case':{'actions':['publish'],'available':available},'prerequisite_ids':['review','approval']}}


@pytest.mark.parametrize('mode,expected',[('FULL',['review']),('SHAM',[]),('SEVERED',[]),('typed-memory',[])])
def test_shared_exact_response_separated_from_actual_local_plan_capture(mode,expected):
    ex,_,_=setup(mode);r=ex.execute(request(ex,['approval']))
    assert set(r)=={'status','response','usage','floors'} and r['response']==expected
    assert r['status']=='ok' and r['usage']['attempts']==1
    c=ex.captures()[0]
    assert c['local_plan']['body']['constraints']['execution_authorized'] is False
    assert c['plan_artifact'] is None and c['capture_receipt'] is None
    assert not c['capability_acceptance_ready']
    if mode=='FULL':assert c['local_plan']['body']['steps'][-1]['depends_on']==['prereq-review']


def test_withdrawal_remains_metered_failure_and_has_no_plan():
    ex,ledger,e=setup('FULL');ledger.invalidate(e['id'],lambda event:True)
    r=ex.execute(request(ex,['approval']))
    assert r['status']=='failed' and r['usage']['attempts']==1
    assert ex.captures()[0]['local_plan'] is None


def test_binding_refusal_never_produces_capture():
    ex,_,_=setup('FULL');q=request(ex,[]);q['subject_pin']='wrong'
    with pytest.raises(Refused,match='execution_binding_mismatch'):ex.execute(q)
    assert ex.captures()==[]


def test_planner_local_finding_withdrawal_is_an_accounted_failure():
    ex,_,_=setup('FULL')
    ex.consumer.retract_source(ex.package['evidence_refs'][0])
    result=ex.execute(request(ex,['approval']))
    assert result['status']=='failed' and result['usage']['attempts']==1
    assert ex.captures()[0]['local_plan'] is None


def test_capture_failure_keeps_trial_and_actual_usage():
    def failed_capture(plan,request):raise RuntimeError('synthetic denied sink')
    ex,_,_=setup('FULL',failed_capture,{'kind':'synthetic-failure-sink','version':'1'})
    result=ex.execute(request(ex,['approval']))
    assert result['status']=='failed' and result['response'] is None
    assert result['usage']['attempts']==1
    assert ex.captures()[0]['capture_error']=='RuntimeError'
    assert ex.captures()[0]['plan_artifact'] is None
