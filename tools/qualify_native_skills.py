"""Actual PeTTa skill dispatch with synthetic transport, no Hive/provider access."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def worker(candidate, runtime):
    for name in ('HIVE_API_URL', 'HIVE_WS_TOKEN'):
        os.environ.pop(name, None)
    sys.path[:0] = [str(runtime/'python'), str(candidate/'src'), str(candidate/'tests'), str(candidate/'modules/hive/src')]
    import hive_commons as bridge
    import helper_command_parser as parser
    from module_loader_test_utils import enabled_module_loader
    from petta import PeTTa
    calls = []
    finding = {'id':'fi_synthetic','recommendation':'Unknown; literal ⁏','disposition':None}
    context = {'findings':[finding],'reviews':[],'authority':'none'}
    def synthetic(method, path, payload=None):
        calls.append((method,path,payload))
        if '/review-context?' in path: return context,None
        if path.endswith('/findings'): return [finding],None
        if path.endswith('/response') or path.endswith('/disposition'): return finding,None
        if path.startswith('/api/agent/requests/'): return {'receiving_goal':'g_synthetic'},None
        if '/revisions/' in path: return {'artifact_id':'ar_synthetic','n':1,'digest':'sha256:synthetic','body':'{}'},None
        if path.endswith('/result'): return {'id':'g_synthetic','status':'submitted'},None
        if path.startswith('/api/agent/goals/'): return {'id':'g_synthetic','binding_digest':'sha256:binding'},None
        raise AssertionError('unexpected synthetic call')
    bridge._call = synthetic
    interpreter = PeTTa(petta_path=str(runtime))
    interpreter.load_metta_file(str(candidate/'modules/hive/skills.metta'))
    cases = [
        ('hive-findings-read ar_synthetic','HIVE-FINDINGS'),
        ('hive-plan-review-context rq_synthetic ar_synthetic 1','HIVE-PLAN-REVIEW-CONTEXT'),
        ('hive-finding-response fi_synthetic '+bridge.encode(json.dumps({'revision':1,'stance':'addressed','note':'Claim only; literal ⁏'},ensure_ascii=False)),'HIVE-FINDING-RESPONSE'),
        ('hive-finding-disposition fi_synthetic '+json.dumps({'request_id':'rq_review','revision':1,'verdict':'still-open'}),'HIVE-FINDING-DISPOSITION'),
        ('hive-plan-return rq_synthetic ar_synthetic 1','HIVE-GOAL-PROPOSED'),
    ]
    results=[]
    with enabled_module_loader(parser,'hive'):
        for command, marker in cases:
            parsed=parser.signature_balance_parentheses(command)
            observed=interpreter.process_metta_string('!'+parsed[1:-1])
            results.append({'skill':command.split()[0],'marker_observed':marker in str(observed)})
    response=next(p for m,path,p in calls if path.endswith('/response'))
    submission=next(p for m,path,p in calls if path.endswith('/result'))
    intact = response['note']=='Claim only; literal ⁏' and submission['data']['proposal']['findings']==[finding] and submission['data']['proposal']['execution_authorized'] is False
    out={'cases':results,'payloads_intact':intact,'all_pass':intact and all(r['marker_observed'] for r in results),'input_encoding':'existing Hive text membrane for semicolons/literal delimiter','transport':'synthetic monkeypatch; no HTTP','paid_calls':0,'limits':['actual PeTTa dispatch, not live Hive or mind reasoning','synthetic transport does not qualify host authorization']}
    print(json.dumps(out))
    return 0 if out['all_pass'] else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--receipt',type=Path);p.add_argument('--worker',action='store_true');a=p.parse_args()
    if a.worker:return worker(a.candidate.resolve(),a.runtime.resolve())
    env=dict(os.environ);env.pop('HIVE_API_URL',None);env.pop('HIVE_WS_TOKEN',None)
    proc=subprocess.Popen([sys.executable,__file__,'--worker','--candidate',str(a.candidate.resolve()),'--runtime',str(a.runtime.resolve())],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    try:stdout,stderr=proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL);stdout,stderr=proc.communicate();out={'all_pass':False,'status':'timeout','paid_calls':0}
    else:
        try:out=json.loads(stdout.strip().splitlines()[-1])
        except (ValueError,IndexError):out={'all_pass':False,'status':'worker_failed','paid_calls':0}
    import hashlib
    out.update(exit_code=proc.returncode,diagnostics_present=bool(stderr.strip()),diagnostics_sha256=hashlib.sha256(stderr.encode()).hexdigest(), candidate_pin=subprocess.check_output(['git','-C',str(a.candidate),'rev-parse','HEAD'],text=True).strip(), runtime_pin=subprocess.check_output(['git','-C',str(a.runtime),'rev-parse','HEAD'],text=True).strip(), initial_probe_limit='Raw ASCII semicolons in JSON command text caused PeTTa syntax failure. Passing existing membrane-encoded text preserves semicolon and literal delimiter.')
    if a.receipt:a.receipt.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out));return 0 if out['all_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
