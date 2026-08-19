"""Integration and failure injection tests for deterministic ReplayEngine with ZERO LLM decisions."""

import json
from pathlib import Path
import threading
import time
import pytest
import uvicorn

from backend.automation.browser import BrowserController
from backend.automation.replay import ReplayEngine
from backend.core.artifact import CapabilityArtifact, InputProperty, OutputProperty, StepArtifact
from backend.core.errors import ExecutionStatus, ResultCode
from backend.core.models import Action, ActionType, LocatorBundle
from backend.core.policy import PolicyEngine
from demo_bank.app import app


@pytest.fixture(scope="session")
def live_server_url():
    """Start local demo bank server for replay integration tests."""
    port = 8766
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    time.sleep(0.6)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.fixture
def member_artifact(live_server_url):
    """Load reference artifact and dynamically configure target URL for test server."""
    artifact = CapabilityArtifact.load_yaml("artifacts/member_balance_v1.yaml")
    # Point first navigate action to live test server
    artifact.steps[0].action.target_url = f"{live_server_url}/members/search"
    return artifact


# ---------------------------------------------------------------------------
# 1. Deterministic Replay Integration Tests (Scenarios A - E)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replay_scenario_a_success(member_artifact, tmp_path):
    """Test A: M-10428 -> SUCCESS, savings_balance = 4283.42."""
    engine = ReplayEngine(evidence_dir=tmp_path)
    result = await engine.execute(
        artifact=member_artifact,
        inputs={"member_id": "M-10428"},
        run_id="test_run_m10428",
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert result.outcome_code == ResultCode.SUCCESS
    assert result.extracted_data.get("savings_balance") == 4283.42
    assert result.steps_completed == len(member_artifact.steps)


@pytest.mark.asyncio
async def test_replay_scenario_b_member_not_found(member_artifact, tmp_path):
    """Test B: M-00000 -> BUSINESS_OUTCOME / MEMBER_NOT_FOUND (not a failure or crash)."""
    engine = ReplayEngine(evidence_dir=tmp_path)
    result = await engine.execute(
        artifact=member_artifact,
        inputs={"member_id": "M-00000"},
        run_id="test_run_m00000",
    )

    assert result.status == ExecutionStatus.BUSINESS_OUTCOME
    assert result.outcome_code == ResultCode.MEMBER_NOT_FOUND
    assert result.error_message is None


@pytest.mark.asyncio
async def test_replay_scenario_c_permission_denied(member_artifact, tmp_path):
    """Test C: M-99999 -> BUSINESS_OUTCOME / PERMISSION_DENIED."""
    engine = ReplayEngine(evidence_dir=tmp_path)
    result = await engine.execute(
        artifact=member_artifact,
        inputs={"member_id": "M-99999"},
        run_id="test_run_m99999",
    )

    assert result.status == ExecutionStatus.BUSINESS_OUTCOME
    assert result.outcome_code == ResultCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_replay_scenario_d_human_required(member_artifact, tmp_path):
    """Test D: M-88888 -> HUMAN_REQUIRED (stops and does NOT auto-click Verify & Continue)."""
    engine = ReplayEngine(evidence_dir=tmp_path)
    result = await engine.execute(
        artifact=member_artifact,
        inputs={"member_id": "M-88888"},
        run_id="test_run_m88888",
    )

    assert result.status == ExecutionStatus.HUMAN_REQUIRED
    assert result.outcome_code == ResultCode.MANUAL_VERIFICATION
    assert result.intervention_request is not None
    assert "manual verification" in result.intervention_request.reason.lower()


@pytest.mark.asyncio
async def test_replay_scenario_e_slow_load(member_artifact, tmp_path):
    """Test E: M-77777 -> SUCCESS despite controlled server delay."""
    engine = ReplayEngine(evidence_dir=tmp_path)
    result = await engine.execute(
        artifact=member_artifact,
        inputs={"member_id": "M-77777"},
        run_id="test_run_m77777",
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert result.outcome_code == ResultCode.SUCCESS
    assert result.extracted_data.get("savings_balance") == 8910.00


# ---------------------------------------------------------------------------
# 2. Critical Architectural Proof: ZERO LLM Replay
# ---------------------------------------------------------------------------

def test_zero_llm_architectural_guarantee():
    """Verify ReplayEngine has zero OpenAI imports or dependencies."""
    import backend.automation.replay as replay_module
    import inspect

    source = inspect.getsource(replay_module)
    assert "openai" not in source.lower()
    assert "langchain" not in source.lower()
    assert "langgraph" not in source.lower()


@pytest.mark.asyncio
async def test_replay_succeeds_without_openai_api_key(member_artifact, monkeypatch, tmp_path):
    """Verify ReplayEngine executes to completion when OPENAI_API_KEY is completely removed."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    
    engine = ReplayEngine(evidence_dir=tmp_path)
    result = await engine.execute(
        artifact=member_artifact,
        inputs={"member_id": "M-10428"},
        run_id="test_run_no_key",
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert result.extracted_data.get("savings_balance") == 4283.42


# ---------------------------------------------------------------------------
# 3. Failure Injection & Error Handling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failure_injection_missing_locator(member_artifact, tmp_path):
    """Inject a bad locator into an in-memory artifact copy and verify HARD_FAILURE."""
    # Modify in-memory copy with non-existent button
    faulty_artifact = CapabilityArtifact.model_validate(member_artifact.to_dict())
    faulty_artifact.steps[2].action.locator = LocatorBundle(
        css="#definitely_missing_button_xyz",
        text="Definitely Missing Button",
    )

    engine = ReplayEngine(evidence_dir=tmp_path)
    result = await engine.execute(
        artifact=faulty_artifact,
        inputs={"member_id": "M-10428"},
        run_id="test_run_faulty_locator",
    )

    assert result.status == ExecutionStatus.HARD_FAILURE
    assert result.outcome_code == ResultCode.TARGET_NOT_FOUND
    assert result.details.get("screenshot_path") is not None


# ---------------------------------------------------------------------------
# 4. Sensitive Data Redaction & Evidence Recording Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evidence_sensitive_data_redaction(member_artifact, tmp_path):
    """Verify that sensitive marked inputs and tokens are sanitized in JSONL evidence."""
    # Mark member_id as sensitive in artifact copy
    sensitive_artifact = CapabilityArtifact.model_validate(member_artifact.to_dict())
    sensitive_artifact.inputs["member_id"].sensitive = True

    engine = ReplayEngine(evidence_dir=tmp_path)
    run_id = "test_run_redaction"
    await engine.execute(
        artifact=sensitive_artifact,
        inputs={"member_id": "M-10428"},
        run_id=run_id,
    )

    log_file = tmp_path / f"{run_id}.jsonl"
    assert log_file.exists()

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) > 0
    raw_content = "".join(lines)

    # Ensure full sensitive value M-10428 is masked when marked sensitive
    assert "M-10***" in raw_content or "[REDACTED" in raw_content
