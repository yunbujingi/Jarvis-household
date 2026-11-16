import concurrent.futures
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient

from jarvis_home.models import Change, today
from jarvis_home.router import command
from jarvis_home.store import Conflict, Store
from jarvis_home.web import create_app


def uid():
    return uuid4().hex


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'private')


def expense(amount='38', **kw):
    return Change(action='expense', name='午饭', amount=amount, category='餐饮', **kw)


def test_purchase_and_expense_atomic_undo(store):
    result = command(store, uid(), '买了三个番茄、一盒牛奶，花了15元')
    assert len(result['records']) == 3
    assert store.snapshot()['net_spend_cents'] == 1500
    assert len(store.snapshot()['items']) == 2
    command(store, uid(), '撤销')
    assert store.snapshot()['items'] == []
    assert store.snapshot()['net_spend_cents'] == 0


def test_restart_encryption_and_key(store):
    store.execute(uid(), [expense('38.10')], text='敏感午饭')
    assert b'38.10' not in store.path.read_bytes()
    assert '敏感午饭'.encode() not in store.path.read_bytes()
    assert '午饭'.encode() not in store.path.read_bytes()
    again = Store(store.directory)
    assert again.snapshot()['net_spend_cents'] == 3810
    assert (store.directory / 'key').stat().st_mode & 0o777 == 0o600
    encrypted = store.pack('a', {'name':'secret'})
    with pytest.raises(InvalidTag):
        store.unpack('b', encrypted)


def test_missing_key_does_not_replace(store):
    (store.directory / 'key').rename(store.directory / 'key.backup')
    with pytest.raises(ValueError, match='密钥缺失'):
        Store(store.directory)
    assert not (store.directory / 'key').exists()


def test_idempotency_concurrent(store):
    request_id = uid()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        out = list(pool.map(lambda _: store.execute(request_id, [expense()]), range(5)))
    assert sum(not o['replayed'] for o in out) == 1
    assert store.snapshot()['net_spend_cents'] == 3800
    with pytest.raises(Conflict):
        store.execute(request_id, [expense('45')])


def test_transaction_rolls_back(store):
    with pytest.raises(ValueError):
        store.execute(uid(), [expense(), Change(action='add_item', name='番茄')])
    assert store.snapshot()['net_spend_cents'] == 0
    assert store.history() == []


def test_unknown_composite_becomes_draft_without_partial_writes(store):
    result = command(store, uid(), '午饭38，关闭客厅灯')
    assert result['status'] == 'draft'
    assert store.snapshot()['net_spend_cents'] == 0
    assert len(store.history()) == 1


@pytest.mark.parametrize('phrase', ['午饭两百多', '打开门锁', '给猫出粮', '买了两盒药品', '午饭38元又83元', ''])
def test_unsupported_inputs_never_create_records(store, phrase):
    command(store, uid(), phrase)
    assert store.snapshot()['entries'] == []
    assert store.snapshot()['items'] == []


def test_money_types_and_precision(store):
    store.execute(uid(), [expense('0.10'), expense('0.20'), expense('20',kind='转账'), expense('100',kind='收入'), expense('0.05',kind='退款')])
    assert store.snapshot()['net_spend_cents'] == 25
    assert store.snapshot()['totals_cents']['收入'] == 10000
    for amount in ['NaN', 'Infinity', '-1', '0', '1.001']:
        with pytest.raises(ValueError):
            expense(amount)


def test_consume_version_and_undo_chain(store):
    added = store.execute(uid(), [Change(action='add_item',name='番茄',quantity=3,unit='个',location='冷藏')])['records'][0]
    take = Change(action='consume',name='番茄',record_id=added['id'],expected_version=1,quantity=2,unit='个')
    store.execute(uid(), [take])
    with pytest.raises(Conflict):
        store.execute(uid(), [take])
    store.execute(uid(), undo=True)
    assert store.snapshot()['items'][0]['quantity'] == '3'
    store.execute(uid(), undo=True)
    assert store.snapshot()['items'] == []
    with pytest.raises(Conflict):
        store.execute(uid(), undo=True)


def test_no_negative_quantity_or_unit_conversion(store):
    store.execute(uid(), [Change(action='add_item',name='菠菜',quantity=1,unit='把',location='冷藏')])
    for q,u,exc in [(2,'把',Conflict),(1,'克',ValueError)]:
        with pytest.raises(exc):
            store.execute(uid(), [Change(action='consume',name='菠菜',quantity=q,unit=u,expected_version=1)])
    assert store.snapshot()['items'][0]['quantity'] == '1'


def test_ambiguous_same_name_does_not_consume(store):
    item = Change(action='add_item',name='番茄',quantity=1,unit='个',location='冷藏')
    store.execute(uid(), [item,item])
    with pytest.raises(Conflict):
        store.execute(uid(), [Change(action='consume',name='番茄',quantity=1,unit='个',expected_version=1)])


def test_expense_correction_and_undo(store):
    item=store.execute(uid(),[expense()])['records'][0]
    store.execute(uid(),[Change(action='update',name='午饭',record_id=item['id'],expected_version=1,amount='45')])
    assert store.snapshot()['net_spend_cents']==4500
    store.execute(uid(),undo=True)
    assert store.snapshot()['net_spend_cents']==3800


def test_fridge_query_does_not_include_documents(store):
    command(store,uid(),'护照放在书房第二个抽屉')
    command(store,uid(),'买了两个番茄')
    result=command(store,uid(),'冰箱里有什么')
    assert '护照' not in result['message'] and '番茄' in result['message']
    assert result['model_calls']==0
    assert store.snapshot()['items'][0]['due'] is None


def test_yesterday_and_multi_expense(store):
    result=command(store,uid(),'昨天早饭12，打车25，猫粮189，微信')
    assert result['status']=='completed'
    assert sum(r['cents'] for r in result['records'])==22600
    assert all(r['payment']=='微信' for r in result['records'])
    assert all(r['on'] < str(today()) for r in result['records'])


def test_web_csrf_hosts_and_xss_rendering(tmp_path):
    app=create_app(tmp_path/'web')
    with TestClient(app,base_url='http://127.0.0.1:18600') as c:
        page=c.get('/')
        assert page.status_code==200
        token=page.text.split('name="home-token" content="')[1].split('"')[0]
        body={'request_id':uid(),'text':'午饭38'}
        assert c.post('/api/command',json=body).status_code==403
        assert c.post('/api/command',json=body,headers={'Origin':'https://evil.example','X-Home-Token':token}).status_code==403
        assert c.get('/',headers={'Host':'evil.example'}).status_code==403
        good={'Origin':'http://127.0.0.1:18600','X-Home-Token':token}
        assert c.post('/api/command',json=body,headers=good).status_code==200
        assert c.post('/api/command',json=body,headers=good).json()['replayed'] is True
        assert c.get('/api/state').json()['net_spend_cents']==3800
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        assert 'innerHTML' not in c.get('/app.js').text


def test_month_validation_and_private_directory(store,tmp_path):
    with pytest.raises(ValueError):
        store.snapshot('2026-13')
    shared=tmp_path/'shared'
    shared.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        Store(shared)


def test_consumption_response_loss_replays_without_decrement(store):
    command(store,uid(),'买了三个番茄')
    request_id=uid()
    command(store,request_id,'拿了两个番茄')
    assert command(store,request_id,'拿了两个番茄')['replayed']
    assert store.snapshot()['items'][0]['quantity']=='1'


@pytest.mark.parametrize('value', ['一二', '二三', '零百', '一一'])
def test_malformed_spoken_numbers_are_not_guessed(store,value):
    assert command(store,uid(),f'买了{value}个番茄')['status']=='draft'
    assert store.snapshot()['items']==[]
