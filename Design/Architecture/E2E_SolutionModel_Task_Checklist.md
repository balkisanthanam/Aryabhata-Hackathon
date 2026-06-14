# Milestone 1 Tasks: Immediate Impact Foundation

- `[x]` **1.1 Localized "Smart Context" PgVector**
  - `[x]` Implement `get_context_for_question()` leveraging `pgvector` to replace full PDF retrieval
  - `[x]` Expose context retrieval as a shared utility for both `Multi-Step` and `Student Feedback` pipelines
- `[x]` **1.2 Centralized "GoldenGenerator"**
  - `[x]` Create `GoldenGenerator` wrapper around `GeminiClient` in `solver_engine.py`
  - `[x]` Implement the two-pass Critique loop (Zero-Shot Gen -> Critique & Feedback -> Final Output)
- `[x]` **1.3 A/B Testing vs Old Solutions**
  - `[x]` Build lightweight LLM-As-A-Judge comparison script
  - `[x]` Run comparison loop over a sample of 50 existing solutions (Old vs New PgVector context)
