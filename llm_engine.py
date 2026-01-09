"""
LLM Engine for Gemini API Integration
Handles synchronous and asynchronous calls to Gemini API with File API support.
"""

import time
import asyncio
import logging
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def upload_files_to_gemini(files: List, api_key: str) -> List:
    """
    Upload multiple PDF and image files to Gemini File API and return file objects.
    
    Args:
        files: List of file-like objects (from Streamlit file_uploader)
        api_key: Gemini API key
        
    Returns:
        List of uploaded file objects from Gemini
    """
    if not files:
        return []
    
    client = genai.Client(api_key=api_key)
    uploaded_files = []
    
    for file in files:
        try:
            # Reset file pointer to beginning
            file.seek(0)
            
            # Get file extension from filename
            filename = getattr(file, 'name', 'uploaded_file')
            file_ext = Path(filename).suffix if '.' in filename else '.pdf'
            
            # Create a temporary file (File API needs file path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                tmp_file.write(file.read())
                tmp_path = tmp_file.name
            
            # Upload to Gemini File API
            logger.info(f"Uploading file to Gemini File API: {filename}")
            
            uploaded = client.files.upload(file=tmp_path)
            uploaded_files.append(uploaded)
            
            logger.info(f"Successfully uploaded: {filename} (URI: {uploaded.name})")
            
            # Clean up temp file
            os.remove(tmp_path)
            
        except Exception as e:
            logger.error(f"Failed to upload file {getattr(file, 'name', 'unknown')}: {e}")
            # Continue with other files even if one fails
    
    return uploaded_files


def run_gemini(
    prompt: str,
    api_key: str,
    files: Optional[List] = None,
    thinking_budget: int = 10000,
    file_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run Gemini model with optional PDF/image files using File API.
    
    Args:
        prompt: The text prompt to send
        api_key: Gemini API key
        files: List of file-like objects to upload (PDFs or images)
        thinking_budget: Thinking budget tokens
        file_metadata: Metadata about files (source_type, filenames)
        
    Returns:
        Dictionary with text, error, elapsed time, and token counts
    """
    out = {"text": "", "error": None, "elapsed": 0}
    start = time.time()
    
    try:
        client = genai.Client(api_key=api_key)
        
        # Log execution start with file info
        if file_metadata and files:
            source_type = file_metadata.get('source_type', 'Unknown')
            filenames = file_metadata.get('filenames', [])
            logger.info(f"Starting Gemini | Files: {len(files)} files ({source_type}) | "
                       f"Files: {', '.join(filenames)} | Thinking budget: {thinking_budget}")
        else:
            logger.info(f"Starting Gemini | Files: None | Thinking budget: {thinking_budget}")
        
        # Build contents list
        contents = []
        
        # Upload files if provided
        if files:
            uploaded_files = upload_files_to_gemini(files, api_key)
            contents.extend(uploaded_files)
            
            if file_metadata:
                source_type = file_metadata.get('source_type', 'Unknown')
                filenames = file_metadata.get('filenames', [])
                logger.info(f"Added {len(uploaded_files)} file(s) to Gemini request | "
                           f"Source: {source_type} | Files: {', '.join(filenames)}")
        
        contents.append(prompt)
        
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                include_thoughts=False,
                thinking_budget=thinking_budget
            )
        )
        
        # Using stream=True to be consistent with previous implementation
        stream = client.models.generate_content_stream(
            model="gemini-2.5-pro",
            contents=contents,
            config=config
        )

        agg = ""
        chunk_count = 0
        usage_metadata = None
        
        for chunk in stream:
            txt = getattr(chunk, "text", "") or ""
            if txt:
                agg += txt
                chunk_count += 1
            
            # Capture usage metadata from the last chunk
            if hasattr(chunk, 'usage_metadata'):
                usage_metadata = chunk.usage_metadata

        out["text"] = agg
        
        # Extract token usage for cost calculation
        if usage_metadata:
            out["input_tokens"] = getattr(usage_metadata, 'prompt_token_count', 0)
            out["output_tokens"] = getattr(usage_metadata, 'candidates_token_count', 0)
            out["total_tokens"] = getattr(usage_metadata, 'total_token_count', 0)
            logger.info(f"Gemini completed | Chunks: {chunk_count} | Tokens: {out['total_tokens']} (in: {out['input_tokens']}, out: {out['output_tokens']}) | Time: {time.time() - start:.2f}s")
        else:
            out["input_tokens"] = 0
            out["output_tokens"] = 0
            out["total_tokens"] = 0
            logger.info(f"Gemini completed | Chunks: {chunk_count} | Output length: {len(agg)} chars | Time: {time.time() - start:.2f}s")
        
    except Exception as e:
        logger.error(f"Gemini execution failed: {e}")
        out["error"] = str(e)
        out["text"] = f"[Gemini Error] {e}"
        
    finally:
        out["elapsed"] = time.time() - start
        logger.debug(f"Gemini execution finished | Elapsed: {out['elapsed']:.2f}s")
    
    return out


async def run_gemini_async(
    prompt: str,
    api_key: str,
    files: Optional[List] = None,
    thinking_budget: int = 5000,
    file_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Async wrapper for run_gemini.
    """
    return await asyncio.to_thread(run_gemini, prompt, api_key, files, thinking_budget, file_metadata)
