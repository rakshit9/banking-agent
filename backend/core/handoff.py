"""Human handoff coordinator, control ownership state machine, and browser session registry."""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from backend.automation.browser import BrowserController
from backend.automation.checkpoints import CheckpointEvaluator
from backend.core.artifact import CapabilityArtifact
from backend.core.errors import BankingAgentError, ResultCode
from backend.core.models import Checkpoint, CheckpointType, ExecutionStatus, RiskLevel
from backend.services.evidence import EvidenceRecorder


class ControlOwner(str, Enum):
    """Authority currently holding control of the active browser session."""

    AUTOMATION = "AUTOMATION"
    HUMAN = "HUMAN"


class RunStatus(str, Enum):
    """Lifecycle state of an execution run."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    RESUMING = "RESUMING"
    SUCCESS = "SUCCESS"
    BUSINESS_OUTCOME = "BUSINESS_OUTCOME"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InterventionStatus(str, Enum):
    """Status of an escalated human intervention."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Intervention(BaseModel):
    """Structured human intervention record."""

    intervention_id: str
    run_id: str
    capability_id: str
    capability_version: str = "1.0.0"
    step_id: Optional[str] = None
    reason: str
    human_readable_summary: str
    expected_state: Optional[str] = None
    observed_state: Optional[str] = None
    control_owner: ControlOwner = ControlOwner.AUTOMATION
    status: InterventionStatus = InterventionStatus.PENDING
    screenshot_path: Optional[str] = None
    resume_checkpoint: Optional[Checkpoint] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolution_notes: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class RunRecord(BaseModel):
    """In-memory representation of an automation or discovery execution run."""

    run_id: str
    mode: str = "replay"
    capability_id: str
    status: RunStatus = RunStatus.QUEUED
    current_step: Optional[str] = None
    control_owner: ControlOwner = ControlOwner.AUTOMATION
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    outcome_code: Optional[str] = None
    intervention_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = ConfigDict(extra="ignore")


class ActiveSession:
    """Holds active runtime components for an executing run."""

    def __init__(
        self,
        run_id: str,
        browser: BrowserController,
        artifact: CapabilityArtifact,
        inputs: Dict[str, Any],
        step_index: int = 0,
        extracted_data: Optional[Dict[str, Any]] = None,
    ):
        self.run_id = run_id
        self.browser = browser
        self.artifact = artifact
        self.inputs = inputs
        self.step_index = step_index
        self.extracted_data = extracted_data or {}
        self.last_activity = datetime.now(timezone.utc)


class HandoffCoordinator:
    """Coordinates control ownership transitions, intervention lifecycles, and session persistence."""

    def __init__(self, evidence_dir: Optional[Path] = None):
        self.evidence_dir = evidence_dir or Path("evidence") / "handoff"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        
        self.runs: Dict[str, RunRecord] = {}
        self.interventions: Dict[str, Intervention] = {}
        self.active_sessions: Dict[str, ActiveSession] = {}
        self._lock = asyncio.Lock()

    # --- Session Management ---

    async def register_session(
        self,
        run_id: str,
        browser: BrowserController,
        artifact: CapabilityArtifact,
        inputs: Dict[str, Any],
        step_index: int = 0,
        extracted_data: Optional[Dict[str, Any]] = None,
    ) -> ActiveSession:
        async with self._lock:
            session = ActiveSession(
                run_id=run_id,
                browser=browser,
                artifact=artifact,
                inputs=inputs,
                step_index=step_index,
                extracted_data=extracted_data,
            )
            self.active_sessions[run_id] = session
            return session

    def get_session(self, run_id: str) -> Optional[ActiveSession]:
        return self.active_sessions.get(run_id)

    async def release_session(self, run_id: str) -> None:
        async with self._lock:
            session = self.active_sessions.pop(run_id, None)
            if session and session.browser:
                try:
                    await session.browser.close()
                except Exception:
                    pass

    # --- Run Record Management ---

    def create_run_record(
        self,
        run_id: str,
        capability_id: str,
        mode: str = "replay",
        inputs: Optional[Dict[str, Any]] = None,
    ) -> RunRecord:
        record = RunRecord(
            run_id=run_id,
            mode=mode,
            capability_id=capability_id,
            status=RunStatus.RUNNING,
            inputs=inputs or {},
        )
        self.runs[run_id] = record
        return record

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self.runs.get(run_id)

    # --- Intervention & Control Ownership State Machine ---

    async def create_intervention(
        self,
        run_id: str,
        capability_id: str,
        reason: str,
        human_readable_summary: str,
        step_id: Optional[str] = None,
        expected_state: Optional[str] = None,
        observed_state: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        resume_checkpoint: Optional[Checkpoint] = None,
    ) -> Intervention:
        """Pause automation and create a pending intervention for human takeover."""
        async with self._lock:
            run = self.runs.get(run_id)
            if not run:
                raise BankingAgentError(f"Run '{run_id}' not found.", code=ResultCode.TARGET_NOT_FOUND)

            if run.status in (RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.CANCELLED):
                raise BankingAgentError(
                    f"Cannot create intervention for completed/terminal run '{run_id}'.",
                    code=ResultCode.POLICY_VIOLATION,
                )

            intervention_id = f"intv_{uuid.uuid4().hex[:8]}"
            intervention = Intervention(
                intervention_id=intervention_id,
                run_id=run_id,
                capability_id=capability_id,
                step_id=step_id,
                reason=reason,
                human_readable_summary=human_readable_summary,
                expected_state=expected_state,
                observed_state=observed_state,
                screenshot_path=screenshot_path,
                resume_checkpoint=resume_checkpoint,
                control_owner=ControlOwner.AUTOMATION,
                status=InterventionStatus.PENDING,
            )

            self.interventions[intervention_id] = intervention

            # Update run state: AUTOMATION -> PAUSED (HUMAN_REQUIRED)
            run.status = RunStatus.HUMAN_REQUIRED
            run.control_owner = ControlOwner.AUTOMATION
            run.current_step = step_id
            run.intervention_id = intervention_id
            run.updated_at = datetime.now(timezone.utc).isoformat()

            # Record handoff evidence
            evidence = EvidenceRecorder(run_id, mode="handoff", output_dir=self.evidence_dir)
            evidence.record_event(
                event="HUMAN_REQUIRED",
                capability_id=capability_id,
                step_id=step_id,
                details={
                    "intervention_id": intervention_id,
                    "reason": reason,
                    "screenshot_path": screenshot_path,
                },
            )

            return intervention

    async def take_control(self, intervention_id: str) -> Intervention:
        """Transfer browser control authority from AUTOMATION -> HUMAN."""
        async with self._lock:
            intervention = self.interventions.get(intervention_id)
            if not intervention:
                raise BankingAgentError(f"Intervention '{intervention_id}' not found.", code=ResultCode.TARGET_NOT_FOUND)

            run = self.runs.get(intervention.run_id)
            if not run:
                raise BankingAgentError(f"Run '{intervention.run_id}' not found.", code=ResultCode.TARGET_NOT_FOUND)

            if intervention.status != InterventionStatus.PENDING:
                raise BankingAgentError(
                    f"Cannot take control of intervention with status '{intervention.status.value}'.",
                    code=ResultCode.POLICY_VIOLATION,
                )

            if intervention.control_owner == ControlOwner.HUMAN:
                raise BankingAgentError(
                    "Control is already owned by HUMAN operator.",
                    code=ResultCode.POLICY_VIOLATION,
                )

            # State transition: PAUSED -> HUMAN
            intervention.control_owner = ControlOwner.HUMAN
            intervention.status = InterventionStatus.IN_PROGRESS

            run.control_owner = ControlOwner.HUMAN
            run.status = RunStatus.PAUSED
            run.updated_at = datetime.now(timezone.utc).isoformat()

            # Record evidence
            evidence = EvidenceRecorder(run.run_id, mode="handoff", output_dir=self.evidence_dir)
            evidence.record_event(
                event="CONTROL_TRANSFERRED_TO_HUMAN",
                capability_id=intervention.capability_id,
                step_id=intervention.step_id,
                details={"intervention_id": intervention_id, "control_owner": "HUMAN"},
            )

            return intervention

    async def resume_automation(
        self,
        intervention_id: str,
        resolution_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate post-human browser state and resume deterministic replay on same session."""
        async with self._lock:
            intervention = self.interventions.get(intervention_id)
            if not intervention:
                raise BankingAgentError(f"Intervention '{intervention_id}' not found.", code=ResultCode.TARGET_NOT_FOUND)

            run = self.runs.get(intervention.run_id)
            if not run:
                raise BankingAgentError(f"Run '{intervention.run_id}' not found.", code=ResultCode.TARGET_NOT_FOUND)

            if intervention.control_owner != ControlOwner.HUMAN:
                raise BankingAgentError(
                    f"Cannot resume: current control owner is '{intervention.control_owner.value}', expected 'HUMAN'.",
                    code=ResultCode.POLICY_VIOLATION,
                )

            session = self.active_sessions.get(intervention.run_id)
            if not session or not session.browser:
                raise BankingAgentError(
                    f"Live browser session for run '{intervention.run_id}' is no longer active.",
                    code=ResultCode.SYSTEM_ERROR,
                )

            # Re-observe live browser session state
            page = session.browser.page
            current_obs = await session.browser.get_observation()

            # Evaluate resume checkpoint: Verify manual roadblock is cleared
            passed_resume = False
            diagnostic = "Resuming verification"
            
            # Check if verification banner is gone or member record is visible
            body_text = await page.inner_text("body")
            if "Additional Verification Required" not in body_text and ("Member Record Overview" in body_text or "View Savings" in body_text or "Savings Account Detail" in body_text):
                passed_resume = True
                diagnostic = "Manual verification obstacle cleared; target profile is visible."
            elif intervention.resume_checkpoint:
                cp_eval = await CheckpointEvaluator.evaluate(intervention.resume_checkpoint, page)
                passed_resume = cp_eval.passed
                diagnostic = cp_eval.diagnostic or ""

            if not passed_resume:
                # Failed resume check: retain HUMAN control
                evidence = EvidenceRecorder(run.run_id, mode="handoff", output_dir=self.evidence_dir)
                evidence.record_event(
                    event="RESUME_CHECKPOINT_FAILED",
                    capability_id=intervention.capability_id,
                    step_id=intervention.step_id,
                    details={"diagnostic": diagnostic},
                )
                raise BankingAgentError(
                    f"Resume validation failed: {diagnostic}. Human intervention remains required.",
                    code=ResultCode.CHECKPOINT_FAILED,
                )

            # State transition: HUMAN -> RESUMING -> AUTOMATION
            intervention.control_owner = ControlOwner.AUTOMATION
            intervention.status = InterventionStatus.RESOLVED
            intervention.resolved_at = datetime.now(timezone.utc).isoformat()
            intervention.resolution_notes = resolution_notes or "Operator completed manual verification."

            run.control_owner = ControlOwner.AUTOMATION
            run.status = RunStatus.RESUMING
            run.updated_at = datetime.now(timezone.utc).isoformat()

            # Record evidence
            evidence = EvidenceRecorder(run.run_id, mode="handoff", output_dir=self.evidence_dir)
            evidence.record_event(
                event="CONTROL_RETURNED_TO_AUTOMATION",
                capability_id=intervention.capability_id,
                step_id=intervention.step_id,
                details={"diagnostic": diagnostic, "intervention_id": intervention_id},
            )

        # 4. Resume deterministic replay outside lock
        return await self._continue_replay_after_resume(session, run)

    async def _continue_replay_after_resume(self, session: ActiveSession, run: RunRecord) -> Dict[str, Any]:
        """Execute remaining deterministic capability steps on the SAME active browser context."""
        artifact = session.artifact
        browser = session.browser
        inputs = session.inputs

        # Identify remaining steps following verification (e.g. click View Savings, extract savings balance)
        start_index = 0
        for idx, step in enumerate(artifact.steps):
            if step.step_id in ("click_view_savings", "open_savings", "extract_savings_balance", "extract_balance"):
                start_index = idx
                break

        evidence = EvidenceRecorder(run.run_id, mode="handoff", output_dir=self.evidence_dir)

        try:
            for idx in range(start_index, len(artifact.steps)):
                step = artifact.steps[idx]
                
                # Execute action
                if step.action.action_type == "click":
                    await browser.click(step.action.locator)
                elif step.action.action_type == "extract":
                    val = await browser.read_text(step.action.locator)
                    # Numeric extraction
                    import re
                    sanitized = re.sub(r"[^\d.-]", "", val)
                    num_val = float(sanitized) if "." in sanitized else int(sanitized)
                    session.extracted_data[step.action.extract_key] = num_val

                evidence.record_event(
                    event="RESUMED_ACTION_EXECUTED",
                    capability_id=artifact.capability_id,
                    step_id=step.step_id,
                )

            # Success
            run.status = RunStatus.SUCCESS
            run.outputs = session.extracted_data
            run.updated_at = datetime.now(timezone.utc).isoformat()

            evidence.record_event(
                event="RUN_SUCCEEDED_AFTER_HANDOFF",
                capability_id=artifact.capability_id,
                details={"outputs": run.outputs},
            )

            return {
                "run_id": run.run_id,
                "status": "SUCCESS",
                "outputs": run.outputs,
                "control_owner": "AUTOMATION",
            }
        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            return {"run_id": run.run_id, "status": "FAILED", "error": str(e)}
        finally:
            await self.release_session(run.run_id)

    async def cancel_intervention(self, intervention_id: str, reason: str = "Operator cancelled run") -> Intervention:
        """Cancel an in-progress intervention and abort the run cleanly."""
        async with self._lock:
            intervention = self.interventions.get(intervention_id)
            if not intervention:
                raise BankingAgentError(f"Intervention '{intervention_id}' not found.", code=ResultCode.TARGET_NOT_FOUND)

            run = self.runs.get(intervention.run_id)
            if run:
                run.status = RunStatus.CANCELLED
                run.error = reason
                run.updated_at = datetime.now(timezone.utc).isoformat()

            intervention.status = InterventionStatus.CANCELLED
            intervention.resolution_notes = reason
            intervention.resolved_at = datetime.now(timezone.utc).isoformat()

        await self.release_session(intervention.run_id)
        return intervention


# Global singleton instance
handoff_coordinator = HandoffCoordinator()
