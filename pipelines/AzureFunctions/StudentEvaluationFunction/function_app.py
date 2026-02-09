import azure.functions as func
import logging
import json
import base64
import os
import requests
import google.generativeai as genai
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from typing import Optional, List, Dict, Any
import io

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Azure Key Vault configuration - set these via environment variables or Azure App Settings
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL", "https://<YOUR_KEYVAULT_NAME>.vault.azure.net/")
KEY_VAULT_SECRET_NAME = os.environ.get("KEY_VAULT_SECRET_NAME", "GOOGLEAPIKEY")
PROMPT_BLOB_URL = os.environ.get("PROMPT_BLOB_URL", "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/feedback/Evaluation.txt")


def get_api_key_from_keyvault() -> str:
    """
    Retrieve Google API key from Azure Key Vault
    """
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
        secret = client.get_secret(KEY_VAULT_SECRET_NAME)
        return secret.value
    except Exception as e:
        logging.error(f"Error retrieving API key from Key Vault: {str(e)}")
        raise


def fetch_blob_content(blob_url: str, as_text: bool = True):
    """
    Fetch content from Azure Blob Storage using Managed Identity with fallback to public access
    
    Args:
        blob_url: The full blob URL
        as_text: If True, decode as UTF-8 text; if False, return raw bytes
    
    Returns:
        Text string or bytes depending on as_text parameter
    """
    try:
        # Try using Managed Identity first (for production)
        if "blob.core.windows.net" in blob_url:
            try:
                from azure.storage.blob import BlobClient
                credential = DefaultAzureCredential()
                blob_client = BlobClient.from_blob_url(blob_url, credential=credential)
                content = blob_client.download_blob().readall()
                return content.decode('utf-8') if as_text else content
            except Exception as auth_error:
                logging.warning(f"Managed Identity auth failed for {blob_url}, trying public access: {str(auth_error)}")
        
        # Fall back to public access (for local testing or if Managed Identity fails)
        response = requests.get(blob_url)
        response.raise_for_status()
        return response.text if as_text else response.content
    except Exception as e:
        logging.error(f"Error fetching blob from {blob_url}: {str(e)}")
        raise


def fetch_prompt_from_blob() -> str:
    """
    Fetch the evaluation prompt template from Azure Blob Storage
    """
    return fetch_blob_content(PROMPT_BLOB_URL, as_text=True)


def fill_prompt_template(prompt_template: str, class_value: str, subject: str, 
                        problem: str, ref_answer: str) -> str:
    """
    Fill the prompt template with provided values
    """
    filled_prompt = prompt_template.replace("{class}", class_value)
    filled_prompt = filled_prompt.replace("{Subject}", subject)
    filled_prompt = filled_prompt.replace("{Problem}", problem)
    filled_prompt = filled_prompt.replace("{RefAnswer}", ref_answer)
    return filled_prompt


def decode_base64_image(base64_string: str) -> bytes:
    """
    Decode base64 encoded image string to bytes
    """
    try:
        # Remove data URL prefix if present
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        return base64.b64decode(base64_string)
    except Exception as e:
        logging.error(f"Error decoding base64 image: {str(e)}")
        raise


def evaluate_with_gemini(prompt: str, student_answer_image: bytes, pdf_content: Optional[bytes],
                         problem_image: Optional[bytes], api_key: str) -> str:
    """
    Call Google Gemini 2.5 Pro model to evaluate the student's answer
    
    Args:
        prompt: The filled prompt template
        student_answer_image: Student's answer as image bytes
        pdf_content: Optional reference PDF
        problem_image: Optional problem statement as image
        api_key: Google API key
    """
    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)
        
        # Use Gemini 2.5 Pro model optimized for multimodal understanding
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        # Prepare content parts with clear labeling for Gemini
        content_parts = [prompt]
        
        # Add problem image if provided (before student answer for better context)
        if problem_image:
            content_parts.append("\n[PROBLEM IMAGE]")
            content_parts.append({
                'mime_type': 'image/jpeg',
                'data': problem_image
            })
        
        # Add student's answer image
        content_parts.append("\n[STUDENT'S ANSWER IMAGE]")
        content_parts.append({
            'mime_type': 'image/jpeg',
            'data': student_answer_image
        })
        
        # Add reference PDF if provided
        if pdf_content:
            content_parts.append("\n[REFERENCE MATERIAL PDF]")
            content_parts.append({
                'mime_type': 'application/pdf',
                'data': pdf_content
            })
        
        # Generate response
        response = model.generate_content(content_parts)
        
        return response.text
        
    except Exception as e:
        logging.error(f"Error calling Gemini API: {str(e)}")
        raise


@app.route(route="evaluate", methods=["POST"])
def evaluate_student_answer(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function HTTP trigger to evaluate student's answer
    
    Expected JSON payload:
    {
        "image_bytes": "base64_encoded_student_answer_image",
        "class": "10",
        "subject": "Mathematics",
        "problem": "Text description of problem..." (optional if problem_image provided),
        "problem_image_bytes": "base64_encoded_problem_image" (optional),
        "reference_answer": "The solution is..." (optional, defaults to "Not provided"),
        "pdf_bytes": "base64_encoded_pdf" (optional),
        "pdf_blob_url": "https://..." (optional)
    }
    
    Note: Either 'problem' (text) or 'problem_image_bytes' (image) or both must be provided
    """
    logging.info('Python HTTP trigger function processing a request.')
    
    try:
        # Parse request body
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON in request body"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate required fields (reference_answer is now optional)
        required_fields = ["image_bytes", "class", "subject"]
        missing_fields = [field for field in required_fields if field not in req_body]
        
        if missing_fields:
            return func.HttpResponse(
                json.dumps({"error": f"Missing required fields: {', '.join(missing_fields)}"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate that at least problem text OR problem image is provided
        problem = req_body.get("problem")
        problem_image_b64 = req_body.get("problem_image_bytes")
        
        if not problem and not problem_image_b64:
            return func.HttpResponse(
                json.dumps({"error": "Either 'problem' (text) or 'problem_image_bytes' must be provided"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Extract inputs
        image_bytes_b64 = req_body.get("image_bytes")
        class_value = str(req_body.get("class"))
        subject = req_body.get("subject")
        reference_answer = req_body.get("reference_answer", "Not provided")  # Default if not provided
        pdf_bytes_b64 = req_body.get("pdf_bytes")
        pdf_blob_url = req_body.get("pdf_blob_url")
        
        # Decode student's answer image
        logging.info("Decoding student's answer image...")
        student_answer_bytes = decode_base64_image(image_bytes_b64)
        
        # Decode problem image if provided
        problem_image_bytes = None
        if problem_image_b64:
            logging.info("Decoding problem image...")
            problem_image_bytes = decode_base64_image(problem_image_b64)
        
        # Get PDF content (optional)
        pdf_content = None
        if pdf_bytes_b64:
            logging.info("Decoding PDF from base64...")
            pdf_content = decode_base64_image(pdf_bytes_b64)
        elif pdf_blob_url:
            logging.info(f"Fetching PDF from blob URL: {pdf_blob_url}")
            pdf_content = fetch_blob_content(pdf_blob_url, as_text=False)
        
        # Fetch prompt template
        logging.info("Fetching prompt template from blob storage...")
        prompt_template = fetch_prompt_from_blob()
        
        # Fill prompt with inputs
        # Use placeholder text if problem is provided as image only
        problem_text = problem if problem else "[Problem provided as image - see attached image]"
        
        logging.info("Filling prompt template...")
        filled_prompt = fill_prompt_template(
            prompt_template, 
            class_value, 
            subject, 
            problem_text, 
            reference_answer
        )
        
        # Get API key from Key Vault
        logging.info("Retrieving API key from Key Vault...")
        api_key = get_api_key_from_keyvault()
        
        # Call Gemini API
        logging.info("Calling Gemini API for evaluation...")
        evaluation_result = evaluate_with_gemini(
            filled_prompt,
            student_answer_bytes,
            pdf_content,
            problem_image_bytes,
            api_key
        )
        
        # Return successful response
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "evaluation": evaluation_result
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e)
            }),
            status_code=500,
            mimetype="application/json"
        )
