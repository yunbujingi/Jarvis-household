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


def test_restore_replay_checksum_and_missing_key(tmp_path):
    from jarvis_home.backup import restore
    store=Store(tmp_path/'source')
    changes=[{'action':'add_item','name':'测试备份','quantity':2,'unit':'盒','location':'测试柜'}]
    first=store.execute('test-restore-add',changes)
    backup(store.directory,tmp_path/'backup')
    restore(tmp_path/'backup',tmp_path/'restored')
    recovered=Store(tmp_path/'restored')
    assert recovered.history()==store.history()
    assert recovered.execute('test-restore-add',changes)=={**first,'replayed':True}
    recovered.execute('test-restore-undo',undo=True)
    assert recovered.snapshot()['items']==[]
    assert len(store.snapshot()['items'])==1
    with pytest.raises(FileExistsError):
        restore(tmp_path/'backup',tmp_path/'restored')
    (tmp_path/'backup'/'key').write_bytes(b'x'*32)
    with pytest.raises(ValueError,match='checksum'):
        restore(tmp_path/'backup',tmp_path/'bad-restored')
    assert not (tmp_path/'bad-restored').exists()


def test_backup_checks_audit_beyond_recent_page(tmp_path):
    from cryptography.exceptions import InvalidTag
    store=Store(tmp_path/'source')
    for index in range(32):
        store.execute(f'test-long-audit-{index}',[{'action':'expense','name':'测试审计','amount':1}])
    with store.connect() as db:
        payload=db.execute('SELECT payload FROM operations WHERE seq=1').fetchone()[0]
        db.execute('UPDATE operations SET payload=? WHERE seq=1',(payload[:-1]+bytes([payload[-1]^1]),))
    assert len(store.history())==30  # recent page alone would miss the corrupt oldest entry
    with pytest.raises(InvalidTag):
        backup(store.directory,tmp_path/'failed-test-backup')
    assert not (tmp_path/'failed-test-backup'/'backup.json').exists()
