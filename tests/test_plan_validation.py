from copy import deepcopy
import pytest
from omegaplanner.protocol import Refused, validate_plan, MAX_STEPS
from omegaplanner.tests.test_protocol import plan


@pytest.mark.parametrize('field,value', [('goal', 3), ('goal', ' '), ('acceptance', 'done'), ('acceptance', []), ('constraints', []), ('unknowns', {}), ('steps', {}), ('steps', [None])])
def test_malformed_plan_fields_refused(field, value):
    body = plan()
    body[field] = value
    with pytest.raises(Refused):
        validate_plan(body)


@pytest.mark.parametrize('field,value', [('id', []), ('depends_on', 'prepare'), ('depends_on', ['prepare', 'prepare']), ('resources', []), ('output', False), ('capabilities_required', [None])])
def test_malformed_step_fields_refused(field, value):
    body = plan()
    body['steps'][1][field] = value
    with pytest.raises(Refused):
        validate_plan(body)


def test_maximum_chain_validates_without_mutation():
    body = plan()
    template = body['steps'][0]
    body['steps'] = [{**deepcopy(template), 'id': f's{i}', 'depends_on': [f's{i-1}'] if i else []} for i in range(MAX_STEPS)]
    original = deepcopy(body)
    validate_plan(body)
    assert body == original
    body['steps'][0]['depends_on'] = [f's{MAX_STEPS-1}']
    with pytest.raises(Refused, match='dependency_cycle'):
        validate_plan(body)


def test_oversized_and_nonfinite_data_refused():
    for value in ['x' * (256 * 1024), float('nan'), float('inf')]:
        body = plan()
        body['constraints']['invented'] = value
        with pytest.raises(Refused):
            validate_plan(body)
    body = plan()
    body['steps'] *= MAX_STEPS
    with pytest.raises(Refused, match='step_count_limit'):
        validate_plan(body)


def test_deep_or_cyclic_json_refused():
    body = plan()
    nested = {}
    body['constraints']['nested'] = nested
    for _ in range(40):
        nested['next'] = {}
        nested = nested['next']
    with pytest.raises(Refused, match='structure_limit'):
        validate_plan(body)
    body = plan()
    body['constraints']['cycle'] = body
    with pytest.raises(Refused, match='structure_limit'):
        validate_plan(body)


def test_invalid_plan_never_reaches_publication_transport():
    from omegaplanner.hive_adapter import HivePlanner
    class Transport:
        def request(self, *args, **kwargs):
            raise AssertionError('invalid plan reached native publication')
    body = plan()
    body['steps'][0]['depends_on'] = ['schedule']
    with pytest.raises(Refused, match='dependency_cycle'):
        HivePlanner(Transport(), 'synthetic-unused').publish('synthetic-artifact', body)
