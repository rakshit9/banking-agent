"""Explorer Agent responsible for deciding safe, goal-directed UI actions."""

from typing import Any, Dict, List, Optional
from backend.core.errors import BankingAgentError, ResultCode
from backend.core.models import ActionType
from backend.services.openai_service import OpenAIService, ProposedAction


ALLOWED_DISCOVERY_ACTIONS = {
    ActionType.NAVIGATE,
    ActionType.CLICK,
    ActionType.FILL,
    ActionType.READ,
    ActionType.EXTRACT,
    ActionType.SCROLL,
}


class ExplorerAgent:
    """Explores the target web surface by analyzing visual/DOM observations and proposing structured actions."""

    def __init__(self, openai_service: Optional[OpenAIService] = None):
        self.openai_service = openai_service or OpenAIService()

    async def decide_next_action(
        self,
        goal: str,
        observation: Dict[str, Any],
        history: List[Dict[str, Any]],
        screenshot_path: Optional[str] = None,
    ) -> ProposedAction:
        """Analyze current observation and propose the next deterministic action towards achieving the goal."""
        proposed = await self.openai_service.propose_next_action(
            goal=goal,
            observation=observation,
            history=history,
            screenshot_path=screenshot_path,
        )

        # Validate action type conforms to permitted discovery primitives
        if proposed.action not in ALLOWED_DISCOVERY_ACTIONS:
            raise BankingAgentError(
                message=f"Explorer proposed unsupported action type '{proposed.action}'.",
                code=ResultCode.UNSUPPORTED_ACTION,
                details={"proposed_action": proposed.action.value},
            )

        return proposed
