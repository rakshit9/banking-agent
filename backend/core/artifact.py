"""CapabilityArtifact schema, validation, and YAML/JSON serialization."""

from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from backend.core.errors import ArtifactValidationError, ExecutionStatus
from backend.core.models import (
    Action,
    Checkpoint,
    RiskLevel,
)


class InputProperty(BaseModel):
    """Definition of a required or optional runtime capability input parameter."""

    type: str = Field(default="string", description="JSON schema data type (e.g. 'string', 'number', 'boolean')")
    required: bool = Field(default=True, description="Whether this input must be provided")
    description: Optional[str] = Field(None, description="Human-readable purpose of this input")
    sensitive: bool = Field(default=False, description="Whether input contains PII or secrets and must be redacted in logs")
    validation_pattern: Optional[str] = Field(None, description="Regex pattern for parameter format validation")

    model_config = ConfigDict(extra="ignore")


class OutputProperty(BaseModel):
    """Definition of an extracted output returned by the capability."""

    type: str = Field(default="string", description="JSON schema data type")
    description: Optional[str] = Field(None, description="Description of the output data")
    required: bool = Field(default=True, description="Whether the capability must successfully extract this output")
    format: Optional[str] = Field(None, description="Semantic format hint (e.g. 'currency', 'account_number', 'date')")

    model_config = ConfigDict(extra="ignore")


class StepArtifact(BaseModel):
    """Deterministic step definition within a capability workflow."""

    step_id: str = Field(..., description="Unique slug for the step, e.g. 'fill_member_id'")
    description: str = Field(..., description="Human-readable description of what this step achieves")
    action: Action
    checkpoint: Optional[Checkpoint] = Field(None, description="Assertion to verify immediately following this step")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Risk level associated with executing this step")
    optional: bool = Field(default=False, description="If true, step failure does not abort overall execution")
    recovery_hint: Optional[str] = Field(None, description="Guidance or retry strategy if step encounters transient errors")

    model_config = ConfigDict(extra="ignore")


class KnownOutcome(BaseModel):
    """Recognizable non-fatal business or authorization outcome."""

    code: str = Field(..., description="Outcome code, e.g. 'MEMBER_NOT_FOUND', 'PERMISSION_DENIED'")
    description: str = Field(..., description="Explanation of what this outcome means")
    category: ExecutionStatus = Field(default=ExecutionStatus.BUSINESS_OUTCOME, description="Execution classification")
    checkpoint: Checkpoint = Field(..., description="Checkpoint condition that identifies this outcome")

    model_config = ConfigDict(extra="ignore")


class SafetyMetadata(BaseModel):
    """Safety and permission governance for the capability."""

    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    read_only: bool = Field(default=True, description="Whether the workflow performs zero modifying or financial actions")
    human_approval_required: bool = Field(default=False, description="Whether an operator must approve before execution")

    model_config = ConfigDict(extra="ignore")


class CompatibilityMetadata(BaseModel):
    """System and environment compatibility metadata for multi-tenant and surface portability."""

    vendor: Optional[str] = Field(None, description="Software vendor, e.g. 'Northstar Core'")
    product: Optional[str] = Field(None, description="Product suite name")
    product_version: Optional[str] = Field(None, description="Compatible version range")
    surface_type: str = Field(default="web", description="Automation surface type ('web', 'desktop', 'terminal')")

    model_config = ConfigDict(extra="ignore")


def utc_now_iso() -> str:
    """Return a canonical UTC timestamp for artifact metadata."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ProvenanceMetadata(BaseModel):
    """Creation, review, and activation metadata for a capability artifact."""

    source: Optional[str] = Field(None, description="Artifact source, e.g. AI_DISCOVERY or BOOTSTRAP")
    discovery_run_id: Optional[str] = Field(None, description="Discovery run that produced this artifact")
    created_at: Optional[str] = Field(None, description="UTC artifact creation timestamp")
    updated_at: Optional[str] = Field(None, description="UTC timestamp for the latest metadata/content change")
    approved_at: Optional[str] = Field(None, description="UTC timestamp when critic approval was granted")
    activated_at: Optional[str] = Field(None, description="UTC timestamp when this revision became active")
    critic_status: Optional[str] = Field(None, description="Critic review status, e.g. APPROVED")

    model_config = ConfigDict(extra="ignore")


class CapabilityArtifact(BaseModel):
    """Typed, versioned, serializable capability artifact representing an automated workflow."""

    schema_version: str = Field(default="1.0", description="Artifact schema specification version")
    capability_id: str = Field(..., description="Global capability identifier, e.g. 'member.get_savings_balance'")
    name: str = Field(..., description="Human-readable capability title")
    version: str = Field(default="1.0.0", description="SemVer capability revision")
    description: str = Field(..., description="Detailed summary of the automated task")
    target_application: str = Field(..., description="Name of the target banking application")
    compatibility: Optional[CompatibilityMetadata] = None
    inputs: Dict[str, InputProperty] = Field(default_factory=dict)
    outputs: Dict[str, OutputProperty] = Field(default_factory=dict)
    safety: SafetyMetadata = Field(default_factory=SafetyMetadata)
    known_outcomes: List[KnownOutcome] = Field(default_factory=list)
    steps: List[StepArtifact] = Field(default_factory=list)
    success_condition: Optional[Checkpoint] = None
    provenance: Optional[ProvenanceMetadata] = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_capability_integrity(self) -> "CapabilityArtifact":
        """Verify internal consistency between step parameters and declared inputs/outputs."""
        declared_input_keys = set(self.inputs.keys())
        declared_output_keys = set(self.outputs.keys())

        # Validate step bindings
        for step in self.steps:
            if step.action.value_from_input:
                if step.action.value_from_input not in declared_input_keys:
                    raise ValueError(
                        f"Step '{step.step_id}' references input '{step.action.value_from_input}' "
                        f"which is not declared in capability inputs: {list(declared_input_keys)}"
                    )
            if step.action.extract_key:
                if step.action.extract_key not in declared_output_keys:
                    raise ValueError(
                        f"Step '{step.step_id}' extracts key '{step.action.extract_key}' "
                        f"which is not declared in capability outputs: {list(declared_output_keys)}"
                    )

        return self

    def ensure_provenance(
        self,
        *,
        source: Optional[str] = None,
        discovery_run_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> ProvenanceMetadata:
        """Attach provenance if missing while preserving existing timestamps."""
        if self.provenance is None:
            now = created_at or utc_now_iso()
            self.provenance = ProvenanceMetadata(
                source=source,
                discovery_run_id=discovery_run_id,
                created_at=now,
                updated_at=now,
            )
        else:
            if source and not self.provenance.source:
                self.provenance.source = source
            if discovery_run_id and not self.provenance.discovery_run_id:
                self.provenance.discovery_run_id = discovery_run_id
            if created_at and not self.provenance.created_at:
                self.provenance.created_at = created_at
            if self.provenance.created_at and not self.provenance.updated_at:
                self.provenance.updated_at = self.provenance.created_at
        return self.provenance

    def mark_approved(self, approved: bool, *, timestamp: Optional[str] = None) -> None:
        """Record critic status and approval timestamp only when approved."""
        provenance = self.ensure_provenance()
        now = timestamp or utc_now_iso()
        provenance.critic_status = "APPROVED" if approved else "NOT_APPROVED"
        if approved and not provenance.approved_at:
            provenance.approved_at = now
        provenance.updated_at = now

    def mark_activated(self, *, timestamp: Optional[str] = None) -> None:
        """Record when this artifact revision became active."""
        provenance = self.ensure_provenance()
        now = timestamp or utc_now_iso()
        provenance.activated_at = now
        provenance.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        """Convert CapabilityArtifact to a plain Python dictionary."""
        return self.model_dump(mode="json", exclude_none=True)

    def to_json(self, indent: int = 2) -> str:
        """Serialize CapabilityArtifact to formatted JSON string."""
        return self.model_dump_json(indent=indent, exclude_none=True)

    def to_yaml(self) -> str:
        """Serialize CapabilityArtifact to YAML string."""
        data = self.to_dict()
        return yaml.dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)

    def save_yaml(self, path: Union[Path, str]) -> None:
        """Save CapabilityArtifact to a YAML file on disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.to_yaml())

    @classmethod
    def load_yaml(cls, source: Union[Path, str]) -> "CapabilityArtifact":
        """Load and validate CapabilityArtifact from a YAML file path or YAML content string."""
        raw_content: str
        if isinstance(source, Path) or (isinstance(source, str) and ("\n" not in source and Path(source).exists())):
            with open(source, "r", encoding="utf-8") as f:
                raw_content = f.read()
        else:
            raw_content = str(source)

        try:
            parsed = yaml.safe_load(raw_content)
        except Exception as e:
            raise ArtifactValidationError(f"Failed to parse YAML content: {e}") from e

        if not isinstance(parsed, dict):
            raise ArtifactValidationError("Capability artifact YAML must root to a mapping object.")

        try:
            return cls.model_validate(parsed)
        except Exception as e:
            raise ArtifactValidationError(f"Capability artifact validation failed: {e}") from e
