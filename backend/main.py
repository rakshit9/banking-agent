"""FastAPI backend service exposing Discovery, Capabilities, Replay, and Human Handoff APIs."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.agents.graph import DiscoveryEngine
from backend.automation.browser import BrowserController
from backend.automation.replay import ReplayEngine
from backend.config import settings
from backend.core.artifact import CapabilityArtifact
from backend.core.errors import BankingAgentError, ResultCode
from backend.core.handoff import ControlOwner, RunRecord, RunStatus, handoff_coordinator
from backend.core.models import ExecutionStatus, RiskLevel
from backend.core.policy import PolicyEngine
from backend.services.evidence import RedactionEngine

app = FastAPI(
    title="Banking Agent API",
    description="Computer-use automation system for legacy banking applications",
    version="1.0.0",
)

# Enable CORS for local frontend integration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ARTIFACTS_DIR = Path("artifacts")


# --- Request & Response Models ---

class ReplayRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)


class DiscoveryRequest(BaseModel):
    goal: str = "Look up member M-10428 and return their current savings balance."
    target_url: Optional[str] = None


class ResumeRequest(BaseModel):
    resolution_notes: Optional[str] = None


class CapabilitySummary(BaseModel):
    capability_id: str
    name: str
    version: str
    description: str
    target_application: str
    risk_level: RiskLevel
    read_only: bool
    input_keys: List[str]
    output_keys: List[str]
    provenance: Optional[Dict[str, Any]] = None
    active: bool = False


# --- Helper Functions ---

def load_all_capabilities() -> List[CapabilityArtifact]:
    artifacts = []
    if ARTIFACTS_DIR.exists():
        for yaml_file in ARTIFACTS_DIR.glob("*.yaml"):
            try:
                art = CapabilityArtifact.load_yaml(yaml_file)
                artifacts.append(art)
            except Exception:
                pass
    return artifacts


def _artifact_created_at_sort_key(artifact: CapabilityArtifact) -> str:
    if artifact.provenance and artifact.provenance.created_at:
        return artifact.provenance.created_at
    return ""


def _artifact_selection_rank(artifact: CapabilityArtifact) -> tuple[int, str]:
    provenance = artifact.provenance
    source = provenance.source if provenance else None
    critic_status = provenance.critic_status if provenance else None
    approved_at = provenance.approved_at if provenance else None

    if source == "AI_DISCOVERY" and (critic_status == "APPROVED" or approved_at):
        priority = 4
    elif source == "AI_DISCOVERY":
        priority = 3
    elif source == "BOOTSTRAP":
        priority = 1
    else:
        priority = 2

    return (priority, _artifact_created_at_sort_key(artifact))


def select_active_capabilities(artifacts: List[CapabilityArtifact]) -> List[CapabilityArtifact]:
    """Select one active artifact per capability_id + version using provenance ranking."""
    selected: Dict[tuple[str, str], CapabilityArtifact] = {}
    for artifact in artifacts:
        key = (artifact.capability_id, artifact.version)
        current = selected.get(key)
        if current is None or _artifact_selection_rank(artifact) > _artifact_selection_rank(current):
            selected[key] = artifact
    return list(selected.values())


def find_capability(capability_id: str) -> Optional[CapabilityArtifact]:
    matches = [art for art in select_active_capabilities(load_all_capabilities()) if art.capability_id == capability_id]
    if not matches:
        return None
    return max(matches, key=_artifact_selection_rank)


async def run_replay_task(run_id: str, artifact: CapabilityArtifact, inputs: Dict[str, Any]):
    """Execute deterministic replay in background and coordinate handoff if interrupted."""
    run_record = handoff_coordinator.get_run(run_id)
    browser = BrowserController(headless=settings.HEADLESS)
    await browser.start()

    # Register active session in handoff coordinator
    await handoff_coordinator.register_session(
        run_id=run_id,
        browser=browser,
        artifact=artifact,
        inputs=inputs,
    )

    replay_engine = ReplayEngine()

    try:
        result = await replay_engine.execute(
            artifact=artifact,
            inputs=inputs,
            browser=browser,
            run_id=run_id,
        )

        if result.status == ExecutionStatus.HUMAN_REQUIRED:
            # Human intervention needed: create intervention record and keep browser open
            intv_req = result.intervention_request
            reason = intv_req.reason if intv_req else "Human verification required."
            await handoff_coordinator.create_intervention(
                run_id=run_id,
                capability_id=artifact.capability_id,
                reason=reason,
                human_readable_summary="Manual operator verification required at security gate.",
                step_id=intv_req.current_step if intv_req else "enter_member_id",
                screenshot_path=intv_req.screenshot_path if intv_req else None,
            )
        elif result.status == ExecutionStatus.SUCCESS:
            run_record.status = RunStatus.SUCCESS
            run_record.outputs = result.extracted_data
            await handoff_coordinator.release_session(run_id)
        elif result.status == ExecutionStatus.BUSINESS_OUTCOME:
            run_record.status = RunStatus.BUSINESS_OUTCOME
            run_record.outcome_code = result.outcome_code.value
            run_record.outputs = result.extracted_data
            await handoff_coordinator.release_session(run_id)
        else:
            run_record.status = RunStatus.FAILED
            run_record.error = result.error_message or "Execution failed."
            await handoff_coordinator.release_session(run_id)

    except Exception as e:
        if run_record:
            run_record.status = RunStatus.FAILED
            run_record.error = str(e)
        await handoff_coordinator.release_session(run_id)


async def run_discovery_task(run_id: str, goal: str, target_url: str):
    """Execute LangGraph discovery workflow in background."""
    run_record = handoff_coordinator.get_run(run_id)
    browser = BrowserController(headless=settings.HEADLESS)
    await browser.start()

    try:
        engine = DiscoveryEngine(browser=browser)
        graph = engine.build_graph()

        initial_state = {
            "run_id": run_id,
            "goal": goal,
            "target_url": target_url,
            "current_observation": {},
            "screenshot_path": None,
            "action_history": [],
            "discovery_trace": [],
            "step_count": 0,
            "max_steps": settings.MAX_DISCOVERY_STEPS,
            "goal_complete": False,
            "extracted_outputs": {},
            "proposed_action": None,
            "compiled_artifact": None,
            "critic_review": None,
            "refinement_count": 0,
            "max_refinements": 2,
            "status": "QUEUED",
            "error": None,
            "saved_artifact_path": None,
            "call_count": 0,
        }

        final_state = await graph.ainvoke(initial_state)

        if final_state.get("status") == "SUCCESS":
            run_record.status = RunStatus.SUCCESS
            run_record.outputs = final_state.get("extracted_outputs", {})
        else:
            run_record.status = RunStatus.FAILED
            run_record.error = final_state.get("error", "Discovery did not achieve goal.")
    except Exception as e:
        if run_record:
            run_record.status = RunStatus.FAILED
            run_record.error = str(e)
    finally:
        await browser.close()


# --- API Routes ---

@app.get("/api/health")
async def get_health():
    """Health check endpoint."""
    return {"status": "ok", "service": "Banking Agent"}


@app.get("/api/capabilities", response_model=List[CapabilitySummary])
async def list_capabilities():
    """List available saved capability summaries."""
    artifacts = select_active_capabilities(load_all_capabilities())
    summaries = []
    for art in artifacts:
        summaries.append(
            CapabilitySummary(
                capability_id=art.capability_id,
                name=art.name,
                version=art.version,
                description=art.description,
                target_application=art.target_application,
                risk_level=art.safety.risk_level,
                read_only=art.safety.read_only,
                input_keys=list(art.inputs.keys()),
                output_keys=list(art.outputs.keys()),
                provenance=art.provenance.model_dump(mode="json", exclude_none=True) if art.provenance else None,
                active=True,
            )
        )
    return summaries


@app.get("/api/capabilities/{capability_id}")
async def get_capability_detail(capability_id: str):
    """Retrieve full CapabilityArtifact specification."""
    art = find_capability(capability_id)
    if not art:
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found.")
    response = art.to_dict()
    response["active"] = True
    return response


@app.post("/api/capabilities/{capability_id}/replay", status_code=status.HTTP_202_ACCEPTED)
async def start_replay(capability_id: str, req: ReplayRequest, background_tasks: BackgroundTasks):
    """Launch deterministic replay in background."""
    art = find_capability(capability_id)
    if not art:
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found.")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    run_record = handoff_coordinator.create_run_record(
        run_id=run_id,
        capability_id=capability_id,
        mode="replay",
        inputs=req.inputs,
    )

    background_tasks.add_task(run_replay_task, run_id, art, req.inputs)

    return {
        "run_id": run_id,
        "capability_id": capability_id,
        "status": run_record.status.value,
    }


@app.post("/api/discovery", status_code=status.HTTP_202_ACCEPTED)
async def start_discovery(req: DiscoveryRequest, background_tasks: BackgroundTasks):
    """Launch AI discovery exploration in background."""
    run_id = f"disc_{uuid.uuid4().hex[:8]}"
    target_url = req.target_url or f"{settings.DEMO_BANK_URL}/"

    run_record = handoff_coordinator.create_run_record(
        run_id=run_id,
        capability_id="discovery.in_progress",
        mode="discovery",
        inputs={"goal": req.goal, "target_url": target_url},
    )

    background_tasks.add_task(run_discovery_task, run_id, req.goal, target_url)

    return {
        "run_id": run_id,
        "status": run_record.status.value,
        "goal": req.goal,
    }


@app.get("/api/runs/{run_id}")
async def get_run_status(run_id: str):
    """Get sanitized execution run status."""
    run = handoff_coordinator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    # Sanitize inputs in response
    sanitized_inputs = RedactionEngine.sanitize(run.inputs)
    return {
        "run_id": run.run_id,
        "mode": run.mode,
        "capability_id": run.capability_id,
        "status": run.status.value,
        "current_step": run.current_step,
        "control_owner": run.control_owner.value,
        "inputs": sanitized_inputs,
        "outputs": run.outputs,
        "outcome_code": run.outcome_code,
        "error": run.error,
        "intervention_id": run.intervention_id,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


@app.get("/api/interventions")
async def list_interventions():
    """List all active or pending interventions."""
    return list(handoff_coordinator.interventions.values())


@app.get("/api/interventions/{intervention_id}")
async def get_intervention_detail(intervention_id: str):
    """Retrieve detailed intervention record."""
    intv = handoff_coordinator.interventions.get(intervention_id)
    if not intv:
        raise HTTPException(status_code=404, detail=f"Intervention '{intervention_id}' not found.")
    return intv


@app.post("/api/interventions/{intervention_id}/take-control")
async def take_control(intervention_id: str):
    """Transfer browser control authority to human operator."""
    try:
        updated = await handoff_coordinator.take_control(intervention_id)
        return {
            "intervention_id": updated.intervention_id,
            "status": updated.status.value,
            "control_owner": updated.control_owner.value,
            "message": "Control successfully transferred to HUMAN operator.",
        }
    except BankingAgentError as e:
        raise HTTPException(status_code=409, detail=e.message)


@app.post("/api/interventions/{intervention_id}/resume")
async def resume_automation(intervention_id: str, req: Optional[ResumeRequest] = None):
    """Validate safe state and resume deterministic replay on same session."""
    notes = req.resolution_notes if req else None
    try:
        result = await handoff_coordinator.resume_automation(intervention_id, resolution_notes=notes)
        return result
    except BankingAgentError as e:
        raise HTTPException(status_code=409, detail=e.message)


@app.post("/api/interventions/{intervention_id}/cancel")
async def cancel_intervention(intervention_id: str):
    """Cancel intervention and terminate session."""
    try:
        canceled = await handoff_coordinator.cancel_intervention(intervention_id)
        return {
            "intervention_id": canceled.intervention_id,
            "status": canceled.status.value,
            "message": "Intervention and run cancelled.",
        }
    except BankingAgentError as e:
        raise HTTPException(status_code=404, detail=e.message)
