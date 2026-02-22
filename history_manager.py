"""
History Manager Module
Handles saving, loading, listing, and managing question generation run history.
Supports user-specific history with file locking for concurrent access.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging
from file_lock import FileLock
from auth import sanitize_username

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manages conversation history for question generation runs (user-specific)."""
    
    def __init__(self, username: str, history_dir: str = "history", max_runs: int = 10):
        """
        Initialize the history manager for a specific user.
        
        Args:
            username: Username for this history manager
            history_dir: Base directory to store history files
            max_runs: Maximum number of runs to keep per user (default: 10)
        """
        self.username = username
        self.sanitized_username = sanitize_username(username)
        self.base_history_dir = Path(history_dir)
        self.history_dir = self.base_history_dir / self.sanitized_username
        self.max_runs = max_runs
        
        # Create both base and user-specific directories
        self.base_history_dir.mkdir(exist_ok=True)
        self.history_dir.mkdir(exist_ok=True)
        
    def _generate_run_id(self) -> str:
        """Generate a unique run ID based on timestamp."""
        return datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
    
    def save_run(
        self,
        session_data: Dict[str, Any],
        output_data: Any,
        files_data: Dict[str, Any],
        run_id: Optional[str] = None
    ) -> str:
        """
        Save a complete generation run with all context (with file locking).
        
        Args:
            session_data: Session configuration and metadata
            output_data: Generated questions output
            files_data: Dictionary of file paths and metadata
            
        Returns:
            run_id: Unique identifier for this run
        """
        try:
            run_id = run_id or self._generate_run_id()
            run_dir = self.history_dir / run_id
            run_dir.mkdir(exist_ok=True)
            
            # Create files subdirectory
            files_dir = run_dir / "files"
            files_dir.mkdir(exist_ok=True)
            
            # Prepare metadata
            metadata = {
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "username": self.username,
                "metadata": {
                    "curriculum": session_data.get("curriculum", ""),
                    "grade": session_data.get("grade", ""),
                    "subject": session_data.get("subject", ""),
                    "chapter": session_data.get("chapter", ""),
                    "old_concept": session_data.get("old_concept", ""),
                    "new_concept": session_data.get("new_concept", ""),
                    "additional_notes": session_data.get("additional_notes", ""),
                    "total_questions": sum(
                        config.get("count", 0) 
                        for config in session_data.get("question_types_config", {}).values()
                    ),
                    "question_types": list(session_data.get("question_types_config", {}).keys())
                },
                "session_config": {
                    "question_types_config": session_data.get("question_types_config", {}),
                    "core_skill_enabled": session_data.get("core_skill_enabled", False)
                },
                "files": files_data
            }
            
            # Use file locking for safe concurrent writes
            metadata_file = run_dir / "metadata.json"
            with FileLock(metadata_file, timeout=5.0):
                # Save metadata
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            # Save output (no locking needed - unique file)
            with open(run_dir / "output.json", "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            # Create thumbnail (preview data for quick display)
            thumbnail = {
                "run_id": run_id,
                "timestamp": metadata["timestamp"],
                "chapter": metadata["metadata"]["chapter"],
                "total_questions": metadata["metadata"]["total_questions"],
                "question_types": metadata["metadata"]["question_types"]
            }
            thumbnail_file = run_dir / "thumbnail.json"
            with FileLock(thumbnail_file, timeout=5.0):
                with open(thumbnail_file, "w", encoding="utf-8") as f:
                    json.dump(thumbnail, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved run {run_id} for user {self.username} to {run_dir}")
            
            # Cleanup old runs
            self.cleanup_old_runs()
            
            return run_id
            
        except Exception as e:
            logger.error(f"Error saving run for user {self.username}: {e}")
            raise
    
    def load_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a complete run by ID.
        
        Args:
            run_id: Unique identifier for the run
            
        Returns:
            Dictionary containing metadata, session_config, and output
        """
        try:
            run_dir = self.history_dir / run_id
            
            if not run_dir.exists():
                logger.warning(f"Run {run_id} not found")
                return None
            
            # Load metadata
            with open(run_dir / "metadata.json", "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            # Load output
            with open(run_dir / "output.json", "r", encoding="utf-8") as f:
                output = json.load(f)
            
            return {
                "metadata": metadata,
                "output": output,
                "run_dir": str(run_dir)
            }
            
        except Exception as e:
            logger.error(f"Error loading run {run_id}: {e}")
            return None
    
    def list_runs(self) -> List[Dict[str, Any]]:
        """
        Get list of all saved runs with metadata.
        
        Returns:
            List of run summaries sorted by timestamp (newest first)
        """
        runs = []
        
        try:
            for run_dir in self.history_dir.iterdir():
                if run_dir.is_dir():
                    thumbnail_file = run_dir / "thumbnail.json"
                    
                    if thumbnail_file.exists():
                        try:
                            with open(thumbnail_file, "r", encoding="utf-8") as f:
                                thumbnail = json.load(f)
                                runs.append(thumbnail)
                        except Exception as e:
                            logger.warning(f"Error loading thumbnail for {run_dir.name}: {e}")
            
            # Sort by timestamp (newest first)
            runs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
        except Exception as e:
            logger.error(f"Error listing runs: {e}")
        
        return runs
    
    def delete_run(self, run_id: str) -> bool:
        """
        Delete a run and its associated files.
        
        Args:
            run_id: Unique identifier for the run
            
        Returns:
            True if successful, False otherwise
        """
        try:
            run_dir = self.history_dir / run_id
            
            if run_dir.exists():
                # Delete the entire run directory
                # Note: shutil.rmtree is atomic enough for our purposes
                # File locking here can cause issues since we're deleting the lock file itself
                shutil.rmtree(run_dir)
                logger.info(f"Deleted run {run_id} for user {self.username}")
                return True
            else:
                logger.warning(f"Run {run_id} not found for user {self.username}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting run {run_id} for user {self.username}: {e}")
            return False
    
    def get_run_summary(self, run_id: str) -> str:
        """
        Get a displayable summary for a run.
        
        Args:
            run_id: Unique identifier for the run
            
        Returns:
            Formatted summary string
        """
        try:
            run_dir = self.history_dir / run_id
            thumbnail_file = run_dir / "thumbnail.json"
            
            if thumbnail_file.exists():
                with open(thumbnail_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                timestamp = datetime.fromisoformat(data.get("timestamp", ""))
                formatted_time = timestamp.strftime("%b %d, %Y %I:%M %p")
                
                chapter = data.get("chapter", "Unknown")
                total_q = data.get("total_questions", 0)
                types = ", ".join(data.get("question_types", []))
                
                return f"{formatted_time} | {chapter} | {total_q} questions ({types})"
            
            return f"Run {run_id}"
            
        except Exception as e:
            logger.error(f"Error getting summary for {run_id}: {e}")
            return f"Run {run_id}"
    
    def cleanup_old_runs(self, keep_last_n: Optional[int] = None) -> None:
        """
        Remove oldest runs to maintain history size limit.
        
        Args:
            keep_last_n: Number of runs to keep (uses self.max_runs if not specified)
        """
        try:
            max_runs = keep_last_n if keep_last_n is not None else self.max_runs
            runs = self.list_runs()
            
            if len(runs) > max_runs:
                # Delete oldest runs
                runs_to_delete = runs[max_runs:]
                
                for run in runs_to_delete:
                    run_id = run.get("run_id")
                    if run_id:
                        self.delete_run(run_id)
                        logger.info(f"Cleaned up old run: {run_id}")
                        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def get_files_dir(self, run_id: str) -> Path:
        """
        Get the files directory for a specific run.
        
        Args:
            run_id: Unique identifier for the run
            
        Returns:
            Path to the files directory
        """
        return self.history_dir / run_id / "files"
