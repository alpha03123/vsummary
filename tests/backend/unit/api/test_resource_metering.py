from dataclasses import replace
import pytest
from backend.core.context import WorkspaceContext
from backend.core.request_context import bind_workspace_context
from backend.core.metering import ResourceUsage, bind_resource_budget, resource_call, response_usage


class Budget:
    def __init__(self):
        self.reservations = []
        self.records = []

    def reserve(self, context, estimate):
        self.reservations.append((context, estimate))
        return estimate.call_id

    def settle(self, reservation, actual):
        self.records.append((reservation, actual))


def test_resource_call_records_actual_usage_with_ownership_and_operation():
    budget = Budget()
    context = WorkspaceContext('workspace', 'actor', 'request')
    with bind_workspace_context(context), bind_resource_budget(budget, 'job'):
        with resource_call(ResourceUsage('embedding', 'configured-model', input_tokens=900)) as measurement:
            measurement.complete(input_tokens=100, output_tokens=0)
    assert budget.reservations[0][0] == context
    reservation, actual = budget.records[0]
    assert reservation == actual.call_id and actual.operation_id == 'job'
    assert actual.input_tokens == 100 and not actual.estimated
    assert len(budget.records) == 1


def test_interrupted_call_preserves_explicit_estimate_and_original_error():
    budget = Budget()
    context = WorkspaceContext('workspace', 'actor', 'request')
    with bind_workspace_context(context), bind_resource_budget(budget, 'job'):
        with pytest.raises(TimeoutError, match='upstream timeout'):
            with resource_call(ResourceUsage('asr', 'configured-model', duration_seconds=60)):
                raise TimeoutError('upstream timeout')
    assert len(budget.records) == 1
    assert budget.records[0][1].estimated and budget.records[0][1].duration_seconds == 60


def test_missing_or_invalid_provider_measurements_fail_instead_of_zero_billing():
    assert response_usage({'usage': {'total_tokens': 42}}) == (42, 0)
    assert response_usage({'usage': {'input_tokens': 12, 'output_tokens': 3}}, require_output=True) == (12, 3)
    for response in ({}, {'usage': {'total_tokens': 42}}, {'usage': {'input_tokens': -1, 'output_tokens': 0}}):
        with pytest.raises(ValueError):
            response_usage(response, require_output=True)
