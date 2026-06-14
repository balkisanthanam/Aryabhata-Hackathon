"""
Student Evaluation Function App — Azure Durable Functions (Python v2).

Queue-triggered pipeline:
  feedback-jobs queue → orchestrator → activities → DB update

All utilities extracted to utils/, activities in activities/, orchestrator in orchestrator.py.
"""
import logging
import json
import traceback
import azure.functions as func
import azure.durable_functions as df

from orchestrator import orchestrator_function
from activities.read_evaluation import read_evaluation_activity
from activities.split_student_hw import split_student_hw_activity
from activities.fetch_student_images import fetch_student_images_activity
from activities.parse_text_ref import parse_text_ref_activity
from activities.split_textbook import split_textbook_activity
from activities.validate_inputs import validate_inputs_activity
from activities.get_chapter_pdf import get_chapter_pdf_activity
from activities.evaluate_batch import evaluate_batch_activity
from activities.update_evaluation import update_evaluation_activity
from activities.save_checkpoint import save_checkpoint_activity
from activities.load_checkpoint import load_checkpoint_activity

# ─── App Init ──────────────────────────────────────────────────────────────────
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)


# ─── Queue Trigger ─────────────────────────────────────────────────────────────
@app.queue_trigger(
    arg_name="msg",
    queue_name="feedback-jobs",
    connection="FEEDBACK_QUEUE_CONNECTION",
)
@app.durable_client_input(client_name="client")
async def feedback_queue_trigger(msg: func.QueueMessage, client):
    """
    Queue trigger: receives a job_id from feedback-jobs queue,
    starts the durable orchestrator with the job_id as both instance ID and input.
    Using job_id as instance ID provides natural deduplication.
    """
    try:
        raw_body = msg.get_body()
        logging.info(f"Queue trigger raw body: {raw_body!r}")
        job_id = raw_body.decode("utf-8").strip().strip('"')
        logging.info(f"Queue trigger received job_id: {job_id}")
        logging.info(f"Durable client type: {type(client)}")

        # Use job_id as instance ID for idempotency
        instance_id = await client.start_new(
            "evaluation_orchestrator",
            instance_id=job_id,
            client_input=job_id,
        )
        logging.info(f"Started orchestration {instance_id} for job {job_id}")
    except Exception as e:
        logging.error(f"Queue trigger FAILED: {e}")
        logging.error(traceback.format_exc())
        raise


# ─── Orchestrator ──────────────────────────────────────────────────────────────
@app.orchestration_trigger(context_name="context")
def evaluation_orchestrator(context: df.DurableOrchestrationContext):
    """Durable orchestrator — delegates to orchestrator.py via yield from."""
    result = yield from orchestrator_function(context)
    return result


# ─── Activity Functions ────────────────────────────────────────────────────────
@app.activity_trigger(input_name="jobId")
def read_evaluation(jobId: str):
    return read_evaluation_activity(jobId)


@app.activity_trigger(input_name="inputData")
def split_student_hw(inputData: dict):
    return split_student_hw_activity(inputData)


@app.activity_trigger(input_name="inputData")
def fetch_student_images(inputData: dict):
    return fetch_student_images_activity(inputData)


@app.activity_trigger(input_name="inputData")
def parse_text_ref(inputData: dict):
    return parse_text_ref_activity(inputData)


@app.activity_trigger(input_name="inputData")
def split_textbook(inputData: dict):
    return split_textbook_activity(inputData)


@app.activity_trigger(input_name="inputData")
def validate_inputs(inputData: dict):
    return validate_inputs_activity(inputData)


@app.activity_trigger(input_name="inputData")
def get_chapter_pdf(inputData: dict):
    return get_chapter_pdf_activity(inputData)


@app.activity_trigger(input_name="inputData")
def evaluate_batch(inputData: dict):
    return evaluate_batch_activity(inputData)


@app.activity_trigger(input_name="inputData")
def update_evaluation(inputData: dict):
    return update_evaluation_activity(inputData)


@app.activity_trigger(input_name="inputData")
def save_checkpoint(inputData: dict):
    return save_checkpoint_activity(inputData)


@app.activity_trigger(input_name="inputData")
def load_checkpoint(inputData: dict):
    return load_checkpoint_activity(inputData)
