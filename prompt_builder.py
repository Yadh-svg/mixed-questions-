"""
Prompt Builder for Question Generation
Constructs prompts from templates with proper placeholder replacement.
"""

import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load prompts.yaml
PROMPTS_FILE = Path(__file__).parent / "prompts.yaml"

with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
    PROMPTS = yaml.safe_load(f)

# Mapping from UI question types to prompt template keys
QUESTION_TYPE_MAPPING = {
    "MCQ": "mcq_questions",
    "Fill in the Blanks": "FIB",
    "Case Study": "case_study_maths",
    "Multi-Part": "multi_part_maths",
    "Assertion-Reasoning": "assertion_reasoning",
    "Descriptive": "descriptive",
    "Descriptive w/ Subquestions": "descriptive_subq"
}


def build_topics_section(questions: List[Dict[str, Any]]) -> str:
    """
    Build the {{TOPICS_SECTION}} string from a list of questions.
    
    Format:
    - Topic: "Topic Name" → Questions: 1, DOK: Y, Marks: Z, Taxonomy: ..., New Concept Source: ..., Additional Notes Source: ...
      Additional Notes for this question: [per-question notes if applicable]
    
    Each question is listed individually with its own metadata.
    """
    lines = []
    
    for q in questions:
        topic = q.get('topic', 'Unnamed Topic')
        new_concept_source = q.get('new_concept_source', 'text')
        new_concept_file = q.get('new_concept_pdf')  # Keep key name for backward compatibility
        additional_notes_source = q.get('additional_notes_source', 'none')
        additional_notes_file = q.get('additional_notes_pdf')  # Keep key name for backward compatibility
        additional_notes_text = q.get('additional_notes_text', '')
        
        # Taxonomy is now a single string, not a list
        taxonomy = q.get('taxonomy', 'Remembering')
        # Handle legacy list format if it exists
        if isinstance(taxonomy, list):
            taxonomy = taxonomy[0] if taxonomy else 'Remembering'
        
        # Determine new concept source label
        if new_concept_source == 'pdf' and new_concept_file:
            filename = getattr(new_concept_file, 'name', 'uploaded_file')
            new_concept_label = f'File ({filename})'
        else:
            new_concept_label = 'Text'
        
        # Determine additional notes source label
        if additional_notes_source == 'pdf' and additional_notes_file:
            filename = getattr(additional_notes_file, 'name', 'uploaded_file')
            additional_notes_label = f'File ({filename})'
        elif additional_notes_source == 'text':
            additional_notes_label = 'Text'
        else:
            additional_notes_label = 'None'
        
        # Each question gets its own line with Questions: 1
        dok = q.get('dok', 1)
        marks = q.get('marks', 1)
        
        line = f'    - Topic: "{topic}" → Questions: 1, DOK: {dok}, Marks: {marks}, Taxonomy: {taxonomy} | New Concept Source: {new_concept_label} | Additional Notes Source: {additional_notes_label}'
        lines.append(line)
        
        # Add per-question additional notes if present
        if additional_notes_source == 'text' and additional_notes_text:
            lines.append(f'      Additional Notes for this question: {additional_notes_text}')
    
    return "\n".join(lines)


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
        additional_notes_source = q.get('additional_notes_source', 'none')
        
        # Check for additional notes file
        if additional_notes_source == 'pdf':
            additional_notes_file = q.get('additional_notes_pdf')  # Keep key name for backward compatibility
            if additional_notes_file and additional_notes_file not in files:  # Avoid duplicates
                files.append(additional_notes_file)
                filename = getattr(additional_notes_file, 'name', 'additional_notes_file')
                filenames.append(filename)
                source_types.add('Additional Notes File')
    
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


def build_prompt_for_batch(
    batch_key: str,
    questions: List[Dict[str, Any]],
    general_config: Dict[str, Any],
    type_config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Build a complete prompt for a batch of questions.
    
    Args:
        batch_key: Question type identifier
        questions: List of question configurations (all same type)
        general_config: General configuration
        type_config: Type-specific configuration (e.g., subparts for Multi-Part)
    
    Returns:
        Dictionary with 'prompt' (str), 'files' (list), and 'file_metadata' (dict)
    """
    logger.info(f"Building prompt for batch: {batch_key}")
    
    # Determine if we're using files and get metadata
    file_info = get_files(questions, general_config)
    files = file_info['files']
    source_type = file_info['source_type']
    filenames = file_info['filenames']
    
    # Get the appropriate template key
    template_key = QUESTION_TYPE_MAPPING.get(batch_key, "mcq_questions")
    
    # Add _pdf suffix if using files (keeping _pdf suffix for backward compatibility with templates)
    if files:
        template_key += "_pdf"
    
    # Get the template
    if template_key not in PROMPTS:
        logger.warning(f"Template {template_key} not found, using mcq_questions")
        template_key = "mcq_questions"
    
    template = PROMPTS[template_key]
    
    # Comprehensive logging
    file_info = f" | Files: {', '.join(filenames)}" if filenames else ""
    logger.info(f"Building prompt | Template: {template_key} | Source: {source_type}{file_info} | Questions: {len(questions)}")
    
    # Build topics section
    topics_section = build_topics_section(questions)
    
    # Calculate total questions
    total_questions = len(questions)
    number_of_topics = len(set(q.get('topic', '') for q in questions if q.get('topic')))
    
    # Build reference instruction based on content sources
    reference_instruction = ""
    
    # Determine if we have files and what types
    has_new_concept_file = any(q.get('new_concept_source') == 'pdf' and q.get('new_concept_pdf') for q in questions)
    has_additional_notes_file = any(q.get('additional_notes_source') == 'pdf' and q.get('additional_notes_pdf') for q in questions)
    has_new_concept_text = any(q.get('new_concept_source') == 'text' for q in questions)
    has_additional_notes_text = any(q.get('additional_notes_source') == 'text' for q in questions)
    
    if files:
        # We have at least one file
        file_names = ', '.join(filenames) if filenames else "the uploaded file(s)"
        
        reference_instruction = f"""
    
    ## CONTENT REFERENCE INSTRUCTION:
    **IMPORTANT**: Each topic in the TOPICS_SECTION below specifies its content sources. Follow them strictly for each topic.
    
    **New Concept Sources:**
    - For topics marked with "New Concept Text" → Refer to the New Concepts section provided below
    - For topics marked with "New Concept File" → Extract concepts from the corresponding uploaded file: {file_names}
    
    **Additional Notes Sources:**
    - **Global Additional Notes** (shown below) apply to ALL questions
    - **Per-Question Additional Notes** are shown directly in the TOPICS_SECTION for specific questions
    - For topics with "Additional Notes File" → Extract additional context from the corresponding uploaded file: {file_names}
    - For topics with "None" → No per-question additional notes for this topic (global notes still apply)
    
    **File Content Guidelines:**
    - Extract relevant concepts, examples, definitions, and problem-solving approaches from the file content
    - Base questions on the material covered in the file, ensuring alignment with the topics specified
    - Use the file as the primary source of information for creating contextually accurate questions
    - Pay attention to the filename mentioned in each topic to use the correct file
    
    **New Concepts (for text-based topics):**
    {{{{New_Concept}}}}
    
    **Global Additional Notes (applies to ALL questions):**
    {{{{Additional_Notes}}}}
    
    **Per-Question Additional Notes:**
    Some topics may have specific additional notes shown directly in the TOPICS_SECTION below.
    These per-question notes supplement the global notes for that specific question.
    
    Note: The New Concepts and Additional Notes sections provide context for topics using text sources.
    For file-based topics, prioritize the file content for question generation.
    """
    else:
        # Text only, no PDFs
        reference_instruction = """
    
    ## CONTENT REFERENCE INSTRUCTION:
    **IMPORTANT**: Each topic in the TOPICS_SECTION below specifies its content sources.
    - All topics use "New Concept Text" → Refer to the New Concepts section provided in this prompt
    - Topics may have per-question "Additional Notes Text" → These are shown directly in the TOPICS_SECTION
    - Topics with "None" for Additional Notes → Do not use per-question additional notes for those topics
    
    **New Concepts to Reference:**
    {{New_Concept}}
    
    **Global Additional Notes (applies to ALL questions):**
    {{Additional_Notes}}
    
    **Per-Question Additional Notes:**
    Some topics may have specific additional notes shown directly in the TOPICS_SECTION below.
    These per-question notes take precedence over global notes for that specific question.
    
    Use the concepts, definitions, formulas, and examples from the New Concepts to create contextually relevant questions.
    Apply global Additional Notes to all questions, and per-question notes where specified.
    """

    
    # Prepare replacements
    replacements = {
        '{{Grade}}': general_config.get('grade', 'Grade 10'),
        '{{Curriculum}}': general_config.get('curriculum', 'NCERT'),
        '{{Subject}}': general_config.get('subject', 'Mathematics'),
        '{{Chapter}}': general_config.get('chapter', 'Chapter'),
        '{{Old_Concept}}': general_config.get('old_concept', 'N/A'),
        '{{New_Concept}}': general_config.get('new_concept', 'N/A'),
        '{{Additional_Notes}}': general_config.get('additional_notes', 'None'),
        '{{TOPICS_SECTION}}': topics_section,
        '{{TOTAL_QUESTIONS}}': str(total_questions),
        '{{NUMBER_OF_TOPICS}}': str(number_of_topics)
    }
    
    # Special handling for multi-part questions
    if 'multi_part' in template_key.lower() and type_config:
        subparts_config = type_config.get('subparts_config', [])
        
        if subparts_config:
            num_subparts = len(subparts_config)
            replacements['{{Number_of_subparts}}'] = str(num_subparts)
            
            # Build subparts section dynamically
            subparts_lines = ["    Subpart Configuration:"]
            for subpart in subparts_config:
                part = subpart.get('part', 'a')
                dok = subpart.get('dok', 1)
                marks = subpart.get('marks', 1.0)
                taxonomy = subpart.get('taxonomy', 'Remembering')
                line = f"      {part} → DOK {dok}, Marks: {marks}, Taxonomy: {taxonomy}"
                subparts_lines.append(line)
            
            replacements['{{SUBPARTS_SECTION}}'] = "\n".join(subparts_lines)
        else:
            # Fallback to default if no config provided
            replacements['{{Number_of_subparts}}'] = '3'
            replacements['{{SUBPARTS_SECTION}}'] = """    Subpart Configuration:
      a → DOK 1, Marks: 1.0, Taxonomy: Remembering
      b → DOK 2, Marks: 1.0, Taxonomy: Understanding
      c → DOK 3, Marks: 1.0, Taxonomy: Applying"""
    
    # Special handling for FIB questions with per-question subparts
    if 'fib' in template_key.lower():
        # For FIB, we need to inject per-question subpart configuration
        # Similar to case study handling
        fib_configs = []
        for idx, q in enumerate(questions, 1):
            num_subparts = q.get('num_subparts', 1)
            
            if num_subparts > 1 and 'subparts' in q:
                subparts = q['subparts']
                subpart_strs = []
                for sp in subparts:
                    part = sp.get('part', 'i')  # Roman numerals
                    dok = sp.get('dok', 1)
                    marks = sp.get('marks', 1.0)
                    taxonomy = sp.get('taxonomy', 'Remembering')
                    subpart_strs.append(f"{part}) DOK {dok}, Marks {marks}, Taxonomy: {taxonomy}")
                
                config_str = f"Question {idx}: {len(subparts)} sub-parts - {', '.join(subpart_strs)}"
                fib_configs.append(config_str)
        
        if fib_configs:
            fib_note = "\n\nFIB Sub-parts Configuration:\n" + "\n".join(fib_configs)
            replacements['{{FIB_SUBPART_SPECS}}'] = fib_note
        else:
            replacements['{{FIB_SUBPART_SPECS}}'] = ""
    

    # Special handling for case study questions
    if 'case_study' in template_key.lower():
        # For case study, we need to inject per-question subpart configuration
        # This will be handled differently - we'll add it to additional notes
        case_study_configs = []
        for idx, q in enumerate(questions, 1):
            if 'subparts' in q:
                subparts = q['subparts']
                subpart_strs = []
                for sp in subparts:
                    part = sp.get('part', 'a')
                    dok = sp.get('dok', 1)
                    marks = sp.get('marks', 1.0)
                    subpart_strs.append(f"({part}) DOK {dok}, Marks {marks}")
                
                config_str = f"Question {idx}: {len(subparts)} sub-parts - {', '.join(subpart_strs)}"
                case_study_configs.append(config_str)
        
        if case_study_configs:
            case_study_note = "\n\nCase Study Sub-parts Configuration:\n" + "\n".join(case_study_configs)
            replacements['{{Additional_Notes}}'] = replacements['{{Additional_Notes}}'] + case_study_note
    
    # Replace placeholders
    prompt = template
    
    # IMPORTANT: Replace {{New_Concept}} and {{Additional_Notes}} in reference_instruction FIRST
    # before injecting it into the prompt
    new_concept_text = general_config.get('new_concept', 'N/A')
    additional_notes_text = general_config.get('additional_notes', 'None')
    
    if reference_instruction:
        reference_instruction = reference_instruction.replace('{{New_Concept}}', new_concept_text)
        reference_instruction = reference_instruction.replace('{{Additional_Notes}}', additional_notes_text)
    
    # Inject reference instruction at the beginning
    # Try multiple injection points to handle different template formats
    if reference_instruction:
        # Try injection point 1: After "## INPUT DETAILS:"
        if '## INPUT DETAILS:' in prompt:
            prompt = prompt.replace('## INPUT DETAILS:', reference_instruction + '\n\n    ## INPUT DETAILS:')
        # Try injection point 2: After "### Inputs (Provided by User)" (for assertion_reasoning)
        elif '### Inputs (Provided by User)' in prompt:
            prompt = prompt.replace('### Inputs (Provided by User)', reference_instruction + '\n\n  ### Inputs (Provided by User)')
        # Fallback: inject at the very beginning after the first line
        else:
            lines = prompt.split('\n', 1)
            if len(lines) > 1:
                prompt = lines[0] + '\n' + reference_instruction + '\n\n' + lines[1]
    
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    
    logger.info(f"Prompt built: {len(prompt)} characters, Files: {len(files) > 0}")
    
    # Log topics for debugging
    topics_list = [q.get('topic', 'NO_TOPIC') for q in questions]
    logger.info(f"Topics in this batch: {topics_list}")
    
    return {
        'prompt': prompt,
        'files': files,
        'file_metadata': {
            'source_type': source_type,
            'filenames': filenames
        }
    }

