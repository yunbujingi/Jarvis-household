"""Synthetic, serial warm-tool benchmark; excludes WAN, ASR, LLM and TTS."""
import argparse
import asyncio
from contextlib import redirect_stdout
import io
import json
import math
import platform
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from jarvis_home.mcp import create_server
from isolated_bridge import isolated_bridge


def summary(values):
    values=sorted(values)
    return {'samples':len(values),'p50_ms':round(values[math.ceil(len(values)*.5)-1],3),
            'p95_ms':round(values[math.ceil(len(values)*.95)-1],3)}


async def measure(directory, count):
    server=create_server(directory/'direct')
    args={'scope':'items','limit':3}
    direct=[]; relay=[]
    await server.call_tool('household_query',args)
    for _ in range(count):
        started=time.perf_counter()
        await server.call_tool('household_query',args)
        direct.append((time.perf_counter()-started)*1000)
    async with isolated_bridge(directory/'bridge') as (request, _, _, _):
        params={'name':'household_query','arguments':args}
        await request(2,'tools/call',params)
        for i in range(count):
            started=time.perf_counter()
            response=await request(i+3,'tools/call',params)
            assert not response['result'].get('isError')
            relay.append((time.perf_counter()-started)*1000)
    return {'environment':{'os':platform.system(),'architecture':platform.machine(),'python':platform.python_version()},
            'condition':'serial warm empty test ledger query, loopback WebSocket + stdio; no TLS/WAN/voice/model',
            'local_tool':summary(direct),'loopback_bridge':summary(relay)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',type=int,default=100)
    args=parser.parse_args()
    if not 10<=args.samples<=10000:
        parser.error('samples must be 10..10000')
    with TemporaryDirectory(prefix='jws-benchmark-') as directory:
        import os
        os.environ['JWS_STATUS_FILE']=str(Path(directory)/'status.json')
        with redirect_stdout(io.StringIO()):
            result=asyncio.run(measure(Path(directory),args.samples))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
