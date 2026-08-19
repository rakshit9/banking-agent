"""Deterministic checkpoint evaluation engine for state and assertion verification."""

from typing import Any, Dict, Optional
from playwright.async_api import Page

from backend.automation.locators import LocatorResolver
from backend.core.models import Checkpoint, CheckpointResult, CheckpointType


class CheckpointEvaluator:
    """Evaluates deterministic pre/post-action checkpoints against active browser page state."""

    @classmethod
    async def evaluate(
        cls,
        checkpoint: Checkpoint,
        page: Page,
        extracted_data: Optional[Dict[str, Any]] = None,
    ) -> CheckpointResult:
        """Evaluate a checkpoint against current page DOM, URL, and extracted variables."""
        data_store = extracted_data or {}

        if checkpoint.type == CheckpointType.URL_CONTAINS:
            return await cls._evaluate_url_contains(checkpoint, page)

        if checkpoint.type == CheckpointType.TEXT_VISIBLE:
            return await cls._evaluate_text_visible(checkpoint, page)

        if checkpoint.type == CheckpointType.ELEMENT_VISIBLE:
            return await cls._evaluate_element_visible(checkpoint, page)

        if checkpoint.type == CheckpointType.OUTPUT_PRESENT:
            return cls._evaluate_output_present(checkpoint, data_store)

        if checkpoint.type == CheckpointType.ONE_OF:
            return await cls._evaluate_one_of(checkpoint, page, data_store)

        return CheckpointResult(
            passed=False,
            checkpoint_type=checkpoint.type,
            expected=checkpoint.expected,
            diagnostic=f"Unsupported checkpoint type: {checkpoint.type}",
        )

    @classmethod
    async def _evaluate_url_contains(cls, checkpoint: Checkpoint, page: Page) -> CheckpointResult:
        current_url = page.url
        expected = checkpoint.expected or ""
        passed = expected in current_url
        return CheckpointResult(
            passed=passed,
            checkpoint_type=CheckpointType.URL_CONTAINS,
            expected=expected,
            observed=current_url,
            matched_outcome=checkpoint.outcome_code if passed else None,
            diagnostic=f"URL '{current_url}' {'contains' if passed else 'does NOT contain'} '{expected}'",
        )

    @classmethod
    async def _evaluate_text_visible(cls, checkpoint: Checkpoint, page: Page) -> CheckpointResult:
        expected = checkpoint.expected or ""
        try:
            # Check for visible text locator
            locator = page.get_by_text(expected)
            count = await locator.count()
            is_visible = False
            if count > 0:
                is_visible = await locator.first.is_visible()
            
            # Secondary check: verify presence in page text if locator failed due to nested tags
            if not is_visible:
                body_text = await page.inner_text("body")
                is_visible = expected in body_text

            return CheckpointResult(
                passed=is_visible,
                checkpoint_type=CheckpointType.TEXT_VISIBLE,
                expected=expected,
                observed=f"Visible: {is_visible}",
                matched_outcome=checkpoint.outcome_code if is_visible else None,
                diagnostic=f"Text '{expected}' is {'visible' if is_visible else 'not visible'} on page.",
            )
        except Exception as e:
            return CheckpointResult(
                passed=False,
                checkpoint_type=CheckpointType.TEXT_VISIBLE,
                expected=expected,
                diagnostic=f"Error checking visible text: {e}",
            )

    @classmethod
    async def _evaluate_element_visible(cls, checkpoint: Checkpoint, page: Page) -> CheckpointResult:
        if not checkpoint.locator:
            return CheckpointResult(
                passed=False,
                checkpoint_type=CheckpointType.ELEMENT_VISIBLE,
                diagnostic="ELEMENT_VISIBLE checkpoint missing target locator bundle.",
            )

        resolution = await LocatorResolver.resolve(page, checkpoint.locator, check_visibility=True)
        passed = resolution.is_found
        return CheckpointResult(
            passed=passed,
            checkpoint_type=CheckpointType.ELEMENT_VISIBLE,
            expected=str(checkpoint.locator.model_dump(exclude_none=True)),
            observed=f"Resolved via {resolution.strategy_used}" if passed else resolution.failure_reason,
            matched_outcome=checkpoint.outcome_code if passed else None,
            diagnostic=f"Element {'found and visible' if passed else 'not visible'}. Diagnostic: {resolution.to_diagnostic().model_dump()}",
        )

    @classmethod
    def _evaluate_output_present(cls, checkpoint: Checkpoint, extracted_data: Dict[str, Any]) -> CheckpointResult:
        key = checkpoint.expected or ""
        present = key in extracted_data and extracted_data[key] is not None
        val_str = str(extracted_data.get(key)) if present else None
        return CheckpointResult(
            passed=present,
            checkpoint_type=CheckpointType.OUTPUT_PRESENT,
            expected=f"Key '{key}' in extracted data",
            observed=f"{key}={val_str}" if present else f"Keys present: {list(extracted_data.keys())}",
            matched_outcome=checkpoint.outcome_code if present else None,
            diagnostic=f"Output variable '{key}' is {'present with value ' + str(val_str) if present else 'missing'}.",
        )

    @classmethod
    async def _evaluate_one_of(
        cls,
        checkpoint: Checkpoint,
        page: Page,
        extracted_data: Dict[str, Any],
    ) -> CheckpointResult:
        branches = checkpoint.branches or []
        attempted_summaries = []

        for index, branch in enumerate(branches):
            branch_result = await cls.evaluate(branch, page, extracted_data)
            if branch_result.passed:
                matched_code = branch.outcome_code or checkpoint.outcome_code or "BRANCH_MATCHED"
                return CheckpointResult(
                    passed=True,
                    checkpoint_type=CheckpointType.ONE_OF,
                    expected=f"One of {len(branches)} branch conditions",
                    observed=f"Matched branch #{index + 1} ({matched_code})",
                    matched_outcome=matched_code,
                    diagnostic=f"Successfully matched branch condition #{index + 1}: {branch_result.diagnostic}",
                )
            attempted_summaries.append(f"Branch #{index + 1} ({branch.type.value}): {branch_result.diagnostic}")

        return CheckpointResult(
            passed=False,
            checkpoint_type=CheckpointType.ONE_OF,
            expected=f"One of {len(branches)} branch conditions",
            observed="None matched",
            diagnostic=f"None of the {len(branches)} ONE_OF branches passed. Evaluations: {attempted_summaries}",
        )
