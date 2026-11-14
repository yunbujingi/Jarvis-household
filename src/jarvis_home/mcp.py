"""Private stdio tool service; no outbound connection until explicitly deployed."""
import os
from pathlib import Path
from typing import Literal
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from .models import Change
from .inventory import query_items
from .store import Store


def create_server(directory):
    store = Store(Path(directory))
    server = FastMCP("家庭账本")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def household_query(month: str | None = None, scope: Literal["overview", "items", "expenses"] = "overview", offset: int = 0, limit: int = 20,
                        name: str | None = None, location: str | None = None,
                        expiry: Literal["all", "overdue", "today", "within_days", "unset"] = "all", days: int = 7) -> dict:
        """查询家庭账本。物品在哪/剩余/何时到期用scope=items，可按name和location子串筛选；同名多批分别回答。
        expiry: all全部、overdue早于今天、today今天到期、within_days今天至days天后含边界、unset未填到期日。
        临期查询用within_days，默认7天；已超期另用overdue。日期和剩余天数由服务端按北京时间计算；未知不等于未到期。
        语音一般limit=3，简短回答所问字段；has_more为真不能把当前页当全部。日期仅用户记录，不推断食品安全。
        月度账目用expenses，金额为分；当前不识别说话人。
        """
        if offset < 0 or not 1 <= limit <= 30:
            raise ValueError("分页范围无效")
        if scope != "items" and (name is not None or location is not None or expiry != "all" or days != 7):
            raise ValueError("物品筛选需使用scope=items")
        snapshot = store.snapshot(month)
        if scope == "items":
            return query_items(snapshot["items"], name=name, location=location, expiry=expiry,
                               days=days, offset=offset, limit=limit)
        result = {k:v for k,v in snapshot.items() if k not in ("items", "entries", "integrations")}
        result["item_count"] = len(snapshot["items"])
        result["expense_count"] = len(snapshot["entries"])
        rows = snapshot["items"] if scope == "items" else snapshot["entries"] if scope == "expenses" else []
        result.update(records=rows[offset:offset + limit], has_more=offset + limit < len(rows))
        return result

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True))
    def household_record(request_id: str, changes: list[Change]) -> dict:
        """按明确指令记录家庭物品或账目；成功后简短复述。
        物品入库用action=add_item，提供name、quantity、unit、location；due仅填用户明确给出的YYYY-MM-DD到期日，未说则留空，不猜保质期。
        缺少数量/单位/位置或日期含糊时先简短追问。多件可一次提交；同名不同批次各自保留。
        移位置用update，先查询获取record_id和expected_version再写location；不能用add_item假装移动。
        同请求重试保持request_id；多条原子写入，可撤销；不控制设备。
        """
        return store.execute(request_id, changes)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True))
    def household_undo(request_id: str) -> dict:
        """撤销最近一次账本写入；仅补偿记录，无法撤销出粮或设备物理动作。"""
        return store.execute(request_id, undo=True)

    return server


def main():
    create_server(os.environ.get("JWS_DATA_DIR", ".runtime")).run(transport="stdio")


if __name__ == "__main__":
    main()
