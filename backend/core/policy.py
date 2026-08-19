"""Deterministic policy engine for pre-execution action gating and security boundaries."""

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field

from backend.config import settings
from backend.core.models import Action, ActionType, RiskLevel


class PolicyDecision(str, Enum):
    """Authoritative policy evaluation decision."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_HUMAN = "REQUIRE_HUMAN"


class PolicyEvaluation(BaseModel):
    """Structured result of a policy evaluation."""

    decision: PolicyDecision
    rule_name: str
    reason: str
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    @property
    def is_blocked(self) -> bool:
        return self.decision == PolicyDecision.BLOCK

    @property
    def requires_human(self) -> bool:
        return self.decision == PolicyDecision.REQUIRE_HUMAN


class PolicyEngine:
    """Evaluates security, domain whitelisting, and risk governance policies before any browser action.
    
    Zero-LLM dependency: All rules are strictly deterministic and evaluated in-memory.
    """

    def __init__(
        self,
        allowed_domains: Optional[Set[str]] = None,
        blocked_actions: Optional[Set[ActionType]] = None,
        require_human_risk_levels: Optional[Set[RiskLevel]] = None,
        blocked_domains: Optional[Set[str]] = None,
    ):
        # Default allowed domains derived from configured Demo Bank host
        base_url = settings.DEMO_BANK_URL
        parsed_base = urlparse(base_url)
        default_allowed = {
            "127.0.0.1",
            "localhost",
            parsed_base.hostname or "127.0.0.1",
            f"{parsed_base.hostname}:{parsed_base.port}" if parsed_base.port else "127.0.0.1:8000",
            "127.0.0.1:8000",
            "localhost:8000",
        }

        self.allowed_domains: Set[str] = allowed_domains or default_allowed
        self.blocked_actions: Set[ActionType] = blocked_actions or set()
        self.require_human_risk_levels: Set[RiskLevel] = require_human_risk_levels or {
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        }
        self.blocked_domains: Set[str] = blocked_domains or set()

    def evaluate_action(
        self,
        action: Action,
        step_risk: RiskLevel = RiskLevel.LOW,
        current_url: Optional[str] = None,
    ) -> PolicyEvaluation:
        """Evaluate an action against security boundaries before execution."""

        # 1. Action Whitelist / Blacklist check
        if action.action_type in self.blocked_actions:
            return PolicyEvaluation(
                decision=PolicyDecision.BLOCK,
                rule_name="BLOCKED_ACTION_TYPE",
                reason=f"Action type '{action.action_type.value}' is explicitly blocked by security policy.",
                details={"action_type": action.action_type.value},
            )

        # 2. Destination Domain Validation for Navigation
        if action.action_type == ActionType.NAVIGATE:
            target_url = action.target_url or action.value or ""
            if target_url:
                domain_eval = self._evaluate_domain(target_url)
                if not domain_eval.is_allowed:
                    return domain_eval

        # 3. Current URL Domain Boundary Check (Ensure browser hasn't drifted out of scope)
        if current_url and current_url != "about:blank":
            curr_eval = self._evaluate_domain(current_url)
            if not curr_eval.is_allowed:
                return PolicyEvaluation(
                    decision=PolicyDecision.BLOCK,
                    rule_name="OUT_OF_SCOPE_SESSION",
                    reason=f"Active browser session drifted to unauthorized domain: '{current_url}'",
                    details={"current_url": current_url},
                )

        # 4. Step Risk Level Evaluation
        if step_risk == RiskLevel.CRITICAL:
            return PolicyEvaluation(
                decision=PolicyDecision.BLOCK,
                rule_name="CRITICAL_RISK_BLOCK",
                reason="Actions with CRITICAL risk level are blocked from automated execution.",
                details={"step_risk": step_risk.value},
            )

        if step_risk in self.require_human_risk_levels:
            return PolicyEvaluation(
                decision=PolicyDecision.REQUIRE_HUMAN,
                rule_name="HIGH_RISK_INTERVENTION",
                reason=f"Action classified as risk level '{step_risk.value}' requires human confirmation.",
                details={"step_risk": step_risk.value},
            )

        # Default Allow
        return PolicyEvaluation(
            decision=PolicyDecision.ALLOW,
            rule_name="DEFAULT_PERMIT",
            reason="Action conforms to all safety, domain, and risk governance rules.",
            details={"action_type": action.action_type.value, "step_risk": step_risk.value},
        )

    def _evaluate_domain(self, url_str: str) -> PolicyEvaluation:
        """Check if a URL conforms to domain whitelisting."""
        parsed = urlparse(url_str)
        hostname = parsed.hostname or ""
        netloc = parsed.netloc or ""

        # Explicit blocked domains check
        if hostname in self.blocked_domains or netloc in self.blocked_domains:
            return PolicyEvaluation(
                decision=PolicyDecision.BLOCK,
                rule_name="EXPLICIT_BLOCKED_DOMAIN",
                reason=f"Domain '{hostname or netloc}' is on the explicit security blacklist.",
                details={"target_url": url_str, "domain": hostname or netloc},
            )

        # Allowed domains check
        if hostname not in self.allowed_domains and netloc not in self.allowed_domains:
            return PolicyEvaluation(
                decision=PolicyDecision.BLOCK,
                rule_name="UNAUTHORIZED_DOMAIN",
                reason=f"Target domain '{hostname or netloc}' is outside authorized domain boundary {sorted(list(self.allowed_domains))}.",
                details={"target_url": url_str, "domain": hostname or netloc},
            )

        return PolicyEvaluation(
            decision=PolicyDecision.ALLOW,
            rule_name="DOMAIN_PERMITTED",
            reason=f"Domain '{hostname or netloc}' is authorized.",
            details={"target_url": url_str, "domain": hostname or netloc},
        )
