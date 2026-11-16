import asyncio
import json
import sys
from unittest.mock import patch

import pytest
from jarvis_home import bridge


@pytest.mark.parametrize("endpoint", ["ws://api.xiaozhi.me/mcp/?token=x", "wss://evil.test/mcp/?token=x", "wss://api.xiaozhi.me/mcp/?token=", "wss://api.xiaozhi.me/mcp/?token=x&token=y", "wss://api.xiaozhi.me/mcp/?token=x#fragment", "wss://api.xiaozhi.me/mcp/?token=%0A", "wss://user@api.xiaozhi.me/mcp/?token=x"])
def test_endpoint_rejects_unapproved_destination(endpoint):
    with pytest.raises(ValueError, match="invalid_official_endpoint"):
        bridge.validate_endpoint(endpoint)


def test_endpoint_permissions(tmp_path):
    path=tmp_path/'endpoint'
    path.write_text('wss://api.xiaozhi.me/mcp/?token=test-only')
    path.chmod(0o644)
    with pytest.raises(ValueError, match="unsafe_endpoint_file"):
        bridge.read_endpoint(path)
    path.chmod(0o600)
    assert bridge.read_endpoint(path).endswith('test-only')
    link=tmp_path/'link'; link.symlink_to(path)
    with pytest.raises(ValueError):
        bridge.read_endpoint(link)


def test_message_bounds():
    for raw in ['[]', '{}', 'null', '{"jsonrpc":"2.0","x":"'+'x'*bridge.MAX_BYTES+'"}', b'{}']:
        with pytest.raises(ValueError):
            bridge.decode_message(raw)


def test_real_child_through_websocket_relay(tmp_path):
    async def run():
        import os
        class Websocket:
            def __init__(self):
                self.input=asyncio.Queue();self.output=asyncio.Queue()
            def __aiter__(self):return self
            async def __anext__(self):return await self.input.get()
            async def send(self,value):await self.output.put(json.loads(value))
        ws=Websocket()
        child=await asyncio.create_subprocess_exec(sys.executable,'-m','jarvis_home.mcp',env={**os.environ,'JWS_DATA_DIR':str(tmp_path/'ledger')},stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            with patch.object(bridge,'status') as status:
                task=asyncio.create_task(bridge.relay(ws,child))
                await ws.input.put(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test','version':'1'}}}))
                result=await asyncio.wait_for(ws.output.get(),5)
                assert 'result' in result
                status.assert_called_once_with('ready')
                await ws.input.put(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'}))
                await ws.input.put(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}))
                tools=await asyncio.wait_for(ws.output.get(),5)
                assert {t['name'] for t in tools['result']['tools']}==bridge.TOOLS
                await ws.input.put(json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'dispense_food','arguments':{}}}))
                with pytest.raises(ValueError,match='tool_not_allowed'):
                    await asyncio.wait_for(task,5)
        finally:
            child.terminate(); await child.wait()
    asyncio.run(run())


def test_configure_private_file_and_no_overwrite(tmp_path, monkeypatch):
    import os
    path=tmp_path/'test-config'/'endpoint'
    monkeypatch.setenv('JWS_ENDPOINT_FILE',str(path))
    monkeypatch.setattr(bridge.getpass,'getpass',lambda _: 'wss://api.xiaozhi.me/mcp/?token=test-only')
    old_mask=os.umask(0o077)
    try:
        bridge.configure()
        assert path.stat().st_mode & 0o777==0o600
        assert bridge.read_endpoint(path).endswith('test-only')
        with pytest.raises(SystemExit,match='endpoint_already_configured'):
            bridge.configure()
    finally:
        os.umask(old_mask)
