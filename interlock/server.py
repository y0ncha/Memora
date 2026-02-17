"""MCP tool for Jira ticket resolution governed by an FSM.

This server exposes a single tool. It does not manage or define how the agent runs.
The agent keeps calling the tool with the current ticket; we validate gates, advance
the FSM when appropriate, and return the updated ticket plus whether the FSM has
finished. The agent calls again as long as the FSM hasn't finished (or stops for its
own reasons).
"""

import json
import logging
from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from interlock.schemas.ticket import Ticket
from interlock.fsm import (
    State,
    AGENT_ROLE_BAD_INPUT,
    get_agent_role,
    transition,
)
from interlock.gates import get_gate_for_state
from interlock.storage import ArtifactStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastMCP server instance
mcp = FastMCP("Interlock", instructions="MCP server for solving Jira tickets with deterministic FSM governance")

# Initialize artifact store
store = ArtifactStore()


def _response(
    *,
    updated_ticket: Ticket | None,
    continue_: bool,
    reason: str,
    next_role: str,
    next_state: str | None = None,
    gate_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build response dict: updated_ticket (same schema as request), continue, reason, next_role."""
    return {
        "updated_ticket": updated_ticket.model_dump(mode="json") if updated_ticket is not None else None,
        "continue": continue_,
        "reason": reason,
        "next_role": next_role,
        "next_state": next_state,
        "gate_result": gate_result,
    }


@mcp.tool()
def interlock_next_step(ticket_json: str) -> dict[str, Any]:
    """
    One step of the FSM: pass the current ticket (JSON). We validate gates and return
    the updated ticket and whether the FSM has finished.

    The agent is expected to keep calling this tool with the returned updated_ticket
    as long as the FSM has not finished (continue is true). We do not define how the
    agent runs—only the tool contract: input = ticket_json (Ticket schema), output =
    updated_ticket (same schema), continue (true = more steps), reason, next_role,
    next_state, gate_result.
    """
    logger.info(f"Tool called: interlock_next_step with ticket_json length: {len(ticket_json)}")
    
    # Parse and validate ticket
    try:
        ticket_data = json.loads(ticket_json)
        ticket = Ticket(**ticket_data)
        logger.info(f"Ticket parsed successfully: ticket_id={ticket.ticket_id}, state={ticket.state}")
        
        # Save ticket to storage
        store.save_ticket(ticket)
        store.save_event(
            run_id=ticket.run_id,
            event_type="tool_call",
            state=ticket.state,
            details={"tool": "interlock_next_step", "ticket_id": ticket.ticket_id},
        )
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return _response(
            updated_ticket=None,
            continue_=False,
            reason=f"Invalid JSON: {str(e)}",
            next_role=AGENT_ROLE_BAD_INPUT,
            next_state=None,
            gate_result={
                "status": "retry",
                "reasons": [f"JSON decode error: {str(e)}"],
                "fixes": ["Ensure ticket_json is valid JSON"],
            },
        )
    except ValidationError as e:
        logger.error(f"Ticket validation error: {e}")
        return _response(
            updated_ticket=None,
            continue_=False,
            reason=f"Ticket validation failed: {str(e)}",
            next_role=AGENT_ROLE_BAD_INPUT,
            next_state=None,
            gate_result={
                "status": "retry",
                "reasons": [str(e)],
                "fixes": ["Check ticket schema: ticket_id, title, state, run_id are required"],
            },
        )
    
    # Get gate for current state
    gate = get_gate_for_state(ticket.state)
    gate_result = gate.validate(ticket)
    logger.info(f"Gate result: status={gate_result.status}, reasons={gate_result.reasons}")
    
    gate_result_dict = {
        "status": gate_result.status,
        "reasons": gate_result.reasons,
        "fixes": gate_result.fixes,
    }

    # If gate fails, return retry or stop (ticket unchanged); response role = canonical role for current state
    if gate_result.status == "stop":
        logger.warning(f"Gate stopped: {gate_result.reasons}")
        current_role = get_agent_role(State(ticket.state))
        ticket_with_role = ticket.model_copy(update={"agent_role": current_role})
        return _response(
            updated_ticket=ticket_with_role,
            continue_=False,
            reason=f"Gate validation failed: {', '.join(gate_result.reasons)}",
            next_role=current_role,
            next_state=None,
            gate_result=gate_result_dict,
        )

    if gate_result.status == "retry":
        logger.info(f"Gate retry: {gate_result.reasons}")
        current_role = get_agent_role(State(ticket.state))
        ticket_with_role = ticket.model_copy(update={"agent_role": current_role})
        return _response(
            updated_ticket=ticket_with_role,
            continue_=False,
            reason=f"Gate validation requires fixes: {', '.join(gate_result.reasons)}",
            next_role=current_role,
            next_state=None,
            gate_result=gate_result_dict,
        )
    
    # Gate passed, proceed with FSM transition
    current_state = State(ticket.state)
    transition_result = transition(current_state)
    logger.info(f"Transition result: status={transition_result.status}, next_state={transition_result.next_state}")

    # If transition says stop (e.g. already in finalize), return current ticket with canonical role
    if transition_result.status != "pass" or transition_result.next_state is None:
        store.save_event(
            run_id=ticket.run_id,
            event_type="gate_passed",
            state=ticket.state,
            details={"gate_status": gate_result.status, "reasons": gate_result.reasons},
        )
        ticket_with_role = ticket.model_copy(update={"agent_role": transition_result.agent_role})
        return _response(
            updated_ticket=ticket_with_role,
            continue_=False,
            reason=transition_result.reason,
            next_role=transition_result.agent_role,
            next_state=None,
            gate_result=gate_result_dict,
        )

    next_state_value = transition_result.next_state.value

    # Build updated ticket with new state, canonical role for that state, and updated_at
    updated_ticket = ticket.model_copy(
        update={
            "state": next_state_value,
            "agent_role": transition_result.agent_role,
            "updated_at": datetime.now(),
        }
    )
    store.save_ticket(updated_ticket)
    store.save_event(
        run_id=ticket.run_id,
        event_type="gate_passed",
        state=ticket.state,
        details={"gate_status": gate_result.status, "reasons": gate_result.reasons},
    )
    store.save_event(
        run_id=ticket.run_id,
        event_type="transition",
        state=ticket.state,
        details={"transition_status": transition_result.status, "next_state": next_state_value},
    )

    logger.info(f"Tool response: continue=True, next_state={next_state_value}")
    return _response(
        updated_ticket=updated_ticket,
        continue_=True,
        reason=transition_result.reason,
        next_role=transition_result.agent_role,
        next_state=next_state_value,
        gate_result=gate_result_dict,
    )


if __name__ == "__main__":
    mcp.run()
