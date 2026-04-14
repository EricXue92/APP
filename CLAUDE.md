# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Let's Tennis** — a tennis social/matchmaking app backend. FastAPI monolith with modular router structure, targeting Traditional Chinese (zh-Hant) as default locale with zh-Hans and English support.

## Commands

```bash
# Dependencies (always use uv, never pip/poetry)
uv add <package>
uv add --dev <package>

# Run server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run all tests (requires local PostgreSQL with lets_tennis_test database)
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_auth.py -v

# Run a single test function
uv run pytest tests/test_auth.py::test_login_username -v

# Alembic migrations
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

## Architecture

### Request flow
`Router → Dependencies (auth/db/lang) → Service → SQLAlchemy Model → PostgreSQL`

### Key patterns

- **App factory**: `app/main.py` — `create_app()` constructs the FastAPI app, registers routers under `/api/v1/` prefix
- **Dependency injection**: `app/dependencies.py` — use `DbSession`, `CurrentUser`, and `Lang` type aliases in router function signatures
- **Auth**: JWT Bearer tokens (access + refresh). `services/auth.py` handles token creation/validation, password hashing. Auth info is stored in `UserAuth` (multi-provider: username, phone, WeChat, Google) linked to `User` via foreign key
- **Multi-provider auth model**: One `User` can have multiple `UserAuth` rows (one per provider). Lookup is by `(provider, provider_user_id)` unique constraint
- **Credit score system**: `services/credit.py` — bounded [0, 100], first cancellation is warning-only (no deduction), tracked via `cancel_count` on User
- **Booking system**: `services/booking.py` + `routers/bookings.py` — post-a-match flow with lifecycle (open → confirmed → completed/cancelled). Creator auto-joins as accepted participant. Cancellation penalty calculated automatically from play datetime. Completion awards +5 credit to all accepted participants.
- **Courts**: `services/court.py` + `routers/courts.py` — hybrid model: admin-seeded courts (approved) + user-submitted courts (unapproved until reviewed). Only approved courts appear in listings and can be used for bookings.
- **i18n**: `app/i18n.py` — simple dict-based translations, `t(key, lang)` function. Language determined via `Accept-Language` header
- **Roles**: `UserRole` enum on User model — `user`, `admin`, `superadmin`

### Database

- **ORM**: SQLAlchemy async with `asyncpg` driver
- **Models inherit from**: `app.database.Base` (DeclarativeBase)
- **Migrations**: Alembic with async engine (configured in `alembic/env.py`)
- **Databases**: `lets_tennis` (dev), `lets_tennis_test` (tests)
- **Config**: `app/config.py` — `pydantic-settings` loading from `.env`

### Testing

- Tests use a separate PostgreSQL database (`lets_tennis_test`) — not mocks
- `tests/conftest.py` provides `session` and `client` fixtures that create/drop all tables per test function
- `client` fixture overrides `get_session` dependency to use the test session
- pytest-asyncio with `asyncio_mode = "auto"` (no need for `@pytest.mark.asyncio` decorator, but existing tests use it)

## Conventions

- NTRP levels are strings like `"3.5"`, `"3.5+"`, `"4.0-"` — the `generate_ntrp_label()` function in `services/auth.py` produces display labels. `_ntrp_to_float()` in `services/booking.py` converts these to floats for range comparison.
- All API error messages should use the `t()` i18n function for user-facing text
- Pydantic schemas use `model_config = {"from_attributes": True}` for ORM compatibility
- Booking validation: credit_score ≥ 60 to create, NTRP range check + gender requirement + capacity check to join
- Booking status state machine: `open → confirmed → completed/cancelled`. Only creator can confirm/complete. Cancel calculates penalty tier automatically (≥24h: -1, 12-24h: -2, <12h: -5, first cancel is always warning-only).
