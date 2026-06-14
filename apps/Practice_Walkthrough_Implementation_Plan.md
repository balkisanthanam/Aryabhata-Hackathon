# Practice Walkthrough Implementation Plan

## Objective
Implement an exercise-aware practice walkthrough that preserves the existing design, keeps sequential walkthrough as the default behavior, and lets users jump to an exercise or question when needed. In parallel, harden pipeline ingestion so the walkthrough never depends on silently incomplete `questiondata.solution` rows.

## Confirmed UX Decisions
- The exercise/question navigator lives inside the existing practice session UX.
- Default behavior on chapter entry remains question-first walkthrough.
- Users can open the navigator and jump to an exercise or question reference when needed.
- Question references only for now; progress-state UX is deferred.
- Ingestion mismatch must result in explicit incomplete state, not silent success.

## Recommended Runtime Flow
1. User selects a chapter from the Practice Dashboard.
2. Practice session opens directly to the first question in the first exercise, preserving the current sequential experience.
3. In parallel, the session loads lightweight exercise summaries for that chapter.
4. If the user opens the navigator, the app lazily loads question references for the selected exercise only.
5. User can either:
   - continue sequentially through next/prev, or
   - start from a chosen exercise, or
   - jump directly to a chosen question reference.

## Backend/API Changes

### 1. Lightweight chapter summary endpoint
Add `GET /api/practice/chapter-map?chapterId=...`

Response shape:

```json
{
  "chapterId": 15,
  "chapterTitle": "Units and Measurement",
  "chapterNumber": "1",
  "subject": "Physics",
  "exercises": [
    {
      "exerciseId": 45,
      "exerciseTitle": "EXERCISES",
      "questionCount": 12,
      "firstQuestionId": 866
    }
  ]
}
```

### 2. Lazy question-list endpoint per exercise
Add `GET /api/practice/exercise-questions?exerciseId=...`

Response shape:

```json
{
  "exerciseId": 45,
  "exerciseTitle": "EXERCISE 2.1",
  "chapterId": 2,
  "questions": [
    {
      "questionId": 866,
      "questionRef": "EXERCISE_2_1_Q1",
      "hasSolution": true
    }
  ]
}
```

### 3. Extend existing question endpoint semantics
Keep `GET /api/practice/question` as the detail endpoint.

Support:
- `exerciseId` only -> return first question in that exercise
- `exerciseId + questionId` -> return the selected question
- `mode=resume` -> preserve existing resume behavior

## Frontend Changes

### 1. Keep current layout and visual language
- Preserve the current practice page structure and header card treatment.
- Add a single “Open Exercise List” action in the session header.
- Use a side panel/drawer consistent with existing app patterns.

### 2. Add in-session navigator
Inside the session route:
- show exercise summaries in the panel
- highlight the current exercise
- provide a “Start From First Question” action for the selected exercise
- show question references as compact chips/buttons
- allow direct jump to a question

### 3. Keep exercise context explicit
Always display:
- subject
- chapter title
- exercise title
- current question reference

## Pipeline Reliability Changes

### 1. Post-ingestion validation
After Stage 3 DB writes, validate:
- expected extracted exercises == inserted `exercisedata` rows for chapter
- expected extracted questions == inserted `questiondata` rows for chapter
- expected solved questions == non-null `questiondata.solution` rows for chapter

### 2. Explicit incomplete state
Persist state such as:

```json
{
  "completion_state": "incomplete",
  "validation_summary": {
    "expected_question_count": 36,
    "actual_question_count": 36,
    "expected_solution_count": 36,
    "actual_solution_count": 0,
    "is_complete": false
  }
}
```

### 3. Recovery alignment
`fix_db_ingestion.py` should re-run the same validation and only mark state complete when counts match.

## Why JSON Standardization Is Deferred
The walkthrough reads PostgreSQL, not saved local solution JSON. Since Gemini raw output is stable and the core issue is DB completeness rather than prompt instability, saved JSON standardization is optional and should not block UX or ingestion reliability work.

## Verification Checklist
1. Chapter entry still opens a question immediately.
2. Exercise list is visible on demand inside the session.
3. Starting from a chosen exercise works.
4. Jumping to a chosen question reference works.
5. Sequential next/prev still crosses exercise boundaries correctly.
6. Resume still works and users can still open the navigator afterward.
7. Stage 3 marks incomplete on DB count mismatch.
8. Recovery utility resolves incomplete state and only then marks completion true.