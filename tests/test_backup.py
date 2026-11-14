from jarvis_home.backup import backup
from jarvis_home.store import Store
import pytest


def test_backup_restores_contents_and_preserves_audit(tmp_path):
    store = Store(tmp_path / "source")
    store.execute("backup-test-1", [{"action": "expense", "name": "测试", "amount": "12.34"}])
    backup(store.directory, tmp_path / "backup")
    restored = Store(tmp_path / "backup")
    assert restored.snapshot() == store.snapshot()
    assert restored.history() == store.history()
    restored.execute("backup-test-2", undo=True)
    assert restored.snapshot()["net_spend_cents"] == 0
    assert store.snapshot()["net_spend_cents"] == 1234
    with pytest.raises(FileExistsError):
        backup(store.directory, tmp_path / "backup")
