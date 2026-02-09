import google.generativeai as genai
import pymupdf  # PyMuPDF
from PIL import Image
import io

def extract_chapter_questions(pdf_path):
    doc = pymupdf.open(pdf_path)
    all_questions = []
    
    # Iterate pages with a "Look-Ahead" window
    for i in range(len(doc)):
        print(f"Processing Page {i+1}...")
        
        # 1. Prepare Images for Context Window (Current + Next)
        # We send TWO images to handle the "Spill-over"
        page_curr = doc.load_page(i)
        pix_curr = page_curr.get_pixmap(dpi=300)
        img_curr = Image.open(io.BytesIO(pix_curr.tobytes()))
        
        inputs = [img_curr]
        has_next_page = False
        
        if i + 1 < len(doc):
            has_next_page = True
            page_next = doc.load_page(i+1)
            pix_next = page_next.get_pixmap(dpi=300)
            img_next = Image.open(io.BytesIO(pix_next.tobytes()))
            inputs.append(img_next)

        # 2. The Context-Aware Prompt
        # We explicitly tell it to handle the split scenarios we discussed
        prompt = f"""
        You are a strict Educational Data Extractor.
        Input: Image 1 (Page {i+1}) and Image 2 (Page {i+2} - context).
        
        TASK: Extract every exercise question that **STARTS** on Image 1.
        
        CRITICAL RULES FOR "SPILL-OVER":
        1. **Text Split:** If a question starts on Image 1 but finishes on Image 2, combine the text.
        2. **Figure Split:** If a question on Image 1 refers to a Figure (e.g. "Fig 12.3") located on Image 2, capture the bounding box from Image 2.
           - Output: "visual_source": "next_page"
        3. **Tables:** Do NOT crop tables. Transcribe them as Markdown in 'question_text'.
        4. **Adjacent Figures:** For figures on Image 1, set "visual_source": "current_page".
        
        Output JSON Schema:
        [
          {{
            "question_id": "12.3",
            "text": "Full question text...",
            "visual_required": true,
            "visual_data": {{
               "source": "current_page" | "next_page",
               "box_2d": [ymin, xmin, ymax, xmax] (0-1000 scale)
            }}
          }}
        ]
        """
        
        # 3. Call Model (Gemini 1.5 Pro - Vision)
        try:
            response = client.models.generate_content(
                model="gemini-1.5-pro",
                contents=[prompt, *inputs],
                config={"response_mime_type": "application/json"}
            )
            
            # 4. Parsing & Cropping Logic
            import json
            batch_data = json.loads(response.text)
            
            for q in batch_data:
                if q.get('visual_required'):
                    # Decision Logic: Which page to crop?
                    source = q['visual_data']['source']
                    coords = q['visual_data']['box_2d']
                    
                    if source == "current_page":
                        # Crop from page_curr using 'coords'
                        pass 
                    elif source == "next_page" and has_next_page:
                        # Crop from page_next using 'coords'
                        pass
                
                all_questions.append(q)
                
        except Exception as e:
            print(f"Error on page {i}: {e}")

    return all_questions