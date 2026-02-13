"""Validation gates for Interlock workflow."""

import logging

from interlock.schemas.responses import GateResult
from interlock.schemas.ticket import Ticket

logger = logging.getLogger(__name__)


def _requirement_ids(ticket: Ticket) -> set[str]:
    """Return all requirement ids across acceptance criteria and constraints."""
    if ticket.requirements is None:
        return set()
    ac_ids = {item.id for item in ticket.requirements.acceptance_criteria}
    constraint_ids = {item.id for item in ticket.requirements.constraints}
    return ac_ids | constraint_ids


def _evidence_ids(ticket: Ticket) -> set[str]:
    """Return known evidence ids."""
    if ticket.evidence is None:
        return set()
    return {item.id for item in ticket.evidence.items}


class Gate:
    """Base class for validation gates."""

    name = "base_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        """Validate a ticket and return gate result."""
        raise NotImplementedError("Subclasses must implement validate method")


class IntakeGate(Gate):
    """Gate for validating ticket intake (state: intake)."""

    name = "intake_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.info("Validating intake for ticket_id=%s", ticket.ticket_id)

        if ticket.state != "intake":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'intake', got '{ticket.state}'"],
                fixes=["Set ticket state to 'intake' before calling interlock_next_step"],
            )

        if not ticket.ticket_id.replace("-", "").replace("_", "").isalnum():
            return GateResult(
                status="retry",
                reasons=["ticket_id must be alphanumeric with optional dashes/underscores"],
                fixes=["Provide ticket_id in format like PROJ-123"],
            )

        return GateResult(status="pass", reasons=["Ticket intake validation passed"], fixes=None)


class ExtractRequirementsGate(Gate):
    """Gate for validating requirements extraction (state: extract_requirements)."""

    name = "extract_requirements_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.info("Validating requirements for ticket_id=%s", ticket.ticket_id)

        if ticket.state != "extract_requirements":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'extract_requirements', got '{ticket.state}'"],
                fixes=["Set ticket state to 'extract_requirements'"],
            )

        if ticket.requirements is None:
            return GateResult(
                status="retry",
                reasons=["requirements artifact is missing"],
                fixes=["Provide requirements.acceptance_criteria, requirements.constraints, and requirements.unknowns"],
            )

        if not ticket.requirements.acceptance_criteria:
            return GateResult(
                status="retry",
                reasons=["requirements.acceptance_criteria must include at least one item"],
                fixes=["Extract at least one concrete acceptance criterion"],
            )

        all_ids = [item.id for item in ticket.requirements.acceptance_criteria + ticket.requirements.constraints]
        if len(all_ids) != len(set(all_ids)):
            return GateResult(
                status="retry",
                reasons=["Requirement IDs must be unique across acceptance_criteria and constraints"],
                fixes=["Use unique IDs such as AC-1, AC-2, C-1"],
            )

        return GateResult(status="pass", reasons=["Requirements are pinned and usable"], fixes=None)


class ScopeContextGate(Gate):
    """Gate for validating context scoping (state: scope_context)."""

    name = "scope_context_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.info("Validating scope for ticket_id=%s", ticket.ticket_id)

        if ticket.state != "scope_context":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'scope_context', got '{ticket.state}'"],
                fixes=["Set ticket state to 'scope_context'"],
            )

        if ticket.scope is None or not ticket.scope.targets:
            return GateResult(
                status="retry",
                reasons=["scope.targets must include at least one retrieval target"],
                fixes=["Add scoped targets with source, query, rationale, and requirement/unknown links"],
            )

        req_ids = _requirement_ids(ticket)
        for target in ticket.scope.targets:
            if not target.related_requirement_ids and not target.related_unknowns:
                return GateResult(
                    status="retry",
                    reasons=[f"Scope target '{target.id}' must link to at least one requirement or unknown"],
                    fixes=["Populate related_requirement_ids or related_unknowns for each target"],
                )
            unknown_req_ids = set(target.related_requirement_ids) - req_ids
            if req_ids and unknown_req_ids:
                return GateResult(
                    status="retry",
                    reasons=[f"Scope target '{target.id}' references unknown requirement ids: {sorted(unknown_req_ids)}"],
                    fixes=["Use requirement ids defined in requirements.acceptance_criteria/constraints"],
                )

        return GateResult(status="pass", reasons=["Scoped retrieval targets are explicit and linked"], fixes=None)


class GatherEvidenceGate(Gate):
    """Gate for validating evidence gathering (state: gather_evidence)."""

    name = "gather_evidence_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.info("Validating evidence for ticket_id=%s", ticket.ticket_id)

        if ticket.state != "gather_evidence":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'gather_evidence', got '{ticket.state}'"],
                fixes=["Set ticket state to 'gather_evidence'"],
            )

        if ticket.evidence is None or not ticket.evidence.items:
            return GateResult(
                status="retry",
                reasons=["evidence.items must include at least one evidence snippet"],
                fixes=["Add evidence items with source_ref, locator, snippet, and supports"],
            )

        req_ids = _requirement_ids(ticket)
        for item in ticket.evidence.items:
            if not item.supports:
                return GateResult(
                    status="retry",
                    reasons=[f"Evidence item '{item.id}' must support at least one requirement or claim"],
                    fixes=["Populate evidence.supports with requirement IDs or claim IDs"],
                )
            if req_ids:
                unknown_support = set(item.supports) - req_ids
                if unknown_support:
                    return GateResult(
                        status="retry",
                        reasons=[f"Evidence item '{item.id}' supports unknown requirement ids: {sorted(unknown_support)}"],
                        fixes=["Link evidence.supports to known requirement IDs"],
                    )

        return GateResult(status="pass", reasons=["Evidence items are traceable and linked"], fixes=None)


class ProposePlanGate(Gate):
    """Gate for validating plan proposal (state: propose_plan)."""

    name = "propose_plan_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.info("Validating plan for ticket_id=%s", ticket.ticket_id)

        if ticket.state != "propose_plan":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'propose_plan', got '{ticket.state}'"],
                fixes=["Set ticket state to 'propose_plan'"],
            )

        if ticket.plan is None or not ticket.plan.steps:
            return GateResult(
                status="retry",
                reasons=["plan.steps must include at least one actionable step"],
                fixes=["Add plan steps tied to requirements and evidence"],
            )

        req_ids = _requirement_ids(ticket)
        ev_ids = _evidence_ids(ticket)
        covered_req_ids: set[str] = set()

        for step in ticket.plan.steps:
            if step.step_type == "delivery" and not step.requirement_ids:
                return GateResult(
                    status="retry",
                    reasons=[f"Delivery step '{step.id}' must map to at least one requirement"],
                    fixes=["Populate step.requirement_ids or mark step_type as 'investigation'"],
                )
            if not step.evidence_ids:
                return GateResult(
                    status="retry",
                    reasons=[f"Plan step '{step.id}' must cite evidence ids"],
                    fixes=["Populate step.evidence_ids using evidence item IDs"],
                )

            unknown_req_ids = set(step.requirement_ids) - req_ids
            if req_ids and unknown_req_ids:
                return GateResult(
                    status="retry",
                    reasons=[f"Plan step '{step.id}' references unknown requirements: {sorted(unknown_req_ids)}"],
                    fixes=["Use requirement ids declared in requirements artifact"],
                )

            unknown_ev_ids = set(step.evidence_ids) - ev_ids
            if ev_ids and unknown_ev_ids:
                return GateResult(
                    status="retry",
                    reasons=[f"Plan step '{step.id}' references unknown evidence ids: {sorted(unknown_ev_ids)}"],
                    fixes=["Use evidence ids declared in evidence artifact"],
                )

            covered_req_ids.update(step.requirement_ids)

        missing = req_ids - covered_req_ids
        if req_ids and missing:
            return GateResult(
                status="retry",
                reasons=[f"Plan does not cover all requirements; missing: {sorted(missing)}"],
                fixes=["Add or adjust plan steps so every requirement is covered"],
            )

        return GateResult(status="pass", reasons=["Plan is actionable and requirement-linked"], fixes=None)


class ActGate(Gate):
    """Gate for validating execution outputs (state: act)."""

    name = "act_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.info("Validating execution for ticket_id=%s", ticket.ticket_id)

        if ticket.state != "act":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'act', got '{ticket.state}'"],
                fixes=["Set ticket state to 'act'"],
            )

        if ticket.execution is None:
            return GateResult(
                status="retry",
                reasons=["execution artifact is missing"],
                fixes=["Provide execution outputs and checkpoints"],
            )

        if not ticket.execution.outputs:
            return GateResult(
                status="retry",
                reasons=["execution.outputs must include at least one candidate output"],
                fixes=["Add candidate outputs with covered requirements and evidence links"],
            )

        if not ticket.execution.checkpoints:
            return GateResult(
                status="retry",
                reasons=["execution.checkpoints is empty"],
                fixes=["Record at least one checkpoint before progressing"],
            )

        req_ids = _requirement_ids(ticket)
        ev_ids = _evidence_ids(ticket)
        covered_req_ids: set[str] = set()

        for output in ticket.execution.outputs:
            covered_req_ids.update(output.covered_requirement_ids)
            unknown_req_ids = set(output.covered_requirement_ids) - req_ids
            if req_ids and unknown_req_ids:
                return GateResult(
                    status="retry",
                    reasons=[f"Output '{output.id}' covers unknown requirements: {sorted(unknown_req_ids)}"],
                    fixes=["Use requirement ids declared in requirements artifact"],
                )
            unknown_ev_ids = set(output.evidence_ids) - ev_ids
            if ev_ids and unknown_ev_ids:
                return GateResult(
                    status="retry",
                    reasons=[f"Output '{output.id}' cites unknown evidence ids: {sorted(unknown_ev_ids)}"],
                    fixes=["Use evidence ids declared in evidence artifact"],
                )

        missing = req_ids - covered_req_ids
        if req_ids and missing:
            return GateResult(
                status="retry",
                reasons=[f"Execution outputs do not cover all requirements; missing: {sorted(missing)}"],
                fixes=["Add outputs or updates that cover missing requirements"],
            )

        return GateResult(status="pass", reasons=["Execution outputs are grounded and coverage-complete"], fixes=None)


class FinalizeGate(Gate):
    """Gate for validating finalization artifact (state: finalize)."""

    name = "finalize_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.info("Validating finalization for ticket_id=%s", ticket.ticket_id)

        if ticket.state != "finalize":
            return GateResult(
                status="retry",
                reasons=[f"Ticket state must be 'finalize', got '{ticket.state}'"],
                fixes=["Set ticket state to 'finalize'"],
            )

        if ticket.finalization is None:
            return GateResult(
                status="retry",
                reasons=["finalization artifact is missing"],
                fixes=["Provide finalization.outcome and finalization.milestone_summary"],
            )

        if ticket.finalization.outcome == "done" and ticket.execution is not None:
            req_ids = _requirement_ids(ticket)
            covered_req_ids = {
                requirement_id
                for output in ticket.execution.outputs
                for requirement_id in output.covered_requirement_ids
            }
            missing = req_ids - covered_req_ids
            if req_ids and missing:
                return GateResult(
                    status="stop",
                    reasons=[f"Cannot finalize as done; requirements remain uncovered: {sorted(missing)}"],
                    fixes=["Set outcome to blocked/invalidated or provide missing execution coverage"],
                )

        return GateResult(status="pass", reasons=["Finalization summary is present"], fixes=None)


class GenericGate(Gate):
    """Fallback gate for unknown states."""

    name = "generic_gate"

    def validate(self, ticket: Ticket) -> GateResult:
        logger.warning("Generic gate used for state=%s", ticket.state)
        return GateResult(
            status="retry",
            reasons=[f"No specific gate configured for state '{ticket.state}'"],
            fixes=["Use one of the known FSM states and corresponding artifacts"],
        )


def get_gate_for_state(state: str) -> Gate:
    """Get the appropriate gate for a given state."""
    gate_map = {
        "intake": IntakeGate(),
        "extract_requirements": ExtractRequirementsGate(),
        "scope_context": ScopeContextGate(),
        "gather_evidence": GatherEvidenceGate(),
        "propose_plan": ProposePlanGate(),
        "act": ActGate(),
        "finalize": FinalizeGate(),
    }
    return gate_map.get(state, GenericGate())
