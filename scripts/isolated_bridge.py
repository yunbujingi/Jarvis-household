"""Loopback WebSocket -> real relay -> real stdio MCP. Test/benchmark only."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import sys

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from jarvis_home import bridge


@asynccontextmanager
async def isolated_bridge(directory, *, drop_id=None, delay_id=None):
    errors = asyncio.Queue()
    children = []

    async def handle(ws):
        child = await asyncio.create_subprocess_exec(sys.executable, '-m', 'jarvis_home.mcp',
            env={'PATH':os.defpath, 'JWS_DATA_DIR':str(directory), 'PYTHONDONTWRITEBYTECODE':'1'},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=bridge.MAX_BYTES + 1)
        children.append(child)

        class Transport:
            def __aiter__(self):
                return ws.__aiter__()

            async def send(self, raw):
                if json.loads(raw).get('id') == drop_id:
                    raise ConnectionError('test response loss')
                if json.loads(raw).get('id') == delay_id:
                    await asyncio.sleep(2)
                await ws.send(raw)
        try:
            await bridge.relay(Transport(), child)
        except Exception as exc:
            await errors.put(type(exc))
        finally:
            await bridge.stop_child(child)
            await ws.close()

    async with serve(handle, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with connect(f'ws://127.0.0.1:{port}', open_timeout=5) as ws:
            async def request(identifier, method, params):
                await ws.send(json.dumps({'jsonrpc':'2.0','id':identifier,'method':method,'params':params}))
                return json.loads(await asyncio.wait_for(ws.recv(), 5))
            await request(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test-isolated','version':'1'}})
            await ws.send(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'}))
            yield request, ws, errors, children
