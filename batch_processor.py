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
from prompt_builder import build_prompt_for_batch

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
    filename = f"prompt_{batch_key}_{timestamp}.txt"
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


async def process_single_batch(
    batch_key: str,
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    type_config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Process a single batch of questions of the same type.
    
    Args:
        batch_key: Question type identifier
        questions: List of question configurations
        general_config: General configuration (curriculum, grade, etc.)
        type_config: Type-specific configuration (e.g., subparts for Multi-Part)
    
    Returns:
        Dictionary with generation results
    """
    logger.info(f"Processing batch: {batch_key} ({len(questions)} questions)")
    
    try:
        # Build the prompt for this batch
        prompt_data = build_prompt_for_batch(batch_key, questions, general_config, type_config)
        
        prompt_text = prompt_data['prompt']
        files = prompt_data.get('files', [])
        file_metadata = prompt_data.get('file_metadata', {})
        api_key = general_config['api_key']
        
        # Save prompt to file for review
        save_prompt_to_file(prompt_text, batch_key)
        
        # Call Gemini API with files and metadata
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
        
        logger.info(f"Batch {batch_key} completed | Source: {result['file_source']} | Time: {result.get('elapsed', 0):.2f}s")
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing batch {batch_key}: {e}")
        return {
            'error': str(e),
            'text': f"Error generating {batch_key} questions: {str(e)}",
            'elapsed': 0,
            'question_count': len(questions),
            'used_pdf': False,
            'batch_key': batch_key,
            'pdf_source': 'N/A'
        }


async def process_questions_batch(
    questions_config: List[Dict[str, Any]],
    general_config: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Process all questions in parallel batches grouped by type.
    
    Args:
        questions_config: List of individual question configurations
        general_config: General configuration (curriculum, grade, chapter, etc.)
    
    Returns:
        Dictionary mapping batch keys to their results
    """
    logger.info(f"Starting batch processing for {len(questions_config)} questions")
    
    # Group questions by type
    grouped_questions = group_questions_by_type_and_topic(questions_config)
    
    # Create async tasks for each batch
    tasks = []
    batch_keys = []
    
    for batch_key, questions in grouped_questions.items():
        task = process_single_batch(batch_key, questions, general_config)
        tasks.append(task)
        batch_keys.append(batch_key)
    
    # Execute all batches in parallel
    logger.info(f"Executing {len(tasks)} batches in parallel...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Combine results
    output = {}
    for batch_key, result in zip(batch_keys, results):
        if isinstance(result, Exception):
            logger.error(f"Batch {batch_key} failed with exception: {result}")
            output[batch_key] = {
                'error': str(result),
                'text': f"Exception in {batch_key}: {str(result)}",
                'elapsed': 0,
                'question_count': len(grouped_questions[batch_key]),
                'used_pdf': False
            }
        else:
            output[batch_key] = result
    
    logger.info("All batches completed")
    return output
