"""
Database Client for AryaBhatta E2E Pipeline.

This module provides PostgreSQL database operations with:
- Azure Managed Identity authentication (DefaultAzureCredential)
- Connection string fallback for local development
- UPSERT operations for idempotent reruns

Tables:
- ChapterData: Book chapters metadata
- ExerciseData: Exercise sections within chapters
- QuestionData: Individual questions with solutions

All operations support the --force-rerun flag via UPSERT.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ExerciseRecord:
    """Exercise record for database insertion."""
    chapter_id: int
    exercise_title: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None


@dataclass
class QuestionRecord:
    """Question record for database insertion."""
    exercise_id: int
    question_ref: str  # e.g., "10.1"
    question_text: str
    has_figure: bool = False
    figure_url: Optional[str] = None
    solution_text: Optional[str] = None
    solution_json: Optional[str] = None  # Full JSON with steps


class DatabaseClient:
    """
    PostgreSQL database client with Azure Managed Identity support.
    
    Authentication priority:
    1. Azure Managed Identity (DefaultAzureCredential)
    2. Connection string from environment variable
    3. Explicit connection parameters
    
    Usage:
        # With managed identity (production)
        client = DatabaseClient(use_managed_identity=True)
        
        # With connection string (local dev)
        client = DatabaseClient(connection_string="...")
        
        # Operations
        exercise_id = client.upsert_exercise(exercise)
        question_id = client.upsert_question(question)
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        connection_string: Optional[str] = None,
        use_managed_identity: bool = True,
        sslmode: str = "require"
    ):
        """
        Initialize database client.
        
        Args:
            host: PostgreSQL host (e.g., <YOUR_PG_SERVER>.postgres.database.azure.com)
            database: Database name (e.g., postgres)
            user: Username (without @servername for managed identity)
            password: Password (ignored if using managed identity)
            connection_string: Full connection string (overrides other params)
            use_managed_identity: Use Azure DefaultAzureCredential for auth
            sslmode: SSL mode (require for Azure)
        """
        self.host = host or os.environ.get("AZURE_PG_HOST", "<YOUR_PG_SERVER>.postgres.database.azure.com")
        self.database = database or os.environ.get("AZURE_PG_DATABASE", "postgres")
        # For Entra auth, user must be the full UPN (external users need #EXT# format)
        self.user = user or os.environ.get("AZURE_PG_USER", "<YOUR_ENTRA_USER>@<YOUR_TENANT>.onmicrosoft.com")
        self.password = password
        self.connection_string = connection_string or os.environ.get("AZURE_PG_CONNECTION_STRING")
        self.use_managed_identity = use_managed_identity
        self.sslmode = sslmode
        self._connection = None
        
        logger.info(f"DatabaseClient initialized: host={self.host}, database={self.database}, "
                    f"managed_identity={use_managed_identity}")
    
    def _get_access_token(self) -> str:
        """Get access token using Azure DefaultAzureCredential."""
        try:
            from azure.identity import DefaultAzureCredential
            
            credential = DefaultAzureCredential()
            # PostgreSQL token scope
            token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
            logger.debug("Successfully obtained managed identity token")
            return token.token
        except Exception as e:
            logger.error(f"Failed to get managed identity token: {e}")
            raise
    
    def connect(self) -> psycopg2.extensions.connection:
        """
        Establish database connection.
        
        Returns:
            psycopg2 connection object
        """
        if self._connection and not self._connection.closed:
            return self._connection
        
        try:
            if self.connection_string:
                # Use full connection string
                logger.info("Connecting using connection string")
                self._connection = psycopg2.connect(self.connection_string)
            
            elif self.use_managed_identity:
                # Use Azure Managed Identity
                logger.info("Connecting using Azure Managed Identity")
                access_token = self._get_access_token()
                
                self._connection = psycopg2.connect(
                    host=self.host,
                    database=self.database,
                    user=self.user,
                    password=access_token,
                    sslmode=self.sslmode
                )
            
            else:
                # Use password authentication
                logger.info("Connecting using password authentication")
                if not self.password:
                    raise ValueError("Password required when not using managed identity")
                
                self._connection = psycopg2.connect(
                    host=self.host,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    sslmode=self.sslmode
                )
            
            logger.info("Database connection established")
            return self._connection
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def close(self):
        """Close database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.info("Database connection closed")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # =========================================================================
    # Lookup Operations
    # =========================================================================
    
    def get_chapter_id(
        self, 
        class_level: str, 
        subject: str, 
        chapter_number: str
    ) -> Optional[int]:
        """
        Get ChapterId for a given class, subject, and chapter number.
        
        Args:
            class_level: Class (e.g., '11', '12')
            subject: Subject name (e.g., 'Maths', 'Physics')
            chapter_number: Chapter number (VARCHAR, e.g., '10', 'VII', '2A')
            
        Returns:
            ChapterId if found, None otherwise
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chapterid FROM chapterdata
                WHERE class = %s AND subject = %s AND chapternumber = %s
                """,
                (class_level, subject, chapter_number)
            )
            row = cur.fetchone()
            return row[0] if row else None
    
    def get_exercise_id(self, chapter_id: int, exercise_title: str) -> Optional[int]:
        """
        Get ExerciseId for a given chapter and exercise title.
        
        Args:
            chapter_id: ChapterId from ChapterData table
            exercise_title: Exercise title (e.g., 'EXERCISES', 'EXERCISE 9.1')
            
        Returns:
            ExerciseId if found, None otherwise
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT exerciseid FROM exercisedata
                WHERE chapterid = %s AND exercise = %s
                """,
                (chapter_id, exercise_title)
            )
            row = cur.fetchone()
            return row[0] if row else None
    
    def get_question_id(self, exercise_id: int, question_ref: str) -> Optional[int]:
        """
        Get QuestionId for a given exercise and question reference.
        
        Args:
            exercise_id: ExerciseId from ExerciseData table
            question_ref: Question reference (e.g., '10.1', '9.15')
            
        Returns:
            QuestionId if found, None otherwise
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT questionid FROM questiondata
                WHERE exerciseid = %s AND question_ref = %s
                """,
                (exercise_id, question_ref)
            )
            row = cur.fetchone()
            return row[0] if row else None
    
    # =========================================================================
    # UPSERT Operations
    # =========================================================================
    
    def upsert_exercise(
        self,
        chapter_id: int,
        exercise_title: str,
        total_questions: Optional[int] = None,
        other_data: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Insert or update an exercise record.
        
        Uses ON CONFLICT on (ChapterId, Exercise) unique constraint.
        
        Args:
            chapter_id: ChapterId from ChapterData
            exercise_title: Exercise title (e.g., 'EXERCISES', 'EXERCISE 9.1')
            total_questions: Number of questions in this exercise
            other_data: Additional exercise metadata as JSONB (exercise section data)
            
        Returns:
            ExerciseId of the upserted record
        """
        import json as json_module
        
        conn = self.connect()
        with conn.cursor() as cur:
            # Convert other_data dict to JSON string for JSONB column
            other_data_json = json_module.dumps(other_data) if other_data else None
            
            cur.execute(
                """
                INSERT INTO exercisedata (chapterid, exercise, totalquestions, otherdata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (chapterid, exercise) 
                DO UPDATE SET 
                    totalquestions = COALESCE(EXCLUDED.totalquestions, exercisedata.totalquestions),
                    otherdata = COALESCE(EXCLUDED.otherdata, exercisedata.otherdata)
                RETURNING exerciseid
                """,
                (chapter_id, exercise_title, total_questions, other_data_json)
            )
            exercise_id = cur.fetchone()[0]
            conn.commit()
            
            logger.info(f"Upserted exercise: ChapterId={chapter_id}, Title='{exercise_title}', Questions={total_questions} -> ExerciseId={exercise_id}")
            return exercise_id
    
    def upsert_question(
        self,
        exercise_id: int,
        question_ref: str,
        content: Dict[str, Any],
        solution: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Insert or update a question record.
        
        Uses ON CONFLICT on (ExerciseId, Question_Ref) unique constraint.
        
        Args:
            exercise_id: ExerciseId from ExerciseData
            question_ref: Question reference (e.g., '10.1')
            content: Question content as JSONB (question_text, has_figure, figure_info, etc.)
            solution: Solution as JSONB (steps, final_answer, etc.) - optional
            
        Returns:
            QuestionId of the upserted record
        """
        import json as json_module
        
        conn = self.connect()
        with conn.cursor() as cur:
            content_json = json_module.dumps(content) if content else None
            solution_json = json_module.dumps(solution) if solution else None
            
            cur.execute(
                """
                INSERT INTO questiondata (exerciseid, question_ref, content, solution)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (exerciseid, question_ref) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    solution = COALESCE(EXCLUDED.solution, questiondata.solution)
                RETURNING questionid
                """,
                (exercise_id, question_ref, content_json, solution_json)
            )
            question_id = cur.fetchone()[0]
            conn.commit()
            
            logger.debug(f"Upserted question: ExerciseId={exercise_id}, Ref='{question_ref}' -> QuestionId={question_id}")
            return question_id
    
    def upsert_questions_batch(
        self,
        questions: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Batch upsert multiple questions.
        
        Each dict should have: exercise_id, question_ref, content (dict),
        and optionally solution (dict)
        
        Args:
            questions: List of question dicts
            
        Returns:
            List of QuestionIds
        """
        question_ids = []
        for q in questions:
            q_id = self.upsert_question(
                exercise_id=q['exercise_id'],
                question_ref=q['question_ref'],
                content=q['content'],
                solution=q.get('solution')
            )
            question_ids.append(q_id)
        
        logger.info(f"Batch upserted {len(question_ids)} questions")
        return question_ids
    
    # =========================================================================
    # Update Operations (for Stage 2 solution ingestion)
    # =========================================================================
    
    def update_question_solution(
        self,
        question_id: int,
        solution: Dict[str, Any]
    ) -> bool:
        """
        Update solution for an existing question.
        
        Args:
            question_id: QuestionId to update
            solution: Solution dict with steps, final_answer, etc.
            
        Returns:
            True if updated, False if question not found
        """
        import json as json_module
        
        conn = self.connect()
        with conn.cursor() as cur:
            solution_json = json_module.dumps(solution) if solution else None
            
            cur.execute(
                """
                UPDATE questiondata
                SET solution = %s
                WHERE questionid = %s
                """,
                (solution_json, question_id)
            )
            conn.commit()
            
            if cur.rowcount > 0:
                logger.debug(f"Updated solution for QuestionId={question_id}")
                return True
            else:
                logger.warning(f"Question not found: QuestionId={question_id}")
                return False
    
    def update_question_content(
        self,
        question_id: int,
        content_updates: Dict[str, Any]
    ) -> bool:
        """
        Merge updates into existing Content JSONB for a question.
        
        Uses PostgreSQL JSONB concatenation to merge updates.
        
        Args:
            question_id: QuestionId to update
            content_updates: Dict of fields to merge into Content
            
        Returns:
            True if updated, False if question not found
        """
        import json as json_module
        
        conn = self.connect()
        with conn.cursor() as cur:
            updates_json = json_module.dumps(content_updates)
            
            cur.execute(
                """
                UPDATE questiondata
                SET content = content || %s::jsonb
                WHERE questionid = %s
                """,
                (updates_json, question_id)
            )
            conn.commit()
            
            if cur.rowcount > 0:
                logger.debug(f"Updated content for QuestionId={question_id}")
                return True
            else:
                logger.warning(f"Question not found: QuestionId={question_id}")
                return False

    # =========================================================================
    # Cleanup Operations
    # =========================================================================
    
    def cleanup_chapter_data(
        self,
        chapter_id: int,
        dry_run: bool = False
    ) -> Dict[str, int]:
        """
        Delete all ExerciseData and QuestionData for a chapter.
        
        Does NOT touch ChapterData table.
        
        Args:
            chapter_id: ChapterId to clean up
            dry_run: If True, only return counts without deleting
            
        Returns:
            Dict with 'exercises_deleted' and 'questions_deleted' counts
        """
        conn = self.connect()
        
        with conn.cursor() as cur:
            # First, get exercise IDs for this chapter
            cur.execute(
                "SELECT exerciseid FROM exercisedata WHERE chapterid = %s",
                (chapter_id,)
            )
            exercise_ids = [row[0] for row in cur.fetchall()]
            
            if not exercise_ids:
                logger.info(f"No exercises found for ChapterId={chapter_id}")
                return {'exercises_deleted': 0, 'questions_deleted': 0}
            
            # Count questions that will be deleted
            cur.execute(
                "SELECT COUNT(*) FROM questiondata WHERE exerciseid = ANY(%s)",
                (exercise_ids,)
            )
            questions_count = cur.fetchone()[0]
            exercises_count = len(exercise_ids)
            
            if dry_run:
                logger.info(f"[DRY RUN] Would delete: {questions_count} questions, {exercises_count} exercises for ChapterId={chapter_id}")
                return {'exercises_deleted': exercises_count, 'questions_deleted': questions_count}
            
            # Delete questions first (FK constraint)
            cur.execute(
                "DELETE FROM questiondata WHERE exerciseid = ANY(%s)",
                (exercise_ids,)
            )
            questions_deleted = cur.rowcount
            
            # Then delete exercises
            cur.execute(
                "DELETE FROM exercisedata WHERE chapterid = %s",
                (chapter_id,)
            )
            exercises_deleted = cur.rowcount
            
            conn.commit()
            
            logger.info(f"Cleanup complete for ChapterId={chapter_id}: "
                       f"deleted {questions_deleted} questions, {exercises_deleted} exercises")
            
            return {'exercises_deleted': exercises_deleted, 'questions_deleted': questions_deleted}
    
    def get_chapter_info(self, chapter_id: int) -> Optional[Dict[str, Any]]:
        """
        Get chapter information by ChapterId.
        
        Args:
            chapter_id: ChapterId to look up
            
        Returns:
            Dict with chapter info or None if not found
        """
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chapterid, class, subject, chapternumber, chaptertitle 
                FROM chapterdata WHERE chapterid = %s
                """,
                (chapter_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    'chapter_id': row[0],
                    'class': row[1],
                    'subject': row[2],
                    'chapter_number': row[3],
                    'chapter_name': row[4]
                }
            return None


# =============================================================================
# Factory Functions
# =============================================================================

def get_db_client(use_managed_identity: bool = True) -> DatabaseClient:
    """
    Factory function to create database client.
    
    Checks for connection string first, then falls back to managed identity.
    
    Args:
        use_managed_identity: Whether to use managed identity if no connection string
        
    Returns:
        Configured DatabaseClient
    """
    connection_string = os.environ.get("AZURE_PG_CONNECTION_STRING")
    
    if connection_string:
        logger.info("Using connection string from environment")
        return DatabaseClient(connection_string=connection_string, use_managed_identity=False)
    
    elif use_managed_identity:
        logger.info("Using Azure Managed Identity")
        return DatabaseClient(use_managed_identity=True)
    
    else:
        # Try to build from individual env vars
        host = os.environ.get("AZURE_PG_HOST")
        database = os.environ.get("AZURE_PG_DATABASE")
        user = os.environ.get("AZURE_PG_USER")
        password = os.environ.get("AZURE_PG_PASSWORD")
        
        if not all([host, user, password]):
            raise ValueError(
                "Database connection not configured. Set AZURE_PG_CONNECTION_STRING "
                "or individual AZURE_PG_* environment variables."
            )
        
        return DatabaseClient(
            host=host,
            database=database,
            user=user,
            password=password,
            use_managed_identity=False
        )


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test database connectivity")
    parser.add_argument("--connection-string", help="PostgreSQL connection string")
    parser.add_argument("--test-query", action="store_true", help="Run test query")
    args = parser.parse_args()
    
    client = DatabaseClient(
        connection_string=args.connection_string,
        use_managed_identity=not args.connection_string
    )
    
    try:
        with client:
            if args.test_query:
                conn = client.connect()
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM chapterdata")
                    count = cur.fetchone()[0]
                    print(f"chapterdata has {count} records")
            else:
                print("Connection successful!")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
