"""
Test Azure Connectivity - Blob Storage and PostgreSQL.

This script tests Azure services using stub data WITHOUT calling Gemini models.
Uses the actual db_client.py and blob_client.py implementations.

Use this to verify identity/connectivity issues before running the full pipeline.

Usage:
    # Test with managed identity (production)
    python test_azure_connectivity.py

    # Test with connection strings (local dev)
    python test_azure_connectivity.py --use-connection-strings
    
    # Test only database
    python test_azure_connectivity.py --db-only
    
    # Test only blob storage
    python test_azure_connectivity.py --blob-only
    
    # Cleanup test data after
    python test_azure_connectivity.py --cleanup
"""

import argparse
import json
import logging
import tempfile
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import the actual clients from your codebase
from db_client import DatabaseClient, get_db_client
from blob_client import BlobClient, get_blob_client, generate_blob_path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# Stub Test Data
# =============================================================================

STUB_QUESTION_CONTENT = {
    "question_id": "TEST_10.99",
    "question_text": r"This is a test question with LaTeX: $E = mc^2$. Calculate the energy.",
    "page_number": 99,
    "has_figure": True,
    "figure_info": [
        {
            "url": None,  # Will be set after blob upload
            "description": "Test diagram showing energy-mass equivalence",
            "type": "DIAGRAM"
        }
    ],
    "figure_references": ["Fig TEST.1"],
    "visual_data": {
        "type": "DIAGRAM",
        "description": "Test diagram",
        "box_2d": [100, 100, 500, 500]
    }
}

STUB_SOLUTION = {
    "question_id": "TEST_10.99",
    "question_text": r"This is a test question with LaTeX: $E = mc^2$. Calculate the energy.",
    "steps": [
        {
            "step_number": 1,
            "step_type": "conceptual",
            "nudge_hint": "What famous equation relates mass and energy?",
            "explanation": r"Einstein's mass-energy equivalence states that mass and energy are interchangeable. The equation $E = mc^2$ shows that a small amount of mass contains enormous energy.",
            "latex_formula": r"$E = mc^2$",
            "visual_asset": {"required": False, "type": "none", "data": "", "caption": ""},
            "embedded_formats": []
        },
        {
            "step_number": 2,
            "step_type": "calculation",
            "nudge_hint": "Substitute the given mass value into the equation.",
            "explanation": r"Given mass $m = 1 \text{ kg}$ and $c = 3 \times 10^8 \text{ m/s}$, we calculate: $E = 1 \times (3 \times 10^8)^2 = 9 \times 10^{16} \text{ J}$",
            "latex_formula": r"$E = 9 \times 10^{16} \text{ J}$",
            "visual_asset": {"required": False, "type": "none", "data": "", "caption": ""},
            "embedded_formats": []
        }
    ],
    "final_answer": r"$E = 9 \times 10^{16} \text{ J}$ or 90 petajoules",
    "rendered_text": "## Question TEST_10.99\n\nThis is a test question...\n\n### Final Answer\n$E = 9 \\times 10^{16} \\text{ J}$",
    "generated_images": []
}

# Test chapter that should exist in your DB (Physics Chapter 10)
TEST_CLASS = "11"
TEST_SUBJECT = "Physics"
TEST_CHAPTER_NUMBER = "10"  # Chapter 10 - Thermal Properties
TEST_EXERCISE_TITLE = "_TEST_EXERCISE"  # Prefixed to avoid conflicts


# =============================================================================
# Test Functions
# =============================================================================

def create_test_image() -> Path:
    """Create a simple test PNG image."""
    try:
        from PIL import Image, ImageDraw
        
        # Create a 200x200 image with gradient and text
        img = Image.new('RGB', (200, 200), color='white')
        draw = ImageDraw.Draw(img)
        
        # Draw a border
        draw.rectangle([5, 5, 195, 195], outline='blue', width=3)
        
        # Draw diagonal lines
        draw.line([10, 10, 190, 190], fill='red', width=2)
        draw.line([10, 190, 190, 10], fill='green', width=2)
        
        # Draw a circle
        draw.ellipse([50, 50, 150, 150], outline='purple', width=2)
        
        # Add text
        draw.text((60, 90), "TEST", fill='black')
        
        # Save to temp file
        temp_path = Path(tempfile.gettempdir()) / "test_aryabhatta_image.png"
        img.save(temp_path)
        logger.info(f"Created test image: {temp_path}")
        return temp_path
        
    except ImportError:
        logger.warning("PIL not installed. Creating minimal PNG file...")
        # Minimal valid PNG (1x1 red pixel)
        png_bytes = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
            0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x05, 0xFE,
            0xD4, 0xEF, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,  # IEND chunk
            0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        temp_path = Path(tempfile.gettempdir()) / "test_aryabhatta_image.png"
        temp_path.write_bytes(png_bytes)
        logger.info(f"Created minimal test PNG: {temp_path}")
        return temp_path


def test_blob_storage(use_connection_string: bool = False, cleanup: bool = False) -> bool:
    """
    Test Azure Blob Storage connectivity using blob_client.py.
    
    Returns:
        True if all tests pass
    """
    logger.info("=" * 60)
    logger.info("TESTING AZURE BLOB STORAGE")
    logger.info("=" * 60)
    
    blob_path = None
    
    try:
        # Initialize client using the actual get_blob_client function
        logger.info("Initializing BlobClient...")
        if use_connection_string:
            conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
            if not conn_str:
                logger.error("❌ AZURE_STORAGE_CONNECTION_STRING not set")
                logger.info("   Set it with: set AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=...")
                return False
            client = BlobClient(connection_string=conn_str, use_managed_identity=False)
        else:
            client = get_blob_client(use_managed_identity=True)
        
        logger.info(f"   Account: {client.account_name}")
        logger.info(f"   Container: {client.container_name}")
        
        # Create test image
        test_image = create_test_image()
        
        # Test the generate_blob_path helper function
        logger.info("Testing generate_blob_path()...")
        blob_path = generate_blob_path(
            class_level=TEST_CLASS,
            subject=TEST_SUBJECT,
            chapter_number=TEST_CHAPTER_NUMBER,
            question_ref="TEST_10.99",
            file_type="test_figure"
        )
        logger.info(f"   Generated path: {blob_path}")
        
        # Add timestamp to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_path = f"_test/connectivity_test_{timestamp}.png"
        
        # Test upload
        logger.info(f"Uploading test image to: {blob_path}")
        url = client.upload_image(
            local_path=test_image,
            blob_path=blob_path,
            content_type="image/png"
        )
        
        logger.info(f"✅ Upload successful!")
        logger.info(f"   URL: {url}")
        
        # Test blob_exists
        logger.info("Testing blob_exists()...")
        exists = client.blob_exists(blob_path)
        if exists:
            logger.info(f"✅ blob_exists() returned True")
        else:
            logger.warning(f"⚠️ blob_exists() returned False (unexpected)")
        
        # Test get_blob_url
        logger.info("Testing get_blob_url()...")
        generated_url = client.get_blob_url(blob_path)
        logger.info(f"   get_blob_url(): {generated_url}")
        
        # Verify URL matches
        if url == generated_url:
            logger.info(f"✅ URLs match")
        else:
            logger.warning(f"⚠️ URLs don't match exactly (may differ in query string)")
        
        # Cleanup if requested
        if cleanup:
            logger.info("Cleaning up test blob...")
            try:
                deleted = client.delete_blob(blob_path)
                if deleted:
                    logger.info(f"✅ Deleted test blob: {blob_path}")
                else:
                    logger.warning(f"⚠️ Blob not found for deletion")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete test blob: {e}")
        else:
            logger.info(f"   (Use --cleanup to delete test blob)")
        
        # Cleanup local test image
        if test_image.exists():
            test_image.unlink()
        
        logger.info("✅ Blob storage tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Blob storage test FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_database(use_connection_string: bool = False, cleanup: bool = False) -> bool:
    """
    Test PostgreSQL database connectivity using db_client.py.
    
    Returns:
        True if all tests pass
    """
    logger.info("=" * 60)
    logger.info("TESTING POSTGRESQL DATABASE")
    logger.info("=" * 60)
    
    exercise_id = None
    question_id = None
    
    try:
        # Initialize client using the actual functions
        logger.info("Initializing DatabaseClient...")
        if use_connection_string:
            conn_str = os.environ.get("AZURE_PG_CONNECTION_STRING")
            if not conn_str:
                logger.error("❌ AZURE_PG_CONNECTION_STRING not set")
                logger.info("   Set it with: set AZURE_PG_CONNECTION_STRING=postgresql://user:pass@host:5432/db")
                return False
            client = DatabaseClient(connection_string=conn_str, use_managed_identity=False)
        else:
            client = get_db_client(use_managed_identity=True)
        
        logger.info(f"   Host: {client.host}")
        logger.info(f"   Database: {client.database}")
        
        with client:
            # Test 1: Basic connection
            logger.info("Test 1: Basic connection...")
            conn = client.connect()
            logger.info("✅ Database connection established")
            
            # Test 2: Read ChapterData using get_chapter_id
            logger.info(f"Test 2: Looking up chapter using get_chapter_id()...")
            logger.info(f"   Params: Class={TEST_CLASS}, Subject={TEST_SUBJECT}, ChapterNumber={TEST_CHAPTER_NUMBER}")
            
            chapter_id = client.get_chapter_id(TEST_CLASS, TEST_SUBJECT, TEST_CHAPTER_NUMBER)
            
            if chapter_id:
                logger.info(f"✅ Found ChapterId: {chapter_id}")
            else:
                logger.warning(f"⚠️ Chapter not found with exact params.")
                logger.info("   Listing available chapters...")
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT chapterid, class, subject, chapternumber, chaptertitle 
                        FROM chapterdata 
                        WHERE subject = %s
                        ORDER BY chapterid
                        LIMIT 10
                    """, (TEST_SUBJECT,))
                    rows = cur.fetchall()
                    if rows:
                        logger.info(f"   Available {TEST_SUBJECT} chapters:")
                        for row in rows:
                            logger.info(f"     ChapterId={row[0]}, Class={row[1]}, Ch={row[3]}: {row[4]}")
                        # Use first available chapter for testing
                        chapter_id = rows[0][0]
                        logger.info(f"   Using ChapterId={chapter_id} for remaining tests")
                    else:
                        logger.error(f"❌ No chapters found for subject {TEST_SUBJECT}")
                        logger.info("   Make sure ChapterData table is populated.")
                        return False
            
            # Test 3: Upsert Exercise using upsert_exercise
            logger.info(f"Test 3: Upserting test exercise using upsert_exercise()...")
            exercise_data = {
                "title": TEST_EXERCISE_TITLE,
                "test": True, 
                "timestamp": datetime.now().isoformat(),
                "question_ids": ["TEST_10.99"]
            }
            
            exercise_id = client.upsert_exercise(
                chapter_id=chapter_id,
                exercise_title=TEST_EXERCISE_TITLE,
                total_questions=1,
                other_data=exercise_data
            )
            logger.info(f"✅ Upserted ExerciseId: {exercise_id}")
            
            # Verify exercise was inserted
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT exercise, totalquestions, otherdata 
                    FROM exercisedata 
                    WHERE exerciseid = %s
                """, (exercise_id,))
                row = cur.fetchone()
                if row:
                    logger.info(f"   Verified: Exercise='{row[0]}', totalQuestions={row[1]}")
                    other_data = row[2]
                    if other_data:
                        logger.info(f"   OtherData keys: {list(other_data.keys()) if isinstance(other_data, dict) else 'N/A'}")
            
            # Test 4: Upsert Question with Content JSONB using upsert_question
            logger.info("Test 4: Upserting test question using upsert_question()...")
            
            question_id = client.upsert_question(
                exercise_id=exercise_id,
                question_ref=STUB_QUESTION_CONTENT["question_id"],
                content=STUB_QUESTION_CONTENT,
                solution=None  # No solution yet
            )
            logger.info(f"✅ Upserted QuestionId: {question_id}")
            
            # Verify question was inserted
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT question_ref, content, solution 
                    FROM questiondata 
                    WHERE questionid = %s
                """, (question_id,))
                row = cur.fetchone()
                if row:
                    content = row[1]
                    logger.info(f"   Verified: Question_Ref='{row[0]}'")
                    logger.info(f"   Content has_figure: {content.get('has_figure') if isinstance(content, dict) else 'N/A'}")
                    logger.info(f"   Solution: {'Present' if row[2] else 'None (expected)'}")
            
            # Test 5: Update Solution using update_question_solution
            logger.info("Test 5: Updating question with solution using update_question_solution()...")
            
            success = client.update_question_solution(
                question_id=question_id,
                solution=STUB_SOLUTION
            )
            
            if success:
                logger.info(f"✅ Updated solution for QuestionId: {question_id}")
            else:
                logger.error(f"❌ Failed to update solution")
                return False
            
            # Test 6: Verify stored data
            logger.info("Test 6: Verifying stored Content and Solution JSONB...")
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT content, solution 
                    FROM questiondata 
                    WHERE questionid = %s
                """, (question_id,))
                row = cur.fetchone()
                
                if row:
                    content = row[0] if isinstance(row[0], dict) else json.loads(row[0]) if row[0] else {}
                    solution = row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {}
                    
                    logger.info(f"✅ Content JSONB stored: {len(json.dumps(content))} bytes")
                    logger.info(f"   - question_id: {content.get('question_id')}")
                    logger.info(f"   - has_figure: {content.get('has_figure')}")
                    logger.info(f"   - figure_references: {content.get('figure_references')}")
                    
                    logger.info(f"✅ Solution JSONB stored: {len(json.dumps(solution))} bytes")
                    logger.info(f"   - steps count: {len(solution.get('steps', []))}")
                    logger.info(f"   - final_answer: {solution.get('final_answer', '')[:50]}...")
                else:
                    logger.error("❌ Could not read back stored data")
                    return False
            
            # Test 7: Test update_question_content (merge into existing JSONB)
            logger.info("Test 7: Testing update_question_content() for JSONB merge...")
            
            success = client.update_question_content(
                question_id=question_id,
                content_updates={"test_update": True, "updated_at": datetime.now().isoformat()}
            )
            
            if success:
                logger.info(f"✅ Merged content updates for QuestionId: {question_id}")
                
                # Verify merge
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT content->>'test_update', content->>'question_id'
                        FROM questiondata 
                        WHERE questionid = %s
                    """, (question_id,))
                    row = cur.fetchone()
                    if row and row[0] == 'true' and row[1] == STUB_QUESTION_CONTENT["question_id"]:
                        logger.info(f"   Verified: test_update added, original question_id preserved")
                    else:
                        logger.warning(f"   JSONB merge result unexpected: {row}")
            else:
                logger.warning(f"⚠️ update_question_content returned False")
            
            # Cleanup if requested
            if cleanup:
                logger.info("Cleaning up test data...")
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM questiondata WHERE questionid = %s
                    """, (question_id,))
                    cur.execute("""
                        DELETE FROM exercisedata WHERE exerciseid = %s
                    """, (exercise_id,))
                    conn.commit()
                logger.info(f"✅ Deleted test exercise (id={exercise_id}) and question (id={question_id})")
            else:
                logger.info(f"   (Use --cleanup to delete test data)")
            
            logger.info("✅ All database tests passed!")
            return True
            
    except Exception as e:
        logger.error(f"❌ Database test FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_combined_flow(use_connection_string: bool = False, cleanup: bool = False) -> bool:
    """
    Test the complete flow: Upload image -> Store URL in DB JSONB.
    
    This simulates what e2e_pipeline.py does during ingestion.
    
    Returns:
        True if all tests pass
    """
    logger.info("=" * 60)
    logger.info("TESTING COMBINED FLOW (Blob + DB)")
    logger.info("=" * 60)
    
    blob_path = None
    question_id = None
    exercise_id = None
    chapter_id = None
    
    try:
        # Step 1: Initialize both clients
        logger.info("Step 1: Initializing clients...")
        
        if use_connection_string:
            blob_conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
            db_conn = os.environ.get("AZURE_PG_CONNECTION_STRING")
            
            if not blob_conn or not db_conn:
                logger.error("❌ Both AZURE_STORAGE_CONNECTION_STRING and AZURE_PG_CONNECTION_STRING required")
                return False
            
            blob_client = BlobClient(connection_string=blob_conn, use_managed_identity=False)
            db_client = DatabaseClient(connection_string=db_conn, use_managed_identity=False)
        else:
            blob_client = get_blob_client(use_managed_identity=True)
            db_client = get_db_client(use_managed_identity=True)
        
        logger.info(f"   Blob: {blob_client.account_name}/{blob_client.container_name}")
        logger.info(f"   DB: {db_client.host}/{db_client.database}")
        
        # Step 2: Create and upload test image
        logger.info("Step 2: Creating and uploading test image...")
        test_image = create_test_image()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_path = generate_blob_path(
            class_level=TEST_CLASS,
            subject=TEST_SUBJECT,
            chapter_number=TEST_CHAPTER_NUMBER,
            question_ref=f"TEST_COMBINED_{timestamp}",
            file_type="figure"
        )
        
        image_url = blob_client.upload_image(
            local_path=test_image,
            blob_path=blob_path
        )
        logger.info(f"✅ Image uploaded: {image_url}")
        
        # Step 3: Build question content with image URL (like e2e_pipeline does)
        logger.info("Step 3: Building question content with image URL...")
        content_with_url = {
            "question_text": STUB_QUESTION_CONTENT["question_text"],
            "page_number": STUB_QUESTION_CONTENT["page_number"],
            "has_figure": True,
            "figure_info": [
                {
                    "url": image_url,
                    "description": "Test figure uploaded via combined flow test",
                    "type": "DIAGRAM",
                    "local_path": str(test_image)
                }
            ],
            "figure_references": ["Fig TEST.COMBINED"],
            "visual_data": {
                "type": "DIAGRAM",
                "description": "Test diagram",
                "cropped_image_path": str(test_image)
            }
        }
        logger.info(f"   figure_info[0].url set to blob URL")
        
        # Step 4: Insert into database
        logger.info("Step 4: Inserting into database...")
        
        with db_client:
            # Get chapter ID
            chapter_id = db_client.get_chapter_id(TEST_CLASS, TEST_SUBJECT, TEST_CHAPTER_NUMBER)
            if not chapter_id:
                logger.warning("Chapter not found, getting first available...")
                conn = db_client.connect()
                with conn.cursor() as cur:
                    cur.execute('SELECT chapterid FROM chapterdata LIMIT 1')
                    row = cur.fetchone()
                    chapter_id = row[0] if row else None
                    
            if not chapter_id:
                raise ValueError("No chapters in database - please populate ChapterData first")
            
            logger.info(f"   Using ChapterId: {chapter_id}")
            
            # Upsert exercise
            exercise_id = db_client.upsert_exercise(
                chapter_id=chapter_id,
                exercise_title=TEST_EXERCISE_TITLE + "_COMBINED",
                total_questions=1,
                other_data={"test": True, "flow": "combined"}
            )
            logger.info(f"   ExerciseId: {exercise_id}")
            
            # Upsert question with image URL in content
            question_id = db_client.upsert_question(
                exercise_id=exercise_id,
                question_ref=f"TEST_COMBINED_{timestamp}",
                content=content_with_url,
                solution=STUB_SOLUTION
            )
            logger.info(f"✅ Question inserted: QuestionId={question_id}")
            
            # Step 5: Verify the URL is correctly stored in JSONB
            logger.info("Step 5: Verifying image URL is stored in Content JSONB...")
            conn = db_client.connect()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT content->'figure_info'->0->>'url'
                    FROM questiondata
                    WHERE questionid = %s
                """, (question_id,))
                row = cur.fetchone()
                stored_url = row[0] if row else None
                
                if stored_url == image_url:
                    logger.info(f"✅ Image URL correctly stored in Content.figure_info[0].url")
                    logger.info(f"   URL: {stored_url[:80]}...")
                else:
                    logger.error(f"❌ URL mismatch!")
                    logger.error(f"   Expected: {image_url}")
                    logger.error(f"   Got: {stored_url}")
                    return False
            
            # Step 6: Verify solution is also stored
            logger.info("Step 6: Verifying solution is stored...")
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT solution->>'final_answer', jsonb_array_length(solution->'steps')
                    FROM questiondata
                    WHERE questionid = %s
                """, (question_id,))
                row = cur.fetchone()
                if row and row[0] and row[1]:
                    logger.info(f"✅ Solution stored: {row[1]} steps, final_answer present")
                else:
                    logger.warning(f"⚠️ Solution may not be fully stored: {row}")
            
            # Cleanup
            if cleanup:
                logger.info("Cleaning up test data...")
                with conn.cursor() as cur:
                    # Delete ALL questions for this exercise (in case of leftover data)
                    cur.execute('DELETE FROM questiondata WHERE exerciseid = %s', (exercise_id,))
                    cur.execute('DELETE FROM exercisedata WHERE exerciseid = %s', (exercise_id,))
                    conn.commit()
                
                try:
                    blob_client.delete_blob(blob_path)
                    logger.info(f"✅ Deleted test blob and database records")
                except Exception as e:
                    logger.warning(f"⚠️ Could not delete blob: {e}")
            else:
                logger.info(f"   (Use --cleanup to delete test data)")
        
        # Cleanup local test image
        if test_image.exists():
            test_image.unlink()
        
        logger.info("✅ Combined flow test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Combined flow test FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Test Azure connectivity using the actual db_client.py and blob_client.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script uses stub data to test Azure Blob Storage and PostgreSQL connectivity
WITHOUT calling Gemini models. Run this first to debug identity/connectivity issues.

Environment Variables (for --use-connection-strings):
    AZURE_PG_CONNECTION_STRING       PostgreSQL connection string
    AZURE_STORAGE_CONNECTION_STRING  Azure Storage connection string

Examples:
    # Test with managed identity (requires 'az login' first)
    az login
    python test_azure_connectivity.py
    
    # Test with connection strings
    set AZURE_PG_CONNECTION_STRING=postgresql://user:pass@server.postgres.database.azure.com:5432/postgres?sslmode=require
    set AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
    python test_azure_connectivity.py --use-connection-strings
    
    # Test only database
    python test_azure_connectivity.py --db-only
    
    # Test only blob storage  
    python test_azure_connectivity.py --blob-only
    
    # Run all tests and cleanup test data
    python test_azure_connectivity.py --cleanup
        """
    )
    parser.add_argument("--use-connection-strings", action="store_true",
                        help="Use connection strings instead of managed identity")
    parser.add_argument("--db-only", action="store_true",
                        help="Test only database connectivity")
    parser.add_argument("--blob-only", action="store_true",
                        help="Test only blob storage connectivity")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete test data after testing")
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("AZURE CONNECTIVITY TEST")
    logger.info("=" * 60)
    logger.info(f"Auth mode: {'Connection Strings' if args.use_connection_strings else 'Managed Identity'}")
    logger.info(f"Cleanup: {args.cleanup}")
    logger.info("")
    
    results = {}
    
    # Run tests based on arguments
    if not args.db_only:
        results["blob"] = test_blob_storage(
            use_connection_string=args.use_connection_strings,
            cleanup=args.cleanup
        )
        logger.info("")
    
    if not args.blob_only:
        results["db"] = test_database(
            use_connection_string=args.use_connection_strings,
            cleanup=args.cleanup
        )
        logger.info("")
    
    # Only run combined test if both individual tests passed
    if not args.db_only and not args.blob_only:
        if results.get("blob") and results.get("db"):
            results["combined"] = test_combined_flow(
                use_connection_string=args.use_connection_strings,
                cleanup=args.cleanup
            )
        else:
            logger.info("Skipping combined test (blob or db test failed)")
            results["combined"] = False
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"  {test_name.upper()}: {status}")
        if not passed:
            all_passed = False
    
    logger.info("")
    if all_passed:
        logger.info("🎉 All tests passed! Azure connectivity is working.")
        logger.info("   You can now run the full E2E pipeline.")
    else:
        logger.error("💥 Some tests failed. Check the logs above for details.")
        logger.info("")
        logger.info("Troubleshooting tips:")
        logger.info("  - For managed identity: Run 'az login' first")
        logger.info("  - For connection strings: Set AZURE_PG_CONNECTION_STRING and AZURE_STORAGE_CONNECTION_STRING")
        logger.info("  - Check firewall rules on PostgreSQL and Storage Account")
        logger.info("  - Verify the identity has proper RBAC roles assigned")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
