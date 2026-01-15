"""
Batch Processor for Parallel Question Generation
Groups questions by type and processes them in parallel batches.
"""

import asyncio
from typing import List, Dict, Any
from collections import defaultdict
import logging
from datetime import datetime
from pathlib import Path
import os

from llm_engine import run_gemini_async
from prompt_builder import build_prompt_for_batch, get_files

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def save_prompt_to_file(prompt_text: str, batch_key: str) -> str:
    """
    Save the generated prompt to a text file.
    
    Args:
        prompt_text: The prompt text to save
        batch_key: The batch key (question type) for naming
    
    Returns:
        Path to the saved file
    """
    # Create prompt_logs directory if it doesn't exist
    logs_dir = Path("prompt_logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize batch_key to remove invalid filename characters
    safe_key = batch_key.replace('/', '_').replace('\\', '_').replace(':', '')
    filename = f"prompt_{safe_key}_{timestamp}.txt"
    filepath = logs_dir / filename
    
    # Save prompt to file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(prompt_text)
    
    logger.info(f"Saved prompt to: {filepath}")
    return str(filepath)




def group_questions_by_type_and_topic(questions_config: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group questions by question type for batch processing.
    Returns a dictionary where keys are question types and values are lists of question configs.
    """
    grouped = defaultdict(list)
    
    for idx, q_config in enumerate(questions_config):
        q_type = q_config.get('type', 'MCQ')
        # Add index for tracking
        q_config['original_index'] = idx
        grouped[q_type].append(q_config)
    
    logger.info(f"Grouped {len(questions_config)} questions into {len(grouped)} batches")
    for q_type, questions in grouped.items():
        logger.info(f"  - {q_type}: {len(questions)} questions")
    
    return dict(grouped)



async def generate_raw_batch(
    batch_key: str,
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    type_config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Generate raw questions for a single batch (Stage 1).
    """
    logger.info(f"Generating RAW batch: {batch_key} ({len(questions)} questions)")
    
    try:
        # Build the prompt for this batch
        prompt_data = build_prompt_for_batch(batch_key, questions, general_config, type_config)
        
        prompt_text = prompt_data['prompt']
        files = prompt_data.get('files', [])
        file_metadata = prompt_data.get('file_metadata', {})
        api_key = general_config['api_key']
        
        # Save prompt to file for review
        save_prompt_to_file(prompt_text, batch_key)
        
        # Call Gemini API for generation
        result = await run_gemini_async(
            prompt=prompt_text,
            api_key=api_key,
            files=files,
            thinking_budget=5000,
            file_metadata=file_metadata
        )
        
        # Add metadata
        result['question_count'] = len(questions)
        result['used_file'] = len(files) > 0
        result['batch_key'] = batch_key
        result['file_source'] = file_metadata.get('source_type', 'N/A')
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating raw batch {batch_key}: {e}")
        return {
            'error': str(e),
            'text': f"Error generating {batch_key} questions: {str(e)}",
            'elapsed': 0,
            'question_count': len(questions),
            'batch_key': batch_key
        }


async def validate_batch(
    batch_key: str,
    validation_prompt_text: str,
    general_config: Dict[str, Any],
    files: List = None,
    file_metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Validate a batch of questions using Gemini 2.5 Pro (Stage 2).
    """
    logger.info(f"Validating batch: {batch_key}")
    
    try:
        api_key = general_config['api_key']
        
        # Save validation prompt to file
        save_prompt_to_file(validation_prompt_text, f"validation_{batch_key}")
        
        # Call Gemini API for validation with files if available
        result = await run_gemini_async(
            prompt=validation_prompt_text,
            api_key=api_key,
            files=files,
            thinking_budget=5000,
            file_metadata=file_metadata
        )
        
        result['batch_key'] = batch_key
        return result
        
    except Exception as e:
        logger.error(f"Error validating batch {batch_key}: {e}")
        return {
            'error': str(e),
            'text': f"Error validating {batch_key} questions: {str(e)}",
            'elapsed': 0,
            'batch_key': batch_key
        }


async def process_batches_pipeline(
    questions_config: List[Dict[str, Any]],
    general_config: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Process questions in a localized pipeline:
    Gen(1) -> Start Val(1) & Gen(2) -> Start Val(2) ...
    """
    logger.info(f"Starting pipeline processing for {len(questions_config)} questions")
    
    # Group questions by type
    grouped_questions = group_questions_by_type_and_topic(questions_config)
    
    # Load validation prompt template
    try:
        import yaml
        with open('validation.yaml', 'r', encoding='utf-8') as f:
            validation_config = yaml.safe_load(f)
            validation_prompt_template = validation_config.get('validation_prompt', '')
            if not validation_prompt_template:
                logger.warning("Validation prompt not found under key 'validation_prompt'. Falling back to raw file read.")
                # Fallback purely for robustness if file wasn't updated correctly
                with open('validation.yaml', 'r', encoding='utf-8') as f:
                    validation_prompt_template = f.read()

    except Exception as e:
        logger.error(f"Failed to load validation.yaml: {e}")
        return {'error': "Critical: validation.yaml not found"}

    pipeline_results = {}
    validation_tasks = []
    
    # Sequential Generation Loop
    for batch_key, questions in grouped_questions.items():
        # 1. Generate Raw (Await)
        logger.info(f">>> Pipeline Stage 1: Generaring {batch_key}")
        raw_result = await generate_raw_batch(batch_key, questions, general_config, type_config=None)
        
        # Store raw result immediately
        pipeline_results[batch_key] = {
            'raw': raw_result,
            'validated': None  # Placeholder
        }
        
        if raw_result.get('error'):
            logger.warning(f"Skipping validation for {batch_key} due to generation error.")
            continue
            

        # 2. Start Validation (Async - Fire and Forget/Collect later)
        
        # Collect context and files for validation
        # file_info = get_files(questions, general_config)
        # val_files = file_info['files']
        # val_file_metadata = file_info.get('file_metadata', {
        #      'source_type': file_info.get('source_type', 'N/A'),
        #      'filenames': file_info.get('filenames', [])
        # })
        
        # Validation should NOT receive files (per user request & to fix race condition)
        val_files = [] 
        val_file_metadata = {'source_type': 'None (Validation)', 'filenames': []}

        # Build Context String for Strict Validation
        context_lines = []
        
        # Global Notes
        if general_config.get('additional_notes'):
            context_lines.append(f"Global Additional Notes: {general_config['additional_notes']}")
        
        # Universal File
        if general_config.get('universal_pdf'):
            u_name = getattr(general_config['universal_pdf'], 'name', 'Universal PDF')
            context_lines.append(f"Universal File Provided: {u_name}")

        # Per Question Context
        context_lines.append("\nPer-Question Context:")
        for idx, q in enumerate(questions):
            q_type = q.get('mcq_type') or q.get('fib_type') or q.get('descriptive_type') or "Standard"
            q_topic = q.get('topic', 'Unknown')
            q_notes = q.get('additional_notes_text', '')
            q_file = q.get('additional_notes_pdf')
            
            line = f"- Q{idx+1} ({q_topic}): Type='{q_type}'"
            if q_notes:
                line += f", Notes='{q_notes}'"
            if q_file:
                fname = getattr(q_file, 'name', 'File')
                line += f", File='{fname}'"
            context_lines.append(line)
            
        input_context_str = "\n".join(context_lines)

        # Determine Output Structure based on Batch Key
        # Map batch_key to validation.yaml keys
        structure_map = {
            "MCQ": "structure_MCQ",
            "Fill in the Blanks": "structure_FIB",
            "Case Study": "structure_Case_Study",
            "Multi-Part": "structure_Multi_Part",
            "Assertion-Reasoning": "structure_AR",
            "Descriptive": "structure_Descriptive",
            "Descriptive w/ Subquestions": "structure_Descriptive_w_subq"
        }
        
        structure_key = structure_map.get(batch_key)
        structure_format = ""
        
        if structure_key and structure_key in validation_config:
            structure_format = validation_config[structure_key]
        else:
            logger.warning(f"No specific output structure found for batch '{batch_key}' (mapped to '{structure_key}'). Using default generic JSON instruction.")
            structure_format = "Return a valid JSON object suitable for this question type."

        # Inject generated content, context, and output structure into validation prompt
        val_prompt = validation_prompt_template.replace("{{GENERATED_CONTENT}}", raw_result['text'])
        val_prompt = val_prompt.replace("{{INPUT_CONTEXT}}", input_context_str)
        val_prompt = val_prompt.replace("{{OUTPUT_FORMAT_RULES}}", structure_format)
        
        logger.info(f">>> Pipeline Stage 2: Scheduling Validation for {batch_key} with {len(val_files)} files")
        val_task = asyncio.create_task(
            validate_batch(batch_key, val_prompt, general_config, files=val_files, file_metadata=val_file_metadata)
        )
        validation_tasks.append((batch_key, val_task))
        
        # Loop continues immediately to next generation
    
    # Wait for all validations to complete
    if validation_tasks:
        logger.info(f"Waiting for {len(validation_tasks)} validation tasks to complete...")
        results = await asyncio.gather(*[t[1] for t in validation_tasks], return_exceptions=True)
        
        for (b_key, _), val_res in zip(validation_tasks, results):
            if isinstance(val_res, Exception):
                logger.error(f"Validation failed for {b_key}: {val_res}")
                pipeline_results[b_key]['validated'] = {'error': str(val_res), 'text': "Validation Exception"}
            else:
                pipeline_results[b_key]['validated'] = val_res
                
    logger.info("Pipeline processing completed.")
    return pipeline_results
