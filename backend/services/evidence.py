"""Evidence recording and structured JSONL auditing with sensitive data redaction."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set
from playwright.async_api import Page


REDACTION_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]{10,}"), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?)[a-zA-Z0-9_\-\.]{10,}"), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(password\s*[:=]\s*['\"]?)[^'\",\s]+"), r"\1[REDACTED_PASSWORD]"),
    (re.compile(r"(?i)(secret\s*[:=]\s*['\"]?)[^'\",\s]+"), r"\1[REDACTED_SECRET]"),
    (re.compile(r"(?i)(cookie\s*[:=]\s*)[^;,\n]+"), r"\1[REDACTED_COOKIE]"),
]

SENSITIVE_KEY_NAMES = {
    "password",
    "token",
    "secret",
    "apikey",
    "api_key",
    "auth",
    "authorization",
    "cookie",
    "cookies",
    "session_id",
    "access_token",
}


class RedactionEngine:
    """Sanitizes runtime payloads and parameters before persisting to disk or evidence logs."""

    @classmethod
    def sanitize(cls, data: Any, sensitive_param_names: Optional[Set[str]] = None) -> Any:
        sensitive_params = sensitive_param_names or set()

        if isinstance(data, dict):
            sanitized_dict = {}
            for k, v in data.items():
                key_lower = str(k).lower()
                if key_lower in SENSITIVE_KEY_NAMES or k in sensitive_params:
                    sanitized_dict[k] = cls._mask_value(v)
                else:
                    sanitized_dict[k] = cls.sanitize(v, sensitive_params)
            return sanitized_dict

        if isinstance(data, list):
            return [cls.sanitize(item, sensitive_params) for item in data]

        if isinstance(data, str):
            masked = data
            for pattern, replacement in REDACTION_PATTERNS:
                masked = pattern.sub(replacement, masked)
            return masked

        return data

    @classmethod
    def _mask_value(cls, val: Any) -> str:
        s = str(val)
        if not s:
            return "[REDACTED]"
        if len(s) > 6 and s.startswith("M-"):
            return f"{s[:4]}***"
        return "[REDACTED]"


class EvidenceRecorder:
    """Records structured JSONL events and captures visual state checkpoints."""

    def __init__(
        self,
        run_id: str,
        mode: str = "replay",
        output_dir: Optional[Path] = None,
        sensitive_keys: Optional[Set[str]] = None,
    ):
        self.run_id = run_id
        self.mode = mode
        self.output_dir = output_dir or Path("evidence") / mode
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.output_dir / f"{run_id}.jsonl"
        self.sensitive_keys = sensitive_keys or set()
        self.events: List[Dict[str, Any]] = []

    def record_event(
        self,
        event: str,
        capability_id: Optional[str] = None,
        step_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Record a sanitized structured audit event into in-memory store and JSONL file."""
        raw_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "mode": self.mode,
            "event": event,
            "capability_id": capability_id,
            "step_id": step_id,
            "duration_ms": duration_ms,
            "details": details or {},
        }

        sanitized = RedactionEngine.sanitize(raw_payload, self.sensitive_keys)
        self.events.append(sanitized)

        # Write to JSONL
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(sanitized) + "\n")
        except Exception:
            pass

        return sanitized

    async def capture_screenshot_evidence(
        self,
        page: Page,
        event_name: str,
        capability_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> Optional[str]:
        """Capture screenshot on failure or human checkpoint, recording metadata in evidence."""
        screenshot_filename = f"{self.run_id}_{event_name.lower()}.png"
        screenshot_path = self.output_dir / screenshot_filename

        try:
            await page.screenshot(path=str(screenshot_path), full_page=False)
            path_str = str(screenshot_path)
            self.record_event(
                event="SCREENSHOT_CAPTURED",
                capability_id=capability_id,
                step_id=step_id,
                details={"event_name": event_name, "screenshot_path": path_str},
            )
            return path_str
        except Exception as e:
            self.record_event(
                event="SCREENSHOT_FAILED",
                capability_id=capability_id,
                step_id=step_id,
                details={"error": str(e)},
            )
            return None
