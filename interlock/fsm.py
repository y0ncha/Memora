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

# Canonical agent role descriptions per state (single source of truth for responses).
# Each must be a clear, rigid instruction for the agent in that state.
AGENT_ROLES: dict[State, str] = {
    State.INTAKE: (
        "Parse the ticket and extract basic information: ticket_id, title, and description. "
        "Do not infer requirements or plan; only normalize and structure the raw ticket."
    ),
    State.EXTRACT_REQUIREMENTS: (
        "Extract acceptance criteria, constraints, and unknowns from the ticket. "
        "Output a structured list of requirements and open questions; do not retrieve context or propose a plan."
    ),
    State.SCOPE_CONTEXT: (
        "Determine what context to retrieve based on the stated requirements and unknowns. "
        "Do not gather code snippets or propose a plan; only decide and request the minimal context needed."
    ),
    State.GATHER_EVIDENCE: (
        "Collect minimal supporting snippets with source pointers (file, line, repo). "
        "Do not propose a plan or execute changes; only gather evidence that will ground the plan."
    ),
    State.PROPOSE_PLAN: (
        "Generate a step-by-step plan tied to requirements and grounded in the gathered evidence. "
        "Do not execute the plan; only produce the plan with clear, checkable steps."
    ),
    State.ACT: (
        "Execute the plan using tools: make the changes, run checks, and produce candidate outputs with checkpoints. "
        "Do not finalize artifacts or post summaries until the act phase is complete."
    ),
    State.FINALIZE: (
        "Store canonical artifacts (e.g. code, docs, config) and post a brief milestone summary. "
        "No further FSM steps after this state."
    ),
}

# Canonical role strings for non-pass outcomes (returned in response when not advancing).
AGENT_ROLE_FINALIZE_DONE = "No further action required; ticket is in final state."
AGENT_ROLE_INVALID_STATE = "Invalid state; cannot proceed. Fix ticket state and call again."
AGENT_ROLE_GATE_RETRY = "Address the reported validation issues and call again with an updated ticket."
AGENT_ROLE_GATE_STOP = "Blocking validation failure; cannot proceed."
AGENT_ROLE_BAD_INPUT = "Fix the request (valid JSON and ticket schema) and call again."


def get_agent_role(state: State) -> str:
    """Return the canonical agent role description for the given state."""
    return AGENT_ROLES.get(state, AGENT_ROLE_INVALID_STATE)


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
            agent_role=AGENT_ROLE_FINALIZE_DONE,
        )

    # Check if transition is allowed
    if current_state not in TRANSITION_MAP:
        logger.error(f"Invalid state for transition: {current_state}")
        return TransitionResult(
            status="stop",
            reason=f"Invalid state: {current_state}",
            next_state=None,
            agent_role=AGENT_ROLE_INVALID_STATE,
        )

    next_state = TRANSITION_MAP[current_state]
    agent_role = get_agent_role(next_state)
    
    logger.info(f"Transition approved: {current_state} -> {next_state}")
    
    return TransitionResult(
        status="pass",
        reason=f"Valid transition from {current_state} to {next_state}",
        next_state=next_state,
        agent_role=agent_role,
    )
