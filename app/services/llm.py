from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import anthropic

from app.config import settings


class RateLimitError(Exception):
    """Raised when a user exceeds the assistant rate limit."""


@runtime_checkable
class LLMProvider(Protocol):
    async def parse(self, system: str, user_message: str) -> dict[str, Any]: ...


class ClaudeProvider:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def parse(self, system: str, user_message: str) -> dict[str, Any]:
        tool = {
            "name": "extract_booking",
            "description": "Extract structured booking fields from user text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "match_type": {"type": ["string", "null"], "enum": ["singles", "doubles", None]},
                    "play_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "start_time": {"type": ["string", "null"], "description": "HH:MM"},
                    "end_time": {"type": ["string", "null"], "description": "HH:MM"},
                    "court_keyword": {"type": ["string", "null"]},
                    "min_ntrp": {"type": ["string", "null"]},
                    "max_ntrp": {"type": ["string", "null"]},
                    "gender_requirement": {"type": ["string", "null"], "enum": ["male_only", "female_only", "any", None]},
                    "cost_description": {"type": ["string", "null"]},
                },
                "required": [
                    "match_type", "play_date", "start_time", "end_time",
                    "court_keyword", "min_ntrp", "max_ntrp",
                    "gender_requirement", "cost_description",
                ],
            },
        }

        response = await self._client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "extract_booking"},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_booking":
                return block.input

        return {
            "match_type": None, "play_date": None, "start_time": None,
            "end_time": None, "court_keyword": None, "min_ntrp": None,
            "max_ntrp": None, "gender_requirement": None, "cost_description": None,
        }


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    provider_name = name or settings.llm_provider
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
    return cls()
