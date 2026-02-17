"""Ticket Pydantic schema for Interlock.

This module defines the canonical ``Ticket`` model used across the Interlock
pipeline. A ticket represents a single work item progressing through a
finite-state machine (FSM) of stages: intake → requirements → context →
evidence → plan → act → finalize.

Example:
    >>> from interlock.schemas.ticket import Ticket
    >>> t = Ticket(
    ...     ticket_id="T-001",
    ...     title="Add login flow",
    ...     state="intake",
    ...     run_id="run-abc",
    ... )
    >>> t.to_json()
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Ticket(BaseModel):
    """Structured ticket representation with strict validation.

    Attributes:
        ticket_id: Unique identifier for the ticket (non-empty, trimmed).
        title: Short title for the ticket (non-empty, trimmed).
        description: Optional longer description.
        state: Current stage in the pipeline FSM (intake, extract_requirements,
            scope_context, gather_evidence, propose_plan, act, finalize).
        run_id: Unique identifier for the execution run (non-empty, trimmed).
        agent_role: Agent's role for the current/next step (set by server on response).
        created_at: When the ticket was created (defaults to now).
        updated_at: When the ticket was last updated (defaults to now).

    Raises:
        ValidationError: If required string fields are empty/whitespace or
            ``state`` is not one of the allowed FSM states.
    """

    model_config = ConfigDict()

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
    agent_role: str | None = Field(None, description="Agent's role for the current/next step (set by server on response)")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    @field_validator("ticket_id", "title", "run_id")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Strip and reject empty or whitespace-only values for required strings."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Ensure state is one of the allowed FSM states."""
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
        """Serialize this ticket to a JSON string.

        Uses ``model_dump(mode="json")`` so datetimes are ISO strings.
        """
        import json
        return json.dumps(self.model_dump(mode="json"), default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "Ticket":
        """Build a ``Ticket`` from a JSON string.

        Args:
            json_str: JSON object string with ticket fields.

        Returns:
            A validated ``Ticket`` instance.

        Raises:
            ValidationError: If the parsed data fails model validation.
        """
        import json
        data = json.loads(json_str)
        return cls(**data)
