from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class CreateBatchRequest(BaseModel):
    title: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class RunBatchRequest(BaseModel):
    profile: str = "fast"
    anchor_doc_id: str | None = None
