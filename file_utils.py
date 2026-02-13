"""
File Utilities Module
Helper functions for file serialization and deserialization in history management.
"""

import io
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


def save_uploaded_file(file_obj: Any, dest_path: Path) -> bool:
    """
    Save an uploaded file object to disk.
    
    Args:
        file_obj: Streamlit UploadedFile or PastedFile object
        dest_path: Destination path to save the file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Read file content
        if hasattr(file_obj, 'getvalue'):
            # BytesIO-like object (PastedFile)
            content = file_obj.getvalue()
        elif hasattr(file_obj, 'read'):
            # File-like object
            file_obj.seek(0)  # Reset to beginning
            content = file_obj.read()
        else:
            logger.warning(f"Unknown file object type: {type(file_obj)}")
            return False
        
        # Write to disk
        with open(dest_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"Saved file to {dest_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving file to {dest_path}: {e}")
        return False


def create_file_object(file_path: Path, name: Optional[str] = None) -> Optional[io.BytesIO]:
    """
    Create a file-like object from a saved file.
    
    Args:
        file_path: Path to the saved file
        name: Optional name for the file object
        
    Returns:
        BytesIO object compatible with Streamlit file uploads
    """
    try:
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return None
        
        # Read file content
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # Create BytesIO object
        file_obj = io.BytesIO(content)
        
        # Add attributes to mimic UploadedFile
        file_obj.name = name or file_path.name
        file_obj.size = len(content)
        
        # Determine file type
        suffix = file_path.suffix.lower()
        if suffix == '.pdf':
            file_obj.type = 'application/pdf'
        elif suffix in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            file_obj.type = f'image/{suffix[1:]}'
        else:
            file_obj.type = 'application/octet-stream'
        
        return file_obj
        
    except Exception as e:
        logger.error(f"Error creating file object from {file_path}: {e}")
        return None


def extract_all_files_from_config(
    question_types_config: Dict[str, Any],
    universal_pdf: Any
) -> Dict[str, Any]:
    """
    Extract all file references from question configuration.
    
    Args:
        question_types_config: Question types configuration dictionary
        universal_pdf: Universal PDF file object
        
    Returns:
        Dictionary mapping file IDs to file objects
    """
    files = {}
    
    try:
        # Add universal PDF if exists
        if universal_pdf:
            files['universal_pdf'] = {
                'file_obj': universal_pdf,
                'filename': getattr(universal_pdf, 'name', 'universal_file.pdf')
            }
        
        # Extract per-question files
        for qtype, config in question_types_config.items():
            questions = config.get('questions', [])
            
            for i, q in enumerate(questions):
                # Check for new concept PDF (per-question)
                new_concept_pdf = q.get('new_concept_pdf')
                if new_concept_pdf:
                    file_id = f"{qtype}_q{i}_new_concept"
                    files[file_id] = {
                        'file_obj': new_concept_pdf,
                        'filename': getattr(new_concept_pdf, 'name', f'{qtype}_q{i}_concept.pdf')
                    }
                
                # Check for additional notes PDF
                additional_notes_pdf = q.get('additional_notes_pdf')
                if additional_notes_pdf:
                    file_id = f"{qtype}_q{i}_additional"
                    files[file_id] = {
                        'file_obj': additional_notes_pdf,
                        'filename': getattr(additional_notes_pdf, 'name', f'{qtype}_q{i}_notes.pdf')
                    }
        
        logger.info(f"Extracted {len(files)} files from configuration")
        
    except Exception as e:
        logger.error(f"Error extracting files from config: {e}")
    
    return files


def save_all_files(files_dict: Dict[str, Any], files_dir: Path) -> Dict[str, str]:
    """
    Save all files to the history directory.
    
    Args:
        files_dict: Dictionary of file IDs to file info
        files_dir: Directory to save files
        
    Returns:
        Dictionary mapping file IDs to saved file paths (relative to files_dir)
    """
    saved_files = {}
    
    try:
        files_dir.mkdir(parents=True, exist_ok=True)
        
        for file_id, file_info in files_dict.items():
            file_obj = file_info['file_obj']
            filename = file_info['filename']
            
            # Create safe filename
            safe_filename = f"{file_id}_{filename}"
            dest_path = files_dir / safe_filename
            
            if save_uploaded_file(file_obj, dest_path):
                # Store relative path
                saved_files[file_id] = safe_filename
        
        logger.info(f"Saved {len(saved_files)} files to {files_dir}")
        
    except Exception as e:
        logger.error(f"Error saving files: {e}")
    
    return saved_files


def restore_files_from_map(
    files_map: Dict[str, str],
    files_dir: Path
) -> Dict[str, Any]:
    """
    Restore file objects from saved files.
    
    Args:
        files_map: Dictionary mapping file IDs to filenames
        files_dir: Directory containing saved files
        
    Returns:
        Dictionary mapping file IDs to restored file objects
    """
    restored_files = {}
    
    try:
        for file_id, filename in files_map.items():
            file_path = files_dir / filename
            
            if file_path.exists():
                file_obj = create_file_object(file_path, name=filename)
                if file_obj:
                    restored_files[file_id] = file_obj
            else:
                logger.warning(f"File not found during restoration: {file_path}")
        
        logger.info(f"Restored {len(restored_files)} files from {files_dir}")
        
    except Exception as e:
        logger.error(f"Error restoring files: {e}")
    
    return restored_files


def restore_files_to_config(
    question_types_config: Dict[str, Any],
    restored_files: Dict[str, Any]
) -> None:
    """
    Restore files into question configuration.
    
    Args:
        question_types_config: Question types configuration dictionary (modified in-place)
        restored_files: Dictionary of restored file objects
    """
    try:
        # Restore per-question files
        for qtype, config in question_types_config.items():
            questions = config.get('questions', [])
            
            for i, q in enumerate(questions):
                # Restore new concept PDF
                file_id = f"{qtype}_q{i}_new_concept"
                if file_id in restored_files:
                    q['new_concept_pdf'] = restored_files[file_id]
                
                # Restore additional notes PDF
                file_id = f"{qtype}_q{i}_additional"
                if file_id in restored_files:
                    q['additional_notes_pdf'] = restored_files[file_id]
        
        logger.info("Restored files to configuration")
        
    except Exception as e:
        logger.error(f"Error restoring files to config: {e}")
