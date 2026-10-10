"""Stored-plan checker loaded through native R17 plugin admission."""
import json
import os
import shutil
from pathlib import Path
import pytest
pytestmark = pytest.mark.skipif(os.environ.get('OMEGAPLANNER_R17') != '1', reason='requires current artifact custody context')
pytest.importorskip('hive.core.app')
from hive.tests.test_core_api import client  # noqa: E402,F401
from omegaplanner.tests.test_hive_adapter import plan  # noqa: E402
from omegaplanner.hive_adapter import HivePlanner, HiveError  # noqa: E402


def test_native_host_checks_stored_plan_then_requester_accepts(client, monkeypatch, tmp_path):
    shutil.copytree(Path(__file__).resolve().parents[1] / 'program', tmp_path / 'omegaplanner')
    monkeypatch.setenv('HIVE_PLUGIN_DIRS', str(tmp_path))
    client.app.state.hive.programs.reload()
    swarms = [client.post('/api/swarms', json={'name': n}).json() for n in ['Invented requester', 'Invented planner', 'Invented foreign']]
    agents = [client.post('/api/agents', json={'name': n, 'kind': 'module', 'swarm_id': s['id']}).json() for n,s in zip(['Asker','Maker','Foreign'],swarms)]
    asker, maker, foreign = [HivePlanner(client, a['token']) for a in agents]
    client.put(f"/api/swarms/{swarms[1]['id']}/services", json={'kinds':['plan']})
    own = client.post(f"/api/swarms/{swarms[0]['id']}/goals",json={'title':'invented plan request','assignee':agents[0]['id']}).json()
    asker.claim(own['id'])
    req = asker.request_plan(own['id'],swarms[1]['id'],'Invented custody check',['return stored plan'],{'validate':'program:omegaplanner'},[],1)
    maker.claim(req['receiving_goal'])
    artifact = maker.create_plan('Invented stored plan')
    revision = maker.publish(artifact['id'],plan())
    foreign_artifact = foreign.create_plan('Invented foreign plan')
    foreign_revision = foreign.publish(foreign_artifact['id'],plan())
    malformed_artifact = maker.create_plan('Invented malformed stored plan')
    malformed_revision = maker._call('POST', f"/api/agent/artifacts/{malformed_artifact['id']}/revisions", {'body': '{"goal":42}', 'parent': None})
    variants = [
        {'plan':revision,'execution_authorized':True},
        {'plan':{**revision,'digest':'sha256:'+'0'*64},'execution_authorized':False},
        {'plan':{**revision,'body':maker.revision(artifact['id'],1)['body']+' '},'execution_authorized':False},
        {'plan':foreign_revision,'execution_authorized':False},
        {'plan':malformed_revision,'execution_authorized':False},
    ]
    for proposal in variants:
        with pytest.raises(HiveError) as exc:
            maker.complete(req['receiving_goal'],'Invented proposal',proposal)
        assert exc.value.status == 422
        assert client.get(f"/api/goals/{req['receiving_goal']}").json()['status'] == 'claimed'
    assert maker.complete(req['receiving_goal'],'Stored plan proposal',{'plan':revision,'execution_authorized':False})['status'] == 'submitted'
    assert asker.review_result(req['receiving_goal'],'accept','Accept structure and custody only')['status'] == 'done'
    assert asker.request(req['id'])['state'] == 'completed'
    attempts = client.get(f"/api/goals/{req['receiving_goal']}/attempts").json()
    assert [a['ok'] for a in attempts] == [False]*5+[True]
    assert [r['action'] for r in client.get(f"/api/goals/{req['receiving_goal']}/reviews").json()] == ['submit', 'accept']
    assert not any(call[0] == 'start' for call in client.supervisor.calls)
