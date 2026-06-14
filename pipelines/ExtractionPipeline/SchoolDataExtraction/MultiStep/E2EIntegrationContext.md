### Brief
Now we are stitching the whole thing as a full pipeline. Essentially we are going to invoke both the stages one after the other and store the results in Azure storage and Azure PostgreSQL. But let's ensure that the two stages can be used separately if needed as it is existing. 

### Changes
1. Extract Chapter/Unit No in stage 1 from the PDF passed. This will be at the beginning of the chapter. We are interested only in the numeric part. For eg. if the title is like 'Unit 7', we get 7. Let's change the prompt for this instruction (it should be captured in the JSON).
2. To Stage 2, we should pass the questions from stage one. I guess this is currently loading from the file. If so, we can let it do that, but connect in a flow
3. We are going to ingest the output of the two stages in a table and azure storage. Please refer to this script for the tables i have created. We need to create entries in ExerciseData and QuestionData effectively. Scripts\DB_Master.sql
Here's the logic
4. (To be done after stage 1)
    a) Once stage one is completed, we get Class, Subject (both already known) and ChapterNumber from the just extracted JSON. With this connect to PostgreSQL (`<DB_HOST>`) and get the ChapterId.
    b) For each Exercise in the JSON from Stage 1 ("exercise_sections" from the json)
    c) insert into ExerciseData (ChapterId (from the previous step), Exercise ("title" json metadata), totalQuestions ("total_questions" json metadata), OtherData ("exercise_sections" for that Exercise in the loop). Get the value of ExerciseId just ingested (it is the primary key generated)
5. (To be done after stage 2)
    a) Now let's insert the questions and solutinos into the QuestionData table. We need to conflate the outputs from stage 1 (questions) and stage 2 (solutions) and insert into QuestionData for each question with its solution.
    Loop through the corresponding "questions" (for that Exercise in the json). For each question snippet ({"question_id":"2.2","question_text":"...","page_number":12,"visual_required":true,"visual_data":{"type":"GRAPH","description":"...","box_2d":[340,405,505,650],"visual_source":"current_page","cropped_image_path":"cropped_images\\keph102\\q2_2_fig.png"},"figure_references":["Fig2.9"]})
        i) If "visual_required" is true, then get the "cropped_image_path". This will point to the corresponding image for that question. Upload into your configured Azure storage account and container (assign a name that can lead back to the question), then get the resource URL.
        ii) in the json snippet for this question, replace "cropped_image_path" with this resource url
        iii) From Solutions snippet (from stage 2), find the corresponding question in the same exercise. Get the solutions snipet for that quesion. {"question_id":"10.2","question_text":"...","steps":[...],"final_answer":"...","generated_images":[]}
        iv) if there is any image from solution, do the same as for the questions (store in Azure storage and replace the path with the url)
        v) insert into QuestionData (ExerciseId (from the previous step's insert into ExerciseData), Question_Ref ("question_id" from the json snippet), Content (the question's snippet), Solution (the solution's snippet))

### Problems to solve
1. How can we have Resumability? This is a platform with disparate  steps.
2. When we rerun steps should we still have the table insertion after that step?
3. Can we have local only mode, where we skip table insertion and Azure storage saving?
4. If you look at the output examples, it is evident that the model is not sending the output json assuming multiple exercises. That's not correct. There are many Exercises (which we haven't seen yet) that has multiple steps. Ideally we need the json to have Exercises and Questions within each exercise and each question within questions as it is existing. The same should apply for Solutions.

### Example files
C:\Bala\Coding\AryaBhatta\ExtractionPipeline\SchoolDataExtraction\MultiStep\Output\solution_physics_20251211_164726.json
C:\Bala\Coding\AryaBhatta\ExtractionPipeline\SchoolDataExtraction\MultiStep\Output\questions_physics_keph203_20251211_180103.json
