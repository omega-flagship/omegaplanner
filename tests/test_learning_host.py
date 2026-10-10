import json
"""L1 existing-host export reads; trusted reference/grant fixtures are synthetic."""
from copy import deepcopy
import pytest
pytest.importorskip('hive.core.app')
pytest.importorskip('omegalearn')  # OmegaLearn is a separate, not yet published package
from hive.tests.test_core_api import client, make_swarm_and_agents
from hive.core.programs import ProgramContext
from omegalearn import Ledger, Refused as LearnRefused
from omegaplanner.learning import stored_plan_export, from_host_exports
from omegaplanner.tests.test_learning import episode
from omegaplanner.tests.test_protocol import plan
from omegaplanner.protocol import canonical


def context(hive, agent, caps):
    ctx=ProgramContext(hive,agent['swarm_id'],{'id':'planner-learn-consumer','capabilities':caps})
    ctx.actor={'kind':'mind','id':agent['id']}
    return ctx


def prepared(client):
    hive=client.app.state.hive;_,(source,reader)=make_swarm_and_agents(client)
    publisher=context(hive,source,['artifacts:read','artifacts:write'])
    published=publisher.publish('plan','Synthetic learning plan',canonical(plan()))
    row=publisher.read_revision(published['artifact_id'],published['revision'])
    args=episode();args.update(stored_plan_export(row,row));args.update(caller=row['author'],scope=source['swarm_id'])
    # Explicit fixture context: no claim that reference eligibility/grants are host-established.
    trusted={'current_subject':args['subject'],'owner':args['caller'],'scope':args['scope'],
             'permissions':args['permissions'],'visible_refs':['finding:1'],'references_valid':True}
    return hive,reader,args,trusted


def test_planner_export_actual_actor_scoped_read_and_idempotent_admission(client):
    hive,reader,args,trusted=prepared(client)
    consumer=from_host_exports(Ledger(),context(hive,reader,['artifacts:read']),lambda event:trusted)
    assert consumer.export_episode(**args)['admission']['new_evidence'] is True
    assert consumer.export_episode(**args)['admission']['new_evidence'] is False
    assert not any(call[0]=='start' for call in client.supervisor.calls)


def test_foreign_reader_is_refused_by_real_host_before_ledger_admission(client):
    hive,reader,args,trusted=prepared(client)
    _,(foreign,_)=make_swarm_and_agents(client); ledger=Ledger()
    consumer=from_host_exports(ledger,context(hive,foreign,['artifacts:read']),lambda event:trusted)
    with pytest.raises(Exception) as failure:consumer.export_episode(**args)
    assert getattr(failure.value,'code',None)=='forbidden'
    assert ledger.checkpoint()['events']=={}


@pytest.mark.parametrize('fault',['capability','actor','stale','author'])
def test_existing_host_read_and_learn_binding_refusals(client,fault):
    hive,reader,args,trusted=prepared(client)
    ctx=context(hive,reader,['artifacts:read']);ledger=Ledger()
    if fault=='capability':ctx._program['capabilities']=[]
    if fault=='actor':ctx.actor=None
    if fault=='stale':trusted['current_subject']=dict(args['subject'],revision='2')
    if fault=='author':args['caller']='agent:'+reader['id'];trusted['owner']=args['caller']
    consumer=from_host_exports(ledger,ctx,lambda event:trusted)
    with pytest.raises(Exception) as failure:consumer.export_episode(**args)
    if fault=='capability':assert getattr(failure.value,'code',None)=='capability_missing'
    elif fault=='actor':assert getattr(failure.value,'code',None)=='actor_required'
    else:assert isinstance(failure.value,LearnRefused)
    assert ledger.checkpoint()['events']=={}


def test_planner_subject_real_host_capture_preserves_exact_proposal(client):
    from omegaplanner.tests.test_bench_subject import setup,request
    from omegaplanner.bench_subject import host_plan_sink
    hive=client.app.state.hive
    _,(agent,_)=make_swarm_and_agents(client)
    ctx=context(hive,agent,['artifacts:write','artifacts:read'])
    ex,_,_=setup('FULL',host_plan_sink(ctx),{'kind':'actor-scoped-host-plan','version':'1'})
    result=ex.execute(request(ex,['approval']))
    assert result['status']=='ok'
    capture=ex.captures()[0];binding=capture['plan_artifact']
    row=ctx.read_revision(binding['artifact_id'],binding['revision'])
    assert row['digest']==binding['digest']
    assert json.loads(row['body'])==capture['local_plan']['body']
    assert capture['capture_receipt'] is None and not capture['capability_acceptance_ready']
    assert not any(call[0]=='start' for call in client.supervisor.calls)


def test_planner_subject_missing_write_capability_is_metered_not_accepted(client):
    from omegaplanner.tests.test_bench_subject import setup,request
    from omegaplanner.bench_subject import host_plan_sink
    hive=client.app.state.hive;_,(agent,_)=make_swarm_and_agents(client)
    ex,_,_=setup('FULL',host_plan_sink(context(hive,agent,['artifacts:read'])),
                 {'kind':'actor-scoped-host-plan','version':'1'})
    result=ex.execute(request(ex,['approval']))
    assert result['status']=='failed' and result['usage']['attempts']==1
    assert ex.captures()[0]['plan_artifact'] is None
