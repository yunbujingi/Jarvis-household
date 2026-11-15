"""Synthetic inventory regression tests; never open the household ledger."""
import hashlib
import hmac
import json

import pytest

from jarvis_home.models import Change
from jarvis_home.store import Conflict, Store


@pytest.fixture
def ledger(tmp_path):
    store = Store(tmp_path / 'test-ledger')
    row = store.execute('test-add-001', [Change(action='add_item', name='测试牛奶', quantity=3,
                        unit='盒', location='测试冰箱', due='2030-01-01')])['records'][0]
    return store, row


def edit(row, **fields):
    return Change(action='update', name=row['name'], record_id=row['id'], expected_version=row['version'], **fields)


def test_correction_replay_undo_and_conflict(ledger):
    store, row = ledger
    change = edit(row, new_name='测试酸奶', location='测试柜', due='2030-02-01', set_quantity=2, unit='盒')
    result = store.execute('test-edit-001', [change])
    assert store.execute('test-edit-001', [change]) == {**result, 'replayed': True}
    assert len(store.history()) == 2
    updated = result['records'][0]
    assert (updated['name'], updated['location'], updated['quantity'], updated['due']) == ('测试酸奶', '测试柜', '2', '2030-02-01')
    with pytest.raises(Conflict):
        store.execute('test-edit-stale', [change])
    store.execute('test-undo-001', undo=True)
    assert store.snapshot()['items'][0] == {**row, 'version': 3}
    assert store.execute('test-edit-001', [change])['replayed']  # retry after undo never reapplies
    assert store.snapshot()['items'][0]['version'] == 3


def test_omitted_null_and_clear_date(ledger):
    store, row = ledger
    for key, fields in [('test-date-001', {'location':'测试二层'}), ('test-date-002', {'due':None,'location':'测试三层'})]:
        row = store.execute(key, [edit(row, **fields)])['records'][0]
        assert row['due'] == '2030-01-01'
    row = store.execute('test-date-clear', [edit(row, clear_due=True)])['records'][0]
    assert row['due'] is None and row['due_source'] == 'unset'
    store.execute('test-date-undo', undo=True)
    assert store.snapshot()['items'][0]['due'] == '2030-01-01'


@pytest.mark.parametrize('fields', [dict(new_name=' '), dict(set_quantity=-1), dict(set_quantity='NaN'),
    dict(set_quantity='1.0001'), dict(due='2030-02-30'), dict(due='2030-02-01',clear_due=True), dict(quantity=1)])
def test_invalid_correction_fields(ledger, fields):
    store, row = ledger
    with pytest.raises(ValueError):
        store.execute('test-invalid-001', [edit(row, **fields)])
    assert len(store.history()) == 1


def test_absolute_quantity_vs_consume_zero_and_undo(ledger):
    store, row = ledger
    with pytest.raises(ValueError):
        store.execute('test-wrong-unit', [edit(row, set_quantity=2,unit='克')])
    row = store.execute('test-set-quantity', [edit(row,set_quantity=2,unit='盒')])['records'][0]
    assert row['quantity'] == '2'
    take = Change(action='consume',name=row['name'],record_id=row['id'],expected_version=2,quantity=1,unit='盒')
    store.execute('test-consume-001',[take])
    assert store.execute('test-consume-001',[take])['replayed']
    row=store.snapshot()['items'][0]
    assert row['quantity']=='1'
    store.execute('test-zero-quantity',[edit(row,set_quantity=0,unit='盒')])
    assert store.snapshot()['items']==[]
    store.execute('test-zero-undo',undo=True)
    assert store.snapshot()['items'][0]['quantity']=='1'


def test_batch_ambiguity_and_atomic_failure(ledger):
    store, row = ledger
    store.execute('test-second-batch',[Change(action='add_item',name=row['name'],quantity=1,unit='盒',location='测试冰箱')])
    with pytest.raises(Conflict):
        store.execute('test-ambiguous',[Change(action='update',name=row['name'],expected_version=1,location='测试柜')])
    with pytest.raises(Conflict):
        store.execute('test-atomic-fail',[edit(row,new_name='测试重命名'),edit(row,location='测试柜')])
    assert all(r['name']==row['name'] for r in store.snapshot()['items'])
    assert len(store.history())==2


def test_midnight_retry_and_legacy_digest(ledger):
    store,row=ledger
    changes=[Change(action='update',name=row['name'],record_id=row['id'],expected_version=1,location='测试位置')]
    # Frozen 0.2.1 serialization: newly optional correction fields were absent.
    legacy = changes[0].model_dump(mode='json',exclude={'new_name','set_quantity','clear_due'})
    result=store.execute('test-legacy-edit',changes)
    body={'changes':[legacy],'text':'','undo':False,'draft':False}
    expected=hmac.new(store.key,json.dumps(body,sort_keys=True,ensure_ascii=False).encode(),hashlib.sha256).hexdigest()
    with store.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
        assert db.execute('SELECT digest FROM operations WHERE id=?',('test-legacy-edit',)).fetchone()[0]==expected
    retry=Change(**{**legacy,'on':'2040-01-01'})
    retry.model_fields_set.discard('on')  # simulate omitted date default on a later day
    assert Store(store.directory).execute('test-legacy-edit',[retry])=={**result,'replayed':True}
    with pytest.raises(Conflict):
        store.execute('test-legacy-edit',[Change(**{**legacy,'on':'2040-01-01'})])


def test_actual_021_encrypted_fixture_upgrade(tmp_path):
    import sqlite3
    from pathlib import Path
    fixture=json.loads((Path(__file__).parent/'fixtures/legacy-0.2.1.json').read_text())
    directory=tmp_path/'test-old-021'
    directory.mkdir(mode=0o700)
    (directory/'key').write_bytes(bytes.fromhex(fixture['key_hex']))
    (directory/'key').chmod(0o600)
    with sqlite3.connect(directory/'home.sqlite3') as db:
        db.executescript('''CREATE TABLE records(id TEXT PRIMARY KEY,payload BLOB NOT NULL);
        CREATE TABLE operations(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,digest TEXT NOT NULL,payload BLOB NOT NULL);
        CREATE TABLE meta(id TEXT PRIMARY KEY,payload BLOB NOT NULL); PRAGMA user_version=1;''')
        for table in ('records','meta'):
            db.executemany(f'INSERT INTO {table} VALUES (?,?)',[(rid,bytes.fromhex(payload)) for rid,payload in fixture['tables'][table]])
        db.executemany('INSERT INTO operations VALUES (?,?,?,?)',[(seq,rid,digest,bytes.fromhex(payload)) for seq,rid,digest,payload in fixture['tables']['operations']])
    store=Store(directory)
    assert store.snapshot()['items'][0]['name']=='测试旧版本物品'
    assert store.execute('test-legacy-021',[fixture['change']])['replayed']
    assert len(store.history())==1
    store.execute('test-upgrade-undo',undo=True)
    assert not store.snapshot()['items']
