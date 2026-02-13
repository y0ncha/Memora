"""Demo script showing an end-to-end governed flow across all Interlock states."""

import logging
from uuid import uuid4

from interlock.fsm import State, transition
from interlock.gates import get_gate_for_state
from interlock.schemas.ticket import Ticket
from interlock.storage import ArtifactStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _call(ticket: Ticket) -> dict:
    """Run the core governance flow without requiring an MCP runtime."""
    store = ArtifactStore()
    store.save_ticket(ticket)
    store.save_event(
        run_id=ticket.run_id,
        event_type="tool_call",
        state=ticket.state,
        details={"tool": "interlock_next_step", "ticket_id": ticket.ticket_id},
    )

    gate = get_gate_for_state(ticket.state)
    gate_result = gate.validate(ticket)
    if gate_result.status != "pass":
        return {
            "status": gate_result.status,
            "reason": ", ".join(gate_result.reasons),
            "next_state": None,
            "agent_role": "Apply fixes before retrying",
            "gate_result": gate_result.model_dump(),
        }

    transition_result = transition(State(ticket.state))
    store.save_event(
        run_id=ticket.run_id,
        event_type="gate_passed",
        state=ticket.state,
        details={"gate_status": gate_result.status},
    )
    store.save_event(
        run_id=ticket.run_id,
        event_type="transition",
        state=ticket.state,
        details={
            "transition_status": transition_result.status,
            "next_state": transition_result.next_state.value if transition_result.next_state else None,
        },
    )
    return {
        "status": transition_result.status,
        "reason": transition_result.reason,
        "next_state": transition_result.next_state.value if transition_result.next_state else None,
        "agent_role": transition_result.agent_role,
        "gate_result": gate_result.model_dump(),
    }


def _print_response(response: dict) -> None:
    """Print a concise governance response."""
    logger.info("  status=%s", response["status"])
    logger.info("  reason=%s", response["reason"])
    logger.info("  next_state=%s", response["next_state"])
    logger.info("  agent_role=%s", response["agent_role"])


def main() -> None:
    """Run a full successful workflow."""
    run_id = str(uuid4())
    logger.info("=" * 60)
    logger.info("Interlock Demo: PRD-aligned governed run")
    logger.info("=" * 60)

    # 1. intake
    ticket = Ticket(
        ticket_id="DEMO-001",
        title="Add user authentication",
        description="Implement user login and invalid credential handling",
        state="intake",
        run_id=run_id,
    )
    logger.info("[1] intake")
    response = _call(ticket)
    _print_response(response)
    if response["status"] != "pass":
        return

    # 2. extract_requirements
    payload = ticket.model_dump(mode="json")
    payload["state"] = response["next_state"]
    payload["requirements"] = {
        "acceptance_criteria": [
            {"id": "AC-1", "text": "User can log in"},
            {"id": "AC-2", "text": "Invalid credentials produce a clear error"},
        ],
        "constraints": [{"id": "C-1", "text": "Reuse existing auth service"}],
        "unknowns": ["Should MFA be included?"],
    }
    ticket = Ticket(**payload)
    logger.info("[2] extract_requirements")
    response = _call(ticket)
    _print_response(response)
    if response["status"] != "pass":
        return

    # 3. scope_context
    payload = ticket.model_dump(mode="json")
    payload["state"] = response["next_state"]
    payload["scope"] = {
        "targets": [
            {
                "id": "T-1",
                "source": "repo",
                "query": "src/auth/**",
                "rationale": "Gather implementation details",
                "related_requirement_ids": ["AC-1", "AC-2", "C-1"],
                "related_unknowns": [],
            }
        ]
    }
    ticket = Ticket(**payload)
    logger.info("[3] scope_context")
    response = _call(ticket)
    _print_response(response)
    if response["status"] != "pass":
        return

    # 4. gather_evidence
    payload = ticket.model_dump(mode="json")
    payload["state"] = response["next_state"]
    payload["evidence"] = {
        "items": [
            {
                "id": "E-1",
                "source": "repo",
                "source_ref": "src/auth/login.py",
                "locator": "L10-L28",
                "snippet": "Login returns token on valid credentials",
                "supports": ["AC-1"],
            },
            {
                "id": "E-2",
                "source": "repo",
                "source_ref": "src/auth/login.py",
                "locator": "L29-L45",
                "snippet": "Invalid credentials return error payload",
                "supports": ["AC-2"],
            },
            {
                "id": "E-3",
                "source": "confluence",
                "source_ref": "AUTH-SERVICE-DOC",
                "locator": "Section 2.1",
                "snippet": "Auth service is the mandated provider",
                "supports": ["C-1"],
            },
        ]
    }
    ticket = Ticket(**payload)
    logger.info("[4] gather_evidence")
    response = _call(ticket)
    _print_response(response)
    if response["status"] != "pass":
        return

    # 5. propose_plan
    payload = ticket.model_dump(mode="json")
    payload["state"] = response["next_state"]
    payload["plan"] = {
        "steps": [
            {
                "id": "P-1",
                "title": "Wire login endpoint",
                "description": "Connect login API to existing auth provider",
                "requirement_ids": ["AC-1", "C-1"],
                "evidence_ids": ["E-1", "E-3"],
                "step_type": "delivery",
            },
            {
                "id": "P-2",
                "title": "Handle invalid credentials",
                "description": "Return standard 401 response with message",
                "requirement_ids": ["AC-2"],
                "evidence_ids": ["E-2"],
                "step_type": "delivery",
            },
        ]
    }
    ticket = Ticket(**payload)
    logger.info("[5] propose_plan")
    response = _call(ticket)
    _print_response(response)
    if response["status"] != "pass":
        return

    # 6. act
    payload = ticket.model_dump(mode="json")
    payload["state"] = response["next_state"]
    payload["execution"] = {
        "checkpoints": ["cp-auth-service-adapter", "cp-login-error-handling"],
        "outputs": [
            {
                "id": "O-1",
                "summary": "Successful authentication flow implemented",
                "covered_requirement_ids": ["AC-1", "C-1"],
                "evidence_ids": ["E-1", "E-3"],
                "status": "candidate",
            },
            {
                "id": "O-2",
                "summary": "Invalid credential response implemented",
                "covered_requirement_ids": ["AC-2"],
                "evidence_ids": ["E-2"],
                "status": "candidate",
            },
        ],
    }
    ticket = Ticket(**payload)
    logger.info("[6] act")
    response = _call(ticket)
    _print_response(response)
    if response["status"] != "pass":
        return

    # 7. finalize
    payload = ticket.model_dump(mode="json")
    payload["state"] = response["next_state"]
    payload["finalization"] = {
        "outcome": "done",
        "milestone_summary": "Pinned requirements were fully covered with grounded outputs and checkpoints",
        "unresolved_items": [],
    }
    ticket = Ticket(**payload)
    logger.info("[7] finalize")
    response = _call(ticket)
    _print_response(response)

    logger.info("=" * 60)
    logger.info("Demo completed. Artifacts were persisted to interlock_data/")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
