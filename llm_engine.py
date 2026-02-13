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


import threading

# Global lock for file reading to prevent race conditions during parallel batches
file_read_lock = threading.Lock()

def save_prompt(prompt: str, prompt_type: str, identifier: str):
    """
    Save the final prompt to a file in prompt_logs directory.
    """
    try:
        log_dir = Path("prompt_logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{prompt_type}_{identifier.replace(' ', '_')}.txt"
        file_path = log_dir / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        
        logger.info(f"Saved {prompt_type} prompt to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save prompt: {e}")

def save_response(response_text: str, response_type: str, identifier: str):
    """
    Save the raw LLM response to a file in response_logs directory.
    """
    try:
        log_dir = Path("response_logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{response_type}_{identifier.replace(' ', '_')}.txt"
        file_path = log_dir / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(response_text)
        
        logger.info(f"Saved {response_type} response to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save response: {e}")

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
    
    client = genai.Client(api_key=api_key, http_options={'timeout': 600000})
    uploaded_files = []
    
    for file in files:
        tmp_path = None
        try:
            # Thread-safe file reading
            # We must lock because multiple parallel batches might try to seek/read 
            # the SAME shared file object (universal_pdf) simultaneously.
            with file_read_lock:
                # Reset file pointer to beginning
                file.seek(0)
                
                # Get file extension from filename
                filename = getattr(file, 'name', 'uploaded_file')
                file_ext = Path(filename).suffix if '.' in filename else '.pdf'
                
                # Create a temporary file (File API needs file path)
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(file.read())
                    tmp_path = tmp_file.name
            
            # Upload to Gemini File API (OUTSIDE the lock for parallelism)
            logger.info(f"Uploading file to Gemini File API: {filename}")
            
            uploaded = client.files.upload(file=tmp_path)
            uploaded_files.append(uploaded)
            
            logger.info(f"Successfully uploaded: {filename} (URI: {uploaded.name})")
            
        except Exception as e:
            logger.error(f"Failed to upload file {getattr(file, 'name', 'unknown')}: {e}")
            # Continue with other files even if one fails
            
        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as cleanup_error:
                   logger.warning(f"Failed to cleanup temp file {tmp_path}: {cleanup_error}")
    
    return uploaded_files


def run_gemini(
    prompt: str,
    api_key: str,
    files: Optional[List] = None,
    thinking_level: str = "high",
    file_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run Gemini model with optional PDF/image files using File API.
    
    Args:
        prompt: The text prompt to send
        api_key: Gemini API key
        files: List of file-like objects to upload (PDFs or images)
        thinking_level: Level of reasoning for Gemini 3 models (e.g., "medium")
        file_metadata: Metadata about files (source_type, filenames)
        
    Returns:
        Dictionary with text, error, elapsed time, and token counts
    """
    out = {"text": "", "error": None, "elapsed": 0}
    start = time.time()
    
    try:
        # Initialize client with extended timeout (10 minutes) to accommodate thinking models
        # Initialize client with extended timeout (10 minutes = 600,000ms if units are ms, or long duration if seconds)
        # The API requires a deadline >= 10s for thinking models.
        client = genai.Client(api_key=api_key, http_options={'timeout': 600000})
        
        # Log execution start with file info
        if file_metadata and files:
            source_type = file_metadata.get('source_type', 'Unknown')
            filenames = file_metadata.get('filenames', [])
            logger.info(f"Starting Gemini | Files: {len(files)} files ({source_type}) | "
                       f"Files: {', '.join(filenames)} | Model: gemini-3-flash-preview")
        else:
            logger.info(f"Starting Gemini | Files: None | Model: gemini-3-flash-preview")
        
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
                thinking_level=thinking_level
            )
        )
        
        # Using stream=True to be consistent with previous implementation
        stream = client.models.generate_content_stream(
            model="gemini-3-flash-preview",
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
            # Handle possible pluralization variations in different SDK versions
            out["thought_tokens"] = getattr(usage_metadata, 'thought_token_count', 
                                   getattr(usage_metadata, 'thoughts_token_count', 0))
            out["total_tokens"] = getattr(usage_metadata, 'total_token_count', 0)
            
            # User wants to treat thinking tokens as output tokens
            # Total Billed Output Tokens = candidates + thought
            out["billed_output_tokens"] = out["output_tokens"] + out["thought_tokens"]
            
            logger.info(f"Gemini completed | Chunks: {chunk_count} | Tokens: {out['total_tokens']} "
                       f"(in: {out['input_tokens']}, out: {out['output_tokens']}, thought: {out['thought_tokens']}) | "
                       f"Time: {time.time() - start:.2f}s")
        else:
            out["input_tokens"] = 0
            out["output_tokens"] = 0
            out["thought_tokens"] = 0
            out["billed_output_tokens"] = 0
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


async def duplicate_questions_async(
    original_question_markdown: str,
    question_code: str,
    num_duplicates: int,
    api_key: str,
    additional_notes: str = "",
    pdf_file: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Generate duplicate versions of a question with different numbers and scenarios.
    
    Args:
        original_question_markdown: The complete question in markdown format (as string)
        question_code: The question identifier (e.g., "q1", "q2")
        num_duplicates: Number of duplicate versions to create
        api_key: Gemini API key
        additional_notes: Optional additional instructions for duplication
        pdf_file: Optional file object (PDF/Image) for context
        
    Returns:
        Dictionary with 'duplicates' (list of duplicate question objects) and metadata
    """
    import yaml
    from pathlib import Path
    
    # Load the duplication prompt template from prompts.yaml
    prompts_path = Path(__file__).parent / "prompts.yaml"
    with open(prompts_path, 'r', encoding='utf-8') as f:
        prompts = yaml.safe_load(f)
    
    prompt_template = prompts.get('duplicate_question', '')
    
    if not prompt_template:
        return {
            "error": "Duplication prompt not found in prompts.yaml",
            "duplicates": []
        }
    
    # Replace template parameters with actual values
    formatted_prompt = prompt_template.replace("{{QUESTION_CODE}}", question_code)
    formatted_prompt = formatted_prompt.replace("{{NUM_DUPLICATES}}", str(num_duplicates))
    formatted_prompt = formatted_prompt.replace("{{ORIGINAL_QUESTION}}", original_question_markdown)
    formatted_prompt = formatted_prompt.replace("{{ADDITIONAL_NOTES}}", additional_notes)
    
    # Save prompt for debugging
    # save_prompt(formatted_prompt, "duplication", question_code)
    
    # Prepare files list if PDF is provided
    files_to_upload = [pdf_file] if pdf_file else None
    
    # Call Gemini 2.5 Pro with higher thinking budget for better quality
    logger.info(f"Generating {num_duplicates} duplicate(s) for question {question_code}")
    
    result = await run_gemini_async(
        prompt=formatted_prompt,
        api_key=api_key,
        files=files_to_upload,
        thinking_level="high",
        file_metadata={'source_type': 'duplicate_context', 'filenames': [getattr(pdf_file, 'name', 'file')]} if pdf_file else None
    )
    
    if result.get('error'):
        logger.error(f"Error generating duplicates: {result['error']}")
        return {
            "error": result['error'],
            "duplicates": [],
            "elapsed": result.get('elapsed', 0)
        }
    
    # Parse the JSON response
    import json
    import re
    
    response_text = result.get('text', '')
    
    # Try to extract JSON array from response
    try:
        # Look for JSON array pattern
        json_match = re.search(r'\[\s*\{.*?\}\s*\]', response_text, re.DOTALL)
        if json_match:
            duplicates_array = json.loads(json_match.group(0))
            logger.info(f"Successfully parsed {len(duplicates_array)} duplicates")
            return {
                "duplicates": duplicates_array,
                "elapsed": result.get('elapsed', 0),
                "input_tokens": result.get('input_tokens', 0),
                "output_tokens": result.get('output_tokens', 0),
                "thought_tokens": result.get('thought_tokens', 0),
                "billed_output_tokens": result.get('billed_output_tokens', 0)
            }
        else:
            logger.warning("No JSON array found in response")
            return {
                "error": "Could not parse JSON response",
                "raw_response": response_text[:500],  # First 500 chars for debugging
                "duplicates": [],
                "elapsed": result.get('elapsed', 0)
            }
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return {
            "error": f"JSON parsing failed: {str(e)}",
            "raw_response": response_text[:500],
            "duplicates": [],
            "elapsed": result.get('elapsed', 0)
        }


async def run_gemini_async(
    prompt: str,
    api_key: str,
    files: Optional[List] = None,
    thinking_level: str = "high",
    file_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Async wrapper for run_gemini.
    """
    return await asyncio.to_thread(run_gemini, prompt, api_key, files, thinking_level, file_metadata)
