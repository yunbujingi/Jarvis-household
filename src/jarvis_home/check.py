"""Installed-package acceptance with synthetic data; no endpoint or network."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .backup import backup, restore
from .store import Store


async def check(directory):
    directory = Path(directory)
    ledger = directory / "ledger"
    env = {"PATH": os.defpath, "JWS_DATA_DIR": str(ledger), "PYTHONDONTWRITEBYTECODE": "1"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "jarvis_home.mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            assert {t.name for t in (await client.list_tools()).tools} == {"household_query", "household_record", "household_undo"}

            async def call(name, arguments):
                result = await client.call_tool(name, arguments)
                assert not result.isError
                return json.loads(result.content[0].text)

            add = {"request_id": "test-check-add", "changes": [{"action": "add_item", "name": "测试物品",
                   "quantity": 3, "unit": "盒", "location": "测试抽屉", "due": "2030-01-01"}]}
            record = (await call("household_record", add))["records"][0]
            correction = {"request_id": "test-check-edit", "changes": [{"action": "update", "name": record["name"],
                          "record_id": record["id"], "expected_version": 1, "new_name": "测试物品纠错",
                          "location": "测试柜", "clear_due": True, "set_quantity": 2, "unit": "盒"}]}
            await call("household_record", correction)
            assert (await call("household_record", correction))["replayed"]
            rows = await call("household_query", {"scope": "items", "expiry": "unset"})
            assert rows["records"][0]["quantity"] == "2" and rows["records"][0]["location"] == "测试柜"
            await call("household_record", {"request_id": "test-check-draft", "draft_text": "测试物品待补全"})
            drafts = await call("household_query", {"scope": "drafts"})
            draft = drafts["records"][0]
            complete = {"request_id": "test-check-complete", "draft_id": draft["draft_id"],
                        "expected_draft_version": 1, "changes": [{"action": "add_item", "name": "测试补全物品",
                        "quantity": 1, "unit": "件", "location": "测试抽屉"}]}
            await call("household_record", complete)
            assert (await call("household_record", complete))["replayed"]
            await call("household_undo", {"request_id": "test-check-complete-undo"})
            assert (await call("household_query", {"scope": "drafts"}))["records"][0]["version"] == 3
    original = Store(ledger)
    backup(ledger, directory / "backup")
    restore(directory / "backup", directory / "restored")
    recovered = Store(directory / "restored")
    assert recovered.snapshot() == original.snapshot()
    assert recovered.history() == original.history()
    assert recovered.drafts() == original.drafts()
    assert recovered.execute(**correction)["replayed"]
    recovered.execute("test-check-undo", undo=True)
    result = recovered.snapshot()["items"][0]
    assert result["name"] == "测试物品" and result["quantity"] == "3" and result["due"] == "2030-01-01"
    assert original.snapshot()["items"][0]["quantity"] == "2"
    return {"installed_package": "passed", "stdio": "passed", "restore_audit_replay_undo": "passed", "draft_completion": "passed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, help="Parent for an exclusively owned temporary test directory")
    args = parser.parse_args()
    # This process owns every fixture; TemporaryDirectory only cleans its own directory.
    with TemporaryDirectory(prefix="jws-check-", dir=args.parent) as directory:
        print(json.dumps(asyncio.run(asyncio.wait_for(check(directory), 45))))


if __name__ == "__main__":
    main()
