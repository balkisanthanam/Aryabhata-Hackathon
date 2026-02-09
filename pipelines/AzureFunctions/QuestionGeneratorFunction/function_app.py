import os
import azure.functions as func
import logging
import json
import random
import csv
import urllib.request
import io
import time
from abc import ABC, abstractmethod
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import openai
try:
    import google.generativeai as genai
except ImportError:
    genai = None

# debugpy setup removed for public release — enable locally if needed
# import debugpy; debugpy.listen(("localhost", 5678))

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

CSV_MAPPING = {
    "Science": os.environ.get("CSV_URL_SCIENCE", "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/examhistory/Pranay-Science.csv"),
    "Hindi": os.environ.get("CSV_URL_HINDI", "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/examhistory/Pranay-Hindi.csv"),
    "Social Studies": os.environ.get("CSV_URL_SST", "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/examhistory/Pranay-SST.csv")
}

DIFFICULTY_MAP = {
    "Easy": ["Basic", "Easy", "Simple"],
    "Medium": ["Medium", "Average"],
    "Difficult": ["Difficult", "Hard", "Advanced"]
}

@app.route(route="generate-questions", methods=["POST"])
def generate_questions(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processing a request for question generation.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    subject = req_body.get('subject', 'Science')
    difficulty = req_body.get('difficulty', 'Medium')
    count = int(req_body.get('numQuestions', 10))

    csv_url = CSV_MAPPING.get(subject)
    
    questions_data = []

    if csv_url:
        try:
            logging.info(f"Fetching CSV from {csv_url}")
            with urllib.request.urlopen(csv_url) as response:
                csv_content = response.read().decode('utf-8')
                f = io.StringIO(csv_content)
                reader = csv.DictReader(f)
                
                target_difficulties = DIFFICULTY_MAP.get(difficulty, [difficulty])
                
                for row in reader:
                    # Filter by difficulty (case-insensitive and trimmed)
                    row_difficulty = row.get('Difficulty', '').strip()
                    if not row_difficulty or any(td.lower() == row_difficulty.lower() for td in target_difficulties):
                        questions_data.append(row)
                        
            logging.info(f"Found {len(questions_data)} questions matching difficulty {difficulty}")
        except Exception as e:
            logging.error(f"Error fetching or parsing CSV: {str(e)}")
            # Fallback will happen below if questions_data is empty

    # Fallback to dummy data if no CSV found or no questions match
    if not questions_data:
        logging.warning(f"No questions found for subject {subject} and difficulty {difficulty}. Using dummy data.")
        dummy_templates = {
            "Science": [{"Question": "What is the chemical formula for water?", "Type": "mcq", "Marks": "1", "Options": "H2O,CO2,O2,H2SO4", "Answer": "0"}],
            "Social Studies": [{"Question": "Who was the first Prime Minister of India?", "Type": "mcq", "Marks": "1", "Options": "Mahatma Gandhi,Jawaharlal Nehru,Sardar Patel,B.R. Ambedkar", "Answer": "1"}],
            "Hindi": [{"Question": "हिंदी वर्णमाला में कितने स्वर होते हैं?", "Type": "mcq", "Marks": "1", "Options": "10,11,12,13", "Answer": "1"}],
            "Maths": [{"Question": "What is 15 × 12?", "Type": "mcq", "Marks": "1", "Options": "150,180,200,175", "Answer": "1"}]
        }
        questions_data = dummy_templates.get(subject, dummy_templates["Science"])

    # Randomly select questions
    if len(questions_data) > count:
        selected_rows = random.sample(questions_data, count)
    else:
        selected_rows = questions_data
        # If we need more, we can duplicate or just return what we have
        # User requested "number of questions requested", so we might need to repeat if short
        while len(selected_rows) < count and selected_rows:
            selected_rows.append(random.choice(questions_data))

    final_questions = []
    for i, row in enumerate(selected_rows):
        q_text = row.get('Question', '')
        q_obj = {
            "id": i + 1,
            "type": row.get('Type', 'subjective').lower() if row.get('Type') else 'subjective',
            "marks": int(row.get('Marks', 1)) if row.get('Marks') else 1,
            "chapter": row.get('Chapter', ''),
            "portion": row.get('Portion', ''),
            "subTopic": row.get('Sub Topic', '')
        }

        # Handle Question field (URL list or text)
        if q_text.startswith('http'):
            # It's an image or list of images
            urls = [u.strip() for u in q_text.split('#') if u.strip()]
            if len(urls) > 1:
                q_obj["imageUrls"] = urls
                q_obj["question"] = "Answer the following question:"
            else:
                q_obj["imageUrl"] = urls[0]
                q_obj["question"] = "Answer the following question:"
        else:
            q_obj["question"] = q_text

        # Handle MCQ options if present (assuming CSV might have them in a field like 'Options' or similar if Type is mcq)
        # For now, following the structure from the dummy but adapted to row data if it exists
        if q_obj["type"] == 'mcq':
            options_str = row.get('Options', '')
            if options_str:
                q_obj["options"] = [o.strip() for o in options_str.split(',')]
            else:
                q_obj["options"] = ["Option A", "Option B", "Option C", "Option D"]
            
            q_obj["correctAnswer"] = int(row.get('Answer', 0)) if row.get('Answer') else 0

        final_questions.append(q_obj)

    return func.HttpResponse(
        json.dumps({
            "subject": subject,
            "difficulty": difficulty,
            "questions": final_questions
        }),
        status_code=200,
        mimetype="application/json"
    )

class PromptService:
    """Service to manage and load prompt templates."""
    def __init__(self, prompts_dir: str = "prompts"):
        # In Azure Functions, we need to handle paths relative to the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.prompts_dir = os.path.join(script_dir, prompts_dir)

    def get_prompt(self, name: str) -> str:
        path = os.path.join(self.prompts_dir, f"{name}.txt")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logging.error(f"Prompt template {name} not found at {path}")
            return ""

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    @abstractmethod
    def call_llm(self, prompt: str, system_message: str = "", vision_image_urls: list = None) -> str:
        pass

class OpenAIProvider(LLMProvider):
    """Implementation for OpenAI (ChatGPT), supports both standard and Azure OpenAI."""
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.endpoint = os.environ.get("OPENAI_ENDPOINT")
        self.api_version = os.environ.get("OPENAI_API_VERSION", "2024-02-15-preview")
        
        if not self.api_key:
            logging.warning("OPENAI_API_KEY not configured.")
            
        if self.endpoint:
            logging.info(f"Using Azure OpenAI with endpoint: {self.endpoint}")
            self.client = openai.AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version
            )
        else:
            logging.info("Using standard OpenAI API")
            self.client = openai.OpenAI(api_key=self.api_key)

    def call_llm(self, prompt: str, system_message: str = "You are a helpful assistant.", vision_image_urls: list = None) -> str:
        if not self.api_key:
            return "ERROR: OpenAI API Key Missing"
        # If vision images are provided, append them as a short list to the prompt
        if vision_image_urls:
            images_note = "\n\n[Images for context - do NOT invent contents, use only to correct OCR]:\n" + "\n".join(vision_image_urls)
            prompt_to_send = prompt + images_note
        else:
            prompt_to_send = prompt

        try:
            response = self.client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL_NAME", "gpt-5-chat"),
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt_to_send}
                ],
                temperature=0,
                response_format={ "type": "json_object" }
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"OpenAI call failed: {str(e)}")
            return f"ERROR: LLM Call Failed - {str(e)}"

class GeminiProvider(LLMProvider):
    """Implementation for Google Gemini API."""
    def __init__(self):
        if not genai:
            logging.warning("google-generativeai library not installed. Install with: pip install google-generativeai")
            self.api_key = None
            self.client = None
            return
        
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logging.warning("GEMINI_API_KEY not configured.")
            self.client = None
            return
        
        genai.configure(api_key=self.api_key)
        self.model = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
        logging.info(f"Configured Gemini provider with model: {self.model}")

    def _fetch_image_from_url(self, image_url: str) -> dict:
        """Fetch image from URL and return as base64-encoded data."""
        try:
            import base64
            with urllib.request.urlopen(image_url) as response:
                image_data = response.read()
                base64_data = base64.standard_b64encode(image_data).decode('utf-8')
                content_type = response.headers.get('content-type', 'image/jpeg')
                return {
                    "mime_type": content_type,
                    "data": base64_data
                }
        except Exception as e:
            logging.error(f"Failed to fetch or encode image from {image_url}: {str(e)}")
            return None

    def call_llm(self, prompt: str, system_message: str = "", vision_image_urls: list = None) -> str:
        if not self.api_key:
            return "ERROR: Gemini API Key Missing or library not installed"
        
        try:
            # Build content parts: system message + user prompt + images
            content_parts = []
            
            # Add system message if provided (as part of the first user message)
            if system_message:
                full_prompt = f"System: {system_message}\n\n{prompt}"
            else:
                full_prompt = prompt
            
            content_parts.append(full_prompt)
            
            # Fetch and add images if provided
            if vision_image_urls:
                for image_url in vision_image_urls:
                    if image_url:
                        image_data = self._fetch_image_from_url(image_url)
                        if image_data:
                            content_parts.append({
                                "mime_type": image_data["mime_type"],
                                "data": image_data["data"]
                            })
                        else:
                            logging.warning(f"Could not fetch image: {image_url}")
            
            # Call Gemini API
            response = genai.GenerativeModel(self.model).generate_content(
                content_parts,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    top_k=1
                )
            )
            
            return response.text
        except Exception as e:
            logging.error(f"Gemini call failed: {str(e)}")
            return f"ERROR: LLM Call Failed - {str(e)}"

class LLMService:
    """Factory service to handle LLM calls based on configuration."""
    def __init__(self):
        provider_name = os.environ.get("LLM_PROVIDER", "openai").lower()
        if provider_name == "openai":
            self.provider = OpenAIProvider()
        elif provider_name == "gemini":
            self.provider = GeminiProvider()
        else:
            logging.error(f"Unsupported LLM provider: {provider_name}")
            self.provider = OpenAIProvider() # Fallback

    def generate(self, prompt: str, system_message: str = "", vision_image_urls: list = None) -> str:
        return self.provider.call_llm(prompt, system_message, vision_image_urls)

def perform_ocr(image_url: str) -> str:
    """Performs OCR on an image URL using Azure Document Intelligence."""
    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")

    if not endpoint or not key:
        logging.error("Azure Document Intelligence endpoint or key not configured.")
        return "ERROR: OCR Configuration Missing"

    try:
        document_analysis_client = DocumentAnalysisClient(
            endpoint=endpoint, credential=AzureKeyCredential(key)
        )

        poller = document_analysis_client.begin_analyze_document_from_url(
            "prebuilt-read", image_url
        )
        result = poller.result()

        extracted_text = ""
        for page in result.pages:
            for line in page.lines:
                extracted_text += line.content + "\n"

        return extracted_text.strip()
    except Exception as e:
        logging.error(f"OCR failed for {image_url}: {str(e)}")
        return f"ERROR: OCR Failed - {str(e)}"

@app.route(route="evaluate-sheet", methods=["POST"])
def evaluate_sheet(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processing a request for sheet evaluation.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    paper_id = req_body.get('paperId')
    blob_urls = req_body.get('blobUrls', [])

    logging.info(f"Evaluation requested for paper {paper_id} with {len(blob_urls)} files.")

    # SAS token and container URL from environment variables
    SAS_TOKEN = os.environ.get("ANSWERSHEET_SAS_TOKEN", os.environ.get("SAS_TOKEN", ""))
    CONTAINER_URL = os.environ.get("CONTAINER_URL", "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/answersheet")
    
    paper_data = None
    if paper_id:
        paper_url = f"{CONTAINER_URL}/answersheet/papers/{paper_id}.json"
        try:
            logging.info(f"Fetching paper details from {paper_url}")
            with urllib.request.urlopen(paper_url) as response:
                paper_data = json.loads(response.read().decode('utf-8'))
            logging.info(f"Successfully fetched paper: {paper_data.get('subject')} - {paper_data.get('difficulty')}")
        except Exception as e:
            logging.error(f"Error fetching paper {paper_id}: {str(e)}")

    # Step 1: Perform OCR on Paper Questions (if images) and Answer Sheets
    logging.info("Starting Step 1: OCR Extraction")
    
    ocr_results = {
        "questions": [],
        "answerSheets": []
    }

    # OCR for Paper
    if paper_data and "questions" in paper_data:
        for q in paper_data["questions"]:
            q_id = str(q.get("id"))
            raw_text = q.get("question", "")
            
            # If question has an image, OCR it to get more context/text
            image_text = ""
            image_url = q.get("imageUrl")
            if image_url:
                logging.info(f"Performing OCR on question {q_id} image")
                image_text = perform_ocr(image_url)
            
            # Handle multiple images if present
            image_urls = q.get("imageUrls", [])
            images_text_list = []
            if image_urls:
                images_text_list = [perform_ocr(url) for url in image_urls]
            
            full_text = raw_text
            if image_text:
                full_text += "\n" + image_text
            if images_text_list:
                full_text += "\n" + "\n".join(images_text_list)
                
            ocr_results["questions"].append({
                "id": q_id,
                "text": raw_text,
                "imageText": image_text,
                "imagesText": images_text_list,
                "fullText": full_text,
                "marks": q.get("marks", 1)
            })

    # OCR for Answer Sheets
    for i, sheet_url in enumerate(blob_urls):
        logging.info(f"Performing OCR on answer sheet {i+1}")
        sheet_text = perform_ocr(sheet_url)
        ocr_results["answerSheets"].append({
            "url": sheet_url,
            "extractedText": sheet_text
        })

    # Step 2: Perform Answer Segmentation (LLM) using Strategy H prompts
    logging.info("Starting Step 2: Answer Segmentation using vision prompts")
    prompt_service = PromptService()
    llm_service = LLMService()

    # Read container & SAS from env to fetch paper if configured
    SAS_TOKEN = os.environ.get("ANSWERSHEET_SAS_TOKEN", os.environ.get("SAS_TOKEN", ""))
    CONTAINER_URL = os.environ.get("ANSWERSHEET_CONTAINER_URL", os.environ.get("CONTAINER_URL", "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/answersheet"))

    # Combine all answer sheet OCR text
    full_ocr_text = "\n\n".join([sheet.get("extractedText", "") for sheet in ocr_results.get("answerSheets", [])])

    # Prepare question paper JSON from available question texts
    paper_questions_json = json.dumps([
        {"id": q.get("id"), "question": q.get("fullText") if q.get("fullText") else q.get("question")}
        for q in ocr_results.get("questions", [])
    ], indent=2)

    segmentation_prompt_tpl = prompt_service.get_prompt("vision_segmentation_prompt")

    prompt = segmentation_prompt_tpl.format(
        ocr_text=full_ocr_text,
        question_paper=paper_questions_json
    )

    logging.info("Calling LLM for vision-aware segmentation...")
    system_message = "You are an expert exam evaluator with vision capabilities. Extract answers into JSON."
    segmentation_response_str = llm_service.generate(prompt, system_message, vision_image_urls=blob_urls if blob_urls else None)

    segmented_answers = []
    try:
        if isinstance(segmentation_response_str, str) and ("```json" in segmentation_response_str or "```" in segmentation_response_str):
            if "```json" in segmentation_response_str:
                segmentation_response_str = segmentation_response_str.split("```json")[1].split("```")[0].strip()
            else:
                segmentation_response_str = segmentation_response_str.split("```")[1].split("```")[0].strip()

        segmentation_data = json.loads(segmentation_response_str)
        segmented_answers = segmentation_data.get("segmentedAnswers", [])
        logging.info(f"Successfully segmented {len(segmented_answers)} answers.")
    except Exception as e:
        logging.error(f"Failed to parse segmentation response: {str(e)}")
        logging.debug(f"Raw segmentation response: {segmentation_response_str}")

    # Step 3: Perform Final Evaluation (LLM) using Strategy H evaluation prompts
    logging.info("Starting Step 3: Final Evaluation (vision-enhanced)")

    evaluation_results = []
    total_score = 0
    max_possible_score = 0

    # Choose batch vs individual: prefer request flag, else env
    batch_evaluation = req_body.get('batchEvaluation')
    if batch_evaluation is None:
        batch_evaluation = os.environ.get('BATCH_EVALUATION', 'true').lower() in ('1', 'true', 'yes')

    if batch_evaluation:
        logging.info("Using batch evaluation flow")
        batch_prompt_tpl = prompt_service.get_prompt("evaluation_vision_batch_prompt")

        # Prepare batch items and collect vision images for context
        questions_map = {str(q.get("id")): q for q in ocr_results.get("questions", [])}
        batch_items = []
        vision_images = []

        # Add original answer sheet images
        for url in blob_urls:
            if url and url not in vision_images:
                vision_images.append(url)

        for ans in segmented_answers:
            q_id = str(ans.get("questionId"))
            student_answer = ans.get("answerText")
            if q_id in questions_map:
                question_data = questions_map[q_id]
                full_question_text = question_data.get("fullText") or question_data.get("question") or ""

                # Add question images to global vision list
                q_image_url = question_data.get("imageUrl")
                q_image_urls = question_data.get("imageUrls", []) or []
                if q_image_url and q_image_url not in vision_images:
                    vision_images.append(q_image_url)
                for u in q_image_urls:
                    if u and u not in vision_images:
                        vision_images.append(u)

                batch_items.append({
                    "questionId": q_id,
                    "question": full_question_text,
                    "studentAnswer": student_answer,
                    "marks": question_data.get("marks", 1)
                })

        if not batch_items:
            logging.warning("No items to batch evaluate.")
        else:
            prompt = batch_prompt_tpl.format(
                batch_data_json=json.dumps(batch_items, indent=2)
            )

            eval_response_str = llm_service.generate(prompt, "You are an expert exam evaluator with vision capabilities.", vision_image_urls=vision_images if vision_images else None)

            # eval_response_str = "{\n  \"evaluation\": [\n    {\n      \"questionId\": \"1\",\n      \"score\": 4,\n      \"feedback\": \"The student correctly identified the agent and object in each case. The image confirms the same entries with proper alignment. However, the student did not explicitly state the observable effect of force (change in shape or motion) for each case, though implied.\",\n      \"expected_answer\": \"Each situation should identify the agent, object, and the observable effect of force (change in shape or motion). For example: (a) Fingers act on lemon – change in shape; (b) Fingers act on tube – change in shape; (c) Load acts on spring – change in length; (d) Legs act on body – change in motion.\",\n      \"missed_points\": [\"Explicit mention of the observable effect of force in each case.\"]\n    },\n    {\n      \"questionId\": \"2\",\n      \"score\": 3,\n      \"feedback\": \"The student correctly mentioned the Doppler effect as the reason. The image confirms the same short answer. However, the explanation lacks detail on how the change in frequency helps the blindfolded person judge distance.\",\n      \"expected_answer\": \"The blindfolded person can guess which player is closer because the sound waves from the nearer player reach her with higher frequency due to the Doppler effect.\",\n      \"missed_points\": [\"Explanation of how frequency change indicates closeness.\"]\n    },\n    {\n      \"questionId\": \"3\",\n      \"score\": 4,\n      \"feedback\": \"The student selected option (d) 'All of the above', which is correct. The image confirms the same. The answer is complete and conceptually accurate.\",\n      \"expected_answer\": \"Lightning helps in nitrogen fixation, formation of ozone, and contributes to chemical reactions that may lead to evolution of new species. Hence, all of the above.\",\n      \"missed_points\": []\n    },\n    {\n      \"questionId\": \"4\",\n      \"score\": 3,\n      \"feedback\": \"The student correctly stated that the solution conducts electricity, causing magnetic needle deflection. The image confirms the same. However, the answer could mention that the deflection occurs due to current flowing through the solution.\",\n      \"expected_answer\": \"When the tester’s ends are dipped into a conducting solution, electric current flows through it, producing a magnetic effect that causes the needle to deflect.\",\n      \"missed_points\": [\"Mention of current flow causing magnetic effect.\"]\n    },\n    {\n      \"questionId\": \"5\",\n      \"score\": 2,\n      \"feedback\": \"The student wrote 'One force is greater than the other', which is incorrect. If the cart moves with the same speed and direction, the net force is zero, meaning forces are equal and opposite. The image confirms the same short answer.\",\n      \"expected_answer\": \"The forces applied are equal in magnitude and opposite in direction, resulting in no change in motion.\",\n      \"missed_points\": [\"Equality and opposite direction of forces.\", \"Inference about constant velocity meaning balanced forces.\"]\n    },\n    {\n      \"questionId\": \"6\",\n      \"score\": 3,\n      \"feedback\": \"The student correctly stated that the device will not work because electricity won’t flow. The image confirms the same. The reasoning is conceptually correct though brief.\",\n      \"expected_answer\": \"No, the device will not work because the current will not flow if the battery’s positive terminal is connected to the negative point of the device; correct polarity is required for current flow.\",\n      \"missed_points\": [\"Explanation of polarity and current direction.\"]\n    },\n    {\n      \"questionId\": \"7\",\n      \"score\": 0,\n      \"feedback\": \"The student selected option (c) 'sharing comb', which is incorrect. The correct answer is (b) 'blood transfusion'. The image confirms the same choice.\",\n      \"expected_answer\": \"AIDS can spread through blood transfusion, sharing infected needles, or from mother to child, not through sharing food or combs.\",\n      \"missed_points\": [\"Correct identification of transmission route.\"]\n    },\n    {\n      \"questionId\": \"8\",\n      \"score\": 4,\n      \"feedback\": \"The student correctly wrote 'Pressure = Force / Area'. The image confirms the formula. This fully explains why pressure increases when area decreases for constant force.\",\n      \"expected_answer\": \"Pressure = Force / Area. For constant force, if area decreases, pressure increases.\",\n      \"missed_points\": []\n    },\n    {\n      \"questionId\": \"9\",\n      \"score\": 4,\n      \"feedback\": \"The student correctly calculated time period and frequency. The image confirms the same values. The answer is complete and accurate.\",\n      \"expected_answer\": \"Time period = Total time / Number of oscillations = 20 s / 10 = 2 s; Frequency = 1 / Time period = 0.5 Hz.\",\n      \"missed_points\": []\n    },\n    {\n      \"questionId\": \"10\",\n      \"score\": 2,\n      \"feedback\": \"The student did not provide an answer. The image shows the space blank. The correct answer involves the Richter scale and its interpretation.\",\n      \"expected_answer\": \"The destructive energy of an earthquake is measured on the Richter scale. An earthquake of magnitude 3 would be recorded by a seismograph but cause little damage.\",\n      \"missed_points\": [\"Name of scale (Richter scale).\", \"Explanation of seismograph recording.\", \"Comment on damage level.\"]\n    }\n  ]\n}"

            try:
                if isinstance(eval_response_str, str) and ("```json" in eval_response_str or "```" in eval_response_str):
                    if "```json" in eval_response_str:
                        eval_response_str = eval_response_str.split("```json")[1].split("```")[0].strip()
                    else:
                        eval_response_str = eval_response_str.split("```")[1].split("```")[0].strip()

                eval_data_list = json.loads(eval_response_str)

                # Sometimes the response contains an evaluation key wrapping the list
                if isinstance(eval_data_list, dict) and "evaluation" in eval_data_list:
                    eval_data_list = eval_data_list["evaluation"]
                
                eval_map = {str(item.get("questionId")): item for item in eval_data_list}

                for item in batch_items:
                    q_id = str(item["questionId"])
                    max_marks = item.get("marks", 1)
                    max_possible_score += max_marks
                    if q_id in eval_map:
                        res = eval_map[q_id]
                        score = float(res.get("score", 0))
                        total_score += score
                        evaluation_results.append({
                            "questionId": q_id,
                            "question": item["question"],
                            "studentAnswer": item["studentAnswer"],
                            "score": score,
                            "maxMarks": max_marks,
                            "feedback": res.get("feedback", ""),
                            "expectedAnswer": res.get("expected_answer", ""),
                            "missedPoints": res.get("missed_points", [])
                        })
                    else:
                        evaluation_results.append({
                            "questionId": q_id,
                            "question": item["question"],
                            "studentAnswer": item["studentAnswer"],
                            "error": "LLM failed to return evaluation for this question"
                        })

            except Exception as e:
                logging.error(f"Batch evaluation parse failed: {str(e)}")
                evaluation_results = [{"error": "Batch evaluation failed", "raw_response": eval_response_str}]

    else:
        logging.info("Using per-question individual evaluation flow")
        eval_prompt_tpl = prompt_service.get_prompt("evaluation_vision_prompt")
        questions_map = {str(q.get("id")): q for q in ocr_results.get("questions", [])}

        for ans in segmented_answers:
            q_id = str(ans.get("questionId"))
            student_answer = ans.get("answerText")
            if q_id in questions_map:
                question_data = questions_map[q_id]
                full_question_text = question_data.get("fullText") or question_data.get("question") or ""
                max_marks = question_data.get("marks", 1)
                max_possible_score += max_marks

                # Build vision images: question images + answer sheet images
                vision_images = []
                q_image_url = question_data.get("imageUrl")
                q_image_urls = question_data.get("imageUrls", []) or []
                if q_image_url:
                    vision_images.append(q_image_url)
                for u in q_image_urls:
                    if u and u not in vision_images:
                        vision_images.append(u)
                for u in blob_urls:
                    if u and u not in vision_images:
                        vision_images.append(u)

                prompt = eval_prompt_tpl.format(
                    question=full_question_text,
                    answer=student_answer
                )

                eval_response_str = llm_service.generate(prompt, "You are an expert exam evaluator with vision capabilities.", vision_image_urls=vision_images if vision_images else None)

                try:
                    if isinstance(eval_response_str, str) and ("```json" in eval_response_str or "```" in eval_response_str):
                        if "```json" in eval_response_str:
                            eval_response_str = eval_response_str.split("```json")[1].split("```")[0].strip()
                        else:
                            eval_response_str = eval_response_str.split("```")[1].split("```")[0].strip()

                    eval_data = json.loads(eval_response_str)
                    score = float(eval_data.get("score", 0))
                    total_score += score
                    evaluation_results.append({
                        "questionId": q_id,
                        "question": full_question_text,
                        "studentAnswer": student_answer,
                        "score": score,
                        "maxMarks": max_marks,
                        "feedback": eval_data.get("feedback", ""),
                        "expectedAnswer": eval_data.get("expected_answer", ""),
                        "missedPoints": eval_data.get("missed_points", [])
                    })
                except Exception as e:
                    logging.error(f"Failed to parse evaluation response for Q{q_id}: {str(e)}")
                    evaluation_results.append({
                        "questionId": q_id,
                        "studentAnswer": student_answer,
                        "error": f"Evaluation failed to parse: {str(e)}",
                        "raw_response": eval_response_str
                    })
            else:
                logging.warning(f"Segmented answer for unknown question ID: {q_id}")

    # Final Result
    evaluation_id = f"EVAL-{int(time.time())}"
    
    result = {
        "status": "success",
        "evaluationId": evaluation_id,
        "message": "Evaluation process started successfully.",
        "details": {
            "paperId": paper_id,
            "subject": paper_data.get('subject') if paper_data else "Unknown",
            "difficulty": paper_data.get('difficulty') if paper_data else "Unknown",
            "questionCount": paper_data.get('questionCount') if paper_data else 0,
            "answerSheetsReceived": len(blob_urls),
            "ocrCompleted": True,
            "segmentationCompleted": len(segmented_answers) > 0,
            "evaluationCompleted": len(evaluation_results) > 0,
            "totalScore": total_score,
            "maxPossibleScore": max_possible_score,
            "ocrResultsSummary": {
                "sheetsProcessed": len(ocr_results["answerSheets"]),
                "questionsProcessed": len(ocr_results["questions"])
            },
            "segmentedAnswers": segmented_answers,
            "evaluationResults": evaluation_results
        }
    }

    return func.HttpResponse(
        json.dumps(result),
        status_code=200,
        mimetype="application/json"
    )

