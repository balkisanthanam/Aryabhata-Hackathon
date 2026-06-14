# Problem Text Format
- The student may refer to problems from their textbook (starting with NCERT) for evaluation and feedback.
- A chapter can have one or more exercises, and each exercise can have one or more problems.
    - Example: Maths chapters often have multiple exercises (for example, `EXERCISE 4.1`).
- `Class`, `Board`, `Subject`, and `Chapter` are expected as pipeline inputs from the caller.
    - If the student provides them in text, that is acceptable.
- Student input should be treated as free-form text, and required information should be extracted.

## Expected data to extract
- `Class` (optional)
- `Board` (optional)
- `Subject` (optional)
- `Chapter Title` (optional), Example: `Problems 8 to 10 in Oscillations`
- `Chapter Number` (optional), May be omitted when this feature is launched inside a chapter context.
- `Exercise Number/Name` (optional), Required when a chapter contains multiple exercises.
- `Problem Numbers` (**mandatory**)

### Output should be JSON with the fields above.

## Examples

### Example 1
- Context:
    - Subject: Physics
    - Chapter: 13
    - Chapter Title: Oscillations
- Sample student inputs:
    - `13.8`
    - `13.8, 13.9`
    - `13.8, 13.9, 13.10`
    - `7, 8, 9`
    - `4-8`
    - `13.8-13.10`
    - `13.4 to 13.10`
    - `Problems 13.8, 13.9, 13.10`
    - `Problems 7, 8, 9`
    - `Problems 4-8`
    - `Probs 13.8-13.10`
    - `Physics Chapter 13 Problems 13.8, 13.9, 13.10`
    - `Physics Chapter 13 Problems 7, 8, 9`
    - `Physics Chapter 13 Problems 4-8`
    - `Physics Chapter 13 Problems 13.8-13.10`
    - `Oscillations probs 13.8 to 13.10`

### Example 2
- Context:
    - Subject: Maths
    - Chapter: 4
    - Chapter Title: Complex Numbers and Quadratic Equations
- Note:
    - This chapter has multiple exercises, so exercise number is expected.
- Sample student inputs:
    - `Ex 4.1 probs 2-5`
    - `Exercise 4.1 3,4,5`
    - `Complex numbers ex 4.1 probs 2-5`
    - `Complex numbers ex 4.1 3,4,5`

### Example 3 (multiple exercises in one request)
- Context:
    - Subject: Maths
    - Chapter: 10
    - Chapter Title: Conic Sections
- Sample student inputs:
    - `Ex 10.1 probs 2-5`
    - `Exercise 10.1 3,4,5`
    - `Conic sections ex 10.1 probs 2-5`
    - `Conic sections ex 10.1 3,4,5`
    - `Ex 10.1 2 to 5, Ex 10.2 4,5`
    - `Miscellaneous ex 2 to 5` (for chapters containing an exercise titled `Miscellaneous Exercise on Chapter 10`)

- Note:
    - The examples are illustrative, not restrictive.
    - Similar variations should also be supported.
