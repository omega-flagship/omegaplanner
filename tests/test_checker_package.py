import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from omegaplanner.tools.package_checker import build

ROOT = Path(__file__).resolve().parents[1]


def test_package_rebuild_matches_reviewed_source(tmp_path):
    for name in ['protocol.py', 'semantics.py']:
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    built = build(tmp_path)
    for name in ['program.py', 'plugin.json', 'SOURCES.json']:
        assert (built / name).read_bytes() == (ROOT / 'program' / name).read_bytes()
    manifest = json.loads((built / 'plugin.json').read_text())
    assert manifest['capabilities'] == []
    sources = json.loads((built / 'SOURCES.json').read_text())
    assert sources['program_sha256'] == hashlib.sha256((built / 'program.py').read_bytes()).hexdigest()


def test_package_loads_without_repository_imports(tmp_path):
    package = ROOT / 'program' / 'program.py'
    code = '''import importlib.util,sys
spec=importlib.util.spec_from_file_location("standalone_checker",sys.argv[1])
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.describe()["contract"] == "0.1"
assert module.validate_result(object(), {}, {"execution_authorized":False})["ok"] is False
assert module.act(None,None,None,None)["status"] == "refused"
assert not any(n == "omegaplanner" or n.startswith("omegaplanner.") for n in sys.modules)
'''
    subprocess.run([sys.executable, '-I', '-c', code, str(package)], cwd=tmp_path, check=True, timeout=10)


def test_default_app_view_passes_real_host_graph_contract_and_home_configuration(monkeypatch):
    spec = importlib.util.spec_from_file_location('planner_home', ROOT / 'program' / 'program.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    from hive.core.programs import validate_graph
    graph = validate_graph('omegaplanner', module.describe(), module.view(None, None, None), None, ValueError)
    assert graph['focus'] == 'planner-checker'
    assert graph['revision']
    monkeypatch.setenv('OMEGAPLANNER_SWARMS', 'synthetic:b, synthetic:a,synthetic:b')
    assert module.home_swarms() == ['synthetic:a', 'synthetic:b']
    monkeypatch.setenv('OMEGAPLANNER_SWARMS', '')
    assert module.home_swarms() == []
