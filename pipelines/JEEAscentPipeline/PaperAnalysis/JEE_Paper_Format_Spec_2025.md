# JEE Main Paper Format Specification

Based on the analysis of the provided 2025 Question Paper and Answer Key PDFs, here is the structured specification document.

## Answer Key Format (by year)

**2025 Answer Key Findings:**
1. **CORRECT OPTION ID format:** (c) A long NTA numeric ID (variable length, typically 9 to 10 digits). 
   *Example from PDF:* "7364751501 → 7364755104" or "65644576 → 656445257"
2. **Integer-type answer format:** For Section B (numerical value) questions, the correct answer is presented as a **plain number**.
   *Example from PDF:* "7364751521 → 1613" or "7364751522 → 5"
3. **Page layout:** Each page features a header identifying the Exam Date and Shift. Below the header, the data is organized into **3 major columns of Q-A pairs per page**, corresponding to "(Mathematics)", "(Physics)", and "(Chemistry)". 
4. **Page 1 anomaly:** Page 1 **does contain actual Q-A pairs**. It serves as the key for the "22.01.2025 First Shift" paper and must not be skipped.
5. **Q ID digit count:** 2025 AK: **Variable length**. Some sessions use 8-digit Question IDs and 9-digit Option IDs (e.g., QID: `65644576`, OID: `656445257`), while others use 10-digit IDs for both (e.g., QID: `7364751501`, OID: `7364755104`).
6. **Session coverage:** One AK PDF covers **all dates and shifts** for a session, including a separate section appended at the end for "Centers Outside India".

## Question Paper — Bilingual Structure
7. **Is the paper bilingual?** Yes. The provided 2025 Question Paper PDF contains both English and Hindi versions of each question.
8. **If bilingual — layout:** (b) English and Hindi versions of the SAME question are adjacent. The English version of the question and its options are printed first, immediately followed by the Hindi translation of that specific question and its options.
9. **Same NTA Question ID for both languages?** **Yes.** Both the English and Hindi occurrences of the question show the exact same NTA Question ID and share the exact same Option IDs.
10. **Distinguishing marker:** There is no broad "Hindi Section" header. The start of the Hindi translation is marked simply by a repetition of the metadata block (e.g., `Question Number: 1 Question Id: 7364751501 Question Type: MCQ...`) directly below the English options.

## Question Paper — Options and IDs
11. **Option IDs printed on paper:** Yes, an NTA numeric ID is printed next to every option for ALL MCQ questions.
    *Example:* `7364755101. स्वतुल्य और संक्रामक है, परन्तु सममित नहीं है`
12. **Option labeling style:** Options are **not** labeled with traditional (A)(B)(C)(D) or (1)(2)(3)(4) markers. The Option ID itself, followed by a period, acts as the label for the option.
13. **Integer-type question layout:** For Section B, there are no options printed. The NTA Question ID is printed in the metadata header exactly like an MCQ. At the bottom of the question, there is placeholder text: `Response Type: Numeric` and `Possible Answers: 1`. 

## Question Paper — Layout
14. **Column count:** The provided digital response sheet PDF uses a **1-column (single column) layout**, reading continuously top-to-bottom.
15. **Section headers:** Subject and section boundaries are marked with explicit plain-text headers. 
    *Exact text used:* "Mathematics Section A", "Mathematics Section B", "Physics Section A", "Physics Section B", "Chemistry Section A", "Chemistry Section B".
16. **Question count per subject (MAJOR CHANGE):** Unlike previous years, the 2025 paper contains **25 questions per subject** (20 MCQ in Section A, and **only 5 Integer in Section B**). The metadata explicitly states: `Number of Questions: 5` and `Number of Questions to be attempted : 5` for Section B.
17. **Question numbering:** Questions are numbered **continuously from 1 to 75** across all subjects (Mathematics 1–25, Physics 26–50, Chemistry 51–75).

## Figures and Diagrams
18. **Frequency:** - Physics: ~30% of questions contain diagrams.
    - Chemistry: ~20% contain structural formulas, plots, or reaction schemes.
    - Mathematics: ~0% (No diagrams observed in the sampled math section).
19. **Column behavior:** Because it is a single-column layout, figures appear completely inline between the question text and the options.
20. **Figure types by subject:** - Physics: Rectangular plates (center of mass), circular hoops with springs, vector diagrams, and resistor circuits.
21. **Structural chemistry:** Complex organic structures (e.g., Carbocations with phenyl rings, structural reaction pathways) are embedded as actual drawn images, not text-based representations.
22. **Figure self-sufficiency:** (c) No — figure is essential. Questions heavily rely on phrases like "(fig - x)", "as shown in figure", or "following circuit" making the visual geometry critical to solving the problem.

## Mathematical Notation
23. **Rendering quality:** Mathematical expressions are rendered natively as **typeset math** (extractable as LaTeX/Unicode strings), not embedded as unreadable images.
24. **Chemical equations:** Chemical equations and equilibrium states are typeset natively using Unicode/LaTeX formatting (e.g., $CH_{4(\mathfrak{g})}+2O_{2(\mathfrak{g})}$).
25. **Special symbols:** Your parser must be robust enough to handle piecewise function bounds (`\begin{cases}`), summations (`\sum_{k=1}^{81}`), matrices, integrals with limits (`\int_{-\frac{\pi}{2}}^{\frac{\pi}{2}}`), and vector arrows (`\vec{a}`).

## Year-by-Year Variations
26. *Compared to the 2024 format:*
    - **Total Question Count:** 2025 dropped the total questions per subject from 30 down to 25. Section B now only contains 5 questions, all of which are mandatory.
    - **Total Numbering:** The paper runs continuously from 1 to 75 (instead of 1 to 90).
    - **ID Length:** 2025 introduces variable-length IDs. Depending on the shift, you may encounter 8-digit, 9-digit, or 10-digit IDs, unlike the strict 11/12-digit format of 2024. 

---

## Critical Flags for Extraction Pipeline

1. **The 25-Question Paradigm Shift:** Hardcoded loops or array splits that assume 30 questions per subject or 90 questions total will break catastrophically on the 2025 papers. The pipeline must dynamically adapt to 20 MCQs and 5 Integer questions per subject.
2. **Variable ID Length Regex:** Do not use strict lengths like `^\d{11}$` or `^\d{12}\.$` for capturing IDs. Your regex must be flexible, such as `^\d{8,12}$` for Question IDs and `^\d{8,12}\.\s` for splitting MCQ options.
3. **Bilingual ID Duplication Trap:** Just like 2024, the English and Hindi versions of the questions are adjacent and use the *exact same Question ID and Option IDs*. The pipeline must prevent "Duplicate ID" DB collisions by using composite keys or merging localization data.
4. **Section B Placeholder Trap:** Every numerical question ends with `Possible Answers: 1`. This system placeholder from the testing engine must be explicitly filtered out to avoid corrupting the extracted correct answers.
