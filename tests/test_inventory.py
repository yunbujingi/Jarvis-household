from datetime import date

import pytest

from jarvis_home.inventory import query_items
from jarvis_home.models import Change
from jarvis_home.store import Store


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    monkeypatch.setattr('jarvis_home.inventory.today', lambda: date(2026, 11, 15))
    store = Store(tmp_path / 'ledger')
    store.execute('inventory-seed', [
        Change(action='add_item', name=name, quantity=quantity, unit='盒', location=location, due=due)
        for name, quantity, location, due in [
            ('牛奶', 2, '冰箱冷藏上层', '2026-11-14'),
            ('牛奶', 3, '冰箱冷藏下层', '2026-11-15'),
            ('酸奶', 1, '冰箱冷藏下层', '2026-11-22'),
            ('牛奶', 1, '储物柜', '2026-11-23'),
            ('备用电池', 4, '书房第二个抽屉', None),
        ]])
    return store


def test_name_location_and_batches(inventory):
    result = query_items(inventory.snapshot()['items'], name='牛奶', location='冷藏')
    assert result['item_count'] == 2
    assert [r['quantity'] for r in result['records']] == ['2', '3']
    assert [r['days_until_due'] for r in result['records']] == [-1, 0]
    assert result['as_of'] == '2026-11-15'
    assert query_items(inventory.snapshot()['items'], name='没有的物品')['records'] == []


@pytest.mark.parametrize('expiry, expected', [
    ('overdue', [-1]), ('today', [0]), ('within_days', [0, 7]), ('unset', [None]),
])
def test_expiry_boundaries_and_unknown(inventory, expiry, expected):
    result = query_items(inventory.snapshot()['items'], expiry=expiry, days=7)
    assert [r['days_until_due'] for r in result['records']] == expected
    assert result['unknown_due_count'] == 1
    assert all(r['due_source'] == ('unset' if r['due'] is None else 'user') for r in result['records'])


def test_pagination_zero_days_and_sort(inventory):
    rows = inventory.snapshot()['items']
    first = query_items(rows, limit=2)
    second = query_items(rows, offset=2, limit=2)
    assert first['item_count'] == 5 and first['has_more'] and second['has_more']
    assert not {r['id'] for r in first['records']} & {r['id'] for r in second['records']}
    assert query_items(rows, offset=4)['records'][0]['name'] == '备用电池'
    assert not query_items(rows, offset=5)['has_more']
    assert query_items(rows, expiry='within_days', days=0)['item_count'] == 1


@pytest.mark.parametrize('options', [{'days': -1}, {'days': 3661}, {'name': '  '}, {'location': ' '},
    {'limit': 31}, {'offset': -1}, {'expiry': 'invented'}])
def test_invalid_query_rejected(inventory, options):
    with pytest.raises(ValueError):
        query_items(inventory.snapshot()['items'], **options)


def test_move_restart_and_undo_keep_due(inventory):
    old = query_items(inventory.snapshot()['items'], name='备用电池')['records'][0]
    inventory.execute('inventory-move', [Change(action='update', name=old['name'], record_id=old['id'],
        expected_version=old['version'], location='玄关抽屉')])
    again = Store(inventory.directory)
    assert query_items(again.snapshot()['items'], location='玄关')['item_count'] == 1
    again.execute('inventory-undo-move', undo=True)
    assert query_items(again.snapshot()['items'], name='备用电池')['records'][0]['location'] == '书房第二个抽屉'
    again.execute('inventory-undo-seed', undo=True)
    assert query_items(again.snapshot()['items'])['item_count'] == 0
