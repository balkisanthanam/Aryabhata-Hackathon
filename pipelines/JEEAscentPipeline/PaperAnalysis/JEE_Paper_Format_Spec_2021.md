# JEE Main Paper Format Specification

Based on the analysis of the provided 2021 Question Paper and Answer Key PDFs, here is the structured specification document. 

## Answer Key Format (by year)

**2021 Answer Key Findings:**
1. **CORRECT OPTION ID format:** (c) A long NTA numeric ID (11 digits).
   *Example from PDF:* "QuestionID: 70819115154 → CorrectOptionID: 70819150613"
2. **Integer-type answer format:** For Section B (numerical value) questions, the correct answer is presented as a **plain number**, not an NTA ID.
   *Example from PDF:* "QuestionID: 70819115174 → CorrectOptionID: 25"
3. **Page layout:** Each page features a header block identifying the Exam Shift, Date, Course, and Medium. Below the header, the data is organized into **3 major columns of Q-A pairs per page**, corresponding directly to the three subjects: "(Physics)", "(Chemistry)", and "(Mathematics)". Each column contains 30 rows of Q-A pairs, making a total of 90 questions per page.
4. **Page 1 anomaly:** Page 1 **does contain actual Q-A pairs**. It is not just a cover page. In the provided AK PDF, Page 1 contains the keys for the "Assamese" medium. Your parser must not skip it.
5. **Q ID digit count:** 2021 AK: 11-digit IDs for both Questions and Options.
6. **Session coverage:** One AK PDF covers **all dates, all shifts, and all mediums** for the entire session. Consequently, there are thousands of unique Question IDs in the PDF, as the identical question translated into 13 different languages will possess 13 distinct Question IDs.

## Question Paper — Bilingual Structure
7. **Is the paper bilingual?** No. The provided 2021 Question Paper PDF is single-language (English only). 
8. **If bilingual — layout:** N/A for the provided 2021 document.
9. **Same NTA Question ID for both languages?** Based on the cross-reference with the Answer Key PDF, the NTA uses **different Question IDs** for different language translations of the same question. 
10. **Distinguishing marker:** N/A for the provided single-language document.

## Question Paper — Options and IDs
11. **Option IDs printed on paper:** Yes, an 11-digit NTA numeric ID is printed directly next to every option for ALL MCQ questions.
    *Example:* `70819150611. $[M^{2}L~T^{2}]$`
12. **Option labeling style:** Options are **not** labeled with (A)(B)(C)(D) or (1)(2)(3)(4). The 11-digit Option ID itself, followed by a period, acts as the label for the option.
13. **Integer-type question layout:** For Section B, there are no options printed. The question metadata (including the 11-digit NTA Question ID) is printed at the top just like MCQs. At the bottom, the engine provides metadata parameters like "Response Type: Numeric" and a placeholder text "Possible Answers: 5 to 5.001". 

## Question Paper — Layout
14. **Column count:** The provided 2021 PDF (which is a digital web-dump/response sheet format) uses a **1-column (single column) layout**, reading continuously top-to-bottom. 
15. **Section headers:** Subject boundaries are marked with explicit, plain-text headers. 
    *Exact text used:* "Physics Section A", "Physics Section B", "Chemistry Section A", "Chemistry Section B", "Mathematics Section A", "Mathematics Section B".
16. **Question count per subject:** It is consistently **30 questions per subject** (20 MCQ in Section A, 10 Integer in Section B). Total 90 questions.
17. **Question numbering:** Questions are numbered **continuously from 1 to 90** across all subjects (Physics: 1-30, Chemistry: 31-60, Mathematics: 61-90).

## Figures and Diagrams
18. **Frequency:** - Physics: ~25% of questions contain diagrams (7-8 out of 30).
    - Chemistry: ~25-30% contain structural diagrams or graphs.
    - Mathematics: ~0% (None found in this specific PDF sample).
19. **Column behavior:** As it is a single-column PDF, figures simply appear inline between the question text and the options.
20. **Figure types by subject:** - Physics: Velocity-time graphs, thermodynamic PV diagrams, spring-mass systems, logic circuits.
    - Chemistry: Adsorption isotherm graphs, organic reaction schemes, and structural formulas.
21. **Structural chemistry:** Complex organic structures (e.g., branched chains, cyclohexane derivatives) are embedded as **actual drawn images/figures**, not as text-based representations.
22. **Figure self-sufficiency:** (c) No — figure is essential and cannot be described adequately in text. The text frequently relies on phrases like "as shown in the figure" or "the corresponding acceleration-time graph".

## Mathematical Notation
23. **Rendering quality:** Mathematical expressions are rendered natively as **typeset math** (extractable to LaTeX/Unicode strings), not as embedded images.
24. **Chemical equations:** Standard inline chemical equations are typeset text using Unicode formatting (e.g., `S_{8(s)} + a OH^{-}_{(aq)} \longrightarrow b S^{2-}_{(aq)}`). Complex reaction mechanisms are embedded as images.
25. **Special symbols:** Symbols that require robust parser handling include vector arrows (`\vec{a}`), coordinate hats (`\hat{i}`), thermodynamic delta (`\Delta`), partial evaluation boundaries, equilibrium arrows (`\rightleftharpoons`), and integrated LaTeX formatting nested inside strings (`$[M^{2}L~T^{2}]$`).

## Year-by-Year Variations
26. *Note: Only the 2021 files were provided for analysis. The following applies exclusively to 2021.*
    - **2021:** Uses 11-digit Question and Option IDs. The question paper is a single-column digital printout. Section B answers in the AK are plain integers. Different languages have different Question IDs. 

---

## Critical Flags for Extraction Pipeline

1. **Section B Placeholder Text Trap:** The 2021 Question Paper contains the string `"Possible Answers: 5 to 5.001"` at the end of *every* Section B integer question. This is a testing engine placeholder and **must be explicitly filtered out** so your pipeline doesn't log "5 to 5.001" as the answer.
2. **AK Mapping by Medium:** Because NTA generates different 11-digit Question IDs for different language translations of the same question, your pipeline **must parse the page headers** in the Answer Key PDF to match the `Exam Date`, `Exam Shift`, and `Medium: English` before mapping IDs.
3. **No A/B/C/D Labels:** Your parser cannot look for traditional option prefixes like "(A)". It must utilize Regex to detect the 11-digit NTA Option ID followed by a dot (`^\d{11}\.\s`) to split and capture the 4 distinct MCQ options.
4. **Data Type Mismatch in AK:** The AK table header specifically says "CORRECT OPTION ID" for both Section A and Section B. However, the data type shifts silently: Section A rows contain 11-digit string IDs, while Section B rows contain the plain integer answer (e.g., "25"). The parser must be prepared for this dynamic type change within the same column based on the question number.
