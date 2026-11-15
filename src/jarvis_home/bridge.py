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
from uuid import uuid4
from urllib.parse import parse_qsl, urlsplit

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

MAX_BYTES = 262144
CALL_TIMEOUT = 20
IO_TIMEOUT = 5
DEADLINE_INTERVAL = 0.25
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


class ChildExited(RuntimeError):
    """Recoverable subprocess failure; never contains child output."""


def diagnostic(event, **fields):
    # Callers supply only fixed categories, local random IDs and numeric metrics.
    print(json.dumps({"event": event, **fields}), flush=True)


def status(phase):
    path = Path(os.environ.get("JWS_STATUS_FILE", "/tmp/jws-status.json"))
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps({"phase": phase, "updated_at": time.time()}))
    temp.replace(path)
    diagnostic("household_bridge", phase=phase)


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

    def finish(request_id, outcome):
        entry = pending.pop(request_id, None)
        if entry and entry["tool"]:
            diagnostic("tool_call", call_id=entry["trace"], tool=entry["tool"],
                       elapsed_ms=round((time.monotonic() - entry["started"]) * 1000, 2),
                       outcome=outcome)


    async def incoming():
        async for raw in ws:
            msg = decode_message(raw)
            method = msg.get("method")
            request_id = msg.get("id")
            if request_id is not None and (type(request_id) not in (str, int) or len(str(request_id)) > 128):
                raise ValueError("invalid_id")
            if method == "notifications/cancelled":
                cancelled_id = msg.get("params", {}).get("requestId")
                if type(cancelled_id) not in (str, int):
                    raise ValueError("invalid_cancel_id")
                finish(cancelled_id, "cancelled_unknown")
            if method and request_id is not None:
                if request_id in pending or len(pending) >= 16:
                    raise ValueError("too_many_requests")
                tool = msg.get("params", {}).get("name") if method == "tools/call" else None
                pending[request_id] = {"started": time.monotonic(), "trace": uuid4().hex,
                                       "tool": tool if tool in TOOLS else None}
                if method == "initialize":
                    initialized.add(request_id)
            if method == "tools/call" and msg.get("params", {}).get("name") not in TOOLS:
                raise ValueError("tool_not_allowed")
            child.stdin.write((raw + "\n").encode())
            await asyncio.wait_for(child.stdin.drain(), IO_TIMEOUT)

    async def outgoing():
        while line := await child.stdout.readline():
            msg = decode_message(line.decode())
            await asyncio.wait_for(ws.send(line.decode().rstrip("\n")), IO_TIMEOUT)
            request_id = msg.get("id")
            if request_id in pending and ("result" in msg or "error" in msg):
                outcome = "error" if "error" in msg or msg.get("result", {}).get("isError") else "success"
                finish(request_id, outcome)
                if request_id in initialized:
                    initialized.remove(request_id)
                    if "result" in msg:
                        status("ready")
        raise ChildExited("child_exited")

    async def deadlines():
        while True:
            await asyncio.sleep(DEADLINE_INTERVAL)
            expired = [key for key, entry in pending.items() if time.monotonic() - entry["started"] > CALL_TIMEOUT]
            if expired:
                for key in expired:
                    finish(key, "timeout_unknown")
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
        for key in list(pending):
            finish(key, "interrupted_unknown")


async def stop_child(child):
    if child.returncode is None:
        try:
            child.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(child.wait(), 3)
        except TimeoutError:
            child.kill()
            await child.wait()


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
            await stop_child(child)


async def run():
    attempt = 0
    status("starting")
    while True:
        if not endpoint_path().exists():
            status("awaiting_configuration")
            await asyncio.sleep(10)
            continue
        try:
            endpoint = read_endpoint(endpoint_path())
        except (ValueError, OSError):
            status("configuration_error")
            return
        started = time.monotonic()
        try:
            await session(endpoint)
        except asyncio.CancelledError:
            raise
        except ChildExited:
            diagnostic("transport_failure", category="child_exited")
        except TimeoutError:
            diagnostic("transport_failure", category="timeout")
        except (ssl.SSLCertVerificationError, ValueError):
            status("protocol_or_tls_error")
            return
        except InvalidStatus as exc:
            if exc.response.status_code in (400, 401, 403, 404):
                status("authentication_rejected")
                return
        except Exception:
            diagnostic("transport_failure", category="connection_lost")
        attempt = 0 if time.monotonic() - started > 60 else min(attempt + 1, 6)
        status("reconnecting")
        delay = min(60, 2 ** attempt) + random.random()
        diagnostic("retry", attempt=attempt, delay_seconds=round(delay, 2))
        await asyncio.sleep(delay)


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
