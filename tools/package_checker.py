"""Build a self-contained host checker from reviewed local source functions."""
import ast
import hashlib
import json
from pathlib import Path


def build(root):
    inputs = {'protocol.py': ['Refused', 'canonical', 'MAX_PLAN_BYTES', 'MAX_STEPS', 'MAX_EDGES', 'validate_plan'],
              'semantics.py': ['validate_result']}
    pieces = ['"""Generated stored-plan checker. Regenerate with tools/package_checker.py.\nNo planning worker or dispatch. Canonical completeness is opt-in host policy.\n"""\nimport hashlib\nimport json\n']
    sources = {}
    for filename, names in inputs.items():
        path = root / filename
        source = path.read_text()
        sources[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        nodes = {}
        for node in ast.parse(source).body:
            name = getattr(node, 'name', None)
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            if name in names:
                nodes[name] = ast.get_source_segment(source, node)
        if set(nodes) != set(names):
            raise ValueError('source symbols changed; review package generator')
        pieces.extend(nodes[name] for name in names)
    pieces.append('''def describe():
    return {"contract": "0.1", "kinds": [{"id": "plan", "label": "Plan", "role": "other"}], "relations": [], "actions": []}


def home_swarms():
    # Explicit enrolment configuration; this advertises homes, not authority. No default: unset means no homes.
    import os
    return sorted(set(s.strip() for s in os.environ.get("OMEGAPLANNER_SWARMS", "").split(",") if s.strip()))


def view(ctx, focus=None, stage=None):
    return {"revision": "planner-checker-home-1", "title": "OmegaPlanner", "focus": "planner-checker",
            "items": [{"id": "planner-checker", "kind": "plan", "label": "Stored-plan checker",
                       "status": "current", "flags": [], "sources": [],
                       "summary": "Checks stored plans and canonical review return. Learning candidates remain proposals."}],
            "links": []}


def act(ctx, action, items, params):
    return {"ok": False, "status": "refused", "message": "This package checks stored plans; it has no actions."}
''')
    body = '\n\n'.join(pieces) + '\n'
    folder = root / 'program'
    folder.mkdir(exist_ok=True)
    (folder / 'program.py').write_text(body)
    manifest = {'id': 'omegaplanner', 'name': 'OmegaPlanner plan checker', 'version': '0.2.1',
                'contract': '0.1', 'module': 'program.py', 'capabilities': [],
                'description': 'Stored-plan validation with opt-in canonical review-return completeness.'}
    (folder / 'plugin.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (folder / 'SOURCES.json').write_text(json.dumps({'sources': sources, 'program_sha256': hashlib.sha256(body.encode()).hexdigest(),
                                                 'generator': 'tools/package_checker.py'}, indent=2) + '\n')
    return folder


if __name__ == '__main__':
    print(build(Path(__file__).resolve().parents[1]))
