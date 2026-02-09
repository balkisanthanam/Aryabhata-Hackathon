# Creating a New Azure Function to Process Student's Feedback

## Introduction

The Solution Feedback's core processory is going to be this Azure Durable function which accepts the necessary parameters, process the params (& fill as needed), weaves a suite of Azure Functions and Gemini models to generate the feedback. This Feedback is then passed back to the user through Postgresql database and Azure Storage.

## Component level Flow

1. Node.js (or any client for that matter) inserts the data into the postgresql table and pushes the message to the queue
2. Azure Durable Function StudentEvaluation Function is Triggered
    - Invoke Azure Function SplitStudentHandwriting Function to split them into individual problem solution (will return multiple image or save in Azure Storage)
    - If the question input is text
        - Parse the text using Gemini-3-Flash to extract the problem numbers and exercise numbers
        - Invoke Gemini 3 Pro model with (the PDF of the chapter, problem & exercise number, student solution image) as tuples in batches. Here i expect the Gemini 3 Pro model to look into the pdf and pick the right problem and evaluate the student solution. It can use the PDF also as grounding for solution
    - If the question input is image
        - Invoke Azure Function SplitTextProblems Function to split them into individual problem images
        - Invoke Gemini 3 Pro model with (the PDF of the chapter, problem image, student solution image) as tuples in batches. Here the model is provided the problem image and the student solutio image. the PDF acts as grounding for solution.
3. Update status and data into db & Azure storage and return

## Azure Durable Function Details

### Trigger

The Azure Durable function is going to be triggered by a Azure Storage Queue. The queue will be created in the same resource group as the Azure function. The Queue's name is feedback-jobs and URL is  <https://<YOUR_STORAGE_ACCOUNT>.queue.core.windows.net/feedback-jobs>

### Function Parameters

The Azure Durable function will be triggered when a new item is added to the feedback-jobs queue.
The function accepts the following parameter:
id (the function will fetch the record from the postgresql db using this id, and all details are available in the db)

### Logic

- Get the data for the id from the postgresql db. Here are the schema details

    | Column Name | Data Type | Nullable | Default |
    | :--- | :--- | :--- | :--- |
    | id | uuid | NO | gen_random_uuid() |
    | userid | integer | NO | NULL |
    | class | character varying | YES | NULL |
    | board | character varying | YES | NULL |
    | subject | character varying | NO | NULL |
    | chapter_id | integer | YES | NULL |
    | chapter_title | character varying | NO | NULL |
    | chapter_number | integer | NO | NULL |
    | pdffileurl | character varying | YES | NULL |
    | status | USER-DEFINED | NO | 'PENDING'::solution_evaluation_status |
    | problem_text_ref | character varying | YES | NULL |
    | problem_image_url | text | YES | NULL |
    | student_work_url | text | NO | NULL |
    | feedback_json | jsonb | YES | NULL |
    | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
    | updated_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |

- Process the Problem input
  - This can have two paths depending on either 'problem_text_ref' or 'problem_image_url' is provided as input (from the table). In future we will have cases where both are provided, each augmenting the other.
  - Process the Student input
    - Call Azure Function SplitStudentHandwriting Function to split them into individual problem solution (will return multiple image or save in Azure Storage)
  - If 'problem_text_ref' is provided
    - Call Gemini 3 Flash model with the prompt <<TBD>> to parse the problem text
    - Match the problem (nos) with the chapter pdf and the cropped student problems. This should result in a list of tuples - (problem_number, student_answer_image (url), subject, chapter pdf (url), chapter title, Exercise)
    - Invoke Gemini model in Batches of 3 (let's make this as a parameter). Prompt <<TBD>>
      - Prepare the params for the Gemini model (should we do this before or inside loop?)
  - If 'problem_image_url' is provided
    - Call Azure Function SplitTextBookProblems Function to split them into individual problem images
    - Match the individual problem images with the chapter pdf and the cropped student problems. This should result in a list of tuples - (problem_image_snippet (url), student_answer_image (url), subject, chapter pdf (url), chapter title)
    - Invoke Gemini model in Batches of 3 (let's make this as a parameter). Prompt <<TBD>>
      - Prepare the params for the Gemini model (should we do this before or inside loop?)

- Verify the results from Gemini
- Update the postgresql db with the results
- Delete the record from the feedback-jobs queue
  - Can the above two steps (updating the db and deleting the record) be executed atomic?

### Checks

- subject has to be one of the entries in the table 'ClassSubjectData'
- chapter has to be one of the entries in the table 'ChapterData'

## How to access Gemini models

## Storage account details

## Problem Text Format

The student can refer to the problems in their book (here NCERT to start) that the student is solving, for which he/she is seeking evaluation and feedback.
A typical NCERT chapter can contain one or more exercises, and each exercise can contain one or more problems. For instance Maths typically has multiple exercise, each having a title (eg. 'EXERCISE 4.1').
The Class, Board, Subject and Chapter are supposed to be provided as input. However if the student choses to provide it is ok.
We should treat this as a free format text and extract information.
The student can hence refer to problems as follows: (Note these are examples and there could be similar such cases)

### Eg 1

Subject - Physics, Chapter - 13, Oscillations (these inputs are separately provided anyway)

Student Problem Text input samples:
'13.8'
'13.8, 13.9'
'13.8, 13.9, 13.10'
'7, 8, 9'
'4-8'
'13.8-13.10'
'13.4 to 13.10'
'Problems 13.8, 13.9, 13.10'
'Problems 7, 8, 9'
'Problems 4-8'
'Probs 13.8-13.10'
'Physics Chapter 13 Problems 13.8, 13.9, 13.10'
'Physics Chapter 13 Problems 7, 8, 9'
'Physics Chapter 13 Problems 4-8'
'Physics Chapter 13 Problems 13.8-13.10'
'Oscillations probs 13.8 to 13.10'

### Eg 2

Subject - Maths, Chapter - 4, COMPLEX NUMBERS AND QUADRATIC EQUATIONS (these inputs are separately provided anyway)
Student Problem Text input samples:
Note that this chapter has multiple exercises. So the expectation is that the student provide the Exercise Number as well.
'Ex 4.1 probs 2-5'
'Exercise 4.1 3,4,5'
'Complex numbers ex 4.1 probs 2-5'
'Complex numbers ex 4.1 3,4,5'

### Eg. 3 - reference to Multiple exercises in the same request

Subject - Maths, Chapter - 10, CONIC SECTIONS (these inputs are separately provided anyway)
Student Problem Text input samples:
'Ex 10.1 probs 2-5'
'Exercise 10.1 3,4,5'
'Conic sections ex 10.1 probs 2-5'
'Conic sections ex 10.1 3,4,5'
'Ex 10.1 2 to 5, Ex 10.2 4,5'
'Miscellaneous ex 2 to 5' (note in this Chapter, there's an Exercise titled 'Miscellaneous Exercise on Chapter 10')

#### Note - The above are not restrictive, we should be able to handle similar cases
