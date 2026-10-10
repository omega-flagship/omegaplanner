from copy import deepcopy
import pytest
from omegaplanner.review_bundle import bundle
from omegaplanner.protocol import Refused

SUBJECT={'artifact_id':'invented','revision':1,'digest':'sha256:invented'}
MANDATES=[{'id':'security','version':'1'},{'id':'cost','version':'1'}]

def projection():
    rows=[]
    for i,mandate in enumerate(MANDATES):
        rows.append({'request_id':f'r{i}','state':'completed','receipt':{'request_id':f'r{i}','subject':SUBJECT,'mandate':mandate,'authority':'none','recommendation':'hold' if i==0 else 'proceed','rationale':'Invented dissent'},'qc':[{'action':'accept','notes':'Preserve verbatim notes'}]})
    return {'subject_digest':SUBJECT['digest'],'requests':rows,'count':2}


def test_dissent_and_qc_preserved_without_execution_permission():
    source=projection();result=bundle(source,SUBJECT,MANDATES)
    assert result['status']=='hold' and result['coverage_complete']
    assert result['requests']==source['requests']
    result['requests'][0]['qc'][0]['notes']='changed copy'
    assert source['requests'][0]['qc'][0]['notes']=='Preserve verbatim notes'
    assert result['execution_authorized'] is False
    assert result['finding_completeness']=='unverified'


def test_missing_mandate_and_unaccepted_receipt_remain_visible():
    source=projection();source['requests'][0]['state']='in-review'
    result=bundle(source,SUBJECT,MANDATES)
    assert result['status']=='hold' and not result['coverage_complete']
    assert result['pending_requests']==['r0']
    assert result['missing_mandates']==[MANDATES[0]]
    empty={'subject_digest':SUBJECT['digest'],'requests':[],'count':0}
    assert bundle(empty,SUBJECT,MANDATES)['status']=='pending'


@pytest.mark.parametrize('change', ['alias','authority','duplicate','count','mandate'])
def test_ambiguous_or_invalid_receipts_refused(change):
    source=deepcopy(projection())
    if change=='alias':source['requests'][0]['receipt']['subject']['artifact_id']='same-digest-other-artifact'
    elif change=='authority':source['requests'][0]['receipt']['authority']='execute'
    elif change=='duplicate':source['requests'][1]['request_id']='r0'
    elif change=='count':source['count']=3
    else:source['requests'][0]['receipt']['mandate']['version']='2'
    with pytest.raises(Refused):bundle(source,SUBJECT,MANDATES)
