"""Rigid FSM registry and transition logic for Interlock."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class State(str, Enum):
    """FSM states for the ticket handshake workflow."""

    FETCH_TICKET = "fetch_ticket"
    EXTRACT_REQUIREMENTS = "extract_requirements"
    SCOPE_CONTEXT = "scope_context"
    GATHER_EVIDENCE = "gather_evidence"
    PROPOSE_PLAN = "propose_plan"
    ACT_VIA_TOOLS = "act_via_tools"
    RECORD_AND_FINALIZE = "record_and_finalize"
    COMPLETE = "complete"
    FAIL_CLOSED = "fail_closed"


class StageSpec(BaseModel):
    """Static contract for each non-terminal stage."""

    state: State
    agent_role: str
    required_fields: tuple[str, ...]


class TransitionResult(BaseModel):
    """Result of an FSM transition."""

    status: Literal["pass", "stop"] = Field(..., description="Transition status")
    reason: str = Field(..., description="Transition reason")
    next_state: State | None = Field(None, description="Next state when status is 'pass'")
    agent_role: str = Field(..., description="Role for the resulting state")


STAGE_SPECS: dict[State, StageSpec] = {
    State.FETCH_TICKET: StageSpec(
        state=State.FETCH_TICKET,
        agent_role=(
            "Stage FETCH_TICKET (1/7). Goal: retrieve the ticket from source systems and normalize it. "
            "Required output fields: external_source, external_ticket_id, title, description. "
            "Do not infer requirements, propose a plan, or execute tools beyond retrieval."
        ),
        required_fields=("external_source", "external_ticket_id", "title", "description"),
    ),
    State.EXTRACT_REQUIREMENTS: StageSpec(
        state=State.EXTRACT_REQUIREMENTS,
        agent_role=(
            "Stage EXTRACT_REQUIREMENTS (2/7). Goal: convert ticket content into explicit requirements. "
            "Required output fields: acceptance_criteria, constraints, unknowns. "
            "Do not retrieve external context or produce execution steps."
        ),
        required_fields=("acceptance_criteria", "constraints", "unknowns"),
    ),
    State.SCOPE_CONTEXT: StageSpec(
        state=State.SCOPE_CONTEXT,
        agent_role=(
            "Stage SCOPE_CONTEXT (3/7). Goal: define what context should be fetched next and why. "
            "Required output fields: retrieval_targets, retrieval_justification. "
            "Do not gather evidence snippets yet."
        ),
        required_fields=("retrieval_targets", "retrieval_justification"),
    ),
    State.GATHER_EVIDENCE: StageSpec(
        state=State.GATHER_EVIDENCE,
        agent_role=(
            "Stage GATHER_EVIDENCE (4/7). Goal: collect minimal traceable evidence with provenance. "
            "Required output fields: evidence_items[{source_id, source_type, locator, snippet}]. "
            "Do not propose the plan yet."
        ),
        required_fields=("evidence_items",),
    ),
    State.PROPOSE_PLAN: StageSpec(
        state=State.PROPOSE_PLAN,
        agent_role=(
            "Stage PROPOSE_PLAN (5/7). Goal: generate a structured plan grounded in requirements and evidence. "
            "Required output fields: plan_steps[{step_id, intent, requirement_refs, evidence_refs}]. "
            "Do not execute plan actions in this stage."
        ),
        required_fields=("plan_steps",),
    ),
    State.ACT_VIA_TOOLS: StageSpec(
        state=State.ACT_VIA_TOOLS,
        agent_role=(
            "Stage ACT_VIA_TOOLS (6/7). Goal: execute the approved plan in controlled chunks. "
            "Required output fields: actions_taken, outputs, checkpoints. "
            "Do not finalize artifacts/outcome yet."
        ),
        required_fields=("actions_taken", "outputs", "checkpoints"),
    ),
    State.RECORD_AND_FINALIZE: StageSpec(
        state=State.RECORD_AND_FINALIZE,
        agent_role=(
            "Stage RECORD_AND_FINALIZE (7/7). Goal: persist artifacts and publish final result. "
            "Required output fields: artifacts, final_summary, outcome(success|partial|blocked). "
            "After this stage, the server moves to COMPLETE."
        ),
        required_fields=("artifacts", "final_summary", "outcome"),
    ),
}


TRANSITION_MAP: dict[State, State] = {
    State.FETCH_TICKET: State.EXTRACT_REQUIREMENTS,
    State.EXTRACT_REQUIREMENTS: State.SCOPE_CONTEXT,
    State.SCOPE_CONTEXT: State.GATHER_EVIDENCE,
    State.GATHER_EVIDENCE: State.PROPOSE_PLAN,
    State.PROPOSE_PLAN: State.ACT_VIA_TOOLS,
    State.ACT_VIA_TOOLS: State.RECORD_AND_FINALIZE,
    State.RECORD_AND_FINALIZE: State.COMPLETE,
}


AGENT_ROLE_COMPLETE = "Run is complete. No further action is required."
AGENT_ROLE_FAIL_CLOSED = "Run is fail-closed. Resolve invalidation report before retrying."
AGENT_ROLE_INVALID_STATE = "Invalid ticket state. Fix state and resubmit."
AGENT_ROLE_BAD_INPUT = "Invalid input payload. Send valid ticket JSON."


def get_agent_role(state: State) -> str:
    """Return canonical role description for a given state."""
    if state == State.COMPLETE:
        return AGENT_ROLE_COMPLETE
    if state == State.FAIL_CLOSED:
        return AGENT_ROLE_FAIL_CLOSED
    spec = STAGE_SPECS.get(state)
    return spec.agent_role if spec else AGENT_ROLE_INVALID_STATE


def get_required_fields(state: State) -> list[str]:
    """Return required payload fields for a state."""
    spec = STAGE_SPECS.get(state)
    if spec is None:
        return []
    return list(spec.required_fields)


def get_next_stage_fields(state: State) -> list[str]:
    """Return the required fields of the next stage."""
    next_state = TRANSITION_MAP.get(state)
    if next_state is None:
        return []
    return get_required_fields(next_state)


def is_terminal(state: State) -> bool:
    """Check whether a state is terminal."""
    return state in {State.COMPLETE, State.FAIL_CLOSED}


def transition(current_state: State) -> TransitionResult:
    """Advance one step in the deterministic FSM."""
    if current_state == State.COMPLETE:
        return TransitionResult(
            status="stop",
            reason="Run already completed",
            next_state=None,
            agent_role=get_agent_role(State.COMPLETE),
        )
    if current_state == State.FAIL_CLOSED:
        return TransitionResult(
            status="stop",
            reason="Run is fail-closed",
            next_state=None,
            agent_role=get_agent_role(State.FAIL_CLOSED),
        )
    if current_state not in TRANSITION_MAP:
        return TransitionResult(
            status="stop",
            reason=f"Invalid state: {current_state}",
            next_state=None,
            agent_role=AGENT_ROLE_INVALID_STATE,
        )

    next_state = TRANSITION_MAP[current_state]
    return TransitionResult(
        status="pass",
        reason=f"Transition {current_state.value} -> {next_state.value}",
        next_state=next_state,
        agent_role=get_agent_role(next_state),
    )
