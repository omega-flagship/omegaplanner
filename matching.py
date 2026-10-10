"""Synthetic matching and board projection candidate, with no Hive side effects.

Identity and eligibility supplied here are invented test inputs. Production must
derive them from authenticated Hive principals and current policy decisions.
"""
from copy import deepcopy
from threading import RLock
from .protocol import Refused


class MatchingHarness:
    def __init__(self):
        self._profiles = {}
        self._tasks = {}
        self._lock = RLock()

    def register(self, profile):
        with self._lock:
            if profile["id"] in self._profiles:
                raise Refused("profile_exists")
            if profile["kind"] not in {"mind", "swarm"}:
                raise Refused("invalid_entity_kind")
            if not isinstance(profile["capacity"], int) or profile["capacity"] < 0:
                raise Refused("invalid_capacity")
            if not isinstance(profile["cost_cents"], int) or profile["cost_cents"] < 0:
                raise Refused("invalid_cost")
            if any(not refs for refs in profile["verified"].values()):
                raise Refused("verification_requires_evidence")
            self._profiles[profile["id"]] = deepcopy(profile)

    def post(self, task):
        with self._lock:
            if task["id"] in self._tasks:
                raise Refused("task_exists")
            if task["kind"] not in {"assignment", "assistance", "service"}:
                raise Refused("invalid_task_kind")
            if not task["acceptance"] or not task["required"]:
                raise Refused("missing_task_requirements")
            if not isinstance(task["max_cost_cents"], int) or task["max_cost_cents"] < 0:
                raise Refused("invalid_budget")
            if task["kind"] == "assistance":
                parent = self._tasks.get(task.get("parent_id"))
                if not parent or parent["state"] != "assigned" or not parent["assignee"]:
                    raise Refused("assistance_requires_active_owner")
                if task["requester"] != parent["assignee"] or task["requester_swarm"] != parent["requester_swarm"]:
                    raise Refused("assistance_owner_mismatch")
            self._tasks[task["id"]] = {**deepcopy(task), "revision": 1, "state": "open", "assignee": None, "evidence_refs": [], "execution_authorized": False}

    def _load(self, entity_id):
        return sum(t["state"] == "assigned" and t["assignee"] == entity_id for t in self._tasks.values())

    def _candidate(self, task, profile):
        required = set(task["required"])
        offered = set(profile["offers"]) | set(profile["verified"])
        reasons = []
        target_kind = "swarm" if task["kind"] == "service" else "mind"
        if profile["kind"] != target_kind:
            reasons.append("entity_kind")
        if not profile["available"]:
            reasons.append("unavailable")
        if self._load(profile["id"]) >= profile["capacity"]:
            reasons.append("at_capacity")
        if task["id"] not in profile["eligible_task_ids"]:
            reasons.append("not_eligible")
        if required - offered:
            reasons.append("missing_capabilities")
        if profile["cost_cents"] > task["max_cost_cents"]:
            reasons.append("over_budget")
        if profile["id"] == task["requester"]:
            reasons.append("self_request")
        if reasons:
            return None, {"entity_id": profile["id"], "reasons": reasons}
        verified = sorted(required & set(profile["verified"]))
        advertised = sorted(required - set(verified))
        return {"entity_id": profile["id"], "swarm_id": profile["swarm_id"], "verified_capabilities": verified, "advertised_only": advertised, "evidence_refs": {c: deepcopy(profile["verified"][c]) for c in verified}, "cost_cents": profile["cost_cents"], "capacity_remaining": profile["capacity"] - self._load(profile["id"]), "reasons": ["required capabilities offered", "synthetic eligibility supplied", "within capacity and estimated cost limit"], "uncertainties": ["advertised capability lacks performance evidence: " + c for c in advertised]}, None

    def match(self, task_id):
        with self._lock:
            task = self._tasks[task_id]
            if task["state"] != "open":
                raise Refused("task_not_open")
            candidates, excluded = [], []
            for profile in self._profiles.values():
                candidate, exclusion = self._candidate(task, profile)
                if candidate:
                    candidates.append(candidate)
                else:
                    excluded.append(exclusion)
            # Transparent initial policy: evidence coverage, cost, spare capacity,
            # stable id. No learned quality score or auto assignment is claimed.
            candidates.sort(key=lambda c: (-len(c["verified_capabilities"]), c["cost_cents"], -c["capacity_remaining"], c["entity_id"]))
            return {"task_id": task_id, "task_revision": task["revision"], "candidates": candidates, "excluded": excluded, "policy_version": "synthetic-evidence-cost-capacity-v1"}

    def accept(self, task_id, entity_id, actor, base_revision):
        with self._lock:
            task = self._tasks[task_id]
            if actor != entity_id:
                raise Refused("recipient_must_accept")
            if task["revision"] != base_revision:
                raise Refused("stale_task")
            if task["state"] != "open":
                raise Refused("task_not_open")
            candidate, _ = self._candidate(task, self._profiles[entity_id])
            if candidate is None:
                raise Refused("candidate_no_longer_eligible")
            task.update(state="assigned", assignee=entity_id, revision=task["revision"] + 1)
            return deepcopy(task)

    def update_availability(self, entity_id, available):
        with self._lock:
            self._profiles[entity_id]["available"] = bool(available)

    def complete(self, task_id, actor, evidence_refs):
        with self._lock:
            task = self._tasks[task_id]
            if task["state"] != "assigned" or task["assignee"] != actor:
                raise Refused("assignee_only")
            if not evidence_refs:
                raise Refused("completion_requires_evidence")
            if any(t.get("parent_id") == task_id and t["state"] in {"open", "assigned"} for t in self._tasks.values()):
                raise Refused("active_assistance")
            task.update(state="done", evidence_refs=deepcopy(evidence_refs), revision=task["revision"] + 1)
            # Evidence is a submitted locator, not independently verified success.
            return deepcopy(task)

    def cancel(self, task_id, actor):
        with self._lock:
            task = self._tasks[task_id]
            if actor != task["requester"]:
                raise Refused("requester_only")
            if task["state"] in {"done", "cancelled"}:
                raise Refused("task_terminal")
            queue = [task_id]
            while queue:
                current_id = queue.pop()
                current = self._tasks[current_id]
                if current["state"] in {"done", "cancelled"}:
                    continue
                current.update(state="cancelled", revision=current["revision"] + 1)
                queue.extend(t["id"] for t in self._tasks.values() if t.get("parent_id") == current_id)

    def board(self, kind, entity_id=None):
        """Projection only; test harness has no production visibility gate."""
        with self._lock:
            if kind not in {"mind", "swarm", "grand"}:
                raise Refused("invalid_board")
            rows = []
            for task in self._tasks.values():
                assignee = self._profiles.get(task["assignee"])
                parent = self._tasks.get(task.get("parent_id"))
                owner = parent["assignee"] if parent else task["assignee"]
                relevant = kind == "grand" or (kind == "mind" and entity_id in {task["requester"], task["assignee"], owner}) or (kind == "swarm" and (entity_id == task["requester_swarm"] or (assignee and entity_id == assignee["swarm_id"])))
                if relevant:
                    row = deepcopy(task)
                    row["outcome_owner"] = owner
                    row["completion_verified"] = False
                    rows.append(row)
            return {"kind": kind, "entity_id": entity_id, "tasks": sorted(rows, key=lambda t: t["id"])}
