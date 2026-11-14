"""Single-owner encrypted records. SQLite transaction = one reversible command."""
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .models import Change, today


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.stat().st_mode & 0o077:
            raise ValueError("数据目录必须仅当前用户可访问（0700）")
        key_path = self.directory / "key"
        db_path = self.directory / "home.sqlite3"
        if key_path.is_symlink() or db_path.is_symlink():
            raise ValueError("数据文件不允许使用符号链接")
        if not key_path.exists():
            if db_path.exists():
                raise ValueError("数据库密钥缺失，停止而非生成新密钥")
            try:
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "wb") as f:
                    f.write(AESGCM.generate_key(bit_length=256))
                    f.flush()
                    os.fsync(f.fileno())
        if key_path.stat().st_mode & 0o077:
            raise ValueError("密钥权限必须为0600")
        self.key = key_path.read_bytes()
        self.cipher = AESGCM(self.key)
        self.path = db_path
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("不支持的数据库版本")
            db.executescript('''
                CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS operations(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS meta(id TEXT PRIMARY KEY, payload BLOB NOT NULL);
                PRAGMA user_version=1;
            ''')
            check = db.execute("SELECT payload FROM meta WHERE id='key-check'").fetchone()
            if check:
                self.unpack("meta:key-check", check[0])
            else:
                db.execute("INSERT INTO meta VALUES (?,?)", ("key-check", self.pack("meta:key-check", {"ok": True})))
        os.chmod(db_path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def pack(self, aad, value):
        nonce = os.urandom(12)
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        return nonce + self.cipher.encrypt(nonce, raw, aad.encode())

    def unpack(self, aad, value):
        return json.loads(self.cipher.decrypt(value[:12], value[12:], aad.encode()))

    def records(self, db):
        return {rid: self.unpack("record:" + rid, raw) for rid, raw in db.execute("SELECT id,payload FROM records")}

    def save(self, db, record):
        db.execute("INSERT OR REPLACE INTO records VALUES (?,?)", (record["id"], self.pack("record:" + record["id"], record)))

    def snapshot(self, month=None):
        month = month or today().strftime("%Y-%m")
        datetime.strptime(month + "-01", "%Y-%m-%d")
        with self.connect() as db:
            values = list(self.records(db).values())
        items = [r for r in values if r["type"] == "item" and not r.get("deleted")]
        entries = [r for r in values if r["type"] == "expense" and not r.get("deleted") and r["on"][:7] == month]
        totals = {k: 0 for k in ("支出", "收入", "转账", "退款")}
        categories = {}
        for r in entries:
            totals[r["kind"]] += r["cents"]
            if r["kind"] in ("支出", "退款"):
                categories[r["category"]] = categories.get(r["category"], 0) + r["cents"] * (-1 if r["kind"] == "退款" else 1)
        return {"items": items, "entries": entries, "month": month, "totals_cents": totals,
                "net_spend_cents": totals["支出"] - totals["退款"], "categories_cents": categories,
                "integrations": {"ha": "existing_bridge_not_connected_here", "petkit": "existing_bridge_not_connected_here"}}

    def execute(self, request_id, changes=(), *, text="", undo=False, draft=False):
        # IDs from every entry point share the same validation contract.
        from .models import Command
        Command(request_id=request_id, text=text or "structured")
        changes = [c if isinstance(c, Change) else Change.model_validate(c) for c in changes]
        if len(changes) > 20 or (undo and (changes or draft)):
            raise ValueError("每次最多20项；撤销不能与其他操作混用")
        body = {"changes": [c.model_dump(mode="json") for c in changes], "text": text, "undo": undo, "draft": draft}
        digest = hmac.new(self.key, json.dumps(body, sort_keys=True, ensure_ascii=False).encode(), hashlib.sha256).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT digest,payload FROM operations WHERE id=?", (request_id,)).fetchone()
            if previous:
                if previous[0] != digest:
                    raise Conflict("同一请求编号不能用于不同内容")
                return {**self.unpack("operation:" + request_id, previous[1])["result"], "replayed": True}
            records = self.records(db)
            before, after = {}, {}
            if undo:
                undone = set()
                target = None
                for rid, raw in db.execute("SELECT id,payload FROM operations ORDER BY seq DESC"):
                    op = self.unpack("operation:" + rid, raw)
                    if op.get("undo_of"):
                        undone.add(op["undo_of"])
                    elif op["after"] and rid not in undone:
                        target = (rid, op)
                        break
                if not target:
                    raise Conflict("没有可以撤销的记录")
                for rid, expected in target[1]["after"].items():
                    # Version increases on compensation; compare business content.
                    current = records[rid]
                    if {k:v for k,v in current.items() if k != "version"} != {k:v for k,v in expected.items() if k != "version"}:
                        raise Conflict("记录已变化，无法覆盖撤销")
                    before[rid] = current
                    old = target[1]["before"][rid]
                    after[rid] = {**(old or current), "version": current["version"] + 1}
                    if old is None:
                        after[rid]["deleted"] = True
                message = "已撤销上一笔记录。"
            elif draft:
                target = None
                message = "这句话暂未写入库存或账目，已保留草稿。请按示例补充数量、金额或位置。"
            else:
                target = None
                if not changes:
                    raise ValueError("没有可执行的记录")
                for change in changes:
                    if change.action in ("add_item", "expense"):
                        rid = uuid4().hex
                        record = {"id": rid, "name": change.name, "version": 1, "on": str(change.on), "deleted": False}
                        if change.action == "add_item":
                            if change.quantity is None or not change.unit or not change.location:
                                raise ValueError("入库需要数量、单位、位置")
                            record.update(type="item", quantity=str(change.quantity), unit=change.unit, location=change.location,
                                          due=str(change.due) if change.due else None, due_source="user" if change.due else "unset")
                        else:
                            if change.amount is None:
                                raise ValueError("记账需要明确金额")
                            record.update(type="expense", cents=int(change.amount * 100), kind=change.kind,
                                          category=change.category, payment=change.payment)
                        before[rid] = None
                    else:
                        matches = [r for r in records.values() if not r.get("deleted") and
                                   (r["id"] == change.record_id if change.record_id else r["name"] == change.name)]
                        if len(matches) != 1:
                            raise Conflict("没有唯一匹配记录，请指定记录编号")
                        old = matches[0]
                        rid = old["id"]
                        if change.expected_version is None or change.expected_version != old["version"]:
                            raise Conflict("记录版本已变化，请刷新后重试")
                        before.setdefault(rid, old.copy())
                        record = {**old, "version": old["version"] + 1}
                        if change.action == "consume":
                            if old["type"] != "item" or change.quantity is None or change.unit != old["unit"]:
                                raise ValueError("取用需要同单位的明确数量")
                            remaining = Decimal(old["quantity"]) - change.quantity
                            if remaining < 0:
                                raise Conflict("取用数量超过库存")
                            record["quantity"] = str(remaining)
                            record["deleted"] = remaining == 0
                        elif old["type"] == "expense":
                            if change.amount is None:
                                raise ValueError("修改账目需提供金额")
                            record["cents"] = int(change.amount * 100)
                        else:
                            if change.location is None:
                                raise ValueError("修改物品需提供位置")
                            record["location"] = change.location
                    records[rid] = record
                    after[rid] = record.copy()
                notes = []
                item_count = sum(c.action == "add_item" for c in changes)
                if item_count:
                    notes.append(f"已记录 {item_count} 项物品")
                for kind in ("支出", "收入", "转账", "退款"):
                    amounts = [c.amount for c in changes if c.action == "expense" and c.kind == kind]
                    if amounts:
                        notes.append(f"已记{kind} {sum(amounts, Decimal(0)):.2f} 元")
                if any(c.action == "consume" for c in changes):
                    notes.append("已扣减取用数量")
                if any(c.action == "update" for c in changes):
                    notes.append("已修改记录")
                message = "，".join(notes) + "。"
            for record in after.values():
                self.save(db, record)
            result = {"request_id": request_id, "status": "draft" if draft else "completed", "message": message,
                      "records": list(after.values()), "replayed": False}
            op = {"input": body, "before": before, "after": after, "undo_of": target[0] if target else None,
                  "result": result, "at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()}
            db.execute("INSERT INTO operations(id,digest,payload) VALUES (?,?,?)", (request_id, digest, self.pack("operation:" + request_id, op)))
            return result

    def history(self):
        with self.connect() as db:
            return [self.unpack("operation:" + rid, raw) for rid, raw in db.execute("SELECT id,payload FROM operations ORDER BY seq DESC LIMIT 30")]

    def replay_text(self, request_id, text):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM operations WHERE id=?", (request_id,)).fetchone()
        if row:
            op = self.unpack("operation:" + request_id, row[0])
            if op["input"]["text"] != text:
                raise Conflict("同一请求编号不能用于不同内容")
            return {**op["result"], "replayed": True}
        return None
