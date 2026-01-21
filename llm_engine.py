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
    
    # Prompt saving logic removed as per user request
    
    # Prepare files list if PDF is provided
    files_to_upload = [pdf_file] if pdf_file else None
    
    # Call Gemini 2.5 Pro with higher thinking budget for better quality
    logger.info(f"Generating {num_duplicates} duplicate(s) for question {question_code}")
    
    result = await run_gemini_async(
        prompt=formatted_prompt,
        api_key=api_key,
        files=files_to_upload,
        thinking_budget=8000,  # Higher budget for quality duplicates
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
                "output_tokens": result.get('output_tokens', 0)
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
    thinking_budget: int = 5000,
    file_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Async wrapper for run_gemini.
    """
    return await asyncio.to_thread(run_gemini, prompt, api_key, files, thinking_budget, file_metadata)
