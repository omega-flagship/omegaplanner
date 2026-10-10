"""Planning client for Hive collab, including structured review completion.

No scheduler or identity assertions: the supplied transport's token determines
the caller. The transport is injected, permitting disposable ASGI qualification.
"""
from .protocol import canonical, validate_plan
from urllib.parse import urlencode


class HiveError(RuntimeError):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(f"Hive refused ({status}): {code}")


class HivePlanner:
    def __init__(self, transport, token):
        self.transport = transport
        self._headers = {"Authorization": "Bearer " + token}

    def _call(self, method, path, body=None):
        response = self.transport.request(method, path, headers=self._headers, json=body)
        if response.status_code >= 400:
            error = response.json().get("error", {})
            raise HiveError(response.status_code, error.get("code", "unknown"))
        return response.json()

    def request_plan(self, held_goal, planner_swarm, title, acceptance, constraints, context_refs, budget_usd):
        return self._call("POST", "/api/agent/requests", {"from_goal": held_goal, "to_swarm": planner_swarm, "kind": "plan", "title": title, "acceptance": acceptance, "constraints": constraints, "context_refs": context_refs, "budget_usd": budget_usd})

    def claim(self, goal_id):
        return self._call("POST", f"/api/agent/goals/{goal_id}/claim")

    def create_plan(self, title):
        return self._call("POST", "/api/agent/artifacts", {"kind": "plan", "title": title})

    def publish(self, artifact_id, plan, parent=None):
        validate_plan(plan)
        return self._call("POST", f"/api/agent/artifacts/{artifact_id}/revisions", {"body": canonical(plan), "parent": parent, "dependency_graph": {s["id"]: s["depends_on"] for s in plan["steps"]}})

    def revision(self, artifact_id, n):
        return self._call("GET", f"/api/agent/artifacts/{artifact_id}/revisions/{n}")

    def request_review(self, held_goal, review_swarm, revision, mandates, context_refs, budget_usd, *, review_by=None):
        constraints = {"mandates": mandates}
        if review_by is not None:
            constraints["review"] = review_by
        return self._call("POST", "/api/agent/requests", {"from_goal": held_goal, "to_swarm": review_swarm, "kind": "review", "title": "Review plan revision " + str(revision["n"]), "subject": {"artifact_id": revision["artifact_id"], "revision": revision["n"], "digest": revision["digest"]}, "constraints": constraints, "context_refs": context_refs, "budget_usd": budget_usd})

    def finding(self, request_id, mandate, step, severity, evidence_refs, recommendation):
        return self._call("POST", "/api/agent/findings", {"request_id": request_id, "mandate": mandate, "target": {"step": step}, "severity": severity, "evidence_refs": evidence_refs, "recommendation": recommendation})

    def respond(self, finding_id, revision, stance, note):
        return self._call("POST", f"/api/agent/findings/{finding_id}/response", {"revision": revision, "stance": stance, "note": note})

    def disposition(self, finding_id, request_id, revision, verdict):
        return self._call("POST", f"/api/agent/findings/{finding_id}/disposition", {"request_id": request_id, "revision": revision, "verdict": verdict})

    def findings(self, artifact_id):
        return self._call("GET", f"/api/agent/artifacts/{artifact_id}/findings")

    def complete(self, goal_id, result, proposal):
        goal = self._call("GET", f"/api/agent/goals/{goal_id}")
        return self._call("POST", f"/api/agent/goals/{goal_id}/result", {"status": "done", "result": result, "data": {"binding_digest": goal["binding_digest"], "proposal": proposal}})

    def complete_review(self, request_id, recommendation, rationale, finding_ids, coverage):
        """Submit review inputs; Hive binds identity, subject and finding digests.

        List only findings raised on this request. Earlier findings remain in
        canonical history and may be dispositioned through the current review.
        """
        return self._call("POST", f"/api/agent/requests/{request_id}/review-complete", {
            "recommendation": recommendation, "rationale": rationale,
            "finding_ids": finding_ids, "coverage": coverage})

    def review_result(self, goal_id, decision, notes=""):
        """Requester accepts or returns submitted work under native review policy."""
        return self._call("POST", f"/api/agent/goals/{goal_id}/review", {
            "decision": decision, "notes": notes})

    def review_receipts(self, subject_digest):
        """Native reviewing-swarm projection; no planner or foreign access added."""
        return self._call("GET", "/api/agent/review-receipts?" + urlencode({"subject_digest": subject_digest}))

    def planning_review_context(self, request_id, artifact_id, revision):
        return self._call("GET", f"/api/agent/requests/{request_id}/review-context?" + urlencode({
            "artifact_id": artifact_id, "revision": revision}))

    def request(self, request_id):
        return self._call("GET", f"/api/agent/requests/{request_id}")

    def cancel(self, request_id):
        return self._call("POST", f"/api/agent/requests/{request_id}/cancel")
