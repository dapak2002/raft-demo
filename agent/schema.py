import re
from typing import Any

from pydantic import BaseModel, Field


class RecordExtract(BaseModel):
    fields: dict[str, str | float | int | bool | list[str]] = Field(
        default_factory=dict,
        description="All fields found in the text as snake_case keys to typed values.",
    )


class Record(BaseModel):
    fields: dict[str, Any]
    raw_text: str = ""

    @staticmethod
    def normalize_key(key: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")

    def field_map(self) -> dict[str, Any]:
        return {self.normalize_key(k): v for k, v in self.fields.items()}

    def get(self, field: str) -> Any:
        return self.field_map().get(self.normalize_key(field))

    def identifier(self) -> str:
        for key, val in self.fields.items():
            if any(t in self.normalize_key(key) for t in ("order", "id", "number", "num")):
                return str(val)
        return str(next(iter(self.fields.values()), "unknown"))


class Filter(BaseModel):
    field: str = Field(description="Field name from the discovered schema")
    operator: str = Field(
        description="Comparison: equals, contains, over, under, at least, at most, not"
    )
    values: list[str | float | int | bool] = Field(
        description="Match if ANY value satisfies the operator. Expand categories and regions into concrete terms.",
        min_length=1,
    )


class QueryPlan(BaseModel):
    filters: list[Filter] = Field(
        default_factory=list,
        description="Filters extracted from the user query, using discovered field names",
    )
