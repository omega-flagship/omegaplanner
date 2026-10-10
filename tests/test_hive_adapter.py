"""Requires PYTHONPATH pointing to the retained platform source pin."""
from copy import deepcopy
import pytest

pytest.importorskip("hive.core.app")
import os  # noqa: E402
from pathlib import Path  # noqa: E402
if not (Path(os.environ.get("PETTA_PATH") or "/nonexistent") / "python" / "petta").is_dir():
    pytest.skip("needs a working PeTTa: set PETTA_PATH (see the README, Test)", allow_module_level=True)
from hive.tests.test_core_api import client  # noqa: E402,F401
from omegaplanner.hive_adapter import HivePlanner, HiveError  # noqa: E402


def plan():
    return {"goal": "Invented workshop", "constraints": {"synthetic": True}, "unknowns": [], "acceptance": ["recover if room unavailable"], "steps": [{"id": "prepare", "depends_on": [], "output": "room plan", "completion_check": "inspect invented plan", "owner_proposal": "unassigned", "capabilities_required": [], "resources": {}, "fallback": "ask again"}, {"id": "schedule", "depends_on": ["prepare"], "output": "schedule", "completion_check": "inspect invented schedule", "owner_proposal": "unassigned", "capabilities_required": [], "resources": {}, "fallback": "delay"}]}


def setup(client, mandate=None):
    swarms = [client.post("/api/swarms", json={"name": name}).json() for name in ["Requester", "Planner", "Review", "Foreign"]]
    agents = [client.post("/api/agents", json={"name": name, "kind": "module", "swarm_id": s["id"]}).json() for name, s in zip(["Asker", "Plan", "Critic", "Other"], swarms)]
    apis = [HivePlanner(client, a["token"]) for a in agents]
    if mandate:
        role = client.post("/api/roles", json={"name": "Invented mandate reviewer", "prompt": "Review only invented inputs", "mandate": mandate}).json()
        assert "id" in role
        assert client.patch(f"/api/agents/{agents[2]['id']}", json={"role_id": role["id"]}).status_code == 200
    for swarm, kind in [(swarms[1], "plan"), (swarms[2], "review")]:
        assert client.put(f"/api/swarms/{swarm['id']}/services", json={"kinds": [kind]}).status_code == 200
    goal = client.post(f"/api/swarms/{swarms[0]['id']}/goals", json={"title": "invented task", "assignee": agents[0]["name"]}).json()
    apis[0].claim(goal["id"])
    rq = apis[0].request_plan(goal["id"], swarms[1]["id"], "Plan workshop", ["return a plan"], {"synthetic": True}, [], 1)
    apis[1].claim(rq["receiving_goal"])
    return swarms, apis, rq


def test_adapter_real_api_revision_review_return(client):
    mandate = {"id": "feasibility", "version": "1"}
    swarms, (asker, planner, reviewer, foreign), root = setup(client, mandate)
    artifact = planner.create_plan("Workshop")
    first = planner.publish(artifact["id"], plan())
    review = planner.request_review(root["receiving_goal"], swarms[2]["id"], first, [mandate], ["synthetic:room"], .2)
    reviewer.claim(review["receiving_goal"])
    assert reviewer.revision(artifact["id"], 1)["digest"] == first["digest"]
    finding = reviewer.finding(review["id"], mandate, "prepare", "major", ["synthetic:room"], "Add room fallback")
    receipt = reviewer.complete_review(review["id"], "revise", "Room fallback needs review", [finding["id"]], ["prepare"])["receipt"]
    assert receipt["subject"]["digest"] == first["digest"]
    assert receipt["authority"] == "none"
    assert receipt["findings"][0]["id"] == finding["id"]
    second_plan = deepcopy(plan())
    second_plan["steps"][0]["fallback"] = "use invented alternate room"
    second = planner.publish(artifact["id"], second_plan, parent=1)
    assert second["changed_steps"] == ["prepare"]
    assert second["affected_steps"] == ["schedule"]
    planner.respond(finding["id"], 2, "addressed", "fallback added")
    assert planner.findings(artifact["id"])[0]["disposition"] is None
    delta = planner.request_review(root["receiving_goal"], swarms[2]["id"], second, [mandate], ["synthetic:room"], .2)
    reviewer.claim(delta["receiving_goal"])
    reviewer.revision(artifact["id"], 2)
    reviewer.disposition(finding["id"], delta["id"], 2, "still-open")
    delta_receipt = reviewer.complete_review(delta["id"], "revise", "Room still unconfirmed; prior objection stays open", [], ["prepare", "schedule"])["receipt"]
    assert delta_receipt["subject"]["digest"] == second["digest"]
    assert delta_receipt["empty"] is True  # no newly raised findings, not absence of dissent
    findings = planner.findings(artifact["id"])
    assert findings[0]["raised_on"]["digest"] == first["digest"]
    assert findings[0]["disposition"]["verdict"] == "still-open"
    # The output is returned as the bound goal proposal. Requester receives the
    # snapshot explicitly, without widening artifact ownership or access.
    output = {"plan": second, "findings": findings, "execution_authorized": False}
    submitted = planner.complete(root["receiving_goal"], "Plan revised; objection remains", output)
    # Historical candidate predates requester acceptance; R17 holds submission.
    if submitted["status"] == "submitted":
        assert asker.request(root["id"])["state"] != "completed"
        asker.review_result(root["receiving_goal"], "accept", "Accept plan as a proposal, retaining dissent")
    returned = asker.request(root["id"])
    assert returned["state"] == "completed"
    assert returned["result"]["proposal"]["execution_authorized"] is False
    with pytest.raises(HiveError) as denied:
        foreign.revision(artifact["id"], 2)
    assert denied.value.status == 403
    assert not any(call[0] == "start" for call in client.supervisor.calls)


def test_adapter_cancellation_revokes_reviewer_access(client):
    swarms, (asker, planner, reviewer, _), root = setup(client, {"id": "cost", "version": "1"})
    artifact = planner.create_plan("Workshop")
    revision = planner.publish(artifact["id"], plan())
    review = planner.request_review(root["receiving_goal"], swarms[2]["id"], revision, [{"id": "cost", "version": "1"}], [], .2)
    reviewer.claim(review["receiving_goal"])
    assert reviewer.revision(artifact["id"], 1)["digest"] == revision["digest"]
    asker.cancel(root["id"])
    assert planner.request(review["id"])["state"] == "cancelled"
    with pytest.raises(HiveError) as denied:
        reviewer.revision(artifact["id"], 1)
    assert denied.value.status == 403


def test_review_completion_refusals_preserve_held_request(client):
    mandate = {"id": "feasibility", "version": "1"}
    swarms, (_, planner, reviewer, foreign), root = setup(client, mandate)
    artifact = planner.create_plan("Invented completion boundaries")
    revision = planner.publish(artifact["id"], plan())
    review = planner.request_review(root["receiving_goal"], swarms[2]["id"], revision, [mandate], ["synthetic:room"], .2)
    reviewer.claim(review["receiving_goal"])
    finding = reviewer.finding(review["id"], mandate, "prepare", "major", ["synthetic:room"], "Retain objection")
    invalid_calls = [
        lambda: reviewer.complete(review["receiving_goal"], "done", {}),
        lambda: reviewer.complete_review(review["id"], "revise", "Omitted finding", [], []),
        lambda: reviewer.complete_review(review["id"], "revise", "Duplicate finding", [finding["id"], finding["id"]], []),
        lambda: reviewer.complete_review(review["id"], "revise", "", [finding["id"]], []),
        lambda: planner.complete_review(review["id"], "proceed", "Planner cannot review itself", [finding["id"]], []),
        lambda: foreign.complete_review(review["id"], "proceed", "Foreign caller", [finding["id"]], []),
    ]
    for invalid in invalid_calls:
        with pytest.raises(HiveError):
            invalid()
        assert planner.request(review["id"])["state"] == "working"
        assert planner.findings(artifact["id"])[0]["disposition"] is None
    done = reviewer.complete_review(review["id"], "hold", "Open objection blocks recommendation", [finding["id"]], ["prepare"])
    stored = planner.request(review["id"])
    assert stored["state"] == "completed"
    assert stored["result"]["review_receipt"] == done["receipt"]
    with pytest.raises(HiveError):
        reviewer.complete_review(review["id"], "proceed", "Cannot replace terminal receipt", [finding["id"]], [])
    assert planner.request(review["id"])["result"]["review_receipt"] == done["receipt"]


def test_review_completion_after_cancellation_is_refused(client):
    mandate = {"id": "feasibility", "version": "1"}
    swarms, (asker, planner, reviewer, _), root = setup(client, mandate)
    artifact = planner.create_plan("Invented cancellation")
    revision = planner.publish(artifact["id"], plan())
    review = planner.request_review(root["receiving_goal"], swarms[2]["id"], revision, [mandate], [], .2)
    reviewer.claim(review["receiving_goal"])
    asker.cancel(root["id"])
    with pytest.raises(HiveError):
        reviewer.complete_review(review["id"], "proceed", "Stale review must fail", [], [])
    assert planner.request(review["id"])["state"] == "cancelled"
