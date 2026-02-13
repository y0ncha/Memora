"""Response models for Interlock gates."""

from typing import Literal

from pydantic import BaseModel, Field


class GateResult(BaseModel):
    """Result of a validation gate."""
    
    status: Literal["pass", "retry", "stop"] = Field(..., description="Gate validation status")
    reasons: list[str] = Field(default_factory=list, description="Reasons for the status")
    fixes: list[str] | None = Field(None, description="Suggested fixes if status is 'retry'")


class InvalidationReport(BaseModel):
    """Structured fail-fast report returned on retry/stop outcomes."""

    failed_state: str = Field(..., description="State where validation failed")
    failed_gate: str = Field(..., description="Gate that produced the failure")
    reason: str = Field(..., description="Primary failure reason")
    fixable: bool = Field(..., description="Whether the issue is retryable")
    minimum_next_action: str = Field(..., description="Minimal input/action required to continue")
