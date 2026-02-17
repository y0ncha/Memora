"""Response models for Interlock gates."""

from typing import Literal

from pydantic import BaseModel, Field


class GateResult(BaseModel):
    """Result of a validation gate."""

    status: Literal["pass", "retry", "stop"] = Field(..., description="Gate validation status")
    reasons: list[str] = Field(default_factory=list, description="Reasons for the status")
    fixes: list[str] | None = Field(None, description="Suggested fixes if status is 'retry'")
