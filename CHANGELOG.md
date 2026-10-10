# Changelog

## 0.2.1-20261008 (handover, 2026-10-10)

Prepared for the private SingularityNET handover. `program/` is unchanged.

- The host-integration tests (`tests/test_hive_adapter.py`, `tests/test_hive_reasoning.py`) skip when
  `PETTA_PATH` does not point at a PeTTa checkout, instead of erroring.
- Moved the retired Boards candidate (`hive_boards.py`, `ui/`, `tests/test_hive_boards.py`) to `retired/boards/`.
- Moved the owner's development notes to `docs/DEVELOPMENT_NOTES.md`, without links to the owner's private
  workspace.
- `LICENSE`: stray third-party appendix removed.
- Added README, STATUS, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, this changelog and
  `.github/repo-description.txt`.

## 0.2.1-20261008

Installed release: the stored-plan checker with opt-in canonical review-return completeness (package 0.2.x).
