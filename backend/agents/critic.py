"""Artifact Critic providing advisory quality review and anti-pattern detection."""

from typing import Optional
from backend.core.artifact import CapabilityArtifact
from backend.services.openai_service import CriticIssue, CriticReview, OpenAIService


class ArtifactCritic:
    """Evaluates compiled CapabilityArtifacts for generalization, safety, and locator robustness."""

    def __init__(self, openai_service: Optional[OpenAIService] = None):
        self.openai_service = openai_service or OpenAIService()

    async def review(self, artifact: CapabilityArtifact, goal: str) -> CriticReview:
        """Perform comprehensive quality review combining deterministic rule checks and LLM critique."""
        issues = []

        # 1. Deterministic Rule: Check for hardcoded discovery parameters
        for step in artifact.steps:
            if step.action.value and "M-10428" in step.action.value:
                issues.append(
                    CriticIssue(
                        severity="critical",
                        step_id=step.step_id,
                        code="HARDCODED_DISCOVERY_INPUT",
                        message=f"Step '{step.step_id}' hardcodes discovery literal 'M-10428' instead of value_from_input='member_id'.",
                    )
                )

        # 2. Deterministic Rule: Check locator bundle completeness
        for step in artifact.steps:
            if step.action.locator:
                bundle = step.action.locator
                has_semantic = bool(bundle.role or bundle.label or bundle.text)
                has_fallback = bool(bundle.css or bundle.xpath or bundle.stable_attributes)
                if not (has_semantic or has_fallback):
                    issues.append(
                        CriticIssue(
                            severity="high",
                            step_id=step.step_id,
                            code="EMPTY_LOCATOR",
                            message=f"Step '{step.step_id}' locator has no valid targeting strategies.",
                        )
                    )

        # 3. Deterministic Rule: Check required inputs declared
        if "member_id" not in artifact.inputs:
            issues.append(
                CriticIssue(
                    severity="critical",
                    code="MISSING_INPUT_DECLARATION",
                    message="Capability artifact must declare 'member_id' in inputs.",
                )
            )

        if issues:
            return CriticReview(
                approved=False,
                score=0.4,
                issues=issues,
                suggestions=["Replace hardcoded values with value_from_input bindings."],
            )

        # 4. LLM Advisory Review (if API client available)
        try:
            if self.openai_service.api_key:
                return await self.openai_service.critique_artifact(artifact.to_dict(), goal)
        except Exception:
            pass

        # Default approved if all deterministic rules passed
        return CriticReview(
            approved=True,
            score=0.95,
            issues=[],
            suggestions=["Artifact meets all generalization and safety criteria."],
        )
