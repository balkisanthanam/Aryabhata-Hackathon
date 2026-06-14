# JEE Main Paper Format Specification

Based on the analysis of the provided 2024 Question Paper and Answer Key PDFs, here is the structured specification document.

## Answer Key Format (by year)

**2024 Answer Key Findings:**
1. **CORRECT OPTION ID format:** (c) A long NTA numeric ID (12 digits). 
   *Example from PDF:* "QUESTION ID: 87827055428 → CORRECT OPTION ID: 878270218242"
2. **Integer-type answer format:** For Section B (numerical value) questions, the correct answer is presented as a **plain number**.
   *Example from PDF:* "87827055448 → 45"
3. **Page layout:** Each page features a header identifying the Exam Shift and Date. Below the header, the data is organized into **3 major columns of Q-A pairs per page**, corresponding to "(Mathematics)", "(Physics)", and "(Chemistry)". 
4. **Page 1 anomaly:** Page 1 **does contain actual Q-A pairs**. It serves as the key for the "04.04.2024 First Shift" paper and must not be skipped.
5. **Q ID digit count:** 2024 AK: **11-digit** Question IDs and **12-digit** Option IDs.
6. **Session coverage:** One AK PDF covers **all dates and shifts** for a session. For example, Page 1 covers April 4 Shift 1, Page 2 covers April 4 Shift 2, Page 3 covers April 5 Shift 1, and so on.

## Question Paper — Bilingual Structure
7. **Is the paper bilingual?** Yes. The provided 2024 Question Paper PDF contains both English and Hindi versions of each question.
8. **If bilingual — layout:** (b) English and Hindi versions of the SAME question are adjacent. The English version of the question and its options are printed first, immediately followed by the Hindi translation of that specific question and its options.
9. **Same NTA Question ID for both languages?** **Yes.** Both the English and Hindi occurrences of the question show the exact same 11-digit NTA Question ID and share the exact same 12-digit Option IDs.
10. **Distinguishing marker:** There is no broad "Hindi Section" header. The start of the Hindi translation is marked simply by a repetition of the metadata block (e.g., `Question Number: 1 Question Id: 87827056058 Question Type: MCQ...`) directly below the English options.

## Question Paper — Options and IDs
11. **Option IDs printed on paper:** Yes, a 12-digit NTA numeric ID is printed next to every option for ALL MCQ questions.
    *Example:* `878270220131. एक तुल्यता संबंध है।`
12. **Option labeling style:** Options are **not** labeled with traditional (A)(B)(C)(D) or (1)(2)(3)(4) markers. The 12-digit Option ID itself acts as the label/bullet point for the option.
13. **Integer-type question layout:** For Section B, there are no options printed. The 11-digit NTA Question ID is printed in the metadata header exactly like an MCQ. At the bottom of the question, there is placeholder text: `Response Type: Numeric` and `Possible Answers: 1`. 

## Question Paper — Layout
14. **Column count:** The provided digital response sheet PDF uses a **1-column (single column) layout**, reading continuously top-to-bottom.
15. **Section headers:** Subject and section boundaries are marked with explicit plain-text headers. 
    *Exact text used:* "Mathematics Section A", "Mathematics Section B", "Physics Section A", "Physics Section B", "Chemistry Section A".
16. **Question count per subject:** Consistently **30 questions per subject** (20 MCQ in Section A, 10 Integer in Section B).
17. **Question numbering:** Questions are numbered **continuously from 1 to 90** across all subjects (e.g., Mathematics 1–30, Physics 31–60, Chemistry 61–90).

## Figures and Diagrams
18. **Frequency:** - Physics: ~20-25% of questions contain diagrams.
    - Chemistry: ~20-30% contain structural formulas, plots, or setups.
    - Mathematics: ~0% (No diagrams observed in the sampled math section).
19. **Column behavior:** Because it is a single-column layout, figures appear completely inline between the question text and the options.
20. **Figure types by subject:** - Physics: Inclined planes with blocks/springs, lens combinations, fluid containers (ice in water/kerosene), and electrical circuits (Zener diodes, heaters).
21. **Structural chemistry:** Complex organic and inorganic structures are embedded as actual drawn images, not text-based representations.
22. **Figure self-sufficiency:** (c) No — figure is essential. Questions heavily rely on phrases like "as shown in the figure above" or "A circular table is rotating... (see figure)", making the visual geometry critical to solving the problem.

## Mathematical Notation
23. **Rendering quality:** Mathematical expressions are rendered natively as **typeset math** (extractable as LaTeX/Unicode strings), not embedded as unreadable images.
24. **Chemical equations:** Chemical equations and equilibrium states are typeset natively using Unicode/LaTeX formatting (e.g., $Cr_{2}O_{7}^{2-}\rightleftharpoons2CrO_{4}^{2-}$).
25. **Special symbols:** Your parser must be robust enough to handle piecewise function bounds (`\begin{cases}`), matrices/determinants (`\begin{matrix}`), equilibrium arrows (`\rightleftharpoons`), limit operators (`lim_{x\rightarrow0^{+}}`), and vector hats/arrows (`\hat{i}`, `\vec{a}`).

## Year-by-Year Variations
26. *Compared to the 2021 format:*
    - **ID Length:** 2024 uses 11-digit Question IDs and 12-digit Option IDs (whereas 2021 used 11 digits for both).
    - **Bilingual Grouping:** 2024 interleaves English and Hindi sequentially on the same page using the *same* Question ID. (In 2021, different languages were entirely different papers with unique Question IDs).
    - **AK Scope:** The 2024 Answer Key aggregates all dates and shifts for a session into a single PDF, whereas older formats sometimes split them.
    - **Section B Placeholder:** The dummy text at the bottom of Section B questions in 2024 is `Possible Answers: 1` (as opposed to the `5 to 5.001` trap seen in 2021).

---

## Critical Flags for Extraction Pipeline

1. **Bilingual ID Duplication Trap:** Because the English and Hindi versions of the questions are adjacent and use the *exact same Question ID and Option IDs*, a naive parser will throw "Duplicate ID" errors or overwrite the English text with the Hindi text. Your database schema must either support a `language` composite key or merge the localized texts into a single JSON object for that Question ID.
2. **Section B Placeholder Trap:** Every numerical question ends with `Possible Answers: 1`. This is a system placeholder from the testing engine. **It must be explicitly regex-filtered out**, or your pipeline will erroneously log "1" as the answer to every Section B question.
3. **ID Length Mismatch:** Do not use a fixed 11-digit regex for all IDs in 2024. Your parser must look for 11 digits for Question IDs (`^\d{11}$`) and 12 digits for Option IDs (`^\d{12}\.$`).
4. **Header-Based Subject Mapping:** Questions do not inherently state their subject in the text. The pipeline must listen for the "Physics Section A" strings and set a stateful variable (`current_subject = "Physics"`) to properly categorize the subsequent 30 questions.
