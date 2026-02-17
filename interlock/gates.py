"""Validation gates for Interlock workflow."""

import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from interlock.schemas.ticket import Ticket
from interlock.schemas.responses import GateResult

logger = logging.getLogger(__name__)


class Gate:
    """Base class for validation gates."""
    
    def validate(self, ticket: Ticket) -> GateResult:
        """
        Validate a ticket and return gate result.
        
        Args:
            ticket: Ticket to validate
            
        Returns:
            GateResult with status, reasons, and fixes
        """
        raise NotImplementedError("Subclasses must implement validate method")


class IntakeGate(Gate):
    """Gate for validating ticket intake (state: intake)."""
    
    def validate(self, ticket: Ticket) -> GateResult:
        """
        Validate ticket intake requirements.
        
        Checks:
        - Ticket schema is valid (Pydantic validation)
        - Required fields are present (ticket_id, title, state)
        - State is 'intake'
        - References are resolvable (basic check)
        
        Args:
            ticket: Ticket to validate
            
        Returns:
            GateResult with validation status
        """
        logger.info(f"Validating ticket intake for ticket_id: {ticket.ticket_id}")
        
        reasons = []
        fixes = []
        
        # Check state
        if ticket.state != "intake":
            reasons.append(f"Ticket state must be 'intake', got '{ticket.state}'")
            fixes.append("Set ticket state to 'intake'")
            return GateResult(
                status="retry",
                reasons=reasons,
                fixes=fixes,
            )
        
        # Check required fields (Pydantic already validates, but we check for clarity)
        if not ticket.ticket_id or not ticket.ticket_id.strip():
            reasons.append("ticket_id is required and cannot be empty")
            fixes.append("Provide a non-empty ticket_id")
            return GateResult(
                status="retry",
                reasons=reasons,
                fixes=fixes,
            )
        
        if not ticket.title or not ticket.title.strip():
            reasons.append("title is required and cannot be empty")
            fixes.append("Provide a non-empty title")
            return GateResult(
                status="retry",
                reasons=reasons,
                fixes=fixes,
            )
        
        # Basic reference validation (for PoC, just check format)
        # In full implementation, this would check if ticket references resolve
        if not ticket.ticket_id.replace("-", "").replace("_", "").isalnum():
            reasons.append("ticket_id format may be invalid (should be alphanumeric with dashes/underscores)")
            fixes.append("Ensure ticket_id follows expected format")
            # This is a warning, not a blocker for PoC
            logger.warning(f"Ticket ID format may be unusual: {ticket.ticket_id}")
        
        # All checks passed
        logger.info(f"Intake gate passed for ticket_id: {ticket.ticket_id}")
        return GateResult(
            status="pass",
            reasons=["Ticket intake validation passed"],
            fixes=None,
        )


class ExtractRequirementsGate(Gate):
    """Gate for validating requirements extraction (state: extract_requirements)."""
    
    def validate(self, ticket: Ticket) -> GateResult:
        """
        Validate requirements extraction.
        
        For PoC, this is a placeholder that checks state.
        In full implementation, would validate requirements artifact.
        
        Args:
            ticket: Ticket to validate
            
        Returns:
            GateResult with validation status
        """
        logger.info(f"Validating requirements extraction for ticket_id: {ticket.ticket_id}")
        
        if ticket.state != "extract_requirements":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'extract_requirements', got '{ticket.state}'"],
                fixes=["Set ticket state to 'extract_requirements'"],
            )
        
        # For PoC, just check state
        # In full implementation, would validate requirements artifact exists and is complete
        logger.info(f"Requirements gate passed for ticket_id: {ticket.ticket_id}")
        return GateResult(
            status="pass",
            reasons=["Requirements extraction validation passed"],
            fixes=None,
        )


class GenericGate(Gate):
    """Generic gate for states without specific validation logic."""
    
    def validate(self, ticket: Ticket) -> GateResult:
        """
        Generic validation that just checks ticket schema is valid.
        
        For PoC, this accepts any valid ticket in any state.
        In full implementation, would have state-specific checks.
        
        Args:
            ticket: Ticket to validate
            
        Returns:
            GateResult with validation status
        """
        logger.info(f"Validating ticket (generic gate) for ticket_id: {ticket.ticket_id}, state: {ticket.state}")
        
        # Basic validation: ticket schema is valid (already validated by Pydantic)
        # For PoC, just pass through
        logger.info(f"Generic gate passed for ticket_id: {ticket.ticket_id}")
        return GateResult(
            status="pass",
            reasons=[f"Generic validation passed for state '{ticket.state}'"],
            fixes=None,
        )


def get_gate_for_state(state: str) -> Gate:
    """
    Get the appropriate gate for a given state.
    
    Args:
        state: Current ticket state
        
    Returns:
        Gate instance for the state
    """
    gate_map = {
        "intake": IntakeGate(),
        "extract_requirements": ExtractRequirementsGate(),
        # Add more gates as needed
    }
    
    gate = gate_map.get(state)
    if gate is None:
        # Use generic gate for states without specific validation
        logger.info(f"No specific gate for state '{state}', using generic validation")
        return GenericGate()  # Fallback to generic gate
    
    return gate
