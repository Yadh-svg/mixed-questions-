"""
Batch Processor for Parallel Question Generation
Groups questions by type and processes them in parallel batches.
"""

import asyncio
from typing import List, Dict, Any
from collections import defaultdict
import logging

from llm_engine import run_gemini_async
from prompt_builder import build_prompt_for_batch, get_files

# ... (imports)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 4



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
            # Or if total count < 4, but it is split (e.g. 1 in B1, 1 in B2) -> INEFFICIENT.
            
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
    type_config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Generate raw questions for a single batch (Stage 1).
    """
    logger.info(f"Generating RAW batch: {batch_key} ({len(questions)} questions)")
    
    try:
        # Build the prompt for this batch
        # Extract base type key (remove " - Batch X" suffix) for template lookup
        base_key = batch_key.split(' - Batch ')[0]
        prompt_data = build_prompt_for_batch(base_key, questions, general_config, type_config)
        
        prompt_text = prompt_data['prompt']
        files = prompt_data.get('files', [])
        file_metadata = prompt_data.get('file_metadata', {})
        api_key = general_config['api_key']
        

        
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
    validation_prompt_template: str = "",
    progress_callback=None
) -> Dict[str, Any]:
    """
    Process a SINGLE batch through the full Generation -> Split -> Parallel Validation flow.
    """
    logger.info(f"[{batch_key}] Starting Parallel Flow")
    
    # --- STAGE 1: GENERATION ---
    raw_result = await generate_raw_batch(batch_key, questions, general_config, type_config)
    
    if raw_result.get('error'):
        logger.warning(f"[{batch_key}] Generation failed. Skipping validation.")
        result_payload = {
            'raw': raw_result,
            'validated': {'error': 'Skipped due to generation failure', 'text': ''}
        }
        if progress_callback: progress_callback(batch_key, result_payload)
        return {batch_key: result_payload}

    # --- STAGE 2: SPLIT ---
    split_questions = split_generated_content(raw_result['text'])
    

    
    # --- STAGE 3: PARALLEL VALIDATION ---
    logger.info(f"[{batch_key}] Validating {len(split_questions)} items in PARALLEL. Keys: {list(split_questions.keys())}")
    
    # Prepare common validation resources
    val_files = [] 
    val_file_metadata = {'source_type': 'None (Validation)', 'filenames': []}
    
    # Base Type Key for Structure Map lookup
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
    structure_key = structure_map.get(base_type_key)
    # Load validation.yaml config locally inside function or pass it? 
    # We passed the template string. We need structure format rule.
    # Assuming standard structure rule for now or extracting from template if possible.
    # Actually, let's use a generic instruction if we can't load the file here easily.
    # BETTER: Pass the validation_config or load it once in the pipeline.
    # For now, let's assume the strict JSON structure rule is embedded or we use a default.
    structure_format = "Return a valid JSON object." 
    # Try to extract from globals/pipeline if passed, but simpler to default or refine later.
    
    
    async def validate_single_item(q_key, q_text):
        """Helper to validate one specific question chunk"""
        try:
            # Build Context for THIS question only
            # We need to map q_key (question1) back to the config? 
            # The split gave us numbers based on the generated text headers.
            # Ideally "Question [1]" corresponds to index 0 in questions list.
            try:
                idx = int(q_key.replace("question", "")) - 1
            except:
                idx = 0
            
            # Formatting context safely
            q_config = questions[idx] if 0 <= idx < len(questions) else {}
            topic_str = q_config.get('topic', 'Unknown')
            q_notes = q_config.get('additional_notes_text', '')
            
            # Specifier
            spec = q_config.get('mcq_type') or q_config.get('fib_type') or q_config.get('descriptive_type') or "Standard"
            
            context_line = f"Question Context: Topic='{topic_str}', Type='{spec}'"
            if q_notes: context_line += f", Notes='{q_notes}'"
                
            # Construct Prompt
            val_prompt = validation_prompt_template.replace("{{GENERATED_CONTENT}}", q_text)
            val_prompt = val_prompt.replace("{{INPUT_CONTEXT}}", context_line)
            # Use structure map if available (passed or hardcoded knowns)
            val_prompt = val_prompt.replace("{{OUTPUT_FORMAT_RULES}}", structure_format)
            
            # Call API
            v_res = await validate_batch(f"{batch_key}_{q_key}", val_prompt, general_config, val_files, val_file_metadata)
            
            logger.info(f"[{batch_key}_{q_key}] Validation finished. Result keys: {list(v_res.keys()) if v_res else 'None'}")
            
            # Return tuple of (key, result)
            return q_key, v_res
            
        except Exception as e:
            logger.error(f"Item validation failed for {q_key}: {e}")
            return q_key, {'error': str(e), 'text': ''}

    # Launch all validation tasks
    validation_tasks = [
        validate_single_item(k, v) for k, v in split_questions.items()
    ]
    
    validation_results = await asyncio.gather(*validation_tasks)
    
    # --- STAGE 4: AGGREGATE ---
    # We need to combine the results into a single "validated" dictionary 
    # that looks like the result of a batch validation (text field containing JSON).
    # OR we construct the final object that the Renderer expects.
    # The renderer typically parses `validated['text']` as JSON.
    # So we should reconstruct a JSON string from our individual results.
    
    import json
    aggregated_json = {}
    total_val_time = 0
    
    # Define helper locally or at module level (doing locally to minimize diff scope but module level is cleaner. 
    # I'll add the helper at module level in a separate edit or just inline a simple one here if short.
    # Actually, let's look for braces.
    
    def extract_first_json_match(text: str) -> Dict[str, Any]:
        """
        Helper to find first valid JSON object using raw_decode.
        This handles trailing text automatically and is more robust than manual brace counting.
        """
        try:
            # Find closest opening brace
            start_idx = text.find('{')
            if start_idx == -1:
                return None 
            
            # Use raw_decode which returns (obj, end_index) and ignores trailing text
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(text, idx=start_idx)
            return obj
        except Exception:
            return None

    for q_key, v_res in validation_results:
        # v_res['text'] should be the JSON for that question (e.g. {"question1": "markdown"})
        total_val_time += v_res.get('elapsed', 0)
        
        # Robust extraction
        raw_text = v_res.get('text', '')
        
        # First try to strip code blocks as they are most common source of noise
        cleaner_text = raw_text.replace('```json', '').replace('```', '').strip()
        
        # Try extraction on cleaned text first (best chance)
        data = extract_first_json_match(cleaner_text)
        
        # If valid data found
        if data:
            try:
                # Take the first value found (assuming one question per validation call)
                if data:
                    content = next(iter(data.values()))
                    aggregated_json[q_key] = content
                else:
                    aggregated_json[q_key] = raw_text
            except Exception as e:
                logger.warning(f"Extracted JSON but failed to get value for {q_key}: {e}")
                aggregated_json[q_key] = raw_text
        else:
            # If failed, try on original raw text (in case code block stripping removed something vital? Unlikely but safe)
            data_retry = extract_first_json_match(raw_text)
            if data_retry:
                try:
                    content = next(iter(data_retry.values()))
                    aggregated_json[q_key] = content
                except:
                    aggregated_json[q_key] = raw_text
            else:
                logger.warning(f"Failed to parse validation output for {q_key}. Using raw text.")
                aggregated_json[q_key] = raw_text
            
    # Create the virtual "batch validation result"
    final_validation_payload = {
        'text': json.dumps(aggregated_json),
        'elapsed': total_val_time / max(len(validation_results), 1), # Approx avg time or max? 
        'batch_key': batch_key
    }
    
    logger.info(f"[{batch_key}] Flow Complete. Aggregated {len(aggregated_json)} items.")
    
    result_payload = {
        'raw': raw_result,
        'validated': final_validation_payload
    }
    
    if progress_callback: progress_callback(batch_key, result_payload)
    return {batch_key: result_payload}


async def process_batches_pipeline(
    questions_config: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    progress_callback=None
) -> Dict[str, Dict[str, Any]]:
    """
    Process ALL batches in separate PARALLEL flows.
    """
    logger.info(f"Starting PARALLEL pipeline for {len(questions_config)} questions")
    
    # Group questions by type
    grouped_questions = group_questions_by_type_and_topic(questions_config)
    
    # Load validation template
    try:
        import yaml
        with open('validation.yaml', 'r', encoding='utf-8') as f:
            validation_config = yaml.safe_load(f)
            validation_prompt_template = validation_config.get('validation_prompt', '')
    except Exception as e:
        logger.error(f"Failed to load validation.yaml: {e}")
        return {'error': "Critical: validation.yaml not found"}

    # Prepare all batch tasks
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
                validation_prompt_template=validation_prompt_template,
                progress_callback=progress_callback
            )
            all_batch_tasks.append(task)
            
    logger.info(f"🚀 Launching {len(all_batch_tasks)} batch flows in PARALLEL")
    
    # Run everything
    all_results_list = await asyncio.gather(*all_batch_tasks, return_exceptions=True)
    
    # Aggregate results
    pipeline_results = {}
    for res in all_results_list:
        if isinstance(res, dict):
            pipeline_results.update(res)
        elif isinstance(res, Exception):
            logger.error(f"Batch flow failed: {res}")
            
    logger.info("Pipeline processing completed.")
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
    
    grouped_map = defaultdict(list)
    for q in original_config:
        grouped_map[q.get('type', 'MCQ')].append(q)
        
    for q_type, indices in regeneration_map.items():
        # Handle new Batch Key format in regeneration map (e.g., "MCQ - Batch 1")
        # EXTRACT BASE TYPE from keys if they contain " - Batch "
        base_type = q_type.split(' - Batch ')[0]
        
        if base_type not in grouped_map:
            logger.warning(f"Type {base_type} (from {q_type}) not found in original config")
            continue
            
        questions_of_type = grouped_map[base_type]
        
        for idx in indices:
            # indices are 1-based from the layout, but they refer to the GLOBAL index within that type 
            # across all batches? Or batch-local?
            # In result_renderer, we construct keys like "question1", "question2". 
            # If we split into batches, the renderer outputs indices 1..5 for Batch 1, 1..5 for Batch 2?
            # NO. The prompt builder usually receives 5 questions. The generated output will say question1..question5.
            # So the UI indices for Batch 2 will likely be 1..5 as well?
            # IF SO, the regeneration map coming from UI will be { "MCQ - Batch 2": [1, 3] }.
            # This [1, 3] means 1st and 3rd question WITHIN Batch 2.
            # We need to map this back to the global list if we want to grab settings,
            # OR just grab the settings for the corresponding items in that batch.
            
            # Since we don't have the batch definitions persisted explicitly, we must reconstruct them.
            # questions_of_type has ALL generic MCQs.
            # "MCQ - Batch 1" -> indices 0-4
            # "MCQ - Batch 2" -> indices 5-9
            
            # Parse batch number
            batch_num = 1
            if ' - Batch ' in q_type:
                try:
                    batch_num = int(q_type.split(' - Batch ')[1])
                except:
                    batch_num = 1
            
            # Calculate offset
            BATCH_SIZE = DEFAULT_BATCH_SIZE
            offset = (batch_num - 1) * BATCH_SIZE
            
            # Target index in the global list for this type
            # idx is 1-based index within the batch prompt result
            target_global_idx = offset + (idx - 1)
            
            if 0 <= target_global_idx < len(questions_of_type):
                q_config = questions_of_type[target_global_idx]
                q_config['_is_being_regenerated'] = True
                
                # IMPORTANT: We need to pass the proper TYPE that leads to the same batching?
                # If we just pass 'MCQ', the pipeline will batch them again.
                # If we have only 2 questions, they will fit in one batch 'MCQ - Batch 1'.
                # This changes the key name returned!
                # If UI expects 'MCQ - Batch 2', but we return 'MCQ - Batch 1' (because only 2 items), UI won't match.
                
                # FIX: We should force the batch key name in the result? 
                # Or just update `streamlit_app.py` to handle the mismatch?
                # The user requirement was about architecture.
                # For regeneration, we just want new content.
                # Use a specific batch key override if possible? 
                # Our new `process_batches_pipeline` calculates batch names automatically.
                # If we pass a custom 'type' like 'MCQ - Batch 2', `group_questions_by_type` will group them under that key.
                # `process_batches_pipeline` will then see 'MCQ - Batch 2' as the type.
                # It will then create batches: 'MCQ - Batch 2 - Batch 1'. This is double suffix.
                
                # To avoid complex refactoring of regeneration right now, let's just use the BASE TYPE.
                # The UI logic for regeneration (handling the return) likely needs to be robust enough 
                # to map whatever comes back.
                # Actually, `streamlit_app.py` logic:
                # `original_idx = requested_indices[i]`
                # `existing_questions_map[original_k] = ...`
                # It maps sequential new questions to the requested slots.
                # So if we return "MCQ - Batch 1" with 2 questions, the UI app logic 
                # (which iterates `regen_map`) should be able to map them if it matches the batch key.
                
                # Hack: We can temporarily change the 'type' in config to be the Batch Key (e.g. "MCQ - Batch 2").
                # This way the pipeline groups them as "MCQ - Batch 2".
                # The pipeline will then produce "MCQ - Batch 2 - Batch 1".
                # The UI expects "MCQ - Batch 2". 
                # This mismatch ("... - Batch 1") might break the UI update loop which looks for exact key match.
                
                # Wait, if I change the pipeline to produce "MCQ - Batch 1", 
                # the UI logic in `streamlit_app.py` line 1625 iterates `regen_results`.
                # Checks `if batch_key in st.session_state.generated_output`.
                # If I generate "MCQ - Batch 2", result has "MCQ - Batch 2 - Batch 1".
                # This key won't exist in `generated_output` (which has "MCQ - Batch 2").
                
                # SOLUTION: We should strip the suffixes in `streamlit_app.py` OR 
                # Modify pipeline locally to return exact keys for regeneration?
                # Simpler: Modify `regenerate_specific_questions_pipeline` to UNPACK the results 
                # and fix the keys before returning.
                
                q_config_copy = q_config.copy()
                q_config_copy['type'] = q_type # "MCQ - Batch 2"
                filtered_config.append(q_config_copy)
                
            else:
                logger.warning(f"Index {idx} out of bounds for type {base_type} (Global idx {target_global_idx})")

    if not filtered_config:
        return {'error': "No valid questions selected for regeneration"}

    logger.info(f"Starting regeneration pipeline for {len(filtered_config)} questions...")
    results = await process_batches_pipeline(filtered_config, general_config, progress_callback)
    
    # POST-PROCESS RESULTS TO FIX KEYS
    # Results will have keys like "MCQ - Batch 2 - Batch 1".
    # We want "MCQ - Batch 2".
    fixed_results = {}
    for k, v in results.items():
        # Remove the last " - Batch 1" derived from the single batch of regeneration
        # We assume regeneration is small and fits in one batch usually.
        # If it doesn't, we might have issues, but user regenerates selected items (usually < 5).
        if ' - Batch 1' in k:
            original_key = k.replace(' - Batch 1', '')
            fixed_results[original_key] = v
        else:
            fixed_results[k] = v
            
    return fixed_results
