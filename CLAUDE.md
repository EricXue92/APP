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
- **Review system**: `services/review.py` + `routers/reviews.py` — post-booking peer review with double-blind reveal. Three rating dimensions (skill, punctuality, sportsmanship) + optional comment. Reviews only visible to both parties after both submit. 24h window from booking completion. `is_hidden` used by Report/Block module to hide content.
- **Report system**: `services/report.py` + `routers/reports.py` — users report abusive content (reviews or users). Polymorphic target: `target_type` (user/review) + `target_id` (always populated). Reasons: no_show, harassment, false_info, inappropriate, other. Admins resolve reports via `/api/v1/admin/reports` with escalating actions: dismissed, warned, content_hidden (sets Review.is_hidden=True), suspended (sets User.is_suspended=True). Unique constraint: one report per (reporter, target_type, target_id).
- **Block system**: `services/block.py` + `routers/blocks.py` — symmetric and silent blocking. When A blocks B: mutual reviews hidden (is_hidden=True), B can't join A's bookings (and vice versa), blocked users' bookings hidden from each other's listings, new reviews between blocked pairs rejected. Unblock is hard delete; hidden reviews are NOT auto-restored. `is_blocked()` helper checks both directions.
- **Follow system**: `services/follow.py` + `routers/follows.py` — unidirectional follow with mutual (friend) detection. `is_mutual` computed at read time by checking reverse follow exists. Block integration: blocked users cannot follow each other, existing follows removed on block creation. Unfollow is hard delete; follows NOT restored on unblock.
- **Suspension**: `is_suspended` field on User model, checked in `get_current_user` dependency — all protected endpoints reject suspended users with 403.
- **Admin dependency**: `AdminUser` type alias in `dependencies.py` — chains on `CurrentUser`, requires `UserRole.admin` or `UserRole.superadmin`.
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
- Review validation: booking must be completed, both parties must be accepted participants, cannot self-review, 24h window from completion, no duplicates. Blind reveal: review visible to reviewee only after reviewee also submits their review for the same booking.
- Block validation: cannot block yourself (400), duplicate block (409). Block enforcement is symmetric — `is_blocked(session, a, b)` checks both directions. Unblock only by blocker, hard delete. Hidden reviews not auto-restored on unblock.
- Report validation: cannot report yourself (400), duplicate report per (reporter, target_type, target_id) (409), cannot report already-hidden review (400). `content_hidden` resolution only valid for review targets (400 if user target). Admin resolve requires pending status.
- Service error convention: `ValueError` → 400, `LookupError` → 409, `PermissionError` → 403 in router exception handlers.
