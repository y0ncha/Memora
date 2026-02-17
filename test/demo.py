"""Demo script showing end-to-end agent governance flow through FSM states."""

import json
import logging
from uuid import uuid4

from interlock.schemas.ticket import Ticket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def simulate_agent_call(ticket: Ticket) -> dict:
    """
    Simulate an agent calling the interlock_next_step tool.
    
    In a real scenario, this would be an MCP client call.
    For demo purposes, we'll call the core logic directly.
    """
    import json
    from interlock.fsm import State, transition
    from interlock.gates import get_gate_for_state
    from interlock.storage import ArtifactStore
    
    store = ArtifactStore()
    
    # Save ticket
    store.save_ticket(ticket)
    store.save_event(
        run_id=ticket.run_id,
        event_type="tool_call",
        state=ticket.state,
        details={"tool": "interlock_next_step", "ticket_id": ticket.ticket_id},
    )
    
    # Get gate for current state
    gate = get_gate_for_state(ticket.state)
    gate_result = gate.validate(ticket)
    
    # If gate fails, return retry or stop
    if gate_result.status == "stop":
        return {
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
    
    if gate_result.status == "retry":
        return {
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
    
    # Gate passed, proceed with FSM transition
    current_state = State(ticket.state)
    transition_result = transition(current_state)
    
    # Save events
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
    return {
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


def main():
    """Run the demo flow."""
    logger.info("=" * 60)
    logger.info("Interlock PoC Demo: Agent Governance Flow")
    logger.info("=" * 60)
    
    run_id = str(uuid4())
    
    # Step 1: Agent starts with ticket in "intake" state
    logger.info("\n[Step 1] Agent creates ticket in 'intake' state")
    ticket1 = Ticket(
        ticket_id="DEMO-001",
        title="Add user authentication",
        description="Implement user login and registration",
        state="intake",
        run_id=run_id,
    )
    
    logger.info(f"Ticket created: {ticket1.ticket_id}, state={ticket1.state}")
    response1 = simulate_agent_call(ticket1)
    
    logger.info(f"\nInterlock Response:")
    logger.info(f"  Status: {response1['status']}")
    logger.info(f"  Next State: {response1['next_state']}")
    logger.info(f"  Agent Role: {response1['agent_role']}")
    logger.info(f"  Gate Result: {response1['gate_result']['status']}")
    
    if response1["status"] != "pass":
        logger.error(f"Unexpected status: {response1['status']}")
        return
    
    # Step 2: Agent updates ticket to next state and calls again
    logger.info("\n[Step 2] Agent updates ticket to 'extract_requirements' state")
    ticket2 = Ticket(
        ticket_id=ticket1.ticket_id,
        title=ticket1.title,
        description=ticket1.description,
        state=response1["next_state"],  # "extract_requirements"
        run_id=run_id,
    )
    
    logger.info(f"Ticket updated: {ticket2.ticket_id}, state={ticket2.state}")
    response2 = simulate_agent_call(ticket2)
    
    logger.info(f"\nInterlock Response:")
    logger.info(f"  Status: {response2['status']}")
    logger.info(f"  Next State: {response2['next_state']}")
    logger.info(f"  Agent Role: {response2['agent_role']}")
    logger.info(f"  Gate Result: {response2['gate_result']['status']}")
    
    if response2["status"] != "pass":
        logger.error(f"Unexpected status: {response2['status']}")
        return
    
    # Step 3: Agent updates ticket to next state
    logger.info("\n[Step 3] Agent updates ticket to 'scope_context' state")
    ticket3 = Ticket(
        ticket_id=ticket2.ticket_id,
        title=ticket2.title,
        description=ticket2.description,
        state=response2["next_state"],  # "scope_context"
        run_id=run_id,
    )
    
    logger.info(f"Ticket updated: {ticket3.ticket_id}, state={ticket3.state}")
    response3 = simulate_agent_call(ticket3)
    
    logger.info(f"\nInterlock Response:")
    logger.info(f"  Status: {response3['status']}")
    logger.info(f"  Next State: {response3['next_state']}")
    logger.info(f"  Agent Role: {response3['agent_role']}")
    logger.info(f"  Gate Result: {response3['gate_result']['status']}")
    
    # Demonstrate validation failure
    logger.info("\n[Step 4] Demonstrating validation failure with invalid ticket")
    try:
        from pydantic import ValidationError
        # This should raise ValidationError
        invalid_ticket = Ticket(
            ticket_id="",  # Invalid: empty ticket_id
            title="Test",
            state="intake",
            run_id=run_id,
        )
        logger.warning("⚠️  Validation should have failed but didn't!")
    except ValidationError as e:
        logger.info(f"✅ Validation correctly rejected invalid ticket: {type(e).__name__}")
        # Show first error message
        error_msg = str(e).split('\n')[0] if '\n' in str(e) else str(e)
        logger.info(f"   Error: {error_msg[:100]}...")  # Truncate long messages
    except Exception as e:
        logger.warning(f"⚠️  Unexpected error type: {type(e).__name__}: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info("Demo completed successfully!")
    logger.info("=" * 60)
    logger.info(f"\nArtifacts saved to: interlock_data/")
    logger.info(f"  - tickets.jsonl: All ticket snapshots")
    logger.info(f"  - events.jsonl: All events (tool calls, gates, transitions)")


if __name__ == "__main__":
    main()
