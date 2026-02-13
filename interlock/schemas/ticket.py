"""Ticket Pydantic schema for Interlock."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from interlock.schemas.artifacts import (
    EvidenceArtifact,
    ExecutionArtifact,
    FinalizationArtifact,
    PlanArtifact,
    RequirementsArtifact,
    ScopeArtifact,
)


class Ticket(BaseModel):
    """Structured ticket representation with strict validation."""
    
    ticket_id: str = Field(..., min_length=1, description="Unique ticket identifier")
    title: str = Field(..., min_length=1, description="Ticket title")
    description: str | None = Field(None, description="Ticket description")
    state: Literal[
        "intake",
        "extract_requirements",
        "scope_context",
        "gather_evidence",
        "propose_plan",
        "act",
        "finalize",
    ] = Field(..., description="Current FSM state")
    run_id: str = Field(..., min_length=1, description="Unique run identifier")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    requirements: RequirementsArtifact | None = Field(None, description="Pinned requirements artifact")
    scope: ScopeArtifact | None = Field(None, description="Scoped retrieval targets artifact")
    evidence: EvidenceArtifact | None = Field(None, description="Collected evidence artifact")
    plan: PlanArtifact | None = Field(None, description="Structured plan artifact")
    execution: ExecutionArtifact | None = Field(None, description="Execution artifact with checkpoints and outputs")
    finalization: FinalizationArtifact | None = Field(None, description="Final milestone summary artifact")
    
    @field_validator("ticket_id", "title", "run_id")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure string fields are non-empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()
    
    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Ensure state is a valid FSM state."""
        valid_states = [
            "intake",
            "extract_requirements",
            "scope_context",
            "gather_evidence",
            "propose_plan",
            "act",
            "finalize",
        ]
        if v not in valid_states:
            raise ValueError(f"Invalid state: {v}. Must be one of {valid_states}")
        return v
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        import json
        return json.dumps(self.model_dump(mode="json"), default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Ticket":
        """Deserialize from JSON string."""
        import json
        data = json.loads(json_str)
        return cls(**data)
    
