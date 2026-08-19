from fastapi.testclient import TestClient

import backend.main as backend_main
from backend.core.artifact import CapabilityArtifact, ProvenanceMetadata
from backend.core.models import ActionType, LocatorBundle


def make_artifact(
    capability_id: str = "member.get_savings_balance",
    *,
    name: str = "Get Member Savings Balance",
    source: str | None = "AI_DISCOVERY",
    created_at: str | None = "2026-08-18T16:42:31Z",
    critic_status: str | None = None,
    approved_at: str | None = None,
) -> CapabilityArtifact:
    provenance = None
    if source or created_at or critic_status or approved_at:
        provenance = ProvenanceMetadata(
            source=source,
            discovery_run_id="disc_test_123" if source == "AI_DISCOVERY" else None,
            created_at=created_at,
            updated_at=created_at,
            approved_at=approved_at,
            critic_status=critic_status,
        )

    return CapabilityArtifact(
        schema_version="1.0",
        capability_id=capability_id,
        name=name,
        version="1.0.0",
        description="Lookup member savings balance",
        target_application="Northstar Core",
        provenance=provenance,
        inputs={"member_id": {"type": "string", "required": True}},
        outputs={"savings_balance": {"type": "string", "required": True}},
        steps=[
            {
                "step_id": "enter_member_id",
                "description": "Enter member ID",
                "action": {
                    "action_type": ActionType.FILL,
                    "value_from_input": "member_id",
                    "locator": LocatorBundle(css="#member_id"),
                },
            },
            {
                "step_id": "extract_balance",
                "description": "Extract savings balance",
                "action": {
                    "action_type": ActionType.EXTRACT,
                    "extract_key": "savings_balance",
                    "locator": LocatorBundle(css="#current_savings_balance"),
                },
            },
        ],
    )


def test_created_at_persists_after_artifact_creation():
    artifact = make_artifact(source=None, created_at=None)
    artifact.ensure_provenance(source="AI_DISCOVERY", discovery_run_id="disc_created")

    assert artifact.provenance is not None
    assert artifact.provenance.created_at is not None

    created_at = artifact.provenance.created_at
    artifact.ensure_provenance(source="AI_DISCOVERY", discovery_run_id="disc_created")

    assert artifact.provenance.created_at == created_at


def test_timestamps_survive_serialization_deserialization(tmp_path):
    artifact = make_artifact(
        created_at="2026-08-18T16:42:31Z",
        critic_status="APPROVED",
        approved_at="2026-08-18T16:45:02Z",
    )
    artifact.mark_activated(timestamp="2026-08-18T16:45:03Z")

    path = tmp_path / "artifact.yaml"
    artifact.save_yaml(path)
    loaded = CapabilityArtifact.load_yaml(path)

    assert loaded.provenance is not None
    assert loaded.provenance.created_at == "2026-08-18T16:42:31Z"
    assert loaded.provenance.approved_at == "2026-08-18T16:45:02Z"
    assert loaded.provenance.activated_at == "2026-08-18T16:45:03Z"


def test_repeated_get_requests_do_not_modify_timestamps(tmp_path, monkeypatch):
    artifact = make_artifact(
        created_at="2026-08-18T16:42:31Z",
        critic_status="APPROVED",
        approved_at="2026-08-18T16:45:02Z",
    )
    artifact.mark_activated(timestamp="2026-08-18T16:45:03Z")
    artifact.save_yaml(tmp_path / "artifact.yaml")
    monkeypatch.setattr(backend_main, "ARTIFACTS_DIR", tmp_path)

    client = TestClient(backend_main.app)
    first = client.get("/api/capabilities/member.get_savings_balance").json()["provenance"]
    second = client.get("/api/capabilities/member.get_savings_balance").json()["provenance"]

    assert first == second


def test_approved_at_is_set_only_on_approval():
    rejected = make_artifact(created_at=None)
    rejected.mark_approved(False, timestamp="2026-08-18T16:45:02Z")
    assert rejected.provenance is not None
    assert rejected.provenance.critic_status == "NOT_APPROVED"
    assert rejected.provenance.approved_at is None

    approved = make_artifact(created_at=None)
    approved.mark_approved(True, timestamp="2026-08-18T16:45:02Z")
    assert approved.provenance is not None
    assert approved.provenance.critic_status == "APPROVED"
    assert approved.provenance.approved_at == "2026-08-18T16:45:02Z"


def test_activated_at_is_set_when_artifact_becomes_active():
    artifact = make_artifact(created_at=None)
    artifact.mark_activated(timestamp="2026-08-18T16:45:03Z")

    assert artifact.provenance is not None
    assert artifact.provenance.activated_at == "2026-08-18T16:45:03Z"


def test_duplicate_selection_can_use_created_at_as_fallback():
    older = make_artifact(name="Older", source=None, created_at="2026-08-18T16:00:00Z")
    newer = make_artifact(name="Newer", source=None, created_at="2026-08-18T17:00:00Z")

    selected = backend_main.select_active_capabilities([older, newer])

    assert len(selected) == 1
    assert selected[0].name == "Newer"


def test_duplicate_selection_prefers_approved_ai_discovered_artifact():
    bootstrap = make_artifact(name="Bootstrap", source="BOOTSTRAP", created_at=None)
    discovered = make_artifact(
        name="Discovered",
        source="AI_DISCOVERY",
        created_at=None,
        critic_status="APPROVED",
        approved_at=None,
    )

    selected = backend_main.select_active_capabilities([bootstrap, discovered])

    assert selected[0].name == "Discovered"


def test_old_artifacts_without_timestamps_still_load():
    artifact = CapabilityArtifact.load_yaml(
        """
schema_version: '1.0'
capability_id: legacy.capability
name: Legacy Capability
version: 1.0.0
description: Legacy artifact without provenance
target_application: Northstar Core
inputs:
  member_id:
    type: string
    required: true
outputs:
  savings_balance:
    type: string
    required: true
steps:
- step_id: enter_member_id
  description: Enter member ID
  action:
    action_type: fill
    value_from_input: member_id
    locator:
      css: '#member_id'
"""
    )

    assert artifact.provenance is None


def test_api_returns_timestamp_and_provenance_metadata(tmp_path, monkeypatch):
    artifact = make_artifact(
        created_at="2026-08-18T16:42:31Z",
        critic_status="APPROVED",
        approved_at="2026-08-18T16:45:02Z",
    )
    artifact.mark_activated(timestamp="2026-08-18T16:45:03Z")
    artifact.save_yaml(tmp_path / "artifact.yaml")
    monkeypatch.setattr(backend_main, "ARTIFACTS_DIR", tmp_path)

    client = TestClient(backend_main.app)
    summary = client.get("/api/capabilities").json()[0]
    detail = client.get("/api/capabilities/member.get_savings_balance").json()

    assert summary["active"] is True
    assert summary["provenance"]["source"] == "AI_DISCOVERY"
    assert summary["provenance"]["created_at"] == "2026-08-18T16:42:31Z"
    assert detail["active"] is True
    assert detail["provenance"]["approved_at"] == "2026-08-18T16:45:02Z"
