"""
File Locking Utility
Cross-platform file locking for safe concurrent access.
"""

import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Platform-specific imports
try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False
    try:
        import fcntl
    except ImportError:
        fcntl = None


class FileLock:
    """
    Context manager for file locking.
    Supports both Windows and Unix systems.
    """
    
    def __init__(self, file_path: Path, timeout: float = 5.0, retry_interval: float = 0.1):
        """
        Initialize file lock.
        
        Args:
            file_path: Path to file to lock
            timeout: Maximum time to wait for lock (seconds)
            retry_interval: Time between retry attempts (seconds)
        """
        self.file_path = Path(file_path)
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.lock_file = None
        self.acquired = False
        
    def __enter__(self):
        """Acquire the lock."""
        # Create lock file path (same name with .lock extension)
        lock_path = self.file_path.parent / f"{self.file_path.name}.lock"
        
        start_time = time.time()
        
        while True:
            try:
                # Try to create/open lock file
                self.lock_file = open(lock_path, 'w')
                
                # Platform-specific locking
                if WINDOWS:
                    # Windows file locking
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:
                    # Unix file locking
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    # No locking available - log warning but continue
                    logger.warning("File locking not available on this platform")
                
                self.acquired = True
                logger.debug(f"Acquired lock on {lock_path}")
                return self
                
            except (IOError, OSError) as e:
                # Lock acquisition failed
                if time.time() - start_time >= self.timeout:
                    logger.error(f"Failed to acquire lock on {lock_path} after {self.timeout}s")
                    # Close file if it was opened
                    if self.lock_file:
                        self.lock_file.close()
                        self.lock_file = None
                    raise TimeoutError(f"Could not acquire lock on {lock_path}") from e
                
                # Wait and retry
                time.sleep(self.retry_interval)
                
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the lock."""
        if self.lock_file:
            try:
                # Platform-specific unlocking
                if WINDOWS and self.acquired:
                    try:
                        msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass  # Already unlocked or error
                elif fcntl is not None and self.acquired:
                    try:
                        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass  # Already unlocked or error
                
                self.lock_file.close()
                
                # Try to remove lock file
                lock_path = self.file_path.parent / f"{self.file_path.name}.lock"
                try:
                    lock_path.unlink()
                    logger.debug(f"Released lock on {lock_path}")
                except Exception:
                    pass  # Lock file might already be deleted
                    
            except Exception as e:
                logger.warning(f"Error releasing lock: {e}")
            finally:
                self.lock_file = None
                self.acquired = False
        
        return False
