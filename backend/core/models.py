"""Shared Pydantic v2 execution models for Banking Agent automation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.errors import ExecutionStatus, ResultCode


class ActionType(str, Enum):
    """Supported deterministic browser action primitives."""

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    READ = "read"
    EXTRACT = "extract"
    SCROLL = "scroll"
    WAIT = "wait"


class RiskLevel(str, Enum):
    """Risk classification for capability execution and individual steps."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CheckpointType(str, Enum):
    """Supported state verification checkpoints."""

    URL_CONTAINS = "URL_CONTAINS"
    TEXT_VISIBLE = "TEXT_VISIBLE"
    ELEMENT_VISIBLE = "ELEMENT_VISIBLE"
    OUTPUT_PRESENT = "OUTPUT_PRESENT"
    ONE_OF = "ONE_OF"


class ResolutionStatus(str, Enum):
    """Outcome of resolving a locator bundle against active DOM."""

    FOUND = "FOUND"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"


class LocatorBundle(BaseModel):
    """Multi-strategy locator bundle representing intent plus fallbacks.
    
    Resolution priority in resolver:
    1. role + accessible_name
    2. label
    3. stable_attributes
    4. text
    5. css
    6. xpath
    """

    role: Optional[str] = Field(None, description="ARIA role, e.g. 'textbox', 'button', 'link'")
    accessible_name: Optional[str] = Field(None, description="Accessible name/label for the role")
    label: Optional[str] = Field(None, description="Associated form field label text")
    text: Optional[str] = Field(None, description="Exact or normalized visible text")
    stable_attributes: Optional[Dict[str, str]] = Field(None, description="Map of stable HTML attributes (id, name, type)")
    css: Optional[str] = Field(None, description="Standard CSS selector fallback")
    xpath: Optional[str] = Field(None, description="XPath selector fallback")
    visual_hint: Optional[str] = Field(None, description="Human/visual description for documentation or inspection")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_has_at_least_one_strategy(self) -> "LocatorBundle":
        has_strategy = any([
            (self.role and self.accessible_name),
            self.role,
            self.label,
            self.text,
            self.stable_attributes,
            self.css,
            self.xpath,
        ])
        if not has_strategy:
            raise ValueError("LocatorBundle must specify at least one valid locator strategy.")
        return self


class Action(BaseModel):
    """Structured representation of a single browser interaction."""

    action_type: ActionType
    locator: Optional[LocatorBundle] = None
    value: Optional[str] = None
    value_from_input: Optional[str] = Field(None, description="Parameter key to bind at runtime, e.g. 'member_id'")
    target_url: Optional[str] = Field(None, description="Destination URL for NAVIGATE actions")
    extract_key: Optional[str] = Field(None, description="Output key name for EXTRACT actions")
    timeout_ms: Optional[int] = Field(None, description="Optional step-specific timeout override in milliseconds")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_action_requirements(self) -> "Action":
        if self.action_type == ActionType.NAVIGATE and not self.target_url and not self.value and not self.value_from_input:
            raise ValueError("NAVIGATE action must specify target_url or value/value_from_input.")
        if self.action_type in (ActionType.CLICK, ActionType.FILL, ActionType.READ, ActionType.EXTRACT) and not self.locator:
            raise ValueError(f"{self.action_type.value.upper()} action requires a locator bundle.")
        if self.action_type == ActionType.FILL and not self.value and not self.value_from_input:
            raise ValueError("FILL action must specify value or value_from_input.")
        if self.action_type == ActionType.EXTRACT and not self.extract_key:
            raise ValueError("EXTRACT action requires extract_key.")
        return self


class Checkpoint(BaseModel):
    """Deterministic post-action or pre-action assertion."""

    type: CheckpointType
    expected: Optional[str] = Field(None, description="Expected string pattern or key depending on checkpoint type")
    locator: Optional[LocatorBundle] = Field(None, description="Target locator for ELEMENT_VISIBLE checkpoints")
    branches: Optional[List["Checkpoint"]] = Field(None, description="Child checkpoint branches for ONE_OF evaluation")
    outcome_code: Optional[str] = Field(None, description="Mapped result code if this checkpoint or branch matches")
    description: Optional[str] = Field(None, description="Human-readable explanation of the checkpoint requirement")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_checkpoint_structure(self) -> "Checkpoint":
        if self.type == CheckpointType.ONE_OF and not self.branches:
            raise ValueError("ONE_OF checkpoint requires a non-empty list of branch checkpoints.")
        if self.type in (CheckpointType.URL_CONTAINS, CheckpointType.TEXT_VISIBLE, CheckpointType.OUTPUT_PRESENT) and not self.expected:
            raise ValueError(f"{self.type.value} checkpoint requires an expected value.")
        if self.type == CheckpointType.ELEMENT_VISIBLE and not self.locator:
            raise ValueError("ELEMENT_VISIBLE checkpoint requires a locator bundle.")
        return self


class CheckpointResult(BaseModel):
    """Evaluation summary for a single checkpoint."""

    passed: bool
    checkpoint_type: CheckpointType
    expected: Optional[str] = None
    observed: Optional[str] = None
    matched_outcome: Optional[str] = None
    diagnostic: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ResolutionDiagnostic(BaseModel):
    """Detailed diagnostics captured during locator resolution."""

    status: ResolutionStatus
    strategy_used: Optional[str] = None
    strategies_attempted: List[str] = Field(default_factory=list)
    match_count: int = 0
    failure_reason: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class Observation(BaseModel):
    """Sanitized runtime observation of the browser state."""

    url: str
    title: str
    visible_text_summary: Optional[str] = None
    screenshot_path: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = ConfigDict(extra="ignore")


class ExecutionResult(BaseModel):
    """Normalized final outcome of a capability execution."""

    run_id: Optional[str] = None
    capability_id: Optional[str] = None
    status: ExecutionStatus
    outcome_code: ResultCode
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    steps_completed: int = 0
    observation: Optional[Observation] = None
    intervention_request: Optional["InterventionRequest"] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class InterventionRequest(BaseModel):
    """Structured request emitted when human intervention is required."""

    run_id: Optional[str] = None
    capability_id: Optional[str] = None
    current_step: Optional[str] = None
    reason: str
    member_id: Optional[str] = None
    current_url: Optional[str] = None
    required_action: str
    expected_state: Optional[str] = None
    observed_state: Optional[str] = None
    screenshot_path: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = ConfigDict(extra="ignore")
