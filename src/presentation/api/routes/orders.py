"""Order API routes — implemented in stage 1."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/orders", tags=["orders"])
