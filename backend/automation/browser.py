"""Playwright browser automation controller with session persistence and abstract surface boundaries."""

from pathlib import Path
from typing import Optional
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from backend.automation.locators import LocatorResolver
from backend.config import settings
from backend.core.errors import BankingAgentError, LocatorResolutionError, ResultCode
from backend.core.models import LocatorBundle, Observation


class BrowserController:
    """Controls browser automation lifecycle, preserving persistent context and session state across actions."""

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        viewport_width: Optional[int] = None,
        viewport_height: Optional[int] = None,
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.viewport_width = viewport_width or settings.DEFAULT_VIEWPORT_WIDTH
        self.viewport_height = viewport_height or settings.DEFAULT_VIEWPORT_HEIGHT

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> "BrowserController":
        """Launch Playwright browser instance, initialize persistent context and base page."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
            )

        if self._context is None:
            self._context = await self._browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                user_agent="Northstar-Core-Automation-Agent/1.0",
            )

        if self._page is None:
            self._page = await self._context.new_page()

        return self

    @property
    def page(self) -> Page:
        """Return the active Playwright Page instance."""
        if self._page is None or self._page.is_closed():
            raise BankingAgentError(
                message="Browser page is not active or has been closed.",
                code=ResultCode.SYSTEM_ERROR,
            )
        return self._page

    @property
    def context(self) -> BrowserContext:
        """Return the active BrowserContext preserving cookies and session state."""
        if self._context is None:
            raise BankingAgentError(
                message="Browser context is not initialized.",
                code=ResultCode.SYSTEM_ERROR,
            )
        return self._context

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> Observation:
        """Navigate to specified URL and return sanitized observation."""
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=settings.BROWSER_TIMEOUT_MS)
            return await self.get_observation()
        except Exception as e:
            raise BankingAgentError(
                message=f"Failed navigating to URL '{url}': {e}",
                code=ResultCode.TARGET_NOT_FOUND,
                details={"target_url": url, "error": str(e)},
            ) from e

    async def click(self, locator: LocatorBundle, timeout_ms: Optional[int] = None) -> None:
        """Resolve locator deterministically and perform click action."""
        resolution = await LocatorResolver.resolve(self.page, locator, check_visibility=True)
        target = resolution.get_locator_or_raise()

        timeout = timeout_ms or settings.BROWSER_TIMEOUT_MS
        try:
            await target.click(timeout=timeout)
        except Exception as e:
            raise BankingAgentError(
                message=f"Failed clicking element resolved via strategy '{resolution.strategy_used}': {e}",
                code=ResultCode.ELEMENT_NOT_INTERACTABLE,
                details={"strategy_used": resolution.strategy_used, "error": str(e)},
            ) from e

    async def fill(self, locator: LocatorBundle, value: str, timeout_ms: Optional[int] = None) -> None:
        """Resolve locator deterministically and fill input text."""
        resolution = await LocatorResolver.resolve(self.page, locator, check_visibility=True)
        target = resolution.get_locator_or_raise()

        timeout = timeout_ms or settings.BROWSER_TIMEOUT_MS
        try:
            await target.fill(value, timeout=timeout)
        except Exception as e:
            raise BankingAgentError(
                message=f"Failed filling input resolved via strategy '{resolution.strategy_used}': {e}",
                code=ResultCode.ELEMENT_NOT_INTERACTABLE,
                details={"strategy_used": resolution.strategy_used, "error": str(e)},
            ) from e

    async def read_text(self, locator: LocatorBundle, timeout_ms: Optional[int] = None) -> str:
        """Resolve locator deterministically and read visible inner text."""
        resolution = await LocatorResolver.resolve(self.page, locator, check_visibility=True)
        target = resolution.get_locator_or_raise()

        timeout = timeout_ms or settings.BROWSER_TIMEOUT_MS
        try:
            text = await target.inner_text(timeout=timeout)
            return text.strip()
        except Exception as e:
            raise BankingAgentError(
                message=f"Failed reading text from element resolved via '{resolution.strategy_used}': {e}",
                code=ResultCode.TARGET_NOT_FOUND,
                details={"strategy_used": resolution.strategy_used, "error": str(e)},
            ) from e

    async def capture_screenshot(self, path: Optional[str] = None) -> bytes:
        """Capture screenshot of the active viewport without exposing sensitive artifacts."""
        if path:
            target_path = Path(path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            return await self.page.screenshot(path=str(target_path), full_page=False)
        return await self.page.screenshot(full_page=False)

    async def get_observation(self, screenshot_path: Optional[str] = None) -> Observation:
        """Extract a structured observation of the active browser state."""
        url = self.page.url
        title = await self.page.title()

        # Extract a brief text summary of the page without logging massive payloads
        try:
            body_text = await self.page.inner_text("body")
            # Truncate summary to avoid bloating logs
            summary = " ".join(body_text.split())[:300]
        except Exception:
            summary = ""

        return Observation(
            url=url,
            title=title,
            visible_text_summary=summary,
            screenshot_path=screenshot_path,
        )

    async def close(self) -> None:
        """Cleanly tear down page, context, browser, and Playwright process."""
        if self._page and not self._page.is_closed():
            await self._page.close()
            self._page = None

        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self) -> "BrowserController":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
