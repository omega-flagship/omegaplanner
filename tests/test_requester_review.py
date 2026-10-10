"""R17 requester acceptance qualification, isolated source required."""
import os
import pytest
pytestmark = pytest.mark.skipif(os.environ.get('OMEGAPLANNER_R17') != '1', reason='requires R17 native source')
pytest.importorskip('hive.core.app')
from hive.tests.test_core_api import client  # noqa: E402,F401
from omegaplanner.tests.test_hive_adapter import setup, plan  # noqa: E402
from omegaplanner.hive_adapter import HiveError  # noqa: E402


def test_requester_returns_then_accepts_plan_proposal(client):
    _, (asker, planner, _, foreign), root = setup(client)
    artifact = planner.create_plan('Invented R17 plan')
    revision = planner.publish(artifact['id'], plan())
    output = {'plan': revision, 'findings': [], 'execution_authorized': False}
    goal_id = root['receiving_goal']
    assert planner.complete(goal_id, 'Plan proposal', output)['status'] == 'submitted'
    assert asker.request(root['id'])['state'] != 'completed'
    for actor in (planner, foreign):
        with pytest.raises(HiveError) as exc:
            actor.review_result(goal_id, 'accept')
        assert exc.value.status == 403
    with pytest.raises(HiveError):
        asker.review_result(goal_id, 'return', '')
    returned = asker.review_result(goal_id, 'return', 'Please retain explicit uncertainty')
    assert returned['status'] == 'claimed'
    assert returned['claimed_by']
    assert returned['returns'] == 1
    output['uncertainty'] = ['Invented room remains unconfirmed']
    assert planner.complete(goal_id, 'Revised plan proposal', output)['status'] == 'submitted'
    assert asker.review_result(goal_id, 'accept', 'Accept proposal only')['status'] == 'done'
    result = asker.request(root['id'])
    assert result['state'] == 'completed'
    assert result['result']['proposal']['execution_authorized'] is False
    assert result['result']['proposal']['uncertainty'] == output['uncertainty']
    with pytest.raises(HiveError):
        asker.review_result(goal_id, 'return', 'Terminal result cannot reopen')
    assert not any(call[0] == 'start' for call in client.supervisor.calls)


def test_third_requester_return_fails_goal(client):
    _, (asker, planner, _, _), root = setup(client)
    goal_id = root['receiving_goal']
    for attempt in range(3):
        assert planner.complete(goal_id, f'Invented proposal {attempt}', {'execution_authorized': False})['status'] == 'submitted'
        out = asker.review_result(goal_id, 'return', 'Invented acceptance criterion remains unmet')
        assert out['status'] == ('failed' if attempt == 2 else 'claimed')
    assert out['returns'] == 3
    with pytest.raises(HiveError):
        planner.complete(goal_id, 'Cannot bypass terminal failure', {'execution_authorized': False})


def test_structured_review_waits_for_designated_quality_review(client):
    from omegaplanner.hive_adapter import HivePlanner
    from omegaplanner.review_bundle import bundle
    mandate = {'id': 'feasibility', 'version': '1'}
    swarms, (_, planner, reviewer, foreign), root = setup(client, mandate)
    qc = client.post('/api/agents', json={'name': 'Invented quality reviewer', 'kind': 'module', 'swarm_id': swarms[2]['id']}).json()
    quality = HivePlanner(client, qc['token'])
    artifact = planner.create_plan('Invented review quality gate')
    revision = planner.publish(artifact['id'], plan())
    request = planner.request_review(root['receiving_goal'], swarms[2]['id'], revision, [mandate], [], .2,
                                     review_by='agent:' + qc['id'])
    reviewer.claim(request['receiving_goal'])
    completion = reviewer.complete_review(request['id'], 'hold', 'Invented evidence is incomplete', [], ['prepare'])
    assert completion['goal']['status'] == 'submitted'
    assert planner.request(request['id'])['state'] == 'in-review'
    for actor in (reviewer, planner, foreign):
        with pytest.raises(HiveError) as exc:
            actor.review_result(request['receiving_goal'], 'accept')
        assert exc.value.status == 403
    receipt = planner.request(request['id'])['result']['review_receipt']
    assert receipt['authority'] == 'none'
    assert receipt['recommendation'] == 'hold'
    pending = bundle(quality.review_receipts(revision['digest']), receipt['subject'], [mandate])
    assert pending['status'] == 'hold' and not pending['coverage_complete']
    assert quality.review_result(request['receiving_goal'], 'accept', 'Accept receipt fidelity; no execution grant')['status'] == 'done'
    completed = planner.request(request['id'])
    assert completed['state'] == 'completed'
    assert completed['result']['review_receipt'] == receipt
    projected = quality.review_receipts(revision['digest'])
    result = bundle(projected, receipt['subject'], [mandate])
    assert result['status'] == 'hold' and result['coverage_complete']
    assert result['requests'][0]['qc'][-1]['notes'] == 'Accept receipt fidelity; no execution grant'
    assert planner.review_receipts(revision['digest'])['count'] == 0
    assert foreign.review_receipts(revision['digest'])['count'] == 0
    assert not any(call[0] == 'start' for call in client.supervisor.calls)
