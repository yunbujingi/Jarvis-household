from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    new_name: str | None = Field(default=None, min_length=1, max_length=100)
    set_quantity: Decimal | None = Field(default=None, ge=0, le=100000, max_digits=10, decimal_places=3)
    clear_due: bool = False
    record_id: str | None = Field(default=None, max_length=64)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("new_name", "name", "unit", "location", "category", "payment")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("不能为空")
        return value.strip() if value else value


    @model_validator(mode="after")
    def correction_fields(self):
        if self.clear_due and self.due is not None:
            raise ValueError("不能同时设置与清除到期日")
        if self.action != "update" and (self.new_name is not None or self.set_quantity is not None or self.clear_due):
            raise ValueError("纠错字段仅用于update")
        if self.action == "update" and self.quantity is not None:
            raise ValueError("绝对数量修正用set_quantity；扣减用consume")
        if self.new_name is not None and not self.record_id:
            raise ValueError("改名必须提供record_id")
        return self


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=2000)
