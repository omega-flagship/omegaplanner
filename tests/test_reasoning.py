from dataclasses import replace
import pytest
from omegaplanner.reasoning import Fact, ProjectionRefused, snapshot, review_scope


def facts():
    return [Fact('Step', (s,), 'plan', 'r2') for s in ('a', 'b', 'c', 'd')] + [
        Fact('DependsOn', ('b', 'a'), 'plan', 'r2'),
        Fact('DependsOn', ('c', 'b'), 'plan', 'r2'),
        Fact('ChangedStep', ('a',), 'delta', 'r2'),
        Fact('OpenFinding', ('objection', 'd'), 'finding', 'v1')]


def make(rows=None, authorize=lambda *args: True):
    return snapshot(principal='synthetic:planner', scope='synthetic:exhibit', artifact_digest='synthetic:digest', observed_at=10, expires_at=20, facts=facts() if rows is None else rows, authorize=authorize)


def run(snap, **changes):
    args = dict(now=11, artifact_digest='synthetic:digest', source_versions={'plan':'r2', 'delta':'r2', 'finding':'v1'}, authorize=lambda *args: True)
    args.update(changes)
    return review_scope(snap, **args)


def test_transitive_change_and_unchanged_dissent_with_provenance():
    snap = make()
    result = run(snap)
    assert result['steps'] == ['a', 'b', 'c', 'd']
    assert result['derivations']['c'][0]['predecessor'] == 'b'
    assert result['derivations']['d'][0]['finding'] == 'objection'
    assert result['snapshot_binding'] == snap.binding
    assert result['execution_authorized'] is False
    assert snap == make(list(reversed(facts())))


@pytest.mark.parametrize('changes', [dict(now=20), dict(now=9), dict(artifact_digest='changed'), dict(source_versions={'plan':'r3'}), dict(authorize=lambda *args: False)])
def test_stale_or_revoked_projection_refused(changes):
    with pytest.raises(ProjectionRefused):
        run(make(), **changes)


def test_tampered_projection_refused():
    with pytest.raises(ProjectionRefused, match='binding'):
        run(replace(make(), scope='other'))


def test_invalid_graphs_and_executable_predicates_refused():
    with pytest.raises(ProjectionRefused, match='cycle'):
        make(facts() + [Fact('DependsOn', ('a', 'c'), 'plan', 'r2')])
    with pytest.raises(ProjectionRefused, match='dangling'):
        make([Fact('DependsOn', ('absent', 'also-absent'), 'plan', 'r2')])
    with pytest.raises(ProjectionRefused):
        Fact('Execute', ('anything',), 'plan', 'r2')
    with pytest.raises(ProjectionRefused, match='authorized'):
        make(authorize=lambda *args: False)


def test_projection_is_immutable_and_fact_limit_is_enforced():
    rows = facts()
    snap = make(rows)
    rows.clear()
    assert run(snap)['steps'] == ['a', 'b', 'c', 'd']
    with pytest.raises(ProjectionRefused, match='oversized'):
        make([Fact('Step', (str(i),), 'plan', 'r2') for i in range(1001)])


def test_global_change_covers_whole_plan_and_conflicting_versions_refuse():
    rows = [f for f in facts() if f.predicate not in {'ChangedStep', 'OpenFinding'}]
    result = run(make(rows + [Fact('GlobalChange', ('budget',), 'delta', 'r2')]))
    assert result['steps'] == ['a', 'b', 'c', 'd']
    assert result['derivations']['d'][0]['changed_context'] == 'budget'
    with pytest.raises(ProjectionRefused, match='incoherent'):
        make(facts() + [Fact('Step', ('new-step',), 'plan', 'r3')])
