"""Pydantic request/response schemas — completed in stage 1."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrderCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    item_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    quantity: int
    item_id: str
    status: str
    created_at: datetime
    update_at: datetime
