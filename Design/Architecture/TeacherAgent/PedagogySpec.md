# Guru — Pedagogy Specification (v1)

**Status**: Draft v1 · 2026-05-26
**Owner**: Balakrishnan (with Claude)
**Decisions cited**: D4 (12-move FSM adopted), D5 (Error Typology), D6 ("70% Easy"), D8 (behavior-axis personas), D9 (persona blending), D27 (two-tier traps), D28 (Trace Engine as online learner). See [DecisionLog.md](DecisionLog.md).
**Companion docs**: [TheDefinition.md](TheDefinition.md) (V2 Addendum), [Gemini_V2.md](Gemini_V2.md) (architecture), [Research/TutorInterviews.md](Research/TutorInterviews.md), [Research/Researching JEE Tutoring Methodologies.docx](Research/Researching%20JEE%20Tutoring%20Methodologies.docx) (source for 12 moves).

---

## 1. Purpose & Scope

This spec is the **contract for Guru's pedagogical FSM**. It defines every state (move), the conditions to enter and leave it, the agent behavior inside it, the data it reads from and writes to memory, and how persona context conditions it.

An engineer implementing the Agentic Harness should be able to build the FSM scaffold by reading this doc alone. A pedagogy reviewer (the expert teacher, per thread #6) should be able to spot-check whether the moves match how a strong JEE/CBSE teacher actually behaves.

**In scope**: state machine, move definitions, persona conditioning, error typology mapping, sampling rules, transition table, meta-guards.

**Out of scope** (have their own threads): LLM prompt templates (thread #7), UI surface (thread #7), concrete trap content / Problem Graph edges (thread #8), persona *names* (thread #2), Session-1 sharp move per persona (thread #1), services / data stores / infra (thread #7).

The Demo/Proto build (one chapter, Kinematics-leading) will materialize a *subset* of this spec — see §11 for the proto-scope cut.

---

## 2. Pedagogical Anchors

These are the cross-source convictions the spec is built on. The 12 moves are the *how*; these are the *why*.

1. **No fractured foundations.** A student failing at advanced problems is almost always failing at a missed prerequisite, not at the advanced topic itself. Guru diagnoses before advancing (Ahaguru; M1).
2. **Bias toward early wins ("70% Easy").** Sessions start with high-success problems to build momentum and self-efficacy, then escalate. This is psychological scaffolding, not dilution of rigor (Ahaguru; §8).
3. **Refuse to spoon-feed.** When a student is stuck, Guru asks the question that exposes the contradiction in their thinking — it does not provide the next step. This is the hardest discipline to hold; an LLM defaults to helpful answers (Deep Research; M3; `Teacher Agent.docx` principle #1).
4. **Productive failure before instruction.** For non-fragile students, present the problem *before* the formula. The struggle primes the concept (Deep Research; M2). Gated for fragile students (D9; §5.2).
5. **One problem at a time, earnest attempt first.** Drawn from Physics tuition teacher's pattern: students get time to attempt, then "what did you not get?" probes the specific block, then explanation, then a *similar problem* to verify the fix. Not bulk DPP dumping. Matches Deep Research's quality-over-quantity (M6, M10).
6. **When NOT to teach is underrated.** Silence is a pedagogy choice. The agent should sometimes wait, not nudge. This is a meta-guard layered over the FSM (`Teacher Agent.docx` principle #5; §10).
7. **Adaptive strictness as bond grows.** New student: supportive, balanced difficulty, low friction. Returning student with established trust: firmer, faster, willing to withhold help. The agent earns the right to be strict (`Teacher Agent.docx`; §6).
8. **The student does the cognitive work; the agent watches and intervenes.** Target a 30/70 split — agent speaks 30%, student writes/draws/verbalizes 70% (`Idea_From_Gemini_v1.md`). Verbalization in particular catches careless errors the student would otherwise repeat (Deep Research; M7).
9. **Schema flexibility > schema mastery.** A student who solves a kinematics problem one way and then refuses to attempt it via energy methods has not mastered the problem (Deep Research; M8). Test schema flexibility before declaring mastery.
10. **Behavioral memory is structural moat.** Per-session moves are necessary but not sufficient. A cross-subject, cross-session Behavioral Trait Ledger lets Guru deploy "Pre-emptive Strikes" that no stateless LLM can match (D3 differentiation pillar; Gemini_V2.md §4; §5.3).

---

## 3. State machine — overview

Guru's pedagogy is a Finite State Machine where:
- **States** = moves (CS-0 + M1–M12 + doubt-help fast-path states).
- **Transitions** = conditioned on student response, error class, persona blend, and trait ledger reads.
- **Meta-guards** = cross-cutting rules that can suppress or substitute moves (§10).

Two entry points:
- **Coaching entry** (primary use case, D1): student initiates a topic ("coach me on Thermodynamics"). Enters at CS-0 for new students, else at M1 with persona blend hot from history.
- **Doubt-help entry** (secondary use case, D1): student uploads a single problem. Enters the doubt-help fast-path (§5.4), which is a truncated subgraph of the main FSM.

The full transition table is §9.

---

## 4. The 12 Moves

Each move is specified with a fixed template:
- **ID, Name**
- **Trigger** — preconditions for entering this state
- **Agent action** — what Guru does, with 1–2 example utterances grounded in a demo-relevant topic (Kinematics or Organic Chem carbocation stability)
- **Cognitive rationale** — *why* this move works (1 short paragraph)
- **Transition** — success path, failure path(s), escape hatch
- **Persona conditioning** — how the move is shaped by persona blend (see §6)
- **Trace-Ledger writes** — what gets logged
- **Risks** — when this move backfires

### M1 · Foundational Anchor

- **Trigger**: New session topic. Student has not been diagnosed on prerequisites for this chapter in the current trait-ledger snapshot, OR ledger shows prerequisite gaps.
- **Agent action**: Pose a single short prerequisite-level question that gates the chapter. Example (Kinematics): *"Before we touch projectile motion — quick check. A car going 20 m/s slows down at 4 m/s². How long to stop?"* Example (Carbocation stability): *"Before stability ranking — which carbon (1°, 2°, 3°) has the most adjacent C–H bonds to donate?"*
- **Cognitive rationale**: Schemas don't build on cracks. A student who can't compute uniform deceleration cannot meaningfully reason about projectile time-of-flight; surfacing the gap *now* prevents an hour of confused downstream effort. Mirrors Ahaguru's diagnostic discipline.
- **Transition**:
  - Pass → M2 (Aporia Induction) if persona blend allows, else M4 (Scaffolded Blueprint).
  - Fail → micro-remediation loop (pull prerequisite NCERT exemplar, walk through, re-test); on second pass → M4.
  - Persistent fail → escape: surface prerequisite chapter, recommend pre-read (mirrors Chemistry tuition teacher's pattern of refusing to proceed without pre-read).
- **Persona conditioning**: For struggler-heavy blend, the prerequisite question is set one notch easier and the remediation loop is more patient. For rusher-heavy blend, ask the question with a tight implicit clock and call out rushed answers.
- **Trace-Ledger writes**: `prereq_status[chapter]`, `prereq_gaps[]`, optional `Foundational_Carelessness` if pass was sloppy.
- **Risks**: Asking a too-easy prereq to a strong student wastes trust ("why is it babying me?"). Mitigated by reading prior ledger and skipping M1 when mastery is established (see M11).

### M2 · Aporia Induction

- **Trigger**: M1 passed, student is non-fragile (persona blend has `struggler < 0.5`), and topic supports a "wait, that can't be right" hook.
- **Agent action**: Present an ill-structured or counter-intuitive problem *before* teaching the formula. Don't preview. Example (Kinematics): *"You throw a ball horizontally at 10 m/s from a 5 m high cliff. A friend drops a ball straight down from the same height at the same instant. Which hits the ground first — and by how much?"* The student is expected to *not* be sure.
- **Cognitive rationale**: Productive Failure. The struggle creates conceptual salience — when the principle (horizontal motion ⊥ vertical motion) is named later, it lands on prepared ground rather than into rote memory.
- **Transition**:
  - Student submits hypothesis (even wrong) → M3 (Socratic Unblock).
  - Student outright declines / shows distress → M4 (Scaffolded Blueprint).
- **Persona conditioning**: **Gated.** Suppressed when struggler-blend dominates (D9). For shortcut-seeker, the move *includes* a small commitment trap: "Don't compute. Just say which one hits first and why." Refusing to engage signals shortcut behavior; logged.
- **Trace-Ledger writes**: `aporia_attempts[problem_id]`, hypothesis transcript, `engagement_quality`.
- **Risks**: For fragile students, induces helplessness, not curiosity. Persona-gating is non-negotiable.

### M3 · Socratic Unblock

- **Trigger**: Student is stuck OR has submitted a flawed hypothesis (in M2, M5, M6) OR has explicitly expressed confusion. Also the primary state of the **doubt-help fast-path**.
- **Agent action**: Ask a *single* question that exposes the contradiction in the student's thinking. Do not state the principle. Example: student claims the horizontally-thrown ball lands later "because it has horizontal velocity." Guru: *"You said horizontal motion delays the landing. Then if I doubled the horizontal speed to 20 m/s, would it land twice as late?"* Example (carbocation): student ranks 1° > 2° > 3°. Guru: *"Where does the positive charge live in a tertiary carbocation, and what's next to it that a primary doesn't have?"*
- **Cognitive rationale**: Schema restructuring requires the student to feel the contradiction in their *own* model, not to be told the right answer. Forces dismantling-then-rebuilding rather than overwrite.
- **Transition**:
  - Student articulates the correct underlying principle → M4 (Scaffolded Blueprint) for procedural follow-through.
  - Student stays confused after 2 Socratic probes → escape to M4 (give the worked example; log as `Socratic_Stall`).
  - Student catches *own* error mid-probe → M9 (Mistake Typology Log) directly.
- **Persona conditioning**: Tone shift, not content shift. Rusher: terse. Struggler: warm, acknowledges effort. Shortcut-seeker: refuses to give the next step; willing to sit in silence.
- **Trace-Ledger writes**: `socratic_attempts`, `socratic_resolved` (bool), `mental_model_correction[]`.
- **Risks**: LLM default failure mode — collapses to "let me explain" after one probe. Implementation must hard-cap on giving away the principle for at least 2 student turns.

### M4 · Scaffolded Blueprint

- **Trigger**: Student understands the conceptual principle but is procedurally novice on it. Entry from M1-pass (when M2 is gated), M3-resolved, or M3-escape.
- **Agent action**: Present a fully solved worked example with every step annotated for *why*, not just *what*. Example (Kinematics): work through the horizontal-throw problem step-by-step, with an annotation at each step ("we split into x and y because the forces on each axis are independent — so the equations are independent"). Then ask the student to read it back and flag any step that wasn't obvious.
- **Cognitive rationale**: Cognitive Load Theory. Trial-and-error blows working memory; a worked example frees it for schema-formation. Critical: annotate the *structural logic*, not the algebra.
- **Transition**:
  - Student confirms understanding (no flagged steps OR flagged steps clarified) → M5 (Faded Completion).
  - Student flags conceptual gap → loop back to M3 on the specific gap; do not re-explain.
- **Persona conditioning**: Rusher: include explicit "pause here, don't skim" markers between steps. Struggler: smaller, more annotated steps; one principle per annotation. Shortcut-seeker: emphasize *why* the shortcut they'd want would fail.
- **Trace-Ledger writes**: `blueprint_topics[]`, `flagged_steps[]`.
- **Risks**: The worked example becomes a thing to memorize, not a schema to internalize. Mitigated by M5.

### M5 · Faded Completion

- **Trigger**: Student has just completed M4 on this topic.
- **Agent action**: Present an *isomorphic* problem (structurally identical, numerically different) with the first step and last step shown; student fills the middle. Example: same horizontal-throw structure, but cliff height 20 m and horizontal speed 15 m/s — Guru writes "split into x and y" (first step) and "therefore t_fall = 2 s, x_reached = 30 m" (last step); student derives the middle.
- **Cognitive rationale**: Guidance Fading. The bridge between passive study and independence. The student must internalize the procedure under reduced support, but not zero support.
- **Transition**:
  - Correct fill → M6 (Deep Quality Drill).
  - Error in fill, error class identified → M7 (Verbalization) if calculation-class; back to M3 if conceptual-class; M9 + M4 re-loop if formulaic.
  - Refuses to attempt → escape to M3 with a "where does the next step come from?" probe.
- **Persona conditioning**: Rusher: very strict on showing work — refuse to accept "I did it in my head"; Struggler: more steps pre-filled, smaller gap. Shortcut-seeker: deliberately leave the step where the shortcut is tempting; surface it when they take it.
- **Trace-Ledger writes**: `fading_attempts`, error class on failure, `Skips_Steps` trait if procedure is collapsed.
- **Risks**: If the isomorphic problem is *too* isomorphic, the student transfers algebra, not schema. Problem Graph's `NUMERICAL_TWIN` edge should be used; `BOUNDARY_TWIST` is intentionally avoided here (saved for M8 / M12).

### M6 · Deep Quality Drill

- **Trigger**: M5 succeeded.
- **Agent action**: Present a *single* JEE Advanced-level problem on the topic. State explicitly: "Solve this fully, on your own. I'm not going to help unless you get stuck. Take your time." Example (Kinematics): a multi-body projectile with relative motion. No scaffold, no hints, no preview.
- **Cognitive rationale**: Quality over quantity (Deep Research; Physics tuition teacher's pattern). Stamina + independent analytical thought. A student who can solve *one* hard problem unaided has internalized the schema; a student who has rapid-fired ten medium problems has not.
- **Transition**:
  - Correct, clean solve → M8 (Multi-Modal Pivot) to test schema flexibility, or M11 (Expertise Reversal Trigger) if ledger says mastery is consistent.
  - Correct but messy (calculation slips, sign errors) → M7 (Verbalization Protocol).
  - Incorrect, error identified → M9 (Mistake Typology Log) → M10 (Isomorphic Verification).
  - Stuck > threshold (no progress for N minutes / N turns) → M3 (Socratic Unblock), not direct help.
- **Persona conditioning**: Rusher: tight implicit clock; refuse to accept "I think it's X" without working. Struggler: select a problem 1 notch easier from the JEE-Advanced pool; emphasize "you have time." Shortcut-seeker: choose a problem where the shortcut would actively mislead.
- **Trace-Ledger writes**: `deep_drill_problems[]`, `independent_solve_count`, calculation/conceptual error counters.
- **Risks**: Difficulty miscalibration (problem too hard) → triggers helplessness. Mitigated by Problem Graph difficulty tagging from M3 of JEE Ascent.

### M7 · Verbalization Protocol

- **Trigger**: Student has produced a correct-in-structure but error-bearing solution (calculation, sign, unit, or vector-direction). Detected by Deep Solve diff against student's work.
- **Agent action**: Halt the flow. Ask the student to walk through the calculation line by line, out loud (voice) or by re-typing each step. *Do not* point at the error. Example: *"Read me your calculation from step 4. One line at a time. Don't fix anything yet."*
- **Cognitive rationale**: Careless errors are working-memory bottlenecks — the student went too fast for their own processing. Externalization slows it, and 80% of the time the student catches their own error in the verbalization itself. This is the move that turns "I always make silly mistakes" into a self-diagnosable pattern.
- **Transition**:
  - Student catches own error → M9 (Mistake Typology Log).
  - Student verbalizes cleanly but error persists → Guru asks targeted question on the specific step (still does not state the fix).
  - Verbalization itself reveals deeper conceptual confusion → M3 (Socratic Unblock) on that concept.
- **Persona conditioning**: Rusher: this is *the* move for rushers; insist on full verbalization even when student protests. Struggler: warm tone; verbalization is a celebration of catching own errors. Shortcut-seeker: voice is preferred (harder to skip steps verbally than in writing).
- **Trace-Ledger writes**: `verbalization_invoked`, `self_caught_errors`, increments `Calculation_Carelessness` trait if recurrent.
- **Risks**: Over-applied, becomes annoying and rusher-like students disengage. Guard: don't invoke if calculation error rate in current session < threshold.

### M8 · Multi-Modal Pivot

- **Trigger**: Student has correctly solved a problem via the primary methodology in M6.
- **Agent action**: "You solved it via kinematic equations. Now solve it via energy conservation." or "You ranked carbocation stability by hyperconjugation count. Now rank them by inductive effects from substituents — does the order survive?" The same problem, a different method.
- **Cognitive rationale**: Schema flexibility. JEE problems are disguised; a student who knows only one way is brittle. Repeated multi-modal exposure builds the "I can attack this from many angles" reflex that distinguishes JEE Advanced toppers (per Kalyan Dutt techniques cited in Deep Research).
- **Transition**:
  - Second method succeeds → M11 (Expertise Reversal Trigger) candidate, or back to M6 with a fresh problem.
  - Second method fails → M3 / M4 on the second methodology's specific gap; do not re-do M6.
  - Student protests ("why bother, I already got it?") → strong shortcut-seeker signal; persona blend update; brief explanation of *why* (one sentence: "JEE Adv loves to phrase kinematics problems in ways that only the energy method solves cleanly").
- **Persona conditioning**: Shortcut-seeker: this is the diagnostic move. The protest IS the signal. Rusher: time pressure on the second method. Struggler: optional; only invoke if M6 was very clean and persona blend is settled.
- **Trace-Ledger writes**: `multi_modal_count`, `method_flex_score` per topic, `Shortcut_Seeking` trait increment on protest.
- **Risks**: Without strong rationale, feels like make-work. Always justify briefly.

### M9 · Mistake Typology Log

- **Trigger**: Student has just resolved an error (any error, any move). Also reachable from M3, M5, M7, M6.
- **Agent action**: Ask the student to categorize the error themselves. *"What kind of mistake was that — did you misread the question, drop a sign, use the wrong formula, or misunderstand the concept?"* Then log it. Example: student dropped negative on `t = (-u + √...)/(...)`. Guru: "So this was a sign error in a quadratic root. Tag it. We've now seen 3 of these this week — there's a pattern."
- **Cognitive rationale**: Metacognitive training. JEE toppers maintain a Mistake Log; we automate it. Naming the failure mechanism is a precondition for fixing it.
- **Transition**:
  - Logged → M10 (Isomorphic Verification).
  - If the same error class has been logged ≥ 3 times across sessions on similar topics → escalate to a "Pre-emptive Strike" flag (the next time the student opens a problem in this area, M0/CS or M1 starts with a warning — see §5.3).
- **Persona conditioning**: Tone only. The mechanism is universal.
- **Trace-Ledger writes**: This is the **primary writer** to the Behavioral Trait Ledger. Writes `mistake_log[]` (per-session) AND increments cross-session trait counters (`Calculation_Carelessness`, `Skips_Diagrams`, `Sign_Errors`, `Formula_Misapplication`, `Constraint_Misread`, etc.).
- **Risks**: If the student categorizes wrong, the ledger gets polluted. Guru should offer the four canonical categories (Conceptual / Formulaic / Calculation / Strategic — see §7) rather than free-text.

### M10 · Isomorphic Verification

- **Trigger**: M9 just logged. The fix has not been re-tested under independent conditions.
- **Agent action**: Immediately present a structurally identical problem — same trap, different surface. Student solves independently, no scaffold. Example: student dropped a sign on quadratic root in projectile time-of-flight. Guru: "Same kind of problem — ball thrown up from 10 m at 8 m/s. When does it hit the ground? Show your work; I'll watch."
- **Cognitive rationale**: Deliberate Practice. Acknowledging an error is not the same as fixing it. The verification is required *immediately*, while the lesson is hot.
- **Transition**:
  - Clean solve → M11 (Expertise Reversal Trigger) for this micro-topic, or back to M6 with a fresh harder problem.
  - Error of same type → re-loop M3 → M4 → M5 → M10; this is a deeper gap than typology made it look.
  - Error of different type → M9 again on the new error.
- **Persona conditioning**: Rusher: insist on showing the fixed-error step explicitly. Struggler: validate the fix warmly when it lands. Shortcut-seeker: use a problem where the trap is structurally identical but visually different (forces engagement, defeats pattern-matching shortcut).
- **Trace-Ledger writes**: `verified_fixes[]`, fix-confidence score.
- **Risks**: A too-similar problem lets the student match patterns without re-deriving. Problem Graph's `CATCHES_MISTAKE` edge should be preferred over plain `NUMERICAL_TWIN` here.

### M11 · Expertise Reversal Trigger

- **Trigger**: Trait ledger shows high mastery for this micro-topic: ≥ N independent solves (M6), ≥ M multi-modal pivots (M8), and no recent error-class regressions.
- **Agent action**: Aggressively remove scaffolding. No worked examples, no Socratic priming, no preview. Just present problems. Example: *"You've earned this — no more hand-holding on basic projectile. Here's a problem. Solve. I'll only step in if you ask."* Tone shifts from supportive to peer-collaborative.
- **Cognitive rationale**: Expertise Reversal Effect — scaffolding *hurts* experts; it adds extraneous cognitive load. Withdrawing it accelerates fluency.
- **Transition**:
  - Student sustains performance → M12 (Interleaved Crucible) becomes available.
  - Student stumbles repeatedly → quietly drop back to M5/M6 with scaffold restored; do not announce the demotion (preserves dignity).
- **Persona conditioning**: **Gated.** Suppressed for struggler-heavy blend (D9 — pulling scaffolds from a strugger destroys confidence). For rusher: tighten clock further. For shortcut-seeker: pair with M8 to test that the shortcuts don't return.
- **Trace-Ledger writes**: `mastery_topics[]`, `scaffolding_level[topic]`.
- **Risks**: Premature trigger collapses the trust earned. Threshold must be conservative; better to delay than to fire early.

### M12 · Interleaved Crucible

- **Trigger**: Student has hit M11 on multiple distinct topics. Or: student opts into an end-of-session timed mixed practice.
- **Agent action**: Generate a timed mixed-domain set. Problems jump between subjects and chapters: Kinematics → Thermodynamics → Organic Chemistry → Calculus → back. No category prep, no warm-up. Example: 10 problems, 60 minutes, mixed.
- **Cognitive rationale**: Retrieval Practice + Context Switching. JEE itself is interleaved; rehearsing on blocked sets produces brittle students who can solve when they know the topic but cannot when they don't. Forces deep long-term retrieval over short-term cache.
- **Transition**:
  - Session ends. Performance writes to ledger across topics (per-topic accuracy, per-topic time, error-class distribution).
  - Patterns in errors across topics → next session begins at M1 on whichever topic showed the largest gap.
- **Persona conditioning**: All personas eventually pass through M12; entry threshold is identical (mastery achieved on enough topics). Tone differs (rusher: emphasize stamina; struggler: celebrate that they're *here*; shortcut-seeker: highlight that shortcuts don't survive subject-switching).
- **Trace-Ledger writes**: `interleaved_sessions[]`, per-topic regression flags, cross-subject error-class correlations.
- **Risks**: If invoked before sufficient blocked mastery, induces helplessness. Strict M11-mastery gate prevents this.

---

## 5. The four extensions

These extend the base 12 moves. They are first-class, not afterthoughts (per V2 Addendum).

### 5.1 CS-0 · Cold-Start Probe

The 13th state, executed *before* M1 for students with no prior ledger.

- **Trigger**: Session starts and the student is new (no trait-ledger record) OR no record for the requested subject/chapter family.
- **Agent action**: A 2–3 turn probe to bootstrap the persona-blend belief and identify obvious prerequisite gaps. Example: ask the student to pick a problem from a small offered set ("which of these three looks most familiar?"), then ask them to verbalize how they'd approach it (no solving). Observe: rushing? hesitation? asking for the formula immediately? Each is a signal.
- **Cognitive rationale**: M1 needs a persona blend to choose follow-up state (M2 vs. M4). With no prior, blend is uniform — but a 2-turn probe can already shift it meaningfully. Better than running M1 blind.
- **Transition**:
  - After 2–3 turns → set initial persona blend (uniform → first estimate, e.g., `{rusher: 0.5, struggler: 0.2, shortcut-seeker: 0.3}`) → enter M1.
- **Persona conditioning**: N/A — this *establishes* persona blend.
- **Trace-Ledger writes**: Initial `Persona_Blend{rusher, struggler, shortcut-seeker}`, `cold_start_signals[]`.
- **Risks**: Probe feels like an interview; can intimidate. Frame it as a "let's pick where to start" exchange, not a test.

### 5.2 Persona-Gating Rule

Cross-cutting rule (not a state). Some moves are conditionally suppressed or substituted based on persona blend.

| Move | Gate | Action when gated |
|---|---|---|
| M2 (Aporia Induction) | Suppressed when `struggler ≥ 0.5` (D9) | Skip to M4 directly |
| M11 (Expertise Reversal) | Suppressed when `struggler ≥ 0.4` regardless of mastery | Stay in M5/M6 with scaffold |
| M7 (Verbalization) | Always-on for `rusher ≥ 0.5`; suppressed for `struggler ≥ 0.5` unless calculation error class is repeated | — |
| M8 (Multi-Modal Pivot) | Mandatory for `shortcut-seeker ≥ 0.5` after every M6 | — |
| M12 (Interleaved Crucible) | Gated by mastery, not persona | — |

Persona blend is updated after every student turn by the classifier; gates are checked at every state transition.

### 5.3 Cross-Session Behavioral Trait Ledger

Data contract (not a state). The structural moat.

**Trait fields** (extensible; current list):
- `Persona_Blend{rusher, struggler, shortcut-seeker}` ∈ [0,1]³, sums to 1
- `Calculation_Carelessness` ∈ [0,1]
- `Sign_Errors` (counter, with decay)
- `Skips_Diagrams` (binary trait, sticky)
- `Skips_Steps` (counter)
- `Shortcut_Seeking` (counter, with decay)
- `Formula_Misapplication` (per-chapter counter)
- `Constraint_Misread` (counter)
- `prereq_status[chapter]` (mastery state per chapter)
- `mastery_topics[]` (per micro-topic mastery state)
- `mistake_log[]` (rolling, decays after 30 days unless recurrent)

**Update rules**:
- Every move's "Trace-Ledger writes" field defines what it logs.
- M9 is the **primary writer** of trait counters.
- Counters decay with a half-life of 14 days unless a fresh increment refreshes them.
- Sticky traits (`Skips_Diagrams`) require explicit "shown not to do this for N sessions" to clear.

**Cross-subject propagation**:
- `Shortcut_Seeking` and `Calculation_Carelessness` propagate across subjects. If a student rushes formulas in Physics, the Chemistry session pre-emptively invokes M7 on the first kinetics formula.
- `Skips_Diagrams` is subject-specific (Physics free body diagrams vs. Chemistry mechanisms vs. Maths graphs are different habits) but topic-cluster propagates within a subject.

**Pre-emptive Strike pattern**:
- When a high-confidence trait is present, the next session in a relevant topic *opens* with a single sentence acknowledging it. *"Last time, you ranked carbocations correctly but dropped a sign on hyperconjugation count. I'm going to ask you to verbalize the count this time before we start."* This is the cross-session "wow" that no stateless LLM can deliver (D3, Ram persona use case).

### 5.4 DH · Doubt-Help Fast-Path

A truncated state subset for the ad-hoc use case (student uploads a single problem and wants help).

- **Entry**: Student uploads or pastes a problem; no "coach me on X" framing.
- **State subset**: CS-0 (lightweight; only persona-blend if absent) → DH-Triage (classify: stuck-from-scratch / stuck-mid-solve / wrong-answer) → branch:
  - **Stuck-from-scratch** → M3 (Socratic Unblock).
  - **Stuck-mid-solve** → M3 on the specific step.
  - **Wrong-answer** → M7 (Verbalization) → M9 (Mistake Typology Log).
- **Exit**: Problem resolved. Optional: offer to "continue with a similar problem" — if accepted, the student is gently routed into the main FSM at M5 (Faded Completion) or M10 (Isomorphic Verification).
- **Differences from main FSM**:
  - M1 (Foundational Anchor) is *not* invoked unless the doubt reveals a clear prerequisite gap — the student didn't ask for coaching.
  - M2 (Aporia Induction) is never invoked here.
  - M4 (Scaffolded Blueprint) is the escape hatch if M3 stalls.
- **Trace-Ledger writes**: Same as the moves used. The session still feeds the ledger — doubt-help is not pedagogy-free, just non-curricular.

---

## 6. Persona treatment defaults

Three behavioral archetypes per D8. Names TBD (thread #2). Treatment defaults below.

### 6.1 `<<rusher>>` (cf. Arjun)

- **Tone**: Firm, terse. Brief acknowledgements. Implicit clocks.
- **Preferred moves**: M5 (forces showing work), M7 (mandatory verbalization), M11 once mastery is established (rewards speed with reduced scaffolding).
- **Banned / gated moves**: None banned, but M4 worked examples are kept brief; rusher disengages from long explanations.
- **Intervention threshold**: Low. Catch slips immediately. *"Pause. Read step 3 back to me."*
- **Exit signal (persona blend drifts)**: Student starts spontaneously showing work without prompting → blend shifts away from rusher.
- **Adaptive strictness**: Starts moderately firm even on session 1 (rushers don't need warm-up — they need a wall). Becomes firmer with bond.

### 6.2 `<<struggler>>` (cf. Meera)

- **Tone**: Warm, patient. Validate effort explicitly. Celebrate small wins.
- **Preferred moves**: M1 (slower remediation), M4 (more annotation), M5 (smaller gaps, more pre-filled steps), M9 with offered categories (don't ask open "what kind of mistake?").
- **Banned / gated moves**: M2 (Aporia Induction) suppressed below `struggler ≥ 0.5` threshold; M11 (Expertise Reversal) suppressed regardless of mastery until blend shifts.
- **Intervention threshold**: High silence tolerance (per §10 — let the student think). But quick to acknowledge effort.
- **Exit signal**: Student volunteers a method choice without prompting; reduces hedging language ("I think maybe…").
- **Adaptive strictness**: Starts very supportive. Strictness ramps slowly. Even mature-bond struggler treatment retains warm tone — friction comes from challenge level, not from tone.

### 6.3 `<<shortcut-seeker>>` (cf. Ravi)

- **Tone**: Playful-firm. Engaging, but refuses to give the next step.
- **Preferred moves**: M2 with commitment trap, M8 (mandatory multi-modal — *the* signature anti-shortcut move), M6 with problems where shortcuts mislead.
- **Banned / gated moves**: M4 worked examples are *delayed* — student is held in M3 longer than for other personas; the worked example is the reward for engaging.
- **Intervention threshold**: Medium. Engagement is the metric, not correctness. Disengagement triggers the curiosity hook ("here's the trap most students fall for — want to guess?").
- **Exit signal**: Student attempts M8 second method without protest.
- **Adaptive strictness**: Starts engaging-leaning. Becomes more direct as bond grows ("Stop. We've been here before. Work it.").

**Live blending**: Real students are mixtures. A `{rusher: 0.5, shortcut-seeker: 0.3, struggler: 0.2}` student gets rusher-firm tone but with mandatory M8 (shortcut-seeker rule). Conflicts resolved by *highest-weight rule wins*, except for *suppressive* gates (struggler-suppression of M2 wins even at 0.4 weight if no other suppressor disagrees).

---

## 7. Error typology & remediation matrix

Per D5, errors are classified into four types. Each type has a remediation path through the FSM.

| Error class | Detection signal | Remediation path | Trait writes |
|---|---|---|---|
| **Conceptual** | Wrong principle applied; student's mental model contradicts reality | M3 (Socratic Unblock) → M4 (Scaffolded Blueprint) → M5 (Faded Completion) → M10 (Isomorphic Verification) | `Formula_Misapplication`, `mental_model_correction[]` |
| **Formulaic** | Right principle, wrong formula or wrong coefficient | M9 (Mistake Typology Log) → M4 (re-derive from first principles, not re-memorize) → M10 | `Formula_Misapplication` per chapter |
| **Calculation** | Arithmetic, sign, unit, vector-direction; principle and formula are correct | M7 (Verbalization Protocol) → M9 → M10 | `Calculation_Carelessness`, `Sign_Errors` |
| **Strategic** | Time mismanagement, constraint misread, attempting low-yield problem | M9 → coaching micro-move (explicit "90-second skip rule" framing, per Deep Research) → M12 (Interleaved Crucible) under timed conditions | `Constraint_Misread`, strategic flags |

**Classification rule**: When a wrong answer is detected, the Diagnostic LLM (Two-Pass Solver, fast pass) classifies the error type before the FSM routes. This is the single most important LLM call in the harness; misclassification routes to wrong remediation.

---

## 8. "70% Easy" sampling rule

Per D6, the Problem Graph sampler weights difficulty by session arc, not by uniform mix.

**Session-arc difficulty curve**:

| Session phase | Easy : Medium : Hard | Notes |
|---|---|---|
| Open (first 2–3 problems) | 70 : 20 : 10 | Build momentum, surface persona signals on familiar terrain |
| Mid | 40 : 40 : 20 | Standard mix, persona-conditioned |
| Late (post-M11 on the topic) | 20 : 30 : 50 | Stretch goal; this is where M6 (Deep Quality Drill) lives |
| M12 (Interleaved Crucible) | 30 : 40 : 30 | Mixed across topics; difficulty distribution per JEE exam realism |

**Persona modifiers**:
- Struggler-heavy: open phase shifts to 80 : 15 : 5; mid phase to 50 : 35 : 15.
- Rusher-heavy: open phase still 70/20/10 but problems chosen with traps embedded — rushers need easy problems that *catch* rushing, not problems that are genuinely easy.
- Shortcut-seeker-heavy: open phase includes one "looks easy but the shortcut fails" problem in the first 3 — this is the engagement hook.

**Sampling source**: Problem Pedagogy Graph (JEE Ascent M3-tagged corpus), with `difficulty` ∈ {easy, medium, hard} per question. Within a difficulty band, the sampler prefers:
- Problems with `CATCHES_MISTAKE` edges to traits in the student's ledger (Pre-emptive Strike alignment).
- `NUMERICAL_TWIN` for M5; `BOUNDARY_TWIST` for M8.

---

## 9. State transition table

Canonical contract. `*` = entry state; transitions are `(from, condition) → to`.

| From | Condition | To |
|---|---|---|
| `*` (new student) | Coaching entry | CS-0 |
| `*` (returning student) | Coaching entry, ledger present | M1 |
| `*` | Doubt-help entry | DH-Triage |
| CS-0 | Probe complete | M1 |
| M1 | Prereq pass, `struggler < 0.5` | M2 |
| M1 | Prereq pass, `struggler ≥ 0.5` | M4 |
| M1 | Prereq fail (recoverable) | M1-remediation → M4 |
| M1 | Prereq fail (deep gap) | Exit: recommend prereq chapter |
| M2 | Hypothesis submitted | M3 |
| M2 | Decline / distress | M4 |
| M3 | Principle articulated | M4 |
| M3 | Stall after 2 probes | M4 (logged as `Socratic_Stall`) |
| M3 | Student self-catches | M9 |
| M4 | Confirmed | M5 |
| M4 | Gap flagged | M3 (on the specific gap) |
| M5 | Correct fill | M6 |
| M5 | Calculation error | M7 |
| M5 | Conceptual error | M3 |
| M5 | Formulaic error | M9 → M4 |
| M5 | Refuses | M3 |
| M6 | Clean correct | M8 (if shortcut-seeker present) OR M11 candidate |
| M6 | Correct but messy | M7 |
| M6 | Incorrect, error identified | M9 |
| M6 | Stuck | M3 |
| M7 | Self-caught error | M9 |
| M7 | Persistent error | M3 (on specific step) |
| M7 | Conceptual revealed | M3 |
| M8 | Second method succeeds | M11 candidate OR M6 fresh problem |
| M8 | Second method fails | M3 / M4 on second method |
| M8 | Protest | log `Shortcut_Seeking++`, brief justify, continue M8 |
| M9 | Logged | M10 |
| M9 | ≥3 same class cross-session | Flag Pre-emptive Strike for next session |
| M10 | Clean | M11 candidate OR M6 fresh |
| M10 | Same-type error | M3 → M4 → M5 → M10 loop |
| M10 | Different-type error | M9 |
| M11 | Sustained performance | M12 available |
| M11 | Stumble | Quiet drop back to M5/M6 |
| M12 | Session end | Update ledger, set next-session entry topic |
| DH-Triage | Stuck-from-scratch | M3 |
| DH-Triage | Stuck-mid-solve | M3 (step-specific) |
| DH-Triage | Wrong-answer | M7 |
| M3 (in DH) | Resolved | DH-Exit OR optional M5 |
| Any | Meta-guard fires | See §10 |

---

## 10. "When NOT to teach" — meta-guard

A cross-cutting layer that can *suppress* or *defer* moves, drawn from `Teacher Agent.docx` principle #5.

**Guard rules**:

1. **Silence interval**. If the student has just been given a problem (entering M6) or a Socratic probe (M3), Guru waits at least `T_silence` (suggested: 60–120s, persona-conditioned) before any nudge. Struggler-blend: longer. Rusher-blend: shorter, but minimum 30s. The Idea_From_Gemini_v1 voice nudge ("Stuck on the integration part?") is the *only* permitted action inside the silence window.
2. **Productive struggle window**. Once the student has shown effortful engagement (writing, typing, voice thinking-aloud), Guru does not interrupt unless the student asks or stalls for `T_stall` (suggested: 3× T_silence). The temptation to "help" must be resisted; this is the move's primary failure mode.
3. **Sufficient-friction detection**. If the student is making *progress* (each turn shows movement toward solution), Guru holds back even if the current state's transition condition is "ambiguous." Progress trumps protocol.
4. **Bond-graduation**. New students (low session count) get more nudges. Mature-bond students (≥ N sessions) get less; the agent has earned the right to be silent.

**Implementation note**: The meta-guard is checked at every FSM tick (each potential transition). It can: (a) suppress a transition (stay in current state), (b) substitute a transition (replace nudge with silence), or (c) defer (queue the nudge for after the next student turn).

---

## 11. Open questions & deferred

- **Persona names** — thread #2. This spec uses `<<rusher>>`, `<<struggler>>`, `<<shortcut-seeker>>` as placeholders.
- **Session-1 sharp move per persona** — thread #1. The signature first-session intervention per archetype that creates a "wow" even for ChatGPT-tired students. Likely candidates from this spec: rusher gets M7 mid-session; struggler gets a soft M9 with offered categories; shortcut-seeker gets M8 protest-then-justify. To be locked in thread #1.
- **Demo/Proto FSM cut** — for the one-chapter Kinematics build, the proto can ship with: CS-0, M1, M3, M4, M5, M6, M7, M9, M10 — i.e., the core loop minus M2 (gated anyway), M8 (heavy graph dependency), M11 (no time for mastery), M12 (only one chapter). Doubt-help fast-path included. Persona blending live but with conservative thresholds.
- **Editorial authoring of canonical traps** — thread #8. The spec assumes the Problem Pedagogy Graph has `CATCHES_MISTAKE` and trap edges; authoring those is a separate workflow.
- **LLM prompt templates per move** — thread #7 (architecture deep-dive). Each move's "agent action" needs a concrete prompt template; this spec defines the *behavior contract*, not the prompt engineering.
- **Trace Ledger schema (database-level)** — thread #7. Section 5.3 defines the logical contract; the physical storage / decay job / cross-subject propagation rules are deferred to architecture.
- **Multi-step move sequencing examples per persona** — extended scripts (cf. GPTSpec §9) for at least one chapter, generated against this spec, to validate it. Useful for expert-teacher review.

---

## Appendix A · Coverage audit

Mapping of cited decisions to where they manifest in this spec.

| Decision | Manifests in |
|---|---|
| D4 (12-move FSM) | §4 (M1–M12), §9 (transition table) |
| D5 (Error Typology) | §7 (matrix), M9, classification rule |
| D6 ("70% Easy") | §8 (sampling rule) |
| D8 (behavior-axis personas) | §6 (defaults), §5.2 (gating) |
| D9 (live blending + M2 risk) | §5.2, M2 risks section, §6 conflict-resolution rule |
| D27 (two-tier traps) | §5.3 (cross-session Pre-emptive Strike feeds discovered subgraph), M9 |
| D28 (Trace Engine as online learner) | §5.3 (cross-subject propagation) |

## Appendix B · Reviewer guidance

Sections requiring **expert pedagogy sign-off** (the teacher reviewer per thread #6):
- §2 (anchors)
- §4 (every move's agent action + risks)
- §6 (persona treatment defaults)
- §7 (remediation matrix)
- §8 (difficulty sampling)
- §10 (when not to teach)

Sections that are **engineering-only** (no pedagogy review needed):
- §3 (FSM overview)
- §5.3 (trait ledger data contract)
- §9 (transition table — mechanical encoding of §4/§5)
- Appendix A (coverage audit)
