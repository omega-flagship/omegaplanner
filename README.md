# OmegaPlanner

OmegaPlanner is the OmegaHive plan checker. It validates stored plans (dependency graphs, immutable plan revisions
with content digests) and, when a request opts in, checks that a returned review is canonical and complete. The
installed app is `program/`, generated from `protocol.py` and `semantics.py` (pinned in `program/SOURCES.json`).
The rest of the repository is the planning library around it: a Hive planning adapter, an inert reasoning
snapshot, task matching and review bundles.

**Tier:** Open source, Apache-2.0 (`LICENSE`; notices in `NOTICE`).

This repository is release **0.2.1-20261008**. `program/` matches the installed release (host source digest
`sha256:004eb0878ba20237aa871608c6a4cfd88ca447f6b1db2ca66fa5f6ad0bbd1887`) except that the default home swarm id
was removed (see `STATUS.md`); this copy's digest is `sha256:e2a96acd56ae314e49a77e65e532195205ba357572ea955efba3fe0ac5a40396`.

| Path | What |
|---|---|
| `program/` | The installed app (`plugin.json`, generated `program.py`, `SOURCES.json`); point `HIVE_PLUGIN_DIRS` at it |
| `protocol.py`, `semantics.py` | Plan and review protocol and the stored-plan checker; `tools/package_checker.py` regenerates `program/` from them |
| `hive_adapter.py`, `hive_reasoning.py`, `reasoning.py` | Planning adapter over the Hive request/artifact/finding APIs, and an inert review-scope reasoning snapshot |
| `matching.py`, `review_bundle.py` | Task matching and reviewer-receipt bundles |
| `learning.py`, `bench_subject.py`, `learning_manifest.json` | Learning and bench integration (needs the separate OmegaLearn package) |
| `tools/` | `package_checker.py`, and the PeTTa / native-skill qualification harnesses |
| `tests/` | pytest |
| `docs/DEVELOPMENT_NOTES.md` | The owner's development notes (historical) |
| `retired/boards/` | The retired Boards candidate (not installed, not tested) |

## Requirements

- **OmegaHive** (the `omegahive` repository) and its Python **3.12** environment: `pip install -r
  hive/requirements.txt` from the omegahive checkout, which includes pytest. `program/` itself needs only the
  standard library.
- For the 8 host-integration tests: **PeTTa at commit `ae66fa8`** with **SWI-Prolog 10.1.14** and **janus-swi
  1.5.3** built against that Python, as in the omegahive README ("Prerequisites"). Without PeTTa those tests skip.
- **Optional:** the OmegaLearn package (not published yet). Its 6 tests skip without it.

## Quick start (mount in a hive)

1. Add `program/` (not the repository root) to `HIVE_PLUGIN_DIRS`.
2. Set `OMEGAPLANNER_SWARMS` to the swarms that use the checker.
3. Optionally pin it with `HIVE_APP_PINS` (the `program/` folder plus the digest above).
4. A planning request opts in by naming the checker: `validate: program:omegaplanner`, and for the strict
   review-return check also `constraints.require_review_complete: true` with `constraints.required_review_mandates`.

## Test

The tests import `omegaplanner.*`, so run them from the folder that **contains** this repository, with
OmegaHive checked out next to it:

```
<parent>/
  omegahive/       # host checkout
  omegaplanner/    # this repository
```

```sh
cd <parent>
python3.12 -m venv .venv
.venv/bin/pip install -r omegahive/hive/requirements.txt
export PATH=$HOME/swipl-patched/bin:$PATH        # the SWI-Prolog 10.1.14 built for PeTTa
export PETTA_PATH=<PeTTa checkout>
PYTHONPATH=omegahive:. .venv/bin/python -m pytest -q omegaplanner/tests
```

Expected: **84 passed, 11 skipped** (OmegaLearn absent: 6; R17 native source: 3; custody and findings
context: 2). Without `PETTA_PATH`: 76 passed, the PeTTa tests skip.

Contract check (no PeTTa needed):

```sh
cd omegahive
python -m hive.programs_check ../omegaplanner/program     # COMPATIBLE with program contract 0.1
```

After changing `protocol.py` or `semantics.py`, regenerate the app with `python tools/package_checker.py`
(the tests fail on drift).

## How it plugs into OmegaHive

OmegaHive loads apps ("Dot programs") from the folders in `HIVE_PLUGIN_DIRS`. For OmegaPlanner that folder is
**`program/`**, which holds `plugin.json` and a dependency-free `program.py` implementing program contract 0.1
(described in `hive/PROGRAMS.md` in the omegahive repository).

- The app declares no capabilities and no actions. Its job is `validate_result`: when a planning request names
  `program:omegaplanner`, the host calls it on the returned proposal. It checks the stored plan revision through
  the host context (`ctx.artifact_revision`, and in strict mode `ctx.findings`) and the plan's structure. A
  valid result still waits for requester review; nothing here grants execution.
- The planning library (`hive_adapter.py` and the rest) is not loaded by the host. It is client code a planner
  mind or harness uses against the Hive HTTP API, with identity from its transport token.

## Licence

Apache-2.0 (`LICENSE`); notices in `NOTICE`.
