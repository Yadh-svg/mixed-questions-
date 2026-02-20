"""
Stage-by-Stage Pipeline Execution Functions
Individual functions for each pipeline stage that can be called independently.
"""

import asyncio
import logging
import json
from typing import Dict, List, Any, Optional
from pathlib import Path

from pipeline_builder import (
    build_scenario_prompt,
    build_question_prompt,
    build_solution_prompt,
    build_analysis_prompt,
    extract_json_from_response
)
from llm_engine import run_gemini_async
from pipeline_executor import get_stage_config
from pipeline_logger import save_stage_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def execute_stage1_scenario(
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None
) -> Dict[str, Any]:
    """
    Execute Stage 1: Scenario Generation
    
    Args:
        questions: List of question configurations
        general_config: General configuration (grade, subject, chapter, etc.)
        files: Optional PDF/image files
        
    Returns:
        Dictionary with:
            - scenario_data: Parsed scenario JSON
            - raw_response: Full LLM response
            - metadata: Timing, tokens, etc.
    """
    logger.info(f"[Stage 1] Starting Scenario Generation for {len(questions)} questions")
    
    try:
        # Build prompt
        prompt_data = build_scenario_prompt(questions, general_config, files)
        prompt_text = prompt_data['prompt']
        
        # Save prompt for debugging
        save_stage_prompt(
            stage_num=1,
            prompt_text=prompt_text,
            metadata={
                'question_count': len(questions),
                'has_files': len(files) > 0 if files else False,
                'grade': general_config.get('grade', 'N/A'),
                'subject': general_config.get('subject', 'N/A'),
                'chapter': general_config.get('chapter', 'N/A')
            }
        )
        
        # Get model config for this stage
        stage_config = get_stage_config('scenario_generation')
        
        # Call LLM
        result = await run_gemini_async(
            prompt=prompt_text,
            api_key=general_config['api_key'],
            files=prompt_data.get('files', []),
            thinking_level=stage_config.get('thinking_level', 'high'),
            temperature=stage_config.get('temperature', 1.0),
            file_metadata=prompt_data.get('file_metadata', {})
        )
        
        # Extract JSON from response
        scenario_data = extract_json_from_response(result.get('text', ''))
        
        if not scenario_data:
            logger.error("[Stage 1] Failed to extract JSON from response")
            return {
                'error': 'Failed to parse scenario JSON',
                'raw_response': result.get('text', ''),
                'metadata': result
            }
        
        logger.info(f"[Stage 1] Completed successfully. Tokens: {result.get('input_tokens', 0)} in, {result.get('output_tokens', 0)} out")
        
        return {
            'scenario_data': scenario_data,
            'raw_response': result.get('text', ''),
            'metadata': {
                'elapsed': result.get('elapsed', 0),
                'input_tokens': result.get('input_tokens', 0),
                'output_tokens': result.get('output_tokens', 0),
                'thought_tokens': result.get('thought_tokens', 0),
                'model': stage_config.get('model', 'unknown')
            }
        }
        
    except Exception as e:
        logger.error(f"[Stage 1] Error: {e}")
        return {
            'error': str(e),
            'raw_response': '',
            'metadata': {}
        }


async def execute_stage2_question(
    scenario_data: Dict[str, Any],
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None
) -> Dict[str, Any]:
    """
    Execute Stage 2: Question Generation from Scenario
    
    Args:
        scenario_data: Output from Stage 1
        questions: List of question configurations
        general_config: General configuration
        files: Optional PDF/image files
        
    Returns:
        Dictionary with question_data, raw_response, metadata
    """
    logger.info("[Stage 2] Starting Question Generation from Scenario")
    
    try:
        # Build prompt
        prompt_data = build_question_prompt(scenario_data, questions, general_config, files)
        prompt_text = prompt_data['prompt']
        
        # Save prompt
        save_stage_prompt(
            stage_num=2,
            prompt_text=prompt_text,
            metadata={
                'question_count': len(questions),
                'has_files': len(files) > 0 if files else False,
                'scenario_topics': len(scenario_data) if isinstance(scenario_data, list) else 1
            }
        )
        
        # Get model config
        stage_config = get_stage_config('question_generation')
        
        # Call LLM
        result = await run_gemini_async(
            prompt=prompt_text,
            api_key=general_config['api_key'],
            files=prompt_data.get('files', []),
            thinking_level=stage_config.get('thinking_level', 'high'),
            temperature=stage_config.get('temperature', 0.8),
            file_metadata=prompt_data.get('file_metadata', {})
        )
        
        # Extract JSON
        question_data = extract_json_from_response(result.get('text', ''))
        
        if not question_data:
            logger.error("[Stage 2] Failed to extract JSON from response")
            return {
                'error': 'Failed to parse question JSON',
                'raw_response': result.get('text', ''),
                'metadata': result
            }
        
        logger.info(f"[Stage 2] Completed successfully")
        
        return {
            'question_data': question_data,
            'raw_response': result.get('text', ''),
            'metadata': {
                'elapsed': result.get('elapsed', 0),
                'input_tokens': result.get('input_tokens', 0),
                'output_tokens': result.get('output_tokens', 0),
                'thought_tokens': result.get('thought_tokens', 0),
                'model': stage_config.get('model', 'unknown')
            }
        }
        
    except Exception as e:
        logger.error(f"[Stage 2] Error: {e}")
        return {
            'error': str(e),
            'raw_response': '',
            'metadata': {}
        }


async def execute_stage3_solution(
    question_data: Dict[str, Any],
    scenario_data: Dict[str, Any],
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None
) -> Dict[str, Any]:
    """
    Execute Stage 3: Solution Generation from Question
    
    Args:
        question_data: Output from Stage 2
        scenario_data: Output from Stage 1
        questions: List of question configurations
        general_config: General configuration
        files: Optional PDF/image files
        
    Returns:
        Dictionary with solution_data, raw_response, metadata
    """
    logger.info("[Stage 3] Starting Solution Generation")
    
    try:
        # Build prompt
        prompt_data = build_solution_prompt(
            question_data, scenario_data, questions, general_config, files
        )
        prompt_text = prompt_data['prompt']
        
        # Save prompt
        save_stage_prompt(
            stage_num=3,
            prompt_text=prompt_text,
            metadata={
                'question_count': len(questions),
                'has_files': len(files) > 0 if files else False
            }
        )
        
        # Get model config
        stage_config = get_stage_config('solution_generation')
        
        # Call LLM
        result = await run_gemini_async(
            prompt=prompt_text,
            api_key=general_config['api_key'],
            files=prompt_data.get('files', []),
            thinking_level=stage_config.get('thinking_level', 'high'),
            temperature=stage_config.get('temperature', 0.3),
            file_metadata=prompt_data.get('file_metadata', {})
        )
        
        # Extract JSON
        solution_data = extract_json_from_response(result.get('text', ''))
        
        if not solution_data:
            logger.error("[Stage 3] Failed to extract JSON from response")
            return {
                'error': 'Failed to parse solution JSON',
                'raw_response': result.get('text', ''),
                'metadata': result
            }
        
        logger.info(f"[Stage 3] Completed successfully")
        
        return {
            'solution_data': solution_data,
            'raw_response': result.get('text', ''),
            'metadata': {
                'elapsed': result.get('elapsed', 0),
                'input_tokens': result.get('input_tokens', 0),
                'output_tokens': result.get('output_tokens', 0),
                'thought_tokens': result.get('thought_tokens', 0),
                'model': stage_config.get('model', 'unknown')
            }
        }
        
    except Exception as e:
        logger.error(f"[Stage 3] Error: {e}")
        return {
            'error': str(e),
            'raw_response': '',
            'metadata': {}
        }


async def execute_stage4_analysis(
    question_data: Dict[str, Any],
    solution_data: Dict[str, Any],
    scenario_data: Dict[str, Any],
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None
) -> Dict[str, Any]:
    """
    Execute Stage 4: Educational Analysis
    
    Args:
        question_data: Output from Stage 2
        solution_data: Output from Stage 3
        scenario_data: Output from Stage 1
        questions: List of question configurations
        general_config: General configuration
        files: Optional PDF/image files
        
    Returns:
        Dictionary with analysis_data, raw_response, metadata
    """
    logger.info("[Stage 4] Starting Educational Analysis")
    
    try:
        # Build prompt
        prompt_data = build_analysis_prompt(
            question_data, solution_data, scenario_data, questions, general_config, files
        )
        prompt_text = prompt_data['prompt']
        
        # Save prompt
        save_stage_prompt(
            stage_num=4,
            prompt_text=prompt_text,
            metadata={
                'question_count': len(questions),
                'has_files': len(files) > 0 if files else False
            }
        )
        
        # Get model config
        stage_config = get_stage_config('analysis_generation')
        
        # Call LLM
        result = await run_gemini_async(
            prompt=prompt_text,
            api_key=general_config['api_key'],
            files=prompt_data.get('files', []),
            thinking_level=stage_config.get('thinking_level', 'medium'),
            temperature=stage_config.get('temperature', 0.8),
            file_metadata=prompt_data.get('file_metadata', {})
        )
        
        # Extract JSON
        analysis_data = extract_json_from_response(result.get('text', ''))
        
        if not analysis_data:
            logger.error("[Stage 4] Failed to extract JSON from response")
            return {
                'error': 'Failed to parse analysis JSON',
                'raw_response': result.get('text', ''),
                'metadata': result
            }
        
        logger.info(f"[Stage 4] Completed successfully")
        
        return {
            'analysis_data': analysis_data,
            'raw_response': result.get('text', ''),
            'metadata': {
                'elapsed': result.get('elapsed', 0),
                'input_tokens': result.get('input_tokens', 0),
                'output_tokens': result.get('output_tokens', 0),
                'thought_tokens': result.get('thought_tokens', 0),
                'model': stage_config.get('model', 'unknown')
            }
        }
        
    except Exception as e:
        logger.error(f"[Stage 4] Error: {e}")
        return {
            'error': str(e),
            'raw_response': '',
            'metadata': {}
        }
