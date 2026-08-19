"""Unit and integration tests for Human Handoff, Control Ownership, and FastAPI backend endpoints."""

import asyncio
from pathlib import Path
import threading
import time
import pytest
import uvicorn
from fastapi.testclient import TestClient

from backend.automation.browser import BrowserController
from backend.automation.replay import ReplayEngine
from backend.core.artifact import CapabilityArtifact
from backend.core.errors import BankingAgentError, ResultCode
from backend.core.handoff import (
    ControlOwner,
    HandoffCoordinator,
    InterventionStatus,
    RunStatus,
    handoff_coordinator,
)
from backend.core.models import ExecutionStatus, LocatorBundle
from backend.main import app
from demo_bank.app import app as demo_bank_app


@pytest.fixture(scope="session")
def live_server_url():
    """Start local demo bank server on dedicated test port."""
    port = 8768
    config = uvicorn.Config(demo_bank_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.6)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.fixture
def api_client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Control Ownership State Machine Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_control_ownership_transitions(tmp_path):
    coordinator = HandoffCoordinator(evidence_dir=tmp_path)
    run = coordinator.create_run_record(run_id="test_run_1", capability_id="member.get_savings_balance")

    assert run.control_owner == ControlOwner.AUTOMATION
    assert run.status == RunStatus.RUNNING

    # 1. Trigger HUMAN_REQUIRED
    intv = await coordinator.create_intervention(
        run_id="test_run_1",
        capability_id="member.get_savings_balance",
        reason="Additional Verification Required",
        human_readable_summary="Operator verification needed.",
    )
    assert intv.status == InterventionStatus.PENDING
    assert run.status == RunStatus.HUMAN_REQUIRED
    assert run.control_owner == ControlOwner.AUTOMATION

    # 2. Operator Takes Control: PAUSED -> HUMAN
    updated_intv = await coordinator.take_control(intv.intervention_id)
    assert updated_intv.control_owner == ControlOwner.HUMAN
    assert updated_intv.status == InterventionStatus.IN_PROGRESS
    assert run.control_owner == ControlOwner.HUMAN
    assert run.status == RunStatus.PAUSED

    # 3. Invalid Transition: Double take-control rejected
    with pytest.raises(BankingAgentError):
        await coordinator.take_control(intv.intervention_id)


@pytest.mark.asyncio
async def test_completed_run_cannot_be_interrupted(tmp_path):
    coordinator = HandoffCoordinator(evidence_dir=tmp_path)
    run = coordinator.create_run_record(run_id="test_run_done", capability_id="member.get_savings_balance")
    run.status = RunStatus.SUCCESS

    with pytest.raises(BankingAgentError, match="terminal"):
        await coordinator.create_intervention(
            run_id="test_run_done",
            capability_id="member.get_savings_balance",
            reason="Test",
            human_readable_summary="Test",
        )


# ---------------------------------------------------------------------------
# 2. Critical M-88888 Same-Session Takeover and Resume Integration Test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m88888_same_session_takeover_and_resume(live_server_url, tmp_path):
    """Demonstrate M-88888 pausing on verification, human taking control of SAME session, verifying, and resuming to SUCCESS."""
    artifact = CapabilityArtifact.load_yaml("artifacts/member_balance_v1.yaml")
    artifact.steps[0].action.target_url = f"{live_server_url}/members/search"

    coordinator = HandoffCoordinator(evidence_dir=tmp_path)
    run_id = "run_m88888_handoff_demo"
    run = coordinator.create_run_record(run_id=run_id, capability_id=artifact.capability_id, inputs={"member_id": "M-88888"})

    browser = BrowserController(headless=True)
    await browser.start()

    await coordinator.register_session(
        run_id=run_id,
        browser=browser,
        artifact=artifact,
        inputs={"member_id": "M-88888"},
    )

    replay_engine = ReplayEngine(evidence_dir=tmp_path)

    # 1. Step 1: Replay starts and hits M-88888 verification gate
    result = await replay_engine.execute(
        artifact=artifact,
        inputs={"member_id": "M-88888"},
        browser=browser,
        run_id=run_id,
    )

    assert result.status == ExecutionStatus.HUMAN_REQUIRED
    assert result.outcome_code == ResultCode.MANUAL_VERIFICATION

    # 2. Create pending intervention
    intv = await coordinator.create_intervention(
        run_id=run_id,
        capability_id=artifact.capability_id,
        reason="Additional Verification Required",
        human_readable_summary="Operator must confirm manual identity match.",
        step_id="submit_member_search",
    )
    assert run.status == RunStatus.HUMAN_REQUIRED

    # 3. Operator claims control: control_owner -> HUMAN
    await coordinator.take_control(intv.intervention_id)
    assert run.control_owner == ControlOwner.HUMAN

    # 4. Human Action on the SAME LIVE BROWSER SESSION: clicks Verify & Continue
    # (Simulated by human operator interacting with the active browser instance)
    locator_verify = LocatorBundle(
        role="button",
        accessible_name="Verify & Continue",
        text="Verify & Continue",
        css="#btn_verify_continue",
    )
    await browser.click(locator_verify)

    # 5. Operator clicks Resume: coordinator validates safe state, transfers control to AUTOMATION, and finishes replay
    resume_result = await coordinator.resume_automation(intv.intervention_id, resolution_notes="Operator verified customer ID.")

    assert resume_result["status"] == "SUCCESS"
    assert resume_result["control_owner"] == "AUTOMATION"
    assert resume_result["outputs"].get("savings_balance") == 5125.75
    assert run.status == RunStatus.SUCCESS
    assert run.outputs.get("savings_balance") == 5125.75


# ---------------------------------------------------------------------------
# 3. FastAPI Endpoint Unit Tests
# ---------------------------------------------------------------------------

def test_api_health(api_client):
    r = api_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "Banking Agent"}


def test_api_capabilities(api_client):
    r = api_client.get("/api/capabilities")
    assert r.status_code == 200
    caps = r.json()
    assert len(caps) >= 1
    assert any(c["capability_id"] == "member.get_savings_balance" for c in caps)


def test_api_capability_detail(api_client):
    r = api_client.get("/api/capabilities/member.get_savings_balance")
    assert r.status_code == 200
    detail = r.json()
    assert detail["capability_id"] == "member.get_savings_balance"
    assert "inputs" in detail


def test_api_capability_not_found(api_client):
    r = api_client.get("/api/capabilities/non_existent_capability")
    assert r.status_code == 404


def test_api_start_replay_and_run_status(api_client):
    r_post = api_client.post(
        "/api/capabilities/member.get_savings_balance/replay",
        json={"inputs": {"member_id": "M-10428"}},
    )
    assert r_post.status_code == 202
    data = r_post.json()
    assert "run_id" in data

    run_id = data["run_id"]
    r_status = api_client.get(f"/api/runs/{run_id}")
    assert r_status.status_code == 200
    status_data = r_status.json()
    assert status_data["run_id"] == run_id


def test_api_unknown_run_404(api_client):
    r = api_client.get("/api/runs/unknown_run_xyz")
    assert r.status_code == 404


def test_api_invalid_take_control_409(api_client):
    r = api_client.post("/api/interventions/non_existent_intv/take-control")
    assert r.status_code == 409 or r.status_code == 404
