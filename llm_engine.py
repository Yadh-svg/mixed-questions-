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
    Save the final prompt to a file in prompt_logs directory. (DISABLED)
    """
    return

def save_response(response_text: str, response_type: str, identifier: str):
    """
    Save the raw LLM response to a file in response_logs directory. (DISABLED)
    """
    return

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
    file_metadata: Optional[Dict[str, Any]] = None,
    model: str = None,
    system_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run Gemini model with optional PDF/image files using File API.
    
    Args:
        prompt: The text prompt to send
        api_key: Gemini API key
        files: List of file-like objects to upload (PDFs or images)
        thinking_level: Level of reasoning for Gemini thinking models (e.g., "high", "medium", "low")
        file_metadata: Metadata about files (source_type, filenames)
        model: Gemini model to use (Required)
        system_prompt: Optional system instruction to set model behavior
        
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
                       f"Files: {', '.join(filenames)} | Model: {model}")
        else:
            logger.info(f"Starting Gemini | Files: None | Model: {model}")
        
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
        
        # Build generation config
        # Some models don't support thinking mode (e.g., gemini-2.5-flash-lite-preview-09-2025)
        # We also support system_instruction for better control.
        config_kwargs = {}
        if thinking_level:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=thinking_level
            )
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
            
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        
        # Using stream=True to be consistent with previous implementation
        stream = client.models.generate_content_stream(
            model=model,
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
            params = {
                'input': getattr(usage_metadata, 'prompt_token_count', 0) or 0,
                'candidates': getattr(usage_metadata, 'candidates_token_count', 0) or 0,
                'thought': getattr(usage_metadata, 'thought_token_count', 
                                 getattr(usage_metadata, 'thoughts_token_count', 0)) or 0
            }
            
            out["input_tokens"] = params['input']
            out["thought_tokens"] = params['thought']
            # Standardize: output_tokens includes thought tokens (like OpenAI)
            out["output_tokens"] = params['candidates'] + params['thought']
            out["total_tokens"] = getattr(usage_metadata, 'total_token_count', 0) or 0
            
            # For backward compatibility or explicit billed tracking
            out["billed_output_tokens"] = out["output_tokens"]
            
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
    pdf_file: Optional[Any] = None,
    model: str = None,
    thinking_level: Optional[str] = None
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
        model: Gemini model to use
        thinking_level: Optional thinking level (high, medium, low, or None)
        
    Returns:
        Dictionary with 'duplicates' (list of duplicate question objects) and metadata
    """
    import yaml
    from pathlib import Path
    
    # Load the duplication prompt template from pipeline_prompts.yaml
    prompts_path = Path(__file__).parent / "pipeline_prompts.yaml"
    with open(prompts_path, 'r', encoding='utf-8') as f:
        prompts = yaml.safe_load(f)
    
    prompt_template = prompts.get('duplicate_question', '')
    
    if not prompt_template:
        return {
            "error": "Duplication prompt not found in pipeline_prompts.yaml",
            "duplicates": []
        }
    
    # Ensure model and thinking_level are set if not passed
    config_data = {}
    try:
        config_path = Path(__file__).parent / "pipeline_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
    except Exception:
        pass

    if not model:
        model = config_data.get('duplication', {}).get('model', 'gemini-3-flash-preview')
    
    if thinking_level is None:
        thinking_level = config_data.get('duplication', {}).get('thinking_level', 'high')
    
    # Replace template parameters with actual values
    formatted_prompt = prompt_template.replace("{{QUESTION_CODE}}", question_code)
    formatted_prompt = formatted_prompt.replace("{{NUM_DUPLICATES}}", str(num_duplicates))
    formatted_prompt = formatted_prompt.replace("{{ORIGINAL_QUESTION}}", original_question_markdown)
    formatted_prompt = formatted_prompt.replace("{{ADDITIONAL_NOTES}}", additional_notes)
    
    # Save prompt for debugging
    save_prompt(formatted_prompt, "duplication", question_code)
    
    # Prepare files list if PDF is provided
    files_to_upload = [pdf_file] if pdf_file else None
    
    # Call Gemini
    logger.info(f"Generating {num_duplicates} duplicate(s) for question {question_code} using model: {model}")
    
    result = await run_gemini_async(
        prompt=formatted_prompt,
        api_key=api_key,
        files=files_to_upload,
        thinking_level=thinking_level,
        file_metadata={'source_type': 'duplicate_context', 'filenames': [getattr(pdf_file, 'name', 'file')]} if pdf_file else None,
        model=model
    )
    
    if result.get('error'):
        logger.error(f"Error generating duplicates: {result['error']}")
        return {
            "error": result['error'],
            "duplicates": [],
            "elapsed": result.get('elapsed', 0)
        }
    
    # Parse the delimited markdown response
    import re
    
    response_text = result.get('text', '')
    # Save raw response for debugging
    save_response(response_text, "duplication", question_code)
    
    # Split the response on the ---DUPLICATE_N--- marker
    # The regex looks for ---DUPLICATE_\d+--- anywhere in the text
    blocks = re.split(r'---DUPLICATE_\d+---', response_text)
    
    # Filter out any empty blocks (usually the text before the first marker)
    duplicates_list = [block.strip() for block in blocks if block.strip()]
    
    if duplicates_list:
        logger.info(f"Successfully extracted {len(duplicates_list)} duplicate raw markdown blocks")
        
        # Package into the expected structure: {"question_code": ..., "markdown": ...}
        duplicates_array = [
            {
                "question_code": f"{question_code}-dup-{i+1}",
                "markdown": block
            }
            for i, block in enumerate(duplicates_list)
        ]
        
        return {
            "duplicates": duplicates_array,
            "elapsed": result.get('elapsed', 0),
            "input_tokens": result.get('input_tokens', 0),
            "output_tokens": result.get('output_tokens', 0),
            "thought_tokens": result.get('thought_tokens', 0),
            "billed_output_tokens": result.get('billed_output_tokens', 0)
        }
    else:
        logger.warning(f"Failed to find any delimited duplicates in response")
        return {
            "error": "Could not extract duplicates from response using delimiter",
            "raw_response": response_text[:500],
            "duplicates": [],
            "elapsed": result.get('elapsed', 0)
        }


async def run_gemini_async(
    prompt: str,
    api_key: str,
    files: Optional[List] = None,
    thinking_level: str = "high",
    file_metadata: Optional[Dict[str, Any]] = None,
    model: str = None,
    system_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Async wrapper for run_gemini.
    """
    return await asyncio.to_thread(run_gemini, prompt, api_key, files, thinking_level, file_metadata, model, system_prompt)


def run_openai(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str = "gpt-4.1",
    temperature: float = 1.0,
    reasoning_effort: str = None
) -> Dict[str, Any]:
    """
    Run OpenAI model using the Responses API.

    Uses the OpenAI Responses API (client.responses.create) which supports
    structured reasoning via the `reasoning.effort` parameter.

    Args:
        system_prompt: System-level instructions for the model.
        user_prompt:   User-facing content / data prompt.
        api_key:       OpenAI API key.
        model:         Model name (e.g. 'gpt-4.1').
        temperature:   Sampling temperature.
        reasoning_effort: Reasoning effort level: 'high' | 'medium' | 'low' | None.
                          When set, enables internal chain-of-thought (like thinking mode).

    Returns:
        Dict with keys: text, error, elapsed, input_tokens, output_tokens.
    """
    from openai import OpenAI

    out = {"text": "", "error": None, "elapsed": 0,
           "input_tokens": 0, "output_tokens": 0,
           "thought_tokens": 0, "total_tokens": 0}
    start = time.time()

    try:
        client = OpenAI(api_key=api_key)

        logger.info(f"Starting OpenAI | Model: {model} | Reasoning effort: {reasoning_effort}")

        # Build kwargs
        create_kwargs = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ]
        }
        
        # Only add temperature if it's a model that supports it (most reasoning models don't)
        if temperature and not model.startswith(('gpt-5', 'o1', 'o3')):
            create_kwargs["temperature"] = temperature

        # Add reasoning if effort is specified
        if reasoning_effort:
            create_kwargs["reasoning"] = {"effort": reasoning_effort}

        response = client.responses.create(**create_kwargs)

        # Extract text — Responses API returns output items
        output_text = ""
        output_items = getattr(response, "output", [])
        
        # Fix for 'NoneType' object is not iterable
        if output_items is None:
            output_items = []
            
        for item in output_items:
            # Handle object-based responses correctly
            if hasattr(item, "content") and item.content:
                for block in item.content:
                    if getattr(block, "type", "") == "output_text":
                        output_text += getattr(block, "text", "")
            # Handle direct dictionary structures (like the one provided in JSON)
            elif isinstance(item, dict) and 'content' in item:
                for block in item.get('content', []):
                    if isinstance(block, dict) and block.get('type') == 'output_text':
                        output_text += block.get('text', '')
            # Fallback: direct text attribute
            elif hasattr(item, "text") and item.text:
                output_text += item.text
            # Fallback for choices (in case it behaves like chat completions)
            elif hasattr(item, "message") and hasattr(item.message, "content"):
                output_text += item.message.content or ""

        # Ultimate fallback if output array was empty or logic missed it
        if not output_text and hasattr(response, "choices"):
            output_text = response.choices[0].message.content or ""
            
        out["text"] = output_text

        # Token usage
        usage = getattr(response, "usage", None)
        if usage:
            out["input_tokens"]  = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0
            out["output_tokens"] = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0
            # Reasoning tokens are billed as output
            reasoning_tokens = getattr(usage, "output_tokens_details", getattr(usage, "completion_tokens_details", None))
            if reasoning_tokens:
                out["thought_tokens"] = getattr(reasoning_tokens, "reasoning_tokens", 0) or 0
            out["total_tokens"] = out["input_tokens"] + out["output_tokens"]

        logger.info(
            f"OpenAI completed | Tokens: {out['total_tokens']} "
            f"(in: {out['input_tokens']}, out: {out['output_tokens']}, "
            f"reasoning: {out['thought_tokens']}) | Time: {time.time() - start:.2f}s"
        )

    except Exception as e:
        logger.error(f"OpenAI execution failed: {e}")
        out["error"] = str(e)
        out["text"]  = f"[OpenAI Error] {e}"

    finally:
        out["elapsed"] = time.time() - start

    return out


async def run_openai_async(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str = "gpt-4.1",
    temperature: float = 1.0,
    reasoning_effort: str = None
) -> Dict[str, Any]:
    """
    Async wrapper for run_openai.
    """
    return await asyncio.to_thread(
        run_openai, system_prompt, user_prompt, api_key, model, temperature, reasoning_effort
    )

async def regenerate_question_async(
    math_core_data: Dict[str, Any],
    question_data: Dict[str, Any],
    general_config: Dict[str, Any],
    files: List,
    previous_question_markdown: str,
    regeneration_reason: str,
    api_key: str,
    model: str = None,
    question_code: str = "regeneration"
) -> Dict[str, Any]:
    """
    Asynchronously regenerates a single question by using a specific regeneration
    prompt format and bypasses standard generation, then immediately validates the output.
    """
    from pipeline_builder import build_regeneration_prompt, extract_json_from_response
    import yaml
    import json
    import os
    
    start_time = time.time()
    logger.info(f"Starting Regeneration for Question")
    
    # Inject Model Fallback if missing
    if not model:
        try:
            config_path = Path(__file__).parent / "pipeline_config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    model = config.get('regeneration', {}).get('model', 'gemini-3-flash-preview')
            else:
                model = 'gemini-3-flash-preview'
        except Exception as e:
            logger.warning(f"Could not load generation config fallback: {e}")
            model = 'gemini-3-flash-preview'
            
    # Load thinking level
    thinking_level = "high"
    try:
         config_path = Path(__file__).parent / "pipeline_config.yaml"
         if config_path.exists():
             with open(config_path, 'r', encoding='utf-8') as f:
                 config = yaml.safe_load(f)
                 thinking_level = config.get('regeneration', {}).get('thinking_level', 'high')
    except Exception:
        pass

    # Build the specialized Regeneration prompt
    regen_payload = build_regeneration_prompt(
        previous_question_markdown=previous_question_markdown,
        regeneration_reason=regeneration_reason,
        general_config=general_config,
        files=files
    )
    
    prompt = regen_payload['prompt']
    combined_files = regen_payload['files']
    
    # Run Generation
    result = await run_gemini_async(
        prompt=prompt,
        api_key=api_key,
        files=combined_files,
        thinking_level=thinking_level,
        model=model,
        system_prompt=regen_payload.get('system_prompt')
    )
    
    elapsed_gen = time.time() - start_time
    
    if result.get("error"):
        return result
        
    response_text = result.get('text', '')
    
    if response_text:
        logger.info(f"Successfully generated draft regenerated question in {elapsed_gen:.2f}s, starting Validation")
        
        # Load validation prompts
        try:
            prompt_path = os.path.join(os.path.dirname(__file__), 'validation.yaml')
            with open(prompt_path, 'r', encoding='utf-8') as f:
                val_prompts = yaml.safe_load(f)
                
            val_sys = val_prompts.get('validation_prompt', '')
            
            q_type = question_data.get('type', 'Case Study')
            format_key = 'structure_Case_Study'
            if 'mcq' in q_type.lower():
                format_key = 'structure_MCQ'
            elif 'fill' in q_type.lower() or 'fib' in q_type.lower():
                format_key = 'structure_FIB'
            elif 'multi' in q_type.lower() and 'part' in q_type.lower():
                format_key = 'structure_Multi_Part'
            elif 'descriptive' in q_type.lower():
                if 'sub' in q_type.lower():
                    format_key = 'structure_Descriptive_w_subq'
                else:
                    format_key = 'structure_Descriptive'
            elif 'assertion' in q_type.lower() or 'reasoning' in q_type.lower():
                format_key = 'structure_AR'
                
            format_rules = val_prompts.get(format_key, '')
            val_sys = val_sys.replace("{{OUTPUT_FORMAT_RULES}}", format_rules)
            
            # Wrap generated text in JSON array format for validation
            generated_json_str = json.dumps({"question1": response_text}, ensure_ascii=False)
            val_sys = val_sys.replace("{{GENERATED_CONTENT}}", generated_json_str)
            
            val_result = await run_gemini_async(
                prompt=val_sys,
                api_key=api_key,
                files=[],
                thinking_level="low",
                model=model,
                system_prompt="You are a strict Question Validator & Minimal-Repair Agent."
            )
            
            val_text = val_result.get('text', '')
            final_markdown = response_text
            
            if val_text:
                extracted = extract_json_from_response(val_text)
                if extracted and isinstance(extracted, dict):
                    for k, v in extracted.items():
                        final_markdown = v
                        break
            
            total_elapsed = time.time() - start_time
            logger.info(f"Validation completed. Total regeneration took {total_elapsed:.2f}s")
            
            return {
                "regenerated_data": {"markdown": final_markdown},
                "raw_response": final_markdown,
                "elapsed": total_elapsed,
                "input_tokens": result.get('input_tokens', 0) + val_result.get('input_tokens', 0),
                "output_tokens": result.get('output_tokens', 0) + val_result.get('output_tokens', 0)
            }
            
        except Exception as e:
            logger.error(f"Validation failed during regeneration: {e}")
            return {
                "regenerated_data": {"markdown": response_text},
                "raw_response": response_text,
                "elapsed": time.time() - start_time,
                "input_tokens": result.get('input_tokens', 0),
                "output_tokens": result.get('output_tokens', 0)
            }
    else:
        logger.error(f"Failed to get regenerated response text")
        return {
            "error": "Failed to generate text for regeneration",
            "raw_response": response_text,
            "elapsed": time.time() - start_time
        }
