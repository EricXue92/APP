# NTRP Level Guide — Design Spec

## Overview

Add a reference endpoint that returns standard NTRP level descriptions in the user's language. Users read the descriptions, self-identify their level, and set it via the existing profile update flow. No quiz, no scoring — just a trilingual content delivery API.

## Endpoint

### `GET /api/v1/ntrp/levels`

Returns all NTRP level groups with descriptions, localized to the requested language.

**Auth:** Not required (usable pre-registration).

**Headers:** `Accept-Language: zh-Hant` (optional, defaults to zh-Hant)

**Response:**

```json
{
  "groups": [
    {
      "title": "Level 1.5 – 2.0: The Novice",
      "levels": [
        {
          "level": "1.5",
          "description": "You are just starting to play. You are working on making contact with the ball and learning the basic court lines."
        },
        {
          "level": "2.0",
          "description": "You can sustain a short rally at a slow pace. You are familiar with the basic positions for singles and doubles play."
        }
      ],
      "skills": [
        { "name": "Forehand", "description": "Developing a consistent swing." },
        {
          "name": "Backhand",
          "description": "Avoids using the backhand; grip issues are common."
        },
        {
          "name": "Serve/Return",
          "description": "Can get the ball in play, though double faults are frequent."
        }
      ]
    },
    {
      "title": "Level 2.5 – 3.0: The Intermediate Beginner",
      "levels": [
        {
          "level": "2.5",
          "description": "You can judge where the ball is going, but movement is still a bit mechanical. You can sustain a short rally with others of the same ability."
        },
        {
          "level": "3.0",
          "description": "This is the most common starting point for league play. You have consistent stroke production and can hit medium-paced shots with some direction."
        }
      ],
      "skills": [
        {
          "name": "Net Play",
          "description": "Comfortable at the net and can hit basic volleys."
        },
        {
          "name": "Strategy",
          "description": "Understands basic doubles positioning (one up, one back)."
        }
      ]
    },
    {
      "title": "Level 3.5 – 4.0: The Competitive Intermediate",
      "levels": [
        {
          "level": "3.5",
          "description": "You have achieved improved stroke dependability and direction on moderate shots. You are starting to use lobs, overheads, and approach shots with success."
        },
        {
          "level": "4.0",
          "description": "You have dependable strokes, including directional control and depth on both forehand and backhand sides."
        }
      ],
      "skills": [
        {
          "name": "Serve",
          "description": "You can use power and spin and are beginning to hit a \"forcing\" second serve."
        },
        {
          "name": "Rally",
          "description": "You can consistently rally from the baseline and \"construct\" points rather than just reacting."
        }
      ]
    },
    {
      "title": "Level 4.5 – 5.0: The Advanced Player",
      "levels": [
        {
          "level": "4.5",
          "description": "You have begun to master the use of power and spin. You can handle pace, have sound footwork, and can control depth of shots."
        },
        {
          "level": "5.0",
          "description": "You have good shot anticipation and frequently have an outstanding shot or weapon around which a game may be structured."
        }
      ],
      "skills": [
        {
          "name": "Strategy",
          "description": "You can vary game plans according to opponents. You hit winners or force errors off of short balls."
        }
      ]
    },
    {
      "title": "Level 5.5 – 7.0: The Elite / Professional",
      "levels": [
        {
          "level": "5.5",
          "description": "You have developed a high-level of consistency and can hit \"heavy\" balls with power and variety."
        },
        {
          "level": "6.0",
          "description": "These ratings are typically reserved for players who have had intensive training for national tournament competition or are professional tour players."
        }
      ],
      "skills": []
    }
  ]
}
```

## Content

5 level groups, each with:

- **title**: group name (e.g., "Level 1.5 – 2.0: The Novice")
- **levels**: individual NTRP levels with descriptions
- **skills**: skill-specific notes for that group (e.g., Forehand, Serve, Strategy)

All text is trilingual (zh-Hant, zh-Hans, en). Content is based on the official USTA NTRP rating descriptions.

### Trilingual Group Titles

| en                                            | zh-Hant                     | zh-Hans                     |
| --------------------------------------------- | --------------------------- | --------------------------- |
| Level 1.5 – 2.0: The Novice                   | 等級 1.5 – 2.0：初學者      | 等级 1.5 – 2.0：初学者      |
| Level 2.5 – 3.0: The Intermediate Beginner    | 等級 2.5 – 3.0：進階初學者  | 等级 2.5 – 3.0：进阶初学者  |
| Level 3.5 – 4.0: The Competitive Intermediate | 等級 3.5 – 4.0：競技中級    | 等级 3.5 – 4.0：竞技中级    |
| Level 4.5 – 5.0: The Advanced Player          | 等級 4.5 – 5.0：高級選手    | 等级 4.5 – 5.0：高级选手    |
| Level 5.5 – 7.0: The Elite / Professional     | 等級 5.5 – 7.0：精英 / 職業 | 等级 5.5 – 7.0：精英 / 职业 |

All level descriptions and skill notes follow the same trilingual pattern.

## Service Layer

**New file: `app/services/ntrp_guide.py`**

- `LEVEL_GROUPS`: list of group dicts with trilingual text for titles, level descriptions, and skill notes
- `get_level_guide(lang: str) -> list[dict]`: resolves trilingual text to the given language, returns the groups list

## Schemas

**New file: `app/schemas/ntrp_guide.py`**

```python
class SkillNote(BaseModel):
    name: str
    description: str

class LevelDetail(BaseModel):
    level: str
    description: str

class LevelGroup(BaseModel):
    title: str
    levels: list[LevelDetail]
    skills: list[SkillNote]

class LevelGuideResponse(BaseModel):
    groups: list[LevelGroup]
```

All with `model_config = {"from_attributes": True}`.

## Router

**New file: `app/routers/ntrp_guide.py`**

- `GET /levels` → `get_level_guide(lang)` → `LevelGuideResponse`

Uses `Lang` dependency. No auth required.

**Register in `app/main.py`:** `app.include_router(ntrp_guide.router, prefix="/api/v1/ntrp", tags=["ntrp"])`

## Testing

**New file: `tests/test_ntrp_guide.py`**

| Test                                | What it verifies                                   |
| ----------------------------------- | -------------------------------------------------- |
| Get levels returns all 5 groups     | Correct group count                                |
| Each group has levels and title     | Structure validation                               |
| Default language is zh-Hant         | Title contains Chinese characters                  |
| English language works              | Title contains "Novice", "Advanced", etc.          |
| zh-Hans language works              | Title contains simplified Chinese                  |
| Level values are valid NTRP strings | Each level matches pattern like "1.5", "3.0", etc. |

## What's NOT changing

- No database tables or migrations
- No changes to existing auth/registration/profile update flow
- No changes to existing `generate_ntrp_label()`
- No new dependencies
- User still sets their NTRP level via `PATCH /api/v1/users/me` with `ntrp_level` field

## Decisions

| Decision       | Choice                                                           | Rationale                                                        |
| -------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------- |
| User flow      | Read descriptions, pick level, apply via existing profile update | Simplest approach. No new write endpoints needed.                |
| Auth required  | No                                                               | Reference content, useful pre-registration.                      |
| Content source | Hardcoded in Python                                              | Standard NTRP descriptions rarely change. YAGNI for DB/config.   |
| i18n approach  | Trilingual dicts in service                                      | Matches app's existing pattern.                                  |
| Structure      | Grouped by level range                                           | Matches official USTA format. Easier to browse than a flat list. |
