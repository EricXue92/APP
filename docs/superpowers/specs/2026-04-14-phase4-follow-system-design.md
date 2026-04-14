# Phase 4 — Follow System Design Spec

## Overview

Unidirectional follow system where mutual follows = friends. Users can follow/unfollow others, view their followers/following lists, and see mutual (friend) status. Integrates with the existing Block system — blocked users cannot follow each other, and existing follows are removed on block.

## Data Model

### Follow table

```
follows
├── id: UUID (PK, default uuid4)
├── follower_id: UUID (FK → users.id, ON DELETE CASCADE)
├── followed_id: UUID (FK → users.id, ON DELETE CASCADE)
├── created_at: DateTime(timezone=True), server_default=now()
└── UNIQUE(follower_id, followed_id)
```

Relationships: `follower` and `followed` pointing to `User`, same pattern as `Block` model.

## Service Layer

**File:** `app/services/follow.py`

### create_follow(session, follower_id, followed_id, lang)

1. Validate `follower_id != followed_id` → `ValueError` (400)
2. Validate target user exists → `ValueError` (400)
3. Check `is_blocked(session, follower_id, followed_id)` → `ValueError` (400)
4. Check duplicate follow → `LookupError` (409)
5. Create `Follow` row, commit, return it

### delete_follow(session, follower_id, followed_id, lang)

1. Look up follow row by `(follower_id, followed_id)`
2. If not found → `LookupError` (404)
3. Hard delete, commit

### list_followers(session, user_id)

Return all `Follow` rows where `followed_id = user_id`, ordered by `created_at desc`.

### list_following(session, user_id)

Return all `Follow` rows where `follower_id = user_id`, ordered by `created_at desc`.

### is_mutual(session, user_a, user_b) → bool

Check both directions exist (A→B and B→A). Used to compute the `is_mutual` field on responses.

### remove_follows_between(session, user_a, user_b)

Delete any follow rows between the two users (both directions). Called from `block.create_block()` during block creation, in the same transaction.

## Schemas

**File:** `app/schemas/follow.py`

### FollowCreateRequest

```python
class FollowCreateRequest(BaseModel):
    followed_id: uuid.UUID
```

### FollowResponse

```python
class FollowResponse(BaseModel):
    id: uuid.UUID
    follower_id: uuid.UUID
    followed_id: uuid.UUID
    is_mutual: bool
    created_at: datetime

    model_config = {"from_attributes": True}
```

`is_mutual` is not stored on the model — it is computed in the service layer. List functions query for reverse follows and return dicts/objects with `is_mutual` populated. The `create_follow` function also checks for the reverse follow and includes `is_mutual` on the returned object.

## Router

**File:** `app/routers/follows.py`
**Registered at:** `/api/v1/follows`

| Method | Path | Auth | Response | Description |
|--------|------|------|----------|-------------|
| POST | `/api/v1/follows` | CurrentUser | 201 FollowResponse | Follow a user |
| DELETE | `/api/v1/follows/{followed_id}` | CurrentUser | 204 | Unfollow a user |
| GET | `/api/v1/follows/followers` | CurrentUser | list[FollowResponse] | List my followers |
| GET | `/api/v1/follows/following` | CurrentUser | list[FollowResponse] | List who I follow |

Exception mapping:
- `ValueError` → 400
- `LookupError` on create → 409
- `LookupError` on delete → 404

## Block Integration

In `services/block.py` `create_block()`, before creating the block row, call `remove_follows_between(session, blocker_id, blocked_id)` to delete any existing follow rows in both directions within the same transaction.

On unblock, follows are NOT restored (same pattern as hidden reviews not being restored on unblock).

Follow creation checks `is_blocked()` and rejects with 400 if either user has blocked the other.

## i18n Keys

| Key | zh-Hans | zh-Hant | en |
|-----|---------|---------|-----|
| `follow.cannot_follow_self` | 不能关注自己 | 不能關注自己 | Cannot follow yourself |
| `follow.already_following` | 已经关注了该用户 | 已經關注了該用戶 | Already following this user |
| `follow.not_found` | 未找到关注记录 | 未找到關注記錄 | Follow not found |
| `follow.user_not_found` | 用户不存在 | 用戶不存在 | User not found |
| `follow.blocked` | 操作被拒绝 | 操作被拒絕 | Action not allowed |

## Testing

**File:** `tests/test_follows.py`

### Test cases

**Happy path:**
- Follow a user → 201, returns FollowResponse with `is_mutual: false`
- Unfollow a user → 204
- List followers → returns correct list
- List following → returns correct list

**Mutual detection:**
- A follows B → `is_mutual: false`
- B follows A → both show `is_mutual: true`
- A unfollows B → B's follow shows `is_mutual: false` again

**Validation:**
- Follow self → 400
- Duplicate follow → 409
- Unfollow non-existent → 404
- Follow blocked user → 400
- Follow user who blocked you → 400
- Target user doesn't exist → 400

**Block integration:**
- A follows B, B follows A → A blocks B → both follow rows removed
- While blocked, A cannot follow B (and vice versa) → 400
