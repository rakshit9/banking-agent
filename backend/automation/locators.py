"""Deterministic locator resolution engine with semantic prioritization and multi-strategy fallbacks."""

from typing import List, Optional
from playwright.async_api import Locator, Page

from backend.core.errors import LocatorResolutionError, ResultCode
from backend.core.models import LocatorBundle, ResolutionDiagnostic, ResolutionStatus


class ResolutionResult:
    """Structured outcome from resolving a LocatorBundle on a Playwright page."""

    def __init__(
        self,
        status: ResolutionStatus,
        locator: Optional[Locator] = None,
        strategy_used: Optional[str] = None,
        strategies_attempted: Optional[List[str]] = None,
        match_count: int = 0,
        failure_reason: Optional[str] = None,
    ):
        self.status = status
        self.locator = locator
        self.strategy_used = strategy_used
        self.strategies_attempted = strategies_attempted or []
        self.match_count = match_count
        self.failure_reason = failure_reason

    @property
    def is_found(self) -> bool:
        return self.status == ResolutionStatus.FOUND and self.locator is not None

    def to_diagnostic(self) -> ResolutionDiagnostic:
        return ResolutionDiagnostic(
            status=self.status,
            strategy_used=self.strategy_used,
            strategies_attempted=self.strategies_attempted,
            match_count=self.match_count,
            failure_reason=self.failure_reason,
        )

    def get_locator_or_raise(self) -> Locator:
        """Return the resolved Playwright Locator or raise a typed LocatorResolutionError."""
        if self.is_found and self.locator is not None:
            return self.locator
        
        if self.status == ResolutionStatus.AMBIGUOUS_TARGET:
            raise LocatorResolutionError(
                message=self.failure_reason or f"Ambiguous target: multiple elements ({self.match_count}) matched.",
                code=ResultCode.AMBIGUOUS_TARGET,
                details=self.to_diagnostic().model_dump(),
            )
        
        raise LocatorResolutionError(
            message=self.failure_reason or "Target element not found using any strategy in bundle.",
            code=ResultCode.TARGET_NOT_FOUND,
            details=self.to_diagnostic().model_dump(),
        )


class LocatorResolver:
    """Resolves LocatorBundle instances against active DOM using strict semantic precedence.
    
    Resolution Priority:
    1. Role + Accessible Name (Semantic accessibility tree)
    2. Label (Associated <label> elements)
    3. Stable Attributes (id, name, data attributes)
    4. Exact Visible Text
    5. CSS Selector
    6. XPath Selector
    """

    @classmethod
    async def resolve(cls, page: Page, bundle: LocatorBundle, check_visibility: bool = True) -> ResolutionResult:
        strategies_attempted: List[str] = []

        # Strategy 1: Role + Accessible Name
        if bundle.role and bundle.accessible_name:
            strategy_name = f"role_accessible_name(role='{bundle.role}', name='{bundle.accessible_name}')"
            strategies_attempted.append(strategy_name)
            candidate = page.get_by_role(bundle.role, name=bundle.accessible_name)
            result = await cls._evaluate_candidate(candidate, strategy_name, strategies_attempted, check_visibility)
            if result is not None:
                return result

        # Strategy 1b: Role only (if no name specified)
        elif bundle.role:
            strategy_name = f"role(role='{bundle.role}')"
            strategies_attempted.append(strategy_name)
            candidate = page.get_by_role(bundle.role)
            result = await cls._evaluate_candidate(candidate, strategy_name, strategies_attempted, check_visibility)
            if result is not None:
                return result

        # Strategy 2: Associated Label
        if bundle.label:
            strategy_name = f"label(label='{bundle.label}')"
            strategies_attempted.append(strategy_name)
            candidate = page.get_by_label(bundle.label)
            result = await cls._evaluate_candidate(candidate, strategy_name, strategies_attempted, check_visibility)
            if result is not None:
                return result

        # Strategy 3: Stable Attributes
        if bundle.stable_attributes:
            for attr_name, attr_val in bundle.stable_attributes.items():
                strategy_name = f"attribute([{attr_name}='{attr_val}'])"
                strategies_attempted.append(strategy_name)
                candidate = page.locator(f"[{attr_name}='{attr_val}']")
                result = await cls._evaluate_candidate(candidate, strategy_name, strategies_attempted, check_visibility)
                if result is not None:
                    return result

        # Strategy 4: Exact Visible Text
        if bundle.text:
            strategy_name = f"text(text='{bundle.text}')"
            strategies_attempted.append(strategy_name)
            candidate = page.get_by_text(bundle.text, exact=True)
            result = await cls._evaluate_candidate(candidate, strategy_name, strategies_attempted, check_visibility)
            if result is not None:
                return result

        # Strategy 5: CSS Selector
        if bundle.css:
            strategy_name = f"css('{bundle.css}')"
            strategies_attempted.append(strategy_name)
            candidate = page.locator(bundle.css)
            result = await cls._evaluate_candidate(candidate, strategy_name, strategies_attempted, check_visibility)
            if result is not None:
                return result

        # Strategy 6: XPath Selector
        if bundle.xpath:
            strategy_name = f"xpath('{bundle.xpath}')"
            strategies_attempted.append(strategy_name)
            xpath_sel = bundle.xpath if bundle.xpath.startswith("xpath=") else f"xpath={bundle.xpath}"
            candidate = page.locator(xpath_sel)
            result = await cls._evaluate_candidate(candidate, strategy_name, strategies_attempted, check_visibility)
            if result is not None:
                return result

        # All strategies exhausted without finding any match
        return ResolutionResult(
            status=ResolutionStatus.TARGET_NOT_FOUND,
            strategies_attempted=strategies_attempted,
            match_count=0,
            failure_reason=f"Element not found. Exhausted {len(strategies_attempted)} locator strategies.",
        )

    @classmethod
    async def _evaluate_candidate(
        cls,
        candidate: Locator,
        strategy_name: str,
        strategies_attempted: List[str],
        check_visibility: bool,
    ) -> Optional[ResolutionResult]:
        """Check element match count and visibility for candidate locator."""
        try:
            count = await candidate.count()
        except Exception as e:
            # Error evaluating locator expression
            return None

        if count == 0:
            # Strategy yielded no DOM match; proceed to next fallback
            return None

        if count > 1:
            # Ambiguous match: Resolver NEVER arbitrarily picks an element
            return ResolutionResult(
                status=ResolutionStatus.AMBIGUOUS_TARGET,
                strategy_used=strategy_name,
                strategies_attempted=strategies_attempted,
                match_count=count,
                failure_reason=f"Ambiguous locator: {count} elements matched strategy '{strategy_name}'.",
            )

        # Exact single match (count == 1)
        if check_visibility:
            try:
                is_visible = await candidate.is_visible()
                if not is_visible:
                    # Single DOM element exists but is hidden; continue checking subsequent strategies
                    return None
            except Exception:
                return None

        return ResolutionResult(
            status=ResolutionStatus.FOUND,
            locator=candidate,
            strategy_used=strategy_name,
            strategies_attempted=strategies_attempted,
            match_count=1,
        )
