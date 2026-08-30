"""اسکیماهای مشترک: صفحه‌بندی و پاسخ استاندارد."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=200)
    search: str | None = None
    sort: str | None = None
    order: str = Field(default="desc", pattern="^(asc|desc)$")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


class OkResponse(BaseModel):
    ok: bool = True
    message: str = "انجام شد."


class BulkAction(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(start|stop|restart|delete|enable|disable|maintenance_on|maintenance_off)$")


def paginate(items: list, total: int, params: PageParams) -> dict:
    pages = max(1, (total + params.per_page - 1) // params.per_page)
    return {"items": items, "total": total, "page": params.page, "per_page": params.per_page, "pages": pages}
