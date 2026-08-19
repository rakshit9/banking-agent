"""OpenAI communication service for computer-use discovery, compilation, and review."""

import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from backend.config import settings
from backend.core.models import ActionType, LocatorBundle


class ProposedAction(BaseModel):
    """Structured action proposal emitted by the Explorer Agent."""

    action: ActionType
    target_description: str = Field(..., description="Short description of the target UI element")
    locator: Optional[LocatorBundle] = Field(None, description="Inferred locator bundle for the target element")
    value: Optional[str] = Field(None, description="Literal input value or navigation URL")
    value_from_input: Optional[str] = Field(None, description="Input parameter name if value represents an input")
    reason_summary: str = Field(..., description="Operational explanation of why this action is chosen")
    expected_state: str = Field(..., description="Expected resulting UI state after this action")
    goal_complete: bool = Field(default=False, description="Whether the objective has been achieved")
    extracted_data: Optional[Dict[str, Any]] = Field(default=None, description="Extracted key-value pairs if goal complete")


class CriticIssue(BaseModel):
    """Single defect or quality warning identified by the Critic."""

    severity: str = Field(..., description="'critical', 'high', 'medium', 'low'")
    step_id: Optional[str] = Field(None, description="Target step identifier")
    code: str = Field(..., description="Issue taxonomy code, e.g. 'HARDCODED_INPUT'")
    message: str = Field(..., description="Actionable remediation advice")


class CriticReview(BaseModel):
    """Structured evaluation of a compiled CapabilityArtifact."""

    approved: bool
    score: float = Field(..., description="Quality score between 0.0 and 1.0")
    issues: List[CriticIssue] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class OpenAIService:
    """Manages OpenAI API interaction for discovery, artifact synthesis, and quality auditing."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.call_count: int = 0

        if not self.api_key:
            self._client = None
        else:
            self._client = AsyncOpenAI(api_key=self.api_key)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            raise ValueError("OPENAI_API_KEY is required for discovery mode.")
        return self._client

    async def propose_next_action(
        self,
        goal: str,
        observation: Dict[str, Any],
        history: List[Dict[str, Any]],
        screenshot_path: Optional[str] = None,
    ) -> ProposedAction:
        """Query LLM to decide next UI action based on current browser state."""
        self.call_count += 1

        system_prompt = (
            "You are an expert legacy banking operations explorer agent. Your task is to operate a banking "
            "web portal to discover the exact UI workflow required to fulfill the user's goal.\n"
            "Rules:\n"
            "1. Propose EXACTLY ONE atomic action per step: 'navigate', 'click', 'fill', 'read', 'extract', or 'scroll'.\n"
            "2. When filling form fields (such as Member ID), identify the semantic role and label.\n"
            "3. If the current view shows the final goal information (e.g. Current Savings Balance), mark goal_complete=True "
            "and extract the target values into extracted_data.\n"
            "4. Be deterministic and concise. Output structured JSON matching the ProposedAction schema."
        )

        user_content: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": f"GOAL: {goal}\n\n"
                f"CURRENT URL: {observation.get('url')}\n"
                f"PAGE TITLE: {observation.get('title')}\n"
                f"PAGE TEXT SUMMARY: {observation.get('visible_text_summary', '')[:400]}\n"
                f"PREVIOUS ACTION HISTORY: {json.dumps(history[-4:] if history else [], indent=2)}\n\n"
                "Determine the next action to take to achieve the goal.",
            }
        ]

        if screenshot_path and Path(screenshot_path).exists():
            try:
                with open(screenshot_path, "rb") as img_file:
                    b64_data = base64.b64encode(img_file.read()).decode("utf-8")
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_data}", "detail": "low"},
                    }
                )
            except Exception:
                pass

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )

            raw_json = response.choices[0].message.content or "{}"
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict) and isinstance(parsed.get("proposed_action"), dict):
                parsed = parsed["proposed_action"]
            if isinstance(parsed, dict):
                if "target_description" not in parsed:
                    parsed["target_description"] = (
                        parsed.get("target")
                        or parsed.get("target_element")
                        or parsed.get("element")
                        or parsed.get("description")
                        or "current target"
                    )
                if "reason_summary" not in parsed:
                    parsed["reason_summary"] = (
                        parsed.get("reason")
                        or parsed.get("rationale")
                        or parsed.get("explanation")
                        or "Next operational step toward the goal."
                    )
                if "expected_state" not in parsed:
                    parsed["expected_state"] = parsed.get("expected_result") or "Progress toward the requested banking workflow."
            return ProposedAction.model_validate(parsed)
        except Exception as e:
            # Re-raise with clean contextual message
            raise RuntimeError(f"OpenAI action proposal failed: {e}") from e

    async def compile_artifact(
        self,
        goal: str,
        trace: List[Dict[str, Any]],
        extracted_outputs: Dict[str, Any],
        target_application: str = "Northstar Core",
        critic_feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synthesize discovery trace into a structured CapabilityArtifact dictionary."""
        self.call_count += 1

        system_prompt = (
            "You are an Artifact Compiler for a computer-use automation system. Your job is to transform a "
            "successful discovery trace into a clean, reusable, parameterized CapabilityArtifact YAML/JSON.\n"
            "Rules:\n"
            "1. Parameterize runtime values: Any discovery member ID (e.g. 'M-10428') MUST be converted to "
            "value_from_input='member_id'. NEVER hardcode 'M-10428' in step actions.\n"
            "2. Define robust multi-strategy LocatorBundles (role, label, text, css, stable_attributes).\n"
            "3. Define appropriate checkpoints (URL_CONTAINS, TEXT_VISIBLE, ONE_OF).\n"
            "4. Define outputs (e.g. savings_balance: {type: 'string', format: 'currency'}).\n"
            "5. Set schema_version='1.0', version='1.0.0', safety={risk_level: 'LOW', read_only: true}."
        )

        user_prompt = (
            f"GOAL: {goal}\n"
            f"TARGET APPLICATION: {target_application}\n"
            f"EXTRACTED OUTPUTS: {json.dumps(extracted_outputs)}\n"
            f"DISCOVERY TRACE:\n{json.dumps(trace, indent=2)}\n\n"
        )
        if critic_feedback:
            user_prompt += f"CRITIC REVISION FEEDBACK:\n{critic_feedback}\n\n"

        user_prompt += "Generate the complete CapabilityArtifact JSON."

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw_json = response.choices[0].message.content or "{}"
        return json.loads(raw_json)

    async def critique_artifact(self, artifact_dict: Dict[str, Any], goal: str) -> CriticReview:
        """Critique compiled capability artifact for parameterization, safety, and robustness."""
        self.call_count += 1

        system_prompt = (
            "You are an Artifact Critic. You rigorously evaluate compiled CapabilityArtifact definitions for:\n"
            "1. Input parameterization: Is discovery input (e.g. 'M-10428') parameterized rather than hardcoded?\n"
            "2. Locator robustness: Do steps include semantic locators and fallbacks?\n"
            "3. Checkpoint verification: Are checkpoints present to verify critical states?\n"
            "4. Safety: Is risk_level appropriate and read_only set correctly?\n"
            "Return structured JSON matching CriticReview schema with approved (bool), score (float), and issues list."
        )

        user_prompt = (
            f"GOAL: {goal}\n\n"
            f"COMPILED ARTIFACT:\n{json.dumps(artifact_dict, indent=2)}\n\n"
            "Evaluate this artifact."
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw_json = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_json)
        return CriticReview.model_validate(parsed)
