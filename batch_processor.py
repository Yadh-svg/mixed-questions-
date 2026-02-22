"""
Batch Processor for Parallel Question Generation
Groups questions by type and processes them in parallel batches.
"""

import asyncio
from typing import List, Dict, Any
from collections import defaultdict
import logging
import json
import time
from pathlib import Path

import os

from llm_engine import run_gemini_async, save_prompt, save_response
from prompt_builder import build_prompt_for_batch, get_files
from pipeline_builder import GENERATION_PIPELINE_MODE

# ... (imports)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 4

# Gemini 3 Flash Preview Pricing (per 1M tokens)
INPUT_PRICE_PER_1M = 0.50  # $0.50 per 1M input tokens
OUTPUT_PRICE_PER_1M = 3.00  # $3.00 per 1M output tokens (includes thought tokens)

def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """
    Calculate the cost of a Gemini API call based on token usage.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens (includes thought tokens)
    
    Returns:
        Total cost in USD
    """
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
    return input_cost + output_cost

def save_batch_metadata(metadata: Dict[str, Any], batch_key: str):
    """
    Save extracted metadata to a dedicated folder.
    """
    if not metadata:
        return
        
    try:
        log_dir = Path("metadata_logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_metadata_{batch_key.replace(' ', '_')}.txt"
        file_path = log_dir / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
            
        logger.info(f"Saved batch metadata to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save batch metadata: {e}")


def extract_first_json_match(text: str) -> Dict[str, Any]:
    """
    Robustly find the first valid JSON object in the text.
    Iterates through all '{' occurrences to handle cases where 
    LaTeX braces (e.g. \cancel{0}) appear before the actual JSON.
    """
    import json
    
    start_idx = -1
    while True:
        # Find next opening brace
        start_idx = text.find('{', start_idx + 1)
        if start_idx == -1:
            return None 
        
        # Try to parse JSON starting from this brace
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(text, idx=start_idx)
            # Basic validation: ensure it's a dict and not just a single value
            if isinstance(obj, dict):
                return obj
        except Exception:
            # Continue searching if this brace wasn't the start of invalid JSON
            continue
            
    return None

def extract_core_skill_metadata(response_text: str, expected_count: int = 0) -> Dict[str, Any]:
    """
    Extract the core skill JSON metadata from LLM response.
    Prioritizes ```json ... ``` blocks, then falls back to raw search.
    """
    import re
    import json
    
    metadata = None
    
    # 1. Try to find JSON code block first (Most reliable)
    code_block_pattern = r'```json\s*(\{.*?\})\s*```'
    match = re.search(code_block_pattern, response_text, re.DOTALL)
    if match:
        try:
            metadata = json.loads(match.group(1))
            logger.info("Extracted metadata from markdown code block.")
        except Exception as e:
            logger.warning(f"Found JSON code block but failed to parse: {e}")
            
    # 2. Fallback to robust raw search
    if not metadata:
        metadata = extract_first_json_match(response_text)
        if metadata:
            logger.info("Extracted metadata using raw search fallback.")
            
    if metadata:
        # Validate structure - check for 'batch_summary'
        if 'batch_summary' in metadata:
             clean_metadata = {}
             for k, v in metadata.items():
                 if isinstance(v, list):
                     clean_metadata[k] = ", ".join(str(x) for x in v)
                 else:
                     clean_metadata[k] = str(v)
             
             summary = clean_metadata.get('batch_summary', '')
             # Split by comma but handle potential numbered list "1. idea, 2. idea"
             items = [s.strip() for s in re.split(r',\s*(?=\d+\.|\w+)', summary) if s.strip()]
             actual_count = len(items)
             
             if expected_count > 0:
                 if actual_count == expected_count:
                     logger.info(f"Metadata verification PASSED: Found {actual_count} entries for {expected_count} questions.")
                 else:
                     logger.warning(f"Metadata verification FAILED: Found {actual_count} entries but expected {expected_count} (one per question).")
             else:
                 logger.info(f"Extracted cumulative batch_summary with approx {actual_count} entries")
                 
             return clean_metadata

    logger.warning("Could not extract batch_summary from response")
    return {}



def group_questions_by_type_and_topic(questions_config: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group questions by question type for batch processing using Priority Packing.
    
    Strategy:
    1. Group by Type.
    2. Within each Type, grouping by Topic.
    3. For each Topic, extract FULL BATCHES (size 4) immediately.
    4. Collect all remaining questions (remainders) into a pool.
    5. Pack the remainder pool into mixed batches of size 4.
    
    This ensures maximal topic coherence in batches to avoid duplication issues 
    while maintaining efficient batch sizes.
    """
    grouped_by_type = defaultdict(list)
    BATCH_SIZE = DEFAULT_BATCH_SIZE

    # 1. Initial Grouping by Type
    for idx, q_config in enumerate(questions_config):
        q_type = q_config.get('type', 'MCQ')
        q_config['original_index'] = idx
        grouped_by_type[q_type].append(q_config)
    
    final_grouped = {}

    for q_type, type_questions in grouped_by_type.items():
        # Smart Preservation Logic
        # Goal: Preserve original order unless we detect INEFFICIENT topic splitting.
        
        # 1. Analyze Input Batches (Hypothetical)
        needs_optimization = False
        topic_batch_map = defaultdict(list)
        
        # Simulate batch assignment based on current order
        for i, q in enumerate(type_questions):
            current_batch_idx = i // BATCH_SIZE
            raw_topic = q.get('topic', '') or 'Unknown'
            # Enhanced normalization: lower, strip, and collapse internal spaces
            topic_key = " ".join(str(raw_topic).strip().lower().split())
            topic_batch_map[topic_key].append(current_batch_idx)

        # 2. Check for inefficiency
        for topic, batch_indices in topic_batch_map.items():
            # If topic appears in only one batch -> Efficient.
            unique_batches = sorted(list(set(batch_indices)))
            if len(unique_batches) <= 1:
                continue
            
            # If topic spans multiple batches, check usage.
            # It is EFFICIENT if all earlier batches are saturated with this topic?
            # Or simpler: It is INEFFICIENT if a topic is split across batches 
            # where the earlier batch had < BATCH_SIZE questions of that topic?
            # NO, earlier batch might be full of OTHER topics.
            
            # Definition: INEFFICIENT if we have multiple partial chunks of the same topic 
            # that COULD be combined into a fuller chunk.
            # Example Bad: Batch 1 has 2 'A', Batch 2 has 2 'A'. (Total 4 'A').
            # We could have put 4 'A' in one batch.
            
            # We check if the topic count in any batch is partial (< 4) AND there are more of that topic elsewhere.
            # Actually, "Priority Packing" puts 4s together.
            # So if we see a topic with total count >= 4, but it never forms a chunk of 4 in input -> INEFFICIENT.
            # Or if total count < 4, but it is split (e.g. 1 in B1, 1 in B2) -> Inefficient.
            
            total_count = len(batch_indices)
            
            # Check consistency
            # Count occurrences per batch
            counts_per_batch = defaultdict(int)
            for b_idx in batch_indices:
                counts_per_batch[b_idx] += 1
                
            # If any batch has a partial amount (< BATCH_SIZE) AND we have other batches with this topic,
            # could we have done better?
            # Yes, we could have combined them.
            # Exception: If the split is necessary because we have too many (e.g. 6 items -> 4 + 2).
            # In that case, one batch MUST have 4.
            # So if we have NO batch with 4 items for this topic, but we have multiple batches -> Could be potentially optimized?
            # Wait, if total=6, and we have 3 in B1, 3 in B2 -> Inefficient (should be 4, 2).
            
            # Rule: Reorder if we find a topic that is split across batches AND doesn't have a max-capacity chunk (4) where possible.
            has_full_chunk = any(c == BATCH_SIZE for c in counts_per_batch.values())
            
            if total_count >= BATCH_SIZE and not has_full_chunk:
                needs_optimization = True
                logger.info(f"[{q_type}] Optimization needed: Topic '{topic}' (Count {total_count}) fragmented inefficiently across batches {dict(counts_per_batch)}")
                break
                
            # Also handle small fragmentation: 2 in B1, 2 in B2 (Total 4).
            # total_count=4. has_full_chunk=False. -> True. Correct.
            
            # What about Total=2? 1 in B1, 1 in B2.
            # total_count=2. < BATCH_SIZE.
            # Is 1+1 inefficient? Yes, we want 2 together.
            # So if total < BATCH_SIZE and len(unique_batches) > 1 -> Inefficient.
            if total_count < BATCH_SIZE and len(unique_batches) > 1:
                needs_optimization = True
                logger.info(f"[{q_type}] Optimization needed: Topic '{topic}' (Count {total_count}) fragmented across batches {unique_batches}")
                break

        # Check if ANY question has the _preserve_order flag (used during regeneration)
        preserve_order = any(q.get('_preserve_order', False) for q in type_questions)
        
        if preserve_order:
            logger.info(f"  - {q_type}: {len(type_questions)} questions (Preserving Original Order - Regeneration Mode)")
            final_grouped[q_type] = type_questions
            continue
        
        if not needs_optimization:
            logger.info(f"  - {q_type}: {len(type_questions)} questions (Preserved User Order - Efficient)")
            final_grouped[q_type] = type_questions
            continue

        logger.info(f"  - {q_type}: Reordering for efficiency (Priority Packing applied)")
        
        # 3. Priority Packing (Original Logic)
        topic_map = defaultdict(list)
        for q in type_questions:
            # Normalize topic: lowercase, strip, collapse spaces. Handle None.
            raw_topic = q.get('topic', '') or 'Unknown'
            topic_key = " ".join(str(raw_topic).strip().lower().split())
            topic_map[topic_key].append(q)
            
        final_list_for_type = []
        remainder_pool = []
        
        # 3. Extract Full Batches
        # Sort topics to ensure deterministic order? Yes.
        sorted_topics = sorted(topic_map.keys())
        
        for topic in sorted_topics:
            questions = topic_map[topic]
            
            # While we have enough for a full batch
            while len(questions) >= BATCH_SIZE:
                # Take chunk
                chunk = questions[:BATCH_SIZE]
                questions = questions[BATCH_SIZE:] # Remove processed
                
                # Add to final list
                final_list_for_type.extend(chunk)
            
            # Add remaining to pool
            remainder_pool.extend(questions)
            
        # 4. Pack Remainder Pool
        # We process the pool in chunks of BATCH_SIZE
        # The pool contains questions from different topics (or same if fragmented)
        # We just slice it up.
        
        chunks = [remainder_pool[i:i + BATCH_SIZE] for i in range(0, len(remainder_pool), BATCH_SIZE)]
        for chunk in chunks:
            final_list_for_type.extend(chunk)
            
        final_grouped[q_type] = final_list_for_type
        
        logger.info(f"  - {q_type}: {len(final_list_for_type)} questions (Packed by Topic)")

    logger.info(f"Grouped {len(questions_config)} questions into {len(final_grouped)} types with Priority Packing.")
    
    return final_grouped



async def generate_raw_batch(
    batch_key: str,
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    type_config: Dict[str, Any] = None,
    previous_batch_metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Generate raw questions for a single batch (Stage 1).
    """
    logger.info(f"Generating RAW batch: {batch_key} ({len(questions)} questions)")
    
    # Load pipeline config to get model
    from pipeline_executor import load_pipeline_config, get_stage_config
    pipeline_conf = load_pipeline_config()
    # For raw generation in legacy mode, we can use 'math_core' or 'writer' model. 
    # 'writer' seems appropriate for question generation.
    stage_conf = get_stage_config('writer', pipeline_conf)
    model_name = stage_conf['model']
    
    try:
        # Build the prompt for this batch
        # Extract base type key (remove " - Batch X" suffix) for template lookup
        base_key = batch_key.split(' - Batch ')[0]
        prompt_data = build_prompt_for_batch(base_key, questions, general_config, type_config, previous_batch_metadata)
        
        prompt_text = prompt_data['prompt']
        
        # Determine if this is a regeneration batch
        is_regeneration = any(q.get('_is_being_regenerated') for q in questions)
        prompt_type = "regeneration" if is_regeneration else "generation"
        
        # Save prompt for debugging/record
        # save_prompt(prompt_text, prompt_type, batch_key)

        files = prompt_data.get('files', [])
        file_metadata = prompt_data.get('file_metadata', {})
        api_key = general_config['api_key']
        
        # Call Gemini API for generation
        result = await run_gemini_async(
            prompt=prompt_text,
            api_key=api_key,
            files=files,
            thinking_level="high",
            file_metadata=file_metadata,
            model=model_name
        )

        # Save raw response for debugging/record
        # if 'text' in result and result['text']:
        #     save_response(result['text'], prompt_type, batch_key)
        
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
    
    # Load pipeline config to get model for validation
    from pipeline_executor import load_pipeline_config, get_stage_config
    pipeline_conf = load_pipeline_config()
    # Use 'analysis' or 'solution' model for validation
    stage_conf = get_stage_config('analysis', pipeline_conf)
    model_name = stage_conf['model']

    try:
        api_key = general_config['api_key']
        
        # Save validation prompt for debugging/record
        # save_prompt(validation_prompt_text, "validation", batch_key)
        
        # Call Gemini API for validation with files if available
        result = await run_gemini_async(
            prompt=validation_prompt_text,
            api_key=api_key,
            files=files,
            thinking_level=stage_conf.get('thinking_level'),
            file_metadata=file_metadata,
            model=model_name
        )
        
        # Save validation response for debugging/record
        # if 'text' in result and result['text']:
        #     save_response(result['text'], "validation", batch_key)
        
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
    general_config: Dict[str, Any],
    progress_callback=None
) -> Dict[str, Dict[str, Any]]:
    """
    Process questions in a BATCHED SEQUENTIAL pipeline:
    1. Split questions into batches of 5 for each type.
    2. Process batches of the SAME type SEQUENTIALLY (Batch 1 -> Batch 2).
    3. Process different question types in PARALLEL.
    
    Architecture:
    ┌─ MCQ Task ───────────────────────────────────┐
    │  [Batch 1 Gen -> Val] → [Batch 2 Gen -> Val] │
    └──────────────────────────────────────────────┘
    ┌─ FIB Task ───────────────────────────────────┐
    │  [Batch 1 Gen -> Val] → [Batch 2 Gen -> Val] │
    └──────────────────────────────────────────────┘
    
    Returns:
        Flattened dictionary of results, e.g.:
        {
            "MCQ - Batch 1": {...},
            "MCQ - Batch 2": {...},
            "FIB - Batch 1": {...}
        }
    """
    logger.info(f"Starting batched pipeline processing for {len(questions_config)} questions")
    
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
                with open('validation.yaml', 'r', encoding='utf-8') as f:
                    validation_prompt_template = f.read()

    except Exception as e:
        logger.error(f"Failed to load validation.yaml: {e}")
        return {'error': "Critical: validation.yaml not found"}

    pipeline_results = {}
    
def split_generated_content(text: str) -> Dict[str, str]:
    """
    Split the raw generated markdown into individual question blocks using the explicit delimiter.
    Delimiter: |||QUESTION_START|||
    """
    questions = {}
    
    # Check if delimiter exists
    if "|||QUESTION_START|||" not in text:
        logger.warning("Explicit delimiter '|||QUESTION_START|||' not found. Attempting fallback split by regex patterns.")
        
        # Fallback: Multi-pattern split
        # Matches:
        # 1. **Question [1]** or **Question 1**
        # 2. QUESTION 1 or Question 1:
        # 3. **Question 1:**
        import re
        # Pattern captures the index (Group 1)
        # We look for "Question" followed by optional space/bracket, digits, optional closing bracket/colon/bold chars
        # Examples: "**Question 1**", "Question [1]", "QUESTION 1"
        pattern = r'(?:\*\*|#|\n|^)?\s*(?:Question|QUESTION)\s*(?:\[)?(\d+)(?:\])?\s*(?:\*\*|:)?'
        
        # We use re.split capturing group 1 (the number)
        # Note: This might be too aggressive if "Question 1" appears in the text.
        # We try to anchor it or rely on markdown header syntax like ** or # if possible, but user said "QUESTION 1" is possible.
        # Let's try a robust pattern that requires newline before or is a clear header.
        
        # Revised Pattern:
        # (Newline or Start) + (Optional **) + Question/QUESTION + (Optional space) + [N] or N + (Optional ] or : or **)
        pattern = r'(?:\n|^)\s*(?:\*\*)?\s*(?:Question|QUESTION)\s*(?:\[)?\s*(\d+)\s*(?:\])?\s*(?:\*\*|:)?'
        
        parts = re.split(pattern, text)
        
        if len(parts) >= 2:
             questions = {}
             # parts[0] is preamble.
             # Loop: parts[1]=num, parts[2]=content, parts[3]=num...
             for i in range(1, len(parts), 2):
                q_num = parts[i]
                content = parts[i+1]
                # Reconstruct header for clarity (always use standard format for internal use)
                full_content = f"**Question [{q_num}]**\n{content}"
                key = f"question{q_num}"
                questions[key] = full_content.strip()
             
             logger.info(f"Fallback split found {len(questions)} items using regex.")
             return questions
        
        logger.warning("Fallback split also failed. returning full text.")
        return {"question1": text}
    
    # Split by delimiter
    # The first part might be preamble/plan
    parts = text.split("|||QUESTION_START|||")
    
    # Skip preamble (part 0)
    # But check if part 0 contains a question? Usually preamble is first.
    # If the output starts immediately with delimiter, part 0 is empty.
    
    q_index = 1
    start_index = 1
    
    # If the text starts with the delimiter, part 0 is empty string.
    if text.strip().startswith("|||QUESTION_START|||"):
        start_index = 1 # part 0 is empty
    elif len(parts) > 1:
        # Preamble exists
        start_index = 1
    else:
        # Should not happen based on 'if' check above
        start_index = 0

    for i in range(start_index, len(parts)):
        content = parts[i].strip()
        if not content: continue
        
        # Strip potential JSON metadata from the end of the last question
        if i == len(parts) - 1:
            # Look for JSON block at the end
            import re
            content = re.sub(r'```json\s*\{.*?\s*\}\s*```', '', content, flags=re.DOTALL).strip()
            # Also catch JSON if not wrapped in code blocks
            if content.endswith('}'):
                # Try to find the last occurrence of '{' and see if it's a JSON block
                last_brace = content.rfind('{')
                if last_brace != -1:
                    potential_json = content[last_brace:]
                    if extract_first_json_match(potential_json):
                        content = content[:last_brace].strip()

        key = f"question{q_index}"
        questions[key] = content
        q_index += 1
        
    logger.info(f"Split generated content into {len(questions)} items: {list(questions.keys())}")
    return questions


async def process_single_batch_flow(
    batch_key: str,
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    type_config: Dict[str, Any] = None,
    validation_prompt_template: Any = "",
    progress_callback=None,
    previous_batch_metadata: Dict[str, Any] = None,
    skip_validation: bool = False
) -> Dict[str, Any]:
    """
    Process a SINGLE batch through the full Generation -> Split -> Batched Validation flow.
    If skip_validation=True (for regeneration), validation is bypassed and generation output is used directly.
    
    NEW: If GENERATION_PIPELINE_MODE is enabled, uses the 4-stage pipeline instead.
    """
    from pipeline_executor import run_stage_pipeline
    from prompt_builder import get_files
    
    logger.info(f"[{batch_key}] Starting Batched Flow (Pipeline Mode: {GENERATION_PIPELINE_MODE})")
    
    # Check if pipeline mode is enabled
    if GENERATION_PIPELINE_MODE in ["SCENARIO_FIRST", "MATH_FIRST"]:
        # ============================================================================
        # NEW PIPELINE MODE: Run 4-stage pipeline
        # ============================================================================
        logger.info(f"[{batch_key}] Using 4-stage pipeline (Scenario → Question → Solution → Analysis)")
        
        try:
            # Get files for this batch (PDF/images)
            files_data = get_files(questions, general_config)
            files = files_data.get('files', [])  # Extract the actual file list
            
            # Create directory for saving prompts
            from pathlib import Path
            prompts_dir = Path("pipeline_outputs") / batch_key.replace(" - ", "_").replace(" ", "_")
            prompts_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"💾 Created prompts directory: {prompts_dir}")
            
            # Run the full 4-stage pipeline with prompt saving
            pipeline_result = await run_stage_pipeline(
                questions, 
                general_config, 
                files,
                save_prompts_dir=prompts_dir,
                previous_batch_metadata=previous_batch_metadata
            )
            
            # Format pipeline output for compatibility with existing system
            # The pipeline returns: {scenario, question, solution, analysis, _pipeline_metadata}
            # We need to convert this to match the expected format
            
            pipeline_payload = {
                'raw': {
                    'text': json.dumps(pipeline_result, indent=2),
                    'elapsed': 0,  # Time tracked within pipeline
                    'batch_key': batch_key,
                    'input_tokens': pipeline_result['_pipeline_metadata']['total_tokens']['input'],
                    'output_tokens': pipeline_result['_pipeline_metadata']['total_tokens']['output'],
                    'thought_tokens': 0,
                    'billed_output_tokens': pipeline_result['_pipeline_metadata']['total_tokens']['output']
                },
                'validated': {
                    'text': json.dumps(pipeline_result, indent=2),
                    'elapsed': 0,
                    'batch_key': batch_key,
                    'input_tokens': 0,
                    'output_tokens': 0
                },
                'core_skill_metadata': pipeline_result['_pipeline_metadata'].get('core_skill_data', {}),
                '_pipeline_output': pipeline_result,  # Store full pipeline structure
                '_prompts_dir': str(prompts_dir)  # Store prompts directory path
            }
            
            # Save detailed batch output for debugging/analysis
            try:
                output_dir = Path("batch_outputs")
                output_dir.mkdir(exist_ok=True)
                clean_key = batch_key.replace(" ", "_").replace("-", "_")
                output_file = output_dir / f"{clean_key}_full_output.json"
                
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(pipeline_payload, f, indent=2)
                logger.info(f"Saved full batch output to {output_file}")
            except Exception as e:
                logger.error(f"Failed to save full batch output: {e}")

            # Use the extracted metadata for the return value
            return {batch_key: pipeline_payload, '_metadata': pipeline_payload['core_skill_metadata']}
            
            if progress_callback:
                progress_callback(batch_key, pipeline_payload)
            
            return {batch_key: pipeline_payload}
            
        except Exception as e:
            logger.error(f"[{batch_key}] Pipeline failed: {e}")
            error_payload = {
                'raw': {'error': str(e), 'text': '', 'elapsed': 0, 'batch_key': batch_key},
                'validated': {'error': 'Pipeline failed', 'text': '', 'elapsed': 0, 'batch_key': batch_key},
                'core_skill_metadata': {}
            }
            if progress_callback:
                progress_callback(batch_key, error_payload)
            return {batch_key: error_payload}
    
    # ============================================================================
    # LEGACY MODE: Original generation-validation flow
    # ============================================================================
    logger.info(f"[{batch_key}] Using legacy generation-validation flow")
    
    # --- STAGE 1: GENERATION ---
    raw_result = await generate_raw_batch(batch_key, questions, general_config, type_config, previous_batch_metadata)
    
    # Extract core skill metadata if enabled
    core_skill_metadata = {}
    if general_config.get('core_skill_enabled', False) and not raw_result.get('error'):
        # Pass number of questions to verify 1:1 mapping
        core_skill_metadata = extract_core_skill_metadata(raw_result.get('text', ''), expected_count=len(questions))
        if core_skill_metadata:
            # Standardize count log
            summary = core_skill_metadata.get('batch_summary', '')
            import re
            count = len([s for s in re.split(r',\s*(?=\d+\.|\w+)', summary) if s.strip()])
            logger.info(f"[{batch_key}] Extracted core skill metadata with {count} items.")
            # Save metadata to separate folder
            # save_batch_metadata(core_skill_metadata, batch_key)
    
    if raw_result.get('error'):
        logger.warning(f"[{batch_key}] Generation failed. Skipping validation.")
        result_payload = {
            'raw': raw_result,
            'validated': {'error': 'Skipped due to generation failure', 'text': ''},
            'core_skill_metadata': core_skill_metadata
        }
        if progress_callback: progress_callback(batch_key, result_payload)
        return {batch_key: result_payload, '_metadata': core_skill_metadata}

    # --- STAGE 2: SPLIT ---
    split_questions = split_generated_content(raw_result['text'])

    # --- STAGE 3: BATCHED VALIDATION (or skip for regeneration) ---
    validated_payload = {}
    
    if skip_validation:
        # For regeneration: Skip validation and use generation output directly
        logger.info(f"[{batch_key}] Skipping validation (regeneration mode). Using generation output directly.")
        
        # Convert split_questions dict directly to JSON format for rendering
        validated_payload = {
            'text': json.dumps(split_questions),
            'elapsed': 0,
            'batch_key': batch_key,
            'input_tokens': 0,
            'output_tokens': 0,
            'thought_tokens': 0,
            'billed_output_tokens': 0
        }
    else:
        # Normal flow: Run validation
        logger.info(f"[{batch_key}] Validating {len(split_questions)} items in ONE HIT.")
        
        # 1. Prepare combined content with clear labels
        combined_questions_text = ""
        for q_key, q_text in split_questions.items():
            q_label = q_key.upper() # "QUESTION1", "QUESTION2", ...
            combined_questions_text += f"\n\n### {q_label}\n{q_text}\n"

        # 2. Prepare combined context for all questions
        context_lines = []
        for i, q_config in enumerate(questions):
            q_label = f"QUESTION{i+1}"
            topic_str = q_config.get('topic', 'Unknown')
            q_notes = q_config.get('additional_notes_text', '')
            # Specifier
            spec = q_config.get('mcq_type') or q_config.get('fib_type') or q_config.get('descriptive_type') or "Standard"
            
            ctx = f"- {q_label}: Topic='{topic_str}', Type='{spec}'"
            if q_notes: ctx += f", Notes='{q_notes}'"
            context_lines.append(ctx)
        
        combined_context = "\n".join(context_lines)
        
        # 3. Get structure format rule from config
        base_type_key = batch_key.split(' - Batch ')[0]
        structure_map = {
            "MCQ": "structure_MCQ",
            "Fill in the Blanks": "structure_FIB",
            "Case Study": "structure_Case_Study",
            "Multi-Part": "structure_Multi_Part",
            "Assertion-Reasoning": "structure_AR",
            "Descriptive": "structure_Descriptive",
            "Descriptive w/ Subquestions": "structure_Descriptive_w_subq"
        }
        struct_rule_key = structure_map.get(base_type_key)
        
        # Handle validation_config passing
        if isinstance(validation_prompt_template, dict):
            validation_config = validation_prompt_template
            prompt_template = validation_config.get('validation_prompt', '')
        else:
            # Fallback if only template string was passed
            prompt_template = validation_prompt_template
            validation_config = {}

        structure_format = validation_config.get(struct_rule_key, "Return a valid JSON object.")
        
        # 4. Construct Batched Validation Prompt
        val_prompt = prompt_template.replace("{{GENERATED_CONTENT}}", combined_questions_text)
        val_prompt = val_prompt.replace("{{INPUT_CONTEXT}}", combined_context)
        val_prompt = val_prompt.replace("{{OUTPUT_FORMAT_RULES}}", structure_format)
        
        # 5. Call API for the whole batch
        val_files = [] 
        val_file_metadata = {'source_type': 'None (Validation)', 'filenames': []}
        
        try:
            v_res = await validate_batch(batch_key, val_prompt, general_config, val_files, val_file_metadata)
            logger.info(f"[{batch_key}] Batched validation finished. Time: {v_res.get('elapsed', 0):.2f}s")
            
            # --- STAGE 4: AGGREGATE & PARSE ---
            raw_val_text = v_res.get('text', '')
            
            # Robust extraction of the JSON object containing results
            data = extract_first_json_match(raw_val_text)
            
            if data:
                validated_payload = {
                    'text': json.dumps(data),
                    'elapsed': v_res.get('elapsed', 0),
                    'batch_key': batch_key,
                    'input_tokens': v_res.get('input_tokens', 0),
                    'output_tokens': v_res.get('output_tokens', 0),
                    'thought_tokens': v_res.get('thought_tokens', 0),
                    'billed_output_tokens': v_res.get('billed_output_tokens', 0)
                }
            else:
                logger.warning(f"[{batch_key}] Failed to parse batched validation response as JSON.")
                validated_payload = {
                    'text': raw_val_text,
                    'error': 'Failed to parse JSON',
                    'elapsed': v_res.get('elapsed', 0),
                    'batch_key': batch_key,
                    'input_tokens': v_res.get('input_tokens', 0),
                    'output_tokens': v_res.get('output_tokens', 0),
                    'thought_tokens': v_res.get('thought_tokens', 0),
                    'billed_output_tokens': v_res.get('billed_output_tokens', 0)
                }
                
        except Exception as e:
            logger.error(f"[{batch_key}] Batched validation failed: {e}")
            validated_payload = {'error': str(e), 'text': '', 'elapsed': 0}

    # --- STAGE 5: COST CALCULATION ---
    # Calculate costs for Generation and Validation
    gen_cost = calculate_cost(raw_result.get('input_tokens', 0), raw_result.get('billed_output_tokens', 0))
    val_cost = calculate_cost(validated_payload.get('input_tokens', 0), validated_payload.get('billed_output_tokens', 0))
    batch_total_cost = gen_cost + val_cost
    
    # Attach costs to result
    raw_result['cost'] = gen_cost
    validated_payload['cost'] = val_cost
    
    result_payload = {
        'raw': raw_result,
        'validated': validated_payload,
        'core_skill_metadata': core_skill_metadata,
        'batch_cost': batch_total_cost
    }
    
    if progress_callback: progress_callback(batch_key, result_payload)
    return {batch_key: result_payload, '_metadata': core_skill_metadata}


async def process_batches_pipeline(
    questions_config: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    progress_callback=None,
    skip_validation: bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    Process ALL batches. Uses PARALLEL flows by default, or SEQUENTIAL per-type
    when core_skill_enabled is True (to pass metadata between batches).
    If skip_validation=True, skips validation step (used for regeneration).
    """
    core_skill_enabled = general_config.get('core_skill_enabled', False)
    mode = "SEQUENTIAL (Core Skill)" if core_skill_enabled else "PARALLEL"
    logger.info(f"Starting {mode} pipeline for {len(questions_config)} questions")
    
    # Group questions by type
    grouped_questions = group_questions_by_type_and_topic(questions_config)
    
    # Load validation template
    try:
        import yaml
        with open('validation.yaml', 'r', encoding='utf-8') as f:
            validation_config = yaml.safe_load(f)
            # Pass the WHOLE config to flow handler
            validation_resource = validation_config
    except Exception as e:
        logger.error(f"Failed to load validation.yaml: {e}")
        return {'error': "Critical: validation.yaml not found"}

    pipeline_results = {}
    total_cost = 0.0
    
    if core_skill_enabled:
        # SEQUENTIAL PROCESSING: Process each type's batches sequentially to pass metadata
        logger.info("🔧 Core Skill enabled: Processing batches SEQUENTIALLY per type")
        
        for base_type_key, all_type_questions in grouped_questions.items():
            BATCH_SIZE = DEFAULT_BATCH_SIZE
            batches = [all_type_questions[i:i + BATCH_SIZE] for i in range(0, len(all_type_questions), BATCH_SIZE)]
            
            # Accumulated metadata for this type
            accumulated_metadata = {}
            
            for i, batch_questions in enumerate(batches):
                batch_key = f"{base_type_key} - Batch {i + 1}"
                
                t_count = len(accumulated_metadata.get('topics', []))
                s_count = len(accumulated_metadata.get('scenarios', []))
                logger.info(f"[Core Skill] Processing {batch_key} with prior knowledge: {t_count} topics, {s_count} scenarios")
                
                # Process this batch with previous metadata
                result = await process_single_batch_flow(
                    batch_key=batch_key,
                    questions=batch_questions,
                    general_config=general_config,
                    type_config=None,
                    validation_prompt_template=validation_resource,
                    progress_callback=progress_callback,
                    previous_batch_metadata=accumulated_metadata if accumulated_metadata else None,
                    skip_validation=skip_validation
                )
                
                # Extract metadata from result
                # LOGIC UPDATE: We now accumulate metadata in Python, 
                # instead of expecting the LLM to pass back the full list.
                batch_metadata = result.pop('_metadata', {})
                if batch_metadata:
                    # Initialize if empty
                    if not accumulated_metadata:
                        accumulated_metadata = batch_metadata.copy()
                        topic_count = len(accumulated_metadata.get('topics', []))
                        logger.info(f"[Core Skill] Initialized metadata with {topic_count} topics")
                    else:
                        # Append new values
                        for key, new_val in batch_metadata.items():
                            if key in accumulated_metadata:
                                current_val = accumulated_metadata[key]
                                
                                # Handle List accumulation (New Core Skill)
                                if isinstance(current_val, list) and isinstance(new_val, list):
                                    # Extend list with new items
                                    accumulated_metadata[key] = current_val + new_val
                                    
                                # Handle String accumulation (Legacy)
                                elif isinstance(current_val, str) and isinstance(new_val, str):
                                    if new_val.strip():
                                        accumulated_metadata[key] = f"{current_val}, {new_val}"
                            else:
                                # New key, just add it
                                accumulated_metadata[key] = new_val
                                
                        # Log summary stats
                        topic_count = len(accumulated_metadata.get('topics', []))
                        scenario_count = len(accumulated_metadata.get('scenarios', []))
                        logger.info(f"[Core Skill] Updated cumulative metadata. Usage: {topic_count} topics, {scenario_count} scenarios.")
                
                # Add batch results to pipeline results
                total_cost += result[batch_key].get('batch_cost', 0.0)
                pipeline_results.update(result)
    else:
        # PARALLEL PROCESSING: Original behavior
        all_batch_tasks = []
        
        for base_type_key, all_type_questions in grouped_questions.items():
            BATCH_SIZE = DEFAULT_BATCH_SIZE
            batches = [all_type_questions[i:i + BATCH_SIZE] for i in range(0, len(all_type_questions), BATCH_SIZE)]
            
            for i, batch_questions in enumerate(batches):
                batch_key = f"{base_type_key} - Batch {i + 1}"
                
                # Create a task for this batch
                task = process_single_batch_flow(
                    batch_key=batch_key,
                    questions=batch_questions,
                    general_config=general_config,
                    type_config=None,
                    validation_prompt_template=validation_resource,
                    progress_callback=progress_callback,
                    previous_batch_metadata=None,
                    skip_validation=skip_validation
                )
                all_batch_tasks.append(task)
                
        logger.info(f"🚀 Launching {len(all_batch_tasks)} batch flows in PARALLEL")
        
        # Run everything
        all_results_list = await asyncio.gather(*all_batch_tasks, return_exceptions=True)
        
        # Aggregate results
        for res in all_results_list:
            if isinstance(res, dict):
                # Remove internal _metadata key before adding to results
                res.pop('_metadata', None)
                # Aggregate cost from first key (should only be one batch key in res)
                for b_key, b_val in res.items():
                    total_cost += b_val.get('batch_cost', 0.0)
                pipeline_results.update(res)
            elif isinstance(res, Exception):
                logger.error(f"Batch flow failed: {res}")
            
    logger.info(f"Pipeline processing completed. Total Cost: ${total_cost:.4f}")
    pipeline_results['_total_cost'] = total_cost
    return pipeline_results


async def regenerate_specific_questions_pipeline(
    original_config: List[Dict[str, Any]],
    regeneration_map: Dict[str, List[int]],
    general_config: Dict[str, Any],
    progress_callback=None
) -> Dict[str, Dict[str, Any]]:
    """
    Regenerate SPECIFIC questions based on their original configuration.
    Wraps the standard batched pipeline for a subset of questions.
    """
    logger.info(f"Regenerating specific questions: {regeneration_map}")
    
    # 1. Filter the configuration to ONLY the selected questions
    filtered_config = []
    
    # 1. Group the original configuration using the SAME logic as the main pipeline
    # This ensures that reordering (Priority Packing) is accounted for
    grouped_questions_map = group_questions_by_type_and_topic(original_config)
    
    for q_type, indices in regeneration_map.items():
        # q_type is the full batch key, e.g., "MCQ - Batch 1"
        # Extract base type (e.g., "MCQ")
        base_type = q_type.split(' - Batch ')[0]
        
        if base_type not in grouped_questions_map:
            logger.warning(f"Type {base_type} (from {q_type}) not found in grouped map")
            continue
            
        questions_of_type = grouped_questions_map[base_type]
        
        # Parse batch number from key
        batch_num = 1
        if ' - Batch ' in q_type:
            try:
                batch_num = int(q_type.split(' - Batch ')[1])
            except:
                batch_num = 1
        
        # Calculate offset within the grouped list for this type
        BATCH_SIZE = DEFAULT_BATCH_SIZE
        offset = (batch_num - 1) * BATCH_SIZE
        
        for idx in indices:
            # idx is 1-based index within the batch prompt result
            # Target index in the global list for this type after Priority Packing
            target_global_idx = offset + (idx - 1)
            
            if 0 <= target_global_idx < len(questions_of_type):
                q_config = questions_of_type[target_global_idx]
                q_config['_is_being_regenerated'] = True
                q_config['_preserve_order'] = True  # CRITICAL: Prevent topic sorting!
                
                # Attach original text if available
                existing_content_map = general_config.get('existing_content_map', {})
                if q_type in existing_content_map:
                    q_key = f"question{idx}"
                    original_text = existing_content_map[q_type].get(q_key, "")
                    if original_text:
                        q_config['original_text'] = original_text
                        logger.info(f"Attached original text for regeneration of {q_type} {q_key}")
                
                # Attach per-question regeneration reason if available
                regeneration_reasons_map = general_config.get('regeneration_reasons_map', {})
                question_identifier = f"{q_type}:{idx}"
                reason = regeneration_reasons_map.get(question_identifier, "")
                if reason:
                    q_config['regeneration_reason'] = reason
                    logger.info(f"Attached regeneration reason for {question_identifier}: {reason[:50]}...")
                
                q_config_copy = q_config.copy()
                q_config_copy['type'] = q_type # Keep the specific batch key for return tracking
                filtered_config.append(q_config_copy)
            else:
                logger.warning(f"Index {idx} out of bounds for {q_type} (Global idx {target_global_idx})")

    if not filtered_config:
        return {'error': "No valid questions selected for regeneration"}

    logger.info(f"Starting regeneration pipeline for {len(filtered_config)} questions...")
    results = await process_batches_pipeline(filtered_config, general_config, progress_callback, skip_validation=True)
    
    # POST-PROCESS RESULTS TO FIX KEYS
    # Results will have keys like "MCQ - Batch 2 - Batch 1".
    # We want "MCQ - Batch 2".
    fixed_results = {}
    for k, v in results.items():
        # Remove ONLY the LAST " - Batch 1" suffix added by the regeneration pipeline
        # Use rsplit to split from the right and only remove the last occurrence
        if ' - Batch 1' in k:
            # Split from right, max 1 split, then rejoin
            # "MCQ - Batch 1 - Batch 1" -> splits to ["MCQ - Batch 1", ""] -> "MCQ - Batch 1"
            # "MCQ - Batch 1" -> splits to ["MCQ", ""] -> "MCQ" (wrong!)
            # Better: Use rsplit with maxsplit and count occurrences
            parts = k.rsplit(' - Batch 1', 1)
            if len(parts) == 2:
                # Successfully split, use the left part
                original_key = parts[0]
            else:
                # Couldn't split (shouldn't happen), keep original
                original_key = k
            fixed_results[original_key] = v
        else:
            fixed_results[k] = v
            
    logger.info(f"Post-processed regeneration results keys: {list(results.keys())} -> {list(fixed_results.keys())}")
    return fixed_results
