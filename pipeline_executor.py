"""
Multi-Stage Pipeline Execution
Updated for 3-Stage Architect-Writer Flow (Math Core -> Writer -> Solution)
"""

import logging
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Config file path
PIPELINE_CONFIG_FILE = Path(__file__).parent / "pipeline_config.yaml"


def load_pipeline_config() -> Dict[str, Any]:
    """Load pipeline configuration from file."""
    try:
        if not PIPELINE_CONFIG_FILE.exists():
             logger.error(f"❌ Config file not found at {PIPELINE_CONFIG_FILE}")
             raise FileNotFoundError(f"Config file not found: {PIPELINE_CONFIG_FILE}")
             
        with open(PIPELINE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if not config:
                logger.warning(f"⚠️ Config file {PIPELINE_CONFIG_FILE} is empty or invalid.")
                return {}
            logger.info(f"✅ Loaded pipeline config with keys: {list(config.keys())}")
            return config
    except Exception as e:
        logger.error(f"❌ Critical Error loading pipeline config: {e}")
        raise e

def get_stage_config(stage_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Get model config for stage."""
    # Direct lookup with fallback for backward compatibility
    fallback_map = {
        'math_core': 'scenario_generation', 
        'writer': 'question_generation',    
        'solution': 'solution_generation'   
    }
    
    # Try direct key first
    if stage_name in config:
        stage_conf = config[stage_name]
    else:
        # Try fallback key
        fallback_key = fallback_map.get(stage_name)
        stage_conf = config.get(fallback_key, {})
    
    # Defaults
    # CRITICAL: Strict model requirement - no defaults allowed
    model = stage_conf.get('model')
    if not model:
        logger.error(f"❌ No model defined for stage '{stage_name}' in pipeline_config.yaml. Strict mode enabled.")
        raise ValueError(f"Missing 'model' configuration for stage '{stage_name}'. Please check pipeline_config.yaml.")
        
    return {
        'model': model,
        'temperature': stage_conf.get('temperature', 0.7),
        'thinking_level': stage_conf.get('thinking_level', None)
    }

async def run_stage_pipeline(
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None,
    save_prompts_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Execute 3-Stage Pipeline:
    1. Math Core (Architect)
    2. Scenario + Question (Writer)
    3. Solution (Teacher)
    """
    from pipeline_builder import (
        build_math_core_prompt,
        build_math_core_prompt,
        build_writer_prompt,
        extract_json_from_response,
        GENERATION_PIPELINE_MODE
    )
    from llm_engine import run_gemini_async
    
    # Reload config to ensure we have latest updates
    pipeline_config = load_pipeline_config()
    
    api_key = general_config['api_key']
    logger.info(f"🚀 Starting 3-Stage Architect-Writer Pipeline for {len(questions)} items")

    try:
        # ============================================================================
        # STAGE 1: MATH CORE (ARCHITECT)
        # ============================================================================
        s1_conf = get_stage_config('math_core', pipeline_config)
        logger.info(f"🏛️ Stage 1: Math Core (Architect) | Model: {s1_conf['model']}")
        
        prompt_data_1 = build_math_core_prompt(questions, general_config, files)
        
        # Save prompt
        if save_prompts_dir:
            with open(save_prompts_dir / "stage1_math_prompt.txt", "w", encoding="utf-8") as f:
                f.write(prompt_data_1['prompt'])

        result_1 = await run_gemini_async(
            prompt=prompt_data_1['prompt'],
            api_key=api_key,
            files=prompt_data_1['files'],
            thinking_level=s1_conf['thinking_level'], # Use config value
            model=s1_conf['model']
        )
        
        math_core_data = extract_json_from_response(result_1['text'])
        if not math_core_data:
            # Fallback
            math_core_data = {"math_cores": [], "raw_text": result_1['text']}
            logger.warning("⚠️ Stage 1 produced no JSON. Passing raw text.")
            
        logger.info("✅ Stage 1 Complete")

        # ============================================================================
        # STAGE 2: WRITER (SCENARIO + QUESTION)
        # ============================================================================
        s2_conf = get_stage_config('writer', pipeline_config)
        logger.info(f"✍️ Stage 2: Writer | Model: {s2_conf['model']}")
        
        prompt_data_2 = build_writer_prompt(math_core_data, questions, general_config, files)
        
        if save_prompts_dir:
            with open(save_prompts_dir / "stage2_writer_prompt.txt", "w", encoding="utf-8") as f:
                f.write(prompt_data_2['prompt'])
                
        result_2 = await run_gemini_async(
            prompt=prompt_data_2['prompt'],
            api_key=api_key,
            files=prompt_data_2['files'],
            thinking_level=s2_conf['thinking_level'],
            model=s2_conf['model']
        )
        
        writer_data = extract_json_from_response(result_2['text'])
        if not writer_data:
             writer_data = {"questions": [], "raw_text": result_2['text']}
        
        logger.info("✅ Stage 2 Complete")
        
        # ============================================================================
        # STAGE 3: SOLUTION (TEACHER) - REMOVED PER USER REQUEST
        # ============================================================================
        # Solution stage has been removed. Stage 2 (Writer) is now the final output.
        solution_data = {} 

        
        # Combine
        # Calculate total tokens
        total_input = result_1.get('input_tokens', 0) + result_2.get('input_tokens', 0)
        total_output = result_1.get('output_tokens', 0) + result_2.get('output_tokens', 0)
        
        final_output = {
            "math_core": math_core_data,
            "writer_output": writer_data,
            "solution_output": solution_data,
            "_pipeline_metadata": {
                "mode": GENERATION_PIPELINE_MODE,
                "stages": 2,
                "total_tokens": {
                    "input": total_input,
                    "output": total_output
                }
            }
        }
        
        return final_output

    except Exception as e:
        logger.error(f"❌ Pipeline Failed: {e}")
        raise e
