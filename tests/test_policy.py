"""Unit tests for deterministic PolicyEngine rules and security boundary enforcement."""

import pytest
from backend.core.models import Action, ActionType, LocatorBundle, RiskLevel
from backend.core.policy import PolicyDecision, PolicyEngine


@pytest.fixture
def policy_engine():
    return PolicyEngine(
        allowed_domains={"127.0.0.1", "localhost", "127.0.0.1:8000", "localhost:8000"},
        blocked_actions={ActionType.SCROLL},
        blocked_domains={"malicious-site.com", "phishing-bank.com"},
    )


def test_policy_allow_local_navigation(policy_engine):
    action = Action(
        action_type=ActionType.NAVIGATE,
        target_url="http://127.0.0.1:8000/members/search",
    )
    res = policy_engine.evaluate_action(action, step_risk=RiskLevel.LOW)
    assert res.decision == PolicyDecision.ALLOW
    assert res.is_allowed is True
    assert res.rule_name == "DEFAULT_PERMIT"


def test_policy_allow_read_action(policy_engine):
    action = Action(
        action_type=ActionType.READ,
        locator=LocatorBundle(css="#current_savings_balance"),
    )
    res = policy_engine.evaluate_action(action, step_risk=RiskLevel.LOW)
    assert res.decision == PolicyDecision.ALLOW


def test_policy_block_external_unauthorized_domain(policy_engine):
    action = Action(
        action_type=ActionType.NAVIGATE,
        target_url="https://external-untrusted-bank.com/transfer",
    )
    res = policy_engine.evaluate_action(action, step_risk=RiskLevel.LOW)
    assert res.decision == PolicyDecision.BLOCK
    assert res.is_blocked is True
    assert res.rule_name == "UNAUTHORIZED_DOMAIN"


def test_policy_block_explicitly_blacklisted_domain(policy_engine):
    action = Action(
        action_type=ActionType.NAVIGATE,
        target_url="http://malicious-site.com/steal-creds",
    )
    res = policy_engine.evaluate_action(action, step_risk=RiskLevel.LOW)
    assert res.decision == PolicyDecision.BLOCK
    assert res.rule_name == "EXPLICIT_BLOCKED_DOMAIN"


def test_policy_block_restricted_action_type(policy_engine):
    action = Action(action_type=ActionType.SCROLL)
    res = policy_engine.evaluate_action(action, step_risk=RiskLevel.LOW)
    assert res.decision == PolicyDecision.BLOCK
    assert res.rule_name == "BLOCKED_ACTION_TYPE"


def test_policy_require_human_on_high_risk(policy_engine):
    action = Action(
        action_type=ActionType.CLICK,
        locator=LocatorBundle(role="button", accessible_name="Approve Transfer"),
    )
    res = policy_engine.evaluate_action(action, step_risk=RiskLevel.HIGH)
    assert res.decision == PolicyDecision.REQUIRE_HUMAN
    assert res.requires_human is True
    assert res.rule_name == "HIGH_RISK_INTERVENTION"


def test_policy_block_on_critical_risk(policy_engine):
    action = Action(
        action_type=ActionType.CLICK,
        locator=LocatorBundle(role="button", accessible_name="Delete Account"),
    )
    res = policy_engine.evaluate_action(action, step_risk=RiskLevel.CRITICAL)
    assert res.decision == PolicyDecision.BLOCK
    assert res.rule_name == "CRITICAL_RISK_BLOCK"


def test_policy_block_out_of_scope_session_drift(policy_engine):
    action = Action(
        action_type=ActionType.CLICK,
        locator=LocatorBundle(css="#btn_submit"),
    )
    # Session drifted to unauthorized external domain
    res = policy_engine.evaluate_action(
        action,
        step_risk=RiskLevel.LOW,
        current_url="https://attacker-redirect.com/login",
    )
    assert res.decision == PolicyDecision.BLOCK
    assert res.rule_name == "OUT_OF_SCOPE_SESSION"
