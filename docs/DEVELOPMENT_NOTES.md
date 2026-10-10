# Development notes (historical)

These are the owner's development notes, kept as written apart from removing links to the owner's private
workspace. Commits such as `601ec0f`, `4fcd9c9`, `8321467`, `433c699`, `eafd789`, `075d9df` and `c6a07d0` are
platform commits from before the handover and are not in the published omegahive history; the counts are what
was observed at the time. For the current state, see `STATUS.md`.


OmegaPlanner creates plans as a native mind swarm; OmegaReview independently reviews immutable plan revisions. This directory contains a synthetic, in-memory application contract harness, not a deployed service, Hive router, or substitute for live minds.

The harness validates dependency graphs, snapshots plan revisions with content digests, binds review requests and findings, separates planner responses from reviewer dispositions, computes affected downstream steps, preserves dissent, and refuses cancelled or stale operations. Actor names are explicit test inputs, not authenticated identities. Snapshot serialization prevents callers mutating stored revisions; production immutability belongs to the platform store.

Run from the folder that contains this repository (see the README, "Test"):

```sh
python -m pytest omegaplanner/tests -q
```

All inputs are invented. No provider calls, Hive activation, private records, execution goals, or approvals are involved.

Platform integration remains pending: authenticated C39 cross-swarm routing, shared budget accounting, request recursion limits, durable artifacts, scoped exhibits, full cancellation propagation, and native mind workers. The protocol harness does not qualify those capabilities. Live planning quality likewise remains untested.

## Matching (and the retired boards candidate)

`matching.py` provides a synthetic candidate shortlist and canonical task projections for mind, swarm and grand boards. It distinguishes assignments, assistance and specialist swarm service requests. Its first ranking policy orders eligible candidates by evidence coverage, estimated cost, spare capacity and stable identifier. Offers without verified evidence remain visibly uncertain. This policy is a starting proposal, not a learned quality score.

Acceptance rechecks eligibility under an in-process lock, reserves a capacity slot, and preserves a single assignee. Assistance keeps the parent outcome owner, returns submitted evidence references and blocks parent completion while assistance is active. Cancellation cascades and releases capacity. No task acceptance grants execution authority.

This is Python domain logic, not a board UI or deployed matching engine. Synthetic eligibility lists and string actors are explicit fixture inputs. Production integration must derive identity and eligibility from current Hive policy, filter board visibility by grants, use durable transactional claims, bind budgets across assistance descendants, and evaluate completion evidence separately. A submitted evidence locator is not verified success. Profile evidence locators are invented inputs, not an independently qualified skill record. Swarm capacity is supplied explicitly here; aggregation from live member capacity remains to be designed.

## Qualified planning API adapter

`hive_adapter.py` uses the actual shared Hive request/artifact/finding APIs, with identity determined by the transport token. It creates no separate scheduler. Two integration checks run against an isolated retained platform source pin `601ec0f6b0aafdd1a2f8e7d9cd07d2c8e32dac21`, exercising actual ASGI routes, disposable storage and authenticated module identities. The process supervisor is fake; no live worker runs.

```sh
PETTA_PATH=<PeTTa checkout> PYTHONPATH=<platform checkout at 601ec0f>:<parent folder> python -m pytest omegaplanner/tests -q
```

Observed: 27 passed. The adapter returns the plan snapshot and findings through the bound planning goal, so the requesting swarm receives the output without acquiring general access to the planner's artifact store. Matching and board API integration remains pending; those routes do not exist at this pin. Runtime spend charged to a root request is also not qualified by this pin's allocation checks.

The design and platform contract notes behind this adapter are internal and not included in this repository.


## Inert reasoning snapshot prototype

`reasoning.py` implements the first interface proposed in the planner's internal Hyperon theory note (not included). It accepts a bounded, immutable projection of Step, DependsOn, ChangedStep, GlobalChange and OpenFinding facts. Every fact has a source ID and version. The snapshot binds those facts to a principal, scope, artifact digest and validity interval. A caller-supplied host authorization callback must affirm every source; it is not a production authentication implementation.

`review_scope` retains unchanged open findings, computes downstream review closure, and covers the whole plan for global changes. It returns the snapshot binding and derivation premises, with execution_authorized false. It checks expiry, current artifact/source versions and access again before returning. The host must repeat checks at later admission; a successful check does not make future use safe against concurrent changes.

This module never interprets fact strings, invokes MeTTa, installs grounded operations, starts Hive or dispatches a task. The digest detects input changes; it is not a signature proving source authenticity. Current versions and scope decisions must be supplied by a trusted adapter. `hive_reasoning.py` now obtains them through authenticated native Hive read APIs, qualified against disposable ASGI fixtures; production integration remains pending. The result's derived review scope is a proposal, not reviewer disposition or capability qualification.

Run the disposable checks with `python -m pytest omegaplanner/tests -q`. Optional native API qualification cases have their own environment gates; skipped cases do not establish runtime acceptance.


## Authenticated Hive reasoning reads

`HiveReasoning(HivePlanner(...))` projects an artifact revision via the supplied client's token-scoped revision and finding APIs. `project(artifact_id, revision, now=..., ttl=60)` verifies the stored body digest and builds inert facts with revision and finding-set fingerprints. `derive(snapshot, artifact_id, revision, now=...)` re-reads the same sources and access scope before computing a proposed review scope. An added finding invalidates even a snapshot whose original finding set was empty.

An opaque per-client binding prevents accidental snapshot reuse by another adapter. It is not an asserted Hive principal, a signed receipt, or a transferable permission. Authorization comes from successful native reads with the same client. Native refusals propagate. Sequential reads are not an atomic database snapshot: findings and access can change after checking, so the host must recheck at later result admission. This adapter never submits a disposition, finishes a request, creates a goal, or evaluates MeTTa.

When a predecessor is readable, the adapter compares structured plan content to compute changes. When it is inaccessible, missing, or not usable, it fails or selects whole-plan review as specified by the code; it does not fabricate parent context. Removed steps and global context changes also trigger whole-plan scope. Findings without a current-revision resolved/withdrawn disposition remain conservatively in scope. This can over-review older resolved findings; it never silently closes dissent.

Qualification commands and counts were recorded in the owner's internal receipts (not included). The tests use synthetic bodies, fake process supervision and an in-process API; no live Hive start or model call is required.

## Disposable PeTTa symbolic comparison

`tools/qualify_petta.py` generates eight invented DAG scenarios and compares a fixed MeTTa review-closure rule set with the Python reference. Only generated opaque atoms enter evaluator source. Snapshot validation precedes evaluation. Each scenario runs in a disposable subprocess with a ten-second timeout and process-group cleanup. This is a qualification harness, not a production evaluator or security sandbox.

On PeTTa `ae66fa8e41dcd5539d614706bd4e5cfb34f9608d`, all eight result sets matched: empty, unchanged, chain, open objection, diamond, multiple seeds, global change and a 24-step chain. The runtime emitted Janus initialization errors because its Python 3.9 framework dependency is unavailable. These comparisons qualify the narrow result behavior despite diagnostics; they do not establish clean runtime health, Python grounding, hyperon-experimental compatibility or live planning acceptance. An initial unbound recursive enumeration timed out; the retained rule queries each known step and traverses its validated DAG predecessors.

```sh
PYTHONPATH=. python omegaplanner/tools/qualify_petta.py --runtime <PeTTa checkout> --receipt <receipt.json>
```

The receipt distinguishes result agreement from runtime cleanliness. The harness returns nonzero for mismatches/timeouts; diagnostics are recorded separately and must be reviewed before runtime adoption.

## Current review completion contract

`HivePlanner.complete_review(request_id, recommendation, rationale, finding_ids, coverage)` uses native `/review-complete`. Hive checks the live held review and mandate, requires every finding newly raised by that reviewer on that request, and creates the receipt with its exact subject, reviewer and finding digests. Generic `complete` remains for planning goals; Hive refuses it for review goals.

A delta receipt may have `empty=true` when no new finding was raised on that request even while an earlier finding remains open. Consumers must retain canonical finding history and dispositions; an empty delta receipt does not establish that all objections are resolved. The updated disposable loop confirms this distinction through final return to the requester, with execution_authorized false. It also checks omitted/duplicate findings, missing rationale, planner/foreign completion, generic completion, terminal replay and cancellation refusals. The qualification pin and counts were recorded in the owner's internal receipts (not included); this supersedes the historical adapter qualification above for the retained candidate pin. Live mind quality and deployed integration remain pending.

## R17 requester acceptance

`review_result(goal_id, decision, notes="")` calls the native agent goal-review route. On platform 4fcd9c9, a planning result is submitted for requester review rather than immediately completed. A requester mind can accept it or return it with notes to the same planner. The author and foreign minds cannot review it. The third return fails the goal. Acceptance completes the planning request; it does not authorize executing the proposed plan.

Qualification: 45 tests passed on an isolated 4fcd9c9 checkout with OMEGAPLANNER_R17=1; three candidate board tests skipped because boards adoption is queued. The full revision/dissent return loop also passed under this contract. These are synthetic ASGI tests with fake supervision, not live mind acceptance. The receipt is internal (not included).

## Review of the review

`request_review(..., review_by='agent:<id>')` optionally names a second reviewer through the native request constraints. On 8321467, structured completion remains submitted and the request stays in-review until that reviewer accepts it. The review author, planner and foreign minds are refused. Acceptance preserves the original receipt, including a hold recommendation and authority none; it does not reinterpret hold as permission to execute.

Latest contract qualification: 46 passed, three candidate-board checks skipped on isolated 8321467. The receipt is internal (not included). Boards were later ruled out; the Boards candidate is kept only in `retired/boards/`.

## Bounded plan validation

`validate_plan` now enforces the required object, list and text shapes before publication or reasoning projection. It requires nonempty goal/acceptance/step output/check/owner-proposal/fallback text, string unknowns and capability lists, structured constraints/resources, unique step IDs and dependencies, and an acyclic graph. Limits: 256 KiB canonical JSON, 256 steps, 512 edges, depth 32 and 20,000 traversed values. Nested structures are checked iteratively before encoding; non-JSON values and non-finite numbers are refused. Optional additional JSON fields remain allowed. Validation does not mutate input.

These checks establish structure only. Owner proposals, capability requirements, resource numbers and acceptance statements are not independently verified facts or execution permissions. The validator does not dispatch work or close findings. The current application adapter rejects invalid plans before invoking native publication. Host-side application validation integration remains separate work.

## Native stored-plan checker prototype

`semantics.validate_result(ctx, goal, proposal)` is qualified through Hive's actual program validation hook at eafd789. It requires a held working native planning request, an explicit execution_authorized false, a plan artifact owned by the receiving swarm, matching stored revision identity/digest, a verified stored body hash and valid bounded plan structure. It derives content from `ctx.artifact_revision`; an optional body copy must exactly match. Missing host custody methods refuse. Valid structure still awaits requester review.

This is a narrow stored-plan checker, not a complete final-return validator. The current host context supplies no canonical findings/receipt projection, so this checker does not certify returned finding completeness, mandate coverage, review quality, latest-revision choice or semantic satisfaction of request constraints. Those remain acceptance work. The integration test loads a temporary program wrapper importing the local checker; production self-contained packaging/adoption is pending. No live plugin was installed.

## Self-contained host package

`program/` now contains the standalone `program:omegaplanner` checker, its manifest and source hashes. `tools/package_checker.py` extracts the reviewed structural validator and host checker into a dependency-free Python module. Regenerate after source changes; the rebuild test rejects drift. The package loads in isolated Python without repository imports and declares no effect capabilities or actions. It does not replace the Planner mind swarm.

Qualification at isolated platform 433c699 uses a disposable copy of this actual package via HIVE_PLUGIN_DIRS, native admission and requester acceptance. 70 Planner tests pass with boards/R17 gates enabled. This newer host retains successful submissions in attempt history as well as refusals. No live installation occurred. The requested `ctx.findings(request)` interface was acknowledged by the platform as owed host work; full findings/receipt completeness remains unqualified until it is available.

## Reviewer-swarm receipt bundle

`HivePlanner.review_receipts(subject_digest)` reads the native reviewing-swarm projection added at 075d9df. Planner/foreign swarms get no receipts belonging to another receiving swarm. `review_bundle.bundle(projection, exact_subject, expected_mandates)` retains all receipt content and QC notes, reports pending requests and missing versioned mandates, and preserves hold/revise/unresolved verdicts without a majority vote. Completed receipts alone cover mandates; in-review/failed/cancelled requests remain incomplete.

The result stays advisory, execution_authorized false and finding_completeness unverified. A proceed-proposal requires complete receipt coverage but is not execution permission. The bundle verifies the full artifact/revision/digest identity in each available receipt, refusing same-digest artifact aliases. Pending receipts have no exact artifact identity in this API, so remain pending. The API is digest-filtered and may include separate request rounds; this bundle does not assert a single planning-request provenance or authoritative freshness. The host findings seam is still required for final-return validation.

## Strict canonical final return (package 0.2.0)

A native plan request can set `constraints.require_review_complete: true` and `constraints.required_review_mandates: [{id, version}, ...]`, alongside `validate: program:omegaplanner`. These are host-request policy fields, never derived from the returned proposal. Without the strict flag the checker retains its structural/custody scope.

Strict mode uses adopted `ctx.findings(request_id, artifact_id, revision)` and requires the latest stored revision. The returned `findings` and `reviews` lists must contain exactly the canonical records, preserving finding history/responses/dispositions, receipt verdicts and QC notes. Duplicate identities, omission or alteration refuse. Every required versioned mandate needs a completed receipt on the current exact subject; historical receipts cannot cover a new revision, and active current reviews block final submission. Cancelled/failed receipts remain visible but cannot supply coverage. Missing context or invalid policy refuses.

Strict acceptance qualifies canonical record preservation and completed mandate coverage at the time of the check. It does not require dissent to disappear: a conditional plan may return with still-open findings and hold receipts, then await requester review. Requester acceptance does not grant execution authority. Semantic planning quality and atomic freshness across concurrent finding/revision changes remain unqualified. Package 0.2.0 is prepared locally, not installed live.

Qualification at isolated c6a07d0: 78 tests pass/no skips, including the self-contained package and strict native return loop. Platform reports findings merged as 59947a7, which is independently present in source. Superseded boards worktree and retained source copies for 601ec0f/6ece92a were removed per platform disk notice; branches, commits, patches and receipts remain. One active Planner checkout is retained.
