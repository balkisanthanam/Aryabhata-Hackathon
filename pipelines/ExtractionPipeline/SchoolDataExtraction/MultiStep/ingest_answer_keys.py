import os
import sys
import json
import logging
import fitz # PyMuPDF
import pathlib
import shutil

from config import PipelineConfig
from gemini_client import GeminiClient
from blob_client import BlobClient
from db_client import DatabaseClient
import argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def extract_json_from_response(text):
    text = text.strip()
    if text.startswith("```json"):
        text = text.split("```json", 1)[1]
        if "```" in text:
            text = text[:text.rfind("```")].strip()
    elif text.startswith("```"):
        text = text.split("```", 1)[1]
        if "```" in text:
            text = text[:text.rfind("```")].strip()
            
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON. Output was: {text[:100]}...")
        with open("failed_parse.json.txt", "w", encoding="utf-8") as f:
            f.write(text)
        return None

def parse_answer_key_pdf(pdf_blob_path: str, cache_file: str = "ans_parsed_cache.json"):
    config = PipelineConfig()
    vision_model = GeminiClient(config)
    
    local_pdf = pdf_blob_path
    logger.info(f"Using local PDF {local_pdf}")
    
    # 1. State Management Loading
    state = {
        "status": "IN_PROGRESS",
        "completed_chunks": [],
        "total_chunks": 0,
        "extracted_data": {}
    }
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                loaded_cache = json.load(f)
                
            # Migration from legacy flat cache array to structured cache state
            if isinstance(loaded_cache, list):
                logger.info("Migrating legacy cache flat array to structured cache state.")
                for chapter in loaded_cache:
                    ch_num = str(chapter.get("chapter_number"))
                    state["extracted_data"][ch_num] = chapter
                # legacy cache in the temp process implies it was fully processed, but to be robust
                # we'll say it's ready for DB ONLY if it looks full
                state["status"] = "READY_FOR_DB"
            else:
                state.update(loaded_cache)
            logger.info(f"Loaded cache state: Status={state['status']}, Chunks Done={len(state['completed_chunks'])}")
        except json.JSONDecodeError:
            logger.warning(f"Cache file {cache_file} was corrupted. Starting fresh.")
    
    if state["status"] == "READY_FOR_DB":
        logger.info("Cache shows extraction is complete. Sending to DB directly.")
        return list(state["extracted_data"].values())

    # 2. Dynamic Chunking
    doc = fitz.open(local_pdf)
    total_pages = len(doc)
    PAGES_PER_CHUNK = 5
    total_chunks = (total_pages + PAGES_PER_CHUNK - 1) // PAGES_PER_CHUNK
    state["total_chunks"] = total_chunks
    
    temp_dir = "temp_chunks"
    os.makedirs(temp_dir, exist_ok=True)
    
    prompt = """
    This is a chunk of an Answer Key section from an NCERT textbook. It contains answers organized by Chapter.
    Extract ALL the answers strictly into the following JSON format. If a chapter continues from a previous page, start or continue it.
    [
        {
            "chapter_number": 1,
            "answers": [
                {
                    "question_ref": "1.1",
                    "answer_text": "Option (a) or the short answer text here."
                }
            ]
        }
    ]
    Format Rules:
    1. Output MUST be valid JSON.
    2. 'chapter_number' must be an integer. If the chapter is written as 'Chapter 1', extract 1.
    3. 'question_ref' should be the exact reference number used in the book (e.g., "1.1", "2.14", "3.1 (i)").
    4. Provide the exact text of the answer in 'answer_text'. Do not include the question.
    """
    
    try:
        for chunk_idx in range(total_chunks):
            if chunk_idx in state["completed_chunks"]:
                logger.info(f"Skipping chunk {chunk_idx} (already processed)")
                continue
                
            start_page = chunk_idx * PAGES_PER_CHUNK
            end_page = min(start_page + PAGES_PER_CHUNK - 1, total_pages - 1)
            
            logger.info(f"Processing chunk {chunk_idx}/{total_chunks-1} (Pages {start_page}-{end_page})")
            
            chunk_doc = fitz.open()
            chunk_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
            chunk_path = os.path.join(temp_dir, f"chunk_{chunk_idx}.pdf")
            chunk_doc.save(chunk_path)
            chunk_doc.close()
            
            # API Call
            response = vision_model.generate(
                model_config=config.extraction_model,
                prompt=prompt,
                document_path=pathlib.Path(chunk_path)
            )
            
            try:
                os.remove(chunk_path) # Cleanup aggressively
            except:
                pass
            
            parsed_json = extract_json_from_response(response.text)
            if not parsed_json:
                 logger.error(f"Failed to parse JSON for chunk {chunk_idx}. Halting pipeline to preserve state.")
                 return None
                 
            # 3. Merging logic
            for chapter in parsed_json:
                ch_num = str(chapter.get("chapter_number"))
                if not ch_num or ch_num == "None":
                    continue
                
                if ch_num not in state["extracted_data"]:
                    state["extracted_data"][ch_num] = {
                        "chapter_number": chapter.get("chapter_number"),
                        "answers": []
                    }
                
                state["extracted_data"][ch_num]["answers"].extend(chapter.get("answers", []))
                
            state["completed_chunks"].append(chunk_idx)
            
            # Save checkpoint
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
                
            logger.info(f"Successfully checkpointed chunk {chunk_idx}")
            
    finally:
        doc.close()
        
    # Check if we are fully done
    if len(state["completed_chunks"]) >= state["total_chunks"]:
        state["status"] = "READY_FOR_DB"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            
        try:
             shutil.rmtree(temp_dir)
        except:
             pass
             
        logger.info("All chunks processed successfully. Ready for DB ingestion.")
        return list(state["extracted_data"].values())
    else:
        logger.warning(f"Pipeline ended prematurely. Processed {len(state['completed_chunks'])}/{state['total_chunks']} chunks.")
        return None

def ingest_to_db(parsed_data: list, class_id: str, subject_name: str):
    db = DatabaseClient(use_managed_identity=True)
    import re
    
    with db.connect() as conn:
        with conn.cursor() as cur:
            for chapter in parsed_data:
                chap_num = chapter.get("chapter_number")
                if not chap_num:
                    continue
                    
                cur.execute("""
                    SELECT chapterid FROM chapterdata 
                    WHERE class = %s AND subject = %s AND chapternumber = %s
                """, (str(class_id), subject_name, str(chap_num)))
                
                chap_row = cur.fetchone()
                if not chap_row:
                    logger.warning(f"Chapter {chap_num} not found in DB for Class {class_id} {subject_name}. Skipping chapter.")
                    continue
                    
                chapter_id = chap_row[0]
                
                ans_list = []
                if "answers" in chapter:
                    ans_list = chapter.get("answers", [])
                elif "exercise_number" in chapter and "question_number" in chapter:
                    ex_num = chapter.get("exercise_number")
                    if "Misc" in str(ex_num) or "misc" in str(ex_num):
                        q_ref = f"Misc {chapter.get('question_number')}"
                    else:
                        q_ref = f"{ex_num}.{chapter.get('question_number')}"
                    ans_list = [{"question_ref": q_ref, "answer_text": chapter.get("answer_text", "")}]
                
                for answer in ans_list:
                    q_ref = answer.get("question_ref")
                    if not q_ref:
                        q_ref = answer.get("question_reference")
                    ans_text = answer.get("answer_text")
                    
                    if not q_ref or not ans_text:
                        continue
                        
                    q_ref_mapped = q_ref.strip()
                    m1 = re.match(r"^(\d+)\.(\d+)[\.\s]+(\d+)", q_ref_mapped)
                    if m1:
                        q_ref_mapped = f"EXERCISE_{m1.group(1)}_{m1.group(2)}_Q{m1.group(3)}"
                    else:
                        m2 = re.search(r"(?i)misc.*?(\d+)[^\d]*$", q_ref_mapped)
                        if m2:
                            q_ref_mapped = f"MISCELLANEOUS_EXERCISE_ON_CHAPTER_{chap_num}_Q{m2.group(1)}"
                            
                    cur.execute("""
                        SELECT q.questionid 
                        FROM questiondata q
                        JOIN exercisedata e ON q.exerciseid = e.exerciseid
                        WHERE e.chapterid = %s AND q.question_ref = %s
                    """, (chapter_id, q_ref_mapped))
                    
                    q_row = cur.fetchone()
                    if not q_row:
                        logger.warning(f"Question Ref {q_ref} (mapped to {q_ref_mapped}) not found for Chapter {chap_num}. Skipping.")
                        continue
                        
                    q_id = q_row[0]
                    
                    cur.execute("""
                        UPDATE questiondata
                        SET answer_key = %s
                        WHERE questionid = %s
                    """, (json.dumps({"answer": ans_text}), q_id))
                    
                    logger.info(f"Updated answer key for QID {q_id} (Ref: {q_ref_mapped})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blob-path", required=True)
    parser.add_argument("--class", dest="class_id", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--cache-file", default="ans_parsed_cache.json")
    
    args = parser.parse_args()
    
    parsed = parse_answer_key_pdf(args.blob_path, args.cache_file)
    if parsed:
        ingest_to_db(parsed, args.class_id, args.subject)


