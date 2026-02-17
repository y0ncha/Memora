"""Pydantic schemas for Interlock artifacts."""

from interlock.schemas.ticket import Ticket
from interlock.schemas.responses import GateResult

__all__ = ["Ticket", "GateResult"]
