"""Disposable synthetic MeTTa comparison; never imports private/Hive records."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile

from omegaplanner.reasoning import Fact, snapshot, review_scope

RULES = '''(= (affected $s) (match &self (ChangedStep $s) yes))
(= (affected $s) (match &self (OpenFinding $f $s) yes))
(= (affected $s) (match &self (GlobalChange $g) yes))
(= (affected $s) (match &self (DependsOn $s $p) (affected $p)))
!(collapse (unique (match &self (Step $s) (let $ok (affected $s) $s))))
'''


def compare(runtime):
    cases = [
        ('empty', 0, [], [], [], False),
        ('unchanged', 3, [(1, 0)], [], [], False),
        ('chain', 4, [(1, 0), (2, 1)], [0], [], False),
        ('open-objection', 4, [(2, 1)], [], [1], False),
        ('diamond', 5, [(1, 0), (2, 0), (3, 1), (3, 2)], [0], [], False),
        ('multiple-seeds', 5, [(2, 0), (3, 1)], [0], [1], False),
        ('global', 4, [(1, 0)], [], [], True),
        ('deep-chain', 24, [(i, i - 1) for i in range(1, 24)], [0], [], False),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='planner-petta-') as scratch:
        for name, count, edges, changes, objections, global_change in cases:
            # Only generated opaque atoms enter evaluator source. No user strings.
            facts = [Fact('Step', (f's{i}',), 'synthetic', 'v1') for i in range(count)]
            facts += [Fact('DependsOn', (f's{i}', f's{j}'), 'synthetic', 'v1') for i, j in edges]
            facts += [Fact('ChangedStep', (f's{i}',), 'synthetic', 'v1') for i in changes]
            facts += [Fact('OpenFinding', (f'f{i}', f's{j}'), 'synthetic', 'v1') for i, j in enumerate(objections)]
            if global_change:
                facts.append(Fact('GlobalChange', ('g0',), 'synthetic', 'v1'))
            snap = snapshot(principal='synthetic', scope='qualification', artifact_digest='synthetic:v1',
                            observed_at=0, expires_at=2, facts=facts, authorize=lambda *_: True)
            expected = review_scope(snap, now=1, artifact_digest=snap.artifact_digest,
                                    source_versions={'synthetic': 'v1'}, authorize=lambda *_: True)['steps']
            source = ''.join(f'({f.predicate} {" ".join(f.args)})\n' for f in snap.facts) + RULES
            path = Path(scratch) / (name + '.metta')
            path.write_text(source)
            proc = subprocess.Popen(['sh', str(runtime / 'run.sh'), str(path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                results.append({'case': name, 'status': 'timeout'})
                continue
            clean = re.sub(r'\x1b\[[0-9;]*m', '', stdout)
            # Parse only the last output line, not echoed input/compiler diagnostics.
            last = clean.strip().splitlines()[-1] if clean.strip() else ''
            valid = re.fullmatch(r'\((?:s\d+(?: s\d+)*)?\)', last) is not None
            observed = sorted(set(last[1:-1].split())) if valid else None
            results.append({'case': name, 'expected': expected, 'observed': observed,
                            'exit_code': proc.returncode, 'matches': proc.returncode == 0 and observed == expected,
                            'diagnostics_present': bool(stderr.strip()),
                            'diagnostics_sha256': hashlib.sha256(stderr.encode()).hexdigest()})
    return {'component': 'synthetic PeTTa review closure comparison',
            'runtime_pin': subprocess.check_output(['git', '-C', str(runtime), 'rev-parse', 'HEAD'], text=True).strip(),
            'rules_sha256': hashlib.sha256(RULES.encode()).hexdigest(), 'cases': results,
            'all_results_match': all(r.get('matches', False) for r in results),
            'runtime_clean': all(not r.get('diagnostics_present', True) for r in results),
            'execution_authorized': False,
            'limits': ['synthetic inputs only', 'no live Hive or provider calls',
                       'PeTTa is not hyperon-experimental compatibility proof',
                       'runtime is a subprocess, not a security sandbox',
                       '10 second per-case limit with process-group cleanup']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    receipt = compare(args.runtime.resolve())
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'matches': receipt['all_results_match'], 'runtime_clean': receipt['runtime_clean'],
                      'cases': len(receipt['cases'])}))
    raise SystemExit(0 if receipt['all_results_match'] else 1)
