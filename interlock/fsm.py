"""FSM state enum and transition logic for Interlock."""

import logging
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class State(str, Enum):
    """FSM states for Interlock lifecycle."""
    
    INTAKE = "intake"
    EXTRACT_REQUIREMENTS = "extract_requirements"
    SCOPE_CONTEXT = "scope_context"
    GATHER_EVIDENCE = "gather_evidence"
    PROPOSE_PLAN = "propose_plan"
    ACT = "act"
    FINALIZE = "finalize"


class TransitionResult(BaseModel):
    """Result of an FSM state transition."""
    
    status: Literal["pass", "retry", "stop"] = Field(..., description="Transition status")
    reason: str = Field(..., description="Reason for the status")
    next_state: State | None = Field(None, description="Next state if status is 'pass'")
    agent_role: str = Field(..., description="Agent's role in the next step")


# State transition map: current_state -> next_state
TRANSITION_MAP: dict[State, State] = {
    State.INTAKE: State.EXTRACT_REQUIREMENTS,
    State.EXTRACT_REQUIREMENTS: State.SCOPE_CONTEXT,
    State.SCOPE_CONTEXT: State.GATHER_EVIDENCE,
    State.GATHER_EVIDENCE: State.PROPOSE_PLAN,
    State.PROPOSE_PLAN: State.ACT,
    State.ACT: State.FINALIZE,
    State.FINALIZE: State.FINALIZE,  # Terminal state
}

# Agent role descriptions for each state
AGENT_ROLES: dict[State, str] = {
    State.INTAKE: "Parse the ticket and extract basic information (ticket_id, title, description)",
    State.EXTRACT_REQUIREMENTS: "Extract acceptance criteria, constraints, and unknowns from the ticket",
    State.SCOPE_CONTEXT: "Determine what context to retrieve based on requirements and unknowns",
    State.GATHER_EVIDENCE: "Collect minimal supporting snippets with source pointers",
    State.PROPOSE_PLAN: "Generate a step-by-step plan tied to requirements and grounded in evidence",
    State.ACT: "Execute the plan using tools, producing candidate outputs with checkpoints",
    State.FINALIZE: "Store canonical artifacts and post milestone summary",
}


def transition(current_state: State) -> TransitionResult:
    """
    Determine the next state transition based on current state.
    
    Args:
        current_state: Current FSM state
        
    Returns:
        TransitionResult with status, next_state, and agent_role
    """
    logger.info(f"Transitioning from state: {current_state}")
    
    # Check if current state is terminal
    if current_state == State.FINALIZE:
        return TransitionResult(
            status="stop",
            reason="Already in final state",
            next_state=None,
            agent_role="No further action required",
        )
    
    # Check if transition is allowed
    if current_state not in TRANSITION_MAP:
        logger.error(f"Invalid state for transition: {current_state}")
        return TransitionResult(
            status="stop",
            reason=f"Invalid state: {current_state}",
            next_state=None,
            agent_role="Invalid state - cannot proceed",
        )
    
    next_state = TRANSITION_MAP[current_state]
    agent_role = AGENT_ROLES.get(next_state, "Continue with next step")
    
    logger.info(f"Transition approved: {current_state} -> {next_state}")
    
    return TransitionResult(
        status="pass",
        reason=f"Valid transition from {current_state} to {next_state}",
        next_state=next_state,
        agent_role=agent_role,
    )
