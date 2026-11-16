import asyncio
import json
from unittest.mock import patch

import pytest

from jarvis_home import bridge
from jarvis_home.store import Store
from scripts.isolated_bridge import isolated_bridge


def test_response_loss_timeout_and_recovery(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('JWS_STATUS_FILE',str(tmp_path/'status.json'))
    async def run():
        directory=tmp_path/'test-ledger'
        args={'name':'household_record','arguments':{'request_id':'test-response-loss', 'changes':[
            {'action':'add_item','name':'测试私密内容不应出现在日志','quantity':2,'unit':'盒','location':'测试柜'}]}}
        async with isolated_bridge(directory,drop_id=2) as (request, ws, errors, children):
            with pytest.raises(Exception):
                await request(2,'tools/call',args)
            assert await asyncio.wait_for(errors.get(),5) is ConnectionError
        assert all(p.returncode is not None for p in children)
        assert len(Store(directory).snapshot()['items'])==1
        async with isolated_bridge(directory) as (request, ws, errors, children):
            result=await request(2,'tools/call',args)
            assert json.loads(result['result']['content'][0]['text'])['replayed']
        args['arguments']['request_id']='test-response-timeout'
        async with isolated_bridge(directory,delay_id=2) as (request, ws, errors, children):
            # Initialization completed before shortening only this synthetic call's deadline.
            with patch.object(bridge,'CALL_TIMEOUT',0.05), patch.object(bridge,'DEADLINE_INTERVAL',0.01):
                with pytest.raises(Exception):
                    await request(2,'tools/call',args)
                assert await asyncio.wait_for(errors.get(),5) is TimeoutError
        assert len(Store(directory).snapshot()['items'])==2  # timeout did NOT undo commit
        async with isolated_bridge(directory) as (request, ws, errors, children):
            result=await request(2,'tools/call',args)
            assert json.loads(result['result']['content'][0]['text'])['replayed']
        assert len(Store(directory).history())==2
    asyncio.run(run())
    log=capsys.readouterr().out
    assert '测试私密' not in log and 'test-response-loss' not in log
    events=[json.loads(line) for line in log.splitlines()]
    calls=[e for e in events if e['event']=='tool_call']
    assert {'success','timeout_unknown','interrupted_unknown'} <= {e['outcome'] for e in calls}
    assert all(len(e['call_id'])==32 and e['elapsed_ms']>=0 for e in calls)


def test_child_exit_and_connection_close_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv('JWS_STATUS_FILE',str(tmp_path/'status.json'))
    async def run():
        async with isolated_bridge(tmp_path/'test-ledger') as (request, ws, errors, children):
            children[0].kill()
            assert await asyncio.wait_for(errors.get(),5) is bridge.ChildExited
        assert children[0].returncode is not None
        async with isolated_bridge(tmp_path/'test-ledger') as (request, ws, errors, children):
            assert 'result' in await request(2,'tools/list',{})
            await ws.close()
        assert children[0].returncode is not None
    asyncio.run(run())


@pytest.mark.parametrize('cancel', [False, True])
def test_draft_response_loss_reconnect_replay_and_undo(tmp_path, monkeypatch, capsys, cancel):
    monkeypatch.setenv('JWS_STATUS_FILE', str(tmp_path/'status.json'))
    directory = tmp_path/'test-draft-ledger'
    store = Store(directory)
    store.execute('test-lost-draft-source', text='测试草稿私密原文', draft=True)
    args = {'name':'household_record', 'arguments':{
        'request_id':'test-lost-draft-resolution', 'draft_id':'test-lost-draft-source',
        'expected_draft_version':1, 'cancel_draft':cancel}}
    if not cancel:
        args['arguments']['changes'] = [{'action':'add_item', 'name':'测试草稿物品',
            'quantity':2, 'unit':'盒', 'location':'测试柜'}]

    async def run():
        async with isolated_bridge(directory, drop_id=2) as (request, _, errors, children):
            with pytest.raises(Exception):
                await request(2, 'tools/call', args)
            assert await asyncio.wait_for(errors.get(), 5) is ConnectionError
        assert all(p.returncode is not None for p in children)
        assert store.drafts()['draft_count'] == 0  # commit survived response loss
        async with isolated_bridge(directory) as (request, _, _, _):
            response = await request(2, 'tools/call', args)
            result = json.loads(response['result']['content'][0]['text'])
            assert result['replayed']
            assert result['draft']['state'] == ('cancelled' if cancel else 'completed')
            assert len(store.history()) == 2
            assert len(store.snapshot()['items']) == (0 if cancel else 1)
            response = await request(3, 'tools/call', {'name':'household_undo',
                'arguments':{'request_id':'test-lost-draft-undo'}})
            assert not response['result'].get('isError')
        assert store.drafts()['records'][0]['version'] == 3
        assert store.snapshot()['items'] == []
    asyncio.run(run())
    log = capsys.readouterr().out
    assert '测试草稿' not in log and 'test-lost-draft' not in log


def test_reconnect_classification_and_backoff(tmp_path, monkeypatch):
    endpoint=tmp_path/'endpoint'
    endpoint.write_text('wss://api.xiaozhi.me/mcp/?token=test-only')
    endpoint.chmod(0o600)
    monkeypatch.setenv('JWS_ENDPOINT_FILE',str(endpoint))
    phases=[]; delays=[]; attempts=[]
    async def session(_):
        attempts.append(1)
        if len(attempts)>4:
            raise asyncio.CancelledError
        raise bridge.ChildExited('synthetic test failure')
    async def sleep(delay):
        delays.append(delay)
    with patch.object(bridge,'session',session), patch.object(bridge,'status',phases.append), patch.object(bridge.asyncio,'sleep',sleep):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(bridge.run())
    assert phases[0]=='starting' and phases.count('reconnecting')==4
    assert all(2**(i+1)<=d<2**(i+1)+1 for i,d in enumerate(delays))


def test_cancel_cleans_pending_without_claiming_rollback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('JWS_STATUS_FILE',str(tmp_path/'status.json'))
    async def run():
        async with isolated_bridge(tmp_path/'test-cancel',delay_id=2) as (request,ws,errors,children):
            await ws.send(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'household_record','arguments':{
                'request_id':'test-cancel-write','changes':[{'action':'expense','name':'测试取消','amount':1}]}}}))
            # Wait for the actual commit before cancelling the delayed transport response.
            for _ in range(100):
                if Store(tmp_path/'test-cancel').history():
                    break
                await asyncio.sleep(.01)
            assert len(Store(tmp_path/'test-cancel').history())==1
            await ws.send(json.dumps({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':2}}))
            with patch.object(bridge,'CALL_TIMEOUT',.05), patch.object(bridge,'DEADLINE_INTERVAL',.01):
                await asyncio.sleep(.15)
                assert errors.empty()  # cancellation removed the deadline, not the committed transaction
            await ws.close()
        assert children[0].returncode is not None
    asyncio.run(run())
    assert 'cancelled_unknown' in capsys.readouterr().out
