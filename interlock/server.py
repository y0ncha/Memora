"""MCP server entry point for Interlock using FastMCP."""

import json
import logging
from typing import Any

from fastmcp import FastMCP
from pydantic import ValidationError

from interlock.schemas.ticket import Ticket
from interlock.fsm import State, transition
from interlock.gates import get_gate_for_state
from interlock.storage import ArtifactStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastMCP server instance
mcp = FastMCP("Interlock")

# Initialize artifact store
store = ArtifactStore()


@mcp.tool()
def interlock_next_step(ticket_json: str) -> dict[str, Any]:
    """
    Get the next step in the Interlock workflow.
    
    Accepts a ticket.json string, validates it, runs gates, and returns governance information:
    whether to continue (status), what the next step is (next_state), and what the agent's role is.
    
    Args:
        ticket_json: JSON string representation of the ticket (must conform to Ticket schema)
        
    Returns:
        Dictionary with status, next_state, agent_role, and gate_result
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
        error_response = {
            "status": "retry",
            "reason": f"Invalid JSON: {str(e)}",
            "next_state": None,
            "agent_role": "Fix JSON syntax and retry",
            "gate_result": {
                "status": "retry",
                "reasons": [f"JSON decode error: {str(e)}"],
                "fixes": ["Ensure ticket_json is valid JSON"],
            },
        }
        logger.error(f"JSON decode error: {e}")
        return error_response
    except ValidationError as e:
        error_response = {
            "status": "retry",
            "reason": f"Ticket validation failed: {str(e)}",
            "next_state": None,
            "agent_role": "Fix ticket schema validation errors and retry",
            "gate_result": {
                "status": "retry",
                "reasons": [f"Validation error: {str(e)}"],
                "fixes": ["Check ticket schema: ticket_id, title, state, run_id are required"],
            },
        }
        logger.error(f"Ticket validation error: {e}")
        return error_response
    
    # Get gate for current state
    gate = get_gate_for_state(ticket.state)
    gate_result = gate.validate(ticket)
    logger.info(f"Gate result: status={gate_result.status}, reasons={gate_result.reasons}")
    
    # If gate fails, return retry or stop
    if gate_result.status == "stop":
        response = {
            "status": "stop",
            "reason": f"Gate validation failed: {', '.join(gate_result.reasons)}",
            "next_state": None,
            "agent_role": "Cannot proceed - blocking validation failure",
            "gate_result": {
                "status": gate_result.status,
                "reasons": gate_result.reasons,
                "fixes": gate_result.fixes,
            },
        }
        logger.warning(f"Gate stopped: {gate_result.reasons}")
        return response
    
    if gate_result.status == "retry":
        response = {
            "status": "retry",
            "reason": f"Gate validation requires fixes: {', '.join(gate_result.reasons)}",
            "next_state": None,
            "agent_role": f"Fix issues and retry: {', '.join(gate_result.fixes or [])}",
            "gate_result": {
                "status": gate_result.status,
                "reasons": gate_result.reasons,
                "fixes": gate_result.fixes,
            },
        }
        logger.info(f"Gate retry: {gate_result.reasons}")
        return response
    
    # Gate passed, proceed with FSM transition
    current_state = State(ticket.state)
    transition_result = transition(current_state)
    logger.info(f"Transition result: status={transition_result.status}, next_state={transition_result.next_state}")
    
    # Save gate and transition events
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
        details={
            "transition_status": transition_result.status,
            "next_state": transition_result.next_state.value if transition_result.next_state else None,
        },
    )
    
    # Build response
    response = {
        "status": transition_result.status,
        "reason": transition_result.reason,
        "next_state": transition_result.next_state.value if transition_result.next_state else None,
        "agent_role": transition_result.agent_role,
        "gate_result": {
            "status": gate_result.status,
            "reasons": gate_result.reasons,
            "fixes": gate_result.fixes,
        },
    }
    
    logger.info(f"Tool response: {response}")
    return response


if __name__ == "__main__":
    mcp.run()
