
## Project

**Let's Tennis** — tennis social/matchmaking app backend. FastAPI monolith. Default locale: zh-Hant (also zh-Hans, English).

## Commands

```bash
uv add <package>                                          # never pip/poetry
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000   # server
uv run pytest tests/ -v                                   # all tests (needs lets_tennis_test DB)
uv run pytest tests/test_auth.py::test_login_username -v  # single test
uv run alembic revision --autogenerate -m "description"   # migration
uv run alembic upgrade head
```

## Architecture

**Request flow:** `Router → Dependencies (auth/db/lang) → Service → SQLAlchemy Model → PostgreSQL`

### Core

- **App factory**: `app/main.py` — `create_app()`, routers under `/api/v1/`
- **DI**: `app/dependencies.py` — `DbSession`, `CurrentUser`, `Lang`, `AdminUser` (requires `admin`/`superadmin`)
- **Auth**: JWT (access + refresh). `services/auth.py`. Multi-provider `UserAuth` keyed on `(provider, provider_user_id)`
- **i18n**: `app/i18n.py` — `t(key, lang)`, from `Accept-Language` header
- **Roles**: `UserRole` — `user`, `admin`, `superadmin`. Suspension via `is_suspended` → 403

### Modules

`services/<name>.py` + `routers/<name>.py` unless noted.

| Module | Key files | Summary |
|--------|-----------|---------|
| Booking | `booking.py` | Lifecycle: `open → confirmed → completed/cancelled`. Creator auto-joins. |
| Courts | `court.py` | Admin-approved + user-submitted. Only approved usable. |
| Credit | `credit.py` (svc only) | Score [0,100]. First cancel = warning. |
| Review | `review.py` | Post-booking, double-blind reveal. 3 dimensions + comment. 24h window. `is_hidden` flag. |
| Report | `report.py` | Polymorphic target (`target_type` + `target_id`). Admin resolve at `/api/v1/admin/reports`. |
| Block | `block.py` | Symmetric + silent. `is_blocked(session, a, b)` checks both directions. Hard delete on unblock. |
| Follow | `follow.py` | Unidirectional, mutual detected at read time. Removed on block. |
| Notification | `notification.py` | In-app polling (no push). 18 types. `create_notification()` internal-only. |
| Ideal Player 理想球友 | `ideal_player.py` (svc only) | Auto-evaluated badge on User. Priority sort in listings. |
| Assistant 约球助理 | `llm.py` + `assistant.py` | NL → booking fields via LLM. Add providers: implement `LLMProvider` protocol. |
| Matching 智能匹配 | `matching.py` + `match_proposal.py` | `MatchPreference` → scored candidates → `MatchProposal` (pending/accepted/rejected/expired). Accept = auto-create booking. |
| Weather 天气 | `weather.py` | QWeather API, Redis-cached. Bad weather → `allows_free_cancel` (waives credit penalty). |
| Chat 聊天 | `chat.py` | WebSocket + REST. Auto-created rooms on booking confirm. `ConnectionManager` for WS. |

### Database

- SQLAlchemy async + `asyncpg`. Models inherit `app.database.Base`
- Alembic async migrations. DBs: `lets_tennis` / `lets_tennis_test`
- Config: `app/config.py` — `pydantic-settings` from `.env`

### Testing

- Real PostgreSQL (`lets_tennis_test`), not mocks
- `conftest.py`: `session` + `client` fixtures, tables created/dropped per test
- `asyncio_mode = "auto"`

## Conventions

- **Errors**: `ValueError` → 400, `LookupError` → 409, `PermissionError` → 403
- **NTRP**: strings (`"3.5"`, `"3.5+"`, `"4.0-"`). See `generate_ntrp_label()`, `_ntrp_to_float()`
- **i18n**: all user-facing errors via `t()`
- **Schemas**: `model_config = {"from_attributes": True}`
- **Blocks**: always symmetric — `is_blocked(session, a, b)` covers both directions
