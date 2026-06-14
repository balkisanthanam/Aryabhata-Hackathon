# Teacher Agent ("Guru") — Decision Log

Append-only log of decisions made on the Teacher Agent initiative. Each entry is dated and numbered. When a prior decision is revisited or reversed, add a new dated entry referencing the original — do not edit history.

Decisions here are the canonical record. `TheDefinition.md` evolves as a design narrative; this log is the source of truth for *what was decided when*.

---

## 2026-05-15 — Functionality alignment session

Source: long discussion between Balakrishnan and Claude grounding the in-progress design corpus (`TheDefinition.md`, `GPTSpec.md`, `Gemini_V2.md`) against a Gemini Deep Research report on JEE tutoring methodologies (`Research/Researching JEE Tutoring Methodologies.docx`).

### Positioning & scope

**D1. Product framing: "JEE Coach through Problems."**
Primary use case: student says *"coach me on Thermodynamics"* or uploads a specific problem. Guru assumes theory exposure exists — it does not teach lectures. Runs a problem-driven progression: diagnose → graded complexity → mastery → interleaving. Ad-hoc single-problem doubt-help is the secondary use case using the same engine. Tutoring (replacing classroom teaching) is explicitly out of scope.

**D2. Target audience.**
CBSE 11-12 + JEE Main/Advanced aspirants, in Mathematics, Physics, Chemistry. Indian market, B2C.

**D3. Differentiation thesis (the moat).**
Four pillars:
- Pedagogy-grounded — modeled on real expert teachers, not a solver with politeness on top.
- Indian/cultural rooting — calm, observant, slightly strict; not Western chatbot chattiness.
- Behavioral memory (cross-session, cross-subject) — structurally impossible for ChatGPT/Gemini.
- Grounded specificity — cited JEE traps, named twists, syllabus alignment; vs ChatGPT's plausible-but-unreliable references.

### Pedagogy

**D4. Adopt the Deep Research 12-Move FSM as v1 pedagogy spec.**
Moves: Foundational Anchor, Aporia Induction, Socratic Unblock, Scaffolded Blueprint, Faded Completion, Deep Quality Drill, Verbalization Protocol, Multi-Modal Pivot, Mistake Typology Log, Isomorphic Verification, Expertise Reversal Trigger, Interleaved Crucible. Adopted with four required extensions: cold-start move, persona-gating (Move 2 risky for fragile students), cross-session Behavioral Trait Ledger (Move 9 made persistent), doubt-help fast-path (subset of moves for ad-hoc use case).

**D5. Error Typology adopted.**
Conceptual / Formulaic / Calculation / Strategic — each with distinct remediation per the Deep Research report.

**D6. Ahaguru's "70% Easy" principle adopted.**
Difficulty distribution biased toward early wins, not balanced. Affects Move 6 (Deep Quality Drill) sampling and overall session arc.

**D7. Pedagogy reference models.**
- Ahaguru (Dr. Balaji Sampath) — formalized framework, characterized by Deep Research report.
- Balakrishnan's son's Physics tuition teacher (private, non-institute, NCERT+JEE+JEE Adv) — to be characterized via structured interview.
- Ahaguru Maths tutor — same approach if access exists.

### Personas

**D8. Persona axis = behavior, not tenure.**
Behavior axis: rusher / struggler / shortcut-seeker (cf. Arjun / Meera / Ravi in `GPTSpec.md`). Tenure (Anu/Ram/Uma from `TheDefinition.md`) describes data state, not pedagogy choices — folded into "cold-start vs returning" as an orthogonal concern.

**D9. Personas are templates with live blending.**
Each persona = a default treatment (preferred moves, intervention thresholds, tone). A live classifier maintains a persona-blend belief (e.g., `{rusher: 0.6, struggler: 0.2, shortcut-seeker: 0.2}`) and updates after each turn. FSM uses the current blend to choose move variants. Cold-start = uniform prior or quick diagnostic; settled estimate by turn ~3-4.

### Multimodal input / output

**D10. No free-form handwriting input in V1.**
Reasons: phones are bad canvases, finger imprecision, low % of student turns are actually symbolic input. Revisit at V2 with real session data.

**D11. V1 input modalities: text + voice + math keyboard + image upload + tap-to-annotate.**
Voice is central for short turns. Gemini multimodal is the V1 ASR/math-interpretation bet. Pre-architecture spike required: 1-day prototype testing Gemini multimodal on real Indian-student speech (10 students × 5 math sentences) to score WER and de-risk before committing.

**D12. V1 output modalities: text (LaTeX/chem-notation), generated diagrams, optional TTS.**

### Architecture (high-level)

**D13. Agentic Harness pattern adopted.**
Most of the system is software (graphs, memory, agents, FSM). Chat LLM is the central expensive piece; everything else is optimizable.

**D14. Two-Pass Solver pattern adopted.**
Fast diagnostic LLM (<800ms) engages the student while heavy Deep Solve runs async. Resolves the "novel problem latency" issue flagged in `TheDefinition.md`.

**D15. Cost target: ~₹120/month per student for ~20 sessions.**
Extra usage paid above that. Margin is thin but plausible if Gemma 4 fine-tune for solutions works.

**D16. Fine-tuning strategy.**
- Solution generator: Gemma 4 fine-tuned to *approach* (not equal) Gemini 3.1 Pro on JEE solutions.
- JEE Gold + NCERT Gold pipelines (Aryabhata main repo) are precursor work.
- ASR and OCR: focused fine-tunes for in-scope vocabulary.
- Orchestrator/judge LLM: stays on Gemini Pro / Claude Sonnet for V1 (harder to distill).

### Graphs

**D17. Two-Graph architecture confirmed.**
- Concept Pedagogy Graph: ~2,500 nodes (mostly populated via JEE Ascent M2 = 2,708 nodes today).
- Problem Pedagogy Graph: 6,400+ JEE 2024 problems (JEE Ascent M3), grows over time.
- Concept edges: prerequisites, canonical traps, isomorphic cross-subject links.
- Problem edges: NUMERICAL_TWIN, BOUNDARY_TWIST, CATCHES_MISTAKE.

**D18. Graph cost is editorial, not runtime.**
Runtime lookups are cheap. The costly piece is authoring traps and twist edges to a quality bar that doesn't break student trust. MVP per chapter ≈ 30-35 expert-review hours. Realistic approach: LLM-bootstrap + expert spot-check with evaluation gates.

### Demo/Proto scope (renamed from "MVP" — see 2026-05-15 update below)

**D19. Demo/Proto scope: one chapter, one subject, fully coached.**
Renamed from "MVP" on 2026-05-15. The first build is a *demo/proto* — for showing potential students, advisors, expert teachers, and other interest groups what Guru does. Not a commercial launch. Implications: polish bar = enough to feel real in a 5-10 min demo; telemetry/feedback capture is more important than payment infra; no auth/billing/account systems in this build; pick the demoable persona moments (stubs acceptable behind the scenes).

Don't sprawl breadth. Leading candidate: **Kinematics (Physics)** — visual intuition rich (showcases multimodal), rushers vs strugglers diverge most clearly (showcases personas), high JEE weight, well-tagged in existing corpus. Alternates: Thermodynamics (Physics or Chem), Limits & Continuity (Maths). Chapter to be confirmed in next session.

### Team & feasibility

**D20. Claude Max alone is not enough, but close.**
Minimum viable team: Balakrishnan + Claude Code + 1 expert teacher (part-time, non-negotiable) + 1-2 content interns + 5-10 student beta testers + freelance designer. Phase 2 additions: 1 ML engineer (for Gemma 4 fine-tunes), marketing/distribution.

### Out of scope / parked

**D21.** GPTSpec's "Curiosity Engine" parked — under-defined, can revisit later.
**D22.** Free-form canvas / handwritten FBDs — out of V1.
**D23.** Real-time peer features, leaderboards, gamification — out of V1.
**D24.** Premium licensed content (Cengage etc.) — Phase 2, don't gate MVP on it.

---

## 2026-05-15 — Follow-up decisions (same session)

### Ingestion & graph dynamics

**D25. Problem Graph is append-only with continuous ingestion.**
JEE + NCERT + (later) crawled sources flow in continuously, not as a one-time load. Each new problem flows through extract → tag (concept) → tag (difficulty) → optionally pair (twins) → optionally annotate (traps observed). Reuses JEE Ascent M3 tagger.

**D26. Crawled sources require a whitelist.**
Copyright + quality + syllabus alignment must be vetted before ingestion. Don't crawl indiscriminately.

**D27. Trap subgraphs are two-tier: canonical (derived) + discovered (observed).**
Resolves Balakrishnan's question on whether traps come from pedagogy knowledge or student performance. Answer is *both*, and they live in separate subgraphs:
- **Canonical traps** — well-documented teaching truths (e.g., "students forget mg cos θ for normal force on incline"). Authored pre-launch from NCERT exemplars, expert teacher notes, coaching material via LLM-bootstrap + expert review. Demo/proto-ready.
- **Discovered traps** — emerge from actual student error logs via the Trace Engine. Cannot exist before real session data. Grow continuously post-launch.

**D28. The Trace Engine is also an online learner that feeds the graph.**
Not just a memory store for per-student pedagogy. As students use Guru, their mistake patterns enrich the discovered-traps subgraph → next students benefit. This compounding effect is part of the structural moat.

### Voice spike refined (replaces earlier spike scope in priority thread #3)

**D29. Voice spike scope (locked).**
- **Subject**: Balakrishnan's son (single subject is fine for proto-stage spike — no recruitment).
- **Sentence mix (20 sentences total)**:
  - 5 Easy formulas: e.g., "sigma x squared", "two times pi r", "half m v squared", "g equals nine point eight".
  - 5 Medium: integrals, log expressions, vector ops, chemistry ratios.
  - 5 Hard: quadratic formula spoken in full, del cross E, multi-step organic name/reaction.
  - 5 Real student turns: not formulas — "I think mu n equals m g sin theta but I'm not sure about the sign", "wait should this be plus or minus?". This is what voice will actually carry.
- **Environments**: quiet room AND noisy room (TV/fan background). Real student rooms aren't quiet.
- **Metric**: not raw WER. Real workflow = ASR → LLM cleanup → structured math output. Score:
  - Intent preserved? (binary per sentence)
  - Symbolic content (variables, operators, numbers) correct after LLM cleanup?
- **Comparison** (optional, 1-2hr add-on): run the same samples through OpenAI Whisper as a cost-fallback comparison.
- **Artifact**: small spreadsheet with raw audio link, Gemini output, LLM-cleanup output, ground truth, per-sentence score.
- **Output**: go/no-go on voice as central V1 modality + boundary doc ("what voice can carry vs what it can't") feeding the math-keyboard UX.

### Open threads (updated)

The earlier priority list still holds. The "voice viability spike" thread (#3) is now fully specified per D29 — ready for execution by Balakrishnan in parallel.

A new thread added below to capture the editorial-authoring discussion that was flagged but deferred:

**8. Editorial authoring workflow** — *how* the canonical traps + twist edges + isomorphic pairs get authored at the quality bar required. Topics for that session: source selection (NCERT exemplars, expert teacher interviews, permissively-usable JEE prep books), LLM-bootstrap workflow with reviewer tooling (Google Sheet acceptable for proto stage), sample sizing (~5 traps × 40 concepts = 200 entries for one chapter), and identifying the expert reviewer. Deferred to its own dedicated chat.

1. Session 1 sharp move per persona — the single surgical move per archetype that even a ChatGPT-tired student notices in session 1.
2. Lock the 3 persona names + per-persona treatment defaults — 1-paragraph spec each.
3. Voice viability spike — 1-day Gemini multimodal ASR test (10 students × 5 math sentences). Go/no-go on voice as central V1 modality.
4. Pedagogy spec authoring — write `Design/Architecture/TeacherAgent/PedagogySpec.md`, customize the 12 moves with the four extensions, integrate tutor interview findings.
5. MVP chapter confirmation — confirm Kinematics or pick alternate.
6. Editorial cost realistic estimate — once chapter locked, estimate exact expert hours + identify the expert teacher.
7. Architecture deep-dive — once functionality + pedagogy locked, do the broad-picture architecture (services, data flow, FSM implementation, memory store). Dependencies (content, models, infra) explicit. Then size MVP delivery timebox.
