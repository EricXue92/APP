# Booking Assistant Agent — Design Spec

## Overview

AI-powered booking form filler. User inputs natural language (e.g., "这周末下午在维园想打单打，3.5 左右，AA"), backend calls Claude to parse into structured booking fields, fuzzy-matches court keywords against Court table, and returns pre-filled form data. Final submission still goes through `create_booking`.

## Decisions

- **LLM provider:** Claude (Sonnet) first, adapter pattern for adding Gemini/OpenAI/others later
- **Rate limit:** 10 requests per user per hour via Redis
- **User context:** Supplement LLM parsing with user profile data (city) when text is missing info
- **Processing:** Backend-only — API key never exposed to client

---

## 1. LLM Adapter Layer

**File:** `app/services/llm.py`

### Protocol

```python
class LLMProvider(Protocol):
    async def parse(self, system: str, user_message: str) -> dict: ...
```

### Claude Provider

`ClaudeProvider` class — uses `anthropic` async SDK, calls `messages.create()` with Sonnet model, returns parsed JSON via tool use (structured output).

### Provider Registry

```python
_PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
}
```

`get_provider()` factory reads `settings.llm_provider`, instantiates the corresponding class. Adding a new provider = create a class, add one line to registry.

### Config Additions (`app/config.py`)

```python
llm_provider: str = "claude"
anthropic_api_key: str = ""
anthropic_model: str = "claude-sonnet-4-20250514"
assistant_rate_limit: int = 10  # per user per hour
```

---

## 2. Assistant Service

**File:** `app/services/assistant.py`

### Core Function

`parse_booking(session, user, text, lang) -> dict`

### Flow

1. **Rate limit check** — Redis key `assistant:{user_id}`, INCR + EXPIRE 3600s. If count > 10, raise `ValueError`.
2. **Build system prompt** — Instructs LLM to extract booking fields from natural language. Includes current date (for resolving "this weekend", "tomorrow"). Written in the user's language.
3. **Build user context** — Fetch user's city from profile. Append as context so LLM can fill gaps (e.g., default city when court not mentioned).
4. **Call LLM** — `get_provider().parse(system, user_message)` → returns structured dict.
5. **Court fuzzy match** — If `court_keyword` is not null, call existing `search_courts_by_keyword()`. Return top match's `court_id` and `court_name`, or null if no match.
6. **Return** — Combined dict: parsed fields + `court_id`/`court_name` (if matched).

### LLM Output Schema

The LLM is instructed to return (via tool use / structured output):

```json
{
  "match_type": "singles | doubles | null",
  "play_date": "YYYY-MM-DD | null",
  "start_time": "HH:MM | null",
  "end_time": "HH:MM | null",
  "court_keyword": "raw keyword | null",
  "min_ntrp": "3.0 | null",
  "max_ntrp": "4.0 | null",
  "gender_requirement": "male_only | female_only | any | null",
  "cost_description": "AA | 免费 | null"
}
```

Unrecognized fields return `null`; iOS client leaves those fields blank for manual input.

### Error Handling

- Rate limit exceeded → `RateLimitError` (defined in `llm.py`, router maps to 429)
- LLM API failure → `RuntimeError` (router maps to 502)
- Malformed LLM response → return all fields as null (graceful degradation)

---

## 3. API Endpoint & Schemas

### Router

**File:** `app/routers/assistant.py`

**Endpoint:** `POST /api/v1/assistant/parse-booking`
- Auth: `CurrentUser`
- Language: `Lang` dependency

Registered in `app/main.py` under `/api/v1/assistant`.

### Schemas (`app/schemas/assistant.py`)

**Request:**

```python
class ParseBookingRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=500)
```

**Response:**

```python
class ParseBookingResponse(BaseModel):
    match_type: str | None = None        # "singles" | "doubles"
    play_date: str | None = None         # "YYYY-MM-DD"
    start_time: str | None = None        # "HH:MM"
    end_time: str | None = None          # "HH:MM"
    court_keyword: str | None = None     # raw keyword from LLM
    court_id: str | None = None          # UUID string if matched
    court_name: str | None = None        # matched court name
    min_ntrp: str | None = None          # e.g. "3.0"
    max_ntrp: str | None = None          # e.g. "4.0"
    gender_requirement: str | None = None # "male_only" | "female_only" | "any"
    cost_description: str | None = None  # "AA" | "免费" etc.
```

### Error Mapping

| Exception | HTTP Status | Meaning |
|-----------|-------------|---------|
| `RateLimitError` | 429 | Too many requests |
| `ValueError` | 400 | Invalid input |
| `RuntimeError` | 502 | LLM service failure |

---

## 4. Testing Strategy

**No real LLM calls in tests.** A `FakeProvider` implements `LLMProvider` protocol with canned responses. Injected via provider registry in test fixtures.

**File:** `tests/test_assistant.py`

### Test Cases

1. **Happy path** — Full text → all fields parsed, court matched
2. **Partial input** — Only `match_type` filled, rest null
3. **Court fuzzy match hit** — `court_keyword` matches a seeded court
4. **Court fuzzy match miss** — `court_keyword` doesn't match → `court_id` null
5. **User context fill** — User's city from profile included in prompt context
6. **Rate limit exceeded** — 11th request in an hour → 429
7. **LLM failure** — Provider raises exception → 502
8. **Malformed LLM response** — Provider returns garbage → all fields null
9. **Auth required** — No token → 401

---

## 5. Files Changed

| File | Change |
|------|--------|
| `app/config.py` | Add `llm_provider`, `anthropic_api_key`, `anthropic_model`, `assistant_rate_limit` |
| `app/services/llm.py` | **New** — LLM adapter protocol, provider registry, `ClaudeProvider`, `RateLimitError` |
| `app/services/assistant.py` | **New** — `parse_booking()` core logic |
| `app/schemas/assistant.py` | **New** — request/response schemas |
| `app/routers/assistant.py` | **New** — `POST /api/v1/assistant/parse-booking` |
| `app/main.py` | Register assistant router |
| `app/i18n.py` | Add assistant error messages |
| `tests/test_assistant.py` | **New** — 9 test cases with FakeProvider |
| `pyproject.toml` | Add `anthropic` dependency |

### Not Modified

- Existing booking flow — assistant only parses, submission still goes through `create_booking`
- Court service — `search_courts_by_keyword()` already exists
- No new database models or migrations needed
