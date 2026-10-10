"""Read-only Hive board/service discovery candidate. No secondary task store.

Route installation requires the platform's existing admin and agent auth guards.
Cross-swarm service discovery is admin-only until a directory visibility policy
exists. Offers alone establish neither demonstrated capability nor eligibility.
"""
from fastapi import Request


class HiveBoards:
    def __init__(self, hive):
        self.hive = hive

    def board(self, kind, entity_id=None):
        if kind not in {"mind", "swarm", "grand"}:
            raise self.hive.error(400, "invalid_board", "unknown board kind")
        if kind != "grand" and not entity_id:
            raise self.hive.error(400, "entity_required", "choose a mind or swarm")
        if kind == "mind":
            self.hive.agent(entity_id)
        if kind == "swarm":
            self.hive.swarm(entity_id)
        goals = [self.hive.goals.view(row) for row in self.hive.db.all("SELECT * FROM goals ORDER BY created_at, id")]
        requests = [self.hive.collab.request_view(row) for row in self.hive.db.all("SELECT * FROM requests ORDER BY created_at, id")]
        if kind == "mind":
            goals = [g for g in goals if entity_id in {g.get("assignee"), g.get("claimed_by")} or g.get("created_by") == "agent:" + entity_id]
            goal_ids = {g["id"] for g in goals}
            requests = [r for r in requests if r["from_principal"] == "agent:" + entity_id or r["from_goal"] in goal_ids or r["receiving_goal"] in goal_ids]
        elif kind == "swarm":
            goals = [g for g in goals if g["swarm_id"] == entity_id]
            requests = [r for r in requests if entity_id in {r["from_swarm"], r["to_swarm"]}]
        return {"kind": kind, "entity_id": entity_id, "goals": goals, "requests": requests, "source": "canonical-hive", "execution_authorized": False}

    def matches(self, need):
        if not need or len(need) > 100:
            raise self.hive.error(400, "invalid_need", "name an advertised service")
        candidates = []
        for swarm in self.hive.swarms():
            if need not in self.hive.collab.services(swarm["id"]):
                continue
            goals = self.hive.goals.list(swarm["id"])
            members = [a for a in self.hive.agents() if a["swarm_id"] == swarm["id"]]
            candidates.append({"entity_id": swarm["id"], "kind": "swarm", "name": swarm["name"], "advertised_services": self.hive.collab.services(swarm["id"]), "provenance": "admin-configured-swarm-services", "verified_capabilities": [], "active_claims": sum(g["status"] in {"claimed", "waiting"} for g in goals), "member_count": len(members), "reasons": ["advertises requested service"], "eligibility": "unverified", "capacity": "unknown", "cost": "unknown", "uncertainties": ["no demonstrated capability qualification", "availability and policy eligibility require assessment"]})
        candidates.sort(key=lambda c: (c["active_claims"], c["entity_id"]))
        return {"need": need, "candidates": candidates, "policy_version": "advertised-service-load-v1", "advisory_only": True, "execution_authorized": False}


def install_routes(app, hive, admin_guard, agent_guard):
    boards = HiveBoards(hive)

    @app.get("/api/boards/{kind}")
    async def operator_board(kind: str, request: Request, entity_id: str | None = None):
        admin_guard(request)
        return boards.board(kind, entity_id)

    @app.get("/api/agent/board")
    async def own_board(request: Request):
        actor = agent_guard(request)
        board = boards.board("mind", actor["id"])
        # Requests contain cross-swarm context. Members receive their own goals
        # and request ids only; scoped detail stays behind readable_request.
        board["requests"] = [{k: row[k] for k in ("id", "kind", "state", "from_goal", "receiving_goal")} for row in board["requests"]]
        return board

    @app.get("/api/match")
    async def service_matches(request: Request, need: str = ""):
        admin_guard(request)
        return boards.matches(need)
