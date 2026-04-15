# Test Coverage Audit — Design Spec

## Goal

Comprehensive test coverage audit of all 13 modules in the Let's Tennis backend. Identify untested functions, missing edge cases, and error paths. Write tests for all gaps. Fix any bugs discovered during audit (documented but fixed separately).

## Scope

All service functions, router endpoints, and critical helper functions across every module. Tests use real PostgreSQL (`lets_tennis_test`), not mocks.

## Known Bug Found During Audit

- **Missing i18n key**: `event.not_participant` used in `app/services/admin.py:363` but not defined in `app/i18n.py`. Will cause key-as-message fallback at runtime.

---

## Module-by-Module Gap Analysis

### 1. Auth (`services/auth.py`, `routers/auth.py`) — 10 tests → needs ~12 more

**Untested service functions:**
- `decode_token()`: expired tokens, tampered tokens, malformed JWT, empty string
- `generate_ntrp_label()`: all level values, "+/-" modifiers, invalid input

**Untested router paths:**
- Login with `is_suspended=True` user (auth.py:63-67) — **never tested**
- Login with `is_active=False` user (auth.py:63-67) — **never tested**
- Phone login MVP code "000000" (auth.py:77)
- Refresh token with invalid type, expired user, malformed token
- Registration with invalid schema fields (password too short, invalid username)

### 2. Users (`services/user.py`, `routers/users.py`) — 4 tests → needs ~8 more

**Untested service functions:**
- `get_user_by_id()` — never tested directly (valid ID, non-existent ID)
- `get_user_auth()` — only USERNAME provider tested; PHONE/WECHAT/GOOGLE missing
- `create_user_with_auth()` — no test without password (OAuth flow), duplicate provider_user_id

**Untested router paths:**
- `PATCH /me` with individual fields (avatar_url, years_playing)
- `PATCH /me` with empty body

### 3. Credit (`services/credit.py`) — 7 tests → needs ~8 more

**Untested scenarios:**
- `CANCEL_12_24H` reason (delta=-2) — **never tested**
- `CANCEL_2H` reason (delta=-5) — **never tested**
- Credit score floor at 0 (score can't go negative) — **never tested**
- `ADMIN_ADJUST` reason — in enum but not in `_DELTAS` dict
- Multiple consecutive cancellations (3+)
- `get_credit_history()`: custom limit, empty history, limit=0

### 4. Booking (`services/booking.py`) — 22 tests → needs ~15 more

**Untested scenarios:**
- `cancel_booking()` time-based tiers: 24h, 12-24h, <12h windows — **never tested**
- `cancel_booking()` weather-free path — **never tested**
- `list_bookings()` block filtering (lines 130-141) — logic exists but untested
- `list_bookings()` combined filters (city + match_type + gender)
- `list_my_bookings()` status filter, ordering verification
- `confirm_booking()` chat room creation verification
- `complete_booking()` only ACCEPTED participants get credit
- `update_participant_status()` reject notification, chat room sync
- `_ntrp_to_float()` edge cases: "3.5+", "3.5-", invalid formats

### 5. Courts (`services/court.py`) — 9 tests → needs ~6 more

**Untested functions:**
- `search_courts_by_keyword()` — **completely untested** (0 tests)
  - Case-insensitive search, partial match, empty keyword, special characters
- `list_courts()` combined filters (city + court_type)
- `list_courts()` with `approved_only=False`

### 6. Review (`services/review.py`) — 15 tests → needs ~10 more

**Untested scenarios:**
- `submit_review()` with blocked users (line 92) — **never tested**
- `get_revealed_reviews_for_user()` with `is_hidden=True` reviews excluded
- `get_review_averages()` hidden reviews excluded, rounding precision
- `get_pending_reviews()` with 4-person doubles match (multiple co-participants)
- `get_pending_reviews()` exact 24h boundary
- `get_booking_reviews_for_user()` non-participant user

### 7. Report (`services/report.py`) — 13 tests → needs ~8 more

**Untested scenarios:**
- `resolve_report()` with WARNED resolution — **never tested**
- `list_reports()` status filtering (pending/resolved)
- `list_my_reports()` empty list, ordering
- Non-existent target_id for review reports
- Various `ReportReason` values (no_show, false_info)

### 8. Block (`services/block.py`) — 13 tests → needs ~6 more

**Untested scenarios:**
- `is_blocked()` bidirectional check — never directly tested with all 4 combinations (A→B, B→A, both, neither)
- `create_block()` proposal expiry (`expire_proposals_on_block`) — **never tested**
- `create_block()` chat room readonly: only PRIVATE rooms affected, GROUP rooms unaffected
- `list_blocks()` empty list, ordering
- Mutual blocks (A blocks B, B blocks A)

### 9. Follow (`services/follow.py`) — 14 tests → needs ~6 more

**Untested functions:**
- `is_mutual()` — no direct unit test (only indirect)
- `remove_follows_between()` — no direct unit test (only via block integration)

**Untested scenarios:**
- `list_followers()` / `list_following()` empty list, ordering
- Follow → unfollow → re-follow cycle
- Mutual notification: both FOLLOWED and MUTUAL_FOLLOW notifications created

### 10. Notification (`services/notification.py`) — 20 tests → needs ~5 more

**Untested scenarios:**
- `create_notification()` — never directly unit-tested (only via integration)
- `get_unread_count()` with mixed read/unread state
- `mark_all_as_read()` when user has no notifications
- `list_notifications()` ordering verification (DESC by created_at)

### 11. Ideal Player (`services/ideal_player.py`) — 10 tests → needs ~5 more

**Untested scenarios:**
- Exact threshold boundaries: credit=90, avg_rating=4.0
- `_avg_review_rating()` with hidden reviews only (should return None)
- `_avg_review_rating()` verify formula: `(skill + punctuality + sportsmanship) / 3.0`
- Non-existent user_id (returns False silently)

### 12. Matching (`services/matching.py`, `services/match_proposal.py`) — 29 tests → needs ~12 more

**Untested functions:**
- `_time_overlap_minutes()` — **zero tests** (critical scoring helper)
- `_compute_time_overlap_ratio()` — **zero tests**
- `_haversine_km()` — **zero tests**
- `get_proposal_by_id()` — lazy expiry logic untested
- `expire_proposals_on_block()` — no direct tests

**Untested scenarios:**
- `compute_match_score()` NTRP boundary at exactly 1.5 gap
- `compute_match_score()` both users with zero preferred courts (weight redistribution)
- `search_candidates()` 30-day inactivity filter boundary
- `respond_to_proposal()` proposer suspended after sending

### 13. Weather (`services/weather.py`) — 23 tests → needs ~8 more

**Untested functions:**
- `check_free_cancel()` — **never directly tested**
- `_fetch_warnings()` — never tested independently
- `_fetch_daily_forecast()` / `_fetch_hourly_forecast()` — never tested independently
- `_parse_daily()` / `_parse_hourly()` — never tested

**Untested scenarios:**
- `get_weather()` cache hit path (only miss tested)
- `get_weather()` hourly vs daily selection boundary at exactly 24 hours
- Chinese typhoon variants in alerts ("颱風", "台风")

### 14. Assistant (`services/assistant.py`, `services/llm.py`) — 14 tests → needs ~4 more

**Untested functions:**
- `_normalize_response()` — never tested

**Untested scenarios:**
- `ClaudeProvider.parse()` tool_use not in response (fallback to empty dict)
- `_build_system_prompt()` with zh-Hans language
- `parse_booking()` with empty court_keyword string

### 15. Chat (`services/chat.py`) — 25 tests → needs ~10 more

**Untested functions:**
- `get_room_by_event_id()` — **never tested**
- `set_event_room_readonly()` — **never tested**

**Untested scenarios:**
- `send_message()` room not found error path
- `get_messages()` invalid cursor (non-existent before_id), empty room
- `add_participant()` duplicate participant
- `remove_participant()` user not in room
- `get_unread_count()` user not a participant
- WebSocket timeout behavior, suspended user connection

### 16. Event (`services/event.py`) — 21 tests → needs ~20 more

**Untested functions (direct tests):**
- `update_event()` — never tested directly
- `remove_participant()` — never tested directly
- `_check_event_completion()` — never tested directly
- `list_my_events()` — never tested

**Untested scenarios:**
- `validate_set_score()` tiebreak variations: 7-6, 10-8 match tiebreak, boundary values
- `validate_match_score()` deciding set with match_tiebreak, too many sets
- `join_event()` NTRP exact boundaries, event exactly full, non-OPEN status
- `confirm_score()` submitter trying to confirm own score
- `dispute_score()` non-player user, already disputed
- `_generate_elimination_draw()` various bracket sizes (2, 3, 4, 7, 8, 16)
- `_generate_round_robin_draw()` odd player count, single group
- `get_standings()` walkover matches, tie-breaking, elimination event
- `get_bracket()` round-robin event (should handle gracefully)
- `cancel_event()` already cancelled/completed event

### 17. Admin (`services/admin.py`) — 21 tests → needs ~15 more

**Untested functions:**
- `list_all_bookings()` — **zero tests**
- `admin_cancel_booking()` — **zero tests**
- `list_all_events()` — **zero tests**
- `admin_cancel_event()` — **zero tests**
- `admin_remove_participant()` — **zero tests**
- `admin_delete_message()` — endpoint tested but service-level gaps

**Untested scenarios:**
- Suspend already-suspended user, unsuspend non-suspended user
- Change role to invalid value
- Approve already-approved court
- Non-existent resource errors (user, court, booking, event, message)
- Pagination and combined filters for all list operations

### 18. Word Filter (`services/word_filter.py`) — 5 tests → needs ~3 more

**Untested scenarios:**
- `None` input (will crash — `content.lower()` on None)
- Partial word matching ("fuck" matches "fucking")
- File not found / empty file behavior

### 19. i18n (`app/i18n.py`) — 5 tests → needs ~3 more

**Untested scenarios:**
- `None` language parameter
- `None` key parameter
- Language code case sensitivity ("EN" vs "en")

---

## Summary

| Module | Current Tests | Estimated New Tests | Priority |
|--------|--------------|-------------------|----------|
| Event | 21 | ~20 | **Critical** |
| Admin | 21 | ~15 | **Critical** |
| Booking | 22 | ~15 | High |
| Matching | 29 | ~12 | High |
| Chat | 25 | ~10 | High |
| Review | 15 | ~10 | High |
| Auth | 10 | ~12 | Medium |
| Credit | 7 | ~8 | Medium |
| Users | 4 | ~8 | Medium |
| Weather | 23 | ~8 | Medium |
| Report | 13 | ~8 | Medium |
| Courts | 9 | ~6 | Medium |
| Block | 13 | ~6 | Medium |
| Follow | 14 | ~6 | Medium |
| Notification | 20 | ~5 | Low |
| Ideal Player | 10 | ~5 | Low |
| Assistant | 14 | ~4 | Low |
| Word Filter | 5 | ~3 | Low |
| i18n | 5 | ~3 | Low |
| **Total** | **280** | **~154** | |

## Approach

- One test file per module (extend existing `tests/test_<module>.py`)
- Tests are integration tests against real PostgreSQL
- Audit first, fix bugs later (document failures, don't fix inline)
- Group new tests logically near existing related tests in each file
