"""Shared route dependencies."""

from __future__ import annotations

from fastapi import Header, HTTPException

from appforge.config import get_settings


def require_operator(x_operator_token: str | None = Header(default=None)) -> None:
    """Protect mutating endpoints when an operator token is configured."""
    settings = get_settings()
    if not settings.operator_token:
        return  # open in local development
    if x_operator_token != settings.operator_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Operator-Token")
