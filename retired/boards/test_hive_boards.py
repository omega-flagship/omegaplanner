import os
import pytest
pytestmark = pytest.mark.skipif(os.environ.get("OMEGAPLANNER_BOARD_CANDIDATE") != "1", reason="requires isolated app with candidate routes installed")
pytest.importorskip("hive.core.app")
from hive.tests.test_core_api import client, agent_headers  # noqa: E402,F401


def test_canonical_boards_follow_claim_and_completion(client):
    swarm = client.post("/api/swarms", json={"name": "Invented builders"}).json()
    mind = client.post("/api/agents", json={"name": "Invented builder", "kind": "module", "swarm_id": swarm["id"]}).json()
    goal = client.post(f"/api/swarms/{swarm['id']}/goals", json={"title": "Invented work", "assignee": mind["id"]}).json()
    paths = [f"/api/boards/mind?entity_id={mind['id']}", f"/api/boards/swarm?entity_id={swarm['id']}", "/api/boards/grand"]
    for path in paths:
        assert client.get(path).json()["goals"][0]["id"] == goal["id"]
    assert client.post(f"/api/agent/goals/{goal['id']}/claim", headers=agent_headers(mind)).status_code == 200
    for path in paths:
        assert client.get(path).json()["goals"][0]["status"] == "claimed"
    assert client.post(f"/api/agent/goals/{goal['id']}/result", headers=agent_headers(mind), json={"status": "done", "result": "synthetic work done"}).status_code == 200
    for path in paths:
        assert client.get(path).json()["goals"][0]["status"] == "done"


def test_member_board_scope_and_admin_discovery(client):
    swarm = client.post("/api/swarms", json={"name": "Invented A"}).json()
    minds = [client.post("/api/agents", json={"name": n, "kind": "module", "swarm_id": swarm["id"]}).json() for n in ["One", "Two"]]
    goals = [client.post(f"/api/swarms/{swarm['id']}/goals", json={"title": n, "assignee": m["id"]}).json() for n, m in zip(["A", "B"], minds)]
    own = client.get("/api/agent/board", headers=agent_headers(minds[0]))
    assert own.status_code == 200
    assert [g["id"] for g in own.json()["goals"]] == [goals[0]["id"]]
    for path in ["/api/boards/grand", "/api/match?need=plan"]:
        assert client.get(path, headers=agent_headers(minds[0])).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_service_discovery_labels_unknowns_and_has_no_assignment_effect(client):
    swarm = client.post("/api/swarms", json={"name": "Invented Planner"}).json()
    client.put(f"/api/swarms/{swarm['id']}/services", json={"kinds": ["plan"]})
    match = client.get("/api/match?need=plan").json()
    assert match["advisory_only"] is True
    candidate = match["candidates"][0]
    assert candidate["entity_id"] == swarm["id"]
    assert candidate["verified_capabilities"] == []
    assert candidate["capacity"] == "unknown" and candidate["eligibility"] == "unverified"
    assert client.get(f"/api/swarms/{swarm['id']}/goals").json() == []
    assert client.get("/api/match?need=not-offered").json()["candidates"] == []
    assert client.get("/api/match").status_code == 400
    assert client.get("/api/boards/mind").status_code == 400
