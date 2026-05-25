"""System-level lightweight API routes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
