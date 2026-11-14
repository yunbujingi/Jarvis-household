"""Dedicated official Xiaozhi transport; no device tools or payload logging."""
import asyncio
import getpass
import json
import logging
import os
from pathlib import Path
import random
import signal
import ssl
import sys
import time
from urllib.parse import parse_qsl, urlsplit

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

MAX_BYTES = 262144
CALL_TIMEOUT = 20
TOOLS = frozenset({"household_query", "household_record", "household_undo"})
LOGGER = logging.getLogger("jws.transport")
LOGGER.handlers[:] = [logging.NullHandler()]
LOGGER.propagate = False
LOGGER.disabled = True


def validate_endpoint(value):
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 8192 or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
            raise ValueError
        url = urlsplit(value)
        query = parse_qsl(url.query, strict_parsing=True, keep_blank_values=True)
        if url.scheme != "wss" or url.netloc not in {"api.xiaozhi.me", "api.xiaozhi.me:443"} or url.path != "/mcp/" or url.fragment:
            raise ValueError
        if len(query) != 1 or query[0][0] != "token" or not query[0][1] or any(ord(c) <= 32 or ord(c) >= 127 for c in query[0][1]):
            raise ValueError
        return value
    except (TypeError, ValueError):
        raise ValueError("invalid_official_endpoint") from None


def endpoint_path():
    return Path(os.environ.get("JWS_ENDPOINT_FILE", "/data/endpoint"))


def read_endpoint(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
        raise ValueError("unsafe_endpoint_file")
    return validate_endpoint(path.read_text().strip())


def configure():
    """Only called interactively, never accepts a secret on the command line."""
    os.umask(0o077)
    path = endpoint_path()
    if path.exists() or path.is_symlink():
        raise SystemExit("endpoint_already_configured")
    value = validate_endpoint(getpass.getpass("官方小智 MCP 接入点（隐藏输入）: "))
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with path.open("x") as f:
        f.write(value)
        f.flush()
        os.fsync(f.fileno())
    print("endpoint_saved")


def status(phase):
    path = Path(os.environ.get("JWS_STATUS_FILE", "/tmp/jws-status.json"))
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps({"phase": phase, "updated_at": time.time()}))
    temp.replace(path)
    print(json.dumps({"event": "household_bridge", "phase": phase}), flush=True)


def decode_message(raw):
    if not isinstance(raw, str) or len(raw.encode()) > MAX_BYTES:
        raise ValueError("invalid_message")
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            raise ValueError
    except (ValueError, RecursionError):
        raise ValueError("invalid_message") from None
    return value


async def relay(ws, child):
    pending = {}
    initialized = set()

    async def incoming():
        async for raw in ws:
            msg = decode_message(raw)
            method = msg.get("method")
            request_id = msg.get("id")
            if request_id is not None and (type(request_id) not in (str, int) or len(str(request_id)) > 128):
                raise ValueError("invalid_id")
            if method and request_id is not None:
                if request_id in pending or len(pending) >= 16:
                    raise ValueError("too_many_requests")
                pending[request_id] = time.monotonic()
                if method == "initialize":
                    initialized.add(request_id)
            if method == "tools/call" and msg.get("params", {}).get("name") not in TOOLS:
                raise ValueError("tool_not_allowed")
            child.stdin.write((raw + "\n").encode())
            await asyncio.wait_for(child.stdin.drain(), 5)

    async def outgoing():
        while line := await child.stdout.readline():
            msg = decode_message(line.decode())
            await asyncio.wait_for(ws.send(line.decode().rstrip("\n")), 5)
            request_id = msg.get("id")
            if request_id in pending and ("result" in msg or "error" in msg):
                pending.pop(request_id)
                if request_id in initialized:
                    initialized.remove(request_id)
                    if "result" in msg:
                        status("ready")
        raise ValueError("child_exited")

    async def deadlines():
        while True:
            await asyncio.sleep(1)
            if any(time.monotonic() - started > CALL_TIMEOUT for started in pending.values()):
                raise TimeoutError("request_timeout")

    tasks = [asyncio.create_task(f()) for f in (incoming, outgoing, deadlines)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def session(endpoint):
    async with connect(endpoint, ssl=ssl.create_default_context(), logger=LOGGER,
                       open_timeout=10, close_timeout=3, ping_interval=20,
                       ping_timeout=20, max_size=MAX_BYTES, max_queue=8) as ws:
        status("connected")
        # The MCP child never receives the endpoint credential or host secrets.
        env = {"PATH": os.defpath, "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "JWS_DATA_DIR": os.environ.get("JWS_DATA_DIR", "/data/ledger")}
        child = await asyncio.create_subprocess_exec(sys.executable, "-m", "jarvis_home.mcp",
                    env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, limit=MAX_BYTES + 1)
        try:
            await relay(ws, child)
        finally:
            if child.returncode is None:
                child.terminate()
                try:
                    await asyncio.wait_for(child.wait(), 3)
                except TimeoutError:
                    child.kill()
                    await child.wait()


async def run():
    attempt = 0
    while True:
        if not endpoint_path().exists():
            status("awaiting_configuration")
            await asyncio.sleep(10)
            continue
        try:
            endpoint = read_endpoint(endpoint_path())
        except ValueError:
            status("configuration_rejected")
            return
        started = time.monotonic()
        try:
            await session(endpoint)
        except asyncio.CancelledError:
            raise
        except (ssl.SSLCertVerificationError, ValueError):
            status("protocol_or_tls_error")
            return
        except InvalidStatus as exc:
            if exc.response.status_code in (400, 401, 403, 404):
                status("authentication_rejected")
                return
        except Exception:
            pass  # Never log exceptions containing endpoint credentials or data.
        attempt = 0 if time.monotonic() - started > 60 else min(attempt + 1, 6)
        status("reconnecting")
        await asyncio.sleep(min(60, 2 ** attempt) + random.random())


async def managed_run():
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        await run()
        # Fatal configuration/auth errors stay stopped, even with restart policy.
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        status("stopped")


def main():
    os.umask(0o077)
    asyncio.run(managed_run())


if __name__ == "__main__":
    main()
