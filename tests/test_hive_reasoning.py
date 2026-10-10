"""Disposable ASGI reads; native platform must be on PYTHONPATH."""
import pytest
pytest.importorskip('hive.core.app')
import os  # noqa: E402
from pathlib import Path  # noqa: E402
if not (Path(os.environ.get("PETTA_PATH") or "/nonexistent") / "python" / "petta").is_dir():
    pytest.skip("needs a working PeTTa: set PETTA_PATH (see the README, Test)", allow_module_level=True)
from hive.tests.test_core_api import client  # noqa: E402,F401
from omegaplanner.tests.test_hive_adapter import setup, plan  # noqa: E402
from omegaplanner.hive_reasoning import HiveReasoning  # noqa: E402
from omegaplanner.hive_adapter import HiveError  # noqa: E402
from omegaplanner.reasoning import ProjectionRefused  # noqa: E402


def test_authenticated_projection_and_revocation(client):
    mandate = {'id':'feasibility', 'version':'1'}
    swarms, (_, planner, reviewer, foreign), root = setup(client, mandate)
    artifact = planner.create_plan('Synthetic projection')
    first = planner.publish(artifact['id'], plan())
    req = planner.request_review(root['receiving_goal'], swarms[2]['id'], first, [mandate], ['synthetic:receipt'], .2)
    reviewer.claim(req['receiving_goal'])
    reader = HiveReasoning(reviewer)
    snap = reader.project(artifact['id'], 1, now=10)
    assert reader.derive(snap, artifact['id'], 1, now=11)['steps'] == ['prepare', 'schedule']
    with pytest.raises(HiveError):
        HiveReasoning(foreign).project(artifact['id'], 1, now=10)
    with pytest.raises(ProjectionRefused):
        HiveReasoning(reviewer).derive(snap, artifact['id'], 1, now=11)
    planner.cancel(req['id'])
    with pytest.raises(HiveError):
        reader.derive(snap, artifact['id'], 1, now=12)


def test_new_finding_invalidates_snapshot_without_closing_dissent(client):
    mandate = {'id':'feasibility', 'version':'1'}
    swarms, (_, planner, reviewer, _), root = setup(client, mandate)
    artifact = planner.create_plan('Synthetic finding projection')
    first = planner.publish(artifact['id'], plan())
    req = planner.request_review(root['receiving_goal'], swarms[2]['id'], first, [mandate], ['synthetic:receipt'], .2)
    reviewer.claim(req['receiving_goal'])
    reader = HiveReasoning(planner)
    snap = reader.project(artifact['id'], 1, now=10)
    reviewer.finding(req['id'], mandate, 'prepare', 'major', ['synthetic:receipt'], 'Retain objection')
    with pytest.raises(ProjectionRefused, match='source changed'):
        reader.derive(snap, artifact['id'], 1, now=11)
    fresh = reader.project(artifact['id'], 1, now=11)
    result = reader.derive(fresh, artifact['id'], 1, now=12)
    assert any(r['rule'] == 'open-objection-v1' for r in result['derivations']['prepare'])
    assert not result['execution_authorized']


def test_reviewer_without_parent_gets_conservative_whole_plan(client):
    from copy import deepcopy
    mandate = {'id':'feasibility', 'version':'1'}
    swarms, (_, planner, reviewer, _), root = setup(client, mandate)
    artifact = planner.create_plan('Synthetic limited delta')
    initial = plan()
    independent = deepcopy(initial['steps'][0])
    independent['id'] = 'independent'
    initial['steps'].append(independent)
    planner.publish(artifact['id'], initial)
    changed = deepcopy(initial)
    changed['steps'][0]['fallback'] = 'another invented fallback'
    second = planner.publish(artifact['id'], changed, parent=1)
    owner = HiveReasoning(planner)
    owner_snap = owner.project(artifact['id'], 2, now=10)
    assert owner.derive(owner_snap, artifact['id'], 2, now=11)['steps'] == ['prepare', 'schedule']
    req = planner.request_review(root['receiving_goal'], swarms[2]['id'], second, [mandate], [], .2)
    reviewer.claim(req['receiving_goal'])
    reader = HiveReasoning(reviewer)
    scoped = reader.project(artifact['id'], 2, now=10)
    assert reader.derive(scoped, artifact['id'], 2, now=11)['steps'] == ['independent', 'prepare', 'schedule']


def test_corrupted_revision_body_is_refused_before_projection(client):
    _, (_, planner, _, _), _ = setup(client)
    artifact = planner.create_plan('Synthetic digest check')
    planner.publish(artifact['id'], plan())
    class CorruptRead:
        def revision(self, artifact_id, n):
            row = planner.revision(artifact_id, n)
            row['body'] += ' '
            return row
    with pytest.raises(ProjectionRefused, match='digest mismatch'):
        HiveReasoning(CorruptRead()).project(artifact['id'], 1, now=10)
