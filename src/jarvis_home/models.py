from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


def today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["add_item", "expense", "consume", "update"]
    name: str = Field(min_length=1, max_length=100)
    quantity: Decimal | None = Field(default=None, gt=0, le=100000, max_digits=10, decimal_places=3)
    unit: str | None = Field(default=None, min_length=1, max_length=12)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0, le=10000000, max_digits=10, decimal_places=2)
    category: str = Field(default="其他", min_length=1, max_length=30)
    payment: str = Field(default="未指定", min_length=1, max_length=30)
    kind: Literal["支出", "收入", "转账", "退款"] = "支出"
    on: date = Field(default_factory=today)
    due: date | None = None
    record_id: str | None = Field(default=None, max_length=64)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("name", "unit", "location", "category", "payment")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("不能为空")
        return value.strip() if value else value


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=2000)
