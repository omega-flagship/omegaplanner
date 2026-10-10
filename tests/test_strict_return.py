"""Final-return completeness through adopted native findings context."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import pytest
pytestmark = pytest.mark.skipif(os.environ.get('OMEGAPLANNER_R17') != '1', reason='requires adopted findings context')
pytest.importorskip('hive.core.app')
from hive.tests.test_core_api import client  # noqa: E402,F401
from omegaplanner.tests.test_hive_adapter import setup, plan  # noqa: E402
from omegaplanner.hive_adapter import HiveError  # noqa: E402


def test_strict_return_rejects_omission_and_stale_plan_but_retains_dissent(client,monkeypatch,tmp_path):
    shutil.copytree(Path(__file__).resolve().parents[1]/'program',tmp_path/'omegaplanner')
    monkeypatch.setenv('HIVE_PLUGIN_DIRS',str(tmp_path));hive=client.app.state.hive;hive.programs.reload()
    mandate={'id':'feasibility','version':'1'}
    swarms,(asker,planner,reviewer,_),root=setup(client,mandate)
    policy={'validate':'program:omegaplanner','require_review_complete':True,'required_review_mandates':[mandate]}
    hive.db.update('requests',root['id'],{'constraints':json.dumps(policy)})
    artifact=planner.create_plan('Invented strict return');first=planner.publish(artifact['id'],plan())
    req=planner.request_review(root['receiving_goal'],swarms[2]['id'],first,[mandate],['synthetic:receipt'],.2)
    reviewer.claim(req['receiving_goal'])
    finding=reviewer.finding(req['id'],mandate,'prepare','major',['synthetic:receipt'],'Keep unresolved objection')
    reviewer.complete_review(req['id'],'hold','Room unconfirmed',[finding['id']],['prepare'])
    def output(revision):
        context=planner.planning_review_context(root['id'],artifact['id'],revision['n'])
        return {'plan':revision,'findings':context['findings'],'reviews':context['reviews'],'execution_authorized':False}
    good=output(first)
    bad=[]
    omitted=deepcopy(good);omitted['findings']=[];bad.append(omitted)
    closed=deepcopy(good);closed['findings'][0]['disposition']={'verdict':'confirmed-resolved','revision':1};bad.append(closed)
    erased=deepcopy(good);erased['reviews']=[];bad.append(erased)
    changed=deepcopy(good);changed['reviews'][0]['receipt']['recommendation']='proceed';bad.append(changed)
    duplicate=deepcopy(good);duplicate['findings']*=2;bad.append(duplicate)
    for proposal in bad:
        with pytest.raises(HiveError) as exc:planner.complete(root['receiving_goal'],'Invented return',proposal)
        assert exc.value.status==422
    second_plan=deepcopy(plan());second_plan['steps'][0]['fallback']='invented alternate room'
    second=planner.publish(artifact['id'],second_plan,parent=1)
    planner.respond(finding['id'],2,'addressed','Planner claim only')
    with pytest.raises(HiveError):planner.complete(root['receiving_goal'],'Stale plan',output(first))
    with pytest.raises(HiveError):planner.complete(root['receiving_goal'],'Missing latest mandate review',output(second))
    delta=planner.request_review(root['receiving_goal'],swarms[2]['id'],second,[mandate],[],.2)
    reviewer.claim(delta['receiving_goal'])
    with pytest.raises(HiveError):planner.complete(root['receiving_goal'],'Review unfinished',output(second))
    reviewer.disposition(finding['id'],delta['id'],2,'still-open')
    reviewer.complete_review(delta['id'],'hold','Objection remains; return for requester judgment',[],['prepare','schedule'])
    final=output(second)
    policy['required_review_mandates']=[{'id':'feasibility','version':'2'}]
    hive.db.update('requests',root['id'],{'constraints':json.dumps(policy)})
    with pytest.raises(HiveError):planner.complete(root['receiving_goal'],'Wrong mandate version',final)
    policy['required_review_mandates']=[mandate]
    hive.db.update('requests',root['id'],{'constraints':json.dumps(policy)})
    import importlib.util
    bridge_path = Path(__import__('hive.core.app', fromlist=['__file__']).__file__).resolve().parents[2]/'modules/hive/src/hive_commons.py'
    spec = importlib.util.spec_from_file_location('planner_return_bridge', bridge_path)
    bridge = importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    def native_call(method, path, payload=None):
        response = client.request(method, path, json=payload, headers=planner._headers)
        return (None, str(response.status_code)) if response.status_code >= 400 else (response.json(), None)
    monkeypatch.setattr(bridge, '_call', native_call)
    assert bridge.plan_return(root['id'], artifact['id'], 999) == '409'
    assert hive.goals.get(root['receiving_goal'])['status']=='claimed'
    assert bridge.plan_return(root['id'], artifact['id'], 2).startswith('HIVE-GOAL-PROPOSED')
    assert hive.goals.get(root['receiving_goal'])['status']=='submitted' 
    assert asker.review_result(root['receiving_goal'],'accept','Receive conditional plan; no execution')['status']=='done'
    returned=asker.request(root['id'])['result']['proposal']
    assert returned['findings'][0]['disposition']['verdict']=='still-open'
    assert returned['reviews'][0]['receipt']['recommendation']=='hold'
    assert returned['execution_authorized'] is False
    assert not any(call[0]=='start' for call in client.supervisor.calls)
