"""Unit tests for Interlock PoC components."""

import json
import pytest
from uuid import uuid4
from pydantic import ValidationError

from interlock.schemas.ticket import Ticket
from interlock.fsm import State, transition, TransitionResult
from interlock.gates import IntakeGate, ExtractRequirementsGate, get_gate_for_state
from interlock.storage import ArtifactStore


class TestTicketSchema:
    """Test Ticket Pydantic schema validation."""
    
    def test_valid_ticket(self):
        """Test creating a valid ticket."""
        ticket = Ticket(
            ticket_id="TEST-001",
            title="Test ticket",
            description="Test description",
            state="intake",
            run_id=str(uuid4()),
        )
        assert ticket.ticket_id == "TEST-001"
        assert ticket.state == "intake"
        assert ticket.title == "Test ticket"
    
    def test_ticket_json_serialization(self):
        """Test ticket JSON serialization."""
        ticket = Ticket(
            ticket_id="TEST-002",
            title="Test",
            state="intake",
            run_id=str(uuid4()),
        )
        json_str = ticket.to_json()
        assert isinstance(json_str, str)
        
        # Should be able to parse it back
        data = json.loads(json_str)
        assert data["ticket_id"] == "TEST-002"
    
    def test_ticket_from_json(self):
        """Test creating ticket from JSON."""
        ticket_data = {
            "ticket_id": "TEST-003",
            "title": "Test",
            "state": "intake",
            "run_id": str(uuid4()),
        }
        ticket = Ticket.from_json(json.dumps(ticket_data))
        assert ticket.ticket_id == "TEST-003"
    
    def test_ticket_empty_ticket_id_fails(self):
        """Test that empty ticket_id fails validation."""
        with pytest.raises(ValidationError):
            Ticket(
                ticket_id="",
                title="Test",
                state="intake",
                run_id=str(uuid4()),
            )
    
    def test_ticket_invalid_state_fails(self):
        """Test that invalid state fails validation."""
        with pytest.raises(ValidationError):
            Ticket(
                ticket_id="TEST-004",
                title="Test",
                state="invalid_state",
                run_id=str(uuid4()),
            )


class TestFSM:
    """Test FSM state transitions."""
    
    def test_transition_from_intake(self):
        """Test transition from intake state."""
        result = transition(State.INTAKE)
        assert result.status == "pass"
        assert result.next_state == State.EXTRACT_REQUIREMENTS
        assert "extract" in result.agent_role.lower()
    
    def test_transition_from_extract_requirements(self):
        """Test transition from extract_requirements state."""
        result = transition(State.EXTRACT_REQUIREMENTS)
        assert result.status == "pass"
        assert result.next_state == State.SCOPE_CONTEXT
    
    def test_transition_from_finalize_stops(self):
        """Test that finalize state stops transitions."""
        result = transition(State.FINALIZE)
        assert result.status == "stop"
        assert result.next_state is None
    
    def test_all_states_have_transitions(self):
        """Test that all non-terminal states have valid transitions."""
        non_terminal_states = [
            State.INTAKE,
            State.EXTRACT_REQUIREMENTS,
            State.SCOPE_CONTEXT,
            State.GATHER_EVIDENCE,
            State.PROPOSE_PLAN,
            State.ACT,
        ]
        
        for state in non_terminal_states:
            result = transition(state)
            assert result.status == "pass"
            assert result.next_state is not None


class TestGates:
    """Test validation gates."""
    
    def test_intake_gate_passes_valid_ticket(self):
        """Test IntakeGate passes valid ticket."""
        ticket = Ticket(
            ticket_id="TEST-005",
            title="Test",
            state="intake",
            run_id=str(uuid4()),
        )
        gate = IntakeGate()
        result = gate.validate(ticket)
        assert result.status == "pass"
        assert len(result.reasons) > 0
    
    def test_intake_gate_fails_wrong_state(self):
        """Test IntakeGate fails when state is not intake."""
        ticket = Ticket(
            ticket_id="TEST-006",
            title="Test",
            state="extract_requirements",
            run_id=str(uuid4()),
        )
        gate = IntakeGate()
        result = gate.validate(ticket)
        assert result.status == "retry"
        assert len(result.reasons) > 0
        assert len(result.fixes) > 0
    
    def test_get_gate_for_state(self):
        """Test getting gate for different states."""
        gate1 = get_gate_for_state("intake")
        assert isinstance(gate1, IntakeGate)
        
        gate2 = get_gate_for_state("extract_requirements")
        assert isinstance(gate2, ExtractRequirementsGate)


class TestStorage:
    """Test artifact storage."""
    
    def test_save_and_retrieve_ticket(self, tmp_path):
        """Test saving and retrieving tickets."""
        store = ArtifactStore(storage_dir=str(tmp_path))
        
        ticket = Ticket(
            ticket_id="TEST-007",
            title="Test",
            state="intake",
            run_id=str(uuid4()),
        )
        
        store.save_ticket(ticket)
        
        retrieved = store.get_ticket("TEST-007")
        assert retrieved is not None
        assert retrieved.ticket_id == "TEST-007"
        assert retrieved.state == "intake"
    
    def test_save_event(self, tmp_path):
        """Test saving events."""
        store = ArtifactStore(storage_dir=str(tmp_path))
        run_id = str(uuid4())
        
        store.save_event(
            run_id=run_id,
            event_type="test_event",
            state="intake",
            details={"test": "data"},
        )
        
        # Verify file was created
        assert store.events_file.exists()


class TestEndToEnd:
    """End-to-end integration tests."""
    
    def test_full_workflow_intake_to_extract(self, tmp_path):
        """Test complete workflow from intake to extract_requirements."""
        from interlock.fsm import State, transition
        from interlock.gates import get_gate_for_state
        from interlock.storage import ArtifactStore
        
        store = ArtifactStore(storage_dir=str(tmp_path))
        run_id = str(uuid4())
        
        # Step 1: Create ticket in intake state
        ticket1 = Ticket(
            ticket_id="E2E-001",
            title="End-to-end test",
            state="intake",
            run_id=run_id,
        )
        
        # Validate gate
        gate = get_gate_for_state(ticket1.state)
        gate_result = gate.validate(ticket1)
        assert gate_result.status == "pass"
        
        # Transition
        transition_result = transition(State(ticket1.state))
        assert transition_result.status == "pass"
        assert transition_result.next_state == State.EXTRACT_REQUIREMENTS
        
        # Step 2: Update ticket to next state
        ticket2 = Ticket(
            ticket_id=ticket1.ticket_id,
            title=ticket1.title,
            state=transition_result.next_state.value,
            run_id=run_id,
        )
        
        # Validate gate for new state
        gate2 = get_gate_for_state(ticket2.state)
        gate_result2 = gate2.validate(ticket2)
        assert gate_result2.status == "pass"
        
        # Save both tickets
        store.save_ticket(ticket1)
        store.save_ticket(ticket2)
        
        # Verify both are stored
        retrieved1 = store.get_ticket("E2E-001")
        assert retrieved1 is not None
        assert retrieved1.state == "intake"
        
        # Latest should be extract_requirements
        retrieved2 = store.get_ticket("E2E-001")
        # Since we save both, the last one should be extract_requirements
        # (get_ticket returns the most recent)
        assert retrieved2.state == "extract_requirements"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
