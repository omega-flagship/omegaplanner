# Status: OmegaPlanner 0.2.1-20261008

Tier: Open (Apache-2.0). Checked on 2026-10-10.

## What works

- **Stored-plan checker (`program/`).** The installed release, less its default home swarm id. Validates plan structure
  (bounded size, unique steps, acyclic dependencies, required fields) and the stored revision's identity and body
  digest through the host context. Strict mode (opt-in per request) also requires the canonical findings and
  review receipts, with every required mandate covered on the current revision.
- **Tests,** in a fresh Python 3.12.13 venv with omegahive's `hive/requirements.txt`, against omegahive `7b1ce3f`:
  - with PeTTa (`ae66fa8`, SWI-Prolog 10.1.14, janus-swi 1.5.3): **84 passed, 11 skipped** (rerun after the default-swarm removal against omegahive `e4571e9`: same);
  - without PeTTa: **76 passed, 11 skipped** (the 8 host-integration tests skip instead of erroring).
- **Contract check.** `python -m hive.programs_check ../omegaplanner/program`: **COMPATIBLE** with program
  contract 0.1.
- **Planning library.** The Hive adapter, reasoning snapshot, matching and review bundles are exercised by the
  tests against an in-process host with synthetic data.

## Limited or known broken

- **Skipped tests (11):** 6 need the unpublished OmegaLearn package; 3 need the R17 native requester-review
  source (`OMEGAPLANNER_R17=1` on a host that has it); 1 needs the current artifact custody context; 1 needs the
  adopted findings context.
- **Not a planner by itself.** The checker validates what a planner mind returns; it does not plan, dispatch or
  grant execution. Live planning quality is not qualified.
- **Freshness across concurrent changes** (a finding or revision added between reads) is not guaranteed
  atomically; the host must recheck at admission.
- **No default swarm.** `OMEGAPLANNER_SWARMS` is required: when it is unset the checker advertises no home swarms.
  The installed release fell back to one swarm id from the organisation's hive; that default was removed in the
  handover copy (`program/program.py`, `tools/package_checker.py`, `program/SOURCES.json` digest), not yet in the
  owner's tree, so `program/program.py` now differs from the installed release by that line and its comment.
- **Boards retired.** The earlier Boards candidate is in `retired/boards/`, not installed and not tested.
- `docs/DEVELOPMENT_NOTES.md` cites platform commits from before the handover that are not in the published
  omegahive history.
