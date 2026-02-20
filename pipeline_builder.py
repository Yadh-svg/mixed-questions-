"""
Pipeline Prompt Builder for Multi-Stage Generation
Implements 3-stage Architect-Writer pipeline: Math Core → Writer (Scenario+Question) → Solution
"""

import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging
import json

import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load pipeline prompts
PIPELINE_PROMPTS_FILE = Path(__file__).parent / "pipeline_prompts.yaml"

with open(PIPELINE_PROMPTS_FILE, 'r', encoding='utf-8') as f:
    PIPELINE_PROMPTS = yaml.safe_load(f)

GENERATION_PIPELINE_MODE = "MATH_FIRST"  # Updated mode

def get_files(questions: List[Dict[str, Any]], general_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract PDF and image files from questions in the batch.
    - Universal file is used for all questions with 'pdf' as new concept source
    - Per-question files are only for additional notes
    
    Returns:
        Dictionary with 'files' (list), 'source_type', and 'filenames'
    """
    files = []
    filenames = []
    source_types = set()
    
    # Check if we have a universal file and if any question uses file as new concept source
    universal_file = general_config.get('universal_pdf')  # Keep key name for backward compatibility
    has_file_new_concept = any(q.get('new_concept_source') == 'pdf' for q in questions)
    
    # Add universal file if it exists and at least one question uses file as new concept source
    if universal_file and has_file_new_concept:
        files.append(universal_file)
        filename = getattr(universal_file, 'name', 'universal_new_concept_file')
        filenames.append(filename)
        source_types.add('Universal New Concept File')
        logger.info(f"Using universal file: {filename}")
    
    # Collect additional notes files from questions
    for q in questions:
        # Check for additional notes file
        additional_notes_file = q.get('additional_notes_pdf')  # Keep key name for backward compatibility
        if additional_notes_file and additional_notes_file not in files:  # Avoid duplicates
            files.append(additional_notes_file)
            filename = getattr(additional_notes_file, 'name', 'uploaded_file')
            filenames.append(filename)
            source_types.add('Additional Notes File')
            logger.info(f"Adding question specific file: {filename}")
    
    # Determine overall source type
    if files:
        if len(source_types) > 1:
            source_type = 'Mixed Files'
        else:
            source_type = list(source_types)[0]
        logger.info(f"Collected {len(files)} file(s) from batch: {', '.join(filenames)}")
    else:
        source_type = 'Text Only'
        logger.info("Using text only (no files)")
    
    return {
        'files': files,
        'source_type': source_type,
        'filenames': filenames
    }

def _get_subparts_count(q: Dict[str, Any]) -> int:
    """Helper to determine subparts count consistently."""
    # Check list-based config first
    subparts = []
    if 'subparts' in q and isinstance(q['subparts'], list) and q['subparts']:
        subparts = q['subparts']
    elif 'subparts_config' in q and isinstance(q['subparts_config'], list) and q['subparts_config']:
        subparts = q['subparts_config']
    
    if subparts:
        return len(subparts)
    
    # Check direct keys
    # Handle string or int input safely
    val = q.get('number_of_subparts') or q.get('num_subparts')
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
            
    return 4  # Default fallback

def _get_batch_type(questions: List[Dict[str, Any]]) -> str:
    """Determine the dominant type of the batch (MCQ, FIB, CBS)."""
    # Assuming batch is homogeneous as per batch_processor logic
    # Default to 'cbs' if unknown
    if not questions:
        return 'cbs'
    
    first_q = questions[0]
    # Check specific type keys or 'type' field
    q_type = first_q.get('type', 'Case Study').lower()
    
    if 'mcq' in q_type:
        return 'mcq'
    elif 'fill' in q_type or 'fib' in q_type:
        return 'fib'
    elif 'assertion' in q_type or 'reasoning' in q_type:
        return 'a&b'
    elif 'multi' in q_type and 'part' in q_type:
        return 'multipart'
    elif 'descriptive' in q_type.lower():
        if 'sub' in q_type.lower():
            return 'descriptive_with_subq'
        return 'descriptive'
    else:
        return 'cbs'

def extract_json_from_response(response_text: str):
    """
    Extract JSON from LLM response with robust handling for LaTeX backslashes.
    """
    import re
    
    # Internal helper for safe parsing
    def rigorous_parse(text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Attempt to fix LaTeX backslashes
            # Escape backslashes that are NOT followed by special JSON chars (n, ", \, u, /)
            # We want to keep \n, \", \\, \uXXXX, \/
            # We want to change \frac to \\frac, \text to \\text, \circ to \\circ, etc.
            fixed_text = re.sub(r'\\(?![n"\\u/])', r'\\\\', text)
            try:
                # logger.info("Attempting to fix JSON with regex sanitization for LaTeX...")
                return json.loads(fixed_text)
            except json.JSONDecodeError:
                pass
        return None

    # Try to find JSON in markdown code block first
    json_block_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if json_block_match:
        json_str = json_block_match.group(1).strip()
        res = rigorous_parse(json_str)
        if res: return res
    
    # Try to find raw JSON
    try:
        array_start = response_text.find('[')
        object_start = response_text.find('{')
        if array_start != -1 and (object_start == -1 or array_start < object_start):
            start = array_start
            end = response_text.rfind(']')
            if end != -1:
                res = rigorous_parse(response_text[start:end+1])
                if res: return res
        elif object_start != -1:
            start = object_start
            end = response_text.rfind('}')
            if end != -1:
                res = rigorous_parse(response_text[start:end+1])
                if res: return res
    except Exception:
        pass
    
    return None

def _sanitize_topic(topic: str) -> str:
    """
    Sanitize the topic string to remove accidental pollution from previous prompts or copy-pastes.
    Fixes issue where 'topic' contains full Question blueprints (e.g. 'Q1: Q1 Topic: ...').
    """
    if not topic:
        return ""
    
    # 1. Check for common prefixes identifying full question dumps
    import re
    # Pattern: Starts with Q1: Q1 Topic: ... or similar
    # Remove "Q<d>: Topic :" prefix
    clean_topic = re.sub(r'^Q\d+\s*:\s*Q\d+\s*Topic\s*:\s*', '', topic, flags=re.IGNORECASE)
    
    # Remove "Q<d>: Topic:" normal prefix if present
    clean_topic = re.sub(r'^Q\d+\s*:\s*Topic\s*:\s*', '', clean_topic, flags=re.IGNORECASE)
    
    # If topic still contains suspect keywords like "Subquestion 1:", "DOK 1:", assume it's a blob and try to take first part
    if "Subquestion" in clean_topic or "DOK" in clean_topic:
        # Heuristic: Take text before "Subquestion" or "Subquestions:" or "DOK"
        # Split by common delimiters of pollution
        parts = re.split(r'\s+Subquestion|\s+DOK|\s+Q\d+\s*:', clean_topic)
        if parts:
            clean_topic = parts[0].strip()
            
    # Remove parentheses wrapping if it looks like (Q1: ...)
    if clean_topic.startswith('(') and clean_topic.endswith(')'):
        clean_topic = clean_topic[1:-1].strip()
        
    # Final cleanup of "Topic:" prefix if remained
    clean_topic = re.sub(r'^Topic\s*:\s*', '', clean_topic, flags=re.IGNORECASE)
    
    return clean_topic.strip()

def _format_question_requirement(q: Dict[str, Any], index: int, batch_type: str) -> str:
    """Format the requirement string for a single question (Shared by Math Core & Writer)."""
    topic = _sanitize_topic(q.get('topic', 'General Topic'))
    notes = q.get('additional_notes_text', '')
    
    # Determine number of subparts and their config
    subparts = []
    if 'subparts' in q and isinstance(q['subparts'], list) and q['subparts']:
        subparts = q['subparts']
    elif 'subparts_config' in q and isinstance(q['subparts_config'], list) and q['subparts_config']:
        subparts = q['subparts_config']
    
    count = _get_subparts_count(q)
    
    # Gather subpart details
    sub_details = []
    if subparts:
        for j, sp in enumerate(subparts, 1):
            p_dok = sp.get('dok', q.get('dok', '1'))
            p_marks = sp.get('marks', 1.0)
            if str(p_dok).isdigit():
                p_dok = f"DOK {p_dok}"
            sub_details.append(f"{j} - {p_dok} - {p_marks} mark")
    else:
        # Fallback if no specific subpart config
        q_dok = q.get('dok', 1)
        q_marks = q.get('marks', 1.0)
        if str(q_dok).isdigit():
            q_dok = f"DOK {q_dok}"
            
        if count == 1:
            sub_details.append(f"1 - {q_dok} - {q_marks} mark")
        else:
            for j in range(1, int(count) + 1):
                sub_details.append(f"{j} - {q_dok} - {q_marks} mark")

    details_str = " , ".join(sub_details)
    
    # Extract additional fields
    mcq_type = q.get('mcq_type', 'Auto')
    fib_type = q.get('fib_type', 'Auto')
    taxonomy = q.get('taxonomy', 'Remembering')
    stmt_based = "YES" if q.get('statement_based', False) else "NO"

    if batch_type == 'mcq':
        q_dok = q.get('dok', 1)
        q_marks = q.get('marks', 1.0)
        if str(q_dok).isdigit():
            q_dok = f"DOK {q_dok}"
        line = f"Q{index}: topic : {topic} , {q_dok} - {q_marks} mark , MCQ Type: {mcq_type}, Taxonomy: {taxonomy}, Statement Based: {stmt_based}"
    elif batch_type == 'fib':
        line = f"Q{index}: topic : {topic} : number of subquestion : {count} , {details_str} , FIB Type: {fib_type}, Taxonomy: {taxonomy}"
    elif batch_type == 'a&b':
        q_dok = q.get('dok', 1)
        q_marks = q.get('marks', 1.0)
        if str(q_dok).isdigit():
            q_dok = f"DOK {q_dok}"
        line = f"Q{index}: topic : {topic} , {q_dok} - {q_marks} mark , Taxonomy: {taxonomy}"
    elif batch_type == 'multipart':
        multipart_type = q.get('multipart_type', 'Auto')
        line = f"Q{index}: topic : {topic} : number of subquestion : {count} , {details_str} , Multi-Part Type: {multipart_type}"
    elif batch_type == 'descriptive':
        descriptive_type = q.get('descriptive_type', 'Auto')
        q_dok = q.get('dok', 1)
        q_marks = q.get('marks', 1.0)
        if str(q_dok).isdigit():
            q_dok = f"DOK {q_dok}"
        line = f"Q{index}: topic : {topic} , {q_dok} - {q_marks} mark , Taxonomy: {taxonomy} , Descriptive Type: {descriptive_type}"
    elif batch_type == 'descriptive_with_subq':
        descriptive_type = q.get('descriptive_type', 'Auto')
        num_subparts = q.get('num_subparts', 2)
        q_dok = q.get('dok', 1)
        q_marks = q.get('marks', 1.0)
        if str(q_dok).isdigit():
            q_dok = f"DOK {q_dok}"
        # Enhanced to include sub-details
        line = f"Q{index}: topic : {topic} , {q_dok} - {q_marks} mark , Taxonomy: {taxonomy} , Descriptive Type: {descriptive_type}, Number of Subquestions: {num_subparts} . Sub-details: {details_str}"
    else:
        # Default/Case Study format
        line = f"Q{index}: topic : {topic} : number of subquestion : {count} , {details_str}"
        
    if notes:
        line += f" \n   [Specific Note for Q{index}: {notes}]"
    
    # Add file reference if present
    add_notes_file = q.get('additional_notes_pdf')
    if add_notes_file:
         filename = getattr(add_notes_file, 'name', 'uploaded_file')
         line += f" \n   [Refer to file for this question: {filename}]"
        
    return line


def build_math_core_prompt(
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None
) -> Dict[str, Any]:
    """Build prompt for Stage 1: Math Core (Architect)."""
    batch_type = _get_batch_type(questions)
    prompt_key = f"{batch_type}_math_core"
    
    logger.info(f"Building Math Core prompt ({batch_type}) for {len(questions)} questions")
    
    template = PIPELINE_PROMPTS.get(prompt_key, PIPELINE_PROMPTS.get('cbs_math_core'))
    
    # Build detailed requirements for each question
    req_list = []
    
    for i, q in enumerate(questions, 1):
        line = _format_question_requirement(q, i, batch_type)
        req_list.append(line)
        
    # specific instruction for subtopics (only for CBS usually, but good generic advice)
    if batch_type == 'cbs':
        req_list.append("\nCRITICAL INSTRUCTION: For EACH sub-question, you must identify a distinct sub-topic or specific mathematical area within the main Topic to ensure variety and depth. Do NOT ask the same type of question for all parts.")

    req_text = "\n".join(req_list)
    
    topics = list(set([q.get('topic', '') for q in questions if q.get('topic')]))
    topic_text = ', '.join(topics) if topics else 'General Topic'
    
    # Global Additional Notes
    global_notes = general_config.get('additional_notes', 'None')
    
    # Prepare Context Strings (New/Old Concept & Files)
    new_concept = general_config.get('new_concept', 'N/A')
    old_concept = general_config.get('old_concept', 'N/A')
    
    # Get File Info to build context
    file_info = get_files(questions, general_config)
    files = file_info['files']
    filenames = file_info['filenames']
    
    context_instruction = f"""
    <source_material>
      <new_concept>
        {new_concept}
      </new_concept>
      
      <old_concept>
        {old_concept}
      </old_concept>
      
      <files_uploaded>
        {', '.join(filenames) if filenames else 'None'}
      </files_uploaded>
      
      <file_instruction>
        - If files are uploaded, use them as the PRIMARY source for specific question details as indicated in requirements.
        - 'New Concept' text above is the theoretical basis.
        - 'Old Concept' is prerequisite knowledge.
      </file_instruction>
    </source_material>
    """
    
    replacements = {
        '{{Grade}}': str(general_config.get('grade', 'Grade 10')),
        '{{Subject}}': general_config.get('subject', 'Mathematics'),
        '{{Chapter}}': general_config.get('chapter', 'Chapter'),
        '{{Topic}}': topic_text,
        '{{Additional_Notes}}': global_notes, # Injected global notes
        '{{Question_Specific_Requirements}}': context_instruction + "\n" + req_text, # Injected detailed requirements + specific notes
    }
    
    prompt = template
    for k, v in replacements.items():
        prompt = prompt.replace(k, v)
        
    return {'prompt': prompt, 'files': files or [], 'file_metadata': {'stage': 'math_core'}}

def build_writer_prompt(
    math_core_data: Dict[str, Any],
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    files: List = None
) -> Dict[str, Any]:
    """Build prompt for Stage 2: Writer (Scenario + Question)."""
    batch_type = _get_batch_type(questions)
    prompt_key = f"{batch_type}_writer"
    
    logger.info(f"Building Writer prompt ({batch_type}) from Math Core")
    logger.info(f"Writer Prompt Files: {len(files) if files else 0}")
    
    template = PIPELINE_PROMPTS.get(prompt_key, PIPELINE_PROMPTS.get('cbs_writer'))
    
    math_core_json = json.dumps(math_core_data, indent=2)
    
    # Requirements string with per-question notes
    req_list = []
    for i, q in enumerate(questions, 1):
        line = _format_question_requirement(q, i, batch_type)
        req_list.append(line)
        
    req_text = "\n".join(req_list)

    # Global Additional Notes
    global_notes = general_config.get('additional_notes', 'None')

    # Prepare Context Strings (New/Old Concept & Files) for Writer as well
    new_concept = general_config.get('new_concept', 'N/A')
    old_concept = general_config.get('old_concept', 'N/A')
    
    # Get File Info to build context
    file_info = get_files(questions, general_config)
    files = file_info['files']
    filenames = file_info['filenames']
    
    context_instruction = f"""
    <source_material>
      <new_concept>
        {new_concept}
      </new_concept>
      
      <old_concept>
        {old_concept}
      </old_concept>
      
      <files_uploaded>
        {', '.join(filenames) if filenames else 'None'}
      </files_uploaded>
    </source_material>
    """

    replacements = {
        '{{Grade}}': str(general_config.get('grade', '10')),
        '{{Subject}}': general_config.get('subject', 'Math'),
        '{{Question_Requirements}}': context_instruction + "\n" + req_text,
        '{{Additional_Notes}}': global_notes, # Injected global notes
        '{{MATH_CORE_DATA}}': math_core_json
    }
    
    prompt = template
    for k, v in replacements.items():
        prompt = prompt.replace(k, v)
        
    return {'prompt': prompt, 'files': files or [], 'file_metadata': {'stage': 'writer'}}


