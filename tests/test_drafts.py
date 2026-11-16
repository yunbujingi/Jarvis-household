"""Synthetic draft lifecycle tests; no household data or external service."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from jarvis_home.backup import backup, restore
from jarvis_home.models import Change
from jarvis_home.router import command
from jarvis_home.store import Conflict, Store


def item(name="测试草稿物品"):
    return Change(action="add_item", name=name, quantity=2, unit="盒", location="测试柜")


def test_legacy_draft_projection_completion_replay_and_undo(tmp_path):
    store = Store(tmp_path / "test-ledger")
    result = command(store, "test-draft-original", "测试物品数量位置未说明")
    assert result["status"] == "draft" and not store.snapshot()["items"]
    # 0.3 drafts have no state rows and only an encrypted operation payload.
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 0
    draft = store.drafts()["records"][0]
    assert draft["draft_id"] == "test-draft-original" and draft["version"] == 1
    args = dict(draft_id=draft["draft_id"], expected_draft_version=1)
    completed = store.execute("test-draft-complete", [item()], **args)
    assert completed["draft"]["state"] == "completed"
    assert len(completed["records"]) == 1
    assert store.snapshot()["items"][0]["due"] is None
    assert store.drafts()["draft_count"] == 0
    # First response lost: reopen the actual database and retry the same request.
    reopened = Store(tmp_path / "test-ledger")
    assert reopened.execute("test-draft-complete", [item()], **args) == {**completed, "replayed": True}
    assert len(reopened.snapshot()["items"]) == 1
    with pytest.raises(Conflict):
        reopened.execute("test-draft-new-id", [item()], **args)
    reopened.execute("test-draft-undo", undo=True)
    assert reopened.snapshot()["items"] == []
    assert reopened.drafts()["records"][0]["version"] == 3
    assert reopened.execute("test-draft-complete", [item()], **args)["replayed"]
    assert reopened.snapshot()["items"] == []  # replay is historical, not re-execution
    with pytest.raises(Conflict):
        reopened.execute("test-stale-after-undo", [item()], **args)
    reopened.execute("test-draft-complete-again", [item()], draft_id=draft["draft_id"], expected_draft_version=3)
    assert len(reopened.snapshot()["items"]) == 1


def test_cancel_is_versioned_reversible_and_not_a_business_record(tmp_path):
    store = Store(tmp_path / "test-ledger")
    store.execute("test-save-draft", text="测试未完成记录", draft=True)
    result = store.execute("test-cancel-draft", draft_id="test-save-draft", expected_draft_version=1, cancel_draft=True)
    assert result["records"] == [] and result["draft"]["state"] == "cancelled"
    assert store.drafts()["draft_count"] == 0
    assert store.drafts("cancelled")["draft_count"] == 1
    assert store.snapshot()["items"] == [] and store.snapshot()["entries"] == []
    assert store.execute("test-cancel-draft", draft_id="test-save-draft", expected_draft_version=1, cancel_draft=True)["replayed"]
    store.execute("test-undo-cancel", undo=True)
    assert store.drafts()["records"][0]["version"] == 3


@pytest.mark.parametrize("kwargs", [
    {"draft_id": "missing-draft", "expected_draft_version": 1},
    {"draft_id": "test-save-draft"},
    {"draft_id": "test-save-draft", "expected_draft_version": 0},
    {"draft_id": "test-save-draft", "expected_draft_version": True},
    {"draft_id": "test-save-draft", "expected_draft_version": 1, "cancel_draft": True},
    {"expected_draft_version": 1}, {"cancel_draft": True},
    {"draft": True, "text": "测试混用"},
    {"draft_id": "test-save-draft", "expected_draft_version": 1, "undo": True},
])
def test_invalid_resolution_does_not_change_draft_or_inventory(tmp_path, kwargs):
    store = Store(tmp_path / "test-ledger")
    store.execute("test-save-draft", text="测试未完成记录", draft=True)
    with pytest.raises(ValueError):
        store.execute("test-invalid-resolution", [item()], **kwargs)
    assert len(store.history()) == 1 and store.drafts()["records"][0]["version"] == 1
    assert store.snapshot()["items"] == []


def test_ambiguous_composite_and_failed_resolution_are_atomic(tmp_path):
    store = Store(tmp_path / "test-ledger")
    command(store, "test-ambiguous-source", "午饭38，测试不明确输入")
    assert store.snapshot()["entries"] == []
    store.execute("test-batches-add", [item("测试同名物品"), item("测试同名物品")])
    args = dict(draft_id="test-ambiguous-source", expected_draft_version=1)
    with pytest.raises(Conflict):
        store.execute("test-failed-complete", [item(), Change(action="consume", name="测试同名物品",
            quantity=1, unit="盒", expected_version=1)], **args)
    assert len(store.snapshot()["items"]) == 2 and store.drafts()["draft_count"] == 1
    assert len(store.history()) == 2
    with pytest.raises(Conflict):
        store.execute("test-not-a-draft", [item()], draft_id="test-batches-add", expected_draft_version=1)


def test_two_clients_cannot_complete_one_draft_twice(tmp_path):
    store = Store(tmp_path / "test-ledger")
    store.execute("test-concurrent-source", text="测试并发草稿", draft=True)
    def complete(index):
        try:
            return store.execute(f"test-concurrent-{index}", [item()], draft_id="test-concurrent-source", expected_draft_version=1)["status"]
        except Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(complete, [1, 2])) == ["completed", "conflict"]
    assert len(store.snapshot()["items"]) == 1


def test_backup_restore_preserves_draft_audit_replay_undo(tmp_path):
    store = Store(tmp_path / "test-ledger")
    store.execute("test-restore-source", text="测试恢复草稿", draft=True)
    args = dict(draft_id="test-restore-source", expected_draft_version=1)
    store.execute("test-restore-complete", [item()], **args)
    backup(store.directory, tmp_path / "backup")
    restore(tmp_path / "backup", tmp_path / "restored")
    recovered = Store(tmp_path / "restored")
    assert recovered.history() == store.history()
    assert recovered.drafts("all") == store.drafts("all")
    assert recovered.execute("test-restore-complete", [item()], **args)["replayed"]
    recovered.execute("test-restore-undo", undo=True)
    assert recovered.drafts()["draft_count"] == 1 and recovered.snapshot()["items"] == []
    assert len(store.snapshot()["items"]) == 1
    with recovered.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


def test_pagination_empty_input_collision_and_state_protection(tmp_path):
    store = Store(tmp_path / "test-ledger")
    for i in range(3):
        store.execute(f"test-page-{i}", text=f"测试草稿{i}", draft=True)
    page = store.drafts(limit=2)
    assert page["draft_count"] == 3 and page["has_more"]
    assert store.drafts(offset=2, limit=2)["records"][0]["text"] == "测试草稿0"
    with pytest.raises(ValueError):
        store.execute("test-blank-source", text=" ", draft=True)
    with pytest.raises(Conflict):
        store.execute("test-page-0", text="测试另一个内容", draft=True)
    with pytest.raises(ValueError):
        store.drafts("unknown")
    with pytest.raises(ValueError):
        store.drafts(limit=31)
    store.execute("test-protect-cancel", draft_id="test-page-0", expected_draft_version=1, cancel_draft=True)
    with store.connect() as db:
        state = next(r for r in store.records(db).values() if r["type"] == "draft")
    with pytest.raises(Conflict):
        store.execute("test-state-update", [Change(action="update", name="待补全记录", record_id=state["id"], expected_version=2, location="测试位置")])
    # Draft text and state stay encrypted at rest.
    assert "测试草稿".encode() not in Path(store.path).read_bytes()


def test_actual_030_encrypted_fixture_is_readable_and_replayable(tmp_path):
    import json
    fixture = json.loads((Path(__file__).parent / 'fixtures' / 'legacy-draft-0.3.0.json').read_text())
    directory = tmp_path / 'test-legacy-ledger'
    directory.mkdir(mode=0o700)
    key = directory / 'key'
    key.write_bytes(bytes.fromhex(fixture['key']))
    key.chmod(0o600)
    store = Store(directory)
    with store.connect() as db:
        for table, rows in fixture['rows'].items():
            for row in rows:
                row[-1] = bytes.fromhex(row[-1])
                db.execute('INSERT OR REPLACE INTO '+table+' VALUES ('+','.join('?' for _ in row)+')', row)
    draft = store.drafts()['records'][0]
    assert draft['draft_id'] == 'test-legacy-draft-030' and draft['version'] == 1
    old_result = store.execute('test-legacy-draft-030', text='测试旧版草稿，数量位置待补全', draft=True)
    assert old_result['replayed'] and old_result['status'] == 'draft'
    store.execute('test-legacy-resolve', [item()], draft_id=draft['draft_id'], expected_draft_version=1)
    store.execute('test-legacy-undo', undo=True)
    assert store.drafts()['records'][0]['version'] == 3
    assert store.snapshot()['items'] == []
