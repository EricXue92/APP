# NTRP Self-Assessment Questionnaire — Design Spec

## Overview

Add a self-assessment questionnaire that helps users determine their NTRP level through 6 multiple-choice questions. The quiz is a standalone feature — it returns a recommended level but does not auto-update the user's profile. No auth required. All content is trilingual (zh-Hant, zh-Hans, en).

## Endpoints

### `GET /api/v1/ntrp/questions`

Returns the quiz questions localized to the requested language.

**Auth:** Not required (usable pre-registration).

**Headers:** `Accept-Language: zh-Hant` (optional, defaults to zh-Hant)

**Response:**

```json
{
  "questions": [
    {
      "id": 1,
      "text": "你打網球多久了？",
      "options": [
        { "key": "a", "text": "不到半年", "points": 1 },
        { "key": "b", "text": "半年到兩年", "points": 2 },
        { "key": "c", "text": "兩年到五年", "points": 3 },
        { "key": "d", "text": "五年以上", "points": 4 }
      ]
    }
  ]
}
```

### `POST /api/v1/ntrp/assess`

Receives answers, calculates NTRP level, returns result with localized label.

**Auth:** Not required.

**Headers:** `Accept-Language: zh-Hant` (for label language)

**Request:**

```json
{
  "answers": [
    { "question_id": 1, "selected": "c" },
    { "question_id": 2, "selected": "b" },
    { "question_id": 3, "selected": "b" },
    { "question_id": 4, "selected": "a" },
    { "question_id": 5, "selected": "c" },
    { "question_id": 6, "selected": "b" }
  ]
}
```

**Response:**

```json
{
  "ntrp_level": "3.5",
  "ntrp_label": "3.5 中級"
}
```

**Validation:** All 6 question IDs must be present. Each `selected` key must be a valid option for that question. Missing or invalid → 400.

## Quiz Content

### Questions (6 total)

| #   | Topic              | What it measures                              |
| --- | ------------------ | --------------------------------------------- |
| 1   | Playing experience | Years of play                                 |
| 2   | Serve ability      | Consistency and technique                     |
| 3   | Rally consistency  | Groundstroke control                          |
| 4   | Net play           | Volleys and overhead                          |
| 5   | Match play         | Tactical awareness and competition experience |
| 6   | Movement & fitness | Court coverage                                |

Each question has 4 options (a/b/c/d) worth 1-4 points.

All question text and option text are stored as trilingual dicts (`zh-Hant`, `zh-Hans`, `en`).

### Scoring Algorithm

- **Total points range:** 6-24 (6 questions × 1-4 points)
- **Mapping:**

| Points | NTRP Level |
| ------ | ---------- |
| 6-8    | 2.0        |
| 9-10   | 2.5        |
| 11-13  | 3.0        |
| 14-16  | 3.5        |
| 17-19  | 4.0        |
| 20-22  | 4.5        |
| 23-24  | 5.0        |

No `+/-` modifiers — the quiz returns a clean base level. Users can adjust manually when applying the result to their profile.

### Localized NTRP Labels

The assess endpoint returns labels in the requested language:

| Level | zh-Hant    | zh-Hans    | en                    |
| ----- | ---------- | ---------- | --------------------- |
| 2.0   | 2.0 初級   | 2.0 初级   | 2.0 Beginner          |
| 2.5   | 2.5 初級   | 2.5 初级   | 2.5 Beginner+         |
| 3.0   | 3.0 中初級 | 3.0 中初级 | 3.0 Intermediate-Low  |
| 3.5   | 3.5 中級   | 3.5 中级   | 3.5 Intermediate      |
| 4.0   | 4.0 中高級 | 4.0 中高级 | 4.0 Intermediate-High |
| 4.5   | 4.5 高級   | 4.5 高级   | 4.5 Advanced          |
| 5.0   | 5.0 高級   | 5.0 高级   | 5.0 Advanced+         |

## Service Layer

**New file: `app/services/ntrp_quiz.py`**

- `QUESTIONS`: list of question dicts with trilingual text and scored options
- `NTRP_LABELS`: trilingual label map for each NTRP level
- `SCORE_TO_NTRP`: list of `(max_points, ntrp_level)` tuples for mapping
- `get_questions(lang: str) -> list[dict]`: resolves trilingual text to the given language
- `calculate_ntrp(answers: list[dict], lang: str) -> dict`: validates all answers, sums points, maps to NTRP level, returns `{"ntrp_level": ..., "ntrp_label": ...}`. Raises `ValueError` for missing questions or invalid option keys.

## Schemas

**New file: `app/schemas/ntrp_quiz.py`**

```python
class QuestionOption(BaseModel):
    key: str
    text: str
    points: int

class Question(BaseModel):
    id: int
    text: str
    options: list[QuestionOption]

class QuestionsResponse(BaseModel):
    questions: list[Question]

class AnswerItem(BaseModel):
    question_id: int
    selected: str

class AssessRequest(BaseModel):
    answers: list[AnswerItem]

class AssessResponse(BaseModel):
    ntrp_level: str
    ntrp_label: str
```

## Router

**New file: `app/routers/ntrp_quiz.py`**

- `GET /` → `get_questions(lang)` → `QuestionsResponse`
- `POST /assess` → `calculate_ntrp(answers, lang)` → `AssessResponse`

Both use the `Lang` dependency for language selection. Neither requires auth.

**Register in `app/main.py`:** `app.include_router(ntrp_quiz.router, prefix="/api/v1/ntrp", tags=["ntrp"])`

## Testing

**New file: `tests/test_ntrp_quiz.py`**

| Test                            | What it verifies                                  |
| ------------------------------- | ------------------------------------------------- |
| Get questions returns all 6     | Correct count and structure                       |
| Get questions respects language | zh-Hant vs en returns different text              |
| Assess lowest scores → 2.0      | All "a" answers (6 points) → NTRP 2.0             |
| Assess highest scores → 5.0     | All "d" answers (24 points) → NTRP 5.0            |
| Assess mid scores → 3.5         | Mixed answers in 14-16 range                      |
| Assess missing question → 400   | Not all 6 question IDs provided                   |
| Assess invalid option key → 400 | Selected key not in question's options            |
| Label language matches request  | zh-Hant returns "中級", en returns "Intermediate" |

## What's NOT changing

- No database tables or migrations
- No changes to existing auth/registration flow
- No changes to existing `generate_ntrp_label()` (quiz has its own trilingual labels)
- No new dependencies

## Decisions

| Decision            | Choice                      | Rationale                                                   |
| ------------------- | --------------------------- | ----------------------------------------------------------- |
| Auto-update profile | No                          | Quiz is a recommendation. User decides whether to apply it. |
| Auth required       | No                          | Useful pre-registration. No sensitive data.                 |
| Questions source    | Hardcoded in Python         | Small fixed quiz. YAGNI for DB/config storage.              |
| i18n approach       | Trilingual dicts in service | App is trilingual. Quiz should match.                       |
| +/- modifiers       | Not returned                | Quiz gives base level. User adjusts manually.               |
| Number of questions | 6                           | Covers key tennis skill dimensions without being tedious.   |
