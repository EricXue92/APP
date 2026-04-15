from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.redis import redis_client
from app.services.court import search_courts_by_keyword
from app.services.llm import RateLimitError, get_provider

_EXPECTED_FIELDS = [
    "match_type", "play_date", "start_time", "end_time",
    "court_keyword", "min_ntrp", "max_ntrp",
    "gender_requirement", "cost_description",
]


async def _check_rate_limit(user_id: str) -> None:
    key = f"assistant:{user_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 3600)
    if count > settings.assistant_rate_limit:
        raise RateLimitError("rate limit exceeded")


def _build_system_prompt(user: User, lang: str) -> str:
    today = date.today().isoformat()

    if lang == "zh-Hant":
        return (
            "你是一個網球約球助手。從用戶的自然語言輸入中提取約球資訊。\n"
            f"今天日期：{today}\n"
            f"用戶所在城市：{user.city}\n"
            "請使用 extract_booking 工具返回結構化數據。"
            "未提及的欄位設為 null。"
        )
    if lang == "zh-Hans":
        return (
            "你是一个网球约球助手。从用户的自然语言输入中提取约球信息。\n"
            f"今天日期：{today}\n"
            f"用户所在城市：{user.city}\n"
            "请使用 extract_booking 工具返回结构化数据。"
            "未提及的字段设为 null。"
        )
    return (
        "You are a tennis booking assistant. Extract booking details from the user's natural language input.\n"
        f"Today's date: {today}\n"
        f"User's city: {user.city}\n"
        "Use the extract_booking tool to return structured data. "
        "Set unmentioned fields to null."
    )


def _normalize_response(raw: dict[str, Any]) -> dict[str, Any]:
    return {field: raw.get(field) for field in _EXPECTED_FIELDS}


async def parse_booking(
    session: AsyncSession,
    user: User,
    text: str,
    lang: str,
) -> dict[str, Any]:
    await _check_rate_limit(str(user.id))

    system = _build_system_prompt(user, lang)
    provider = get_provider()

    raw = await provider.parse(system, text)
    result = _normalize_response(raw)

    # Court fuzzy match
    court_keyword = result.get("court_keyword")
    result["court_id"] = None
    result["court_name"] = None
    if court_keyword:
        courts = await search_courts_by_keyword(session, court_keyword)
        if courts:
            result["court_id"] = str(courts[0].id)
            result["court_name"] = courts[0].name

    return result
