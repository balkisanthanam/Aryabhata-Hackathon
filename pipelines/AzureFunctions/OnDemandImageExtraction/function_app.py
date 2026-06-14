import azure.functions as func
import logging
import json
import os
import requests
import google.generativeai as genai
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import fitz  # PyMuPDF
from PIL import Image
import io
from typing import List, Dict, Any

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Azure Key Vault configuration
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL", "<KEY_VAULT_URL>")
KEY_VAULT_SECRET_NAME = os.environ.get("KEY_VAULT_SECRET_NAME", "<KEY_VAULT_SECRET_NAME>")
PROMPT_BLOB_URL = os.environ.get("PROMPT_BLOB_URL", "<PROMPT_BLOB_URL>")

# Gemini model configuration (from environment variable or default)
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3-pro-preview')


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
    Fetch the on-demand extraction prompt template from Azure Blob Storage
    """
    return fetch_blob_content(PROMPT_BLOB_URL, as_text=True)


def fill_prompt_template(prompt_template: str, exercise_name: str, problem_number: str) -> str:
    """
    Fill the prompt template with provided values
    """
    filled_prompt = prompt_template.replace("{Exercise Name}", exercise_name)
    filled_prompt = filled_prompt.replace("{Problem Number}", problem_number)
    return filled_prompt


def call_gemini_for_coordinates(prompt: str, pdf_content: bytes, api_key: str) -> Dict[str, Any]:
    """
    Call Google Gemini  model to extract bounding box coordinates
    
    Args:
        prompt: The filled prompt template
        pdf_content: PDF file as bytes
        api_key: Google API key
    
    Returns:
        JSON response with problem_id and segments containing bounding boxes
    """
    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)
        
        # Use configured Gemini model from environment variable
        logging.info(f"Using Gemini model: {GEMINI_MODEL}")
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # Prepare content parts
        content_parts = [
            prompt,
            {
                'mime_type': 'application/pdf',
                'data': pdf_content
            }
        ]
        
        # Generate response with 3-minute timeout for large model
        response = model.generate_content(
            content_parts,
            request_options={'timeout': 180}  # 3 minutes timeout
        )
        
        # Parse JSON response
        response_text = response.text.strip()
        
        logging.info(f"Raw Gemini response (first 500 chars): {response_text[:500]}")
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]  # Remove ```json
        elif response_text.startswith('```'):
            response_text = response_text[3:]  # Remove ```
        
        if response_text.endswith('```'):
            response_text = response_text[:-3]  # Remove ```
        
        response_text = response_text.strip()
        
        # Parse JSON
        coordinates_data = json.loads(response_text)
        
        logging.info(f"Parsed coordinates data: {json.dumps(coordinates_data)}")
        
        return coordinates_data
        
    except Exception as e:
        logging.error(f"Error calling Gemini API: {str(e)}")
        raise


def crop_problem_from_pdf(pdf_bytes: bytes, segments: List[Dict[str, Any]]) -> bytes:
    """
    Crop problem regions from PDF based on bounding box coordinates
    
    Args:
        pdf_bytes: PDF file as bytes
        segments: List of segments with page_number and bbox coordinates
                 bbox format: [ymin, xmin, ymax, xmax] (0-1000 scale)
    
    Returns:
        Image bytes (PNG format)
    """
    try:
        # Open PDF from bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []

        for idx, segment in enumerate(segments):
            page_num = segment['page_number'] - 1  # 0-indexed in PyMuPDF
            bbox_norm = segment['bbox']  # [ymin, xmin, ymax, xmax] (0-1000 scale)
            
            logging.info(f"Segment {idx+1}: Page {segment['page_number']}, BBox (0-1000): {bbox_norm}")
            
            page = doc[page_num]
            width, height = page.rect.width, page.rect.height
            
            # Convert normalized 0-1000 coordinates to PDF points
            y1 = (bbox_norm[0] / 1000) * height
            x1 = (bbox_norm[1] / 1000) * width
            y2 = (bbox_norm[2] / 1000) * height
            x2 = (bbox_norm[3] / 1000) * width
            
            logging.info(f"  Page size: {width}x{height}, PDF coords: x1={x1:.1f}, y1={y1:.1f}, x2={x2:.1f}, y2={y2:.1f}")
            
            # Crop
            rect = fitz.Rect(x1, y1, x2, y2)
            pix = page.get_pixmap(clip=rect, dpi=300)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)

        # Close the PDF document
        doc.close()

        # If multi-segment, stitch images vertically
        if len(images) > 1:
            total_height = sum(img.height for img in images)
            max_width = max(img.width for img in images)
            final_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))
            
            y_offset = 0
            for img in images:
                final_img.paste(img, (0, y_offset))
                y_offset += img.height
        else:
            final_img = images[0]
        
        # Convert to bytes
        img_byte_arr = io.BytesIO()
        final_img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        return img_byte_arr.getvalue()
        
    except Exception as e:
        logging.error(f"Error cropping PDF: {str(e)}")
        raise


@app.route(route="extract_image", methods=["POST"])
def extract_image_from_pdf(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function HTTP trigger to extract problem image from PDF
    
    Expected JSON payload:
    {
        "pdf_blob_url": "<PDF_BLOB_URL>",
        "exercise_name": "Exercise 8.1",
        "problem_number": "12"
    }
    
    Returns:
        Binary image data (PNG format) with appropriate headers
    """
    logging.info('OnDemand Image Extraction function processing a request.')
    
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
        
        # Validate required fields
        required_fields = ["pdf_blob_url", "exercise_name", "problem_number"]
        missing_fields = [field for field in required_fields if field not in req_body]
        
        if missing_fields:
            return func.HttpResponse(
                json.dumps({"error": f"Missing required fields: {', '.join(missing_fields)}"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Extract inputs
        pdf_blob_url = req_body.get("pdf_blob_url")
        exercise_name = req_body.get("exercise_name")
        problem_number = str(req_body.get("problem_number"))
        
        logging.info(f"Processing: PDF={pdf_blob_url}, Exercise={exercise_name}, Problem={problem_number}")
        
        # Fetch PDF from blob storage
        logging.info(f"Fetching PDF from blob URL: {pdf_blob_url}")
        pdf_content = fetch_blob_content(pdf_blob_url, as_text=False)
        
        # Fetch prompt template
        logging.info("Fetching prompt template from blob storage...")
        prompt_template = fetch_prompt_from_blob()
        
        # Fill prompt with inputs
        logging.info("Filling prompt template...")
        filled_prompt = fill_prompt_template(prompt_template, exercise_name, problem_number)
        
        # Get API key from Key Vault
        logging.info("Retrieving API key from Key Vault...")
        api_key = get_api_key_from_keyvault()
        
        # Call Gemini API to get bounding box coordinates
        logging.info("Calling Gemini API to extract coordinates...")
        coordinates_data = call_gemini_for_coordinates(filled_prompt, pdf_content, api_key)
        
        logging.info(f"Received coordinates: {json.dumps(coordinates_data)}")
        
        # Normalize the response format to handle different prompt outputs
        segments = None
        
        if 'segments' in coordinates_data:
            # Standard format with segments array
            segments = coordinates_data['segments']
        elif 'bbox' in coordinates_data:
            # Direct format - convert to segments array
            segments = [{
                'page_number': coordinates_data.get('page_number', 1),  # Default to page 1
                'bbox': coordinates_data['bbox']
            }]
        elif isinstance(coordinates_data, list):
            # Array of segments directly
            segments = coordinates_data
        
        # Validate we have segments
        if not segments or len(segments) == 0:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "No segments found in Gemini response",
                    "raw_response": coordinates_data
                }),
                status_code=422,
                mimetype="application/json"
            )
        
        # Extract image from PDF using the coordinates
        logging.info("Extracting and cropping image from PDF...")
        image_bytes = crop_problem_from_pdf(pdf_content, segments)
        
        logging.info(f"Successfully extracted image, size: {len(image_bytes)} bytes")
        
        # Return image as binary response
        return func.HttpResponse(
            body=image_bytes,
            status_code=200,
            mimetype="image/png",
            headers={
                "Content-Type": "image/png",
                "Content-Disposition": f"inline; filename=problem_{problem_number}.png"
            }
        )
        
    except json.JSONDecodeError as e:
        logging.error(f"JSON parsing error: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": f"Failed to parse Gemini response as JSON: {str(e)}"
            }),
            status_code=500,
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
