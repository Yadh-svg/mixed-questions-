"""
Batch Processor for Parallel Question Generation
Groups questions by type and processes them in parallel batches.
"""

import asyncio
from typing import List, Dict, Any
from collections import defaultdict
import logging

from llm_engine import run_gemini_async
from prompt_builder import build_prompt_for_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        pdf_files = prompt_data.get('pdf_files', [])
        pdf_metadata = prompt_data.get('pdf_metadata', {})
        api_key = general_config['api_key']
        
        # Call Gemini API with PDF files and metadata
        result = await run_gemini_async(
            prompt=prompt_text,
            api_key=api_key,
            pdf_files=pdf_files,
            thinking_budget=5000,
            pdf_metadata=pdf_metadata
        )
        
        # Add metadata
        result['question_count'] = len(questions)
        result['used_pdf'] = len(pdf_files) > 0
        result['batch_key'] = batch_key
        result['pdf_source'] = pdf_metadata.get('source_type', 'N/A')
        
        logger.info(f"Batch {batch_key} completed | Source: {result['pdf_source']} | Time: {result.get('elapsed', 0):.2f}s")
        
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
