1) Implement the smart context using our newly built Vector Index. This will be rolled out to both the two existing solutions - NCERT multi-step pipeline and also the Student Feedback - what's the expected savings from this?
	- Question - Solution Feedback pipeline extracts questions also fresh from the PDFs. We can make it read from the questiondata. With this we can get rid of PDF completely
2) Evaluator for Solutions (I missed the evaluator and LLM-as-Judge from the plan. Include them)
	1) Component 1 - Verification against Answer provided by NCERT and for JEE Main the Answer key. This can help us filter obvious. But note that not all answers can have NCERT keys, for definitions won't have. Prove will not, but they are obvious. Note this step is applicable only where Answer key exists.
	2) Component 2 - Picks a model solution (if one is not provided or doesn't exist in cache, it invokes the model solution to generate one). Compares the given solution against the model solution. Given the steps need not be exact, should we have another model to do this comparing?

3) Model Solution using Gemini 3.1 Pro
	1) Use Gemini 3.1 Pro as the Solution Generator. We already have this in NCERT. We centralise this. In addition we iterate one for JEE Main also
	2) Have a critique model to ensure the model solution is robus. Should this also be Gemini 3.1 Pro as the model solution has Gemini 3.1 Pro?
4) Data collection - NCERT
	1) we have already done solutions on NCERT and is stored. We need to come up with way to filter Gold from this. Maybe a 2-stage process? 
		stage 1 - Run Critique from the above step.
		stage 2 - Run Evaluator for Solutions
		Shouldn't we run this for all solutions generated so far and update the Prod db?
	2) Sample the required # of data from the above step
5) Data collection - JEE Main
	1) Take a required sample of JEE Ingested questions
	2) Generate Module solution as in step 3 (both Gemini 3.1 pro one and the Critique)
	3) ingest these into the db
	4) Sample the required # of data from the above step
6) Split and have Training and Testing sets
7) Fine-tune Gemini 3 Flash with training. Use the Testing set to evaluate iterations
8) Deploy model in Google Cloud for "Scale to zero" or "Pay for Usage" option
9) Update The NCERT Multi-Step pipeline and the Student Feedback pipeline to use this deployed model
10) For JEE Main (JEE Ascent), will use this separately in that pipeline?
