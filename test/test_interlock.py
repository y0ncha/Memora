"""Unit tests for Interlock PoC components."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from interlock.fsm import State, transition
from interlock.gates import (
    ActGate,
    ExtractRequirementsGate,
    FinalizeGate,
    GatherEvidenceGate,
    IntakeGate,
    ProposePlanGate,
    ScopeContextGate,
    get_gate_for_state,
)
from interlock.schemas.ticket import Ticket
from interlock.storage import ArtifactStore


def _base_ticket(state: str) -> Ticket:
    """Create a valid ticket skeleton for tests."""
    return Ticket(
        ticket_id="TEST-001",
        title="Interlock gate validation test",
        state=state,
        run_id=str(uuid4()),
    )


def _ticket_with_requirements() -> Ticket:
    """Create ticket with pinned requirements."""
    return Ticket(
        ticket_id="TEST-001",
        title="Interlock gate validation test",
        state="extract_requirements",
        run_id=str(uuid4()),
        requirements={
            "acceptance_criteria": [
                {"id": "AC-1", "text": "User can log in"},
                {"id": "AC-2", "text": "Invalid password shows error"},
            ],
            "constraints": [{"id": "C-1", "text": "Must use existing auth service"}],
            "unknowns": ["Should MFA be mandatory?"],
        },
    )


def _ticket_with_scope() -> Ticket:
    """Create ticket prepared for scope_context gate."""
    base = _ticket_with_requirements()
    payload = base.model_dump(mode="json")
    payload["state"] = "scope_context"
    payload["scope"] = {
        "targets": [
            {
                "id": "T-1",
                "source": "repo",
                "query": "src/auth/**",
                "rationale": "Auth logic likely lives here",
                "related_requirement_ids": ["AC-1", "AC-2"],
                "related_unknowns": [],
            },
            {
                "id": "T-2",
                "source": "jira",
                "query": "PROJ-123 comments",
                "rationale": "Clarify MFA unknown",
                "related_requirement_ids": [],
                "related_unknowns": ["Should MFA be mandatory?"],
            },
        ]
    }
    return Ticket(**payload)


def _ticket_with_evidence() -> Ticket:
    """Create ticket prepared for gather_evidence gate."""
    base = _ticket_with_scope()
    payload = base.model_dump(mode="json")
    payload["state"] = "gather_evidence"
    payload["evidence"] = {
        "items": [
            {
                "id": "E-1",
                "source": "repo",
                "source_ref": "src/auth/login.py",
                "locator": "L20-L38",
                "snippet": "login() returns token on valid credentials",
                "supports": ["AC-1"],
            },
            {
                "id": "E-2",
                "source": "repo",
                "source_ref": "src/auth/login.py",
                "locator": "L40-L56",
                "snippet": "invalid password path returns 401 with message",
                "supports": ["AC-2"],
            },
            {
                "id": "E-3",
                "source": "confluence",
                "source_ref": "AUTH-ARCH",
                "locator": "Section 2",
                "snippet": "Auth service must be reused",
                "supports": ["C-1"],
            },
        ]
    }
    return Ticket(**payload)


def _ticket_with_plan() -> Ticket:
    """Create ticket prepared for propose_plan gate."""
    base = _ticket_with_evidence()
    payload = base.model_dump(mode="json")
    payload["state"] = "propose_plan"
    payload["plan"] = {
        "steps": [
            {
                "id": "P-1",
                "title": "Implement login flow",
                "description": "Wire login endpoint to auth service",
                "requirement_ids": ["AC-1", "C-1"],
                "evidence_ids": ["E-1", "E-3"],
                "step_type": "delivery",
            },
            {
                "id": "P-2",
                "title": "Handle invalid credentials",
                "description": "Return structured 401 error payload",
                "requirement_ids": ["AC-2"],
                "evidence_ids": ["E-2"],
                "step_type": "delivery",
            },
        ]
    }
    return Ticket(**payload)


def _ticket_with_execution() -> Ticket:
    """Create ticket prepared for act gate."""
    base = _ticket_with_plan()
    payload = base.model_dump(mode="json")
    payload["state"] = "act"
    payload["execution"] = {
        "checkpoints": ["cp-login-controller", "cp-auth-service-integration"],
        "outputs": [
            {
                "id": "O-1",
                "summary": "Login endpoint supports successful authentication",
                "covered_requirement_ids": ["AC-1", "C-1"],
                "evidence_ids": ["E-1", "E-3"],
                "status": "candidate",
            },
            {
                "id": "O-2",
                "summary": "Invalid credentials return 401 with message",
                "covered_requirement_ids": ["AC-2"],
                "evidence_ids": ["E-2"],
                "status": "candidate",
            },
        ],
    }
    return Ticket(**payload)


def _ticket_with_finalization() -> Ticket:
    """Create ticket prepared for finalize gate."""
    base = _ticket_with_execution()
    payload = base.model_dump(mode="json")
    payload["state"] = "finalize"
    payload["finalization"] = {
        "outcome": "done",
        "milestone_summary": "Requirements pinned, evidence gathered, plan executed with checkpoints",
        "unresolved_items": [],
    }
    return Ticket(**payload)


class TestTicketSchema:
    """Test Ticket Pydantic schema validation."""

    def test_valid_ticket(self):
        """Test creating a valid ticket."""
        ticket = _base_ticket("intake")
        assert ticket.ticket_id == "TEST-001"
        assert ticket.state == "intake"

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

    def test_transition_from_finalize_stops(self):
        """Test that finalize state stops transitions."""
        result = transition(State.FINALIZE)
        assert result.status == "stop"
        assert result.next_state is None


class TestGates:
    """Test validation gates."""

    def test_intake_gate_passes_valid_ticket(self):
        """Test IntakeGate passes valid ticket."""
        gate = IntakeGate()
        result = gate.validate(_base_ticket("intake"))
        assert result.status == "pass"

    def test_extract_requirements_gate_requires_artifact(self):
        """Test ExtractRequirementsGate retries without requirements artifact."""
        gate = ExtractRequirementsGate()
        result = gate.validate(_base_ticket("extract_requirements"))
        assert result.status == "retry"
        assert "requirements artifact is missing" in result.reasons

    def test_scope_context_gate_valid(self):
        """Test ScopeContextGate passes when targets are linked."""
        gate = ScopeContextGate()
        result = gate.validate(_ticket_with_scope())
        assert result.status == "pass"

    def test_gather_evidence_gate_valid(self):
        """Test GatherEvidenceGate passes with grounded evidence."""
        gate = GatherEvidenceGate()
        result = gate.validate(_ticket_with_evidence())
        assert result.status == "pass"

    def test_propose_plan_gate_valid(self):
        """Test ProposePlanGate passes for coverage-complete plan."""
        gate = ProposePlanGate()
        result = gate.validate(_ticket_with_plan())
        assert result.status == "pass"

    def test_act_gate_requires_checkpoints(self):
        """Test ActGate fails when checkpoints are missing."""
        ticket = _ticket_with_execution()
        ticket.execution = ticket.execution.model_copy(update={"checkpoints": []})
        gate = ActGate()
        result = gate.validate(ticket)
        assert result.status == "retry"
        assert "execution.checkpoints is empty" in result.reasons

    def test_finalize_gate_valid(self):
        """Test FinalizeGate passes for valid finalization artifact."""
        gate = FinalizeGate()
        result = gate.validate(_ticket_with_finalization())
        assert result.status == "pass"

    def test_get_gate_for_state(self):
        """Test gate dispatch for all workflow states."""
        assert isinstance(get_gate_for_state("intake"), IntakeGate)
        assert isinstance(get_gate_for_state("extract_requirements"), ExtractRequirementsGate)
        assert isinstance(get_gate_for_state("scope_context"), ScopeContextGate)
        assert isinstance(get_gate_for_state("gather_evidence"), GatherEvidenceGate)
        assert isinstance(get_gate_for_state("propose_plan"), ProposePlanGate)
        assert isinstance(get_gate_for_state("act"), ActGate)
        assert isinstance(get_gate_for_state("finalize"), FinalizeGate)


class TestStorage:
    """Test artifact storage."""

    def test_save_and_retrieve_ticket(self, tmp_path):
        """Test saving and retrieving latest ticket snapshot."""
        store = ArtifactStore(storage_dir=str(tmp_path))
        run_id = str(uuid4())

        intake_ticket = Ticket(
            ticket_id="TEST-007",
            title="Test",
            state="intake",
            run_id=run_id,
        )
        extract_ticket = Ticket(
            ticket_id="TEST-007",
            title="Test",
            state="extract_requirements",
            run_id=run_id,
            requirements={
                "acceptance_criteria": [{"id": "AC-1", "text": "Example"}],
                "constraints": [],
                "unknowns": [],
            },
        )

        store.save_ticket(intake_ticket)
        store.save_ticket(extract_ticket)

        retrieved = store.get_ticket("TEST-007")
        assert retrieved is not None
        assert retrieved.state == "extract_requirements"

    def test_save_event(self, tmp_path):
        """Test saving events."""
        store = ArtifactStore(storage_dir=str(tmp_path))
        store.save_event(
            run_id=str(uuid4()),
            event_type="test_event",
            state="intake",
            details={"test": "data"},
        )
        assert store.events_file.exists()


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_gate_and_transition_sequence(self):
        """Test full validation and transition path through all non-terminal states."""
        tickets = [
            _base_ticket("intake"),
            _ticket_with_requirements(),
            _ticket_with_scope(),
            _ticket_with_evidence(),
            _ticket_with_plan(),
            _ticket_with_execution(),
            _ticket_with_finalization(),
        ]

        expected_next = [
            State.EXTRACT_REQUIREMENTS,
            State.SCOPE_CONTEXT,
            State.GATHER_EVIDENCE,
            State.PROPOSE_PLAN,
            State.ACT,
            State.FINALIZE,
            None,
        ]

        for ticket, next_state in zip(tickets, expected_next):
            gate = get_gate_for_state(ticket.state)
            gate_result = gate.validate(ticket)
            assert gate_result.status == "pass"

            result = transition(State(ticket.state))
            if next_state is None:
                assert result.status == "stop"
                assert result.next_state is None
            else:
                assert result.status == "pass"
                assert result.next_state == next_state
