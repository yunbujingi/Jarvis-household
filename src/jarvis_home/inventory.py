"""Deterministic inventory filters; dates describe records, not food safety."""
from datetime import date

from .models import today


def query_items(items, *, name=None, location=None, expiry="all", days=7, offset=0, limit=20):
    if expiry not in {"all", "overdue", "today", "within_days", "unset"}:
        raise ValueError("到期筛选无效")
    if not 0 <= days <= 3660 or offset < 0 or not 1 <= limit <= 30:
        raise ValueError("查询范围无效")
    for value in (name, location):
        if value is not None and (not value.strip() or len(value) > 100):
            raise ValueError("名称或位置不能为空且最多100字")
    as_of = today()
    matches = [item for item in items
               if (name is None or name.strip().casefold() in item["name"].casefold())
               and (location is None or location.strip().casefold() in item["location"].casefold())]
    unknown_count = sum(not item.get("due") for item in matches)
    rows = []
    for item in matches:
        due = date.fromisoformat(item["due"]) if item.get("due") else None
        remaining = (due - as_of).days if due else None
        state = "unset" if due is None else "overdue" if remaining < 0 else "today" if remaining == 0 else "future"
        if expiry == "all" or expiry == state or (expiry == "within_days" and remaining is not None and 0 <= remaining <= days):
            rows.append({**item, "days_until_due": remaining, "expiry_status": state})
    rows.sort(key=lambda item: (item.get("due") or "9999-12-31", item["name"], item["id"]))
    selected = rows[offset:offset + limit]
    return {"as_of": str(as_of), "timezone": "Asia/Shanghai", "item_count": len(rows),
            "unknown_due_count": unknown_count, "records": selected,
            "has_more": offset + limit < len(rows)}
