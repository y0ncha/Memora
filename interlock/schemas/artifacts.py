"""Structured artifact schemas used across Interlock FSM states."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RequirementItem(BaseModel):
    """Single acceptance criterion or constraint item."""

    id: str = Field(..., min_length=1, description="Stable requirement identifier")
    text: str = Field(..., min_length=1, description="Requirement text")
    priority: Literal["must", "should", "could"] = Field("must", description="Requirement priority")

    @field_validator("id", "text")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """Ensure values are not blank strings."""
        return value.strip()


class RequirementsArtifact(BaseModel):
    """Pinned requirements extracted from the ticket."""

    acceptance_criteria: list[RequirementItem] = Field(default_factory=list)
    constraints: list[RequirementItem] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)

    @field_validator("unknowns")
    @classmethod
    def validate_unknowns(cls, values: list[str]) -> list[str]:
        """Normalize unknown entries."""
        return [value.strip() for value in values if value and value.strip()]


class RetrievalTarget(BaseModel):
    """Single scoped target to retrieve context from."""

    id: str = Field(..., min_length=1, description="Stable retrieval target id")
    source: Literal["repo", "jira", "confluence", "github", "other"] = Field(..., description="Target source")
    query: str = Field(..., min_length=1, description="Path/query/filter used for retrieval")
    rationale: str = Field(..., min_length=1, description="Why this retrieval target matters")
    related_requirement_ids: list[str] = Field(default_factory=list, description="Linked requirement ids")
    related_unknowns: list[str] = Field(default_factory=list, description="Linked unknowns from requirements artifact")


class ScopeArtifact(BaseModel):
    """Context scope definition for retrieval."""

    targets: list[RetrievalTarget] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """Evidence snippet with provenance."""

    id: str = Field(..., min_length=1, description="Stable evidence identifier")
    source: Literal["repo", "jira", "confluence", "github", "tool_output", "other"] = Field(..., description="Evidence source")
    source_ref: str = Field(..., min_length=1, description="File/path/url/reference id")
    locator: str = Field(..., min_length=1, description="Line range or location hint")
    snippet: str = Field(..., min_length=1, description="Minimal supporting snippet")
    supports: list[str] = Field(default_factory=list, description="Requirement ids or claim ids this evidence supports")


class EvidenceArtifact(BaseModel):
    """Evidence collection for the run."""

    items: list[EvidenceItem] = Field(default_factory=list)


class PlanStep(BaseModel):
    """Single step in a proposed plan."""

    id: str = Field(..., min_length=1, description="Stable plan step identifier")
    title: str = Field(..., min_length=1, description="Step title")
    description: str = Field(..., min_length=1, description="Step intent and expected effect")
    requirement_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    step_type: Literal["delivery", "investigation"] = Field("delivery")


class PlanArtifact(BaseModel):
    """Structured plan tied to requirements and evidence."""

    steps: list[PlanStep] = Field(default_factory=list)


class CandidateOutput(BaseModel):
    """Output produced during execution."""

    id: str = Field(..., min_length=1, description="Output id")
    summary: str = Field(..., min_length=1, description="What was produced")
    covered_requirement_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["candidate", "validated", "blocked"] = Field("candidate")


class ExecutionArtifact(BaseModel):
    """Execution phase artifact with checkpointing support."""

    checkpoints: list[str] = Field(default_factory=list, description="Checkpoint identifiers")
    outputs: list[CandidateOutput] = Field(default_factory=list)


class FinalizationArtifact(BaseModel):
    """Final milestone summary posted at the end of a run."""

    outcome: Literal["done", "blocked", "invalidated"] = Field(..., description="Run outcome")
    milestone_summary: str = Field(..., min_length=1, description="High-signal summary for ticket updates")
    unresolved_items: list[str] = Field(default_factory=list)
