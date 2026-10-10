from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from omegaplanner.matching import MatchingHarness
from omegaplanner.protocol import Refused


def profile(entity="m1", **changes):
    return {"id": entity, "kind": "mind", "swarm_id": "builders", "offers": ["plan"], "verified": {"plan": ["synthetic:receipt"]}, "available": True, "capacity": 1, "cost_cents": 10, "eligible_task_ids": ["t1", "t2", "help", "svc"], **changes}


def task(task_id="t1", **changes):
    return {"id": task_id, "kind": "assignment", "requester": "requesting-mind", "requester_swarm": "requesting-swarm", "required": ["plan"], "acceptance": ["return invented plan"], "max_cost_cents": 20, **changes}


def setup():
    h = MatchingHarness()
    h.register(profile())
    h.register(profile("m2"))
    h.post(task())
    return h


def test_evidence_precedes_advertising_and_matching_is_advisory():
    h = MatchingHarness()
    h.register(profile("advertised", verified={}, cost_cents=1))
    h.register(profile("verified"))
    h.post(task())
    candidates = h.match("t1")["candidates"]
    assert [c["entity_id"] for c in candidates] == ["verified", "advertised"]
    assert candidates[1]["advertised_only"] == ["plan"]
    assert candidates[1]["uncertainties"]
    assert h.board("grand")["tasks"][0]["assignee"] is None


@pytest.mark.parametrize("changes,reason", [({"available": False}, "unavailable"), ({"capacity": 0}, "at_capacity"), ({"eligible_task_ids": []}, "not_eligible"), ({"cost_cents": 21}, "over_budget"), ({"offers": [], "verified": {}}, "missing_capabilities")])
def test_ineligible_candidates_excluded(changes, reason):
    h = MatchingHarness()
    h.register(profile(**changes))
    h.post(task())
    result = h.match("t1")
    assert result["candidates"] == []
    assert reason in result["excluded"][0]["reasons"]


def test_concurrent_acceptance_has_one_winner():
    h = setup()
    barrier = Barrier(2)

    def accept(entity):
        barrier.wait()
        try:
            h.accept("t1", entity, entity, 1)
            return "accepted"
        except Refused:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, ["m1", "m2"]))
    assert sorted(results) == ["accepted", "refused"]


def test_accept_rechecks_availability_and_requires_recipient():
    h = setup()
    h.match("t1")
    with pytest.raises(Refused, match="recipient_must_accept"):
        h.accept("t1", "m1", "requesting-mind", 1)
    h.update_availability("m1", False)
    with pytest.raises(Refused, match="no_longer_eligible"):
        h.accept("t1", "m1", "m1", 1)


def test_capacity_releases_on_cancel_and_no_execution_is_authorized():
    h = setup()
    h.accept("t1", "m1", "m1", 1)
    h.post(task("t2"))
    assert "m1" not in [c["entity_id"] for c in h.match("t2")["candidates"]]
    h.cancel("t1", "requesting-mind")
    assigned = h.accept("t2", "m1", "m1", 1)
    assert assigned["execution_authorized"] is False


def test_assistance_preserves_owner_and_returns_evidence_on_all_boards():
    h = setup()
    h.accept("t1", "m1", "m1", 1)
    h.post(task("help", kind="assistance", requester="m1", parent_id="t1"))
    h.accept("help", "m2", "m2", 1)
    with pytest.raises(Refused, match="active_assistance"):
        h.complete("t1", "m1", ["synthetic:premature"])
    h.complete("help", "m2", ["synthetic:contribution"])
    rows = []
    for kind, entity in [("mind", "m1"), ("mind", "m2"), ("swarm", "builders"), ("grand", None)]:
        rows.append(next(t for t in h.board(kind, entity)["tasks"] if t["id"] == "help"))
    assert all(row == rows[0] for row in rows)
    assert rows[0]["outcome_owner"] == "m1"
    assert rows[0]["completion_verified"] is False
    assert rows[0]["evidence_refs"] == ["synthetic:contribution"]
    h.complete("t1", "m1", ["synthetic:plan"])


def test_cancellation_cascades_and_late_completion_refused():
    h = setup()
    h.accept("t1", "m1", "m1", 1)
    h.post(task("help", kind="assistance", requester="m1", parent_id="t1"))
    h.accept("help", "m2", "m2", 1)
    h.cancel("t1", "requesting-mind")
    assert all(t["state"] == "cancelled" for t in h.board("grand")["tasks"])
    with pytest.raises(Refused):
        h.complete("help", "m2", ["synthetic:late"])


def test_service_matches_swarm_and_empty_verification_is_refused():
    h = setup()
    h.register(profile("planner-swarm", kind="swarm", swarm_id="planner-swarm"))
    h.post(task("svc", kind="service"))
    assert [c["entity_id"] for c in h.match("svc")["candidates"]] == ["planner-swarm"]
    with pytest.raises(Refused, match="verification_requires_evidence"):
        h.register(profile("false-verification", verified={"plan": []}))


def test_board_copies_do_not_mutate_canonical_tasks():
    h = setup()
    h.board("grand")["tasks"][0]["state"] = "done"
    assert h.board("grand")["tasks"][0]["state"] == "open"
