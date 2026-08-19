"""Deterministic ReplayEngine executing CapabilityArtifacts with ZERO LLM decisions."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, Optional
import uuid

from backend.automation.browser import BrowserController
from backend.automation.checkpoints import CheckpointEvaluator
from backend.core.artifact import CapabilityArtifact
from backend.core.errors import (
    BankingAgentError,
    ExecutionStatus,
    LocatorResolutionError,
    ResultCode,
)
from backend.core.models import (
    ActionType,
    CheckpointType,
    ExecutionResult,
    InterventionRequest,
    RiskLevel,
)
from backend.core.policy import PolicyEngine
from backend.services.evidence import EvidenceRecorder


class ReplayEngine:
    """Production execution engine that deterministically replays saved CapabilityArtifacts.
    
    Architectural Guarantee: ZERO LLM calls or reasoning. Pure deterministic execution.
    """

    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
        evidence_dir: Optional[Path] = None,
    ):
        self.policy_engine = policy_engine or PolicyEngine()
        self.evidence_dir = evidence_dir

    async def execute(
        self,
        artifact: CapabilityArtifact,
        inputs: Dict[str, Any],
        browser: Optional[BrowserController] = None,
        run_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a CapabilityArtifact workflow deterministically against active browser."""
        execution_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        # Identify sensitive input parameter names for evidence redaction
        sensitive_keys = {
            k for k, prop in artifact.inputs.items() if getattr(prop, "sensitive", False)
        }
        
        evidence = EvidenceRecorder(
            run_id=execution_id,
            mode="replay",
            output_dir=self.evidence_dir,
            sensitive_keys=sensitive_keys,
        )

        evidence.record_event(
            event="RUN_STARTED",
            capability_id=artifact.capability_id,
            details={
                "version": artifact.version,
                "target_application": artifact.target_application,
                "step_count": len(artifact.steps),
            },
        )

        # 1. Validate Input Parameters
        validation_error = self._validate_inputs(artifact, inputs)
        if validation_error:
            evidence.record_event(
                event="RUN_FAILED",
                capability_id=artifact.capability_id,
                details={"error_code": ResultCode.INVALID_INPUT.value, "reason": validation_error},
            )
            return ExecutionResult(
                run_id=execution_id,
                capability_id=artifact.capability_id,
                status=ExecutionStatus.HARD_FAILURE,
                outcome_code=ResultCode.INVALID_INPUT,
                error_message=f"Input validation error: {validation_error}",
                steps_completed=0,
            )

        evidence.record_event(
            event="INPUT_VALIDATED",
            capability_id=artifact.capability_id,
            details={"inputs": inputs},
        )

        # 2. Browser Session Lifecycle
        should_close_browser = False
        active_browser = browser
        if active_browser is None:
            active_browser = BrowserController(headless=True)
            await active_browser.start()
            should_close_browser = True

        steps_completed = 0
        extracted_data: Dict[str, Any] = {}

        try:
            for step in artifact.steps:
                evidence.record_event(
                    event="STEP_STARTED",
                    capability_id=artifact.capability_id,
                    step_id=step.step_id,
                    details={"description": step.description, "action_type": step.action.action_type.value},
                )

                # Policy Evaluation before any browser action
                current_url = active_browser.page.url if active_browser.page and not active_browser.page.is_closed() else None
                policy_eval = self.policy_engine.evaluate_action(
                    action=step.action,
                    step_risk=step.risk_level,
                    current_url=current_url,
                )

                evidence.record_event(
                    event="POLICY_CHECK",
                    capability_id=artifact.capability_id,
                    step_id=step.step_id,
                    details={
                        "decision": policy_eval.decision.value,
                        "rule": policy_eval.rule_name,
                        "reason": policy_eval.reason,
                    },
                )

                if policy_eval.is_blocked:
                    screenshot = await evidence.capture_screenshot_evidence(
                        active_browser.page, "policy_violation", artifact.capability_id, step.step_id
                    )
                    evidence.record_event(
                        event="RUN_FAILED",
                        capability_id=artifact.capability_id,
                        step_id=step.step_id,
                        details={"error_code": ResultCode.POLICY_VIOLATION.value, "reason": policy_eval.reason},
                    )
                    return ExecutionResult(
                        run_id=execution_id,
                        capability_id=artifact.capability_id,
                        status=ExecutionStatus.HARD_FAILURE,
                        outcome_code=ResultCode.POLICY_VIOLATION,
                        error_message=f"Policy violation: {policy_eval.reason}",
                        steps_completed=steps_completed,
                        details={"screenshot_path": screenshot},
                    )

                if policy_eval.requires_human:
                    screenshot = await evidence.capture_screenshot_evidence(
                        active_browser.page, "human_required", artifact.capability_id, step.step_id
                    )
                    intervention_req = InterventionRequest(
                        run_id=execution_id,
                        capability_id=artifact.capability_id,
                        current_step=step.step_id,
                        reason=policy_eval.reason,
                        member_id=inputs.get("member_id"),
                        current_url=current_url,
                        required_action="Human operator approval required for high-risk action.",
                        screenshot_path=screenshot,
                    )
                    evidence.record_event(
                        event="HUMAN_REQUIRED",
                        capability_id=artifact.capability_id,
                        step_id=step.step_id,
                        details={"reason": policy_eval.reason},
                    )
                    return ExecutionResult(
                        run_id=execution_id,
                        capability_id=artifact.capability_id,
                        status=ExecutionStatus.HUMAN_REQUIRED,
                        outcome_code=ResultCode.UNEXPECTED_DIALOG,
                        intervention_request=intervention_req,
                        steps_completed=steps_completed,
                    )

                # Resolve Step Action Values
                runtime_val = self._resolve_action_value(step.action, inputs)

                # Execute Action with Bounded Recovery
                action_res = await self._execute_action_with_recovery(
                    browser=active_browser,
                    step=step,
                    runtime_value=runtime_val,
                    evidence=evidence,
                    artifact_id=artifact.capability_id,
                )

                if action_res.get("failed"):
                    screenshot = await evidence.capture_screenshot_evidence(
                        active_browser.page, "hard_failure", artifact.capability_id, step.step_id
                    )
                    evidence.record_event(
                        event="RUN_FAILED",
                        capability_id=artifact.capability_id,
                        step_id=step.step_id,
                        details=action_res,
                    )
                    return ExecutionResult(
                        run_id=execution_id,
                        capability_id=artifact.capability_id,
                        status=ExecutionStatus.HARD_FAILURE,
                        outcome_code=action_res.get("code", ResultCode.TARGET_NOT_FOUND),
                        error_message=action_res.get("message", "Step action execution failed."),
                        steps_completed=steps_completed,
                        details={"screenshot_path": screenshot, **action_res},
                    )

                # Store Extracted Data if applicable
                if step.action.action_type == ActionType.EXTRACT and step.action.extract_key:
                    raw_extracted = action_res.get("extracted_text", "")
                    cleaned_val = self._parse_extracted_value(
                        raw_extracted, artifact.outputs.get(step.action.extract_key)
                    )
                    extracted_data[step.action.extract_key] = cleaned_val

                evidence.record_event(
                    event="ACTION_EXECUTED",
                    capability_id=artifact.capability_id,
                    step_id=step.step_id,
                    details={
                        "action_type": step.action.action_type.value,
                        "target": step.action.locator.accessible_name if step.action.locator else None,
                    },
                )

                # Checkpoint & Known Outcome Verification
                if step.checkpoint:
                    cp_result = await CheckpointEvaluator.evaluate(
                        checkpoint=step.checkpoint,
                        page=active_browser.page,
                        extracted_data=extracted_data,
                    )

                    if step.checkpoint.type == CheckpointType.ONE_OF:
                        if cp_result.passed:
                            outcome = cp_result.matched_outcome
                            
                            # Handle Business Outcome: MEMBER_NOT_FOUND
                            if outcome == ResultCode.MEMBER_NOT_FOUND.value:
                                evidence.record_event(
                                    event="BUSINESS_OUTCOME",
                                    capability_id=artifact.capability_id,
                                    step_id=step.step_id,
                                    details={"outcome_code": ResultCode.MEMBER_NOT_FOUND.value},
                                )
                                return ExecutionResult(
                                    run_id=execution_id,
                                    capability_id=artifact.capability_id,
                                    status=ExecutionStatus.BUSINESS_OUTCOME,
                                    outcome_code=ResultCode.MEMBER_NOT_FOUND,
                                    extracted_data=extracted_data,
                                    steps_completed=steps_completed + 1,
                                    observation=await active_browser.get_observation(),
                                )

                            # Handle Business Outcome: PERMISSION_DENIED
                            if outcome == ResultCode.PERMISSION_DENIED.value:
                                evidence.record_event(
                                    event="BUSINESS_OUTCOME",
                                    capability_id=artifact.capability_id,
                                    step_id=step.step_id,
                                    details={"outcome_code": ResultCode.PERMISSION_DENIED.value},
                                )
                                return ExecutionResult(
                                    run_id=execution_id,
                                    capability_id=artifact.capability_id,
                                    status=ExecutionStatus.BUSINESS_OUTCOME,
                                    outcome_code=ResultCode.PERMISSION_DENIED,
                                    extracted_data=extracted_data,
                                    steps_completed=steps_completed + 1,
                                    observation=await active_browser.get_observation(),
                                )

                            # Handle Interstitial: MANUAL_VERIFICATION / HUMAN_REQUIRED
                            if outcome == ResultCode.MANUAL_VERIFICATION.value:
                                screenshot = await evidence.capture_screenshot_evidence(
                                    active_browser.page, "human_required", artifact.capability_id, step.step_id
                                )
                                intervention_req = InterventionRequest(
                                    run_id=execution_id,
                                    capability_id=artifact.capability_id,
                                    current_step=step.step_id,
                                    reason="This member requires manual verification before account information can be displayed.",
                                    member_id=inputs.get("member_id"),
                                    current_url=active_browser.page.url,
                                    required_action="Operator must review verification documents and confirm authorization via 'Verify & Continue'.",
                                    expected_state="Member Record Overview",
                                    observed_state="Additional Verification Required",
                                    screenshot_path=screenshot,
                                )
                                evidence.record_event(
                                    event="HUMAN_REQUIRED",
                                    capability_id=artifact.capability_id,
                                    step_id=step.step_id,
                                    details={"reason": intervention_req.reason},
                                )
                                return ExecutionResult(
                                    run_id=execution_id,
                                    capability_id=artifact.capability_id,
                                    status=ExecutionStatus.HUMAN_REQUIRED,
                                    outcome_code=ResultCode.MANUAL_VERIFICATION,
                                    intervention_request=intervention_req,
                                    steps_completed=steps_completed + 1,
                                    observation=await active_browser.get_observation(),
                                )

                            # Successful branch match: continue
                            evidence.record_event(
                                event="CHECKPOINT_PASSED",
                                capability_id=artifact.capability_id,
                                step_id=step.step_id,
                                details={"diagnostic": cp_result.diagnostic},
                            )
                        else:
                            # ONE_OF checkpoint failed completely
                            screenshot = await evidence.capture_screenshot_evidence(
                                active_browser.page, "checkpoint_failed", artifact.capability_id, step.step_id
                            )
                            evidence.record_event(
                                event="CHECKPOINT_FAILED",
                                capability_id=artifact.capability_id,
                                step_id=step.step_id,
                                details={"diagnostic": cp_result.diagnostic},
                            )
                            return ExecutionResult(
                                run_id=execution_id,
                                capability_id=artifact.capability_id,
                                status=ExecutionStatus.HARD_FAILURE,
                                outcome_code=ResultCode.CHECKPOINT_FAILED,
                                error_message=cp_result.diagnostic,
                                steps_completed=steps_completed,
                                details={"screenshot_path": screenshot},
                            )
                    else:
                        # Standard Checkpoint Evaluation
                        if not cp_result.passed:
                            screenshot = await evidence.capture_screenshot_evidence(
                                active_browser.page, "checkpoint_failed", artifact.capability_id, step.step_id
                            )
                            evidence.record_event(
                                event="CHECKPOINT_FAILED",
                                capability_id=artifact.capability_id,
                                step_id=step.step_id,
                                details={"diagnostic": cp_result.diagnostic},
                            )
                            return ExecutionResult(
                                run_id=execution_id,
                                capability_id=artifact.capability_id,
                                status=ExecutionStatus.HARD_FAILURE,
                                outcome_code=ResultCode.CHECKPOINT_FAILED,
                                error_message=cp_result.diagnostic,
                                steps_completed=steps_completed,
                                details={"screenshot_path": screenshot},
                            )

                        evidence.record_event(
                            event="CHECKPOINT_PASSED",
                            capability_id=artifact.capability_id,
                            step_id=step.step_id,
                            details={"diagnostic": cp_result.diagnostic},
                        )

                steps_completed += 1

            # 3. Success Condition & Output Completeness Check
            if artifact.success_condition:
                succ_eval = await CheckpointEvaluator.evaluate(
                    checkpoint=artifact.success_condition,
                    page=active_browser.page,
                    extracted_data=extracted_data,
                )
                if not succ_eval.passed:
                    screenshot = await evidence.capture_screenshot_evidence(
                        active_browser.page, "success_condition_failed", artifact.capability_id
                    )
                    evidence.record_event(
                        event="RUN_FAILED",
                        capability_id=artifact.capability_id,
                        details={"diagnostic": succ_eval.diagnostic},
                    )
                    return ExecutionResult(
                        run_id=execution_id,
                        capability_id=artifact.capability_id,
                        status=ExecutionStatus.HARD_FAILURE,
                        outcome_code=ResultCode.CHECKPOINT_FAILED,
                        error_message=f"Final success condition not met: {succ_eval.diagnostic}",
                        steps_completed=steps_completed,
                        details={"screenshot_path": screenshot},
                    )

            # Ensure all required declared outputs exist
            for out_name, out_prop in artifact.outputs.items():
                if out_prop.required and (out_name not in extracted_data or extracted_data[out_name] is None):
                    return ExecutionResult(
                        run_id=execution_id,
                        capability_id=artifact.capability_id,
                        status=ExecutionStatus.HARD_FAILURE,
                        outcome_code=ResultCode.TARGET_NOT_FOUND,
                        error_message=f"Required capability output '{out_name}' was not extracted.",
                        steps_completed=steps_completed,
                    )

            evidence.record_event(
                event="RUN_SUCCEEDED",
                capability_id=artifact.capability_id,
                details={"extracted_data": extracted_data, "steps_completed": steps_completed},
            )

            return ExecutionResult(
                run_id=execution_id,
                capability_id=artifact.capability_id,
                status=ExecutionStatus.SUCCESS,
                outcome_code=ResultCode.SUCCESS,
                extracted_data=extracted_data,
                steps_completed=steps_completed,
                observation=await active_browser.get_observation(),
            )

        finally:
            if should_close_browser and active_browser is not None:
                await active_browser.close()

    def _validate_inputs(self, artifact: CapabilityArtifact, inputs: Dict[str, Any]) -> Optional[str]:
        """Validate runtime inputs against capability input specifications."""
        for param_name, prop in artifact.inputs.items():
            if prop.required and param_name not in inputs:
                return f"Missing required input parameter '{param_name}'."

            if param_name in inputs:
                val = inputs[param_name]
                if prop.validation_pattern and isinstance(val, str):
                    if not re.match(prop.validation_pattern, val):
                        return (
                            f"Input '{param_name}' value '{val}' fails validation pattern '{prop.validation_pattern}'."
                        )
        return None

    def _resolve_action_value(self, action: Any, inputs: Dict[str, Any]) -> Optional[str]:
        """Bind runtime parameter values to step action."""
        if action.value_from_input:
            return str(inputs.get(action.value_from_input, ""))
        return action.value

    async def _execute_action_with_recovery(
        self,
        browser: BrowserController,
        step: Any,
        runtime_value: Optional[str],
        evidence: EvidenceRecorder,
        artifact_id: str,
        max_attempts: int = 2,
    ) -> Dict[str, Any]:
        """Execute single step action with bounded deterministic retry."""
        action = step.action
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                if action.action_type == ActionType.NAVIGATE:
                    target_url = action.target_url or runtime_value or ""
                    await browser.navigate(target_url)
                    return {"success": True}

                if action.action_type == ActionType.FILL:
                    await browser.fill(action.locator, runtime_value or "", timeout_ms=action.timeout_ms)
                    return {"success": True}

                if action.action_type == ActionType.CLICK:
                    await browser.click(action.locator, timeout_ms=action.timeout_ms)
                    return {"success": True}

                if action.action_type == ActionType.READ:
                    text = await browser.read_text(action.locator, timeout_ms=action.timeout_ms)
                    return {"success": True, "read_text": text}

                if action.action_type == ActionType.EXTRACT:
                    extracted = await browser.read_text(action.locator, timeout_ms=action.timeout_ms)
                    return {"success": True, "extracted_text": extracted}

                if action.action_type == ActionType.SCROLL:
                    await browser.page.evaluate("window.scrollBy(0, 300)")
                    return {"success": True}

                if action.action_type == ActionType.WAIT:
                    await asyncio.sleep(0.5)
                    return {"success": True}

            except (LocatorResolutionError, BankingAgentError, Exception) as e:
                last_error = e
                if attempt < max_attempts:
                    evidence.record_event(
                        event="RECOVERY_ATTEMPT",
                        capability_id=artifact_id,
                        step_id=step.step_id,
                        details={"attempt": attempt, "error": str(e), "recovery_action": "state_delay_retry"},
                    )
                    await asyncio.sleep(0.5)

        # Retries exhausted
        err_code = getattr(last_error, "code", ResultCode.TARGET_NOT_FOUND)
        return {
            "failed": True,
            "code": err_code,
            "message": str(last_error),
            "step_id": step.step_id,
            "attempts": max_attempts,
        }

    def _parse_extracted_value(self, raw_str: str, output_prop: Optional[Any]) -> Any:
        """Deterministic numeric and string normalization without LLM."""
        cleaned = raw_str.strip()
        if not output_prop:
            return cleaned

        # Currency / Float normalization: "$4,283.42" -> 4283.42
        if output_prop.format == "currency" or output_prop.type in ("number", "float", "decimal"):
            # Strip currency symbols and comma separators
            sanitized = re.sub(r"[^\d.-]", "", cleaned)
            try:
                if "." in sanitized:
                    return float(sanitized)
                return int(sanitized)
            except ValueError:
                return cleaned

        return cleaned
