"""Error taxonomy, result codes, and base exceptions for Banking Agent."""

from enum import Enum
from typing import Any, Dict, Optional


class ExecutionStatus(str, Enum):
    """High-level execution outcome categories."""

    SUCCESS = "SUCCESS"
    BUSINESS_OUTCOME = "BUSINESS_OUTCOME"
    RECOVERABLE_ERROR = "RECOVERABLE_ERROR"
    HARD_FAILURE = "HARD_FAILURE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class ResultCode(str, Enum):
    """Normalized result and error codes across discovery, validation, and replay."""

    # Success
    SUCCESS = "SUCCESS"

    # Business Outcomes (Legitimate non-error domain outcomes)
    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"

    # Recoverable Runtime Conditions
    PAGE_LOADING = "PAGE_LOADING"
    KNOWN_DIALOG = "KNOWN_DIALOG"
    RATE_LIMITED = "RATE_LIMITED"
    TRANSIENT_DELAY = "TRANSIENT_DELAY"

    # Human Intervention Conditions
    MANUAL_VERIFICATION = "MANUAL_VERIFICATION"
    UNEXPECTED_DIALOG = "UNEXPECTED_DIALOG"
    CAPTCHA_DETECTED = "CAPTCHA_DETECTED"
    MFA_REQUIRED = "MFA_REQUIRED"

    # Automation & Locator Failures
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    ELEMENT_NOT_INTERACTABLE = "ELEMENT_NOT_INTERACTABLE"
    CHECKPOINT_FAILED = "CHECKPOINT_FAILED"

    # Policy & System Failures
    POLICY_VIOLATION = "POLICY_VIOLATION"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class BankingAgentError(Exception):
    """Base exception for all Banking Agent runtime and artifact errors."""

    def __init__(
        self,
        message: str,
        code: ResultCode = ResultCode.SYSTEM_ERROR,
        status: ExecutionStatus = ExecutionStatus.HARD_FAILURE,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details or {}


class LocatorResolutionError(BankingAgentError):
    """Raised when locator bundle resolution fails deterministically."""

    def __init__(
        self,
        message: str,
        code: ResultCode = ResultCode.TARGET_NOT_FOUND,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status=ExecutionStatus.HARD_FAILURE,
            details=details,
        )


class CheckpointEvaluationError(BankingAgentError):
    """Raised when an expected checkpoint condition is not met."""

    def __init__(
        self,
        message: str,
        code: ResultCode = ResultCode.CHECKPOINT_FAILED,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status=ExecutionStatus.HARD_FAILURE,
            details=details,
        )


class ArtifactValidationError(BankingAgentError):
    """Raised when a CapabilityArtifact fails schema validation or integrity checks."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=ResultCode.INVALID_INPUT,
            status=ExecutionStatus.HARD_FAILURE,
            details=details,
        )
