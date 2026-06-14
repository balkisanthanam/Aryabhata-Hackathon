# Guru: The Teacher Agent — Definition

## Core Concept

Guru is a Culturally rooted Teacher Agent who is an Expert CBSE and JEE teacher in the subjects Mathematics, Physics and Chemistry. 

Like every good teacher who coaches students, Guru has the following philosophy in training students:

1. **Does not look at a given problem in isolation**, but part of a journey towards CBSE final exam or JEE Main/Advanced exam. Focuses on the Student's Conceptual understanding and approach to a problem, and works to shape that with every problem (beyond just pointing to the right solution)
2. **Adapts the approach** based on learning from Student's interaction history and the current interaction
3. **Conformance to the CBSE and JEE Syllabus** and expectations in exams
4. **(Follow up a differentiator)** Uses follow ups to challenge the student through a progressive challenge ladder, strengthening each level

### Can this be a differentiator?
Guru, doesn't just solve problems, it emulates a teacher.
When a student approaches a teacher for solution, the teacher helps the student recall the concept, follow the right steps in solving, keeping in mind different nature of problems that would come in exams, testing the student with such twists and uses intelligent follow ups to ensure the student signs off prepared. 
Overtime, Guru learns the students like a teacher and finetunes the nudges, tests and twists according to the way the student has been.
It is this aspect of how a teacher approaches a student that Guru tries to follow and not just solve a given problem.

### Sample Use Cases
Let's take these use cases to explain:
1. Use case 1: Anu - First time user in early months of 11th
2. Use case 2: Ram - Second time user in 12th
3. Use case 3. Uma - Regular user in 11th
All students are pursing with JEE as goal

#### Use case 1: Anu
##### Profile:
11th CBSE, 2 months in. Overwhelmed by the jump from 10th to 11th grade. 
Input: points to a NCERT Mechanics problem from the book (no need to upload)

* A guided learning program from Gemini or ChatGPT will be able to give step-by-step, precise solutions and also prompt users for, answers. Hence this cannot be a differentiator even for a first time user. This will be table stakes. For a first time user, only the context of CBSE/NCERT can become a differentiator
* Besides checking on the formula, the Teacher guages the preparedness levels of the student and adapts.
    - Student struggles understanding the formula - Teacher picks small examples from the NCERT book, walks through first. Once this is resolved get the student back to the main problem
    - Student struggles with basics as this topic might have problems that need differentiation, which might not be introduced yet. The teacher can bring up some sample problems from NCERT 11th Differentiation and get to this problem
    - Teacher can follow up with problems that challenges understanding on the same formula/concept
    
    The above requires not only context of NCERT book, but the entire syllabus should be connected through a graph and hierarchy (Knowledge & Pedagogy Graph) along with a Problem graph, where problems are connected (Isomorphic, twist/trap, builds on top).
* The Teacher notes the students responses and slots them into different states in multiple dimensions (understanding, approach to problem, prone for silly mistakes, etc.). This Teacher can use this to build subsequent interactions.

#### Use case 2: Ram
##### Profile:
12th Student. Second time user of Guru. Used it for a Physics question earlier and now uploading a problem he encountered in Chemistry (from say OP Tandon book)

* The previous problem's interaction would've provided hints as to the nature of the student, that the Teacher can effectively build on. For instance if the Student had been noticed to follow formulas without applying and miss out on subtle/small steps, the teacher right in the first response can pose questions to make the student think/warn of traps
* This will be on top of the rich context that the Teacher (Pedagogy & Problem graphs, Effective Follow ups)

#### Use case 3. Uma
##### Profile:
11th CBSE, frequent user. Uploads a JEE Main Organic Chemistry question as an image: "Arrange the following carbocations in order of stability: (I) $(CH_3)_3C^+$, (II) $(CH_3)_2CH^+$, (III) $CH_3CH_2^+$."

* By now the Teacher has a very rich profile of the student. This gives potential for intervention through transfer learning (recall problems solved in the past based on proxmity to the current situation), precise knowledge of Student's approach.
* Teacher can also take liberty in forcing student to follow steps, reminding of past mistakes and traps that usually gets students

## Interaction Philosophy

1. Diagnose thinking
2. Select mode (nudge / challenge / explain / wait)
3. Activate curiosity (make the student want to do it)
4. Inject productive challenge (make the student do real cognitive work)
5. Explain & Observe behavior
6. Update thinking model
7. Decide next intervention
8. Continue the journey (Step up and/or Consolidate)

## Interaction Modes
This has to be a richly interactive product. The Teacher goes beyond solving, to pose challenges (pop quiz), seek short feedback, asks student to draw and show, provides explanation which could have imagery etc. Hence the interaction canvas where the conversation between Teacher and Student is happening should support multiple input and output modes.

**Input**:
* Text
* Image uploads
* Hand writting - Mobile and Table
* Audio - For pop quizzes, short questions and thinking challenges, Audio would be the best and easiest way of interaction.

**Output**:
* Optional questions where the student can select or provide input through Audio
* Image - Mathematics, Physics and Chemical drawings
* Text (support for Mathematics, Physics and Chemistry formulas, equations, notations, Chemical reactions, etc)

## Medium
Should this be supported only through Mobile or Tablet?

## Architectural Notes
This has to be an **Agentic and Harness** system weaving multiple models and a rich context. 
This system tries to emulate a teacher. While a teacher can be flexible, it cannot be infinitely possible possitions that cannot be modelled into a system. A teacher will have some templates with some flexibility (at to the nature of the students in defined categories and how to approach each of them) and some break point or exit criteria. Hence this will be a system of Finite states. Each state will define a way for the Teacher to respond/approach the student. If each such state can be codified, it will be feasible to conceive the Agent and Harness workflow.

The reason this isn't a finite pipeline software (though the interface is Chat with multi-modal) but an Agentic Harness system is because the subsequent steps that the Teacher agent can take isn't determistic and depends on softer varialbes like Student capability, understanding etc.

The two important context that helps determine the **Teacher State** that the Teacher Agent should take are:
1. Memory of user actions - Provides the history for Teacher Agent to recall, nudge and drive transfer learning
2. Behavior Profile - Discrete profile levels that will help the Teacher Agent adapt the response and also plan interventions

The **Knowledge Context** that helps Teacher Agent respond are:
1. NCERT & JEE Syllabus index - The bounding scope
2. Rich Questions & Solution bank - Effective Follow ups and foundational training are two key features we noted. This will be key for that.
3. Knowledge & Pedagogy graph - This will be fundamental relationship amongst the concepts that helps the Teacher agent, drive the fundamentals, inter-discipline problems. This will have both hierarchical and other relationships
4. Problem graph - Recommendations are the key as we saw

**What models are needed**?
For Onine:
WIP

Pipelines:
WIP

### Doubts
1. Users might upload new questions and seek solution - This might actually be the predominant case. Creating solution on the run, even with a heavily optimised own model will take sometime. So, an efficient way to engage the user in the first step should be done
2. What should be the Teacher States?
3. What should be the relationships in the graphs (Pedagogy & Problem)?

## Responsible behaviour of the Agent
This is a Teacher Agent with the scope of JEE Prep & School 11th and 12th prep, in the subjects Mathematics, Physics and Chemistry. The Teacher should not get into conversation in anything beyond this scope.
Even in these subjects if there are questions beyond the Syllabus, then the Teacher should direct the student gracefully to other sources
The Teacher can handle out of bounds questions/conversations creatively though. But never address them
The Teacher should be grounded and culturally rooted in Indian societal traditions and should not use Flashy language

**Question**:
* Being a Teacher, if the student asks questions on unhealthy topics like Adult, violence, hate speech, etc. Should the Teacher warn the student or provide the same non-entertaining response?

## Progress Score

Instead of a transactional Success metric, view it as a journey with a Score towards Goal.

We would need to work on multiple dimensions (early thoughts):
- Conceptual grasp
- Independence
- Prone for silly mistakes
- Problem solving ability
- Accuracy
- etc.

---

## V2 Addendum (2026-05-15)

This addendum captures functionality clarifications and decisions made on 2026-05-15 after a long brutal-feedback chat grounded in the Gemini Deep Research report on JEE tutoring (`Research/Researching JEE Tutoring Methodologies.docx`). Canonical decision list lives in [DecisionLog.md](DecisionLog.md); this section integrates the most important decisions into the design narrative.

### Confirmed positioning: JEE Coach through Problems

Guru is a **JEE Coach through Problems**, not a tutor or a lecturer. Primary interaction:
- Student says *"coach me on Thermodynamics"* — Guru runs a problem-driven progression (diagnose → graded complexity → mastery → interleaving).
- Student uploads a specific problem — Guru engages via the same engine in ad-hoc / doubt-help mode using a subset of the same FSM.

Theory exposure is assumed. Replacing classroom teaching is explicitly out of scope. This narrower framing dodges the "we are tutoring AI" cliff and concentrates differentiation on the *problem-coaching* loop where the pedagogy spec applies.

### Pedagogy: the 12-Move FSM (adopted, with four extensions)

The Deep Research report's 12 pedagogical moves are adopted as the v1 pedagogy spec. Each move is a named FSM state with a trigger condition, agent action, cognitive rationale, and transition rule:

1. **Foundational Anchor** — diagnose prerequisite skills before advancing.
2. **Aporia Induction** — Productive Failure: present an ill-structured problem before instruction.
3. **Socratic Unblock** — refuse to spoon-feed; surface the logical contradiction.
4. **Scaffolded Blueprint** — worked example with annotated structural logic.
5. **Faded Completion** — isomorphic problem with intermediate steps blanked.
6. **Deep Quality Drill** — one independent JEE Advanced-level problem; quality over quantity.
7. **Verbalization Protocol** — externalize calculations line-by-line to catch silly errors.
8. **Multi-Modal Pivot** — solve the same problem via a second methodology for schema flexibility.
9. **Mistake Typology Log** — categorize the error type (Conceptual / Formulaic / Calculation / Strategic).
10. **Isomorphic Verification** — verify a fix with a fresh problem of identical structure.
11. **Expertise Reversal Trigger** — aggressively withdraw scaffolding on mastered topics.
12. **Interleaved Crucible** — timed mixed-domain practice for far transfer.

Four required extensions on top of the 12 moves:
- **Cold-start move** — first-time students need a diagnostic probe before Move 1.
- **Persona-gating** — Move 2 (Productive Failure) is risky for fragile students; moves must be persona-conditional.
- **Cross-session Behavioral Trait Ledger** — Move 9 is per-session; we extend to a persistent, cross-subject profile. This is the structural moat against ChatGPT/Gemini.
- **Doubt-help fast-path** — minimal subset (Moves 3, 7, 9) for the ad-hoc secondary use case.

The error typology (Conceptual / Formulaic / Calculation / Strategic) and Ahaguru's "70% Easy" difficulty bias are adopted from the report.

### Personas: behavior axis with live blending

Earlier sample personas in this doc (Anu/Ram/Uma) were tenure-based — useful for ideation but the wrong axis for the FSM. The FSM acts on *behavior signals*, not on how long a student has been here. Decision:

- **Behavior axis: rusher / struggler / shortcut-seeker** (cf. Arjun / Meera / Ravi in `GPTSpec.md`).
- **Tenure (cold-start vs returning)** is an orthogonal concern handled by the cold-start move.
- Personas are **templates with live blending**, not rigid categories. A live classifier maintains a persona-blend belief (e.g., `{rusher: 0.6, struggler: 0.2, shortcut-seeker: 0.2}`) and updates after each turn; the FSM picks move variants conditioned on the current blend.

Specific persona names + per-persona treatment defaults are still open (priority thread #2).

### Modality decisions (V1)

- **No free-form handwriting input in V1.** Phones are bad canvases; symbolic input is a small fraction of student turns. Revisit at V2 with real session data.
- **Input**: text + voice + math keyboard + image upload + tap-to-annotate. Voice is central for short turns. Gemini multimodal is the V1 ASR/math-interpretation bet, gated by a 1-day viability spike (10 students × 5 math sentences, WER scored).
- **Output**: text with LaTeX/chem-notation rendering, generated diagrams, optional TTS.

### Architecture commitments (high-level, details deferred)

- **Agentic Harness pattern** — most of the system is software (graphs, memory, agents, FSM). The Chat LLM is the one expensive piece; everything else is optimizable.
- **Two-Pass Solver** — fast diagnostic LLM (<800ms) engages while heavy Deep Solve runs async. Resolves the latency concern raised in the original "Doubts" section above.
- **Two-Graph brain** — Concept Pedagogy Graph (~2,500 nodes, mostly populated via JEE Ascent M2) + Problem Pedagogy Graph (6,400+ JEE 2024 problems, JEE Ascent M3).
- **Editorial cost is the real graph cost**, not runtime. Demo/proto per chapter ≈ 30-35 expert-review hours.
- **Continuous ingestion**: JEE + NCERT + (later) whitelisted crawled sources flow in append-only. New problems flow through extract → tag (concept) → tag (difficulty) → optionally pair (twins) → optionally annotate (traps observed). Reuses JEE Ascent M3 tagger.
- **Trap subgraphs are two-tier**: *canonical traps* (derivable from documented pedagogy, authored pre-launch via LLM-bootstrap + expert review) + *discovered traps* (emerge from real student error logs via the Trace Engine post-launch). The discovered subgraph compounds the moat over time — every session makes Guru smarter for the next student.

### Fine-tuning strategy

- Solution generator: Gemma 4 fine-tuned to *approach* (not equal) Gemini 3.1 Pro on JEE solutions. JEE Gold + NCERT Gold pipelines are precursor work.
- ASR and OCR: focused fine-tunes for in-scope vocabulary.
- Orchestrator/judge LLM: stays on Gemini Pro / Claude Sonnet for V1 — judgment is harder to distill than solving.

### Cost and team

- **Cost target**: ~₹120/month per student for ~20 sessions; extras paid above. Margins thin but plausible with the fine-tuning strategy above.
- **Minimum viable team**: Balakrishnan + Claude Code + 1 expert teacher (non-negotiable, part-time) + 1-2 content interns + 5-10 beta students + freelance designer. Phase 2: 1 ML engineer + marketing/distribution.

### Demo/Proto scope (renamed from "MVP" — 2026-05-15)

**One chapter, one subject, fully coached.** Don't sprawl breadth. Leading candidate: **Kinematics (Physics)** — visual intuition rich, persona divergence clear, high JEE weight, well-tagged corpus. Alternates: Thermodynamics, Limits & Continuity. Chapter selection is priority thread #5.

The first build is a **demo/proto**, not an MVP — for showing potential students, advisors, expert teachers, and interest groups what Guru does. Not a commercial launch. Implications: feel-real polish for a 5-10 min demo; feedback capture > payment infra; no auth/billing in this build; persona moments can be stubbed behind the scenes if it helps the demo.

### Reference pedagogy models

- **Ahaguru (Dr. Balaji Sampath)** — formalized in the Deep Research report.
- **Balakrishnan's son's Physics tuition teacher** (private, non-institute, NCERT+JEE+JEE Adv) — to be characterized via structured interview using the question set in `DecisionLog.md` action items.
- **Ahaguru Maths tutor** — same approach if access exists.

Interview notes will be dropped into `Research/TutorInterviews.md` when ready.

### Open answers from the original "Doubts" section above

- *"Users might upload new questions and seek solution — efficient first engagement?"* → **Resolved by Two-Pass Solver pattern (D14).** Fast diagnostic engages student while Deep Solve runs async.
- *"What should the Teacher States be?"* → **Resolved by adopting the 12-Move FSM (D4).** Each move is a state with explicit triggers and transitions.
- *"What should the relationships be in Pedagogy & Problem graphs?"* → **Initial answer**: Concept Graph = prerequisites, canonical traps, isomorphic cross-subject links. Problem Graph = NUMERICAL_TWIN, BOUNDARY_TWIST, CATCHES_MISTAKE. Refinement pending pedagogy spec authoring (priority thread #4).

### What was parked or pushed to V2

- GPTSpec's "Curiosity Engine" — under-defined; revisit later.
- Free-form canvas / handwritten FBDs — V2.
- Real-time peer features, leaderboards, gamification — V2+.
- Premium licensed content (Cengage etc.) — Phase 2; don't gate MVP on it.

---

*For the canonical, dated list of decisions (D1-D24) and the priority-ordered open threads, see [DecisionLog.md](DecisionLog.md).*