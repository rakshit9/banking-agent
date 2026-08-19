"""Unit and integration tests for CapabilityArtifact, LocatorBundle, LocatorResolver, Checkpoints, and BrowserController."""

import asyncio
import threading
from pathlib import Path
import pytest
import uvicorn
import yaml

from backend.automation.browser import BrowserController
from backend.automation.checkpoints import CheckpointEvaluator
from backend.automation.locators import LocatorResolver
from backend.core.artifact import CapabilityArtifact, InputProperty, OutputProperty, StepArtifact
from backend.core.errors import ArtifactValidationError, LocatorResolutionError, ResultCode
from backend.core.models import (
    Action,
    ActionType,
    Checkpoint,
    CheckpointType,
    ExecutionStatus,
    LocatorBundle,
    ResolutionStatus,
    RiskLevel,
)
from demo_bank.app import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_server_url():
    """Start local demo bank server on a test port for live Playwright tests."""
    port = 8765
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Allow server to bind and listen
    import time
    time.sleep(0.6)

    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


# ---------------------------------------------------------------------------
# 1. Capability Artifact & Serialization Tests
# ---------------------------------------------------------------------------

def test_valid_capability_artifact_creation():
    artifact = CapabilityArtifact(
        schema_version="1.0",
        capability_id="test.capability",
        name="Test Capability",
        version="1.0.0",
        description="A test capability artifact",
        target_application="Northstar Core",
        inputs={
            "member_id": InputProperty(type="string", required=True, description="Member ID parameter")
        },
        outputs={
            "balance": OutputProperty(type="string", required=True, description="Extracted balance")
        },
        steps=[
            StepArtifact(
                step_id="fill_id",
                description="Fill member identifier",
                action=Action(
                    action_type=ActionType.FILL,
                    value_from_input="member_id",
                    locator=LocatorBundle(role="textbox", accessible_name="Member ID"),
                ),
            )
        ],
    )
    assert artifact.schema_version == "1.0"
    assert artifact.version == "1.0.0"
    assert "member_id" in artifact.inputs
    assert artifact.steps[0].action.value_from_input == "member_id"


def test_invalid_artifact_undeclared_input_rejected():
    with pytest.raises(ValueError, match="not declared in capability inputs"):
        CapabilityArtifact(
            capability_id="test.invalid",
            name="Invalid Capability",
            description="Testing invalid input reference",
            target_application="Northstar Core",
            inputs={},  # No inputs declared
            steps=[
                StepArtifact(
                    step_id="bad_step",
                    description="References undeclared input",
                    action=Action(
                        action_type=ActionType.FILL,
                        value_from_input="undeclared_param",
                        locator=LocatorBundle(css="#input"),
                    ),
                )
            ],
        )


def test_yaml_round_trip():
    yaml_path = Path("artifacts/member_balance_v1.yaml")
    assert yaml_path.exists(), "member_balance_v1.yaml must exist on disk."

    # Load from disk
    artifact = CapabilityArtifact.load_yaml(yaml_path)
    assert artifact.schema_version == "1.0"
    assert artifact.capability_id == "member.get_savings_balance"
    assert artifact.inputs["member_id"].required is True

    # Parameterization check: member_id is parameterized, not hardcoded M-10428 in reusable action
    step_fill = next(s for s in artifact.steps if s.step_id == "enter_member_id")
    assert step_fill.action.value_from_input == "member_id"
    assert step_fill.action.value != "M-10428"

    # Serialize to YAML and re-parse
    serialized_yaml = artifact.to_yaml()
    reloaded = CapabilityArtifact.load_yaml(serialized_yaml)

    assert reloaded.capability_id == artifact.capability_id
    assert len(reloaded.steps) == len(artifact.steps)
    assert reloaded.safety.read_only is True


# ---------------------------------------------------------------------------
# 2. LocatorBundle Model Tests
# ---------------------------------------------------------------------------

def test_locator_bundle_semantic_and_fallbacks():
    bundle = LocatorBundle(
        role="textbox",
        accessible_name="Member ID",
        label="Member ID",
        stable_attributes={"id": "member_id"},
        css="#member_id",
        xpath="//input[@id='member_id']",
    )
    assert bundle.role == "textbox"
    assert bundle.accessible_name == "Member ID"
    assert bundle.css == "#member_id"


def test_empty_locator_bundle_rejected():
    with pytest.raises(ValueError, match="at least one valid locator strategy"):
        LocatorBundle()


# ---------------------------------------------------------------------------
# 3. Deterministic Locator Resolver Tests (Playwright Isolated DOM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_locator_resolver_strategies():
    async with BrowserController(headless=True) as browser:
        page = browser.page
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <label for="member_id">Member ID</label>
            <input type="text" id="member_id" name="member_id" placeholder="Enter ID" />
            <button id="search_button" type="submit">Search</button>
            <a id="btn_view_savings" href="/accounts/savings">View Savings</a>
        </body>
        </html>
        """
        await page.set_content(html_content)

        # 1. Resolve textbox via role + accessible name
        bundle_textbox = LocatorBundle(
            role="textbox",
            accessible_name="Member ID",
            label="Member ID",
            css="#member_id",
        )
        res_textbox = await LocatorResolver.resolve(page, bundle_textbox)
        assert res_textbox.status == ResolutionStatus.FOUND
        assert res_textbox.is_found
        assert "role_accessible_name" in res_textbox.strategy_used

        # 2. Resolve button via role + accessible name
        bundle_button = LocatorBundle(
            role="button",
            accessible_name="Search",
            text="Search",
            css="#search_button",
        )
        res_button = await LocatorResolver.resolve(page, bundle_button)
        assert res_button.status == ResolutionStatus.FOUND
        assert res_button.is_found

        # 3. Resolve link via exact text
        bundle_link = LocatorBundle(
            text="View Savings",
            css="#btn_view_savings",
        )
        res_link = await LocatorResolver.resolve(page, bundle_link)
        assert res_link.status == ResolutionStatus.FOUND

        # 4. Target not found
        bundle_missing = LocatorBundle(
            css="#non_existent_element",
            text="Does Not Exist",
        )
        res_missing = await LocatorResolver.resolve(page, bundle_missing)
        assert res_missing.status == ResolutionStatus.TARGET_NOT_FOUND
        assert not res_missing.is_found
        assert len(res_missing.strategies_attempted) == 2


@pytest.mark.asyncio
async def test_locator_resolver_ambiguous_target():
    async with BrowserController(headless=True) as browser:
        page = browser.page
        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
            <button class="duplicate-btn">Action</button>
            <button class="duplicate-btn">Action</button>
        </body>
        </html>
        """
        await page.set_content(html_content)

        bundle_ambiguous = LocatorBundle(css=".duplicate-btn")
        res_ambiguous = await LocatorResolver.resolve(page, bundle_ambiguous)
        assert res_ambiguous.status == ResolutionStatus.AMBIGUOUS_TARGET
        assert res_ambiguous.match_count == 2

        with pytest.raises(LocatorResolutionError) as exc_info:
            res_ambiguous.get_locator_or_raise()
        assert exc_info.value.code == ResultCode.AMBIGUOUS_TARGET


# ---------------------------------------------------------------------------
# 4. Checkpoint Evaluator Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_checkpoint_evaluator_types():
    async with BrowserController(headless=True) as browser:
        page = browser.page
        await page.set_content("""
        <html>
            <head><title>Member Detail</title></head>
            <body>
                <h1>Member Record Overview</h1>
                <div id="balance">$4,283.42</div>
            </body>
        </html>
        """)

        # 1. TEXT_VISIBLE (Success)
        cp_text_pass = Checkpoint(type=CheckpointType.TEXT_VISIBLE, expected="Member Record Overview")
        res_text_pass = await CheckpointEvaluator.evaluate(cp_text_pass, page)
        assert res_text_pass.passed is True
        assert res_text_pass.checkpoint_type == CheckpointType.TEXT_VISIBLE

        # 2. TEXT_VISIBLE (Failure)
        cp_text_fail = Checkpoint(type=CheckpointType.TEXT_VISIBLE, expected="Non Existent Notice")
        res_text_fail = await CheckpointEvaluator.evaluate(cp_text_fail, page)
        assert res_text_fail.passed is False

        # 3. URL_CONTAINS
        cp_url = Checkpoint(type=CheckpointType.URL_CONTAINS, expected="about:blank")
        res_url = await CheckpointEvaluator.evaluate(cp_url, page)
        assert res_url.passed is True

        # 4. OUTPUT_PRESENT
        cp_output_pass = Checkpoint(type=CheckpointType.OUTPUT_PRESENT, expected="savings_balance")
        res_output_pass = await CheckpointEvaluator.evaluate(
            cp_output_pass, page, extracted_data={"savings_balance": "$4,283.42"}
        )
        assert res_output_pass.passed is True

        cp_output_fail = Checkpoint(type=CheckpointType.OUTPUT_PRESENT, expected="missing_key")
        res_output_fail = await CheckpointEvaluator.evaluate(
            cp_output_fail, page, extracted_data={"savings_balance": "$4,283.42"}
        )
        assert res_output_fail.passed is False


@pytest.mark.asyncio
async def test_checkpoint_one_of_branches():
    async with BrowserController(headless=True) as browser:
        page = browser.page
        await page.set_content("""
        <html>
            <body>
                <h2>Access Denied</h2>
                <p>You do not have permission to view this member.</p>
            </body>
        </html>
        """)

        cp_one_of = Checkpoint(
            type=CheckpointType.ONE_OF,
            branches=[
                Checkpoint(type=CheckpointType.TEXT_VISIBLE, expected="Member Record Overview", outcome_code="SUCCESS"),
                Checkpoint(type=CheckpointType.TEXT_VISIBLE, expected="Member Not Found", outcome_code="MEMBER_NOT_FOUND"),
                Checkpoint(type=CheckpointType.TEXT_VISIBLE, expected="Access Denied", outcome_code="PERMISSION_DENIED"),
                Checkpoint(type=CheckpointType.TEXT_VISIBLE, expected="Additional Verification Required", outcome_code="MANUAL_VERIFICATION"),
            ],
        )

        res_one_of = await CheckpointEvaluator.evaluate(cp_one_of, page)
        assert res_one_of.passed is True
        assert res_one_of.matched_outcome == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# 5. Live BrowserController Session Persistence Integration Test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_browser_controller_live_flow_and_session_persistence(live_server_url):
    """Test BrowserController executing against live demo bank preserving single context session."""
    async with BrowserController(headless=True) as browser:
        # 1. Navigate to Member Search
        obs = await browser.navigate(f"{live_server_url}/members/search")
        assert "Member Search" in obs.title or "Northstar Core" in obs.title

        # 2. Fill search form with M-88888 (Manual Verification scenario)
        locator_input = LocatorBundle(
            role="textbox",
            accessible_name="Member ID",
            label="Member ID",
            css="#member_id",
        )
        await browser.fill(locator_input, "M-88888")

        # 3. Click Search
        locator_search = LocatorBundle(
            role="button",
            accessible_name="Search",
            css="#search_button",
        )
        await browser.click(locator_search)

        # 4. Verify landing on Additional Verification Required
        body_text = await browser.read_text(LocatorBundle(css="body"))
        assert "Additional Verification Required" in body_text

        # 5. Click Verify & Continue on the SAME session
        locator_verify = LocatorBundle(
            role="button",
            accessible_name="Verify & Continue",
            css="#btn_verify_continue",
            text="Verify & Continue",
        )
        await browser.click(locator_verify)

        # 6. Verify same context session now sees Jordan Lee member profile
        profile_text = await browser.read_text(LocatorBundle(css="body"))
        assert "Jordan Lee" in profile_text
        assert "View Savings" in profile_text

        # 7. Click View Savings
        locator_savings = LocatorBundle(
            role="link",
            accessible_name="View Savings",
            css="#btn_view_savings",
            text="View Savings",
        )
        await browser.click(locator_savings)

        # 8. Read Savings Balance
        locator_balance = LocatorBundle(css="#current_savings_balance")
        balance_val = await browser.read_text(locator_balance)
        assert balance_val == "$5,125.75" or balance_val == "$5125.75"
