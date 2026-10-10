from copy import deepcopy
import pytest
from omegaplanner.protocol import PlanningHarness, Refused


def plan():
    def step(name, dependencies):
        return {"id": name, "depends_on": dependencies, "output": "invented output", "completion_check": "inspect synthetic output", "owner_proposal": "unassigned", "capabilities_required": [], "resources": {"minutes": 1}, "fallback": "return for replanning"}
    return {"goal": "Prepare an invented workshop", "acceptance": ["schedule includes a recovery route"], "constraints": {"classification": "synthetic"}, "unknowns": ["room availability"], "steps": [step("prepare", []), step("schedule", ["prepare"])]}


MANDATES = [{"id": "feasibility", "version": "1"}, {"id": "cost", "version": "1"}]


def reviewed():
    h = PlanningHarness()
    h.publish("planner", plan(), 0)
    request = h.request_review("planner", 1, MANDATES)
    findings = [{"id": "f1", "step": "prepare", "mandate": MANDATES[0], "severity": "major", "evidence_refs": ["synthetic:room"], "recommendation": "include a second room"}, {"id": "f2", "step": "schedule", "mandate": MANDATES[1], "severity": "minor", "evidence_refs": [], "recommendation": "confirm costs"}]
    h.submit_review("reviewer", {**request, "findings": findings})
    return h


def test_complete_application_loop_preserves_dissent_and_independent_resolution():
    h = reviewed()
    body = plan()
    body["steps"][0]["fallback"] = "use invented second room"
    r2 = h.publish("planner", body, 1)
    assert r2["review_steps"] == ["prepare", "schedule"]
    h.respond("planner", "f1", 2, "addressed", "added fallback")
    h.respond("planner", "f2", 2, "disputed", "cost remains unknown")
    returned = h.return_plan("requester")
    assert returned["findings"][0]["disposition"] is None
    delta = h.request_review("planner", 2, MANDATES)
    h.disposition("reviewer", "f1", delta["request_id"], delta["subject"], "confirmed-resolved")
    h.disposition("reviewer", "f2", delta["request_id"], delta["subject"], "still-open")
    returned = h.return_plan("requester")
    assert returned["execution_authorized"] is False
    assert returned["findings"][1]["disposition"]["verdict"] == "still-open"
    assert returned["findings"][1]["raised_on"]["revision"] == 1
    assert returned["findings"][1]["applicability"][-1] == {"revision": 2, "state": "unverified"}


def test_revision_copy_cannot_change_snapshot_or_digest():
    h = PlanningHarness()
    original = h.publish("planner", plan(), 0)
    digest = original["digest"]
    original["body"]["goal"] = "tampered"
    assert h.revision(1, "reviewer")["digest"] == digest
    assert h.revision(1, "reviewer")["body"]["goal"] != "tampered"


@pytest.mark.parametrize("failure", ["foreign", "digest", "stale", "cancel", "role", "cycle", "duplicate", "reserved"])
def test_refusals(failure):
    h = PlanningHarness()
    h.publish("planner", plan(), 0)
    request = h.request_review("planner", 1, MANDATES)
    with pytest.raises(Refused):
        if failure == "foreign":
            h.revision(1, "outsider")
        elif failure == "digest":
            request["subject"]["digest"] = "wrong"
            h.submit_review("reviewer", {**request, "findings": []})
        elif failure == "stale":
            h.publish("planner", plan(), 1)
            h.submit_review("reviewer", {**request, "findings": []})
        elif failure == "cancel":
            h.cancel("requester")
            h.submit_review("reviewer", {**request, "findings": []})
        elif failure == "role":
            h.submit_review("planner", {**request, "findings": []})
        elif failure == "cycle":
            body = plan()
            body["steps"][0]["depends_on"] = ["schedule"]
            h.publish("planner", body, 1)
        elif failure == "duplicate":
            body = plan()
            body["steps"].append(deepcopy(body["steps"][0]))
            h.publish("planner", body, 1)
        else:
            h.submit_review("reviewer", {**request, "findings": [{"id": "f1", "mandate": MANDATES[0], "step": "prepare", "disposition": "resolved"}]})


def test_planner_cannot_close_and_reviewer_cannot_write_planner_response():
    h = reviewed()
    with pytest.raises(Refused, match="planner_only"):
        h.respond("reviewer", "f1", 1, "addressed", "no")
    request = h.request_review("planner", 1, MANDATES)
    with pytest.raises(Refused, match="reviewer_only"):
        h.disposition("planner", "f1", request["request_id"], request["subject"], "confirmed-resolved")


def test_global_constraint_change_requires_all_steps_to_be_reviewed():
    h = reviewed()
    body = plan()
    body["constraints"]["deadline"] = "invented tomorrow"
    revision = h.publish("planner", body, 1)
    assert revision["changed_steps"] == []
    assert revision["review_steps"] == ["prepare", "schedule"]
