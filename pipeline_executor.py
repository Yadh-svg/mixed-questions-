"""
Multi-Stage Pipeline Execution
3-Stage Pipeline: Math Core (Gemini) → Writer/Question Generator (Gemini) → Solution (Gemini Flash)
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

def get_stage_config(stage_name: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get model config for a stage.
    
    Returns a dict with at minimum:
        - provider:          "gemini" | "openai"
        - model:             model name string
        - temperature:       float
        - thinking_level:    str | None   (Gemini only)
        - reasoning_effort:  str | None   (OpenAI only)
    """
    if config is None:
        config = load_pipeline_config()

    # Direct lookup with fallback for backward compatibility
    fallback_map = {
        'math_core': 'scenario_generation',
        'writer':    'question_generation',
        'solution':  'solution_generation'
    }
    
    # Try direct key first
    if stage_name in config:
        stage_conf = config[stage_name]
    else:
        fallback_key = fallback_map.get(stage_name)
        stage_conf = config.get(fallback_key, {})
    
    # Strict model requirement
    model = stage_conf.get('model')
    if not model:
        logger.error(f"❌ No model defined for stage '{stage_name}' in pipeline_config.yaml.")
        raise ValueError(f"Missing 'model' configuration for stage '{stage_name}'. Please check pipeline_config.yaml.")
        
    return {
        'provider':         stage_conf.get('provider', 'gemini'),
        'model':            model,
        'temperature':      stage_conf.get('temperature', 0.7),
        'thinking_level':   stage_conf.get('thinking_level', None),     # Gemini
        'reasoning_effort': stage_conf.get('reasoning_effort', None),   # OpenAI
    }

async def run_stage_pipeline(
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None,
    save_prompts_dir: Optional[Path] = None,
    previous_batch_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute 3-Stage Pipeline:
    1. Math Core           (Gemini Flash Lite  — extract topics / math structure from PDF)
    2. Writer/Question Gen (Gemini            — generate Scenario + Question)
    3. Solution            (Gemini Flash       — generate Solution, Key Idea, Steps)
    """
    from pipeline_builder import (
        build_math_core_prompt,
        build_writer_prompt,
        build_solution_prompt,
        extract_json_from_response,
        GENERATION_PIPELINE_MODE
    )
    from llm_engine import run_gemini_async, run_openai_async
    
    # Reload config to ensure we have latest updates
    pipeline_config = load_pipeline_config()
    
    gemini_api_key = general_config['api_key']
    openai_api_key = general_config.get('openai_api_key', '')
    
    logger.info(f"🚀 Starting 3-Stage Pipeline for {len(questions)} items")

    try:
        # ============================================================================
        # STAGE 1: MATH CORE (ARCHITECT)  —  Gemini Flash Lite
        # ============================================================================
        s1_conf = get_stage_config('math_core', pipeline_config)
        logger.info(f"🏛️ Stage 1: Math Core | Provider: {s1_conf['provider']} | Model: {s1_conf['model']}")
        
        prompt_data_1 = build_math_core_prompt(questions, general_config, files, previous_batch_metadata)

        result_1 = await run_gemini_async(
            prompt=prompt_data_1['prompt'],
            api_key=gemini_api_key,
            files=prompt_data_1['files'],
            thinking_level=s1_conf['thinking_level'],
            model=s1_conf['model']
        )
        
        if save_prompts_dir:
            with open(save_prompts_dir / "stage1_math_core_prompt.txt", "w", encoding="utf-8") as f:
                f.write(f"=== USER PROMPT ===\n{prompt_data_1.get('prompt', '')}")
            with open(save_prompts_dir / "stage1_math_core_output.txt", "w", encoding="utf-8") as f:
                f.write(f"=== RAW OUTPUT ===\n{result_1['text']}")
                
        math_core_data = extract_json_from_response(result_1['text'])
        if not math_core_data:
            math_core_data = {"math_cores": [], "raw_text": result_1['text']}
            logger.warning("⚠️ Stage 1 produced no JSON. Passing raw text.")
            
        logger.info("✅ Stage 1 Complete")

        # ============================================================================
        # STAGE 2: WRITER (SCENARIO + QUESTION)  —  Gemini
        # ============================================================================
        s2_conf = get_stage_config('writer', pipeline_config)
        logger.info(f"✍️ Stage 2: Writer | Provider: {s2_conf['provider']} | Model: {s2_conf['model']}")
        
        prompt_data_2 = build_writer_prompt(
            math_core_data, questions, general_config, files, previous_batch_metadata
        )

        if save_prompts_dir:
            with open(save_prompts_dir / "stage2_writer_prompt.txt", "w", encoding="utf-8") as f:
                f.write(f"=== SYSTEM PROMPT ===\n{prompt_data_2.get('system_prompt', '')}\n\n"
                        f"=== USER PROMPT ===\n{prompt_data_2.get('user_prompt', prompt_data_2.get('prompt',''))}")

        if s2_conf['provider'] == 'openai':
            if not openai_api_key or openai_api_key == 'YOUR_OPENAI_API_KEY_HERE':
                raise ValueError(
                    "OpenAI API key is missing. Please set OPENAI_API_KEY in .streamlit/secrets.toml"
                )
            result_2 = await run_openai_async(
                system_prompt=prompt_data_2.get('system_prompt', ''),
                user_prompt=prompt_data_2.get('user_prompt', prompt_data_2.get('prompt', '')),
                api_key=openai_api_key,
                model=s2_conf['model'],
                temperature=s2_conf['temperature'],
                reasoning_effort=s2_conf.get('reasoning_effort')
            )
        else:
            # Gemini
            result_2 = await run_gemini_async(
                prompt=prompt_data_2.get('user_prompt', prompt_data_2.get('prompt', '')),
                api_key=gemini_api_key,
                files=prompt_data_2['files'],
                thinking_level=s2_conf['thinking_level'],
                model=s2_conf['model'],
                system_prompt=prompt_data_2.get('system_prompt')
            )

        if save_prompts_dir:
            with open(save_prompts_dir / "stage2_writer_prompt.txt", "w", encoding="utf-8") as f:
                f.write(f"=== SYSTEM PROMPT ===\n{prompt_data_2.get('system_prompt', '')}\n\n"
                        f"=== USER PROMPT ===\n{prompt_data_2.get('user_prompt', prompt_data_2.get('prompt',''))}")
            with open(save_prompts_dir / "stage2_writer_output.txt", "w", encoding="utf-8") as f:
                f.write(f"=== RAW OUTPUT ===\n{result_2['text']}")
        
        writer_data = extract_json_from_response(result_2['text'])
        if not writer_data:
             writer_data = {"questions": [], "raw_text": result_2['text']}
        
        logger.info("✅ Stage 2 Complete")

        # ============================================================================
        # STAGE 2.5: DOK 3 UPGRADER (STRENGTHENS DOK 3)  —  Gemini (Conditional)
        # ============================================================================
        # 1. Identify which questions/configs in the current batch require DOK 3 upgrading
        dok3_indices = [] # 0-based indices within the 'questions' list
        for idx, q_conf in enumerate(questions):
            is_q_dok3 = False
            # Check top-level DOK
            if str(q_conf.get('dok')) == '3' or q_conf.get('dok') == 3:
                is_q_dok3 = True
            else:
                # Check subparts DOK
                subparts = q_conf.get('subparts') or q_conf.get('subparts_config') or []
                if any(str(sp.get('dok')) == '3' or sp.get('dok') == 3 for sp in subparts):
                    is_q_dok3 = True
            
            if is_q_dok3:
                dok3_indices.append(idx)

        if dok3_indices:
            s25_conf = get_stage_config('dok_upgrader', pipeline_config)
            logger.info(f"🛡️ Stage 2.5: DOK 3 Upgrader | Upgrading {len(dok3_indices)} questions | Model: {s25_conf['model']}")
            
            # 2. Filter writer_data and questions config to only include DOK 3 items
            filtered_questions_conf = [questions[i] for i in dok3_indices]
            
            # Handle potential index mismatch if writer generated unexpected number of questions
            # But usually it's a 1:1 mapping in this pipeline
            all_writer_questions = writer_data.get('questions', [])
            filtered_writer_questions = []
            for i in dok3_indices:
                if i < len(all_writer_questions):
                    filtered_writer_questions.append(all_writer_questions[i])
            
            if not filtered_writer_questions:
                logger.warning("⚠️ DOK 3 Upgrader skip: No corresponding questions found in Writer output.")
                result_25_input = result_25_output = result_25_thought = 0
            else:
                filtered_writer_data = {**writer_data, 'questions': filtered_writer_questions}
                
                from pipeline_builder import build_dok_upgrader_prompt
                prompt_data_25 = build_dok_upgrader_prompt(
                    filtered_writer_data, filtered_questions_conf, general_config, files,
                    original_indices=dok3_indices
                )

                if save_prompts_dir:
                    with open(save_prompts_dir / "stage25_dok_upgrader_prompt.txt", "w", encoding="utf-8") as f:
                        f.write(f"=== SYSTEM PROMPT ===\n{prompt_data_25.get('system_prompt', '')}\n\n"
                                f"=== USER PROMPT ===\n{prompt_data_25.get('user_prompt', prompt_data_25.get('prompt', ''))}")

                result_25 = await run_gemini_async(
                    prompt=prompt_data_25.get('user_prompt', prompt_data_25.get('prompt', '')),
                    api_key=gemini_api_key,
                    files=prompt_data_25['files'],
                    thinking_level=s25_conf['thinking_level'],
                    model=s25_conf['model'],
                    system_prompt=prompt_data_25.get('system_prompt')
                )

                if save_prompts_dir:
                    with open(save_prompts_dir / "stage25_dok_upgrader_output.txt", "w", encoding="utf-8") as f:
                        f.write(f"=== RAW OUTPUT ===\n{result_25['text']}")

                upgraded_data = extract_json_from_response(result_25['text'])
                if upgraded_data and 'UPGRADED_QUESTION' in upgraded_data:
                    upgraded_data = upgraded_data['UPGRADED_QUESTION']
                if upgraded_data and 'questions' in upgraded_data:
                    # 3. Merge upgraded questions back into the main writer_data
                    upgraded_questions = upgraded_data['questions']
                    
                    # Create a map of ID -> question for easier merging
                    all_q_map = {q.get('question_id', f"Q{i+1}"): q for i, q in enumerate(all_writer_questions)}
                    
                    found_upgrades = 0
                    for u_q in upgraded_questions:
                        u_id = u_q.get('question_id')
                        if u_id in all_q_map:
                            # Direct ID match
                            idx = [i for i, q in enumerate(all_writer_questions) if q.get('question_id') == u_id][0]
                            all_writer_questions[idx] = u_q
                            found_upgrades += 1
                        else:
                            # Fallback: find by matching index if ID is missing/wrong
                            # We'll use the position in the upgraded_questions list to match dok3_indices
                            pass 

                    # If ID matching failed to find all, fallback to index-based merging
                    if found_upgrades < len(upgraded_questions):
                         logger.info(f"ID matching only found {found_upgrades}/{len(upgraded_questions)}. Falling back to index-based merge.")
                         for i, idx_in_batch in enumerate(dok3_indices):
                            if i < len(upgraded_questions) and idx_in_batch < len(all_writer_questions):
                                all_writer_questions[idx_in_batch] = upgraded_questions[i]
                    
                    writer_data['questions'] = all_writer_questions
                    logger.info("✅ DOK 3 Questions Upgraded and Merged (Order Preserved)")
                else:
                    logger.warning("⚠️ DOK 3 Upgrader produced no valid question JSON. Keeping original Writer output.")
                
                result_25_input = result_25.get('input_tokens', 0)
                result_25_output = result_25.get('output_tokens', 0)
                result_25_thought = result_25.get('thought_tokens', 0)
        else:
            result_25_input = result_25_output = result_25_thought = 0
        
        # ============================================================================
        # STAGE 3: SOLUTION (KEY IDEA + STEPS + SOLUTION)  —  Gemini Flash
        # ============================================================================
        s3_conf = get_stage_config('solution', pipeline_config)
        logger.info(f"📖 Stage 3: Solution | Provider: {s3_conf['provider']} | Model: {s3_conf['model']}")

        prompt_data_3 = build_solution_prompt(writer_data, math_core_data, questions, general_config, files)

        result_3 = await run_gemini_async(
            prompt=prompt_data_3.get('prompt', ''),
            api_key=gemini_api_key,
            files=prompt_data_3['files'],
            thinking_level=s3_conf['thinking_level'],
            model=s3_conf['model']
        )

        if save_prompts_dir:
            with open(save_prompts_dir / "stage3_solution_prompt.txt", "w", encoding="utf-8") as f:
                f.write(f"=== USER PROMPT ===\n{prompt_data_3.get('prompt', '')}")
            with open(save_prompts_dir / "stage3_solution_output.txt", "w", encoding="utf-8") as f:
                f.write(f"=== RAW OUTPUT ===\n{result_3['text']}")

        solution_data = extract_json_from_response(result_3['text'])
        if not solution_data:
            solution_data = {"questions": [], "raw_text": result_3['text']}
            logger.warning("⚠️ Stage 3 produced no JSON. Passing raw text.")

        logger.info("✅ Stage 3 Complete")
        
        # Merge solution data into writer data so validation has everything
        if isinstance(solution_data, dict):
            # Support both 'questions' and 'solutions' (legacy compat)
            sol_qs = solution_data.get('questions') or solution_data.get('solutions') or []
            
            if isinstance(writer_data, dict) and 'questions' in writer_data:
                wr_qs = writer_data['questions']
                
                # Create lookup by question_id or fallback to index matching
                sol_map = {sq.get('question_id', f"Q{i+1}"): sq for i, sq in enumerate(sol_qs)}
                
                for i, wq in enumerate(wr_qs):
                    q_id = wq.get('question_id', f"Q{i+1}")
                    sq = None
                    if q_id in sol_map:
                        sq = sol_map[q_id]
                    elif i < len(sol_qs):
                        sq = sol_qs[i]
                    
                    if sq:
                        if 'answer_key' in sq:
                            wq['answer_key'] = sq['answer_key']
                        if 'solution' in sq:
                            wq['solution'] = sq['solution']
                        if 'key_idea' in sq:
                            wq['key_idea'] = sq['key_idea']
                        if 'distractor_analysis' in sq:
                            wq['distractor_analysis'] = sq['distractor_analysis']

        # ============================================================================
        # EXTRACT CORE SKILL METADATA
        # ============================================================================
        used_topics = []
        if isinstance(math_core_data, dict):
            # 1. Try core_skill_metadata (if enabled)
            metadata = math_core_data.get('core_skill_metadata', {})
            used_topics = metadata.get('topics_used', [])
            
            # 2. Fallback to the top-level topic field from the new extraction structure
            if not used_topics:
                topic = math_core_data.get('topic')
                if topic:
                    used_topics = [topic]
            if not isinstance(used_topics, list):
                used_topics = []
        
        used_scenarios = []
        if isinstance(writer_data, dict) and 'core_skill_metadata' in writer_data:
            metadata = writer_data.get('core_skill_metadata', {})
            used_scenarios = metadata.get('scenarios_used', [])
            if not isinstance(used_scenarios, list):
                used_scenarios = []
                    
        core_skill_data = {
            "topics": used_topics,
            "scenarios": used_scenarios
        }

        # Token totals
        total_input  = (result_1.get('input_tokens',  0) +
                        result_2.get('input_tokens',  0) +
                        result_25_input +
                        result_3.get('input_tokens',  0))
        total_output = (result_1.get('output_tokens', 0) +
                        result_2.get('output_tokens', 0) +
                        result_25_output +
                        result_3.get('output_tokens', 0))
        total_thought = (result_1.get('thought_tokens', 0) +
                         result_2.get('thought_tokens', 0) +
                         result_25_thought +
                         result_3.get('thought_tokens', 0))
        
        final_output = {
            "math_core":       math_core_data,
            "writer_output":   writer_data,
            "solution_output": solution_data,
            "_pipeline_metadata": {
                "mode":   GENERATION_PIPELINE_MODE,
                "stages": 3,
                "total_tokens": {
                    "input":  total_input,
                    "output": total_output,
                    "thought": total_thought
                },
                "core_skill_data": core_skill_data
            }
        }
        
        return final_output

    except Exception as e:
        logger.error(f"❌ Pipeline Failed: {e}")
        raise e
