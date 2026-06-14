"""
Launch (or re-attach to) a Vertex AI tuning job for Aryabhata's M3 SFT.

Stages:
  1. Validate auth (Application Default Credentials).
  2. Validate the local Vertex JSONL dataset (line count, basic shape).
  3. Idempotently upload the dataset to GCS (skip if same CRC32C already there).
  4. Submit a Vertex tuning job (google-genai SDK, v1beta1, regional endpoint).
  5. Poll until terminal state. On success, record the tuned endpoint to
     runs/tuning_jobs.json so batch_evaluator.py --model flash-tuned can pick it up.

CLI modes:
  --dry-run                  : auth + dataset + GCS bucket check. No billable submit.
  (no flag)                  : full submit + poll-until-terminal.
  --no-wait                  : submit, record state=RUNNING, exit immediately.
  --check <job.name>         : re-attach to an existing job, poll until terminal,
                               update runs/tuning_jobs.json.

Region fallback (R6 in M3 plan): if us-central1 doesn't accept gemini-2.5-flash
for tuning, pass --location us-east5 and/or --base-model gemini-2.5-flash-lite.

Prereqs (verify ONCE before first dry-run):
  gcloud auth application-default login
  gcloud config set project animated-rope-453904-j7
  # IAM check (REPLACE PLACEHOLDER_EMAIL with your actual gcloud-login email;
  # one line on PowerShell — no bash-style line continuations):
  gcloud projects get-iam-policy animated-rope-453904-j7 --flatten="bindings[].members" --filter="bindings.members:PLACEHOLDER_EMAIL" --format="value(bindings.role)"
  # Expect: roles/aiplatform.user + roles/storage.objectAdmin (or higher, e.g. roles/owner / roles/editor).

Install (only if missing):
  pip install google-genai google-cloud-storage google-crc32c
"""

import argparse
import base64
import json
import os
import shutil
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CWD = Path(__file__).resolve().parent
RUNS_DIR = CWD / "runs"
JOBS_LEDGER = RUNS_DIR / "tuning_jobs.json"

DEFAULT_PROJECT = "animated-rope-453904-j7"
DEFAULT_LOCATION = "us-central1"
DEFAULT_BUCKET = "aryabhata-tuning"
DEFAULT_GCS_PREFIX = "m3"
DEFAULT_DATASET = "gold_sft_vertex_v1.jsonl"
DEFAULT_BASE_MODEL = "gemini-2.5-flash"
DEFAULT_DISPLAY_NAME = "aryabhata-flash-sft-v1"

TERMINAL_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
POLL_INTERVAL_SECONDS = 60


# ---------------------------------------------------------------------------
# Lazy SDK imports — give a clean install hint if missing instead of a stack trace.

def _import_genai():
    try:
        from google import genai
        from google.genai.types import HttpOptions, CreateTuningJobConfig, TuningDataset
        return genai, HttpOptions, CreateTuningJobConfig, TuningDataset
    except ImportError as e:
        print(f"ERROR: google-genai SDK not installed ({e}). Run: pip install google-genai", file=sys.stderr)
        sys.exit(2)


def _import_storage():
    try:
        from google.cloud import storage
        from google.cloud.exceptions import NotFound
        return storage, NotFound
    except ImportError as e:
        print(f"ERROR: google-cloud-storage not installed ({e}). Run: pip install google-cloud-storage", file=sys.stderr)
        sys.exit(2)


def _import_auth():
    try:
        import google.auth
        return google.auth
    except ImportError as e:
        print(f"ERROR: google-auth not installed ({e}). Run: pip install google-auth", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# CRC32C helper for upload idempotency. google-crc32c is a transitive dep of
# google-cloud-storage in most installs; fall back to size-only comparison if absent.

def _local_crc32c_base64(path: Path) -> str | None:
    try:
        import google_crc32c
    except ImportError:
        return None
    hasher = google_crc32c.Checksum()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    return base64.b64encode(struct.pack(">I", int.from_bytes(hasher.digest(), "big"))).decode("ascii")


# ---------------------------------------------------------------------------
# Pre-flight checks.

def check_auth() -> str:
    google_auth = _import_auth()
    try:
        creds, project = google_auth.default()
    except Exception as e:
        print(f"ERROR: ADC not configured ({e}). Run: gcloud auth application-default login", file=sys.stderr)
        sys.exit(2)
    principal = (
        getattr(creds, "service_account_email", None)
        or getattr(creds, "_account", None)
        or getattr(creds, "quota_project_id", None)
        or "<unknown principal>"
    )
    print(f"  Auth: principal={principal}  default_project={project}")
    return principal


def check_dataset(path: Path) -> int:
    if not path.exists():
        print(f"ERROR: dataset not found: {path}", file=sys.stderr)
        sys.exit(2)
    line_count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                line_count += 1
    if line_count == 0:
        print(f"ERROR: dataset is empty: {path}", file=sys.stderr)
        sys.exit(2)
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Dataset: {path.name}  lines={line_count}  size={size_mb:.2f}MB")
    return line_count


def ensure_bucket(project: str, location: str, bucket_name: str, create_if_missing: bool):
    storage, NotFound = _import_storage()
    client = storage.Client(project=project)
    try:
        bucket = client.get_bucket(bucket_name)
        print(f"  GCS bucket: gs://{bucket_name}  (exists, location={bucket.location})")
        return bucket
    except NotFound:
        if not create_if_missing:
            print(f"  GCS bucket: gs://{bucket_name}  MISSING (would be created on real submit)")
            return None
        print(f"  GCS bucket: gs://{bucket_name}  MISSING — creating in {location}...")
        bucket = client.create_bucket(bucket_name, location=location)
        print(f"  GCS bucket: gs://{bucket_name}  CREATED")
        return bucket


def upload_dataset(bucket, dataset_path: Path, gcs_prefix: str) -> str:
    blob_name = f"{gcs_prefix}/{dataset_path.name}"
    blob = bucket.blob(blob_name)
    local_crc = _local_crc32c_base64(dataset_path)

    if blob.exists():
        blob.reload()
        same_crc = local_crc is not None and blob.crc32c == local_crc
        same_size = blob.size == dataset_path.stat().st_size
        if same_crc or (local_crc is None and same_size):
            reason = "matching crc32c" if same_crc else "matching size (crc32c lib not installed)"
            print(f"  GCS object: gs://{bucket.name}/{blob_name}  SKIP upload ({reason})")
            return f"gs://{bucket.name}/{blob_name}"
        print(f"  GCS object: gs://{bucket.name}/{blob_name}  EXISTS but differs — re-uploading")
    else:
        print(f"  GCS object: gs://{bucket.name}/{blob_name}  UPLOADING")

    blob.upload_from_filename(str(dataset_path))
    print(f"  GCS object: gs://{bucket.name}/{blob_name}  UPLOADED")
    return f"gs://{bucket.name}/{blob_name}"


# ---------------------------------------------------------------------------
# Tuning-job ledger (runs/tuning_jobs.json).

def _atomic_write_ledger(records: list[dict]) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    tmp_path = JOBS_LEDGER.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    os.replace(tmp_path, JOBS_LEDGER)


def _load_ledger() -> list[dict]:
    if not JOBS_LEDGER.exists():
        return []
    try:
        return json.loads(JOBS_LEDGER.read_text(encoding="utf-8"))
    except Exception:
        # Don't lose data on corruption — back it up and start fresh.
        backup = JOBS_LEDGER.with_suffix(f".corrupt.{int(time.time())}.json")
        shutil.copy2(JOBS_LEDGER, backup)
        print(f"  WARN: tuning_jobs.json was corrupt; backed up to {backup.name}", file=sys.stderr)
        return []


def record_job(job_dict: dict) -> None:
    records = _load_ledger()
    # Update-in-place if same job_name already present (re-checks shouldn't duplicate rows).
    name = job_dict.get("job_name")
    for i, r in enumerate(records):
        if r.get("job_name") == name:
            records[i] = {**r, **job_dict}
            _atomic_write_ledger(records)
            return
    records.append(job_dict)
    _atomic_write_ledger(records)


# ---------------------------------------------------------------------------
# Tuning-job lifecycle.

def _job_state(job) -> str:
    state = getattr(job, "state", None)
    return state.name if state is not None and hasattr(state, "name") else str(state)


def _extract_tuned_endpoint(job) -> tuple[str | None, str | None]:
    tuned = getattr(job, "tuned_model", None)
    if tuned is None:
        return (None, None)
    return (getattr(tuned, "endpoint", None), getattr(tuned, "model", None))


def submit_tuning_job(client, base_model: str, gcs_uri: str, display_name: str):
    _, _, CreateTuningJobConfig, TuningDataset = _import_genai()
    print(f"  Submitting tune: base_model={base_model}  dataset={gcs_uri}  display_name={display_name}")
    job = client.tunings.tune(
        base_model=base_model,
        training_dataset=TuningDataset(gcs_uri=gcs_uri),
        config=CreateTuningJobConfig(tuned_model_display_name=display_name),
    )
    print(f"  Launched: name={job.name}  state={_job_state(job)}")
    return job


def poll_until_terminal(client, job_name: str):
    """Re-fetches job every POLL_INTERVAL_SECONDS until terminal. Returns the final job object."""
    start = time.time()
    last_state = None
    while True:
        job = client.tunings.get(name=job_name)
        state = _job_state(job)
        elapsed = int(time.time() - start)
        if state != last_state:
            print(f"  [{elapsed:>5d}s] state={state}")
            last_state = state
        if state in TERMINAL_STATES:
            return job
        try:
            time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print(
                f"\n  Interrupted. Job continues server-side. Re-attach with:\n"
                f"    python launch_tuning_job.py --check {job_name}",
                file=sys.stderr,
            )
            sys.exit(130)


# ---------------------------------------------------------------------------
# Mode handlers.

def mode_dry_run(args) -> int:
    print("=== DRY RUN ===  (no billable submit)")
    check_auth()
    dataset_path = (CWD / args.dataset) if not Path(args.dataset).is_absolute() else Path(args.dataset)
    check_dataset(dataset_path)
    ensure_bucket(args.project, args.location, args.bucket, create_if_missing=False)
    gcs_uri = f"gs://{args.bucket}/{args.gcs_prefix}/{dataset_path.name}"
    print()
    print("Would launch:")
    print(f"  project        : {args.project}")
    print(f"  location       : {args.location}  (v1beta1 tuning API)")
    print(f"  base_model     : {args.base_model}")
    print(f"  display_name   : {args.display_name}")
    print(f"  training_data  : {gcs_uri}")
    print()
    print("To proceed for real:")
    print(f"  python {Path(__file__).name}")
    return 0


def _build_client(project: str, location: str):
    genai, HttpOptions, _, _ = _import_genai()
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=HttpOptions(api_version="v1beta1"),
    )


def mode_launch(args, *, wait: bool) -> int:
    print("=== LAUNCH ===" + ("" if wait else "  (--no-wait, will not poll)"))
    check_auth()
    dataset_path = (CWD / args.dataset) if not Path(args.dataset).is_absolute() else Path(args.dataset)
    check_dataset(dataset_path)
    bucket = ensure_bucket(args.project, args.location, args.bucket, create_if_missing=True)
    if bucket is None:
        print("ERROR: GCS bucket unavailable; aborting before submit.", file=sys.stderr)
        return 2
    gcs_uri = upload_dataset(bucket, dataset_path, args.gcs_prefix)

    client = _build_client(args.project, args.location)
    job = submit_tuning_job(client, args.base_model, gcs_uri, args.display_name)

    endpoint, model_resource = _extract_tuned_endpoint(job)
    base_record = {
        "job_name": job.name,
        "tuned_endpoint": endpoint,
        "tuned_model": model_resource,
        "base_model": args.base_model,
        "dataset_uri": gcs_uri,
        "display_name": args.display_name,
        "project": args.project,
        "location": args.location,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": _job_state(job),
    }
    record_job(base_record)
    print(f"  Recorded to: {JOBS_LEDGER}")

    if not wait:
        print(f"  Exiting without polling. Re-attach with:")
        print(f"    python {Path(__file__).name} --check {job.name}")
        return 0

    final_job = poll_until_terminal(client, job.name)
    final_state = _job_state(final_job)
    endpoint, model_resource = _extract_tuned_endpoint(final_job)
    record_job({**base_record, "state": final_state, "tuned_endpoint": endpoint, "tuned_model": model_resource,
                "finished_timestamp": datetime.now(timezone.utc).isoformat()})

    if final_state != "JOB_STATE_SUCCEEDED":
        err = getattr(final_job, "error", None)
        print(f"ERROR: tuning ended with state={final_state}  error={err}", file=sys.stderr)
        return 1

    print(f"  SUCCESS: tuned_endpoint={endpoint}  tuned_model={model_resource}")
    return 0


def mode_check(args) -> int:
    print(f"=== CHECK ===  job={args.check}")
    check_auth()
    client = _build_client(args.project, args.location)
    job = client.tunings.get(name=args.check)
    state = _job_state(job)
    print(f"  current state={state}")
    if state not in TERMINAL_STATES:
        job = poll_until_terminal(client, args.check)
        state = _job_state(job)

    endpoint, model_resource = _extract_tuned_endpoint(job)
    record_job({
        "job_name": args.check,
        "tuned_endpoint": endpoint,
        "tuned_model": model_resource,
        "project": args.project,
        "location": args.location,
        "state": state,
        "checked_timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if state != "JOB_STATE_SUCCEEDED":
        err = getattr(job, "error", None)
        print(f"ERROR: tuning ended with state={state}  error={err}", file=sys.stderr)
        return 1
    print(f"  SUCCESS: tuned_endpoint={endpoint}  tuned_model={model_resource}")
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--location", default=DEFAULT_LOCATION, help="us-central1 default; fallback us-east5 per R6")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--gcs-prefix", default=DEFAULT_GCS_PREFIX)
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Path to Vertex-format JSONL (default: gold_sft_vertex_v1.jsonl in script dir)")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL, help="Fallback per R6: gemini-2.5-flash-lite")
    parser.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Auth + dataset + GCS reachability check. No billable submit.")
    mode.add_argument("--no-wait", action="store_true", help="Submit and exit; do not poll.")
    mode.add_argument("--check", metavar="JOB_NAME", help="Re-attach to existing job (projects/.../tuningJobs/<id>)")
    args = parser.parse_args()

    print(f"--- launch_tuning_job.py ---  cwd={CWD}")
    if args.dry_run:
        return mode_dry_run(args)
    if args.check:
        return mode_check(args)
    return mode_launch(args, wait=not args.no_wait)


if __name__ == "__main__":
    sys.exit(main())
