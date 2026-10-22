import pytest
from sqlalchemy import select
from app.db.models import Category, Component, MotherboardSpec, RamSpec
from app.services.ac3 import filter_domains
from app.services.compatibility import SelectedPart
from test_compatibility import parts


def test_cascading_removal_and_input_preservation(parts):
    cpu = parts[Category.CPU]
    board = parts[Category.MOTHERBOARD]
    ram = parts[Category.RAM]
    bad_board = SelectedPart(Component(id=101, category=Category.MOTHERBOARD),
        MotherboardSpec(socket="AM5", memory_type="DDR5", memory_slots=4, max_memory_gb=128))
    bad_ram = SelectedPart(Component(id=102, category=Category.RAM),
        RamSpec(memory_type="DDR5", modules=2, capacity_gb=32))
    # RAM -> board is visited before the unsupported board is removed.
    domains = {Category.RAM: [ram, bad_ram], Category.MOTHERBOARD: [board, bad_board], Category.CPU: [cpu]}
    result = filter_domains(domains)
    assert result[Category.MOTHERBOARD] == [board]
    assert result[Category.RAM] == [ram]
    assert len(domains[Category.RAM]) == 2
    assert filter_domains(result) == result


def test_conflicting_fixed_selections(parts):
    parts[Category.MOTHERBOARD].spec.socket = "AM5"
    result = filter_domains({c: [parts[c]] for c in (Category.CPU, Category.MOTHERBOARD)})
    assert any(not values for values in result.values())


def test_unknown_data_retained(parts):
    board = SelectedPart(parts[Category.MOTHERBOARD].component, None)
    domains = {Category.CPU: [parts[Category.CPU]], Category.MOTHERBOARD: [board]}
    assert filter_domains(domains) == domains


def test_optional_parts_follow_cpu_capabilities(parts):
    cpu = parts[Category.CPU]
    domains = {Category.CPU: [cpu], Category.GPU: [None], Category.COOLER: [None]}
    assert filter_domains(domains) == domains
    cpu.spec.integrated_graphics = False
    assert any(not values for values in filter_domains(domains).values())


def test_empty_required_domain_propagates(parts):
    result = filter_domains({Category.CPU: [parts[Category.CPU]], Category.RAM: []})
    assert not result[Category.CPU]


@pytest.mark.parametrize('payload', [{"components": {"cpu": True}}, {"components": {"cpu": 1, "ram": 1}}, {"extra": 1}])
def test_invalid_filter_input(client, payload):
    assert client.post('/compatibility/filter', json=payload).status_code == 422


def test_filter_endpoint(catalog_client):
    client, db = catalog_client
    cpu = db.scalar(select(Component).where(Component.slug == 'amd-ryzen-5-5500'))
    response = client.post('/compatibility/filter', json={'components': {'cpu': cpu.id}})
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'arc_consistent'
    assert result['domains']['cpu'] == [cpu.id]
    assert None not in result['domains']['gpu']
    assert None not in result['domains']['cooler']
    boards = list(db.scalars(select(MotherboardSpec).where(MotherboardSpec.component_id.in_(result['domains']['motherboard']))))
    assert boards and all(board.socket == 'AM4' for board in boards)
    assert client.post('/compatibility/filter', json={}).status_code == 200
    assert client.post('/compatibility/filter', json={'components': {'ram': cpu.id}}).status_code == 422
    assert client.post('/compatibility/filter', json={'components': {'cpu': 99999999}}).status_code == 404
