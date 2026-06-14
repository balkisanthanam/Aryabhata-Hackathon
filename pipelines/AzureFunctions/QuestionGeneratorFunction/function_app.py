import os
import azure.functions as func
import logging
import json
import random
import cgi
import csv
import urllib.request
import io
import time
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, unquote
from abc import ABC, abstractmethod
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.cosmos import CosmosClient
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, ContentSettings, generate_blob_sas
import openai
try:
    import google.generativeai as genai
except ImportError:
    genai = None

# Manual debugpy setup for reliable breakpoints
try:
    import debugpy
    if not debugpy.is_client_connected():
        debugpy.listen(("0.0.0.0", 5678))
        logging.info("Debugpy listening on port 5678")
except Exception as e:
    logging.warning(f"Could not start debugpy: {e}")

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

CSV_MAPPING = {
    "Science": os.environ.get("SCIENCE_HISTORY_CSV_URL", "<SCIENCE_HISTORY_CSV_URL>"),
    "Hindi": os.environ.get("HINDI_HISTORY_CSV_URL", "<HINDI_HISTORY_CSV_URL>"),
    "Social Studies": os.environ.get("SOCIAL_STUDIES_HISTORY_CSV_URL", "<SOCIAL_STUDIES_HISTORY_CSV_URL>")
}

DIFFICULTY_MAP = {
    "All": [],
    "None": [],
    "Easy": ["Basic", "Easy", "Simple"],
    "Medium": ["Medium", "Average"],
    "Difficult": ["Difficult", "Hard", "Advanced"]
}

COSMOS_INTERACTIONS_CONTAINER = os.environ.get("COSMOS_INTERACTIONS_CONTAINER", "question_interactions")
SMART_SELECTION_SCORE_THRESHOLD = float(os.environ.get("SMART_SELECTION_SCORE_THRESHOLD", "0.6"))
PAPER_BLOB_PREFIX = os.environ.get("PAPER_BLOB_PREFIX", "papers").strip("/")


def _parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _normalize_difficulty_tokens(difficulty: str) -> list:
    if difficulty is None:
        return []
    diff_value = str(difficulty).strip()
    if not diff_value or diff_value.lower() in ("none", "all"):
        return []
    mapped = DIFFICULTY_MAP.get(diff_value, [diff_value])
    return [str(token).strip().lower() for token in mapped if str(token).strip()]


def _extract_row_marks(row: dict) -> int:
    if not isinstance(row, dict):
        return 0

    for key in ("Marks", "marks", "mark"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(str(value).strip())
        except Exception:
            continue

    return 0


def _extract_row_chapter(row: dict) -> str:
    if not isinstance(row, dict):
        return ""

    for key in ("Chapter", "chapterName", "chapter", "chapterKey"):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text

    return ""


def _normalize_chapter_filters(chapters_data) -> list:
    if not chapters_data:
        return []

    if isinstance(chapters_data, str):
        chapters = [chapters_data]
    elif isinstance(chapters_data, list):
        chapters = chapters_data
    else:
        return []

    normalized = []
    seen = set()
    for chapter in chapters:
        chapter_text = str(chapter).strip()
        if not chapter_text:
            continue
        key = chapter_text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(chapter_text)

    return normalized


def _filter_questions_by_chapters(questions_data: list, selected_chapters: list) -> list:
    chapter_filters = {chapter.lower() for chapter in _normalize_chapter_filters(selected_chapters)}
    if not chapter_filters:
        return questions_data

    filtered_rows = []
    for row in questions_data:
        chapter = _extract_row_chapter(row).lower()
        if chapter and chapter in chapter_filters:
            filtered_rows.append(row)

    return filtered_rows


def _build_chapter_list(questions_data: list) -> list:
    chapters = []
    seen = set()

    for row in questions_data:
        chapter = _extract_row_chapter(row)
        if not chapter:
            continue
        chapter_key = chapter.lower()
        if chapter_key in seen:
            continue
        seen.add(chapter_key)
        chapters.append(chapter)

    return sorted(chapters, key=lambda value: value.lower())


def _select_questions_by_marks_distribution(questions_data: list, count: int) -> list:
    distribution_map = {
        5: {1: 2, 2: 1, 3: 1, 5: 1},
        10: {1: 4, 2: 3, 3: 2, 5: 1},
        15: {1: 6, 2: 4, 3: 3, 5: 2},
        20: {1: 8, 2: 5, 3: 4, 5: 3}
    }

    target_distribution = distribution_map.get(count)
    if not target_distribution:
        return []

    pools = {1: [], 2: [], 3: [], 5: []}
    for row in questions_data:
        marks = _extract_row_marks(row)
        if marks in pools:
            pools[marks].append(row)

    selected_rows = []
    for marks, needed in target_distribution.items():
        pool = pools.get(marks, [])
        if not pool:
            continue

        if len(pool) >= needed:
            selected_rows.extend(random.sample(pool, needed))
        else:
            selected_rows.extend(pool)
            while len([q for q in selected_rows if _extract_row_marks(q) == marks]) < needed:
                selected_rows.append(random.choice(pool))

    if len(selected_rows) > count:
        return random.sample(selected_rows, count)

    if len(selected_rows) < count and questions_data:
        while len(selected_rows) < count:
            selected_rows.append(random.choice(questions_data))

    return selected_rows


def _build_storage_signing_context():
    conn_str = (
        os.environ.get("ANSWERSHEET_STORAGE_CONNECTION_STRING")
        or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        or os.environ.get("AzureWebJobsStorage")
    )
    # ✅ FIXED: Use the same container resolution as _get_answersheet_container_client()
    container = _resolve_answersheet_container_name()

    if not conn_str or not container:
        return None

    parts = {}
    for chunk in conn_str.split(";"):
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            parts[key] = value

    account_name = parts.get("AccountName")
    account_key = parts.get("AccountKey")

    if not account_name or not account_key:
        return None

    logging.info(f"[ANSWERSHEET_TRACE] Storage signing context: account={account_name}, container={container}")
    return {
        "account_name": account_name,
        "account_key": account_key,
        "container": container
    }


def _resolve_answersheet_container_name() -> str:
    explicit_name = os.environ.get("ANSWERSHEET_CONTAINER_NAME")
    if explicit_name:
        return explicit_name.strip()

    url_candidates = [
        os.environ.get("ANSWERSHEET_CONTAINER_URL"),
        os.environ.get("CONTAINER_URL")
    ]
    for url in url_candidates:
        if not url:
            continue
        try:
            parsed = urlparse(url)
            candidate = (parsed.path or "").strip("/")
            if candidate:
                return candidate.split("/")[0]
        except Exception:
            continue

    return "answersheet"


def _get_answersheet_container_client():
    # Credentials-only flow (no SAS URL in backend).
    conn_str = (
        os.environ.get("ANSWERSHEET_STORAGE_CONNECTION_STRING")
        or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        or os.environ.get("AzureWebJobsStorage")
    )
    if not conn_str:
        return None

    try:
        service = BlobServiceClient.from_connection_string(conn_str)
        container_name = _resolve_answersheet_container_name()
        return service.get_container_client(container_name)
    except Exception as e:
        logging.error(f"Failed to create answersheet container client: {e}")
        return None


def _guess_extension(filename: str, content_type: str) -> str:
    if filename and "." in filename:
        return os.path.splitext(filename)[1].lower()

    mime_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf"
    }
    return mime_map.get((content_type or "").lower(), ".bin")


def _get_file_value(file_obj, attribute: str, default=None):
    if isinstance(file_obj, dict):
        return file_obj.get(attribute, default)
    return getattr(file_obj, attribute, default)


def _extract_upload_bytes(file_obj):
    if isinstance(file_obj, dict):
        body = file_obj.get("body")
        if isinstance(body, str):
            return body.encode("utf-8")
        return body

    if hasattr(file_obj, "read"):
        data = file_obj.read()
        if isinstance(data, str):
            return data.encode("utf-8")
        return data

    body = getattr(file_obj, "body", None)
    if isinstance(body, str):
        return body.encode("utf-8")
    return body


def _extract_uploaded_files(file_collection, field_name: str):
    if not file_collection:
        return []

    if hasattr(file_collection, "getlist"):
        return [file for file in file_collection.getlist(field_name) if file]

    if isinstance(file_collection, dict):
        raw_value = file_collection.get(field_name)
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return [file for file in raw_value if file]
        return [raw_value]

    return []


def _parse_multipart_request(req: func.HttpRequest):
    content_type = req.headers.get("content-type") or req.headers.get("Content-Type") or ""
    body = req.get_body() or b""
    if not body or "multipart/form-data" not in content_type.lower():
        return {}, {}

    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(body)),
    }

    form = cgi.FieldStorage(fp=io.BytesIO(body), environ=environ, keep_blank_values=True)

    fields = {}
    files_by_field = {}

    if not getattr(form, "list", None):
        return fields, files_by_field

    for item in form.list:
        if item.filename:
            files_by_field.setdefault(item.name, []).append({
                "filename": item.filename,
                "content_type": item.type or "application/octet-stream",
                "body": item.file.read() if hasattr(item, "file") and item.file else (item.value.encode("utf-8") if isinstance(item.value, str) else item.value),
            })
        else:
            fields[item.name] = item.value

    return fields, files_by_field


def _upload_answer_sheet_files(files, paper_id: str) -> list:
    container_client = _get_answersheet_container_client()
    signing_ctx = _build_storage_signing_context()

    if not container_client or not signing_ctx:
        raise ValueError("Storage configuration missing")

    upload_batch_id = paper_id or str(uuid.uuid4())
    upload_prefix = f"student-uploads/{upload_batch_id}/{int(time.time())}"
    uploaded_urls = []
    
    logging.info(f"[ANSWERSHEET_TRACE] Starting upload of {len(files)} files to prefix: {upload_prefix}")

    for index, file_obj in enumerate(files):
        filename = _get_file_value(file_obj, "filename", "") or f"answersheet_{index + 1}"
        content_type = (
            _get_file_value(file_obj, "content_type", "")
            or _get_file_value(file_obj, "mimetype", "")
            or "application/octet-stream"
        )
        file_bytes = _extract_upload_bytes(file_obj)

        if not file_bytes:
            logging.warning(f"[ANSWERSHEET_TRACE] Skipping file {index+1}: no bytes extracted")
            continue

        logging.info(f"[ANSWERSHEET_TRACE] File {index+1}: {filename} ({len(file_bytes)} bytes, {content_type})")
        
        extension = _guess_extension(filename, content_type)
        blob_name = f"{upload_prefix}/page_{index + 1}{extension}"

        container_client.upload_blob(
            name=blob_name,
            data=file_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )
        signed_url = _sign_blob_reference(blob_name, signing_ctx, force_resign=True)
        uploaded_urls.append(signed_url)
        logging.info(f"[ANSWERSHEET_TRACE] File {index+1} uploaded to blob: {blob_name}")
        logging.info(f"[ANSWERSHEET_TRACE] File {index+1} signed URL: {signed_url[:100]}...")

    logging.info(f"[ANSWERSHEET_TRACE] Upload complete. Total files uploaded: {len(uploaded_urls)}")
    return uploaded_urls


def _download_json_blob(container_client, blob_name: str):
    try:
        data = container_client.download_blob(blob_name).readall()
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        logging.warning(f"Failed to read history blob {blob_name}: {e}")
        return None


def _save_history_paper(container_client, paper: dict):
    paper_id = str(paper.get("id", "")).strip()
    if not paper_id:
        raise ValueError("paper.id is required")

    blob_name = f"{PAPER_BLOB_PREFIX}/{paper_id}.json"
    body = json.dumps(paper, ensure_ascii=False)
    container_client.upload_blob(name=blob_name, data=body.encode("utf-8"), overwrite=True)
    return blob_name


def _delete_history_paper(container_client, paper_id: str, blob_name: str = "") -> bool:
    if blob_name:
        try:
            container_client.delete_blob(blob_name, delete_snapshots="include")
            return True
        except Exception as e:
            logging.warning(f"Delete by blob name failed for {blob_name}: {e}")

    candidate = f"{PAPER_BLOB_PREFIX}/{paper_id}.json"
    try:
        container_client.delete_blob(candidate, delete_snapshots="include")
        return True
    except Exception:
        pass

    return False


def _load_history_paper(container_client, paper_id: str):
    if not paper_id:
        return None

    blob_name = f"{PAPER_BLOB_PREFIX}/{paper_id}.json"
    paper = _download_json_blob(container_client, blob_name)
    return paper if isinstance(paper, dict) else None


def _is_sas_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return "sig=" in (parsed.query or "")
    except Exception:
        return False


def _extract_blob_name(image_ref: str, default_container: str) -> str:
    if not image_ref:
        return ""

    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        parsed = urlparse(image_ref)
        path = (parsed.path or "").lstrip("/")
        if not path:
            return ""

        path_parts = path.split("/", 1)
        if len(path_parts) != 2 or not path_parts[1]:
            return ""

        container_name, blob_name = path_parts
        if default_container and container_name != default_container:
            return ""

        return unquote(blob_name)
    return image_ref.lstrip("/")


def _sign_blob_reference(image_ref: str, signing_ctx: dict, expiry_minutes: int = 60, force_resign: bool = False) -> str:
    if not image_ref:
        return ""

    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        if _is_sas_url(image_ref) and not force_resign:
            return image_ref

    blob_name = _extract_blob_name(image_ref, signing_ctx["container"])
    if not blob_name:
        return image_ref

    sas_token = generate_blob_sas(
        account_name=signing_ctx["account_name"],
        container_name=signing_ctx["container"],
        blob_name=blob_name,
        account_key=signing_ctx["account_key"],
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
    )

    return (
        f"https://{signing_ctx['account_name']}.blob.core.windows.net/"
        f"{signing_ctx['container']}/{blob_name}?{sas_token}"
    )


def _renew_question_image_urls(question: dict, signing_ctx: dict) -> int:
    renewed = 0

    image_url = question.get("imageUrl")
    if isinstance(image_url, str) and image_url.strip():
        try:
            question["imageUrl"] = _sign_blob_reference(image_url.strip(), signing_ctx, force_resign=True)
            renewed += 1
        except Exception as e:
            logging.warning(f"Failed to renew imageUrl: {str(e)}")

    image_urls = question.get("imageUrls")
    if isinstance(image_urls, list) and image_urls:
        updated_urls = []
        for url in image_urls:
            if not isinstance(url, str) or not url.strip():
                continue
            try:
                updated_urls.append(_sign_blob_reference(url.strip(), signing_ctx, force_resign=True))
                renewed += 1
            except Exception as e:
                logging.warning(f"Failed to renew imageUrls entry: {str(e)}")
                updated_urls.append(url)

        question["imageUrls"] = updated_urls

    return renewed


def _load_questions_from_csv(subject: str, difficulty: str) -> list:
    csv_url = CSV_MAPPING.get(subject)
    questions_data = []

    if not csv_url:
        return questions_data

    try:
        logging.info(f"Fetching CSV from {csv_url}")
        with urllib.request.urlopen(csv_url) as response:
            csv_content = response.read().decode('utf-8')
            f = io.StringIO(csv_content)
            reader = csv.DictReader(f)

            target_difficulties = _normalize_difficulty_tokens(difficulty)
            for row in reader:
                row_difficulty = row.get('Difficulty', '').strip()
                if not target_difficulties:
                    questions_data.append(row)
                elif not row_difficulty or any(td == row_difficulty.lower() for td in target_difficulties):
                    questions_data.append(row)

        logging.info(f"CSV source returned {len(questions_data)} questions for {subject}/{difficulty}")
    except Exception as e:
        logging.error(f"Error fetching or parsing CSV: {str(e)}")

    return questions_data


def _match_answer_index(options: list, answer_text: str) -> int:
    if not options:
        return 0

    answer_text_norm = (answer_text or "").strip().lower()
    if not answer_text_norm:
        return 0

    for idx, option in enumerate(options):
        option_norm = str(option).strip().lower()
        if option_norm == answer_text_norm:
            return idx
        if option_norm.startswith(answer_text_norm):
            return idx
        if answer_text_norm.startswith(option_norm):
            return idx

    if len(answer_text_norm) >= 2 and answer_text_norm[1] == "." and answer_text_norm[0].isalpha():
        candidate = ord(answer_text_norm[0]) - ord('a')
        if 0 <= candidate < len(options):
            return candidate

    return 0


def _normalize_mistakes_list(mistakes_data) -> list:
    if isinstance(mistakes_data, list):
        return [str(m).strip() for m in mistakes_data if str(m).strip()]
    if isinstance(mistakes_data, str) and mistakes_data.strip():
        return [s.strip() for s in re.split(r"[\n;,]", mistakes_data) if s.strip()]
    return []


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_text_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_glossary_list(value) -> list:
    if not isinstance(value, list):
        return []

    glossary = []
    for item in value:
        if not isinstance(item, dict):
            continue
        term = _to_text(item.get("term"))
        meaning = _to_text(item.get("meaning"))
        if term and meaning:
            glossary.append({"term": term, "meaning": meaning})

    return glossary


def _build_schema_driven_explain_payload(req_body: dict, question_text: str) -> dict | None:
    question_item = req_body.get("questionItem") if isinstance(req_body.get("questionItem"), dict) else {}

    if not question_item:
        return None

    explain_data = question_item.get("explainData") if isinstance(question_item.get("explainData"), dict) else {}
    explain_question = question_item.get("explainQuestion") if isinstance(question_item.get("explainQuestion"), dict) else {}
    explain_obj = explain_data if explain_data else explain_question
    solution_obj = question_item.get("solutionData") if isinstance(question_item.get("solutionData"), dict) else {}

    simplified_question = _to_text(
        explain_obj.get("simplifiedQuestion")
        or explain_obj.get("simplified_question_text")
        or question_item.get("simplifiedQuestion")
        or question_text
    )

    what_to_do = _as_text_list(
        explain_obj.get("whatToDo")
        or explain_obj.get("hints")
        or explain_obj.get("steps")
        or question_item.get("whatToDo")
        or solution_obj.get("steps")
    )

    glossary = _as_glossary_list(
        explain_obj.get("glossary") or question_item.get("glossary")
    )

    common_mistakes = _as_text_list(
        explain_obj.get("commonMistakes")
        or solution_obj.get("commonMistakes")
        or question_item.get("commonMistakes")
    )

    final_explanation = _to_text(
        explain_obj.get("finalExplanation")
        or explain_obj.get("explanation")
        or solution_obj.get("finalAnswer")
        or solution_obj.get("summary")
        or question_item.get("finalExplanation")
        or question_item.get("explanation")
        or question_item.get("solutionText")
    )

    answer_text = _to_text(
        question_item.get("answerText") or solution_obj.get("answerText") or req_body.get("answerText")
    )

    encouragement = _to_text(
        explain_obj.get("encouragement") or req_body.get("encouragement") or "You can do this. Take one small step at a time."
    )

    # If there is no meaningful schema payload, caller should fallback to LLM.
    if not any([what_to_do, glossary, common_mistakes, final_explanation, simplified_question]):
        return None

    return {
        "simplifiedQuestion": simplified_question or question_text,
        "whatToDo": what_to_do,
        "glossary": glossary,
        "encouragement": encouragement,
        "commonMistakes": common_mistakes,
        "finalExplanation": final_explanation,
        "answerText": answer_text,
        "source": "kb"
    }


def _load_questions_from_cosmos(subject: str, difficulty: str, req_body: dict) -> list:
    endpoint = os.environ.get("COSMOS_ENDPOINT")
    key = os.environ.get("COSMOS_KEY")
    database_name = os.environ.get("COSMOS_DATABASE")
    container_name = os.environ.get("COSMOS_CONTAINER")

    if not endpoint or not key or not database_name or not container_name:
        logging.warning("Cosmos source selected but COSMOS_* configuration is incomplete.")
        return []

    try:
        cosmos_client = CosmosClient(endpoint, key)
        container = cosmos_client.get_database_client(database_name).get_container_client(container_name)

        normalized_subject = str(subject or "").strip().lower()
        normalized_difficulties = _normalize_difficulty_tokens(difficulty)

        query_parts = [
            "SELECT * FROM c",
            "WHERE LOWER(c.subject) = @subject",
            "AND c.status = @status"
        ]
        parameters = [
            {"name": "@subject", "value": normalized_subject},
            {"name": "@status", "value": "approved"}
        ]

        if normalized_difficulties:
            query_parts.append("AND ARRAY_CONTAINS(@difficulties, LOWER(c.difficulty))")
            parameters.append({"name": "@difficulties", "value": normalized_difficulties})

        optional_filters = {
            "curriculum": req_body.get("curriculum"),
            "grade": req_body.get("grade"),
            "chapterKey": req_body.get("chapterKey"),
            "chapterName": req_body.get("chapterName"),
            "school": req_body.get("school"),
            "type": req_body.get("type")
        }

        for field_name, field_value in optional_filters.items():
            if field_value:
                param_name = f"@{field_name}"
                query_parts.append(f"AND LOWER(c.{field_name}) = {param_name}")
                parameters.append({"name": param_name, "value": str(field_value).strip().lower()})

        query = "\n".join(query_parts)
        items = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))

        signing_ctx = _build_storage_signing_context()
        question_rows = []
        for item in items:
            options = item.get("options", [])
            if not isinstance(options, list):
                options = []

            raw_image_urls = item.get("imageUrls") or []
            if not isinstance(raw_image_urls, list):
                raw_image_urls = []

            # Backward compatibility: some documents keep image metadata in images[] only.
            if not raw_image_urls:
                image_objects = item.get("images") or []
                if isinstance(image_objects, list):
                    for image_obj in image_objects:
                        if not isinstance(image_obj, dict):
                            continue
                        blob_name = image_obj.get("blobName")
                        blob_url = image_obj.get("blobUrl")
                        if blob_name:
                            raw_image_urls.append(str(blob_name))
                        elif blob_url:
                            raw_image_urls.append(str(blob_url))

            signed_image_urls = []
            for image_ref in raw_image_urls:
                try:
                    signed_image_urls.append(_sign_blob_reference(image_ref, signing_ctx) if signing_ctx else image_ref)
                except Exception as sign_err:
                    logging.warning(f"Failed to sign image URL for item {item.get('id')}: {str(sign_err)}")
                    signed_image_urls.append(image_ref)

            question_rows.append({
                "Question": item.get("questionText", "") or "",
                "Type": item.get("type", "subjective") or "subjective",
                "Marks": str(item.get("marks", 1) or 1),
                "Chapter": item.get("chapterName", "") or "",
                "Portion": item.get("concept", "") or "",
                "Sub Topic": item.get("subConcept", "") or "",
                "Options": ",".join([str(option).strip() for option in options]),
                "Answer": str(_match_answer_index(options, item.get("answerText", ""))),
                "ImageUrls": "#".join([url for url in signed_image_urls if url]),
                "QuestionId": item.get("id", ""),
                "SolutionText": item.get("solutionText", "") or "",
                "Explanation": item.get("explanation", "") or "",
                "CommonMistakes": item.get("commonMistakes", []) or [],
                "AnswerText": item.get("answerText", "") or "",
                "ExplainData": item.get("explainData") or item.get("explanationData") or item.get("explain") or {},
                "ExplainQuestion": item.get("explainQuestion") or {},
                "SolutionData": item.get("solutionData") or item.get("solution") or {},
                "GlossaryData": item.get("glossary") or [],
                "WhatToDoData": item.get("whatToDo") or item.get("steps") or []
            })

        logging.info(f"Cosmos source returned {len(question_rows)} questions for {subject}/{difficulty}")
        return question_rows
    except Exception as e:
        logging.error(f"Error querying Cosmos question bank: {str(e)}")
        return []


def _get_interactions_container():
    endpoint = os.environ.get("COSMOS_ENDPOINT")
    key = os.environ.get("COSMOS_KEY")
    database_name = os.environ.get("COSMOS_DATABASE")

    if not endpoint or not key or not database_name:
        return None

    try:
        cosmos_client = CosmosClient(endpoint, key)
        return cosmos_client.get_database_client(database_name).get_container_client(COSMOS_INTERACTIONS_CONTAINER)
    except Exception as e:
        logging.warning(f"Could not connect to interactions container: {e}")
        return None


def _load_student_interaction_summary(user_id: str, subject: str) -> dict:
    try:
        container = _get_interactions_container()
        if not container:
            return {"seen": set(), "explained": set(), "poor": set()}

        items = list(container.query_items(
            query="SELECT c.cosmosId, c.type, c.score, c.maxMarks FROM c WHERE c.userId = @uid AND c.subject = @sub",
            parameters=[
                {"name": "@uid", "value": str(user_id)},
                {"name": "@sub", "value": str(subject).strip().lower()}
            ],
            enable_cross_partition_query=True
        ))

        seen = set()
        explained = set()
        poor = set()

        for item in items:
            cosmos_id = _to_text(item.get("cosmosId"))
            if not cosmos_id:
                continue

            event_type = _to_text(item.get("type"))
            if event_type in ("displayed", "explain_clicked", "evaluated"):
                seen.add(cosmos_id)

            if event_type == "explain_clicked":
                explained.add(cosmos_id)

            if event_type == "evaluated":
                try:
                    score = float(item.get("score") or 0)
                    max_marks = float(item.get("maxMarks") or 1)
                    if max_marks > 0 and (score / max_marks) < SMART_SELECTION_SCORE_THRESHOLD:
                        poor.add(cosmos_id)
                except Exception:
                    continue

        return {"seen": seen, "explained": explained, "poor": poor}
    except Exception as e:
        logging.warning(f"Could not load interaction summary: {e}")
        return {"seen": set(), "explained": set(), "poor": set()}


def _sample_from_pool(pool: list, needed: int) -> list:
    if needed <= 0 or not pool:
        return []
    if len(pool) <= needed:
        return list(pool)
    return random.sample(pool, needed)


def _select_with_priority_distribution(tiers: list, count: int) -> list:
    distribution_map = {
        5: {1: 2, 2: 1, 3: 1, 5: 1},
        10: {1: 4, 2: 3, 3: 2, 5: 1},
        15: {1: 6, 2: 4, 3: 3, 5: 2},
        20: {1: 8, 2: 5, 3: 4, 5: 3}
    }

    target_distribution = distribution_map.get(count)
    if not target_distribution:
        flat = []
        for tier in tiers:
            flat.extend(tier)
        return _sample_from_pool(flat, count)

    selected = []
    selected_ids = set()

    def _row_key(row):
        return f"{_to_text(row.get('QuestionId'))}|{_to_text(row.get('Question'))}|{_extract_row_marks(row)}"

    for marks, needed in target_distribution.items():
        remaining = needed

        for tier in tiers:
            if remaining <= 0:
                break

            candidates = [
                row for row in tier
                if _extract_row_marks(row) == marks and _row_key(row) not in selected_ids
            ]
            picks = _sample_from_pool(candidates, remaining)
            for pick in picks:
                key = _row_key(pick)
                if key in selected_ids:
                    continue
                selected.append(pick)
                selected_ids.add(key)
                remaining -= 1
                if remaining <= 0:
                    break

        if remaining > 0:
            fallback_pool = [row for tier in tiers for row in tier if _extract_row_marks(row) == marks]
            while remaining > 0 and fallback_pool:
                pick = random.choice(fallback_pool)
                selected.append(pick)
                remaining -= 1

    if len(selected) < count:
        fallback_all = [row for tier in tiers for row in tier]
        while len(selected) < count and fallback_all:
            selected.append(random.choice(fallback_all))

    if len(selected) > count:
        selected = random.sample(selected, count)

    return selected


def _apply_priority_selection(pool: list, count: int, seen_ids: set, explained_ids: set, poor_ids: set, use_distribution: bool):
    # No prior history: let caller use current baseline behavior.
    if not seen_ids and not explained_ids and not poor_ids:
        return None

    def _row_cosmos_id(row):
        return _to_text(row.get("QuestionId"))

    never_seen = []
    explain_tier = []
    poor_tier = []
    seen_ok = []

    for row in pool:
        cosmos_id = _row_cosmos_id(row)
        if not cosmos_id or cosmos_id not in seen_ids:
            never_seen.append(row)
        elif cosmos_id in explained_ids:
            explain_tier.append(row)
        elif cosmos_id in poor_ids:
            poor_tier.append(row)
        else:
            seen_ok.append(row)

    tiers = [never_seen, explain_tier, poor_tier, seen_ok]

    if use_distribution:
        return _select_with_priority_distribution(tiers, count)

    selected = []
    for tier in tiers:
        remaining = count - len(selected)
        if remaining <= 0:
            break
        selected.extend(_sample_from_pool(tier, remaining))

    while len(selected) < count and pool:
        selected.append(random.choice(pool))

    return selected

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
    difficulty = req_body.get('difficulty', 'None')
    count = int(req_body.get('numQuestions', 10))
    selected_chapters = _normalize_chapter_filters(req_body.get('selectedChapters', []))

    requested_source = str(req_body.get('questionBankSource', os.environ.get('QUESTION_BANK_SOURCE', 'cosmos'))).strip().lower()
    if requested_source not in ("cosmos", "csv"):
        requested_source = "cosmos"

    csv_fallback_enabled = _parse_bool(
        req_body.get('enableCsvFallback', os.environ.get('ENABLE_CSV_FALLBACK', 'true')),
        default=True
    )

    questions_data = []
    source_used = requested_source

    if requested_source == "cosmos":
        questions_data = _load_questions_from_cosmos(subject, difficulty, req_body)
        if not questions_data and csv_fallback_enabled:
            logging.warning("No questions from Cosmos. Falling back to CSV source.")
            questions_data = _load_questions_from_csv(subject, difficulty)
            if questions_data:
                source_used = "csv"
    else:
        questions_data = _load_questions_from_csv(subject, difficulty)
        if not questions_data:
            source_used = "csv"

    # Apply optional chapter selection filter before fallback handling.
    if selected_chapters:
        questions_data = _filter_questions_by_chapters(questions_data, selected_chapters)

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
        source_used = "dummy"

    use_distribution_logic = str(difficulty).strip().lower() in ("none", "all")
    user_id = _to_text(req_body.get("userId")) or "1"

    interaction_summary = _load_student_interaction_summary(user_id, subject)
    smart_selected_rows = _apply_priority_selection(
        questions_data,
        count,
        interaction_summary["seen"],
        interaction_summary["explained"],
        interaction_summary["poor"],
        use_distribution_logic
    )

    if smart_selected_rows is not None:
        selected_rows = smart_selected_rows
    elif use_distribution_logic:
        selected_rows = _select_questions_by_marks_distribution(questions_data, count)
    elif len(questions_data) > count:
        selected_rows = random.sample(questions_data, count)
    else:
        selected_rows = list(questions_data)
        # If we need more, we can duplicate or just return what we have
        # User requested "number of questions requested", so we might need to repeat if short
        while len(selected_rows) < count and selected_rows:
            selected_rows.append(random.choice(questions_data))

    final_questions = []
    for i, row in enumerate(selected_rows):
        q_text = row.get('Question', '')
        q_obj = {
            "id": i + 1,
            "cosmosId": row.get('QuestionId', ''),
            "type": row.get('Type', 'subjective').lower() if row.get('Type') else 'subjective',
            "marks": int(row.get('Marks', 1)) if row.get('Marks') else 1,
            "chapter": row.get('Chapter', ''),
            "portion": row.get('Portion', ''),
            "subTopic": row.get('Sub Topic', ''),
            "solutionText": row.get('SolutionText', ''),
            "explanation": row.get('Explanation', ''),
            "commonMistakes": _normalize_mistakes_list(row.get('CommonMistakes', [])),
            "answerText": row.get('AnswerText', ''),
            "explainData": row.get('ExplainData', {}),
            "explainQuestion": row.get('ExplainQuestion', {}),
            "solutionData": row.get('SolutionData', {}),
            "glossary": row.get('GlossaryData', []),
            "whatToDo": row.get('WhatToDoData', [])
        }

        # Prefer explicit image URL field from Cosmos/CSV rows.
        explicit_image_urls = [u.strip() for u in str(row.get('ImageUrls', '')).split('#') if u.strip()]

        # Handle Question field (URL list or text)
        if explicit_image_urls:
            if len(explicit_image_urls) > 1:
                q_obj["imageUrls"] = explicit_image_urls
            else:
                q_obj["imageUrl"] = explicit_image_urls[0]
            q_obj["question"] = q_text if q_text else "Answer the following question:"
        elif q_text.startswith('http'):
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
            "selectedChapters": selected_chapters,
            "questionBankRequested": requested_source,
            "questionBankSource": source_used,
            "questions": final_questions
        }),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="track-interaction", methods=["POST"])
def track_interaction(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    user_id = _to_text(req_body.get("userId")) or "1"
    events = req_body.get("events", [])

    if not isinstance(events, list) or not events:
        return func.HttpResponse(
            json.dumps({"saved": 0}),
            status_code=200,
            mimetype="application/json"
        )

    container = _get_interactions_container()
    if not container:
        return func.HttpResponse(
            json.dumps({"error": "Interactions container unavailable"}),
            status_code=503,
            mimetype="application/json"
        )

    saved = 0
    for event in events:
        if not isinstance(event, dict):
            continue

        event_type = _to_text(event.get("type"))
        cosmos_id = _to_text(event.get("cosmosId"))
        if not event_type or not cosmos_id:
            continue

        interaction_doc = {
            "id": f"{user_id}-{event_type}-{cosmos_id}-{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
            "userId": user_id,
            "type": event_type,
            "cosmosId": cosmos_id,
            "subject": _to_text(event.get("subject")).lower(),
            "chapter": _to_text(event.get("chapter")),
            "subTopic": _to_text(event.get("subTopic")),
            "marks": event.get("marks"),
            "score": event.get("score"),
            "maxMarks": event.get("maxMarks"),
            "timestamp": _to_text(event.get("timestamp")) or datetime.now(timezone.utc).isoformat()
        }

        try:
            container.upsert_item(interaction_doc)
            saved += 1
        except Exception as e:
            logging.warning(f"Failed to save interaction event: {e}")

    return func.HttpResponse(
        json.dumps({"saved": saved}),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="clear-interaction-data", methods=["POST"])
def clear_interaction_data(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        req_body = {}

    user_id = _to_text(req_body.get("userId")) or "1"
    subject = _to_text(req_body.get("subject")).lower()

    container = _get_interactions_container()
    if not container:
        return func.HttpResponse(
            json.dumps({"error": "Interactions container unavailable"}),
            status_code=503,
            mimetype="application/json"
        )

    try:
        if subject:
            query = "SELECT c.id FROM c WHERE c.userId = @uid AND c.subject = @subject"
            parameters = [
                {"name": "@uid", "value": user_id},
                {"name": "@subject", "value": subject}
            ]
        else:
            query = "SELECT c.id FROM c WHERE c.userId = @uid"
            parameters = [{"name": "@uid", "value": user_id}]

        docs = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))

        deleted = 0
        for doc in docs:
            try:
                container.delete_item(item=doc["id"], partition_key=user_id)
                deleted += 1
            except Exception as e:
                logging.warning(f"Failed deleting interaction {doc.get('id')}: {e}")

        return func.HttpResponse(
            json.dumps({"deleted": deleted}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Failed clearing interaction data: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="chapter-options", methods=["POST"])
def chapter_options(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        req_body = {}

    subject = req_body.get('subject', 'Science')
    difficulty = req_body.get('difficulty', 'None')
    requested_source = str(req_body.get('questionBankSource', os.environ.get('QUESTION_BANK_SOURCE', 'cosmos'))).strip().lower()
    if requested_source not in ("cosmos", "csv"):
        requested_source = "cosmos"

    csv_fallback_enabled = _parse_bool(
        req_body.get('enableCsvFallback', os.environ.get('ENABLE_CSV_FALLBACK', 'true')),
        default=True
    )

    questions_data = []
    source_used = requested_source

    if requested_source == "cosmos":
        questions_data = _load_questions_from_cosmos(subject, difficulty, req_body)
        if not questions_data and csv_fallback_enabled:
            questions_data = _load_questions_from_csv(subject, difficulty)
            if questions_data:
                source_used = "csv"
    else:
        questions_data = _load_questions_from_csv(subject, difficulty)
        if not questions_data:
            source_used = "csv"

    chapters = _build_chapter_list(questions_data)

    return func.HttpResponse(
        json.dumps({
            "subject": subject,
            "difficulty": difficulty,
            "questionBankSource": source_used,
            "chapters": chapters
        }),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="renew-paper-image-urls", methods=["POST"])
def renew_paper_image_urls(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    paper = req_body.get("paper") if isinstance(req_body, dict) else None
    if not isinstance(paper, dict):
        return func.HttpResponse(
            json.dumps({"error": "Request must include a 'paper' object"}),
            status_code=400,
            mimetype="application/json"
        )

    signing_ctx = _build_storage_signing_context()
    if not signing_ctx:
        return func.HttpResponse(
            json.dumps({"error": "Storage signing configuration missing"}),
            status_code=500,
            mimetype="application/json"
        )

    paper_out = dict(paper)
    raw_questions = paper.get("questions", [])
    questions_out = []
    renewed_count = 0

    if isinstance(raw_questions, list):
        for question in raw_questions:
            if isinstance(question, dict):
                question_out = dict(question)
                renewed_count += _renew_question_image_urls(question_out, signing_ctx)
                questions_out.append(question_out)
            else:
                questions_out.append(question)

    paper_out["questions"] = questions_out

    return func.HttpResponse(
        json.dumps({
            "paper": paper_out,
            "renewedUrls": renewed_count
        }),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="paper-history/list", methods=["GET"])
def list_paper_history(req: func.HttpRequest) -> func.HttpResponse:
    container_client = _get_answersheet_container_client()
    if not container_client:
        return func.HttpResponse(
            json.dumps({"error": "Storage configuration missing"}),
            status_code=500,
            mimetype="application/json"
        )

    papers = []
    seen_ids = set()
    prefixes = [PAPER_BLOB_PREFIX + "/"]

    for prefix in prefixes:
        try:
            for blob in container_client.list_blobs(name_starts_with=prefix):
                blob_name = blob.name
                if not blob_name.lower().endswith(".json"):
                    continue

                paper = _download_json_blob(container_client, blob_name)
                if not isinstance(paper, dict):
                    continue
                if paper.get("deleted"):
                    continue

                paper_id = str(paper.get("id", "")).strip()
                if paper_id and paper_id in seen_ids:
                    continue

                if paper_id:
                    seen_ids.add(paper_id)

                paper["blobName"] = blob_name
                papers.append(paper)
        except Exception as e:
            logging.warning(f"Failed listing history blobs for prefix {prefix}: {e}")

    return func.HttpResponse(
        json.dumps({"papers": papers}),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="paper-history/save", methods=["POST"])
def save_paper_history(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    paper = req_body.get("paper") if isinstance(req_body, dict) and isinstance(req_body.get("paper"), dict) else req_body
    if not isinstance(paper, dict):
        return func.HttpResponse(
            json.dumps({"error": "Request must include paper object"}),
            status_code=400,
            mimetype="application/json"
        )

    container_client = _get_answersheet_container_client()
    if not container_client:
        return func.HttpResponse(
            json.dumps({"error": "Storage configuration missing"}),
            status_code=500,
            mimetype="application/json"
        )

    try:
        blob_name = _save_history_paper(container_client, paper)
        paper_out = dict(paper)
        paper_out["blobName"] = blob_name
        return func.HttpResponse(
            json.dumps({"paper": paper_out, "saved": True}),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="paper-history/delete", methods=["POST"])
def delete_paper_history(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    paper_id = str(req_body.get("paperId", "")).strip() if isinstance(req_body, dict) else ""
    blob_name = str(req_body.get("blobName", "")).strip() if isinstance(req_body, dict) else ""

    if not paper_id and not blob_name:
        return func.HttpResponse(
            json.dumps({"error": "paperId or blobName is required"}),
            status_code=400,
            mimetype="application/json"
        )

    container_client = _get_answersheet_container_client()
    if not container_client:
        return func.HttpResponse(
            json.dumps({"error": "Storage configuration missing"}),
            status_code=500,
            mimetype="application/json"
        )

    deleted = _delete_history_paper(container_client, paper_id, blob_name)
    if not deleted:
        return func.HttpResponse(
            json.dumps({"error": "Paper not found or could not be deleted"}),
            status_code=404,
            mimetype="application/json"
        )

    return func.HttpResponse(
        json.dumps({"deleted": True}),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="explain-question", methods=["POST"])
def explain_question(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json"
        )

    question_text = _to_text(req_body.get("question"))
    if not question_text and isinstance(req_body.get("questionItem"), dict):
        question_text = _to_text(req_body.get("questionItem", {}).get("question"))

    if not question_text:
        return func.HttpResponse(
            json.dumps({"error": "'question' is required"}),
            status_code=400,
            mimetype="application/json"
        )

    schema_payload = _build_schema_driven_explain_payload(req_body, question_text)
    if schema_payload:
        return func.HttpResponse(
            json.dumps({"explanation": schema_payload}),
            status_code=200,
            mimetype="application/json"
        )

    question_item = req_body.get("questionItem") if isinstance(req_body.get("questionItem"), dict) else {}
    solution_text = _to_text(question_item.get("solutionText") or req_body.get("solutionText"))
    explanation_text = _to_text(question_item.get("explanation") or req_body.get("explanation"))
    common_mistakes = _normalize_mistakes_list(
        question_item.get("commonMistakes") if question_item else req_body.get("commonMistakes", [])
    )
    answer_text = _to_text(question_item.get("answerText") or req_body.get("answerText"))

    payload = {
        "question": question_text,
        "type": question_item.get("type") if question_item else req_body.get("type", ""),
        "marks": question_item.get("marks") if question_item else req_body.get("marks", ""),
        "subject": req_body.get("subject", ""),
        "chapter": question_item.get("chapter") if question_item else req_body.get("chapter", ""),
        "subTopic": question_item.get("subTopic") if question_item else req_body.get("subTopic", ""),
        "options": (question_item.get("options") if question_item else req_body.get("options", [])) or [],
        "solutionText": solution_text,
        "explanation": explanation_text,
        "commonMistakes": common_mistakes,
        "answerText": answer_text
    }

    prompt = (
        "You are a kind teacher helping a student with limited vocabulary and comprehension difficulty. "
        "Simplify the question in very clear, short language without changing what is being asked. "
        "If useful, break the approach into small steps and explain difficult words.\n\n"
        "Return ONLY valid JSON with this exact structure:\n"
        "{\n"
        "  \"simplifiedQuestion\": \"...\",\n"
        "  \"whatToDo\": [\"...\", \"...\"],\n"
        "  \"glossary\": [{\"term\": \"...\", \"meaning\": \"...\"}],\n"
        "  \"encouragement\": \"...\",\n"
        "  \"commonMistakes\": [\"...\"],\n"
        "  \"finalExplanation\": \"...\"\n"
        "}\n\n"
        "Rules:\n"
        "- Use simple words suitable for middle school.\n"
        "- Keep each bullet concise.\n"
        "- Do not provide the final answer to the question.\n\n"
        f"Question payload:\n{json.dumps(payload, ensure_ascii=False)}"
    )

    llm_service = LLMService()
    explanation_raw = llm_service.generate(
        prompt,
        "You simplify academic questions for students with learning and comprehension difficulties."
    )

    if isinstance(explanation_raw, str) and explanation_raw.startswith("ERROR:"):
        return func.HttpResponse(
            json.dumps({"error": explanation_raw}),
            status_code=500,
            mimetype="application/json"
        )

    try:
        explanation_content = explanation_raw
        if isinstance(explanation_content, str) and ("```json" in explanation_content or "```" in explanation_content):
            if "```json" in explanation_content:
                explanation_content = explanation_content.split("```json")[1].split("```")[0].strip()
            else:
                explanation_content = explanation_content.split("```")[1].split("```")[0].strip()

        explanation_json = json.loads(explanation_content)
        if not isinstance(explanation_json.get("commonMistakes"), list):
            explanation_json["commonMistakes"] = []
        if "finalExplanation" not in explanation_json:
            explanation_json["finalExplanation"] = ""
        explanation_json["source"] = "llm"
    except Exception:
        explanation_json = {
            "simplifiedQuestion": str(explanation_raw),
            "whatToDo": [],
            "glossary": [],
            "encouragement": "Take your time and solve one small part at a time.",
            "commonMistakes": [],
            "finalExplanation": "",
            "source": "llm"
        }

    return func.HttpResponse(
        json.dumps({"explanation": explanation_json}),
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

    def _test_url_accessibility(self, url: str) -> bool:
        """Test if a URL is accessible from this environment."""
        try:
            import urllib.request
            request = urllib.request.Request(url, method='HEAD')
            response = urllib.request.urlopen(request, timeout=5)
            accessible = response.status == 200
            if self._is_verbose_logging_enabled():
                logging.info(f"[OPENAI_VISION] URL accessibility test: {url[:80]}... -> {response.status}")
            return accessible
        except Exception as e:
            logging.error(f"[OPENAI_VISION] URL NOT accessible: {url[:80]}... -> {str(e)}")
            return False

    def _is_localhost_runtime(self) -> bool:
        """Detect whether we're running locally (Functions Core Tools/localhost)."""
        website_instance_id = os.environ.get("WEBSITE_INSTANCE_ID")
        return not bool(website_instance_id)

    def _is_verbose_logging_enabled(self) -> bool:
        """Enable verbose OpenAI logging only on localhost by default.

        Can be overridden in any environment with OPENAI_VERBOSE_LOGS=true.
        """
        override = os.environ.get("OPENAI_VERBOSE_LOGS", "").lower() in ("1", "true", "yes")
        return override or self._is_localhost_runtime()

    def _log_full_openai_response(self, response, label: str) -> None:
        """Log response payload.

        Full payload is logged only in verbose mode (localhost by default).
        Otherwise, log compact metadata.
        """
        if not self._is_verbose_logging_enabled():
            try:
                response_id = getattr(response, "id", None)
                model = getattr(response, "model", None)
                usage = getattr(response, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
                completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
                total_tokens = getattr(usage, "total_tokens", None) if usage else None
                logging.info(
                    f"[OPENAI_VISION] {label} - response_id={response_id}, model={model}, "
                    f"tokens(prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens})"
                )
            except Exception:
                logging.info(f"[OPENAI_VISION] {label} - response received")
            return

        try:
            if hasattr(response, "model_dump_json"):
                serialized = response.model_dump_json(indent=2)
            elif hasattr(response, "model_dump"):
                serialized = json.dumps(response.model_dump(), indent=2, default=str)
            else:
                serialized = json.dumps(response, indent=2, default=str)
        except Exception as e:
            serialized = f"<failed to serialize response: {str(e)}>\n{str(response)}"

        logging.info(f"[OPENAI_VISION] {label} - FULL OPENAI RESPONSE:\n{serialized}")

    def call_llm(self, prompt: str, system_message: str = "You are a helpful assistant.", vision_image_urls: list = None) -> str:
        if not self.api_key:
            return "ERROR: OpenAI API Key Missing"
        
        try:
            # Build message content with proper vision support
            user_content = []
            
            # Add text content
            user_content.append({"type": "text", "text": prompt})
            
            # ✅ FIXED: Add images using proper OpenAI vision format
            if vision_image_urls:
                if self._is_verbose_logging_enabled():
                    logging.info(f"[OPENAI_VISION] Adding {len(vision_image_urls)} images to request")
                for i, image_url in enumerate(vision_image_urls):
                    if image_url:
                        if self._is_verbose_logging_enabled():
                            logging.info(f"[OPENAI_VISION] [{i+1}/{len(vision_image_urls)}] Testing URL accessibility: {image_url[:80]}...")
                        
                        # Test if URL is accessible
                        if not self._test_url_accessibility(image_url):
                            logging.error(f"[OPENAI_VISION] [{i+1}/{len(vision_image_urls)}] URL IS NOT ACCESSIBLE TO OPENAI - skipping this image")
                            continue
                        
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        })
                        if self._is_verbose_logging_enabled():
                            logging.info(f"[OPENAI_VISION] [{i+1}/{len(vision_image_urls)}] Added image URL (accessible): {image_url[:80]}...")
            
            if self._is_verbose_logging_enabled():
                logging.info(f"[OPENAI_VISION] Final content array has {len(user_content)} items (text + {len(user_content)-1} images)")

            try:
                response = self.client.chat.completions.create(
                    model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4"),
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_content}  # ✅ Proper structured content with vision
                    ],
                    temperature=0,
                    response_format={ "type": "json_object" }
                )
                self._log_full_openai_response(response, "Primary call")
                result_text = response.choices[0].message.content
                logging.info(f"[OPENAI_VISION] OpenAI returned successfully ({len(result_text)} chars)")
                return result_text
            except Exception as e:
                # If JSON mode fails, try without response_format
                logging.warning(f"[OPENAI_VISION] JSON mode failed: {str(e)}. Retrying without response_format...")
                try:
                    response = self.client.chat.completions.create(
                        model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4"),
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_content}
                        ],
                        temperature=0
                    )
                    self._log_full_openai_response(response, "Retry call")
                    result_text = response.choices[0].message.content
                    logging.info(f"[OPENAI_VISION] Retry succeeded ({len(result_text)} chars)")
                    return result_text
                except Exception as retry_e:
                    logging.error(f"[OPENAI_VISION] Retry also failed: {str(retry_e)}", exc_info=True)
                    raise
        except Exception as e:
            logging.error(f"[OPENAI_VISION] OpenAI call failed: {str(e)}", exc_info=True)
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
            logging.info(f"[GEMINI_VISION] Fetching image from URL: {image_url[:100]}...")
            with urllib.request.urlopen(image_url) as response:
                image_data = response.read()
                logging.info(f"[GEMINI_VISION] Image fetched: {len(image_data)} bytes")
                base64_data = base64.standard_b64encode(image_data).decode('utf-8')
                content_type = response.headers.get('content-type', 'image/jpeg')
                logging.info(f"[GEMINI_VISION] Image encoded to base64, mime_type: {content_type}")
                return {
                    "mime_type": content_type,
                    "data": base64_data
                }
        except Exception as e:
            logging.error(f"[GEMINI_VISION] Failed to fetch or encode image from {image_url}: {str(e)}")
            return None

    def call_llm(self, prompt: str, system_message: str = "", vision_image_urls: list = None) -> str:
        if not self.api_key:
            return "ERROR: Gemini API Key Missing or library not installed"
        
        try:
            # Build content parts: system message + user prompt + images
            content_parts = []
            
            logging.info(f"[GEMINI_VISION] Starting Gemini call. vision_image_urls count: {len(vision_image_urls) if vision_image_urls else 0}")
            
            # Add system message if provided (as part of the first user message)
            if system_message:
                full_prompt = f"System: {system_message}\n\n{prompt}"
            else:
                full_prompt = prompt
            
            content_parts.append(full_prompt)
            logging.info(f"[GEMINI_VISION] Added prompt text ({len(full_prompt)} chars)")
            
            # Fetch and add images if provided
            if vision_image_urls:
                logging.info(f"[GEMINI_VISION] Processing {len(vision_image_urls)} image URLs")
                for idx, image_url in enumerate(vision_image_urls):
                    if image_url:
                        logging.info(f"[GEMINI_VISION] [{idx+1}/{len(vision_image_urls)}] Processing image URL: {image_url[:80]}...")
                        image_data = self._fetch_image_from_url(image_url)
                        if image_data:
                            content_parts.append({
                                "mime_type": image_data["mime_type"],
                                "data": image_data["data"]
                            })
                            logging.info(f"[GEMINI_VISION] [{idx+1}/{len(vision_image_urls)}] Image added to content_parts (mime: {image_data['mime_type']})")
                        else:
                            logging.warning(f"[GEMINI_VISION] [{idx+1}/{len(vision_image_urls)}] Could not fetch image: {image_url}")
            
            logging.info(f"[GEMINI_VISION] Final content_parts count: {len(content_parts)} (1 text + {len(content_parts)-1} images)")
            
            # Call Gemini API
            logging.info(f"[GEMINI_VISION] Calling Gemini API with {len(content_parts)-1} images")
            response = genai.GenerativeModel(self.model).generate_content(
                content_parts,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    top_k=1
                )
            )
            
            logging.info(f"[GEMINI_VISION] Gemini API returned successfully ({len(response.text)} chars)")
            return response.text
        except Exception as e:
            logging.error(f"[GEMINI_VISION] Gemini call failed: {str(e)}", exc_info=True)
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

    req_body = {}
    paper_id = None
    blob_urls = []
    content_type = (req.headers.get("content-type") or req.headers.get("Content-Type") or "").lower()

    if "multipart/form-data" in content_type:
        logging.info("[ANSWERSHEET_TRACE] Request is multipart/form-data")
        parsed_fields, parsed_files = _parse_multipart_request(req)

        form_data = getattr(req, "form", None)
        files_collection = getattr(req, "files", None)

        files = _extract_uploaded_files(files_collection, "answerSheets")
        if not files:
            files = parsed_files.get("answerSheets", [])

        if form_data and hasattr(form_data, "get"):
            paper_id = form_data.get("paperId")
        else:
            paper_id = parsed_fields.get("paperId")

        logging.info(f"[ANSWERSHEET_TRACE] Extracted from request: paperId={paper_id}, files_count={len(files)}")
        
        if not files:
            logging.error("[ANSWERSHEET_TRACE] No files extracted from multipart request")
            return func.HttpResponse(
                json.dumps({"error": "At least one answer sheet file is required"}),
                status_code=400,
                mimetype="application/json"
            )

        try:
            blob_urls = _upload_answer_sheet_files(files, str(paper_id or "").strip())
            logging.info(f"[ANSWERSHEET_TRACE] After upload: blob_urls count={len(blob_urls)}")
            for i, url in enumerate(blob_urls):
                logging.info(f"[ANSWERSHEET_TRACE] blob_url[{i}]: {url[:100]}...")
            
            if not blob_urls:
                logging.error("[ANSWERSHEET_TRACE] Upload succeeded but returned no blob URLs")
                return func.HttpResponse(
                    json.dumps({"error": "File upload to blob storage failed - no URLs returned"}),
                    status_code=500,
                    mimetype="application/json"
                )
        except ValueError as exc:
            logging.error(f"[ANSWERSHEET_TRACE] Upload failed: {str(exc)}")
            return func.HttpResponse(
                json.dumps({"error": str(exc)}),
                status_code=500,
                mimetype="application/json"
            )
    else:
        logging.info("[ANSWERSHEET_TRACE] Request is NOT multipart - using legacy blobUrls from JSON")
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
        logging.info(f"[ANSWERSHEET_TRACE] From JSON: paperId={paper_id}, blob_urls count={len(blob_urls)}")

    logging.info(f"[ANSWERSHEET_TRACE] Evaluation requested for paper {paper_id} with {len(blob_urls)} image files.")

    paper_data = None
    if paper_id:
        try:
            history_container = _get_answersheet_container_client()
            if history_container:
                paper_data = _load_history_paper(history_container, str(paper_id))
            if paper_data:
                logging.info(f"Successfully fetched paper {paper_id} from history storage")
            else:
                logging.warning(f"Paper {paper_id} not found in history storage")
        except Exception as e:
            logging.error(f"Error fetching paper {paper_id} from history storage: {str(e)}")

    # Step 1: Perform OCR on Paper Questions (if images) and Answer Sheets
    logging.info("Starting Step 1: OCR Extraction")
    
    ocr_results = {
        "questions": [],
        "answerSheets": []
    }

    # ocr_results["questions"] = [{'id': '1', 'text': 'Answer the following question:', 'imageText': 'Q.5. In the following situations identify the agent\nexerting a force and the object on which it acts.\nState the form in which the effect of force is\nobservable in each case.\n(Medium)\n(a)* Expelling lemon juice by squeezing it between the\nfingers.\n(b) Taking out paste from a toothpaste tube.\n() A load suspended from a spring while its other\nend is on a hook fixed to wall.\n(d) An athlete taking a high jump to clear the bar at a\nheight of 5 metres.', 'imagesText': [...], 'fullText': 'Answer the following question:\nQ.5. In the following situations identify the agent\nexerting a force and the object on which it acts.\nState the form in which the effect of force is\nobservable in each case.\n(Medium)\n(a)* Expelling lemon juice by squeezing it between the\nfingers.\n(b) Taking out paste from a toothpaste tube.\n() A load suspended from a spring while its other\nend is on a hook fixed to wall.\n(d) An athlete taking a high jump to clear the bar at a\nheight of 5 metres.', 'marks': 3}, {'id': '2', 'text': 'Answer the following question:', 'imageText': '0.1. How is the blind folded person able to guess\nwhich player is closer to her?\n(Al/Medium)', 'imagesText': [...], 'fullText': 'Answer the following question:\n0.1. How is the blind folded person able to guess\nwhich player is closer to her?\n(Al/Medium)', 'marks': 3}, {'id': '3', 'text': 'Answer the following question:', 'imageText': 'Q. 4. How is lightning useful to us?\n(Medium)\n(a) It helps in nitrogen fixation and promotes plant\ngrowth.\n(b) Ozone is formed which prevent ultraviolet rays\nfalling on the earth.\n(c) It helps in the evolution of a new species.\n(d) All of the above', 'imagesText': [...], 'fullText': 'Answer the following question:\nQ. 4. How is lightning useful to us?\n(Medium)\n(a) It helps in nitrogen fixation and promotes plant\ngrowth.\n(b) Ozone is formed which prevent ultraviolet rays\nfalling on the earth.\n(c) It helps in the evolution of a new species.\n(d) All of the above', 'marks': 3}, {'id': '4', 'text': 'Answer the following question:', 'imageText': '(Iv) electroplating\nQ. 2. When the free ends of the tester are dipped into the\nsolution, the magnetic needle shows deflection.\nCan you explain the reason?\n(Medium)', 'imagesText': [...], 'fullText': 'Answer the following question:\n(Iv) electroplating\nQ. 2. When the free ends of the tester are dipped into the\nsolution, the magnetic needle shows deflection.\nCan you explain the reason?\n(Medium)', 'marks': 3}, {'id': '5', 'text': 'Two persons are applying forces on two opposite sides of a moving cart. The cart still moves with the same speed in the same direction. What do you infer about the magnitudes and direction of the forces applied?', 'imageText': '', 'imagesText': [...], 'fullText': 'Two persons are applying forces on two opposite sides of a moving cart. The cart still moves with the same speed in the same direction. What do you infer about the magnitudes and direction of the forces applied?', 'marks': 3}, {'id': '6', 'text': 'Answer the following question:', 'imageText': 'Q.8. Will an electric device work if we place the\npositive terminal of a battery towards the negative\npoint of the device? Explain your answer.\n(CBSE SAS)', 'imagesText': [...], 'fullText': 'Answer the following question:\nQ.8. Will an electric device work if we place the\npositive terminal of a battery towards the negative\npoint of the device? Explain your answer.\n(CBSE SAS)', 'marks': 2}, {'id': '7', 'text': 'Answer the following question:', 'imageText': 'AIDS can spread from an infected person to\nanother person through:\n(Medium)\n[NCERT Exemplar Pg 53, Q. 2] @0\n(a) sharing food\n(b) blood transfusion\n(c) sharing comb\n(d) a mosquito bite', 'imagesText': [...], 'fullText': 'Answer the following question:\nAIDS can spread from an infected person to\nanother person through:\n(Medium)\n[NCERT Exemplar Pg 53, Q. 2] @0\n(a) sharing food\n(b) blood transfusion\n(c) sharing comb\n(d) a mosquito bite', 'marks': 1}, {'id': '8', 'text': 'Answer the following question:', 'imageText': 'Q. 1. The pressure on an object increases with decrease\nin area even when force is constant. Explain.\n(Difficult)', 'imagesText': [...], 'fullText': 'Answer the following question:\nQ. 1. The pressure on an object increases with decrease\nin area even when force is constant. Explain.\n(Difficult)', 'marks': 3}, {'id': '9', 'text': 'Answer the following question:', 'imageText': 'Q. 1. A simple pendulum makes 10 oscillations in\n20 s. What is the time period and frequency of its\noscillations?\n(NCERT Exemplar Q. 16 Pg 75)(AI/Difficult)', 'imagesText': [...], 'fullText': 'Answer the following question:\nQ. 1. A simple pendulum makes 10 oscillations in\n20 s. What is the time period and frequency of its\noscillations?\n(NCERT Exemplar Q. 16 Pg 75)(AI/Difficult)', 'marks': 3}, {'id': '10', 'text': 'Answer the following question:', 'imageText': 'Q. 6. Name the scale on which the destructive energy\nof an earthquake is measured. An earthquake\nmeasures 3 on this scale. Would it be recorded by a\nseismograph? Is it likely to cause much damage?\n(Medium)', 'imagesText': [...], 'fullText': 'Answer the following question:\nQ. 6. Name the scale on which the destructive energy\nof an earthquake is measured. An earthquake\nmeasures 3 on this scale. Would it be recorded by a\nseismograph? Is it likely to cause much damage?\n(Medium)', 'marks': 2}]
    # ocr_results["anwers"] = [{'url': '<SIGNED_ANSWERSHEET_URL>', 'extractedText': '...'}]

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
    logging.info(f"[ANSWERSHEET_TRACE] Step 2: blob_urls count={len(blob_urls)}")
    
    prompt_service = PromptService()
    llm_service = LLMService()

    # Read container & SAS from env to fetch paper if configured
    SAS_TOKEN = os.environ.get("ANSWERSHEET_SAS_TOKEN", os.environ.get("SAS_TOKEN", ""))
    CONTAINER_URL = os.environ.get("ANSWERSHEET_CONTAINER_URL", os.environ.get("CONTAINER_URL", "<ANSWERSHEET_CONTAINER_URL>"))

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
    logging.info(f"[ANSWERSHEET_TRACE] Step 2: Calling LLM with vision_image_urls={len(blob_urls)}")
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
        batch_evaluation = False
    elif isinstance(batch_evaluation, str):
        batch_evaluation = batch_evaluation.lower() in ('1', 'true', 'yes')

    include_full_sheet_in_per_question = os.environ.get('INCLUDE_FULL_ANSWERSHEET_IN_PER_QUESTION', 'false').lower() in ('1', 'true', 'yes')

    if batch_evaluation:
        logging.info("Using batch evaluation flow")
        logging.info(f"[ANSWERSHEET_TRACE] Batch eval: blob_urls count={len(blob_urls)}")
        batch_prompt_tpl = prompt_service.get_prompt("evaluation_vision_batch_prompt")

        # Prepare batch items and collect vision images for context
        questions_map = {str(q.get("id")): q for q in ocr_results.get("questions", [])}
        # Build a lookup from paper_data so we can access rich solution fields
        paper_data_map = {}
        if paper_data and "questions" in paper_data:
            for pq in paper_data["questions"]:
                paper_data_map[str(pq.get("id"))] = pq
        batch_items = []
        vision_images = []

        # Add original answer sheet images
        for url in blob_urls:
            if url and url not in vision_images:
                vision_images.append(url)

        logging.info(f"[ANSWERSHEET_TRACE] Batch eval: vision_images count after adding blobs={len(vision_images)}")

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

                # Pull solution/reference fields from the saved paper question object
                pq_data = paper_data_map.get(q_id, {})
                reference_answer = pq_data.get("answerText") or pq_data.get("solutionText") or ""
                common_mistakes = pq_data.get("commonMistakes") or []
                solution_explanation = pq_data.get("explanation") or ""

                item = {
                    "questionId": q_id,
                    "question": full_question_text,
                    "studentAnswer": student_answer,
                    "marks": question_data.get("marks", 1)
                }
                if reference_answer:
                    item["referenceAnswer"] = reference_answer
                if common_mistakes:
                    item["commonMistakes"] = common_mistakes if isinstance(common_mistakes, list) else [common_mistakes]
                if solution_explanation:
                    item["explanation"] = solution_explanation
                batch_items.append(item)

        if not batch_items:
            logging.warning("No items to batch evaluate.")
        else:
            prompt = batch_prompt_tpl.format(
                batch_data_json=json.dumps(batch_items, indent=2)
            )

            logging.info(f"[ANSWERSHEET_TRACE] Batch eval: Calling LLM with vision_images count={len(vision_images)}")
            for i, url in enumerate(vision_images):
                logging.info(f"[ANSWERSHEET_TRACE] Batch eval: vision_images[{i}]: {url[:80]}...")
            
            eval_response_str = llm_service.generate(prompt, "You are an expert exam evaluator with vision capabilities.", vision_image_urls=vision_images if vision_images else None)

            # eval_response_str = "{\n  \"evaluation\": [\n    {\n      \"questionId\": \"1\",\n      \"score\": 4,\n      \"feedback\": \"The student correctly identified the agent and object in each case. The image confirms the same entries with proper alignment. However, the student did not explicitly state the observable effect of force (change in shape or motion) for each case, though implied.\",\n      \"expected_answer\": \"Each situation should identify the agent, object, and the observable effect of force (change in shape or motion). For example: (a) Fingers act on lemon – change in shape; (b) Fingers act on tube – change in shape; (c) Load acts on spring – change in length; (d) Legs act on body – change in motion.\",\n      \"missed_points\": [\"Explicit mention of the observable effect of force in each case.\"]\n    },\n    {\n      \"questionId\": \"2\",\n      \"score\": 3,\n      \"feedback\": \"The student correctly mentioned the Doppler effect as the reason. The image confirms the same short answer. However, the explanation lacks detail on how the change in frequency helps the blindfolded person judge distance.\",\n      \"expected_answer\": \"The blindfolded person can guess which player is closer because the sound waves from the nearer player reach her with higher frequency due to the Doppler effect.\",\n      \"missed_points\": [\"Explanation of how frequency change indicates closeness.\"]\n    },\n    {\n      \"questionId\": \"3\",\n      \"score\": 4,\n      \"feedback\": \"The student selected option (d) 'All of the above', which is correct. The image confirms the same. The answer is complete and conceptually accurate.\",\n      \"expected_answer\": \"Lightning helps in nitrogen fixation, formation of ozone, and contributes to chemical reactions that may lead to evolution of new species. Hence, all of the above.\",\n      \"missed_points\": []\n    },\n    {\n      \"questionId\": \"4\",\n      \"score\": 3,\n      \"feedback\": \"The student correctly stated that the solution conducts electricity, causing magnetic needle deflection. The image confirms the same. However, the answer could mention that the deflection occurs due to current flowing through the solution.\",\n      \"expected_answer\": \"When the tester’s ends are dipped into a conducting solution, electric current flows through it, producing a magnetic effect that causes the needle to deflect.\",\n      \"missed_points\": [\"Mention of current flow causing magnetic effect.\"]\n    },\n    {\n      \"questionId\": \"5\",\n      \"score\": 2,\n      \"feedback\": \"The student wrote 'One force is greater than the other', which is incorrect. If the cart moves with the same speed and direction, the net force is zero, meaning forces are equal and opposite. The image confirms the same short answer.\",\n      \"expected_answer\": \"The forces applied are equal in magnitude and opposite in direction, resulting in no change in motion.\",\n      \"missed_points\": [\"Equality and opposite direction of forces.\", \"Inference about constant velocity meaning balanced forces.\"]\n    },\n    {\n      \"questionId\": \"6\",\n      \"score\": 3,\n      \"feedback\": \"The student correctly stated that the device will not work because electricity won’t flow. The image confirms the same. The reasoning is conceptually correct though brief.\",\n      \"expected_answer\": \"No, the device will not work because the current will not flow if the battery’s positive terminal is connected to the negative point of the device; correct polarity is required for current flow.\",\n      \"missed_points\": [\"Explanation of polarity and current direction.\"]\n    },\n    {\n      \"questionId\": \"7\",\n      \"score\": 0,\n      \"feedback\": \"The student selected option (c) 'sharing comb', which is incorrect. The correct answer is (b) 'blood transfusion'. The image confirms the same choice.\",\n      \"expected_answer\": \"AIDS can spread through blood transfusion, sharing infected needles, or from mother to child, not through sharing food or combs.\",\n      \"missed_points\": [\"Correct identification of transmission route.\"]\n    },\n    {\n      \"questionId\": \"8\",\n      \"score\": 4,\n      \"feedback\": \"The student correctly wrote 'Pressure = Force / Area'. The image confirms the formula. This fully explains why pressure increases when area decreases for constant force.\",\n      \"expected_answer\": \"Pressure = Force / Area. For constant force, if area decreases, pressure increases.\",\n      \"missed_points\": []\n    },\n    {\n      \"questionId\": \"9\",\n      \"score\": 4,\n      \"feedback\": \"The student correctly calculated time period and frequency. The image confirms the same values. The answer is complete and accurate.\",\n      \"expected_answer\": \"Time period = Total time / Number of oscillations = 20 s / 10 = 2 s; Frequency = 1 / Time period = 0.5 Hz.\",\n      \"missed_points\": []\n    },\n    {\n      \"questionId\": \"10\",\n      \"score\": 2,\n      \"feedback\": \"The student did not provide an answer. The image shows the space blank. The correct answer involves the Richter scale and its interpretation.\",\n      \"expected_answer\": \"The destructive energy of an earthquake is measured on the Richter scale. An earthquake of magnitude 3 would be recorded by a seismograph but cause little damage.\",\n      \"missed_points\": [\"Name of scale (Richter scale).\", \"Explanation of seismograph recording.\", \"Comment on damage level.\"]\n    }\n  ]\n}"

            try:
                if isinstance(eval_response_str, str) and ("```json" in eval_response_str or "```" in eval_response_str):
                    if "```json" in eval_response_str:
                        eval_response_str = eval_response_str.split("```json")[1].split("```")[0].strip()
                    else:
                        eval_response_str = eval_response_str.split("```")[1].split("```")[0].strip()

                eval_data_list = json.loads(eval_response_str)
                logging.info(f"[ANSWERSHEET_TRACE] Batch eval response type: {type(eval_data_list).__name__}")
                
                if isinstance(eval_data_list, dict):
                    logging.info(f"[ANSWERSHEET_TRACE] Dict keys: {list(eval_data_list.keys())}")
                    logging.info(f"[ANSWERSHEET_TRACE] Full response (first 800 chars): {str(eval_response_str)[:800]}")

                # Sometimes the response contains an evaluation key wrapping the list
                if isinstance(eval_data_list, dict):
                    # Try different possible keys where the evaluation list might be
                    possible_keys = ["evaluation", "evaluations", "results", "answers", "data"]
                    found_list = None
                    for key in possible_keys:
                        if key in eval_data_list:
                            found_list = eval_data_list[key]
                            logging.info(f"[ANSWERSHEET_TRACE] Found evaluation data under key '{key}'")
                            break
                    
                    if found_list is None:
                        logging.info(f"[ANSWERSHEET_TRACE] Could not find evaluation wrapper key. Available keys: {list(eval_data_list.keys())}")
        
                        # Check if this is a single evaluation object (has questionId, score, feedback, etc.)
                        if "questionId" in eval_data_list and "score" in eval_data_list:
                            found_list = [eval_data_list]  # Wrap single evaluation in list
                            logging.info(f"[ANSWERSHEET_TRACE] Detected single evaluation object. Wrapping in list.")
                        # If no list found, treat the dict items as individual evaluations (mapping style)
                        elif all(isinstance(v, dict) for v in eval_data_list.values()):
                            found_list = list(eval_data_list.values())
                            logging.info(f"[ANSWERSHEET_TRACE] Treating dict values as evaluations ({len(found_list)} items)")
                        else:
                            raise ValueError(f"Response dict does not contain a list of evaluations. Keys: {list(eval_data_list.keys())}")
                    
                    eval_data_list = found_list
                
                # Ensure eval_data_list is actually a list
                if not isinstance(eval_data_list, list):
                    logging.error(f"[ANSWERSHEET_TRACE] Response is still not a list. Type: {type(eval_data_list).__name__}")
                    raise ValueError(f"Expected list, got {type(eval_data_list).__name__}")
                
                eval_map = {str(item.get("questionId")): item for item in eval_data_list}

                for item in batch_items:
                    q_id = str(item["questionId"])
                    max_marks = item.get("marks", 1)
                    max_possible_score += max_marks
                    if q_id in eval_map:
                        res = eval_map[q_id]
                        raw_score = res.get("score", 0)
                        try:
                            score = float(raw_score)
                        except Exception:
                            if isinstance(raw_score, str) and "/" in raw_score:
                                try:
                                    score = float(raw_score.split("/")[0].strip())
                                except Exception:
                                    score = 0.0
                            else:
                                score = 0.0

                        score = max(0.0, min(score, float(max_marks)))
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
                logging.error(f"[ANSWERSHEET_TRACE] Batch evaluation parse failed: {str(e)}", exc_info=True)
                evaluation_results = [{"error": "Batch evaluation failed", "raw_response": eval_response_str}]

    else:
        logging.info("Using per-question individual evaluation flow")
        logging.info(f"[ANSWERSHEET_TRACE] Per-question eval: blob_urls count={len(blob_urls)}")
        logging.info(f"[ANSWERSHEET_TRACE] Per-question eval: include_full_sheet_images={include_full_sheet_in_per_question}")
        eval_prompt_tpl = prompt_service.get_prompt("evaluation_vision_prompt")
        questions_map = {str(q.get("id")): q for q in ocr_results.get("questions", [])}
        # Build a lookup from paper_data so we can access rich solution fields
        paper_data_map = {}
        if paper_data and "questions" in paper_data:
            for pq in paper_data["questions"]:
                paper_data_map[str(pq.get("id"))] = pq

        for ans in segmented_answers:
            q_id = str(ans.get("questionId"))
            student_answer = ans.get("answerText")
            if q_id in questions_map:
                question_data = questions_map[q_id]
                full_question_text = question_data.get("fullText") or question_data.get("question") or question_data.get("text") or ""
                question_image_ocr = "\n".join([t for t in ([question_data.get("imageText", "")] + (question_data.get("imagesText", []) or [])) if t])
                max_marks = question_data.get("marks", 1)
                max_possible_score += max_marks

                # Build vision images for this question (default: question images only)
                vision_images = []
                q_image_url = question_data.get("imageUrl")
                q_image_urls = question_data.get("imageUrls", []) or []
                if q_image_url:
                    vision_images.append(q_image_url)
                for u in q_image_urls:
                    if u and u not in vision_images:
                        vision_images.append(u)

                # Optional: include full answer-sheet images per question only when explicitly enabled
                if include_full_sheet_in_per_question:
                    for u in blob_urls:
                        if u and u not in vision_images:
                            vision_images.append(u)

                # Pull solution/reference fields from the saved paper question object
                pq_data = paper_data_map.get(q_id, {})
                answer_text_from_question_bank = pq_data.get("answerText") or ""
                reference_answer = pq_data.get("answerText") or pq_data.get("solutionText") or ""
                common_mistakes = pq_data.get("commonMistakes") or []
                solution_explanation = pq_data.get("explanation") or ""

                prompt = eval_prompt_tpl.format(
                    question=full_question_text,
                    question_image_ocr=question_image_ocr,
                    answer=student_answer,
                    max_marks=max_marks,
                    answer_text_from_question_bank=answer_text_from_question_bank,
                    reference_answer=reference_answer,
                    common_mistakes=json.dumps(common_mistakes if isinstance(common_mistakes, list) else [common_mistakes]) if common_mistakes else "[]",
                    explanation=solution_explanation
                )

                logging.info(f"[ANSWERSHEET_TRACE] Per-question eval: Q{q_id} calling LLM with vision_images count={len(vision_images)}")
                for i, url in enumerate(vision_images):
                    logging.info(f"[ANSWERSHEET_TRACE] Per-question eval: Q{q_id} vision_images[{i}]: {url[:80]}...")
                
                eval_response_str = llm_service.generate(prompt, "You are an expert exam evaluator with vision capabilities.", vision_image_urls=vision_images if vision_images else None)

                try:
                    if isinstance(eval_response_str, str) and ("```json" in eval_response_str or "```" in eval_response_str):
                        if "```json" in eval_response_str:
                            eval_response_str = eval_response_str.split("```json")[1].split("```")[0].strip()
                        else:
                            eval_response_str = eval_response_str.split("```")[1].split("```")[0].strip()

                    eval_data = json.loads(eval_response_str)
                    
                    # Handle case where response is wrapped in a dict
                    if isinstance(eval_data, dict) and "score" not in eval_data and len(eval_data) == 1:
                        # Extract single nested evaluation if present
                        possible_keys = ["evaluation", "result", "data"]
                        for key in possible_keys:
                            if key in eval_data and isinstance(eval_data[key], dict) and "score" in eval_data[key]:
                                eval_data = eval_data[key]
                                break
                    
                    raw_score = eval_data.get("score", 0)
                    try:
                        score = float(raw_score)
                    except Exception:
                        if isinstance(raw_score, str) and "/" in raw_score:
                            try:
                                score = float(raw_score.split("/")[0].strip())
                            except Exception:
                                score = 0.0
                        else:
                            score = 0.0

                    score = max(0.0, min(score, float(max_marks)))
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
                    logging.error(f"[ANSWERSHEET_TRACE] Failed to parse evaluation response for Q{q_id}: {str(e)}", exc_info=True)
                    logging.error(f"[ANSWERSHEET_TRACE] Raw response was: {eval_response_str[:500] if isinstance(eval_response_str, str) else str(eval_response_str)[:500]}")
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

