"""Unit and workflow tests for OpenAI Explorer, LangGraph discovery, Compiler, and Critic."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.agents.compiler import ArtifactCompiler
from backend.agents.critic import ArtifactCritic
from backend.agents.explorer import ExplorerAgent
from backend.agents.graph import DiscoveryEngine
from backend.automation.browser import BrowserController
from backend.core.artifact import CapabilityArtifact
from backend.core.errors import BankingAgentError, ResultCode
from backend.core.models import ActionType, LocatorBundle
from backend.core.policy import PolicyEngine
from backend.services.openai_service import CriticIssue, CriticReview, OpenAIService, ProposedAction


# ---------------------------------------------------------------------------
# 1. Explorer Agent Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explorer_returns_valid_structured_action():
    mock_openai = MagicMock(spec=OpenAIService)
    mock_openai.propose_next_action = AsyncMock(
        return_value=ProposedAction(
            action=ActionType.CLICK,
            target_description="Member Search",
            reason_summary="Click Member Search button",
            expected_state="Member Search form visible",
            goal_complete=False,
        )
    )

    explorer = ExplorerAgent(openai_service=mock_openai)
    action = await explorer.decide_next_action(
        goal="Find member M-10428 savings balance",
        observation={"url": "http://127.0.0.1:8000/", "title": "Dashboard"},
        history=[],
    )

    assert action.action == ActionType.CLICK
    assert action.target_description == "Member Search"
    assert action.goal_complete is False


@pytest.mark.asyncio
async def test_explorer_rejects_unsupported_action():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProposedAction(
            action="execute_shell_script",  # invalid action
            target_description="terminal",
            reason_summary="run command",
            expected_state="done",
        )


# ---------------------------------------------------------------------------
# 2. Artifact Compiler & Parameterization Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compiler_parameterizes_discovery_member_id():
    mock_openai = MagicMock(spec=OpenAIService)
    # Model returns raw compiled json containing literal M-10428
    mock_openai.compile_artifact = AsyncMock(
        return_value={
            "schema_version": "1.0",
            "capability_id": "member.get_savings_balance",
            "name": "Get Member Savings Balance",
            "version": "1.0.0",
            "description": "Look up member profile and savings balance",
            "target_application": "Northstar Core",
            "inputs": {
                "member_id": {
                    "type": "string",
                    "required": True,
                    "description": "Member identifier",
                }
            },
            "outputs": {
                "savings_balance": {
                    "type": "string",
                    "required": True,
                    "format": "currency",
                }
            },
            "steps": [
                {
                    "step_id": "enter_member_id",
                    "description": "Enter member ID into search input",
                    "action": {
                        "action_type": "fill",
                        "value": "M-10428",  # Literal hardcoded value from discovery
                        "locator": {
                            "role": "textbox",
                            "accessible_name": "Member ID",
                            "css": "#member_id",
                        },
                    },
                },
                {
                    "step_id": "extract_balance",
                    "description": "Read savings balance",
                    "action": {
                        "action_type": "extract",
                        "extract_key": "savings_balance",
                        "locator": {"css": "#current_savings_balance"},
                    },
                },
            ],
        }
    )

    compiler = ArtifactCompiler(openai_service=mock_openai)
    artifact = await compiler.compile(
        goal="Look up member M-10428 and return their current savings balance.",
        trace=[{"step": 1, "action": "fill", "target": "Member ID", "value": "M-10428"}],
        extracted_outputs={"savings_balance": 4283.42},
    )

    assert isinstance(artifact, CapabilityArtifact)
    # Verify M-10428 was parameterized
    fill_step = next(s for s in artifact.steps if s.step_id == "enter_member_id")
    assert fill_step.action.value_from_input == "member_id"
    assert fill_step.action.value != "M-10428"
    assert "member_id" in artifact.inputs


# ---------------------------------------------------------------------------
# 3. Artifact Critic Quality & Anti-pattern Detection Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_critic_rejects_hardcoded_discovery_id():
    faulty_artifact = CapabilityArtifact(
        schema_version="1.0",
        capability_id="test.faulty",
        name="Faulty Artifact",
        version="1.0.0",
        description="Testing critic rejection",
        target_application="Northstar Core",
        inputs={"member_id": {"type": "string", "required": True}},
        outputs={"savings_balance": {"type": "string", "required": True}},
        steps=[
            {
                "step_id": "fill_id",
                "description": "Fill ID",
                "action": {
                    "action_type": "fill",
                    "value": "M-10428",  # Hardcoded literal
                    "locator": {"role": "textbox", "accessible_name": "Member ID"},
                },
            }
        ],
    )

    critic = ArtifactCritic()
    review = await critic.review(faulty_artifact, goal="Look up member M-10428")

    assert review.approved is False
    assert any(i.code == "HARDCODED_DISCOVERY_INPUT" for i in review.issues)


@pytest.mark.asyncio
async def test_critic_approves_clean_parameterized_artifact():
    valid_artifact = CapabilityArtifact.load_yaml("artifacts/member_balance_v1.yaml")
    critic = ArtifactCritic()
    review = await critic.review(valid_artifact, goal="Look up member M-10428")

    assert review.approved is True
    assert review.score >= 0.8


# ---------------------------------------------------------------------------
# 4. LangGraph Discovery Flow & Loop Detection Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_langgraph_loop_detection_triggers_human_required(tmp_path):
    browser = MagicMock(spec=BrowserController)
    browser.get_observation = AsyncMock(
        return_value=MagicMock(
            model_dump=lambda: {"url": "http://127.0.0.1:8000/", "title": "Dashboard", "visible_text_summary": "Dashboard"},
            visible_text_summary="Dashboard",
        )
    )
    browser.capture_screenshot = AsyncMock(return_value=b"fake_png")
    browser.navigate = AsyncMock()
    browser.click = AsyncMock()

    mock_openai = MagicMock(spec=OpenAIService)
    # Propose the exact same action repeatedly
    mock_openai.propose_next_action = AsyncMock(
        return_value=ProposedAction(
            action=ActionType.CLICK,
            target_description="Stuck Button",
            reason_summary="Click repeatedly",
            expected_state="Same",
            goal_complete=False,
        )
    )

    engine = DiscoveryEngine(
        browser=browser,
        policy_engine=PolicyEngine(),
        openai_service=mock_openai,
        evidence_dir=tmp_path,
    )

    # Simulate 2 previous identical actions
    state = {
        "run_id": "test_stuck_run",
        "goal": "Test goal",
        "target_url": "http://127.0.0.1:8000",
        "current_observation": {"url": "http://127.0.0.1:8000"},
        "screenshot_path": None,
        "action_history": [
            {"action": "click", "target": "Stuck Button"},
            {"action": "click", "target": "Stuck Button"},
        ],
        "discovery_trace": [],
        "step_count": 2,
        "max_steps": 10,
        "goal_complete": False,
        "extracted_outputs": {},
        "proposed_action": {"action": "click", "target_description": "Stuck Button", "value": None},
        "compiled_artifact": None,
        "critic_review": None,
        "refinement_count": 0,
        "max_refinements": 2,
        "status": "EXPLORING",
        "error": None,
        "saved_artifact_path": None,
        "call_count": 0,
    }

    res = await engine._node_execute_action(state)
    assert res.get("status") == "HUMAN_REQUIRED"
    assert "STUCK_LOOP" in res.get("error", "")


# ---------------------------------------------------------------------------
# 5. Generalization Proof: Replay Discovered Artifact on Different Inputs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_discovered_artifact_generalization_and_replay(tmp_path):
    """Compile a discovery trace into member_balance_discovered_v1.yaml, then replay on M-77777 and M-00000."""
    from backend.automation.replay import ReplayEngine
    from backend.core.errors import ExecutionStatus, ResultCode
    import threading
    import time
    import uvicorn
    from demo_bank.app import app

    # 1. Start test server
    port = 8767
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.6)

    try:
        # 2. Compile discovery trace using compiler
        discovery_trace = [
            {
                "step": 1,
                "action": "navigate",
                "target": "Member Search",
                "value": f"http://127.0.0.1:{port}/members/search",
            },
            {
                "step": 2,
                "action": "fill",
                "target": "Member ID",
                "value": "M-10428",  # Discovery input to be parameterized
                "locator": {
                    "role": "textbox",
                    "accessible_name": "Member ID",
                    "label": "Member ID",
                    "css": "#member_id",
                    "stable_attributes": {"id": "member_id"},
                },
            },
            {
                "step": 3,
                "action": "click",
                "target": "Search",
                "locator": {
                    "role": "button",
                    "accessible_name": "Search",
                    "css": "#search_button",
                    "stable_attributes": {"id": "search_button"},
                },
            },
            {
                "step": 4,
                "action": "click",
                "target": "View Savings",
                "locator": {
                    "role": "link",
                    "accessible_name": "View Savings",
                    "css": "#btn_view_savings",
                    "stable_attributes": {"id": "btn_view_savings"},
                },
            },
            {
                "step": 5,
                "action": "extract",
                "target": "Current Savings Balance",
                "locator": {
                    "css": "#current_savings_balance",
                    "text": "$",
                    "stable_attributes": {"id": "current_savings_balance"},
                },
            },
        ]

        mock_openai = MagicMock(spec=OpenAIService)
        mock_openai.compile_artifact = AsyncMock(
            return_value={
                "schema_version": "1.0",
                "capability_id": "member.get_savings_balance",
                "name": "Get Member Savings Balance (Discovered)",
                "version": "1.0.0",
                "description": "AI-discovered workflow for retrieving savings balance",
                "target_application": "Northstar Core",
                "inputs": {
                    "member_id": {
                        "type": "string",
                        "required": True,
                        "description": "Primary member ID",
                        "validation_pattern": r"^M-\d{5}$",
                    }
                },
                "outputs": {
                    "savings_balance": {
                        "type": "string",
                        "required": True,
                        "format": "currency",
                    }
                },
                "safety": {"risk_level": "LOW", "read_only": True},
                "steps": [
                    {
                        "step_id": "navigate_search",
                        "description": "Open search page",
                        "action": {
                            "action_type": "navigate",
                            "target_url": f"http://127.0.0.1:{port}/members/search",
                        },
                        "checkpoint": {"type": "URL_CONTAINS", "expected": "/members/search"},
                    },
                    {
                        "step_id": "enter_member_id",
                        "description": "Enter member ID",
                        "action": {
                            "action_type": "fill",
                            "value": "M-10428",  # Compiler will parameterize this
                            "locator": {
                                "role": "textbox",
                                "accessible_name": "Member ID",
                                "label": "Member ID",
                                "css": "#member_id",
                                "stable_attributes": {"id": "member_id"},
                            },
                        },
                    },
                    {
                        "step_id": "submit_search",
                        "description": "Click Search",
                        "action": {
                            "action_type": "click",
                            "locator": {
                                "role": "button",
                                "accessible_name": "Search",
                                "css": "#search_button",
                                "stable_attributes": {"id": "search_button"},
                            },
                        },
                        "checkpoint": {
                            "type": "ONE_OF",
                            "branches": [
                                {"type": "TEXT_VISIBLE", "expected": "Member Record Overview", "outcome_code": "SUCCESS"},
                                {"type": "TEXT_VISIBLE", "expected": "Member Not Found", "outcome_code": "MEMBER_NOT_FOUND"},
                                {"type": "TEXT_VISIBLE", "expected": "Access Denied", "outcome_code": "PERMISSION_DENIED"},
                                {"type": "TEXT_VISIBLE", "expected": "Additional Verification Required", "outcome_code": "MANUAL_VERIFICATION"},
                            ],
                        },
                    },
                    {
                        "step_id": "open_savings",
                        "description": "Click View Savings",
                        "action": {
                            "action_type": "click",
                            "locator": {
                                "role": "link",
                                "accessible_name": "View Savings",
                                "css": "#btn_view_savings",
                                "stable_attributes": {"id": "btn_view_savings"},
                            },
                        },
                        "checkpoint": {"type": "URL_CONTAINS", "expected": "/accounts/savings"},
                    },
                    {
                        "step_id": "extract_balance",
                        "description": "Extract Current Savings Balance",
                        "action": {
                            "action_type": "extract",
                            "extract_key": "savings_balance",
                            "locator": {
                                "css": "#current_savings_balance",
                                "text": "$",
                                "stable_attributes": {"id": "current_savings_balance"},
                            },
                        },
                        "checkpoint": {"type": "OUTPUT_PRESENT", "expected": "savings_balance"},
                    },
                ],
                "success_condition": {"type": "OUTPUT_PRESENT", "expected": "savings_balance"},
            }
        )

        compiler = ArtifactCompiler(openai_service=mock_openai)
        discovered_artifact = await compiler.compile(
            goal="Look up member M-10428 and return their current savings balance.",
            trace=discovery_trace,
            extracted_outputs={"savings_balance": 4283.42},
        )

        # 3. Critic Review
        critic = ArtifactCritic()
        review = await critic.review(discovered_artifact, goal="Look up member M-10428")
        assert review.approved is True

        # 4. Save discovered artifact to disk
        discovered_path = Path("artifacts") / "member_balance_discovered_v1.yaml"
        discovered_artifact.save_yaml(discovered_path)
        assert discovered_path.exists()

        # 5. Generalization Test: Replay on M-77777 (Casey Wright) using deterministic ReplayEngine (ZERO LLM)
        replay_engine = ReplayEngine(evidence_dir=tmp_path)
        result_77777 = await replay_engine.execute(
            artifact=discovered_artifact,
            inputs={"member_id": "M-77777"},
            run_id="discovered_replay_m77777",
        )
        assert result_77777.status == ExecutionStatus.SUCCESS
        assert result_77777.outcome_code == ResultCode.SUCCESS
        assert result_77777.extracted_data.get("savings_balance") == 8910.00

        # 6. Business Outcome Test: Replay on M-00000 (Not Found)
        result_00000 = await replay_engine.execute(
            artifact=discovered_artifact,
            inputs={"member_id": "M-00000"},
            run_id="discovered_replay_m00000",
        )
        assert result_00000.status == ExecutionStatus.BUSINESS_OUTCOME
        assert result_00000.outcome_code == ResultCode.MEMBER_NOT_FOUND

    finally:
        server.should_exit = True
